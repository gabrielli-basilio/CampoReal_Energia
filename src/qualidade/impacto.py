"""Impacto da limpeza nos indicadores de negócio (antes x depois) e índice de qualidade."""
from src.qualidade.regras import configuracao  # noqa: F401

DIMENSOES = ["Completude", "Unicidade", "Validade", "Consistência", "Acurácia", "Integridade referencial", "Atualidade"]


def indice_por_dimensao(conn, id_execucao):
    """Índice = média de (100 - % de falha) das regras avaliadas; geral = média das dimensões."""
    with conn.cursor() as cur:
        cur.execute("SELECT dimensao, AVG(100 - percentual_falha) FROM qualidade.metricas "
                    "WHERE id_execucao = %s AND registros_avaliados > 0 GROUP BY dimensao", (id_execucao,))
        por_dim = {d: float(v) for d, v in cur.fetchall()}
    geral = sum(por_dim.values()) / len(por_dim) if por_dim else None
    return por_dim, geral


def _agrupado(conn, consulta):
    with conn.cursor() as cur:
        cur.execute(consulta)
        return cur.fetchall()


def consultas(origem):
    tem_pld = "LEFT JOIN staging.pld_horario p ON p.cod_submercado = TRIM(u.cod_submercado) AND p.data_hora = m.data_hora"
    antes = f"""SELECT f.cod_fonte, TRIM(u.cod_submercado), SUM(m.energia_mwh), SUM(m.energia_mwh * p.pld_rs_mwh), COUNT(*)
                FROM {origem}.medicao_geracao m JOIN {origem}.usina u ON u.id_usina = m.id_usina
                JOIN {origem}.fonte_energia f ON f.id_fonte = u.id_fonte {tem_pld} GROUP BY 1, 2"""
    depois = f"""SELECT u.cod_fonte, TRIM(u.cod_submercado), SUM(m.energia_mwh), SUM(m.energia_mwh * p.pld_rs_mwh), COUNT(*)
                 FROM staging.medicao_geracao m JOIN staging.usina u ON u.id_usina = m.id_usina {tem_pld} GROUP BY 1, 2"""
    return antes, depois


def somar(linhas):
    """[(fonte, sub, geracao, receita, n)] -> dicionário de recortes."""
    r = {"TOTAL": [0.0, 0.0, 0]}
    for fonte, sub, ger, rec, n in linhas:
        for chave in (f"fonte:{fonte}", f"submercado:{sub}", "TOTAL"):
            r.setdefault(chave, [0.0, 0.0, 0])
            r[chave][0] += float(ger or 0)
            r[chave][1] += float(rec or 0)
            r[chave][2] += n
    return r


def calcular_impacto(conn, cfg, id_antes, id_depois, logger):
    origem = (cfg.get("origem") or {}).get("schema", "campo_real_energia")
    q_antes, q_depois = consultas(origem)
    a, d = somar(_agrupado(conn, q_antes)), somar(_agrupado(conn, q_depois))
    with conn.cursor() as cur:
        cur.execute("SELECT EXISTS (SELECT 1 FROM staging.pld_horario)")
        tem_pld = cur.fetchone()[0]

    linhas = []
    for recorte in sorted(set(a) | set(d)):
        va, vd = a.get(recorte, [0, 0, 0]), d.get(recorte, [0, 0, 0])
        linhas.append(("geracao_mwh", recorte, va[0], vd[0]))
        linhas.append(("receita_pld_rs", recorte, va[1] if tem_pld else None, vd[1] if tem_pld else None))
    linhas.append(("registros_medicao", "TOTAL", a["TOTAL"][2], d["TOTAL"][2]))

    ia, ga = indice_por_dimensao(conn, id_antes)
    idp, gd = indice_por_dimensao(conn, id_depois)
    linhas.append(("indice_qualidade", "TOTAL", ga, gd))
    for dim in DIMENSOES:
        linhas.append(("indice_qualidade", f"dim:{dim}", ia.get(dim), idp.get(dim)))

    with conn.cursor() as cur:
        cur.execute("TRUNCATE qualidade.impacto_limpeza")
        for ind, rec, antes, depois in linhas:
            dif = None if antes is None or depois is None else round(depois - antes, 2)
            pct = None if dif is None or not antes else round(100.0 * dif / antes, 4)
            cur.execute("INSERT INTO qualidade.impacto_limpeza (indicador, recorte, valor_antes, valor_depois, diferenca, "
                        "variacao_pct) VALUES (%s,%s,%s,%s,%s,%s)",
                        (ind, rec, None if antes is None else round(antes, 2), None if depois is None else round(depois, 2), dif, pct))
    conn.commit()
    logger.info("Impacto da limpeza gravado (%s linhas). Receita %s", len(linhas),
                "calculada com o PLD" if tem_pld else "NÃO calculada: staging.pld_horario está vazia")
