"""Extracao do clima horario do Open-Meteo (archive-api) nas coordenadas das usinas.

O clima so e baixado DEPOIS da limpeza do cadastro: uma usina tem latitude com
sinal trocado (cairia fora do Brasil) e existe uma usina duplicada.

Uso:  python -m src.extracao.clima
"""
import re
import sys
import time
from datetime import date, datetime

from psycopg2.extras import Json, execute_values

from src.comum.config import carregar_config
from src.comum.conexao import conectar, garantir_tabelas
from src.comum.log import Execucao, criar_logger
from src.comum.retry import ErroExtracao, pegar_json

VARIAVEIS = ["temperature_2m", "shortwave_radiation", "wind_speed_100m", "precipitation"]
PADRAO_COD = re.compile(r"^CRE-[A-Z]{3}-\d{3}$")


# ---------- funcoes puras (testaveis sem internet) ----------

def dentro_do_brasil(lat, lon):
    return -34.0 <= lat <= 6.0 and -74.0 <= lon <= -34.0


def ajustar_usina(cod, lat, lon):
    """Devolve (cod, lat, lon) valido ou None se a usina deve ficar de fora.

    - codigo fora do padrao (ex.: CRE-EOL-07, cadastro duplicado) -> fora
    - latitude positiva onde o ponto com sinal invertido cai no Brasil -> inverte o sinal
    - ponto ainda fora do Brasil -> fora
    """
    cod = str(cod).strip()
    if not PADRAO_COD.match(cod):
        return None
    lat, lon = float(lat), float(lon)
    if not dentro_do_brasil(lat, lon) and dentro_do_brasil(-lat, lon):
        lat = -lat
    if not dentro_do_brasil(lat, lon):
        return None
    return cod, lat, lon


def normalizar_clima(resposta):
    """JSON do Open-Meteo -> lista de (data_hora, temp, radiacao, vento, chuva)."""
    if "hourly" not in resposta:
        raise ErroExtracao("Resposta vazia: Open-Meteo nao devolveu o bloco 'hourly'")
    h = resposta["hourly"]
    faltando = [c for c in ["time"] + VARIAVEIS if c not in h]
    if faltando:
        raise ErroExtracao(f"Mudanca de colunas: faltam {faltando} na resposta do Open-Meteo")
    if not h["time"]:
        raise ErroExtracao("Resposta vazia: lista de horas sem registros")
    linhas = []
    for i, t in enumerate(h["time"]):
        linhas.append((
            datetime.strptime(t, "%Y-%m-%dT%H:%M"),
            h["temperature_2m"][i],
            h["shortwave_radiation"][i],
            h["wind_speed_100m"][i],
            h["precipitation"][i],
        ))
    return linhas


def horas_esperadas(inicio, fim):
    return ((fim - inicio).days + 1) * 24


# ---------- banco ----------

def carregar_usinas(conn, cfg, logger):
    """Usa staging.usina. Se nao existir ainda, le a origem e aplica o ajuste minimo."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('staging.usina')")
        existe = cur.fetchone()[0] is not None
    brutas = None
    if existe:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT cod_usina, latitude, longitude FROM staging.usina")
                brutas = cur.fetchall()
            logger.info("Usinas lidas de staging.usina (cadastro tratado)")
        except Exception as e:
            conn.rollback()
            logger.warning("staging.usina existe mas nao deu para ler (%s). Usando a origem.", e)
    if brutas is None:
        schema = cfg["origem"]["schema"]
        with conn.cursor() as cur:
            cur.execute(f"SELECT cod_usina, latitude, longitude FROM {schema}.usina")
            brutas = cur.fetchall()
        logger.warning("staging.usina indisponivel: lendo a origem com ajuste minimo de cadastro")
    usinas = {}
    for cod, lat, lon in brutas:
        ok = ajustar_usina(cod, lat, lon)
        if ok is None:
            logger.warning("Usina %s ignorada (codigo fora do padrao ou fora do Brasil)", cod)
        else:
            usinas[ok[0]] = ok
    return sorted(usinas.values())


def linhas_de_clima(conn, cod):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM staging.clima_horario WHERE cod_usina = %s", (cod,))
        return cur.fetchone()[0]


def gravar(conn, cod, lat, lon, ini, fim, resposta, linhas):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO raw.clima (cod_usina, latitude, longitude, data_inicio, data_fim, resposta)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (cod_usina, data_inicio, data_fim)
               DO UPDATE SET resposta = EXCLUDED.resposta, extraido_em = NOW()""",
            (cod, lat, lon, ini, fim, Json(resposta)),
        )
        execute_values(
            cur,
            """INSERT INTO staging.clima_horario
               (cod_usina, data_hora, temperatura_c, radiacao_wm2, vento_100m_kmh, chuva_mm) VALUES %s
               ON CONFLICT (cod_usina, data_hora) DO UPDATE SET
                 temperatura_c = EXCLUDED.temperatura_c, radiacao_wm2 = EXCLUDED.radiacao_wm2,
                 vento_100m_kmh = EXCLUDED.vento_100m_kmh, chuva_mm = EXCLUDED.chuva_mm,
                 extraido_em = NOW()""",
            [(cod,) + l for l in linhas],
            page_size=5000,
        )
    conn.commit()


# ---------- execucao ----------

def extrair_usina(conn, cfg, cod, lat, lon, logger):
    o = cfg["open_meteo"]
    ini = date.fromisoformat(o["data_inicio"])
    fim = date.fromisoformat(o["data_fim"])
    esperado = horas_esperadas(ini, fim)

    with Execucao("OPEN-METEO", cod) as ex:
        if linhas_de_clima(conn, cod) >= esperado:
            ex.status = "JA_COMPLETO"
            logger.info("%s: clima ja completo (%s horas)", cod, esperado)
            return False  # nao chamou a API

        params = {
            "latitude": lat, "longitude": lon,
            "start_date": ini.isoformat(), "end_date": fim.isoformat(),
            "hourly": ",".join(VARIAVEIS), "timezone": o["fuso"],
        }
        resposta = pegar_json(o["url"], params, o["timeout"], o["tentativas"],
                              o["espera_segundos"], logger)
        linhas = normalizar_clima(resposta)
        ex.lidas = len(linhas)
        if len(linhas) != esperado:
            logger.warning("%s: esperado %s horas, vieram %s", cod, esperado, len(linhas))
        gravar(conn, cod, lat, lon, ini, fim, resposta, linhas)
        ex.gravadas = len(linhas)
        logger.info("%s: %s horas gravadas", cod, len(linhas))
        return True


def main():
    logger = criar_logger()
    cfg = carregar_config()
    conn = conectar()
    garantir_tabelas(conn)
    usinas = carregar_usinas(conn, cfg, logger)
    logger.info("%s usinas para baixar o clima", len(usinas))
    erros = 0
    for cod, lat, lon in usinas:
        try:
            chamou_api = extrair_usina(conn, cfg, cod, lat, lon, logger)
            if chamou_api:
                time.sleep(cfg["open_meteo"]["pausa_entre_usinas"])  # respeita o limite da API
        except Exception as e:
            conn.rollback()
            erros += 1
            logger.error("%s: ERRO %s", cod, e)
    conn.close()
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())