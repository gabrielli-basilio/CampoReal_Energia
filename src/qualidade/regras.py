"""Regras de qualidade de dados (32 regras, 7 dimensões).

Cada regra é uma função reutilizável marcada com o decorador

    @regra(nome, dimensão, tabela, descrição, decisão)

e recebe um Contexto. Devolve (registros_avaliados, registros_com_falha).

O mesmo código roda em duas fases:
  ANTES  -> sobre a origem (schema campo_real_energia), como os dados chegaram
  DEPOIS -> sobre a staging já limpa (schema staging)
Por isso as consultas usam {s} (schema operacional da fase) e {o} (origem, para
tabelas de domínio como fonte_energia e submercado). PLD e clima já vivem na
staging e são avaliados igualmente nas duas fases.

Dimensões: Completude, Unicidade, Validade, Consistência, Acurácia,
Integridade referencial e Atualidade.
"""
from dataclasses import dataclass
from typing import Callable

PADRAO = {
    # período em que a origem deve ter medição horária (o banco fictício só tem 2025)
    "periodo_origem": {"inicio": "2025-01-01 00:00", "fim": "2025-12-31 23:00"},
    "sla_atraso_horas": 24,        # dado que chega depois disso está atrasado
    "travado_min_horas": 12,       # leituras idênticas seguidas a partir daqui = medidor travado
    "tolerancia_potencia": 1.001,  # energia acima de potência x 1 h x tolerância = impossível
    "fator_kwh": 100,              # energia acima de potência x fator = suspeita de unidade errada
    "faixas_clima": {              # limites físicos plausíveis para o Brasil
        "radiacao_wm2": [0, 1400],
        "vento_100m_kmh": [0, 200],
        "temperatura_c": [-10, 50],
        "chuva_mm": [0, 200],
    },
}

USINA_VALIDA = "cod_usina ~ '^CRE-[A-Z][A-Z][A-Z]-[0-9][0-9][0-9]$'"

REGRAS = []


@dataclass
class Regra:
    nome: str
    dimensao: str
    tabela: str
    descricao: str
    decisao: str
    funcao: Callable


def regra(nome, dimensao, tabela, descricao, decisao):
    def decorador(funcao):
        REGRAS.append(Regra(nome, dimensao, tabela, descricao, decisao, funcao))
        return funcao
    return decorador


def configuracao(cfg):
    """Mistura config.yaml (seção opcional 'qualidade') com os padrões."""
    conf = {k: (dict(v) if isinstance(v, dict) else v) for k, v in PADRAO.items()}
    for k, v in ((cfg or {}).get("qualidade") or {}).items():
        if isinstance(v, dict) and isinstance(conf.get(k), dict):
            conf[k].update(v)
        else:
            conf[k] = v
    return conf


class Contexto:
    def __init__(self, conn, schema, cfg, origem="campo_real_energia"):
        self.conn, self.s, self.o = conn, schema, origem
        self.cfg = cfg or {}
        self.conf = configuracao(cfg)

    def sql(self, texto):
        return texto.replace("{s}", self.s).replace("{o}", self.o)

    def linha(self, texto, params=None):
        with self.conn.cursor() as cur:
            cur.execute(self.sql(texto), params or {})
            return cur.fetchone()

    def contar(self, avaliados, falhas, params=None):
        """Roda duas contagens e devolve (avaliados, falhas)."""
        return (self.linha(avaliados, params)[0] or 0, self.linha(falhas, params)[0] or 0)

    def tem_linhas(self, tabela):
        return self.linha(f"SELECT EXISTS (SELECT 1 FROM {tabela})")[0]


# --------------------------------------------------------------------------
# COMPLETUDE: falta algum valor, hora, dia ou campo de cadastro?
# --------------------------------------------------------------------------

@regra("usina_campo_obrigatorio_vazio", "Completude", "usina",
       "Usina com nome, UF ou município vazio (cadastro feito às pressas).", "DESCARTAR")
def usina_campo_obrigatorio_vazio(ctx):
    return ctx.contar(
        "SELECT COUNT(*) FROM {s}.usina",
        "SELECT COUNT(*) FROM {s}.usina WHERE COALESCE(TRIM(nome), '') = '' "
        "OR COALESCE(TRIM(uf), '') = '' OR COALESCE(TRIM(municipio), '') = ''")


@regra("medicao_energia_nula", "Completude", "medicao_geracao",
       "Hora com energia_mwh nula (falha de comunicação do medidor).", "SINALIZAR")
