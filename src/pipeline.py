"""Pipeline completo: PLD -> limpeza -> clima -> carga do DW.

Uso:  python -m src.pipeline
"""
import importlib.util
import subprocess
import sys


def existe(modulo):
    try:
        return importlib.util.find_spec(modulo) is not None
    except ModuleNotFoundError:
        return False


def rodar(nome, modulo, args=()):
    print(f"\n=== {nome} ===")
    resultado = subprocess.run([sys.executable, "-m", modulo, *args])
    if resultado.returncode != 0:
        print(f"ERRO no passo '{nome}'. Pipeline interrompido.")
        sys.exit(resultado.returncode)


def main():
    rodar("1. PLD da CCEE", "src.extracao.ccee")

    if existe("src.qualidade.executar"):
        rodar("2. Limpeza (qualidade)", "src.qualidade.executar", ["--etapas", "limpeza"])
    else:
        print("\n=== 2. Limpeza: src/qualidade ainda nao existe (parte do Biel). Pulando. ===")

    rodar("3. Clima do Open-Meteo", "src.extracao.clima")

    if existe("src.carga_dw"):
        rodar("4. Carga do DW", "src.carga_dw")
    else:
        print("\n=== 4. Carga do DW: src/carga_dw.py ainda nao existe (parte do Joao). Pulando. ===")

    print("\nPipeline terminado.")


if __name__ == "__main__":
    main()