"""Limpeza: origem (campo_real_energia) -> staging, com uma decisão justificada por problema.

Regra do jogo: a origem NUNCA é alterada. Tudo que muda acontece no caminho até a
staging, e cada mudança fica registrada em qualidade.tratamento (e, quando o
registro é retirado, em qualidade.quarentena).

As 4 decisões:
  CORRIGIR    só quando há evidência no próprio dado (outra coluna, outra tabela,
              física da usina). Nada é imputado: nenhum valor é inventado.
  DESCARTAR   cópia que não acrescenta informação (duplicidade).
  QUARENTENA  registro que não dá para atribuir ou corrigir com segurança. Sai do
              caminho e fica guardado inteiro para análise humana.
  SINALIZAR   dado plausível ou impossível de corrigir sem inventar: segue para o DW
              com status SINALIZADO e uma flag explicando o motivo.

Status final de cada medição (usado em dim_status_qualidade do DW):
  OK < SINALIZADO < CORRIGIDO < ANULADO (vale o mais grave).
"""
import json
import re
from datetime import datetime

import pandas as pd
from psycopg2.extras import Json, execute_values

from src.qualidade.regras import UF_SUBMERCADO, configuracao  # noqa: F401  (UF_SUBMERCADO documenta o mapa)

RANK = {"OK": 0, "SINALIZADO": 1, "CORRIGIDO": 2, "ANULADO": 3}
PADRAO_COD = re.compile(r"^CRE-[A-Z]{3}-\d{3}$")

# UF de cada submercado do SIN (mesmo mapa usado na regra usina_uf_incoerente_submercado)
UF_DO_SUBMERCADO = {
    "SE": {"SP", "MG", "RJ", "ES", "GO", "DF", "MT", "MS", "RO", "AC"},
    "S": {"PR", "SC", "RS"},
    "NE": {"BA", "SE", "AL", "PE", "PB", "RN", "CE", "PI"},
    "N": {"PA", "TO", "MA", "AM", "AP", "RR"},
}
# Referência cadastral (IBGE) dos municípios das usinas: evidência independente para corrigir a UF
MUNICIPIO_UF = {
    "Capitão Leônidas Marques": "PR", "Caçador": "SC", "Santana do Livramento": "RS", "Janaúba": "MG",
    "Sertãozinho": "SP", "Bom Jesus da Lapa": "BA", "João Câmara": "RN", "Peixe": "TO",
    "Santo Antônio dos Lopes": "MA",
}


# ---------------------------------------------------------------- utilidades

def ler(conn, sql):
    with conn.cursor() as cur:
        cur.execute(sql)
        colunas = [c[0] for c in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=colunas)


def num(serie):
    return pd.to_numeric(serie, errors="coerce").astype(float)


def limpo(valor):
    """NaN/NaT -> None e tipos do pandas -> tipos do Python (para o psycopg2)."""
    if valor is None or (not isinstance(valor, (list, dict, str)) and pd.isna(valor)):
        return None
    if hasattr(valor, "item") and not isinstance(valor, (pd.Timestamp,)):
        try:
            return valor.item()
        except Exception:
            return valor
    if isinstance(valor, pd.Timestamp):
        return valor.to_pydatetime()
    return valor


def registro_json(linha):
    return {k: (None if (not isinstance(v, str) and pd.isna(v)) else (str(v) if isinstance(v, (pd.Timestamp, datetime)) else limpo(v)))
            for k, v in linha.items()}


class Registro:
    """Acumula tratamentos e quarentena para gravar no fim."""

    def __init__(self):
        self.tratamentos, self.quarentena = [], []

    def tratar(self, regra, tabela, chave, decisao, justificativa, antes=None, depois=None):
        self.tratamentos.append((regra, tabela, str(chave)[:120], decisao, justificativa,
                                 None if antes is None else str(antes), None if depois is None else str(depois)))

    def quarentenar(self, tabela, regra, motivo, linha, chave):
        self.quarentena.append((tabela, regra, motivo, registro_json(linha)))
        self.tratar(regra, tabela, chave, "QUARENTENA", motivo)


