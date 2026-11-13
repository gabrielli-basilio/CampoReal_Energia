SET search_path TO dw_campo_real;

-- Feriados nacionais de 2026: a origem só traz 2025 e o PLD vai até 2026 (calendário oficial, Lei 662/1949 e Lei 14.759/2023).
CREATE TEMP TABLE feriado AS
SELECT data, descricao, tipo FROM campo_real_energia.feriado_nacional
UNION ALL
SELECT * FROM (VALUES
  (DATE '2026-01-01', 'Confraternização Universal', 'Feriado'),
  (DATE '2026-02-16', 'Carnaval', 'Ponto facultativo'),
  (DATE '2026-02-17', 'Carnaval', 'Ponto facultativo'),
  (DATE '2026-04-03', 'Sexta-feira Santa', 'Feriado'),
  (DATE '2026-04-21', 'Tiradentes', 'Feriado'),
  (DATE '2026-05-01', 'Dia do Trabalho', 'Feriado'),
  (DATE '2026-06-04', 'Corpus Christi', 'Ponto facultativo'),
  (DATE '2026-09-07', 'Independência do Brasil', 'Feriado'),
  (DATE '2026-10-12', 'Nossa Senhora Aparecida', 'Feriado'),
  (DATE '2026-11-02', 'Finados', 'Feriado'),
  (DATE '2026-11-15', 'Proclamação da República', 'Feriado'),
  (DATE '2026-11-20', 'Dia da Consciência Negra', 'Feriado'),
  (DATE '2026-12-25', 'Natal', 'Feriado')
) AS f (data, descricao, tipo);

-- dim_tempo: todas as horas de 2025 e 2026 + membro desconhecido
INSERT INTO dim_tempo (sk_tempo, nome_mes, nome_dia_semana, faixa_horaria, nome_feriado, estacao_ano,
                       periodo_hidrologico, patamar_carga)
VALUES (-1, 'N/D', 'N/D', 'N/D', 'N/D', 'N/D', 'N/D', 'N/D')
ON CONFLICT (sk_tempo) DO NOTHING;

INSERT INTO dim_tempo
SELECT
    TO_CHAR(t, 'YYYYMMDDHH24')::INT,
    t,
    t::DATE,
    EXTRACT(YEAR FROM t),
    EXTRACT(QUARTER FROM t),
    EXTRACT(MONTH FROM t),
    (ARRAY['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'])[EXTRACT(MONTH FROM t)],
    TO_CHAR(t, 'YYYY-MM'),
    EXTRACT(DAY FROM t),
    EXTRACT(ISODOW FROM t),
    (ARRAY['Segunda','Terça','Quarta','Quinta','Sexta','Sábado','Domingo'])[EXTRACT(ISODOW FROM t)],
    EXTRACT(HOUR FROM t),
    CASE WHEN EXTRACT(HOUR FROM t) < 6 THEN 'Madrugada'
         WHEN EXTRACT(HOUR FROM t) < 12 THEN 'Manhã'
         WHEN EXTRACT(HOUR FROM t) < 18 THEN 'Tarde'
         ELSE 'Noite' END,
    EXTRACT(ISODOW FROM t) IN (6, 7),
    f.data IS NOT NULL AND f.tipo = 'Feriado',
    f.descricao,
    EXTRACT(ISODOW FROM t) NOT IN (6, 7) AND (f.data IS NULL OR f.tipo <> 'Feriado'),
    CASE WHEN TO_CHAR(t, 'MMDD') >= '1221' OR TO_CHAR(t, 'MMDD') < '0320' THEN 'Verão'
         WHEN TO_CHAR(t, 'MMDD') < '0621' THEN 'Outono'
         WHEN TO_CHAR(t, 'MMDD') < '0922' THEN 'Inverno'
         ELSE 'Primavera' END,
    CASE WHEN EXTRACT(MONTH FROM t) IN (12, 1, 2, 3, 4) THEN 'Úmido' ELSE 'Seco' END,
    EXTRACT(MONTH FROM t) BETWEEN 4 AND 11,
    CASE WHEN EXTRACT(HOUR FROM t) BETWEEN 18 AND 20
              AND EXTRACT(ISODOW FROM t) NOT IN (6, 7) AND (f.data IS NULL OR f.tipo <> 'Feriado') THEN 'Pesado'
         WHEN EXTRACT(HOUR FROM t) <= 6
              OR EXTRACT(ISODOW FROM t) = 7 OR f.tipo = 'Feriado' THEN 'Leve'
         ELSE 'Médio' END
FROM generate_series(TIMESTAMP '2025-01-01 00:00', TIMESTAMP '2026-12-31 23:00', INTERVAL '1 hour') AS g (t)
LEFT JOIN feriado f ON f.data = t::DATE
ON CONFLICT (sk_tempo) DO NOTHING;

-- dim_submercado
INSERT INTO dim_submercado VALUES (-1, '?', 'Desconhecido', 'Desconhecido')
ON CONFLICT (sk_submercado) DO NOTHING;
INSERT INTO dim_submercado (sk_submercado, cod_submercado, nome, regioes)
SELECT ROW_NUMBER() OVER (ORDER BY CASE TRIM(cod_submercado) WHEN 'SE' THEN 1 WHEN 'S' THEN 2 WHEN 'NE' THEN 3 ELSE 4 END),
       TRIM(cod_submercado), nome, regioes
