# Relatório de qualidade de dados: Campo Real Energia

Etapa 2 do trabalho. Código em `src/qualidade/`, SQL em `sql/02_qualidade/`, resultados no schema `qualidade` do banco.
Os números de cada execução ficam em `docs/relatorio_qualidade_execucao.md` (gerado por `python -m src.qualidade.relatorio`).

## 1. Como funciona

**Regra do jogo:** a origem (`campo_real_energia`) nunca é alterada. A limpeza acontece no caminho até a `staging`.

```
origem ──► avalia ANTES (32 regras + profiling) ──► limpeza ──► staging ──► avalia DEPOIS ──► impacto ──► DW
```

| Peça | Arquivo | O que faz |
|---|---|---|
| Regras | `src/qualidade/regras.py` | 32 funções reutilizáveis com o decorador `@regra(nome, dimensão, tabela, descrição, decisão)`, 7 dimensões |
| Limpeza | `src/qualidade/limpeza.py` | Aplica uma decisão justificada por problema; grava `staging.*`, `qualidade.tratamento` e `qualidade.quarentena` |
| Profiling | `src/qualidade/profiling.py` | Tipo, nulos, distintos, mínimo, máximo, média e quartis de cada coluna (`qualidade.profiling`) |
| Impacto | `src/qualidade/impacto.py` | Geração, receita ao PLD e índice de qualidade antes × depois (`qualidade.impacto_limpeza`) |
| Execução | `src/qualidade/executar.py` | Orquestra tudo e grava `qualidade.metricas` (regra, dimensão, tabela, avaliados, falhas, %, data) |

Cada regra roda duas vezes com o mesmo código: sobre a origem (ANTES) e sobre a staging (DEPOIS). A diferença mostra o que a limpeza resolveu e o que sobrou de propósito (itens só sinalizados).

**Índice de qualidade** = média, por dimensão, de (100 − % de falha) das regras avaliadas; o índice geral é a média das 7 dimensões. Regras com 0 avaliados (tabela ainda vazia) ficam de fora.

## 2. As quatro decisões

| Decisão | Quando | Exemplo |
|---|---|---|
| **Corrigir** | Só com evidência no próprio dado (outra coluna, outra tabela, física da usina) | Planilha em kWh: ÷ 1000 |
| **Descartar** | Cópia que não acrescenta informação | Reprocessamento da integração |
| **Quarentena** | Não dá para atribuir ou corrigir com segurança; o registro fica guardado inteiro | Medição de equipamento fora do cadastro |
| **Sinalizar** | Dado plausível ou sem como corrigir sem inventar; segue com status `SINALIZADO` | Medidor travado |

Princípio: **corrigir sem evidência é inventar dado.** Por isso nenhum valor é imputado: horas que nunca chegaram continuam faltando, e leituras nulas continuam nulas.

## 3. Problemas encontrados por dimensão

Contagens da origem fictícia (determinísticas) e do PLD real.

### Completude
| Problema | Regra | Afetados | Decisão e justificativa |
|---|---|---|---|
| Cadastro com município vazio | `usina_campo_obrigatorio_vazio` | 1 usina | Descartar: é a cópia duplicada (ver Unicidade) |
| Energia nula (falha de comunicação, UHE Tocantins, 05/03 10h–15h) | `medicao_energia_nula` | 6 horas | Sinalizar: não há como saber a geração; imputar seria inventar |
| Horas que não chegaram (EOL Coxilha Real em 10/11: 24 h; UFV Campo Real Minas de 29 a 31/12: 72 h) | `medicao_horas_faltantes` | 96 horas | Sinalizar: registrado por trecho em `qualidade.tratamento` |
| Medição sem usina | `medicao_sem_usina` | 1 | Quarentena: não dá para saber de quem é a energia |
| PLD e clima faltando | `pld_horas_faltantes`, `clima_horas_faltantes` | 0 | Sinalizar |

### Unicidade
| Problema | Regra | Afetados | Decisão e justificativa |
|---|---|---|---|
| `CRE-EOL-07` duplica `CRE-EOL-007` (mesma fonte, submercado, coordenada e potência; código fora do padrão; nome com espaço) | `usina_duplicada` | 1 | Descartar a cópia e manter o código padrão |
| Reprocessamento da UFV Campo Real Minas em 20/01 | `medicao_duplicada_usina_hora` | 24 | Descartar: valor idêntico, só mudou o `recebido_em` |
| Lançamento MANUAL (+10%) sobre a leitura automática da PCH em 01/06 | `medicao_duplicada_usina_hora` | 4 | Descartar o manual: prevalece o SCADA, sem aprovação nem evidência |

### Validade
| Problema | Regra | Afetados | Decisão e justificativa |
|---|---|---|---|
| Energia negativa (EOL Ventos do Potiguar, 03/02) | `medicao_energia_negativa` | 4 | Corrigir para 0: é consumo de serviços auxiliares, geração negativa não existe |
| Ano 2052 digitado | `medicao_data_fora_do_periodo` | 1 | Quarentena: o recebimento sugere 14/05/2025, mas essa hora já tem leitura automática |
| Latitude positiva (UFV Campo Real Minas) | `usina_coordenada_fora_do_brasil` | 1 | Corrigir o sinal: invertido, o ponto cai em Janaúba/MG |
| Início de operação em 2031 (UFV Sertão do Sol) | `usina_data_inicio_futura` | 1 | Sinalizar: a data correta é desconhecida; a usina tem medições em 2025 |
| Parada com fim antes do início (05/11) | `parada_intervalo_invertido` | 1 | Quarentena: não se sabe se o erro está no início, no fim ou no dia |
| PLD fora do piso/teto da ANEEL | `pld_fora_limites_regulatorios` | 0 | Sinalizar e investigar. Limites 2025: R$ 58,60 a R$ 1.542,23; 2026: R$ 57,31 a R$ 1.611,04 |