def medicao_energia_nula(ctx):
    return ctx.contar("SELECT COUNT(*) FROM {s}.medicao_geracao",
                      "SELECT COUNT(*) FROM {s}.medicao_geracao WHERE energia_mwh IS NULL")


@regra("medicao_horas_faltantes", "Completude", "medicao_geracao",
       "Horas esperadas (usinas válidas x horas do período) sem nenhuma medição.", "SINALIZAR")
def medicao_horas_faltantes(ctx):
    p = ctx.conf["periodo_origem"]
    r = ctx.linha("""
        WITH u AS (SELECT id_usina FROM {s}.usina WHERE """ + USINA_VALIDA + """),
             h AS (SELECT generate_series(%(ini)s::timestamp, %(fim)s::timestamp, INTERVAL '1 hour') AS data_hora),
             e AS (SELECT u.id_usina, h.data_hora FROM u CROSS JOIN h)
        SELECT COUNT(*), COUNT(*) FILTER (WHERE m.id_usina IS NULL)
        FROM e LEFT JOIN (SELECT DISTINCT id_usina, data_hora FROM {s}.medicao_geracao) m
               ON m.id_usina = e.id_usina AND m.data_hora = e.data_hora""",
                  {"ini": p["inicio"], "fim": p["fim"]})
    return r[0], r[1]


@regra("pld_horas_faltantes", "Completude", "pld_horario",
       "Horas de PLD ausentes entre 01/01/2025 e a última hora publicada (4 submercados).", "SINALIZAR")
def pld_horas_faltantes(ctx):
    if not ctx.tem_linhas("staging.pld_horario"):
        return 0, 0
    r = ctx.linha("""
        SELECT (SELECT COUNT(*) FROM {o}.submercado)
               * (FLOOR(EXTRACT(EPOCH FROM (MAX(data_hora) - TIMESTAMP '2025-01-01 00:00')) / 3600) + 1)::BIGINT,
               COUNT(*)
        FROM staging.pld_horario""")
    esperado, existente = int(r[0]), int(r[1])
    return esperado, max(esperado - existente, 0)


@regra("clima_horas_faltantes", "Completude", "clima_horario",
       "Horas de clima ausentes por usina no período configurado em open_meteo.", "SINALIZAR")
def clima_horas_faltantes(ctx):
    if not ctx.tem_linhas("staging.clima_horario"):
        return 0, 0  # clima é baixado depois da limpeza: reavalie depois do pipeline completo
    om = ctx.cfg.get("open_meteo", {})
    ini, fim = om.get("data_inicio", "2025-01-01"), om.get("data_fim", "2025-12-31")
    r = ctx.linha("""
        SELECT (SELECT COUNT(*) FROM {s}.usina WHERE """ + USINA_VALIDA + """)
               * ((%(fim)s::date - %(ini)s::date + 1) * 24),
               (SELECT COUNT(*) FROM staging.clima_horario c
                 WHERE c.data_hora >= %(ini)s::date AND c.data_hora < %(fim)s::date + 1
                   AND c.cod_usina IN (SELECT cod_usina FROM {s}.usina WHERE """ + USINA_VALIDA + """))""",
                  {"ini": ini, "fim": fim})
    esperado, existente = int(r[0]), int(r[1])
    return esperado, max(esperado - existente, 0)


@regra("medicao_sem_usina", "Completude", "medicao_geracao",
       "Medição sem id_usina: não dá para saber de quem é a energia.", "QUARENTENA")
def medicao_sem_usina(ctx):
    return ctx.contar("SELECT COUNT(*) FROM {s}.medicao_geracao",
                      "SELECT COUNT(*) FROM {s}.medicao_geracao WHERE id_usina IS NULL")


# --------------------------------------------------------------------------
# UNICIDADE: o mesmo fato ou a mesma usina aparece mais de uma vez?
# --------------------------------------------------------------------------

@regra("usina_duplicada", "Unicidade", "usina",
       "Mesma usina cadastrada duas vezes (mesma fonte, submercado, coordenada e potência).", "DESCARTAR")
def usina_duplicada(ctx):
    return ctx.contar(
        "SELECT COUNT(*) FROM {s}.usina",
        "SELECT COUNT(*) - COUNT(DISTINCT (id_fonte, cod_submercado, ABS(latitude), longitude, potencia_mw)) "
        "FROM {s}.usina")