def pior(a, b):
    return a if RANK[a] >= RANK[b] else b


# ---------------------------------------------------------------- cadastro

def limpar_usina(usina, fonte, reg, logger):
    u = usina.copy()
    u["cod_usina"] = u["cod_usina"].astype(str).str.strip()
    u["latitude"], u["longitude"], u["potencia_mw"] = num(u["latitude"]), num(u["longitude"]), num(u["potencia_mw"])
    u["cod_submercado"] = u["cod_submercado"].astype(str).str.strip()
    u["flags"] = ""

    # Unicidade: mesma fonte + submercado + coordenada (sem sinal) + potência
    u["_grupo"] = list(zip(u["id_fonte"], u["cod_submercado"], u["latitude"].abs().round(4),
                           u["longitude"].round(4), u["potencia_mw"]))
    u["_valido"] = u["cod_usina"].apply(lambda c: bool(PADRAO_COD.match(c)))
    descartar = []
    for _, grupo in u.groupby("_grupo"):
        if len(grupo) > 1:
            manter = grupo.sort_values(["_valido", "id_usina"], ascending=[False, True]).iloc[0]
            for _, extra in grupo.drop(manter.name).iterrows():
                descartar.append(extra.name)
                reg.tratar("usina_duplicada", "usina", extra["cod_usina"], "DESCARTAR",
                           f"Mesma fonte, submercado, coordenada e potência de {manter['cod_usina']}; código fora do "
                           f"padrão CRE-XXX-999, município vazio e nome com espaço sobrando. Cópia sem informação nova.",
                           antes=f"{extra['cod_usina']} / '{extra['nome']}'", depois=f"mantida {manter['cod_usina']}")
    u = u.drop(index=descartar)

    # Validade: latitude com sinal trocado
    for i, r in u.iterrows():
        dentro = lambda la, lo: -34 <= la <= 6 and -74 <= lo <= -34  # noqa: E731
        if not dentro(r["latitude"], r["longitude"]) and dentro(-r["latitude"], r["longitude"]):
            u.at[i, "latitude"] = -r["latitude"]
            reg.tratar("usina_coordenada_fora_do_brasil", "usina", r["cod_usina"], "CORRIGIR",
                       f"Latitude {r['latitude']} cai fora do Brasil; com o sinal invertido o ponto fica em "
                       f"{r['municipio']}/{r['uf']}, coerente com UF e submercado. Único erro possível é o sinal.",
                       antes=r["latitude"], depois=-r["latitude"])
            u.at[i, "flags"] += "latitude_corrigida;"

    # Consistência: UF x submercado
    for i, r in u.iterrows():
        if r["uf"].strip() not in UF_DO_SUBMERCADO.get(r["cod_submercado"], set()):
            uf_ref = MUNICIPIO_UF.get(str(r["municipio"]).strip())
            if uf_ref and uf_ref in UF_DO_SUBMERCADO[r["cod_submercado"]]:
                u.at[i, "uf"] = uf_ref
                reg.tratar("usina_uf_incoerente_submercado", "usina", r["cod_usina"], "CORRIGIR",
                           f"UF {r['uf']} não pertence ao submercado {r['cod_submercado']}; o município "
                           f"{r['municipio']} fica em {uf_ref} (referência IBGE) e a coordenada confirma.",
                           antes=r["uf"], depois=uf_ref)
                u.at[i, "flags"] += "uf_corrigida;"
            else:
                reg.tratar("usina_uf_incoerente_submercado", "usina", r["cod_usina"], "SINALIZAR",
                           "UF incoerente com o submercado e sem referência independente para corrigir.", antes=r["uf"])
                u.at[i, "flags"] += "uf_incoerente;"

    # Validade: início de operação no futuro
    hoje = pd.Timestamp.today().date()
    for i, r in u.iterrows():
        if pd.Timestamp(r["data_inicio_operacao"]).date() > hoje:
            reg.tratar("usina_data_inicio_futura", "usina", r["cod_usina"], "SINALIZAR",
                       "Início de operação no futuro, mas a usina tem medições em 2025. A data correta é desconhecida: "
                       "mantida como veio e sinalizada, sem inventar outra.", antes=r["data_inicio_operacao"])
            u.at[i, "flags"] += "data_inicio_futura;"

    fonte_cod = dict(zip(fonte["id_fonte"], fonte["cod_fonte"]))
    u["cod_fonte"] = u["id_fonte"].map(fonte_cod)
    return u


