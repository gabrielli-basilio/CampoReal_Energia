# Relatório de qualidade: execução 1/2

Gerado em 13/11/2026 17:00. Origem avaliada na execução 1 (ANTES) e staging na 2 (DEPOIS).

## 1. Resumo por dimensão
| Dimensão | Regras | Falhas antes | Falhas depois | Índice antes | Índice depois |
|---|---|---|---|---|---|
| Acurácia | 5 | 264 | 208 | 99,92 | 99,94 |
| Atualidade | 2 | 317 | 289 | 94,24 | 94,26 |
| Completude | 6 | 104 | 103 | 98,31 | 99,98 |
| Consistência | 5 | 64 | 24 | 97,93 | 99,99 |
| Integridade referencial | 3 | 24 | 0 | 99,99 | 100,00 |
| Unicidade | 4 | 29 | 0 | 97,49 | 100,00 |
| Validade | 7 | 8 | 1 | 95,84 | 98,41 |

## 2. Todas as regras (antes × depois)
| Dimensão | Regra | Tabela | Avaliados | Falha antes | Falha depois | Decisão |
|---|---|---|---|---|---|---|
| Acurácia | medicao_acima_da_potencia_instalada | medicao_geracao | 78.773 | 26 | 0 | CORRIGIR |
| Acurácia | medicao_lancamento_manual | medicao_geracao | 78.798 | 30 | 24 | SINALIZAR |
| Acurácia | medicao_medidor_travado | medicao_geracao | 62.183 | 72 | 72 | SINALIZAR |
| Acurácia | medicao_unidade_suspeita_kwh | medicao_geracao | 78.773 | 24 | 0 | CORRIGIR |
| Acurácia | pld_valor_atipico | pld_horario | 65.472 | 112 | 112 | SINALIZAR |
| Atualidade | medicao_atraso_integracao | medicao_geracao | 78.798 | 316 | 288 | SINALIZAR |
| Atualidade | usina_sem_dados_recentes | medicao_geracao | 9 | 1 | 1 | SINALIZAR |
| Completude | clima_horas_faltantes | clima_horario | 78.840 | 0 | 0 | SINALIZAR |
| Completude | medicao_energia_nula | medicao_geracao | 78.798 | 6 | 7 | SINALIZAR |
| Completude | medicao_horas_faltantes | medicao_geracao | 78.840 | 96 | 96 | SINALIZAR |
| Completude | medicao_sem_usina | medicao_geracao | 78.798 | 1 | 0 | QUARENTENA |
| Completude | pld_horas_faltantes | pld_horario | 65.472 | 0 | 0 | SINALIZAR |
| Completude | usina_campo_obrigatorio_vazio | usina | 10 | 1 | 0 | DESCARTAR |
| Consistência | medicao_energia_maior_que_disponibilidade | medicao_geracao | 78.797 | 30 | 0 | CORRIGIR |
| Consistência | medicao_geracao_durante_parada | medicao_geracao | 1.672 | 4 | 0 | CORRIGIR |
| Consistência | medicao_recebido_antes_da_medicao | medicao_geracao | 78.798 | 25 | 24 | SINALIZAR |
| Consistência | medicao_solar_a_noite | medicao_geracao | 17.473 | 4 | 0 | CORRIGIR |
| Consistência | usina_uf_incoerente_submercado | usina | 10 | 1 | 0 | CORRIGIR |
| Integridade referencial | medicao_usina_inexistente | medicao_geracao | 78.797 | 24 | 0 | QUARENTENA |
| Integridade referencial | parada_usina_inexistente | parada_usina | 11 | 0 | 0 | QUARENTENA |
| Integridade referencial | usina_fonte_submercado_inexistente | usina | 10 | 0 | 0 | SINALIZAR |
| Unicidade | medicao_duplicada_usina_hora | medicao_geracao | 78.797 | 28 | 0 | DESCARTAR |
| Unicidade | parada_sobreposta | parada_usina | 11 | 0 | 0 | SINALIZAR |
| Unicidade | pld_duplicado_submercado_hora | pld_horario | 65.472 | 0 | 0 | DESCARTAR |
| Unicidade | usina_duplicada | usina | 10 | 1 | 0 | DESCARTAR |
| Validade | clima_fora_de_faixa | clima_horario | 146.880 | 0 | 0 | SINALIZAR |
| Validade | medicao_data_fora_do_periodo | medicao_geracao | 78.798 | 1 | 0 | QUARENTENA |
| Validade | medicao_energia_negativa | medicao_geracao | 78.798 | 4 | 0 | CORRIGIR |
| Validade | parada_intervalo_invertido | parada_usina | 11 | 1 | 0 | QUARENTENA |
| Validade | pld_fora_limites_regulatorios | pld_horario | 65.472 | 0 | 0 | SINALIZAR |
| Validade | usina_coordenada_fora_do_brasil | usina | 10 | 1 | 0 | CORRIGIR |
| Validade | usina_data_inicio_futura | usina | 10 | 1 | 1 | SINALIZAR |