@regra("medicao_duplicada_usina_hora", "Unicidade", "medicao_geracao",
       "Mais de uma medição para a mesma usina na mesma hora (reprocessamento ou lançamento manual).", "DESCARTAR")
def medicao_duplicada_usina_hora(ctx):
    return ctx.contar(
        "SELECT COUNT(*) FROM {s}.medicao_geracao WHERE id_usina IS NOT NULL",
        "SELECT COUNT(*) - COUNT(DISTINCT (id_usina, data_hora)) FROM {s}.medicao_geracao "
        "WHERE id_usina IS NOT NULL")


@regra("pld_duplicado_submercado_hora", "Unicidade", "pld_horario",
       "Registros do raw da CCEE repetidos para o mesmo submercado e hora.", "DESCARTAR")
def pld_duplicado_submercado_hora(ctx):
    from src.extracao.ccee import converter_registro
    if ctx.linha("SELECT to_regclass('raw.pld_horario')")[0] is None:
        return 0, 0
    with ctx.conn.cursor() as cur:
        cur.execute("SELECT registro FROM raw.pld_horario")
        chaves = []
        for (reg,) in cur.fetchall():
            sub, data_hora, _ = converter_registro(reg)
            chaves.append((sub, data_hora))
    return len(chaves), len(chaves) - len(set(chaves))


@regra("parada_sobreposta", "Unicidade", "parada_usina",
       "Duas paradas da mesma usina cobrindo o mesmo intervalo de tempo.", "SINALIZAR")
def parada_sobreposta(ctx):
    return ctx.contar(
        "SELECT COUNT(*) FROM {s}.parada_usina",
        "SELECT COUNT(*) FROM {s}.parada_usina a JOIN {s}.parada_usina b "
        "ON a.id_usina = b.id_usina AND a.id_parada < b.id_parada "
        "AND a.inicio <= b.fim AND b.inicio <= a.fim "
        "WHERE a.fim >= a.inicio AND b.fim >= b.inicio")


# --------------------------------------------------------------------------
# VALIDADE: o valor está no domínio e nas regras (sinal, faixa, datas, limites)?
# --------------------------------------------------------------------------

@regra("medicao_energia_negativa", "Validade", "medicao_geracao",
       "Energia gerada negativa (consumo dos serviços auxiliares lançado como geração).", "CORRIGIR")
def medicao_energia_negativa(ctx):
    return ctx.contar("SELECT COUNT(*) FROM {s}.medicao_geracao",
                      "SELECT COUNT(*) FROM {s}.medicao_geracao WHERE energia_mwh < 0")


@regra("medicao_data_fora_do_periodo", "Validade", "medicao_geracao",
       "data_hora anterior a 01/01/2025 ou no futuro (erro de digitação no ano).", "QUARENTENA")
def medicao_data_fora_do_periodo(ctx):
    return ctx.contar("SELECT COUNT(*) FROM {s}.medicao_geracao",
                      "SELECT COUNT(*) FROM {s}.medicao_geracao "
                      "WHERE data_hora < TIMESTAMP '2025-01-01' OR data_hora > NOW()")


@regra("usina_data_inicio_futura", "Validade", "usina",
       "Início de operação no futuro para uma usina que já tem medições.", "SINALIZAR")
def usina_data_inicio_futura(ctx):
    return ctx.contar("SELECT COUNT(*) FROM {s}.usina",
                      "SELECT COUNT(*) FROM {s}.usina WHERE data_inicio_operacao > CURRENT_DATE")


@regra("usina_coordenada_fora_do_brasil", "Validade", "usina",
       "Latitude ou longitude fora do retângulo do Brasil (sinal trocado).", "CORRIGIR")
def usina_coordenada_fora_do_brasil(ctx):
    return ctx.contar("SELECT COUNT(*) FROM {s}.usina",
                      "SELECT COUNT(*) FROM {s}.usina WHERE latitude NOT BETWEEN -34 AND 6 "
                      "OR longitude NOT BETWEEN -74 AND -34")


@regra("parada_intervalo_invertido", "Validade", "parada_usina",
       "Parada com fim anterior ao início.", "QUARENTENA")
def parada_intervalo_invertido(ctx):
    return ctx.contar("SELECT COUNT(*) FROM {s}.parada_usina",
                      "SELECT COUNT(*) FROM {s}.parada_usina WHERE fim < inicio")


@regra("pld_fora_limites_regulatorios", "Validade", "pld_horario",
       "PLD abaixo do piso ou acima do teto horário da ANEEL do respectivo ano (config limites_pld).", "SINALIZAR")