# ---------------------------------------------------------------- paradas

def limpar_paradas(parada, usina_limpa, reg):
    p = parada.copy()
    cod = dict(zip(usina_limpa["id_usina"], usina_limpa["cod_usina"]))
    manter = []
    for i, r in p.iterrows():
        chave = f"parada {r['id_parada']} ({cod.get(r['id_usina'], r['id_usina'])})"
        if r["id_usina"] not in cod:
            reg.quarentenar("parada_usina", "parada_usina_inexistente",
                            "Parada de usina que não existe no cadastro.", r, chave)
        elif r["fim"] < r["inicio"]:
            reg.quarentenar("parada_usina", "parada_intervalo_invertido",
                            f"Fim ({r['fim']}) anterior ao início ({r['inicio']}). Não dá para saber se o erro está "
                            f"no início, no fim ou no dia; aplicar a parada às medições seria chutar.", r, chave)
        else:
            manter.append(i)
    p = p.loc[manter].copy()
    p["cod_usina"] = p["id_usina"].map(cod)
    return p


# ---------------------------------------------------------------- medições

def trechos_de_horas(horas):
    """Agrupa horas (ordenadas) em trechos contínuos -> lista de (inicio, fim, n)."""
    trechos, ini, ant = [], None, None
    for h in horas:
        if ini is None:
            ini = ant = h
        elif h - ant == pd.Timedelta(hours=1):
            ant = h
        else:
            trechos.append((ini, ant, int((ant - ini) / pd.Timedelta(hours=1)) + 1))
            ini = ant = h
    if ini is not None:
        trechos.append((ini, ant, int((ant - ini) / pd.Timedelta(hours=1)) + 1))
    return trechos


