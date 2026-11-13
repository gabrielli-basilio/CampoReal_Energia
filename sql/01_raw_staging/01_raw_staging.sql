-- Camada raw: o dado exatamente como chegou, com data/hora da extracao e origem.
-- Camada staging: dado tratado, com tipos e chave definidos.
-- Pode rodar varias vezes (IF NOT EXISTS).

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;

-- Log de cada execucao
CREATE TABLE IF NOT EXISTS raw.log_extracao (
    id_execucao      SERIAL PRIMARY KEY,
    fonte            VARCHAR(30)  NOT NULL,
    recurso          VARCHAR(80),
    inicio           TIMESTAMP    NOT NULL DEFAULT NOW(),
    fim              TIMESTAMP,
    linhas_lidas     INTEGER      NOT NULL DEFAULT 0,
    linhas_gravadas  INTEGER      NOT NULL DEFAULT 0,
    status           VARCHAR(20)  NOT NULL DEFAULT 'EXECUTANDO',
    erro             TEXT
);

-- PLD bruto da CCEE: 1 linha por registro retornado pela API (JSON como veio)
-- Grao: 1 registro da API
CREATE TABLE IF NOT EXISTS raw.pld_horario (
    id_raw        BIGSERIAL PRIMARY KEY,
    fonte         VARCHAR(30)  NOT NULL DEFAULT 'CCEE',
    resource_id   VARCHAR(80)  NOT NULL,
    ano           SMALLINT     NOT NULL,
    posicao       INTEGER      NOT NULL,      -- posicao do registro na API (offset)
    registro      JSONB        NOT NULL,
    extraido_em   TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE (resource_id, posicao)
);

-- Clima bruto do Open-Meteo: 1 linha por usina com a resposta inteira
CREATE TABLE IF NOT EXISTS raw.clima (
    id_raw        BIGSERIAL PRIMARY KEY,
    fonte         VARCHAR(30)  NOT NULL DEFAULT 'OPEN-METEO',
    cod_usina     VARCHAR(12)  NOT NULL,
    latitude      NUMERIC(9,6) NOT NULL,
    longitude     NUMERIC(9,6) NOT NULL,
    data_inicio   DATE         NOT NULL,
    data_fim      DATE         NOT NULL,
    resposta      JSONB        NOT NULL,
    extraido_em   TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE (cod_usina, data_inicio, data_fim)
);

-- PLD tratado. Grao: 1 submercado x 1 hora
CREATE TABLE IF NOT EXISTS staging.pld_horario (
    cod_submercado  CHAR(2)       NOT NULL,
    data_hora       TIMESTAMP     NOT NULL,
    pld_rs_mwh      NUMERIC(12,2),
    extraido_em     TIMESTAMP     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (cod_submercado, data_hora)
);

-- Clima tratado. Grao: 1 usina x 1 hora
CREATE TABLE IF NOT EXISTS staging.clima_horario (
    cod_usina        VARCHAR(12)  NOT NULL,
    data_hora        TIMESTAMP    NOT NULL,
    temperatura_c    NUMERIC(6,2),
    radiacao_wm2     NUMERIC(8,2),
    vento_100m_kmh   NUMERIC(6,2),
    chuva_mm         NUMERIC(6,2),
    extraido_em      TIMESTAMP    NOT NULL DEFAULT NOW(),
    PRIMARY KEY (cod_usina, data_hora)
);