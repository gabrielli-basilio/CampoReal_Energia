-- Data warehouse da Campo Real Energia (star schema).
-- Grãos declarados em docs/modelagem.md e repetidos no comentário de cada fato.

CREATE SCHEMA IF NOT EXISTS dw_campo_real;
SET search_path TO dw_campo_real;

CREATE TABLE IF NOT EXISTS dim_tempo (
    sk_tempo             INTEGER      PRIMARY KEY,          -- yyyymmddhh; -1 = desconhecido
    data_hora            TIMESTAMP    UNIQUE,
    data                 DATE,
    ano                  SMALLINT,
    trimestre            SMALLINT,
    mes                  SMALLINT,
    nome_mes             VARCHAR(10),
    ano_mes              CHAR(7),
    dia                  SMALLINT,
    dia_semana           SMALLINT,                          -- 1 = segunda ... 7 = domingo
    nome_dia_semana      VARCHAR(10),
    hora                 SMALLINT,
    faixa_horaria        VARCHAR(10),
    fim_de_semana        BOOLEAN,
    feriado              BOOLEAN,
    nome_feriado         VARCHAR(60),
    dia_util             BOOLEAN,
    estacao_ano          VARCHAR(10),
    periodo_hidrologico  VARCHAR(10),
    safra_cana           BOOLEAN,
    patamar_carga        VARCHAR(10)
);