def limpar_medicoes(medicao, usina_limpa, parada_limpa, conf, reg, logger):
    m = medicao.copy()
    m["energia"] = num(m["energia_mwh"])
    m["disp"] = num(m["disponibilidade_mw"])
    m["id_usina"] = pd.to_numeric(m["id_usina"], errors="coerce").astype("Int64")
    m["data_hora"] = pd.to_datetime(m["data_hora"])
    m["recebido_em"] = pd.to_datetime(m["recebido_em"])
    m["status"], m["flags"] = "OK", ""
    cod = dict(zip(usina_limpa["id_usina"], usina_limpa["cod_usina"]))
    pot = dict(zip(usina_limpa["id_usina"], usina_limpa["potencia_mw"]))
    fonte_de = dict(zip(usina_limpa["id_usina"], usina_limpa["cod_fonte"]))
    tol = conf["tolerancia_potencia"]

    def chave(r):
        return f"{cod.get(r['id_usina'], 'usina ' + str(r['id_usina']))} {r['data_hora']:%Y-%m-%d %H:%M} (id_medicao {r['id_medicao']})"

    def marcar(idx, status, flag):
        m.loc[idx, "status"] = pior(m.at[idx, "status"], status)
        if flag not in m.at[idx, "flags"]:
            m.at[idx, "flags"] += flag + ";"

    # 1. Integridade: sem usina e usina inexistente -> quarentena
    saiu = []
    for i, r in m.iterrows():
        if pd.isna(r["id_usina"]):
            reg.quarentenar("medicao_geracao", "medicao_sem_usina",
                            "Medição MANUAL sem id_usina: não dá para atribuir a energia a nenhuma usina.", r, chave(r))
            saiu.append(i)
        elif int(r["id_usina"]) not in cod:
            reg.quarentenar("medicao_geracao", "medicao_usina_inexistente",
                            f"id_usina {int(r['id_usina'])} não existe no cadastro. Os valores repetem as leituras de outra "
                            f"usina em outro dia, mas sem evidência para atribuir; fica guardado para análise.", r, chave(r))
            saiu.append(i)
    m = m.drop(index=saiu)

    # 2. Validade: data fora do período
    saiu = []
    for i, r in m[(m["data_hora"] < pd.Timestamp("2025-01-01")) | (m["data_hora"] > pd.Timestamp.now())].iterrows():
        candidata = r["data_hora"].replace(year=r["recebido_em"].year) if pd.notna(r["recebido_em"]) else None
        existe = candidata is not None and ((m["id_usina"] == r["id_usina"]) & (m["data_hora"] == candidata)).any()
        motivo = (f"data_hora no ano {r['data_hora'].year}. O recebimento em {r['recebido_em']} sugere {candidata}, "
                  f"mas essa hora já tem leitura automática; é provável lançamento manual duplicado com ano digitado "
                  f"errado. Não reinserido.") if existe else \
                 f"data_hora no ano {r['data_hora'].year} (futuro) e sem leitura equivalente para corrigir."
        reg.quarentenar("medicao_geracao", "medicao_data_fora_do_periodo", motivo, r, chave(r))
        saiu.append(i)
    m = m.drop(index=saiu)

    # 3. Unicidade: mesma usina e mesma hora
    m["_prio"] = (m["origem"].fillna("") != "SCADA").astype(int)
    m = m.sort_values(["id_usina", "data_hora", "_prio", "recebido_em", "id_medicao"])
    repetida = m.duplicated(["id_usina", "data_hora"], keep="first")
    mantida = m[~repetida].set_index(["id_usina", "data_hora"])["energia"]
    for i, r in m[repetida].iterrows():
        ref = mantida.get((r["id_usina"], r["data_hora"]))
        if r["origem"] != "SCADA":
            just = (f"Lançamento {r['origem']} sobre uma leitura automática da mesma hora, {r['energia']:.3f} contra "
                    f"{ref:.3f} MWh. Prevalece o SCADA; o manual não tem aprovação nem evidência.")
        else:
            just = (f"Cópia da mesma leitura reprocessada pela integração (recebida em {r['recebido_em']}); "
                    f"valor idêntico ao original, sem informação nova.")
        reg.tratar("medicao_duplicada_usina_hora", "medicao_geracao", chave(r), "DESCARTAR", just,
                   antes=r["energia"], depois=ref)
    m = m[~repetida].copy()

    # 4. Valores impossíveis ou com evidência de erro
    m = m.sort_values(["id_usina", "data_hora"]).reset_index(drop=True)
    m["pot"] = m["id_usina"].map(pot).astype(float)
    original_nula = m["energia"].isna()
    base = m["energia"].where(m["energia"] <= m["pot"] * tol)
    vizinha = pd.concat([base.groupby(m["id_usina"]).shift(1), base.groupby(m["id_usina"]).shift(-1)], axis=1).mean(axis=1)

    for i, r in m[m["energia"] > m["pot"] * tol].iterrows():
        e, p = r["energia"], r["pot"]
        if e > p * conf["fator_kwh"] and e / 1000 <= p * tol:
            m.at[i, "energia"] = round(e / 1000, 3)
            marcar(i, "CORRIGIDO", "unidade_kwh_para_mwh")
            reg.tratar("medicao_unidade_suspeita_kwh", "medicao_geracao", chave(r), "CORRIGIR",
                       f"Energia {e:.0f} é {e / p:.0f}x a potência da usina ({p:.0f} MW) e a linha tem origem "
                       f"{r['origem']}: planilha digitada em kWh. Dividindo por 1000 o valor fica dentro da capacidade.",
                       antes=e, depois=m.at[i, "energia"])
        elif e / 10 <= p * tol and pd.notna(vizinha[i]) and abs(e / 10 - vizinha[i]) <= 0.2 * p:
            m.at[i, "energia"] = round(e / 10, 3)
            marcar(i, "CORRIGIDO", "virgula_deslocada")
            reg.tratar("medicao_acima_da_potencia_instalada", "medicao_geracao", chave(r), "CORRIGIR",
                       f"Energia {e:.1f} excede a potência ({p:.0f} MW). Dividida por 10 resulta {e / 10:.1f}, a menos de "
                       f"20% da potência da média das horas vizinhas ({vizinha[i]:.1f}): vírgula deslocada.",
                       antes=e, depois=m.at[i, "energia"])
        else:
            motivo = (f"Energia {e:.0f} MWh excede a potência instalada ({p:.0f} MW) e nenhuma escala conhecida "
                      f"(÷10, ÷1000) a aproxima das horas vizinhas. Valor impossível retirado (ANULADO, não substituído); "
                      f"o original fica na quarentena.")
            reg.quarentenar("medicao_geracao", "medicao_acima_da_potencia_instalada", motivo, r, chave(r))
            m.at[i, "energia"] = float("nan")
            marcar(i, "ANULADO", "pico_impossivel_anulado")

    for i, r in m[m["energia"] < 0].iterrows():
        marcar(i, "CORRIGIDO", "negativa_zerada")
        reg.tratar("medicao_energia_negativa", "medicao_geracao", chave(r), "CORRIGIR",
                   "Geração negativa não existe: é o consumo dos serviços auxiliares lançado como geração. A geração "
                   "da hora foi zero.", antes=r["energia"], depois=0)
        m.at[i, "energia"] = 0.0

    paradas = parada_limpa[["id_usina", "inicio", "fim", "motivo"]]
    for i, r in m[m["energia"] > 0].iterrows():
        hit = paradas[(paradas["id_usina"] == r["id_usina"]) & (paradas["inicio"] <= r["data_hora"]) & (r["data_hora"] <= paradas["fim"])]
        if len(hit):
            marcar(i, "CORRIGIDO", "geracao_em_parada_zerada")
            reg.tratar("medicao_geracao_durante_parada", "medicao_geracao", chave(r), "CORRIGIR",
                       f"Hora dentro da parada \"{hit.iloc[0]['motivo']}\" e com disponibilidade_mw = {r['disp']:.0f} na "
                       f"própria linha: duas fontes dizem que a usina não podia gerar.", antes=r["energia"], depois=0)
            m.at[i, "energia"] = 0.0

    solar = m["id_usina"].map(fonte_de) == "UFV"
    noite = (m["data_hora"].dt.hour < 5) | (m["data_hora"].dt.hour >= 20)
    for i, r in m[solar & noite & (m["energia"] > 0)].iterrows():
        marcar(i, "CORRIGIDO", "solar_noite_zerada")
        reg.tratar("medicao_solar_a_noite", "medicao_geracao", chave(r), "CORRIGIR",
                   "Usina solar não gera sem sol (hora local 20h-4h). Indício de relógio do medidor errado; a geração "
                   "desse horário é zero.", antes=r["energia"], depois=0)
        m.at[i, "energia"] = 0.0

    # 5. Sinalizações: segue para o DW, mas marcado
    for i, r in m[original_nula & (m["status"] != "ANULADO")].iterrows():
        marcar(i, "SINALIZADO", "energia_nula")
        reg.tratar("medicao_energia_nula", "medicao_geracao", chave(r), "SINALIZAR",
                   "Falha de comunicação do medidor. Não há como saber a geração: mantida nula, sem imputar.")

    seq = m.sort_values(["id_usina", "data_hora"])
    novo = ((seq["energia"] != seq["energia"].shift()) | (seq["id_usina"] != seq["id_usina"].shift())
            | ((seq["data_hora"] - seq["data_hora"].shift()) != pd.Timedelta(hours=1)))
    corrida = novo.cumsum()
    tamanho = seq.groupby(corrida)["energia"].transform("size")
    for i, r in seq[(tamanho >= conf["travado_min_horas"]) & (seq["energia"] > 0)].iterrows():
        marcar(i, "SINALIZADO", "medidor_travado")
        reg.tratar("medicao_medidor_travado", "medicao_geracao", chave(r), "SINALIZAR",
                   f"Mesma leitura ({r['energia']:.3f}) por {int(tamanho[i])} horas seguidas. O valor é plausível, então "
                   f"não há evidência de qual seria o correto: só sinalizado.", antes=r["energia"])

    for i, r in m[m["recebido_em"] < m["data_hora"]].iterrows():
        marcar(i, "SINALIZADO", "recebido_antes_da_medicao")
        reg.tratar("medicao_recebido_antes_da_medicao", "medicao_geracao", chave(r), "SINALIZAR",
                   f"recebido_em ({r['recebido_em']}) anterior à hora medida: relógio do servidor errado. A energia não "
                   f"é afetada; só o carimbo de recebimento não é confiável.")

    atraso = (m["recebido_em"] - m["data_hora"]) > pd.Timedelta(hours=conf["sla_atraso_horas"])
    for i, r in m[atraso].iterrows():
        marcar(i, "SINALIZADO", "integracao_atrasada")
        dias = (r["recebido_em"] - r["data_hora"]).days
        reg.tratar("medicao_atraso_integracao", "medicao_geracao", chave(r), "SINALIZAR",
                   f"Dado recebido {dias} dias depois da hora medida (limite {conf['sla_atraso_horas']} h). O valor é "
                   f"válido; o atraso afeta a atualidade, não o resultado.")

    for i, r in m[(m["origem"].fillna("") != "SCADA")].iterrows():
        marcar(i, "SINALIZADO", "lancamento_manual")
        reg.tratar("medicao_lancamento_manual", "medicao_geracao", chave(r), "SINALIZAR",
                   f"Origem {r['origem']}: lançamento manual sem aprovação. Mantido como informação de auditoria.")

    # 6. Completude: horas que nunca chegaram (não existe linha para marcar: registra o buraco)
    p = conf["periodo_origem"]
    grade = pd.date_range(p["inicio"], p["fim"], freq="h")
    for id_usina, codigo in cod.items():
        if not PADRAO_COD.match(codigo):
            continue
        presentes = set(m.loc[m["id_usina"] == id_usina, "data_hora"])
        faltantes = [h for h in grade if h not in presentes]
        for ini, fim, n in trechos_de_horas(faltantes):
            reg.tratar("medicao_horas_faltantes", "medicao_geracao", f"{codigo} {ini:%Y-%m-%d %H:%M} a {fim:%Y-%m-%d %H:%M}",
                       "SINALIZAR", f"{n} hora(s) sem medição. Não preenchidas: criar geração onde não há leitura seria "
                                    f"inventar dado.", depois=f"{n} h")
    ultimas = m.groupby("id_usina")["data_hora"].max()
    corte = ultimas.max() - pd.Timedelta(hours=24)
    for id_usina, mx in ultimas.items():
        if mx < corte:
            reg.tratar("usina_sem_dados_recentes", "medicao_geracao", cod[id_usina], "SINALIZAR",
                       f"Última medição em {mx}, mais de 24 h antes da última do conjunto ({ultimas.max()}): a usina "
                       f"parou de enviar dados.", depois=str(mx))
    return m