def pld_fora_limites_regulatorios(ctx):
    if not ctx.tem_linhas("staging.pld_horario"):
        return 0, 0
    casos = []
    for ano, lim in (ctx.cfg.get("limites_pld") or {}).items():
        if lim and lim.get("piso") is not None and lim.get("teto") is not None:
            casos.append(f"WHEN {int(ano)} THEN (pld_rs_mwh < {float(lim['piso'])} OR pld_rs_mwh > {float(lim['teto'])})")
    if not casos:
        return ctx.contar("SELECT COUNT(*) FROM staging.pld_horario", "SELECT 0")
    expr = "CASE EXTRACT(YEAR FROM data_hora)::INT " + " ".join(casos) + " ELSE FALSE END"
    return ctx.contar("SELECT COUNT(*) FROM staging.pld_horario",
                      f"SELECT COUNT(*) FROM staging.pld_horario WHERE pld_rs_mwh IS NOT NULL AND {expr}")


@regra("clima_fora_de_faixa", "Validade", "clima_horario",
       "Radiação, vento, temperatura ou chuva fora da faixa física plausível.", "SINALIZAR")
def clima_fora_de_faixa(ctx):
    if not ctx.tem_linhas("staging.clima_horario"):
        return 0, 0
    cond = []
    for coluna, (lo, hi) in ctx.conf["faixas_clima"].items():
        cond.append(f"{coluna} < {lo} OR {coluna} > {hi}")
    return ctx.contar("SELECT COUNT(*) FROM staging.clima_horario",
                      "SELECT COUNT(*) FROM staging.clima_horario WHERE " + " OR ".join(cond))


# --------------------------------------------------------------------------
# CONSISTÊNCIA: os dados concordam entre si e com o mundo físico?
# --------------------------------------------------------------------------

UF_SUBMERCADO = """(VALUES ('SP','SE'),('MG','SE'),('RJ','SE'),('ES','SE'),('GO','SE'),('DF','SE'),('MT','SE'),
    ('MS','SE'),('RO','SE'),('AC','SE'),('PR','S'),('SC','S'),('RS','S'),('BA','NE'),('SE','NE'),('AL','NE'),
    ('PE','NE'),('PB','NE'),('RN','NE'),('CE','NE'),('PI','NE'),('PA','N'),('TO','N'),('MA','N'),('AM','N'),
    ('AP','N'),('RR','N')) AS m (uf, sub)"""


@regra("usina_uf_incoerente_submercado", "Consistência", "usina",
       "UF que não pertence ao submercado cadastrado da usina.", "CORRIGIR")
def usina_uf_incoerente_submercado(ctx):
    return ctx.contar(
        "SELECT COUNT(*) FROM {s}.usina",
        "SELECT COUNT(*) FROM {s}.usina u LEFT JOIN " + UF_SUBMERCADO +
        " ON m.uf = TRIM(u.uf) WHERE m.sub IS DISTINCT FROM TRIM(u.cod_submercado)")


@regra("medicao_geracao_durante_parada", "Consistência", "medicao_geracao",
       "Energia positiva em hora de parada registrada da usina (impossibilidade física).", "CORRIGIR")
def medicao_geracao_durante_parada(ctx):
    base = ("FROM {s}.medicao_geracao m JOIN {s}.parada_usina p ON p.id_usina = m.id_usina "
            "AND m.data_hora BETWEEN p.inicio AND p.fim WHERE p.fim >= p.inicio")
    return ctx.contar("SELECT COUNT(*) " + base, "SELECT COUNT(*) " + base + " AND m.energia_mwh > 0")


@regra("medicao_energia_maior_que_disponibilidade", "Consistência", "medicao_geracao",
       "Energia da hora maior que a potência disponível informada na própria linha.", "CORRIGIR")
def medicao_energia_maior_que_disponibilidade(ctx):
    return ctx.contar(
        "SELECT COUNT(*) FROM {s}.medicao_geracao WHERE disponibilidade_mw IS NOT NULL",
        "SELECT COUNT(*) FROM {s}.medicao_geracao "
        "WHERE disponibilidade_mw IS NOT NULL AND energia_mwh > disponibilidade_mw * 1.001")


@regra("medicao_recebido_antes_da_medicao", "Consistência", "medicao_geracao",
       "Dado recebido antes da hora medida (relógio do servidor errado).", "SINALIZAR")
