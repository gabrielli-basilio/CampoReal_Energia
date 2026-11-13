"""Log: console + arquivo logs/extracao.log + tabela raw.log_extracao."""

import logging

import psycopg2

from src.comum.config import RAIZ, dados_banco


def criar_logger(nome="extracao"):
    logger = logging.getLogger(nome)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formato = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(formato)
    logger.addHandler(console)
    pasta = RAIZ / "logs"
    pasta.mkdir(exist_ok=True)
    arquivo = logging.FileHandler(pasta / "extracao.log", encoding="utf-8")
    arquivo.setFormatter(formato)
    logger.addHandler(arquivo)
    return logger


class Execucao:
    """Registra uma execucao em raw.log_extracao.

    Usa conexao propria com autocommit: o log fica salvo mesmo se a carga der erro.

    Uso:
        with Execucao("CCEE", "2025") as ex:
            ex.lidas += 10
            ex.gravadas += 10
        # status OK; se ex.status = "JA_COMPLETO" antes de sair, mantem esse status
    """

    def __init__(self, fonte, recurso):
        self.fonte = fonte
        self.recurso = recurso
        self.lidas = 0
        self.gravadas = 0
        self.status = "OK"
        self.erro = None
        self.id = None
        self.conn = None

    def __enter__(self):
        self.conn = psycopg2.connect(**dados_banco())
        self.conn.autocommit = True
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO raw.log_extracao (fonte, recurso) VALUES (%s, %s) RETURNING id_execucao",
                (self.fonte, self.recurso),
            )
            self.id = cur.fetchone()[0]
        return self

    def __exit__(self, tipo, valor, tb):
        if tipo is not None:
            self.status = "ERRO"
            self.erro = f"{tipo.__name__}: {valor}"[:2000]
        with self.conn.cursor() as cur:
            cur.execute(
                """UPDATE raw.log_extracao
                   SET fim = NOW(), linhas_lidas = %s, linhas_gravadas = %s,
                       status = %s, erro = %s
                   WHERE id_execucao = %s""",
                (self.lidas, self.gravadas, self.status, self.erro, self.id),
            )
        self.conn.close()
        return False  # nao engole o erro