# ---------------------------------------------------------------- gravação

def gravar_staging(conn, usina, parada, medicao):
    with conn.cursor() as cur:
        cur.execute("TRUNCATE staging.medicao_geracao, staging.parada_usina, staging.usina")
        execute_values(cur, """INSERT INTO staging.usina (id_usina, cod_usina, nome, id_fonte, cod_fonte, cod_submercado,
                               uf, municipio, latitude, longitude, potencia_mw, data_inicio_operacao, situacao,
                               flags_qualidade) VALUES %s""",
                       [tuple(limpo(v) for v in (r.id_usina, r.cod_usina, str(r.nome).strip(), r.id_fonte, r.cod_fonte,
                                                 r.cod_submercado, str(r.uf).strip(), str(r.municipio).strip(), r.latitude,
                                                 r.longitude, r.potencia_mw, r.data_inicio_operacao, r.situacao,
                                                 r.flags.rstrip(";") or None)) for r in usina.itertuples()])
        execute_values(cur, "INSERT INTO staging.parada_usina (id_parada, id_usina, cod_usina, inicio, fim, tipo, motivo) VALUES %s",
                       [tuple(limpo(v) for v in (r.id_parada, r.id_usina, r.cod_usina, r.inicio, r.fim, r.tipo, r.motivo))
                        for r in parada.itertuples()])
        cod = dict(zip(usina["id_usina"], usina["cod_usina"]))
        execute_values(cur, """INSERT INTO staging.medicao_geracao (id_medicao, id_usina, cod_usina, data_hora, energia_mwh,
                               disponibilidade_mw, origem, recebido_em, status_qualidade, flags_qualidade) VALUES %s""",
                       [(int(r.id_medicao), int(r.id_usina), cod[int(r.id_usina)], limpo(r.data_hora), limpo(r.energia),
                         limpo(r.disp), r.origem, limpo(r.recebido_em), r.status, r.flags.rstrip(";") or None)
                        for r in medicao.itertuples()], page_size=5000)


