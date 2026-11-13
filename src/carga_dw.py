"""Cria e carrega o Data Warehouse (schema dw_campo_real) a partir da staging.

Pré-requisitos: extração (CCEE e clima) e limpeza da origem já rodadas.
A parte de qualidade (fato_qualidade e fato_impacto_limpeza) só é carregada
quando o schema qualidade já existe.

Uso:  python -m src.carga_dw
"""
import sys

from src.comum.config import RAIZ
from src.comum.conexao import conectar
from src.comum.log import Execucao, criar_logger

OBRIGATORIAS = [
    "campo_real_energia.submercado",
    "campo_real_energia.fonte_energia",
    "campo_real_energia.feriado_nacional",
    "staging.pld_horario",
    "staging.clima_horario",
    "staging.usina",
    "staging.parada_usina",
    "staging.medicao_geracao",
]
QUALIDADE = ["qualidade.execucao", "qualidade.metricas", "qualidade.impacto_limpeza"]

SCRIPTS = [
    "sql/03_dw/01_ddl_dw.sql",
    "sql/04_carga_dw/01_dimensoes.sql",
    "sql/04_carga_dw/02_fatos.sql",
]
SCRIPT_QUALIDADE = "sql/04_carga_dw/03_qualidade.sql"
SCRIPT_VIEWS = "sql/03_dw/02_views.sql"

CONTAGEM = """
SELECT 'dim_tempo' AS tabela, COUNT(*) FROM dw_campo_real.dim_tempo
UNION ALL SELECT 'dim_usina', COUNT(*) FROM dw_campo_real.dim_usina
UNION ALL SELECT 'fato_geracao', COUNT(*) FROM dw_campo_real.fato_geracao
UNION ALL SELECT 'fato_pld', COUNT(*) FROM dw_campo_real.fato_pld
UNION ALL SELECT 'fato_clima', COUNT(*) FROM dw_campo_real.fato_clima
UNION ALL SELECT 'fato_parada_hora', COUNT(*) FROM dw_campo_real.fato_parada_hora
UNION ALL SELECT 'fato_qualidade', COUNT(*) FROM dw_campo_real.fato_qualidade
UNION ALL SELECT 'fato_impacto_limpeza', COUNT(*) FROM dw_campo_real.fato_impacto_limpeza
"""


def faltando(cur, tabelas):
    ausentes = []
    for tabela in tabelas:
        cur.execute("SELECT to_regclass(%s)", (tabela,))
        if cur.fetchone()[0] is None:
            ausentes.append(tabela)
    return ausentes


def executar(cur, caminho, logger):
    logger.info("Executando %s", caminho)
    cur.execute((RAIZ / caminho).read_text(encoding="utf-8"))


def main():
    logger = criar_logger("carga_dw")
    conn = conectar()
    try:
        with conn.cursor() as cur:
            ausentes = faltando(cur, OBRIGATORIAS)
        if ausentes:
            logger.error("Faltam tabelas para carregar o DW: %s", ", ".join(ausentes))
            logger.error("Rode antes a extração (src.extracao.ccee e src.extracao.clima) "
                         "e a limpeza (src.qualidade.executar --etapas limpeza).")
            sys.exit(1)

        with Execucao("CARGA_DW", "dw_campo_real") as ex, conn.cursor() as cur:
            for script in SCRIPTS:
                executar(cur, script, logger)
            if faltando(cur, QUALIDADE):
                logger.warning("Schema qualidade ainda não existe: fato_qualidade e "
                               "fato_impacto_limpeza ficam vazios nesta carga.")
            else:
                executar(cur, SCRIPT_QUALIDADE, logger)
            executar(cur, SCRIPT_VIEWS, logger)
            conn.commit()

            cur.execute(CONTAGEM)
            linhas = cur.fetchall()
            ex.gravadas = sum(n for _, n in linhas)
            for tabela, n in linhas:
                logger.info("%-22s %8d linhas", tabela, n)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
