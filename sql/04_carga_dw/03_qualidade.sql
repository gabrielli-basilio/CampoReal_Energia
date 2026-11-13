-- Roda só quando o schema qualidade (etapa do Biel) já existe.
SET search_path TO dw_campo_real;

TRUNCATE fato_qualidade, fato_impacto_limpeza;

-- dim_regra_qualidade
INSERT INTO dim_regra_qualidade VALUES (-1, 'desconhecida', 'N/D', 'N/D', 'Regra não cadastrada', NULL)
ON CONFLICT (sk_regra) DO NOTHING;
INSERT INTO dim_regra_qualidade (sk_regra, regra, dimensao, tabela, descricao, decisao)
SELECT COALESCE((SELECT MAX(sk_regra) FROM dim_regra_qualidade), 0) + ROW_NUMBER() OVER (ORDER BY r.regra),
       r.regra, r.dimensao, r.tabela, r.descricao, r.decisao
FROM (SELECT DISTINCT ON (regra) regra, dimensao, tabela, descricao, decisao
      FROM qualidade.metricas ORDER BY regra, id_metrica DESC) r
WHERE NOT EXISTS (SELECT 1 FROM dim_regra_qualidade d WHERE d.regra = r.regra);

-- fato_qualidade: última execução de cada fase
INSERT INTO fato_qualidade (id_execucao, sk_regra, sk_tempo_execucao, fase, registros_avaliados, registros_falha,
                            percentual_falha, indice_qualidade)
SELECT m.id_execucao, COALESCE(r.sk_regra, -1),
       COALESCE(t.sk_tempo, -1), m.fase, m.registros_avaliados, m.registros_falha, m.percentual_falha,
       100 - m.percentual_falha
FROM qualidade.metricas m
JOIN (SELECT fase, MAX(id_execucao) AS id_execucao FROM qualidade.execucao GROUP BY fase) ult
  ON ult.id_execucao = m.id_execucao
LEFT JOIN dim_regra_qualidade r ON r.regra = m.regra
LEFT JOIN dim_tempo t ON t.data_hora = DATE_TRUNC('hour', m.executado_em AT TIME ZONE 'America/Sao_Paulo');

INSERT INTO fato_impacto_limpeza
SELECT indicador, recorte, valor_antes, valor_depois, diferenca, variacao_pct FROM qualidade.impacto_limpeza;
