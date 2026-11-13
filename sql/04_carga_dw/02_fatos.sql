SET search_path TO dw_campo_real;

TRUNCATE fato_geracao, fato_pld, fato_clima, fato_parada_hora;

-- Usina vigente na hora do fato (SCD 2)
CREATE TEMP TABLE usina_vigente AS
SELECT d.sk_usina, d.cod_usina, d.valido_de, d.valido_ate, d.potencia_mw, f.sk_fonte, s.sk_submercado, d.cod_submercado
FROM dim_usina d
JOIN dim_fonte f ON f.cod_fonte = d.cod_fonte
JOIN dim_submercado s ON s.cod_submercado = d.cod_submercado
WHERE d.sk_usina > 0;

-- fato_pld
INSERT INTO fato_pld (sk_tempo, sk_submercado, pld_rs_mwh)
SELECT COALESCE(t.sk_tempo, -1), COALESCE(s.sk_submercado, -1), p.pld_rs_mwh
FROM staging.pld_horario p
LEFT JOIN dim_tempo t ON t.data_hora = p.data_hora
LEFT JOIN dim_submercado s ON s.cod_submercado = TRIM(p.cod_submercado);

-- fato_geracao: geração valorada ao PLD da hora no submercado da usina
INSERT INTO fato_geracao (sk_tempo, sk_usina, sk_fonte, sk_submercado, sk_status, energia_mwh, disponibilidade_mw,
                          potencia_mw, pld_rs_mwh, receita_pld_rs, flags_qualidade)
SELECT COALESCE(t.sk_tempo, -1),
       COALESCE(u.sk_usina, -1),
       COALESCE(u.sk_fonte, -1),
       COALESCE(u.sk_submercado, -1),
       COALESCE(st.sk_status, -1),
       m.energia_mwh,
       m.disponibilidade_mw,
       u.potencia_mw,
       p.pld_rs_mwh,
       ROUND(m.energia_mwh * p.pld_rs_mwh, 2),
       m.flags_qualidade
FROM staging.medicao_geracao m
LEFT JOIN dim_tempo t ON t.data_hora = m.data_hora
LEFT JOIN usina_vigente u ON u.cod_usina = m.cod_usina AND m.data_hora::DATE BETWEEN u.valido_de AND u.valido_ate
LEFT JOIN dim_status_qualidade st ON st.status = m.status_qualidade
LEFT JOIN fato_pld p ON p.sk_tempo = t.sk_tempo AND p.sk_submercado = u.sk_submercado;

-- fato_clima
INSERT INTO fato_clima (sk_tempo, sk_usina, sk_submercado, radiacao_wm2, vento_100m_kmh, temperatura_c, precipitacao_mm)
SELECT COALESCE(t.sk_tempo, -1), COALESCE(u.sk_usina, -1), COALESCE(u.sk_submercado, -1),
       c.radiacao_wm2, c.vento_100m_kmh, c.temperatura_c, c.chuva_mm
FROM staging.clima_horario c
LEFT JOIN dim_tempo t ON t.data_hora = c.data_hora
LEFT JOIN usina_vigente u ON u.cod_usina = c.cod_usina AND c.data_hora::DATE BETWEEN u.valido_de AND u.valido_ate;

-- fato_parada_hora: energia não gerada = média gerada pela usina no mesmo mês e hora, fora de paradas
CREATE TEMP TABLE perfil_esperado AS
SELECT g.sk_usina, t.mes, t.hora, AVG(g.energia_mwh) AS energia_media
FROM fato_geracao g
JOIN dim_tempo t ON t.sk_tempo = g.sk_tempo
WHERE g.energia_mwh IS NOT NULL
  AND g.sk_status <> 4
  AND NOT EXISTS (SELECT 1 FROM staging.parada_usina p
                  JOIN dim_usina d ON d.cod_usina = p.cod_usina
                  WHERE d.sk_usina = g.sk_usina AND t.data_hora BETWEEN p.inicio AND p.fim)
GROUP BY g.sk_usina, t.mes, t.hora;

INSERT INTO fato_parada_hora (sk_tempo, sk_usina, sk_tipo_parada, sk_submercado, id_parada, motivo,
                              horas_indisponiveis, energia_nao_gerada_mwh, receita_nao_gerada_rs)
SELECT t.sk_tempo, u.sk_usina, COALESCE(tp.sk_tipo_parada, -1), u.sk_submercado, p.id_parada, p.motivo,
       1, ROUND(e.energia_media, 3), ROUND(e.energia_media * f.pld_rs_mwh, 2)
FROM staging.parada_usina p
CROSS JOIN LATERAL generate_series(p.inicio, p.fim, INTERVAL '1 hour') AS h (data_hora)
JOIN dim_tempo t ON t.data_hora = h.data_hora
JOIN usina_vigente u ON u.cod_usina = p.cod_usina AND h.data_hora::DATE BETWEEN u.valido_de AND u.valido_ate
LEFT JOIN dim_tipo_parada tp ON tp.tipo = p.tipo
LEFT JOIN perfil_esperado e ON e.sk_usina = u.sk_usina AND e.mes = t.mes AND e.hora = t.hora
LEFT JOIN fato_pld f ON f.sk_tempo = t.sk_tempo AND f.sk_submercado = u.sk_submercado;

DROP TABLE usina_vigente, perfil_esperado;