FROM campo_real_energia.submercado
ON CONFLICT (cod_submercado) DO UPDATE SET nome = EXCLUDED.nome, regioes = EXCLUDED.regioes;

-- dim_fonte
INSERT INTO dim_fonte VALUES (-1, '?', 'Desconhecida', 'N/D', 'N/D')
ON CONFLICT (sk_fonte) DO NOTHING;
INSERT INTO dim_fonte (sk_fonte, cod_fonte, descricao, renovavel, intermitente)
SELECT id_fonte, cod_fonte, descricao,
       CASE WHEN renovavel THEN 'Renovável' ELSE 'Não renovável' END,
       CASE WHEN intermitente THEN 'Intermitente' ELSE 'Despachável' END
FROM campo_real_energia.fonte_energia
ON CONFLICT (cod_fonte) DO UPDATE SET descricao = EXCLUDED.descricao, renovavel = EXCLUDED.renovavel,
                                      intermitente = EXCLUDED.intermitente;

-- dim_tipo_parada
INSERT INTO dim_tipo_parada VALUES
  (-1, 'Desconhecido', 'Tipo de parada não informado'),
  (1, 'Programada', 'Manutenção planejada com antecedência'),
  (2, 'Forçada', 'Falha ou restrição não planejada')
ON CONFLICT (sk_tipo_parada) DO NOTHING;

-- dim_status_qualidade
INSERT INTO dim_status_qualidade VALUES
  (-1, 'DESCONHECIDO', 'Status não informado', FALSE),
  (1, 'OK', 'Passou em todas as regras', TRUE),
  (2, 'CORRIGIDO', 'Valor corrigido por regra justificada (ver qualidade.tratamento)', TRUE),
  (3, 'SINALIZADO', 'Valor mantido, mas com alerta (atraso, medidor travado, nulo)', TRUE),
  (4, 'ANULADO', 'Valor impossível retirado; original em qualidade.quarentena', FALSE)
ON CONFLICT (sk_status) DO NOTHING;

-- dim_usina (SCD tipo 2)
INSERT INTO dim_usina (sk_usina, cod_usina, nome, cod_fonte, fonte, cod_submercado, submercado, uf, municipio,
                       hash_atributos, valido_de, valido_ate, atual, versao, situacao)
VALUES (-1, '?', 'Desconhecida', '?', 'Desconhecida', '?', 'Desconhecido', '??', 'Desconhecido',
        REPEAT('0', 32), DATE '1900-01-01', DATE '9999-12-31', TRUE, 1, 'N/D')
ON CONFLICT (sk_usina) DO NOTHING;

CREATE TEMP TABLE usina_nova AS
SELECT u.*, f.descricao AS fonte, s.nome AS submercado,
       MD5(CONCAT_WS('|', u.nome, u.cod_fonte, u.cod_submercado, u.uf, u.municipio, u.latitude, u.longitude,
                     u.potencia_mw, u.data_inicio_operacao, u.situacao)) AS hash_atributos
FROM staging.usina u
JOIN campo_real_energia.fonte_energia f ON f.cod_fonte = u.cod_fonte
JOIN campo_real_energia.submercado s ON TRIM(s.cod_submercado) = TRIM(u.cod_submercado);

-- Fecha a versão atual das usinas que mudaram
UPDATE dim_usina d
SET valido_ate = CURRENT_DATE - 1, atual = FALSE
FROM usina_nova n
WHERE d.cod_usina = n.cod_usina AND d.atual AND d.hash_atributos <> n.hash_atributos;

-- Insere a primeira versão (vale desde sempre) ou a nova versão (vale a partir de hoje)
INSERT INTO dim_usina (sk_usina, cod_usina, nome, cod_fonte, fonte, cod_submercado, submercado, uf, municipio,
                       latitude, longitude, potencia_mw, data_inicio_operacao, situacao, flags_qualidade,
                       hash_atributos, valido_de, valido_ate, atual, versao)
SELECT NEXTVAL('seq_sk_usina'), n.cod_usina, n.nome, n.cod_fonte, n.fonte, TRIM(n.cod_submercado), n.submercado,
       n.uf, n.municipio, n.latitude, n.longitude, n.potencia_mw, n.data_inicio_operacao, n.situacao,
       n.flags_qualidade, n.hash_atributos,
       CASE WHEN v.versao IS NULL THEN DATE '1900-01-01' ELSE CURRENT_DATE END,
       DATE '9999-12-31', TRUE, COALESCE(v.versao, 0) + 1
FROM usina_nova n
LEFT JOIN (SELECT cod_usina, MAX(versao) AS versao FROM dim_usina GROUP BY cod_usina) v ON v.cod_usina = n.cod_usina
WHERE NOT EXISTS (SELECT 1 FROM dim_usina d WHERE d.cod_usina = n.cod_usina AND d.atual);

DROP TABLE feriado, usina_nova;