def gravar_registros(conn, reg, id_execucao):
    with conn.cursor() as cur:
        cur.execute("TRUNCATE qualidade.tratamento, qualidade.quarentena")
        execute_values(cur, """INSERT INTO qualidade.tratamento (id_execucao, regra, tabela, chave, decisao, justificativa,
                               valor_antes, valor_depois) VALUES %s""",
                       [(id_execucao,) + t for t in reg.tratamentos], page_size=2000)
        execute_values(cur, "INSERT INTO qualidade.quarentena (id_execucao, tabela, regra, motivo, registro) VALUES %s",
                       [(id_execucao, t, r, mo, Json(rg, dumps=lambda o: json.dumps(o, default=str)))
                        for t, r, mo, rg in reg.quarentena])


def executar_limpeza(conn, cfg, logger, id_execucao):
    origem = (cfg.get("origem") or {}).get("schema", "campo_real_energia")
    conf = configuracao(cfg)
    usina = ler(conn, f"SELECT * FROM {origem}.usina ORDER BY id_usina")
    fonte = ler(conn, f"SELECT * FROM {origem}.fonte_energia")
    parada = ler(conn, f"SELECT * FROM {origem}.parada_usina ORDER BY id_parada")
    medicao = ler(conn, f"SELECT * FROM {origem}.medicao_geracao ORDER BY id_medicao")
    logger.info("Origem lida: %s usinas, %s paradas, %s medições", len(usina), len(parada), len(medicao))

    reg = Registro()
    usina_l = limpar_usina(usina, fonte, reg, logger)
    parada_l = limpar_paradas(parada, usina_l, reg)
    medicao_l = limpar_medicoes(medicao, usina_l, parada_l, conf, reg, logger)

    gravar_staging(conn, usina_l, parada_l, medicao_l)
    gravar_registros(conn, reg, id_execucao)
    conn.commit()
    resumo = pd.Series([t[3] for t in reg.tratamentos]).value_counts().to_dict()
    logger.info("Staging gravada: %s usinas, %s paradas, %s medições. Tratamentos: %s",
                len(usina_l), len(parada_l), len(medicao_l), resumo)
    return {"usinas": len(usina_l), "paradas": len(parada_l), "medicoes": len(medicao_l), "tratamentos": resumo}