## 3. Tratamentos (um por registro)
| Regra | Decisão | Registros |
|---|---|---|
| medicao_acima_da_potencia_instalada | QUARENTENA | 1 |
| medicao_acima_da_potencia_instalada | CORRIGIR | 1 |
| medicao_atraso_integracao | SINALIZAR | 288 |
| medicao_data_fora_do_periodo | QUARENTENA | 1 |
| medicao_duplicada_usina_hora | DESCARTAR | 28 |
| medicao_energia_negativa | CORRIGIR | 4 |
| medicao_energia_nula | SINALIZAR | 6 |
| medicao_geracao_durante_parada | CORRIGIR | 4 |
| medicao_horas_faltantes | SINALIZAR | 2 |
| medicao_lancamento_manual | SINALIZAR | 24 |
| medicao_medidor_travado | SINALIZAR | 72 |
| medicao_recebido_antes_da_medicao | SINALIZAR | 24 |
| medicao_sem_usina | QUARENTENA | 1 |
| medicao_solar_a_noite | CORRIGIR | 4 |
| medicao_unidade_suspeita_kwh | CORRIGIR | 24 |
| medicao_usina_inexistente | QUARENTENA | 24 |
| parada_intervalo_invertido | QUARENTENA | 1 |
| usina_coordenada_fora_do_brasil | CORRIGIR | 1 |
| usina_data_inicio_futura | SINALIZAR | 1 |
| usina_duplicada | DESCARTAR | 1 |
| usina_sem_dados_recentes | SINALIZAR | 1 |
| usina_uf_incoerente_submercado | CORRIGIR | 1 |

## 4. Quarentena
| Tabela | Regra | Registros |
|---|---|---|
| medicao_geracao | medicao_acima_da_potencia_instalada | 1 |
| medicao_geracao | medicao_data_fora_do_periodo | 1 |
| medicao_geracao | medicao_sem_usina | 1 |
| medicao_geracao | medicao_usina_inexistente | 24 |
| parada_usina | parada_intervalo_invertido | 1 |

## 5. Impacto da limpeza nos indicadores de negócio
| Indicador | Recorte | Antes | Depois | Diferença | Variação |
|---|---|---|---|---|---|
| geracao_mwh | TOTAL | 3.865.626,4 | 3.121.118,7 | -744.507,8 | -19,26% |
| geracao_mwh | fonte:BIO | 927.792,2 | 185.989,7 | -741.802,4 | -79,95% |
| geracao_mwh | fonte:EOL | 629.673,7 | 629.178,1 | -495,6 | -0,08% |
| geracao_mwh | fonte:PCH | 130.846,4 | 130.789,9 | -56,5 | -0,04% |
| geracao_mwh | fonte:UFV | 281.523,1 | 281.056,0 | -467,2 | -0,17% |
| geracao_mwh | fonte:UHE | 1.514.383,2 | 1.513.225,1 | -1.158,1 | -0,08% |
| geracao_mwh | fonte:UTE | 381.407,9 | 380.879,9 | -528,0 | -0,14% |
| geracao_mwh | submercado:N | 921.957,9 | 921.429,9 | -528,0 | -0,06% |
| geracao_mwh | submercado:NE | 662.661,1 | 662.547,7 | -113,4 | -0,02% |
| geracao_mwh | submercado:S | 1.240.560,1 | 1.238.846,6 | -1.713,6 | -0,14% |
| geracao_mwh | submercado:SE | 1.040.447,3 | 298.294,5 | -742.152,8 | -71,33% |
| receita_pld_rs | TOTAL | R$ 803.911.871,49 | R$ 638.208.469,59 | R$ -165.703.401,90 | -20,61% |
| receita_pld_rs | fonte:BIO | R$ 210.063.259,94 | R$ 44.738.199,08 | R$ -165.325.060,86 | -78,70% |
| receita_pld_rs | fonte:EOL | R$ 129.964.313,72 | R$ 129.901.718,80 | R$ -62.594,92 | -0,05% |
| receita_pld_rs | fonte:PCH | R$ 28.881.614,53 | R$ 28.878.304,57 | R$ -3.309,96 | -0,01% |
| receita_pld_rs | fonte:UFV | R$ 42.730.538,62 | R$ 42.689.539,44 | R$ -40.999,18 | -0,10% |
| receita_pld_rs | fonte:UHE | R$ 304.819.854,64 | R$ 304.720.144,38 | R$ -99.710,26 | -0,03% |
| receita_pld_rs | fonte:UTE | R$ 87.452.290,04 | R$ 87.280.563,32 | R$ -171.726,72 | -0,20% |
| receita_pld_rs | submercado:N | R$ 173.622.587,25 | R$ 173.450.860,53 | R$ -171.726,72 | -0,10% |
| receita_pld_rs | submercado:NE | R$ 121.055.827,81 | R$ 121.035.558,91 | R$ -20.268,90 | -0,02% |
| receita_pld_rs | submercado:S | R$ 279.523.747,38 | R$ 279.357.933,00 | R$ -165.814,38 | -0,06% |
| receita_pld_rs | submercado:SE | R$ 229.709.709,06 | R$ 64.364.117,16 | R$ -165.345.591,90 | -71,98% |

## 6. Fontes externas (PLD e clima)
| Regra | Avaliados | Com falha |
|---|---|---|
| pld_horas_faltantes | 65.472 | 0 |
| clima_horas_faltantes | 78.840 | 0 |
| pld_fora_limites_regulatorios | 65.472 | 0 |
| clima_fora_de_faixa | 146.880 | 0 |
| pld_valor_atipico | 65.472 | 112 |

Se `pld_fora_limites_regulatorios` ou `pld_horas_faltantes` tiverem falha, investigue (limite configurado errado em `limites_pld`? hora faltando na CCEE?) e registre a conclusão em `docs/relatorio_qualidade.md`. Regra com 0 avaliados significa tabela ainda vazia: rode o pipeline e esta avaliação de novo.