### Consistência
| Problema | Regra | Afetados | Decisão e justificativa |
|---|---|---|---|
| UF `PE` para usina de Sertãozinho (submercado Sudeste) | `usina_uf_incoerente_submercado` | 1 | Corrigir para `SP`: município (IBGE) e submercado concordam |
| Térmica gerando durante o overhaul (05/06, 18h–21h, com disponibilidade 0) | `medicao_geracao_durante_parada` | 4 | Corrigir para 0: parada registrada e disponibilidade 0 na própria linha |
| Energia maior que a disponibilidade da linha | `medicao_energia_maior_que_disponibilidade` | 30 | Mesmos casos das regras de Acurácia e acima; ver tratamentos |
| Recebido antes de ser medido (PCH, 05/08) | `medicao_recebido_antes_da_medicao` | 24 | Sinalizar: relógio do servidor; a energia não é afetada |
| Solar gerando à noite (UFV Sertão do Sol, 12/08, 20h–23h) | `medicao_solar_a_noite` | 4 | Corrigir para 0: impossibilidade física, relógio do medidor errado |

### Acurácia
| Problema | Regra | Afetados | Decisão e justificativa |
|---|---|---|---|
| Planilha em kWh (bagaço, 10/05) | `medicao_unidade_suspeita_kwh` | 24 | Corrigir ÷ 1000: valor 1000× a potência, origem MANUAL, e o resultado cabe na capacidade. Sem isso, a usina aparece gerando quase 5× o real |
| Vírgula deslocada (UHE Campo Real Iguaçu, 22/04 14h) | `medicao_acima_da_potencia_instalada` | 1 | Corrigir ÷ 10: o resultado fica a menos de 20% da potência da média das horas vizinhas |
| Pico de 499 MWh numa eólica de 50 MW (03/07 03h) | `medicao_acima_da_potencia_instalada` | 1 | Quarentena + valor anulado (`ANULADO`): nenhuma escala conhecida o aproxima dos vizinhos |
| Medidor travado (bagaço, 01 a 03/09, 72 h iguais) | `medicao_medidor_travado` | 72 | Sinalizar: valor plausível, não há evidência do correto |
| Lançamentos manuais | `medicao_lancamento_manual` | 30 antes, 24 depois | Sinalizar: auditoria |
| PLD atípico | `pld_valor_atipico` | 112 | Sinalizar: preço de escassez é real |

### Integridade referencial
| Problema | Regra | Afetados | Decisão e justificativa |
|---|---|---|---|
| Medições do equipamento 99, fora do cadastro (EOL, 15/10) | `medicao_usina_inexistente` | 24 | Quarentena: repetem leituras de outra usina, mas sem evidência para atribuir |

### Atualidade
| Problema | Regra | Afetados | Decisão e justificativa |
|---|---|---|---|
| UHE Tocantins: dados de 20 a 31/12 recebidos em fevereiro/2026 (≈ 50 dias de atraso) | `medicao_atraso_integracao` | 288 | Sinalizar: valor válido, atraso afeta a atualidade |
| UFV Campo Real Minas parou de enviar em 28/12 | `usina_sem_dados_recentes` | 1 usina | Sinalizar: alerta recomendado |

## 4. Resultado antes × depois

| Indicador | Antes | Depois |
|---|---|---|
| Medições | 78.798 | 78.744 (−54: 28 duplicadas, 25 órfãs ou sem usina, 1 com ano errado) |
| Geração total | 3.865.626 MWh | 3.121.119 MWh (**−19,3%**) |
| Geração da biomassa | 927.792 MWh | 185.990 MWh (a planilha em kWh quase quintuplicava) |
| Índice geral de qualidade | 97,67 | 98,94 |

Os itens que continuam com falha no DEPOIS são os que só foram sinalizados de propósito: energia nula, horas faltantes, medidor travado, atraso da integração, recebimento antes da medição, lançamentos manuais, data de início futura e usina sem dados recentes.

> Valores da execução de 13/11/2026 sobre o banco do Neon, com o PLD real da CCEE (65.472 linhas, 2025 até o último mês publicado de 2026). Detalhe completo em `docs/relatorio_qualidade_execucao.md`.

### Impacto da limpeza na receita

| Indicador | Antes | Depois | Variação |
|---|---|---|---|
| Receita valorada ao PLD | R$ 803.911.871,49 | R$ 638.208.469,59 | −20,61% |
| Receita da biomassa (BIO) | R$ 210.063.259,94 | R$ 44.738.199,08 | −78,70% |

A receita cai quase o mesmo que a geração (−19,3%), porque o erro de unidade da biomassa infla as duas na mesma proporção. Sem a limpeza, o painel mostraria R$ 165,7 milhões que não existem.

## 5. Regras do PLD (extração real)

- `pld_fora_limites_regulatorios`: 0 registros fora do piso/teto de 65.472 avaliados.
- `pld_horas_faltantes`: 0 horas ausentes nos 4 submercados (65.472 linhas).
- `pld_duplicado_submercado_hora`: 0 duplicados.
- `pld_valor_atipico`: 112 registros sinalizados. São preços de escassez reais, não erro: seguem no DW com a sinalização.

## 6. Limitações

- A correção de UF usa uma referência de municípios das nove usinas (`MUNICIPIO_UF` em `limpeza.py`). Um município novo cairia como "sinalizar".
- A regra de medidor travado usa 12 horas seguidas (`qualidade.travado_min_horas` no `config.yaml`) e ignora leituras zero.
- As regras de clima só avaliam depois que o clima foi baixado: rode `python -m src.qualidade.executar` de novo ao fim do pipeline.