CREATE TABLE IF NOT EXISTS dim_submercado (
    sk_submercado   SMALLINT     PRIMARY KEY,
    cod_submercado  VARCHAR(2)   NOT NULL UNIQUE,
    nome            VARCHAR(40)  NOT NULL,
    regioes         VARCHAR(80)  NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_fonte (
    sk_fonte      SMALLINT     PRIMARY KEY,
    cod_fonte     VARCHAR(10)  NOT NULL UNIQUE,
    descricao     VARCHAR(40)  NOT NULL,
    renovavel     VARCHAR(15)  NOT NULL,
    intermitente  VARCHAR(15)  NOT NULL
);

-- SCD tipo 2: cada mudança de atributo rastreado gera uma nova versão.
CREATE TABLE IF NOT EXISTS dim_usina (
    sk_usina              INTEGER      PRIMARY KEY,
    cod_usina             VARCHAR(12)  NOT NULL,
    nome                  VARCHAR(80)  NOT NULL,
    cod_fonte             VARCHAR(10)  NOT NULL,
    fonte                 VARCHAR(40)  NOT NULL,
    cod_submercado        VARCHAR(2)   NOT NULL,
    submercado            VARCHAR(40)  NOT NULL,
    uf                    CHAR(2)      NOT NULL,
    municipio             VARCHAR(60)  NOT NULL,
    latitude              NUMERIC(9,6),
    longitude             NUMERIC(9,6),
    potencia_mw           NUMERIC(8,2),
    data_inicio_operacao  DATE,
    situacao              VARCHAR(20)  NOT NULL,
    flags_qualidade       TEXT,
    hash_atributos        CHAR(32)     NOT NULL,
    valido_de             DATE         NOT NULL,
    valido_ate            DATE         NOT NULL,
    atual                 BOOLEAN      NOT NULL,
    versao                SMALLINT     NOT NULL
);
CREATE SEQUENCE IF NOT EXISTS seq_sk_usina START 1;
CREATE INDEX IF NOT EXISTS ix_dim_usina_cod ON dim_usina (cod_usina, valido_de, valido_ate);

CREATE TABLE IF NOT EXISTS dim_tipo_parada (
    sk_tipo_parada  SMALLINT     PRIMARY KEY,
    tipo            VARCHAR(20)  NOT NULL UNIQUE,
    descricao       VARCHAR(80)  NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_status_qualidade (
    sk_status   SMALLINT     PRIMARY KEY,
    status      VARCHAR(20)  NOT NULL UNIQUE,
    descricao   VARCHAR(120) NOT NULL,
    confiavel   BOOLEAN      NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_regra_qualidade (
    sk_regra   SMALLINT     PRIMARY KEY,
    regra      VARCHAR(80)  NOT NULL UNIQUE,
    dimensao   VARCHAR(30)  NOT NULL,
    tabela     VARCHAR(60)  NOT NULL,
    descricao  VARCHAR(255) NOT NULL,
    decisao    VARCHAR(20)
);

-- Grão: 1 usina x 1 hora de 2025 (horas medidas após a limpeza).
CREATE TABLE IF NOT EXISTS fato_geracao (
    sk_tempo            INTEGER      NOT NULL REFERENCES dim_tempo,
    sk_usina            INTEGER      NOT NULL REFERENCES dim_usina,
    sk_fonte            SMALLINT     NOT NULL REFERENCES dim_fonte,
    sk_submercado       SMALLINT     NOT NULL REFERENCES dim_submercado,
    sk_status           SMALLINT     NOT NULL REFERENCES dim_status_qualidade,
    energia_mwh         NUMERIC(12,3),
    disponibilidade_mw  NUMERIC(8,2),
    potencia_mw         NUMERIC(8,2) NOT NULL,
    pld_rs_mwh          NUMERIC(10,2),
    receita_pld_rs      NUMERIC(16,2),
    flags_qualidade     TEXT,
    CONSTRAINT pk_fato_geracao PRIMARY KEY (sk_tempo, sk_usina)
);

-- Grão: 1 submercado x 1 hora (PLD horário publicado pela CCEE, 2025 e 2026).
CREATE TABLE IF NOT EXISTS fato_pld (
    sk_tempo       INTEGER       NOT NULL REFERENCES dim_tempo,
    sk_submercado  SMALLINT      NOT NULL REFERENCES dim_submercado,
    pld_rs_mwh     NUMERIC(10,2) NOT NULL,
    CONSTRAINT pk_fato_pld PRIMARY KEY (sk_tempo, sk_submercado)
);

-- Grão: 1 usina x 1 hora (clima Open-Meteo na coordenada da usina).
CREATE TABLE IF NOT EXISTS fato_clima (
    sk_tempo         INTEGER      NOT NULL REFERENCES dim_tempo,
    sk_usina         INTEGER      NOT NULL REFERENCES dim_usina,
    sk_submercado    SMALLINT     NOT NULL REFERENCES dim_submercado,
    radiacao_wm2     NUMERIC(8,2),
    vento_100m_kmh   NUMERIC(8,2),
    temperatura_c    NUMERIC(6,2),
    precipitacao_mm  NUMERIC(8,2),
    CONSTRAINT pk_fato_clima PRIMARY KEY (sk_tempo, sk_usina)
);

-- Grão: 1 parada x 1 hora indisponível.
CREATE TABLE IF NOT EXISTS fato_parada_hora (
    sk_tempo               INTEGER       NOT NULL REFERENCES dim_tempo,
    sk_usina               INTEGER       NOT NULL REFERENCES dim_usina,
    sk_tipo_parada         SMALLINT      NOT NULL REFERENCES dim_tipo_parada,
    sk_submercado          SMALLINT      NOT NULL REFERENCES dim_submercado,
    id_parada              INTEGER       NOT NULL,
    motivo                 VARCHAR(120)  NOT NULL,
    horas_indisponiveis    NUMERIC(4,2)  NOT NULL,
    energia_nao_gerada_mwh NUMERIC(12,3),
    receita_nao_gerada_rs  NUMERIC(16,2),
    CONSTRAINT pk_fato_parada_hora PRIMARY KEY (sk_tempo, sk_usina, id_parada)
);

-- Grão: 1 regra x 1 execução da avaliação de qualidade (fase ANTES ou DEPOIS da limpeza).
CREATE TABLE IF NOT EXISTS fato_qualidade (
    id_execucao          BIGINT       NOT NULL,
    sk_regra             SMALLINT     NOT NULL REFERENCES dim_regra_qualidade,
    sk_tempo_execucao    INTEGER      NOT NULL REFERENCES dim_tempo,
    fase                 VARCHAR(10)  NOT NULL,
    registros_avaliados  INTEGER      NOT NULL,
    registros_falha      INTEGER      NOT NULL,
    percentual_falha     NUMERIC(7,4) NOT NULL,
    indice_qualidade     NUMERIC(7,4) NOT NULL,
    CONSTRAINT pk_fato_qualidade PRIMARY KEY (id_execucao, sk_regra)
);

-- Grão: 1 indicador de negócio x 1 recorte (fonte ou total), comparando antes e depois da limpeza.
CREATE TABLE IF NOT EXISTS fato_impacto_limpeza (
    indicador     VARCHAR(80)   NOT NULL,
    recorte       VARCHAR(40)   NOT NULL,
    valor_antes   NUMERIC(18,2),
    valor_depois  NUMERIC(18,2),
    diferenca     NUMERIC(18,2),
    variacao_pct  NUMERIC(9,4),
    CONSTRAINT pk_fato_impacto PRIMARY KEY (indicador, recorte)
);
