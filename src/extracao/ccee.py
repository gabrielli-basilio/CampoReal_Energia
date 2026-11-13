"""Extracao do PLD horario da CCEE (via API CKAN ou arquivos CSV locais na pasta dados/)."""
import csv
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from psycopg2.extras import Json, execute_values

from src.comum.config import carregar_config
from src.comum.conexao import conectar, garantir_tabelas
from src.comum.log import Execucao, criar_logger
from src.comum.retry import ErroExtracao, pegar_json

SUBMERCADOS = {
    "SUDESTE": "SE", "SE": "SE", "SUDESTE/CENTRO-OESTE": "SE",
    "SUL": "S", "S": "S",
    "NORDESTE": "NE", "NE": "NE",
    "NORTE": "N", "N": "N",
}

COLUNAS = {
    "mes": ["MES_REFERENCIA", "MES_REF", "MES"],
    "submercado": ["SUBMERCADO", "COD_SUBMERCADO"],
    "dia": ["DIA", "DATA"],
    "hora": ["HORA", "HORA_DIA"],
    "pld": ["PLD_HORA", "PLD", "PRECO"],
}


# ---------- funcoes puras ----------

def achar_coluna(registro, apelidos):
    mapa = {str(k).upper().strip("\ufeff"): v for k, v in registro.items()}
    for nome in apelidos:
        if nome in mapa:
            return mapa[nome]
    raise ErroExtracao(f"Mudanca de colunas: nenhuma de {apelidos} em {list(registro.keys())}")


def converter_registro(registro):
    sub_bruto = str(achar_coluna(registro, COLUNAS["submercado"])).strip().upper()
    if sub_bruto not in SUBMERCADOS:
        raise ErroExtracao(f"Submercado desconhecido: {sub_bruto!r}")
    cod_sub = SUBMERCADOS[sub_bruto]

    dia = str(achar_coluna(registro, COLUNAS["dia"])).strip()
    hora = int(float(achar_coluna(registro, COLUNAS["hora"])))
    if not 0 <= hora <= 23:
        raise ErroExtracao(f"Hora fora de 0-23: {hora}")

    if re.match(r"^\d{4}-\d{2}-\d{2}", dia):
        base = datetime.strptime(dia[:10], "%Y-%m-%d")
    elif re.match(r"^\d{2}/\d{2}/\d{4}", dia):
        base = datetime.strptime(dia[:10], "%d/%m/%Y")
    else:
        mes = str(achar_coluna(registro, COLUNAS["mes"])).strip()
        base = datetime(int(mes[:4]), int(mes[4:6]), int(float(dia)))
    data_hora = base + timedelta(hours=hora)

    bruto = achar_coluna(registro, COLUNAS["pld"])
    pld = None if bruto in (None, "") else round(float(str(bruto).replace(",", ".")), 2)
    return cod_sub, data_hora, pld


def paginar(buscar_pagina, limite, offset_inicial=0):
    offset = offset_inicial
    while True:
        registros, total = buscar_pagina(offset, limite)
        if not registros:
            return
        yield offset, registros
        offset += len(registros)
        if offset >= total:
            return


# ---------- leitura de CSV local ----------

def ler_csv_local(caminho_csv, tamanho_lote=5000):
    """Lê o CSV baixado do portal da CCEE detectando delimitador (; ou ,) e encoding."""
    for enc in ("utf-8-sig", "latin-1"):
        try:
            with open(caminho_csv, mode="r", encoding=enc) as f:
                amostra = f.read(4096)
                f.seek(0)
                delimitador = ";" if amostra.count(";") > amostra.count(",") else ","
                leitor = csv.DictReader(f, delimiter=delimitador)
                registros = list(leitor)
                return registros
        except UnicodeDecodeError:
            continue
    raise ErroExtracao(f"Nao foi possivel decodificar o arquivo {caminho_csv}")


# ---------- acesso a API ----------

def descobrir_recursos(cfg, logger):
    c = cfg["ccee"]
    dados = pegar_json(c["url_pacote"], {"id": c["dataset"]}, c["timeout"],
                       c["tentativas"], c["espera_segundos"], logger)
    achados = {}
    for rec in dados["result"].get("resources", []):
        texto = " ".join(str(rec.get(k, "")) for k in ("name", "description", "url"))
        for ano in re.findall(r"20\d{2}", texto):
            achados.setdefault(int(ano), rec["id"])
    return achados


def total_da_api(cfg, resource_id, logger):
    c = cfg["ccee"]
    dados = pegar_json(c["url_busca"], {"resource_id": resource_id, "limit": 1},
                       c["timeout"], c["tentativas"], c["espera_segundos"], logger)
    return dados["result"].get("total", 0)


def criar_buscador(cfg, resource_id, logger):
    c = cfg["ccee"]

    def buscar(offset, limite):
        dados = pegar_json(
            c["url_busca"],
            {"resource_id": resource_id, "limit": limite, "offset": offset, "sort": "_id asc"},
            c["timeout"], c["tentativas"], c["espera_segundos"], logger,
        )
        res = dados["result"]
        return res.get("records", []), res.get("total", 0)

    return buscar


# ---------- banco ----------

