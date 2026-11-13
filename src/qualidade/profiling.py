"""Profiling de cada coluna: tipo, nulos, distintos, mínimo, máximo, média e quartis.

Roda sobre a origem (como os dados chegaram) e sobre as tabelas externas da staging.
O resultado fica em qualidade.profiling, ligado à execução ANTES.
"""
from psycopg2 import sql

NUMERICOS = {"smallint", "integer", "bigint", "numeric", "double precision", "real"}


def tabelas_para_perfilar(origem):
    return [(origem, t) for t in ("submercado", "fonte_energia", "usina", "feriado_nacional", "parada_usina",
                                  "medicao_geracao")] + [("staging", "pld_horario"), ("staging", "clima_horario")]


def perfilar(conn, cfg, id_execucao, logger):
    origem = (cfg.get("origem") or {}).get("schema", "campo_real_energia")
    total = 0
    with conn.cursor() as cur:
        cur.execute("DELETE FROM qualidade.profiling WHERE id_execucao = %s", (id_execucao,))
        for schema, tabela in tabelas_para_perfilar(origem):
            cur.execute("SELECT column_name, data_type FROM information_schema.columns "
                        "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position", (schema, tabela))
            colunas = cur.fetchall()
            for coluna, tipo in colunas:
                c = sql.Identifier(coluna)
                t = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(tabela))
                if tipo in NUMERICOS:
                    extra = sql.SQL(", AVG({c}), percentile_cont(0.25) WITHIN GROUP (ORDER BY {c}), "
                                    "percentile_cont(0.5) WITHIN GROUP (ORDER BY {c}), "
                                    "percentile_cont(0.75) WITHIN GROUP (ORDER BY {c})").format(c=c)
                    ext = sql.SQL("MIN({c})::text, MAX({c})::text").format(c=c)
                elif tipo == "boolean":
                    extra, ext = sql.SQL(", NULL, NULL, NULL, NULL"), sql.SQL("MIN({c}::int)::text, MAX({c}::int)::text").format(c=c)
                elif tipo in ("jsonb", "json"):
                    extra, ext = sql.SQL(", NULL, NULL, NULL, NULL"), sql.SQL("NULL, NULL")
                else:
                    extra, ext = sql.SQL(", NULL, NULL, NULL, NULL"), sql.SQL("MIN({c})::text, MAX({c})::text").format(c=c)
                distintos = sql.SQL("NULL") if tipo in ("jsonb", "json") else sql.SQL("COUNT(DISTINCT {c})").format(c=c)
                consulta = sql.SQL("SELECT COUNT(*), COUNT({c}), {d}, {e}{x} FROM {t}").format(c=c, d=distintos, e=ext, x=extra, t=t)
                cur.execute(consulta)
                n, nn, dist, mn, mx, media, q1, med, q3 = cur.fetchone()
                nulos = n - nn
                cur.execute("INSERT INTO qualidade.profiling (id_execucao, tabela, coluna, tipo_dado, registros, nulos, pct_nulos, "
                            "distintos, minimo, maximo, media, q1, mediana, q3) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            (id_execucao, f"{schema}.{tabela}", coluna, tipo, n, nulos,
                             round(100.0 * nulos / n, 3) if n else 0, dist, mn, mx, media, q1, med, q3))
                total += 1
    conn.commit()
    logger.info("Profiling gravado: %s colunas", total)
    return total
