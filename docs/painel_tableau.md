# Guia do painel (Tableau): Campo Real Energia

Regra da professora: o painel lê **somente o schema `dw_campo_real`**, nunca a origem, a staging ou o schema `qualidade`.
Arquivo final: `painel/campo_real.twbx` (pasta de trabalho empacotada). Lucas faz a base e os dashboards 0 a 4; Enzo faz os dashboards 5 a 8.

## 1. Conexão
- Precisa do **Tableau Desktop** (licença de estudante serve). O Tableau Public não conecta em PostgreSQL.
- Conectar → PostgreSQL. Servidor: host do Neon. Porta 5432. Banco: `campo_real`. Exija SSL. Esquema: `dw_campo_real`.
- Use **Extrair** (extract), não conexão ao vivo: o `.twbx` fica independente do banco e não carrega senha.
- Plano B sem Desktop: exportar as tabelas do `dw_campo_real` para CSV e conectar nos arquivos.

| Tipo | Tabelas |
|---|---|
| Dimensões | `dim_tempo`, `dim_usina`, `dim_fonte`, `dim_submercado`, `dim_tipo_parada`, `dim_status_qualidade`, `dim_regra_qualidade` |
| Fatos | `fato_geracao`, `fato_pld`, `fato_clima`, `fato_parada_hora`, `fato_qualidade`, `fato_impacto_limpeza` |
| Views | `vw_captura_por_fonte`, `vw_pld_hora_mes`, `vw_correlacao_clima` |

## 2. Modelo de dados (relações)
Na aba Fonte de Dados, use o **modelo de relações** (arrastar tabelas para o canvas), não junções: assim cada fato mantém a sua granularidade e não duplica linhas.

| Dimensão | Liga em |
|---|---|
| `dim_tempo[sk_tempo]` | `fato_geracao`, `fato_pld`, `fato_clima`, `fato_parada_hora`, `fato_qualidade[sk_tempo_execucao]` |
| `dim_usina[sk_usina]` | `fato_geracao`, `fato_clima`, `fato_parada_hora` |
| `dim_fonte[sk_fonte]` | `fato_geracao` |
| `dim_submercado[sk_submercado]` | `fato_geracao`, `fato_pld`, `fato_clima`, `fato_parada_hora` |
| `dim_tipo_parada[sk_tipo_parada]` | `fato_parada_hora` |
| `dim_status_qualidade[sk_status]` | `fato_geracao` |
| `dim_regra_qualidade[sk_regra]` | `fato_qualidade` |

`fato_impacto_limpeza` e as três views ficam em fontes de dados separadas (ou sem relação): são lidas sozinhas.
Ordenação de meses: na planilha, ordene `nome_mes` pelo campo `mes` (Ordenar → Campo).

## 3. Campos calculados
Crie em Análise → Criar campo calculado. Nomes de colunas são os do DW atual.

```
// Geração e valor
Geração MWh              : SUM([energia_mwh])
Receita PLD (R$)         : SUM([receita_pld_rs])
Geração valorada MWh     : SUM(IF NOT ISNULL([receita_pld_rs]) THEN [energia_mwh] END)
Preço capturado (R$/MWh) : [Receita PLD (R$)] / [Geração valorada MWh]
PLD médio (R$/MWh)       : AVG([pld_rs_mwh])
Razão de captura         : [Preço capturado (R$/MWh)] / [PLD médio (R$/MWh)]
Fator de capacidade      : SUM([energia_mwh]) / SUM([potencia_mw])

// Paradas
Horas indisponíveis       : SUM([horas_indisponiveis])
Energia não gerada (MWh)  : SUM([energia_nao_gerada_mwh])
Receita não gerada (R$)   : SUM([receita_nao_gerada_rs])

// Clima
Radiação média (W/m²)     : AVG([radiacao_wm2])
Vento médio 100 m (km/h)  : AVG([vento_100m_kmh])

// Qualidade
Índice da dimensão        : AVG(IF [registros_avaliados] > 0 THEN [indice_qualidade] END)
Índice geral              : WINDOW_AVG([Índice da dimensão])   // Calcular usando: dimensao (dimensao no Detalhe)
Falhas antes              : SUM(IF [fase] = "ANTES"  THEN [registros_falha] END)
Falhas depois             : SUM(IF [fase] = "DEPOIS" THEN [registros_falha] END)

// Antes x depois da limpeza (fato_impacto_limpeza)
Receita antes (R$)  : SUM(IF [indicador]="receita_pld_rs" AND [recorte]="TOTAL" THEN [valor_antes]  END)
Receita depois (R$) : SUM(IF [indicador]="receita_pld_rs" AND [recorte]="TOTAL" THEN [valor_depois] END)
Variação da receita : ([Receita depois (R$)] - [Receita antes (R$)]) / [Receita antes (R$)]
Geração antes (MWh) : SUM(IF [indicador]="geracao_mwh" AND [recorte]="TOTAL" THEN [valor_antes]  END)
Geração depois (MWh): SUM(IF [indicador]="geracao_mwh" AND [recorte]="TOTAL" THEN [valor_depois] END)
```
O índice geral deve bater com o `docs/relatorio_qualidade_execucao.md` (gerado ao rodar `python -m src.qualidade.executar`): confira antes de publicar.

