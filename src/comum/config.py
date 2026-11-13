import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[2]


def carregar_config():
    load_dotenv(RAIZ / ".env")
    caminho = RAIZ / "config" / "config.yaml"
    if not caminho.exists():
        raise FileNotFoundError(
            "config/config.yaml nao encontrado. Copie config/config.example.yaml para config/config.yaml"
        )
    with open(caminho, encoding="utf-8") as f:
        return yaml.safe_load(f)


def dados_banco():
    """Credenciais vindas do .env (nunca escritas no codigo)."""
    load_dotenv(RAIZ / ".env")
    obrigatorias = ["DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"]
    faltando = [v for v in obrigatorias if not os.getenv(v)]
    if faltando:
        raise ValueError("Faltam variaveis no .env: " + ", ".join(faltando))
    return {
        "host": os.getenv("DB_HOST"),
        "port": os.getenv("DB_PORT", "5432"),
        "dbname": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "sslmode": os.getenv("DB_SSLMODE", "require"),
    }