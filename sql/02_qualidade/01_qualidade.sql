-- Schema qualidade: tudo que a avaliação de qualidade grava (etapa da Biel).
-- Pode rodar várias vezes (IF NOT EXISTS). A origem NUNCA é alterada.

CREATE SCHEMA IF NOT EXISTS qualidade;

-- Uma linha por avaliação: ANTES da limpeza (sobre a origem) ou DEPOIS (sobre a staging).
CREATE TABLE IF NOT EXISTS qualidade.execucao (
    id_execucao  SERIAL       PRIMARY KEY,
    fase         VARCHAR(10)  NOT NULL CHECK (fase IN ('ANTES', 'DEPOIS')),
    inicio       TIMESTAMP    NOT NULL DEFAULT NOW(),
    fim          TIMESTAMP,
    observacao   TEXT
);

-- Resultado de cada regra em cada execução. Grão: 1 regra x 1 execução.
CREATE TABLE IF NOT EXISTS qualidade.metricas (
    id_metrica           BIGSERIAL    PRIMARY KEY,
    id_execucao          INTEGER      NOT NULL REFERENCES qualidade.execucao,
    fase                 VARCHAR(10)  NOT NULL,
    regra                VARCHAR(80)  NOT NULL,
    dimensao             VARCHAR(30)  NOT NULL,
    tabela               VARCHAR(60)  NOT NULL,
    descricao            VARCHAR(255) NOT NULL,
    decisao              VARCHAR(20),
    registros_avaliados  INTEGER      NOT NULL,
    registros_falha      INTEGER      NOT NULL,
    percentual_falha     NUMERIC(7,4) NOT NULL,
    executado_em         TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE (id_execucao, regra)
);

-- O que foi feito com cada registro problemático (só a última limpeza fica aqui).
CREATE TABLE IF NOT EXISTS qualidade.tratamento (
    id_tratamento  BIGSERIAL    PRIMARY KEY,
    id_execucao    INTEGER      REFERENCES qualidade.execucao,
    regra          VARCHAR(80)  NOT NULL,
    tabela         VARCHAR(60)  NOT NULL,
    chave          VARCHAR(120) NOT NULL,
    decisao        VARCHAR(20)  NOT NULL CHECK (decisao IN ('CORRIGIR', 'DESCARTAR', 'QUARENTENA', 'SINALIZAR')),
    justificativa  TEXT         NOT NULL,
    valor_antes    TEXT,
    valor_depois   TEXT,
    registrado_em  TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- Registros retirados do caminho, guardados inteiros para análise humana.
CREATE TABLE IF NOT EXISTS qualidade.quarentena (
    id_quarentena  BIGSERIAL    PRIMARY KEY,
    id_execucao    INTEGER      REFERENCES qualidade.execucao,
    tabela         VARCHAR(60)  NOT NULL,
    regra          VARCHAR(80)  NOT NULL,
    motivo         TEXT         NOT NULL,
    registro       JSONB        NOT NULL,
    registrado_em  TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- Profiling de cada coluna. Fica ligado à execução ANTES.
CREATE TABLE IF NOT EXISTS qualidade.profiling (
    id_execucao  INTEGER      NOT NULL REFERENCES qualidade.execucao,
    tabela       VARCHAR(80)  NOT NULL,
    coluna       VARCHAR(80)  NOT NULL,
    tipo_dado    VARCHAR(40),
    registros    BIGINT,
    nulos        BIGINT,
    pct_nulos    NUMERIC(7,3),
    distintos    BIGINT,
    minimo       TEXT,
    maximo       TEXT,
    media        NUMERIC(20,4),
    q1           NUMERIC(20,4),
    mediana      NUMERIC(20,4),
    q3           NUMERIC(20,4),
    PRIMARY KEY (id_execucao, tabela, coluna)
);

-- Indicadores de negócio antes x depois da limpeza (só o último cálculo fica aqui).
CREATE TABLE IF NOT EXISTS qualidade.impacto_limpeza (
    indicador     VARCHAR(80)   NOT NULL,
    recorte       VARCHAR(40)   NOT NULL,
    valor_antes   NUMERIC(18,2),
    valor_depois  NUMERIC(18,2),
    diferenca     NUMERIC(18,2),
    variacao_pct  NUMERIC(9,4),
    calculado_em  TIMESTAMP     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (indicador, recorte)
);