## 4. Período 2025 a 2026: o que existe em cada fato
| Fato | Período | Consequência |
|---|---|---|
| `fato_pld` | 2025 e 2026 até o último mês publicado | Dashboard 4 mostra os dois anos (filtro de ano) |
| `fato_clima` | 2025 e 2026 até a data configurada em `open_meteo.data_fim` | No dashboard 6, filtre `ano = 2025` para comparar com a geração |
| `fato_geracao`, `fato_parada_hora` | **só 2025** (a origem só tem 2025) | Dashboards 1, 2, 3 e 5 com filtro `ano = 2025` |

Receita e preço capturado só existem onde há geração, então são sempre de 2025. Deixe isso escrito no painel.

## 5. Dashboards
Cada dashboard = **uma pergunta como título**, evidência no meio, caixa de texto com a conclusão no rodapé e a linha de fontes:
`Fontes: CCEE, Dados Abertos (PLD horário), CC-BY 4.0 · Open-Meteo, CC-BY 4.0 · Dados operacionais fictícios da Campo Real Energia.`
Crie uma planilha por visual e monte cada dashboard arrastando-as (tamanho fixo, ex.: 1200 x 800).

### Lucas: base e dashboards 0 a 4
| # | Pergunta | Planilhas |
|---|---|---|
| 0 Capa | Quanto a nossa geração vale e podemos confiar? | Quatro números (BANs): `Geração MWh`, `Receita PLD (R$)`, `Preço capturado`, `Índice geral` (fase DEPOIS). Mapa com latitude/longitude de `dim_usina` e tamanho por geração |
| 1 | Quanto geramos por usina, fonte e submercado? | Barras de geração por usina (cor por fonte); linha por `ano_mes` e fonte; tabela usina × `Fator de capacidade`; filtros de submercado e fonte. Filtro de ano = 2025 |
| 2 | Quanto a nossa geração vale a preço de mercado? | Número da receita; barras empilhadas por mês e submercado; mapa de árvore (treemap) por usina |
| 3 | Qual fonte captura o melhor preço? | Barras de `Preço capturado` por fonte com linha de referência no PLD médio; tabela de `vw_captura_por_fonte` com `razao_captura` colorida (verde > 1, vermelho < 1) |
| 4 | Em que horas e meses o PLD é mais alto, e geramos nesses momentos? | Tabela de destaque (highlight table) hora × `nome_mes` com `PLD médio`; linhas de `Geração MWh` por hora e fonte; filtros de submercado e ano |

### Enzo: dashboards 5 a 8
| # | Pergunta | Planilhas |
|---|---|---|
| 5 | Quanto perdemos com paradas? | Números `Horas indisponíveis`, `Energia não gerada (MWh)`, `Receita não gerada (R$)`; barras por tipo de parada e por usina; tabela com o motivo. Nota: "energia não gerada estimada pela média da usina no mesmo mês e hora" |
| 6 | O clima explica a nossa geração? | Dispersão `Radiação média` × `Geração MWh` (um ponto por dia: `data` no Detalhe), filtrada em fonte = Solar fotovoltaica; o mesmo com `Vento médio 100 m` e Eólica; tabela da `vw_correlacao_clima`. Filtro ano = 2025 |
| 7 | Podemos confiar nesses números? | `Índice geral` antes e depois (filtro fase); barras de `Falhas antes` e `Falhas depois` por dimensão; tabela dimensão × tabela com o índice; receita antes/depois; pizza ou barra de `Geração MWh` por status de qualidade |
| 8 | Recomendação | Caixa de texto com as três recomendações abaixo |

**Dashboard 8, recomendações com base nas evidências:**
1. Programar manutenções no mês e na faixa de PLD mais baixos (cruza os dashboards 4 e 5).
2. Bloquear lançamentos MANUAL sem aprovação e validar a unidade na entrada: o maior erro do ano foi uma planilha em kWh.
3. Criar alerta de atualidade: uma usina parou de enviar dados no fim do ano e outra entregou dezembro com cerca de 50 dias de atraso.

## 6. Checklist
- [ ] Extração feita só do `dw_campo_real`; relações conferidas
- [ ] Campos calculados criados (Lucas avisa o Enzo; exportar a pasta de trabalho compartilhada ou repetir os campos)
- [ ] Dashboards 0 a 8 com título, conclusão e linha de fontes
- [ ] Números do dashboard 7 conferidos com a Biel
- [ ] `painel/campo_real.twbx` salvo e enviado
