# Ajustes por membro (período 2025 a 2026)

Legenda: **NOVO** = arquivo criado, não mexe em nada existente. **PEDE OK** = altera algo que já existe; só será feito com aprovação.

## Biel: qualidade de dados (pronto, NOVO)
- `sql/02_qualidade/01_qualidade.sql`, `02_staging_limpo.sql`
- `src/qualidade/` (regras, limpeza, profiling, impacto, executar, relatorio)
- `tests/test_qualidade.py`, `docs/relatorio_qualidade.md`
- Rodar: `python -m src.qualidade.executar` (ciclo completo: limpeza, antes, depois).
- Pendente após rodar com PLD real: preencher em `relatorio_qualidade.md` a receita antes × depois e as conclusões das regras de PLD.

## Gabi: extração e carga
Falta, para cobrir 2025 a 2026: PLD e clima até o último mês publicado (hoje o clima está limitado a 2025).
- **PEDE OK:** `config/config.example.yaml` (período 2025-01-01 a 2026, `open_meteo.data_fim`), `README.md` (período e novo passo de qualidade), `docs/evidencias/falha_fonte.md` (registrar a linha do log de CSV de reserva), `requirements.txt` (confirmar `psycopg2-binary`, `pandas`).
- Rodar a extração real e conferir a contagem de linhas de PLD e clima.

## João: modelagem
Já existe no branch `modelagem-joao`; o que escrevi apenas se encaixa nele (a staging limpa segue o contrato do `carga_dw.py`).
- **PEDE OK:** `docs/modelagem.md`: trocar o período do clima para 2025 a 2026; o feriados de 2026 já estão em `01_dimensoes.sql`.
- Conferir que as views `vw_captura_por_fonte`, `vw_pld_hora_mes`, `vw_correlacao_clima` rodam com dados reais.

## Lucas: painel parte 1, Tableau (NOVO)
`docs/painel_tableau.md` (conexão, relações, campos calculados, dashboards 0 a 4) e `painel/LEIAME.md`. Entrega: `painel/campo_real.twbx`.

## Enzo: painel parte 2, Tableau (NOVO)
Dashboards 5 a 8 em `docs/painel_tableau.md`.

## Pontos que preciso que você decida
1. Posso alterar os arquivos existentes marcados **PEDE OK** acima (Gabi e João)?
2. A cópia no seu PC está atrás do GitHub (o trabalho do João está no branch `modelagem-joao`); faça `git fetch` e `git checkout modelagem-joao` antes de rodar.
3. Limitação conhecida: geração só existe em 2025; isso precisa aparecer no painel e no relatório.