def gravar_raw(conn, resource_id, ano, offset, registros):
    linhas = [(resource_id, ano, offset + i, Json(r)) for i, r in enumerate(registros)]
    with conn.cursor() as cur:
        execute_values(
            cur,
            "INSERT INTO raw.pld_horario (resource_id, ano, posicao, registro) VALUES %s "
            "ON CONFLICT (resource_id, posicao) DO NOTHING",
            linhas,
        )
    conn.commit()


def raw_para_staging(conn, resource_id):
    with conn.cursor() as cur:
        cur.execute("SELECT registro FROM raw.pld_horario WHERE resource_id = %s ORDER BY posicao",
                    (resource_id,))
        brutos = [r[0] for r in cur.fetchall()]
    convertidos = {}
    for reg in brutos:
        sub, data_hora, pld = converter_registro(reg)
        convertidos[(sub, data_hora)] = pld
    linhas = [(s, d, p) for (s, d), p in convertidos.items()]
    with conn.cursor() as cur:
        execute_values(
            cur,
            "INSERT INTO staging.pld_horario (cod_submercado, data_hora, pld_rs_mwh) VALUES %s "
            "ON CONFLICT (cod_submercado, data_hora) DO UPDATE "
            "SET pld_rs_mwh = EXCLUDED.pld_rs_mwh, extraido_em = NOW()",
            linhas,
            page_size=5000,
        )
    conn.commit()
    return len(linhas)


def linhas_no_raw(conn, resource_id):
    with conn.cursor() as cur:
        cur.execute("SELECT COALESCE(MAX(posicao) + 1, 0) FROM raw.pld_horario WHERE resource_id = %s",
                    (resource_id,))
        return cur.fetchone()[0]


# ---------- execucao ----------

def extrair_ano(conn, cfg, ano, resource_id, logger, simular_falha=False):
    arquivo_local = Path("dados") / f"pld_horario_{ano}.csv"

    with Execucao("CCEE", f"PLD_HORARIO_{ano}") as ex:
        if arquivo_local.exists() and not simular_falha:
            logger.info("%s: lendo arquivo local %s", ano, arquivo_local)
            todos = ler_csv_local(arquivo_local)
            total = len(todos)
            ja_tem = linhas_no_raw(conn, resource_id)
            logger.info("%s: CSV tem %s registros, raw ja tem %s", ano, total, ja_tem)

            if ja_tem >= total:
                ex.status = "JA_COMPLETO"
                logger.info("%s: ja completo, nada a gravar", ano)
                return

            limite = cfg["ccee"]["limite_por_pagina"]
            for offset in range(ja_tem, total, limite):
                lote = todos[offset : offset + limite]
                gravar_raw(conn, resource_id, ano, offset, lote)
                ex.lidas += len(lote)
                ex.gravadas += len(lote)
                logger.info("%s: gravados %s de %s", ano, offset + len(lote), total)

            n = raw_para_staging(conn, resource_id)
            logger.info("%s: staging.pld_horario atualizado (%s linhas no ano)", ano, n)
            return

        total = total_da_api(cfg, resource_id, logger)
        if total == 0:
            raise ErroExtracao(f"Resposta vazia: a API nao retornou registros para {ano}")
        ja_tem = linhas_no_raw(conn, resource_id)
        logger.info("%s: API tem %s registros, raw ja tem %s", ano, total, ja_tem)

        if ja_tem >= total:
            ex.status = "JA_COMPLETO"
            logger.info("%s: ja completo, nada a baixar", ano)
            return

        buscar = criar_buscador(cfg, resource_id, logger)
        for offset, registros in paginar(buscar, cfg["ccee"]["limite_por_pagina"], ja_tem):
            gravar_raw(conn, resource_id, ano, offset, registros)
            ex.lidas += len(registros)
            ex.gravadas += len(registros)
            logger.info("%s: baixados %s de %s", ano, offset + len(registros), total)

        n = raw_para_staging(conn, resource_id)
        logger.info("%s: staging.pld_horario atualizado (%s linhas no ano)", ano, n)


def main(simular_falha=False):
    logger = criar_logger()
    cfg = carregar_config()
    if simular_falha:
        cfg["ccee"]["url_pacote"] = "https://ccee.invalid"
        cfg["ccee"]["url_busca"] = "https://ccee.invalid"
        cfg["ccee"]["tentativas"] = 2
        cfg["ccee"]["espera_segundos"] = 1
        logger.warning("MODO SIMULAR FALHA: a CCEE sera acessada num endereco invalido")

    conn = conectar()
    garantir_tabelas(conn)

    ids = {int(k): v for k, v in (cfg["ccee"].get("resource_ids") or {}).items()}
    descobertos = None
    erro_descoberta = None
    erros = 0

    for ano in cfg["ccee"]["anos"]:
        try:
            if ano not in ids:
                if descobertos is None and erro_descoberta is None:
                    try:
                        descobertos = descobrir_recursos(cfg, logger)
                    except Exception as e:
                        erro_descoberta = e
                if erro_descoberta is not None:
                    raise erro_descoberta
                if ano not in descobertos:
                    raise ErroExtracao(
                        f"Recurso nao encontrado para {ano}. Coloque o id em resource_ids no config.yaml"
                    )
                ids[ano] = descobertos[ano]
            extrair_ano(conn, cfg, ano, ids[ano], logger, simular_falha=simular_falha)
        except Exception as e:
            conn.rollback()
            erros += 1
            logger.error("%s: ERRO %s", ano, e)
    conn.close()
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main(simular_falha="--simular-falha" in sys.argv))