def medicao_recebido_antes_da_medicao(ctx):
    return ctx.contar("SELECT COUNT(*) FROM {s}.medicao_geracao WHERE recebido_em IS NOT NULL",
                      "SELECT COUNT(*) FROM {s}.medicao_geracao WHERE recebido_em < data_hora")


@regra("medicao_solar_a_noite", "Consistência", "medicao_geracao",
       "Usina solar com energia positiva fora do período de sol (antes das 5h ou a partir das 20h).", "CORRIGIR")
def medicao_solar_a_noite(ctx):
    base = ("FROM {s}.medicao_geracao m JOIN {s}.usina u ON u.id_usina = m.id_usina "
            "JOIN {o}.fonte_energia f ON f.id_fonte = u.id_fonte WHERE f.cod_fonte = 'UFV'")
    return ctx.contar(
        "SELECT COUNT(*) " + base,
        "SELECT COUNT(*) " + base + " AND m.energia_mwh > 0 "
        "AND (EXTRACT(HOUR FROM m.data_hora) < 5 OR EXTRACT(HOUR FROM m.data_hora) >= 20)")


# --------------------------------------------------------------------------
# ACURÁCIA: o valor é plausível? Outliers, unidades erradas, sensores estranhos
# --------------------------------------------------------------------------

@regra("medicao_acima_da_potencia_instalada", "Acurácia", "medicao_geracao",
       "Energia de uma hora maior que a potência instalada da usina (pico, vírgula deslocada ou unidade errada).",
       "CORRIGIR")
def medicao_acima_da_potencia_instalada(ctx):
    base = "FROM {s}.medicao_geracao m JOIN {s}.usina u ON u.id_usina = m.id_usina"
    return ctx.contar("SELECT COUNT(*) " + base,
                      "SELECT COUNT(*) " + base + " WHERE m.energia_mwh > u.potencia_mw * %(tol)s",
                      {"tol": ctx.conf["tolerancia_potencia"]})


@regra("medicao_unidade_suspeita_kwh", "Acurácia", "medicao_geracao",
       "Energia centenas de vezes acima da potência instalada: planilha digitada em kWh em vez de MWh.", "CORRIGIR")
def medicao_unidade_suspeita_kwh(ctx):
    base = "FROM {s}.medicao_geracao m JOIN {s}.usina u ON u.id_usina = m.id_usina"
    return ctx.contar("SELECT COUNT(*) " + base,
                      "SELECT COUNT(*) " + base + " WHERE m.energia_mwh > u.potencia_mw * %(f)s",
                      {"f": ctx.conf["fator_kwh"]})


@regra("medicao_medidor_travado", "Acurácia", "medicao_geracao",
       "Mesma leitura positiva repetida por horas seguidas (medidor travado, valor plausível).", "SINALIZAR")
def medicao_medidor_travado(ctx):
    r = ctx.linha("""
        WITH d AS (SELECT DISTINCT id_usina, data_hora, energia_mwh FROM {s}.medicao_geracao
                   WHERE id_usina IS NOT NULL AND energia_mwh > 0),
             g AS (SELECT id_usina, energia_mwh,
                          data_hora - ROW_NUMBER() OVER (PARTITION BY id_usina, energia_mwh ORDER BY data_hora)
                                      * INTERVAL '1 hour' AS grupo FROM d),
             r AS (SELECT COUNT(*) AS n FROM g GROUP BY id_usina, energia_mwh, grupo)
        SELECT (SELECT COUNT(*) FROM d), COALESCE(SUM(n) FILTER (WHERE n >= %(min)s), 0) FROM r""",
                  {"min": ctx.conf["travado_min_horas"]})
    return int(r[0]), int(r[1])


@regra("medicao_lancamento_manual", "Acurácia", "medicao_geracao",
       "Medição com origem diferente de SCADA (lançamento manual sem aprovação).", "SINALIZAR")
def medicao_lancamento_manual(ctx):
    return ctx.contar("SELECT COUNT(*) FROM {s}.medicao_geracao",
                      "SELECT COUNT(*) FROM {s}.medicao_geracao WHERE COALESCE(origem, '') <> 'SCADA'")


@regra("pld_valor_atipico", "Acurácia", "pld_horario",
       "PLD além de 3 x IQR do submercado (apenas sinaliza: preço de escassez é real).", "SINALIZAR")
