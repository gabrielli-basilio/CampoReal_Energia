"""Gera docs/relatorio_qualidade_execucao.md com os números reais da última execução.

Uso:  python -m src.qualidade.relatorio
Depois copie a variação da receita para a seção "Impacto da limpeza" de docs/relatorio_qualidade.md.
"""
import sys
from datetime import datetime

from src.comum.config import RAIZ
from src.comum.conexao import conectar


def brl(v):
    return "n/d" if v is None else f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def num(v, casas=0):
    return "n/d" if v is None else f"{float(v):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def tabela(cabecalho, linhas):
    saida = ["| " + " | ".join(cabecalho) + " |", "|" + "|".join(["---"] * len(cabecalho)) + "|"]
    saida += ["| " + " | ".join(str(c) for c in l) + " |" for l in linhas]
    return "\n".join(saida)


def gerar():
    conn = conectar()
    cur = conn.cursor()
    cur.execute("SELECT fase, MAX(id_execucao) FROM qualidade.execucao GROUP BY fase")
    ids = dict(cur.fetchall())
    if "ANTES" not in ids or "DEPOIS" not in ids:
        sys.exit("Rode antes: python -m src.qualidade.executar")
    a, d = ids["ANTES"], ids["DEPOIS"]
    md = [f"# Relatório de qualidade: execução {a}/{d}",
          f"\nGerado em {datetime.now():%d/%m/%Y %H:%M}. Origem avaliada na execução {a} (ANTES) e staging na {d} (DEPOIS).\n"]

    cur.execute("""SELECT x.dimensao, COUNT(*), SUM(x.registros_falha), SUM(y.registros_falha),
                          ROUND(AVG(100 - x.percentual_falha) FILTER (WHERE x.registros_avaliados > 0), 2),
                          ROUND(AVG(100 - y.percentual_falha) FILTER (WHERE y.registros_avaliados > 0), 2)
                   FROM qualidade.metricas x JOIN qualidade.metricas y ON y.regra = x.regra AND y.id_execucao = %s
                   WHERE x.id_execucao = %s GROUP BY 1 ORDER BY 1""", (d, a))
    md += ["## 1. Resumo por dimensão", tabela(["Dimensão", "Regras", "Falhas antes", "Falhas depois", "Índice antes", "Índice depois"],
                                               [(r[0], r[1], num(r[2]), num(r[3]), num(r[4], 2), num(r[5], 2)) for r in cur.fetchall()])]

    cur.execute("""SELECT x.dimensao, x.regra, x.tabela, x.registros_avaliados, x.registros_falha, y.registros_falha, x.decisao
                   FROM qualidade.metricas x JOIN qualidade.metricas y ON y.regra = x.regra AND y.id_execucao = %s
                   WHERE x.id_execucao = %s ORDER BY 1, 2""", (d, a))
    md += ["\n## 2. Todas as regras (antes × depois)",
           tabela(["Dimensão", "Regra", "Tabela", "Avaliados", "Falha antes", "Falha depois", "Decisão"],
                  [(r[0], r[1], r[2], num(r[3]), num(r[4]), num(r[5]), r[6]) for r in cur.fetchall()])]

    cur.execute("SELECT regra, decisao, COUNT(*) FROM qualidade.tratamento GROUP BY 1, 2 ORDER BY 1")
    md += ["\n## 3. Tratamentos (um por registro)", tabela(["Regra", "Decisão", "Registros"], cur.fetchall())]

    cur.execute("SELECT tabela, regra, COUNT(*) FROM qualidade.quarentena GROUP BY 1, 2 ORDER BY 1, 2")
    md += ["\n## 4. Quarentena", tabela(["Tabela", "Regra", "Registros"], cur.fetchall())]

    cur.execute("SELECT indicador, recorte, valor_antes, valor_depois, diferenca, variacao_pct FROM qualidade.impacto_limpeza "
                "WHERE indicador IN ('geracao_mwh', 'receita_pld_rs') ORDER BY indicador, recorte")
    linhas = []
    for ind, rec, va, vd, dif, pct in cur.fetchall():
        f = brl if ind == "receita_pld_rs" else (lambda v: num(v, 1))
        linhas.append((ind, rec, f(va), f(vd), f(dif), "n/d" if pct is None else f"{float(pct):.2f}%".replace(".", ",")))
    md += ["\n## 5. Impacto da limpeza nos indicadores de negócio",
           tabela(["Indicador", "Recorte", "Antes", "Depois", "Diferença", "Variação"], linhas)]

    cur.execute("SELECT regra, registros_avaliados, registros_falha FROM qualidade.metricas "
                "WHERE id_execucao = %s AND regra IN ('pld_fora_limites_regulatorios', 'pld_horas_faltantes', "
                "'pld_valor_atipico', 'clima_horas_faltantes', 'clima_fora_de_faixa')", (d,))
    md += ["\n## 6. Fontes externas (PLD e clima)",
           tabela(["Regra", "Avaliados", "Com falha"], [(r[0], num(r[1]), num(r[2])) for r in cur.fetchall()]),
           "\nSe `pld_fora_limites_regulatorios` ou `pld_horas_faltantes` tiverem falha, investigue (limite configurado "
           "errado em `limites_pld`? hora faltando na CCEE?) e registre a conclusão em `docs/relatorio_qualidade.md`. "
           "Regra com 0 avaliados significa tabela ainda vazia: rode o pipeline e esta avaliação de novo."]
    conn.close()
    destino = RAIZ / "docs" / "relatorio_qualidade_execucao.md"
    destino.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Relatório gravado em {destino}")


if __name__ == "__main__":
    gerar()
