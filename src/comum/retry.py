"""Requisicao HTTP com nova tentativa, tempo limite e tratamento de limite de requisicoes."""

import time

import requests


class ErroExtracao(Exception):
    """Erro de extracao (fonte fora do ar, resposta vazia, colunas mudaram...)."""


def pegar_json(url, params, timeout=60, tentativas=3, espera=2, logger=None):
    ultimo_erro = None
    for n in range(1, tentativas + 1):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code == 429:  # limite de requisicoes
                pausa = int(r.headers.get("Retry-After", espera * n * 5))
                if logger:
                    logger.warning("Limite de requisicoes (429). Aguardando %ss", pausa)
                time.sleep(pausa)
                ultimo_erro = "HTTP 429 (limite de requisicoes)"
                continue
            r.raise_for_status()
            return r.json()
        except (requests.Timeout, requests.ConnectionError) as e:
            ultimo_erro = f"{type(e).__name__}: {e}"
        except (requests.HTTPError, ValueError) as e:
            ultimo_erro = f"{type(e).__name__}: {e}"
        if logger:
            logger.warning("Tentativa %s/%s falhou: %s", n, tentativas, ultimo_erro)
        if n < tentativas:
            time.sleep(espera * n)  # espera cresce a cada tentativa
    raise ErroExtracao(f"Falhou apos {tentativas} tentativas: {ultimo_erro}")