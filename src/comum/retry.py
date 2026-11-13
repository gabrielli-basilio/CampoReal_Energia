"""Utilitarios de requisicao HTTP com retentativas sem dependencias externas."""

import json
import subprocess
import time
from urllib.parse import urlencode, urlparse


class ErroExtracao(Exception):
    """Erro levantado quando a extracao falha apos todas as tentativas ou recebe dados invalidos."""


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def _montar_url(url, params):
    if not params:
        return url
    separador = "&" if "?" in url else "?"
    return f"{url}{separador}{urlencode(params)}"


def pegar_json(url, params=None, timeout=60, tentativas=3, espera_segundos=2, logger=None):
    """Faz uma requisicao GET esperando JSON via curl nativo do Windows."""
    url_completa = _montar_url(url, params)
    parsed = urlparse(url)
    referer = f"{parsed.scheme}://{parsed.netloc}/"
    ultimo_erro = None

    comando = [
        "curl.exe",
        "-sS",
        "-L",
        "-f",
        "--max-time",
        str(timeout),
        "-H",
        f"User-Agent: {USER_AGENT}",
        "-H",
        "Accept: application/json, text/plain, */*",
        "-H",
        "Accept-Language: pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "-H",
        f"Referer: {referer}",
        url_completa,
    ]

    for tentativa in range(1, tentativas + 1):
        try:
            proc = subprocess.run(
                comando,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            if proc.returncode != 0:
                detalhe = proc.stderr.strip() or f"codigo de saida {proc.returncode}"
                raise RuntimeError(f"Erro HTTP/rede no curl: {detalhe}")
            return json.loads(proc.stdout)
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