"""Utilitarios de requisicao HTTP com retentativas e emulacao de navegador."""

import time
from urllib.parse import urlparse

from curl_cffi import requests


class ErroExtracao(Exception):
    """Erro levantado quando a extracao falha apos todas as tentativas ou recebe dados invalidos."""


HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}


def pegar_json(url, params=None, timeout=60, tentativas=3, espera_segundos=2, logger=None):
    """Faz uma requisicao GET esperando JSON, emulando navegador para evitar bloqueio WAF."""
    parsed = urlparse(url)
    headers_req = {
        **HEADERS,
        "Referer": f"{parsed.scheme}://{parsed.netloc}/",
    }
    ultimo_erro = None

    for tentativa in range(1, tentativas + 1):
        try:
            resp = requests.get(
                url,
                params=params,
                headers=headers_req,
                timeout=timeout,
                impersonate="chrome",
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            ultimo_erro = e
            if logger:
                logger.warning(
                    "Tentativa %s/%s falhou: %s: %s",
                    tentativa,
                    tentativas,
                    type(e).__name__,
                    e,
                )
            if tentativa < tentativas:
                time.sleep(espera_segundos * (2 ** (tentativa - 1)))

    raise ErroExtracao(
        f"Falhou apos {tentativas} tentativas: {type(ultimo_erro).__name__}: {ultimo_erro}"
    )
