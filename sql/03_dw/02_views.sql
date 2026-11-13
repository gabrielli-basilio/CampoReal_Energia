SET search_path TO dw_campo_real;

-- P1: geração mensal e fator de capacidade por usina
CREATE OR REPLACE VIEW vw_geracao_mensal AS
SELECT t.ano_mes, u.cod_usina, u.nome AS usina, u.fonte, u.submercado,
       SUM(g.energia_mwh) AS geracao_mwh,
       SUM(g.potencia_mw) AS energia_possivel_mwh,
       100 * SUM(g.energia_mwh) / NULLIF(SUM(g.potencia_mw), 0) AS fator_capacidade_pct
FROM fato_geracao g
JOIN dim_tempo t ON t.sk_tempo = g.sk_tempo
JOIN dim_usina u ON u.sk_usina = g.sk_usina
GROUP BY t.ano_mes, u.cod_usina, u.nome, u.fonte, u.submercado;

-- P3: preço capturado e razão de captura por fonte (base: PLD médio de 2025 nos submercados onde a fonte gera)
CREATE OR REPLACE VIEW vw_captura_por_fonte AS
WITH pld_medio AS (
    SELECT p.sk_submercado, AVG(p.pld_rs_mwh) AS pld_medio
    FROM fato_pld p JOIN dim_tempo t ON t.sk_tempo = p.sk_tempo
    WHERE t.ano = 2025
    GROUP BY p.sk_submercado
),
por_sub AS (
    SELECT g.sk_fonte, g.sk_submercado,
           SUM(g.energia_mwh) FILTER (WHERE g.receita_pld_rs IS NOT NULL) AS geracao_mwh,
           SUM(g.receita_pld_rs) AS receita_rs
    FROM fato_geracao g
    GROUP BY g.sk_fonte, g.sk_submercado
)
SELECT f.descricao AS fonte,
       SUM(s.geracao_mwh) AS geracao_mwh,
       SUM(s.receita_rs) AS receita_rs,
       SUM(s.receita_rs) / NULLIF(SUM(s.geracao_mwh), 0) AS preco_capturado,
       SUM(s.geracao_mwh * pm.pld_medio) / NULLIF(SUM(s.geracao_mwh), 0) AS pld_medio_referencia,
       SUM(s.receita_rs) / NULLIF(SUM(s.geracao_mwh * pm.pld_medio), 0) AS razao_captura
FROM por_sub s
JOIN dim_fonte f ON f.sk_fonte = s.sk_fonte
JOIN pld_medio pm ON pm.sk_submercado = s.sk_submercado
GROUP BY f.descricao;

-- P4: mapa de calor hora x mês do PLD
CREATE OR REPLACE VIEW vw_pld_hora_mes AS
SELECT t.ano, t.mes, t.nome_mes, t.hora, s.cod_submercado, AVG(p.pld_rs_mwh) AS pld_medio
FROM fato_pld p
JOIN dim_tempo t ON t.sk_tempo = p.sk_tempo
JOIN dim_submercado s ON s.sk_submercado = p.sk_submercado
GROUP BY t.ano, t.mes, t.nome_mes, t.hora, s.cod_submercado;

-- P6: correlação clima x geração por usina
CREATE OR REPLACE VIEW vw_correlacao_clima AS
SELECT u.cod_usina, u.fonte,
       CORR(g.energia_mwh, c.radiacao_wm2) AS corr_radiacao,
       CORR(g.energia_mwh, c.vento_100m_kmh) AS corr_vento,
       CORR(g.energia_mwh, c.temperatura_c) AS corr_temperatura,
       COUNT(*) AS horas
FROM fato_geracao g
JOIN fato_clima c ON c.sk_tempo = g.sk_tempo AND c.sk_usina = g.sk_usina
JOIN dim_usina u ON u.sk_usina = g.sk_usina
WHERE g.energia_mwh IS NOT NULL
GROUP BY u.cod_usina, u.fonte;