def pld_valor_atipico(ctx):
    if not ctx.tem_linhas("staging.pld_horario"):
        return 0, 0
    r = ctx.linha("""
        WITH q AS (SELECT cod_submercado,
                          percentile_cont(0.25) WITHIN GROUP (ORDER BY pld_rs_mwh) AS q1,
                          percentile_cont(0.75) WITHIN GROUP (ORDER BY pld_rs_mwh) AS q3
                   FROM staging.pld_horario GROUP BY cod_submercado)
        SELECT (SELECT COUNT(*) FROM staging.pld_horario),
               COUNT(*) FILTER (WHERE p.pld_rs_mwh > q.q3 + 3 * (q.q3 - q.q1)
                                   OR p.pld_rs_mwh < q.q1 - 3 * (q.q3 - q.q1))
        FROM staging.pld_horario p JOIN q USING (cod_submercado)""")
    return int(r[0]), int(r[1])


# --------------------------------------------------------------------------
# INTEGRIDADE REFERENCIAL: todo registro aponta para algo que existe?
# --------------------------------------------------------------------------

@regra("medicao_usina_inexistente", "Integridade referencial", "medicao_geracao",
       "Medição de um id_usina que não existe no cadastro (equipamento fora do cadastro).", "QUARENTENA")
def medicao_usina_inexistente(ctx):
    return ctx.contar(
        "SELECT COUNT(*) FROM {s}.medicao_geracao WHERE id_usina IS NOT NULL",
        "SELECT COUNT(*) FROM {s}.medicao_geracao m WHERE m.id_usina IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM {s}.usina u WHERE u.id_usina = m.id_usina)")


@regra("parada_usina_inexistente", "Integridade referencial", "parada_usina",
       "Parada de uma usina que não existe no cadastro.", "QUARENTENA")
def parada_usina_inexistente(ctx):
    return ctx.contar(
        "SELECT COUNT(*) FROM {s}.parada_usina",
        "SELECT COUNT(*) FROM {s}.parada_usina p "
        "WHERE NOT EXISTS (SELECT 1 FROM {s}.usina u WHERE u.id_usina = p.id_usina)")


@regra("usina_fonte_submercado_inexistente", "Integridade referencial", "usina",
       "Usina apontando para fonte ou submercado que não existe nas tabelas de domínio.", "SINALIZAR")
def usina_fonte_submercado_inexistente(ctx):
    return ctx.contar(
        "SELECT COUNT(*) FROM {s}.usina",
        "SELECT COUNT(*) FROM {s}.usina u "
        "WHERE NOT EXISTS (SELECT 1 FROM {o}.fonte_energia f WHERE f.id_fonte = u.id_fonte) "
        "OR NOT EXISTS (SELECT 1 FROM {o}.submercado s WHERE TRIM(s.cod_submercado) = TRIM(u.cod_submercado))")


# --------------------------------------------------------------------------
# ATUALIDADE: o dado chegou a tempo? Alguma usina parou de enviar?
# --------------------------------------------------------------------------

@regra("medicao_atraso_integracao", "Atualidade", "medicao_geracao",
       "Medição recebida mais de 24 h depois da hora medida (integração atrasada).", "SINALIZAR")
def medicao_atraso_integracao(ctx):
    return ctx.contar(
        "SELECT COUNT(*) FROM {s}.medicao_geracao WHERE recebido_em IS NOT NULL",
        "SELECT COUNT(*) FROM {s}.medicao_geracao WHERE recebido_em - data_hora > %(sla)s * INTERVAL '1 hour'",
        {"sla": ctx.conf["sla_atraso_horas"]})


@regra("usina_sem_dados_recentes", "Atualidade", "medicao_geracao",
       "Usina cuja última medição é mais de 24 h anterior à última medição do conjunto (parou de enviar).",
       "SINALIZAR")
def usina_sem_dados_recentes(ctx):
    r = ctx.linha("""
        WITH u AS (SELECT id_usina FROM {s}.usina WHERE """ + USINA_VALIDA + """),
             ult AS (SELECT u.id_usina, MAX(m.data_hora) AS mx FROM u
                     LEFT JOIN {s}.medicao_geracao m ON m.id_usina = u.id_usina AND m.data_hora <= NOW()
                     GROUP BY u.id_usina),
             g AS (SELECT MAX(mx) AS gm FROM ult)
        SELECT COUNT(*), COUNT(*) FILTER (WHERE ult.mx IS NULL OR ult.mx < g.gm - INTERVAL '24 hours')
        FROM ult CROSS JOIN g""")
    return int(r[0]), int(r[1])


assert len(REGRAS) == 32, f"esperadas 32 regras, achei {len(REGRAS)}"
