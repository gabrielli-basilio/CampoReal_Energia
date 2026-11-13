"""Conexao com o PostgreSQL (Neon) e criacao das tabelas raw/staging."""

import psycopg2

from src.comum.config import RAIZ, dados_banco


def conectar():
    return psycopg2.connect(**dados_banco())


def garantir_tabelas(conn):
    """Executa sql/01_raw_staging/*.sql (pode rodar varias vezes)."""
    pasta = RAIZ / "sql" / "01_raw_staging"
    for arquivo in sorted(pasta.glob("*.sql")):
        with conn.cursor() as cur:
            cur.execute(arquivo.read_text(encoding="utf-8"))
    conn.commit()