-- Staging do cadastro e da operação, já limpa. Saída da etapa de qualidade e
-- entrada do DW (ver contrato em docs/modelagem.md, seção 10).
-- As tabelas são recriadas a cada limpeza (TRUNCATE + carga); a origem não é tocada.

CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE IF NOT EXISTS staging.usina (
    id_usina              INTEGER      PRIMARY KEY,
    cod_usina             VARCHAR(12)  NOT NULL UNIQUE,
    nome                  VARCHAR(80)  NOT NULL,
    id_fonte              SMALLINT     NOT NULL,
    cod_fonte             VARCHAR(10)  NOT NULL,
    cod_submercado        VARCHAR(2)   NOT NULL,
    uf                    CHAR(2)      NOT NULL,
    municipio             VARCHAR(60)  NOT NULL,
    latitude              NUMERIC(9,6) NOT NULL,
    longitude             NUMERIC(9,6) NOT NULL,
    potencia_mw           NUMERIC(8,2) NOT NULL,
    data_inicio_operacao  DATE         NOT NULL,
    situacao              VARCHAR(20)  NOT NULL,
    flags_qualidade       TEXT
);

CREATE TABLE IF NOT EXISTS staging.parada_usina (
    id_parada   INTEGER      PRIMARY KEY,
    id_usina    INTEGER      NOT NULL,
    cod_usina   VARCHAR(12)  NOT NULL,
    inicio      TIMESTAMP    NOT NULL,
    fim         TIMESTAMP    NOT NULL,
    tipo        VARCHAR(20)  NOT NULL,
    motivo      VARCHAR(120) NOT NULL,
    CHECK (fim >= inicio)
);

-- Grão: 1 usina x 1 hora (sem duplicidade, sem usina órfã).
CREATE TABLE IF NOT EXISTS staging.medicao_geracao (
    id_medicao          BIGINT        PRIMARY KEY,
    id_usina            INTEGER       NOT NULL,
    cod_usina           VARCHAR(12)   NOT NULL,
    data_hora           TIMESTAMP     NOT NULL,
    energia_mwh         NUMERIC(12,3),
    disponibilidade_mw  NUMERIC(8,2),
    origem              VARCHAR(20),
    recebido_em         TIMESTAMP,
    status_qualidade    VARCHAR(12)   NOT NULL DEFAULT 'OK'
                        CHECK (status_qualidade IN ('OK', 'CORRIGIDO', 'SINALIZADO', 'ANULADO')),
    flags_qualidade     TEXT,
    UNIQUE (id_usina, data_hora)
);
CREATE INDEX IF NOT EXISTS ix_stg_medicao_cod_data ON staging.medicao_geracao (cod_usina, data_hora);
