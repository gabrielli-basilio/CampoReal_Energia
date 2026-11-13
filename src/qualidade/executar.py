"""Avaliação de qualidade + limpeza.

Uso:
    python -m src.qualidade.executar                  # ciclo completo (padrão)
    python -m src.qualidade.executar --etapas limpeza # o mesmo; é o que o pipeline chama
    python -m src.qualidade.executar --etapas antes   # só avalia a origem (e faz o profiling)
    python -m src.qualidade.executar --etapas depois  # só reavalia a staging

Ciclo completo = avalia ANTES (+ profiling) -> limpa (origem -> staging) -> avalia DEPOIS -> impacto.
O clima só existe depois do pipeline: as regras de clima aparecem com 0 avaliados na primeira passada.
Rode de novo este módulo depois de `python -m src.pipeline` para avaliá-las.
"""
import argparse
import sys

from src.comum.conexao import conectar, garantir_tabelas
from src.comum.config import RAIZ, carregar_config
from src.comum.log import criar_logger
from src.qualidade import regras as modulo_regras
from src.qualidade.impacto import calcular_impacto
from src.qualidade.limpeza import executar_limpeza
from src.qualidade.profiling import perfilar
from src.qualidade.regras import REGRAS, Contexto


def criar_objetos(conn):
    """Executa sql/02_qualidade/*.sql (idempotente)."""
    for arquivo in sorted((RAIZ / "sql" / "02_qualidade").glob("*.sql")):
        with conn.cursor() as cur:
            cur.execute(arquivo.read_text(encoding="utf-8"))
    conn.commit()


def avaliar(conn, cfg, fase, logger):
    """Roda as 32 regras e grava uma linha por regra em qualidade.metricas. Devolve id_execucao."""
    origem = (cfg.get("origem") or {}).get("schema", "campo_real_energia")
    schema = origem if fase == "ANTES" else "staging"
    with conn.cursor() as cur:
        cur.execute("INSERT INTO qualidade.execucao (fase, observacao) VALUES (%s, %s) RETURNING id_execucao",
                    (fase, f"regras sobre {schema}"))
        id_execucao = cur.fetchone()[0]
    conn.commit()
    ctx = Contexto(conn, schema, cfg, origem)
    erros = 0
    for r in REGRAS:
        try:
            avaliados, falhas = r.funcao(ctx)
        except Exception as e:  # uma regra com problema não derruba as outras
            conn.rollback()
            logger.error("Regra %s falhou: %s", r.nome, e)
            avaliados, falhas, erros = 0, 0, erros + 1
        pct = round(100.0 * falhas / avaliados, 4) if avaliados else 0
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO qualidade.metricas (id_execucao, fase, regra, dimensao, tabela, descricao, decisao,
                           registros_avaliados, registros_falha, percentual_falha) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (id_execucao, fase, r.nome, r.dimensao, r.tabela, r.descricao, r.decisao, avaliados, falhas, pct))
        conn.commit()
    with conn.cursor() as cur:
        cur.execute("UPDATE qualidade.execucao SET fim = NOW() WHERE id_execucao = %s", (id_execucao,))
        cur.execute("SELECT COUNT(*) FILTER (WHERE registros_falha > 0), SUM(registros_falha) FROM qualidade.metricas "
                    "WHERE id_execucao = %s", (id_execucao,))
        com_falha, soma = cur.fetchone()
    conn.commit()
    logger.info("Avaliação %s (execução %s): %s regras, %s com falha, %s registros com falha%s", fase, id_execucao,
                len(REGRAS), com_falha, soma, f", {erros} regra(s) com erro" if erros else "")
    return id_execucao


def ultima_execucao(conn, fase):
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(id_execucao) FROM qualidade.execucao WHERE fase = %s", (fase,))
        return cur.fetchone()[0]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--etapas", choices=["limpeza", "antes", "depois"], default="limpeza")
    args = ap.parse_args(argv)
    logger = criar_logger("qualidade")
    cfg = carregar_config()
    conn = conectar()
    try:
        garantir_tabelas(conn)
        criar_objetos(conn)
        if args.etapas == "limpeza":
            id_antes = avaliar(conn, cfg, "ANTES", logger)
            perfilar(conn, cfg, id_antes, logger)
            executar_limpeza(conn, cfg, logger, id_antes)
            id_depois = avaliar(conn, cfg, "DEPOIS", logger)
            calcular_impacto(conn, cfg, id_antes, id_depois, logger)
        elif args.etapas == "antes":
            id_antes = avaliar(conn, cfg, "ANTES", logger)
            perfilar(conn, cfg, id_antes, logger)
        else:
            id_antes, id_depois = ultima_execucao(conn, "ANTES"), avaliar(conn, cfg, "DEPOIS", logger)
            if id_antes:
                calcular_impacto(conn, cfg, id_antes, id_depois, logger)
    except Exception:
        conn.rollback()
        logger.exception("Qualidade interrompida")
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
