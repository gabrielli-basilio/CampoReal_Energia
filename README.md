# DW Campo Real Energia

Trabalho prático de Data Warehouse desenvolvido em **Python 3.10+** e **PostgreSQL (Neon)**.

---

## 1. Fontes de Dados e Licenças

| Fonte | Dados Extraídos | Grão | Licença |
| :--- | :--- | :--- | :--- |
| **CCEE · Dados Abertos** | PLD horário, 2025-01-01 a 2026-10-31 (último mês publicado) | Submercado × Hora | CC-BY 4.0 |
| **Open-Meteo · API Histórica** | Temperatura, radiação, vento e chuva, 2025-01-01 a 2026-10-31 | Usina × Hora | CC-BY 4.0 (não comercial) |
| **Campo Real Energia** | Tabelas operacionais de origem | Variável | Base fictícia da disciplina |

> **Período coberto:** 2025-01-01 a 2026-10-31. O fim do período é controlado por
> `open_meteo.data_fim` e `ccee.anos` em `config/config.yaml`.

---

## 2. Pré-requisitos

* **Python:** Versão 3.10 ou superior.
* **Versionamento:** Git instalado na máquina.
* **Banco de Dados:** Conta no [Neon](https://neon.tech) com um banco criado chamado `campo_real`.
* **Cliente SQL:** DBeaver ou pgAdmin para executar scripts e consultar tabelas.

---

## 3. Instalação e Configuração

Execute os comandos abaixo na raiz do projeto para preparar o ambiente virtual e os arquivos locais:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
copy config\config.example.yaml config\config.yaml
```

### Variáveis e Parâmetros Locais
Os arquivos `.env` e `config/config.yaml` estão listados no `.gitignore` e não são enviados ao repositório. Preencha-os antes de rodar os scripts:

| Arquivo | O que configurar | Valores de Referência |
| :--- | :--- | :--- |
| **`.env`** | Credenciais de conexão com o banco Neon | `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` e `DB_SSLMODE=require` |
| **`config/config.yaml`** | Limites regulatórios do PLD (ANEEL) e IDs dos recursos CKAN | **2025:** piso `58.60` / teto `1542.23`<br>**2026:** piso `57.31` / teto `1611.04` |

---

## 4. Ordem de Execução

| Passo | Etapa | Comando / Ação | Resultado Esperado |
| :---: | :--- | :--- | :--- |
| **1** | **Carga de Origem** | Executar `sql/00_origem/campo_real_energia_postgres.sql` no DBeaver ou pgAdmin | 10 usinas e 78.798 medições carregadas no schema de origem |
| **2** | **Extração CCEE** | `python -m src.extracao.ccee` | Carga do PLD horário de 2025 e 2026 nas camadas `raw` e `staging` |
| **3** | **Pipeline Completo** | `python -m src.pipeline` | Executa CCEE, limpeza (quando disponível), clima e carga do DW |
| **4** | **Testes Unitários** | `python -m pytest -q` | Todos os testes de regras, paginação e falhas aprovados (`6 passed`) |
| **5** | **Verificação de Qualidade** | Executar as consultas da seção 5.1 no DBeaver ou pgAdmin | Contagens de PLD e clima conferem com o esperado para 2025-01-01 a 2026-10-31 |

---

## 5. Arquitetura e Regras de Extração

### Camadas de Dados no PostgreSQL

| Camada | Tabelas | Finalidade |
| :--- | :--- | :--- |
| **Raw** | `raw.pld_horario`, `raw.clima` | Armazena o retorno bruto da API em formato `JSON`, preservando data/hora da extração e origem. |
| **Staging** | `staging.pld_horario`, `staging.clima_horario` | Dados tipados, deduplicados e padronizados para alimentar o Data Warehouse. |
| **Auditoria** | `raw.log_extracao` | Registra início, fim, linhas lidas, linhas gravadas, status e mensagens de erro de cada execução. |

### 5.1 Verificação de Qualidade (após a extração)

Confere se a carga cobre todo o período, sem buracos por mês:

```sql
-- PLD horário: linhas por mês
SELECT date_trunc('month', data_hora) AS mes, COUNT(*) AS linhas
FROM staging.pld_horario
GROUP BY 1 ORDER BY 1;

-- Clima horário: linhas por mês
SELECT date_trunc('month', data_hora) AS mes, COUNT(*) AS linhas
FROM staging.clima_horario
GROUP BY 1 ORDER BY 1;

-- Auditoria: últimas execuções de cada extração
SELECT *
FROM raw.log_extracao
ORDER BY 1 DESC
LIMIT 10;
```

**Contagens esperadas (2025-01-01 a 2026-10-31 = 669 dias × 24 h = 16.056 horas):**

| Tabela | Esperado |
| :--- | :--- |
| `staging.pld_horario` | 16.056 por submercado (64.224 com 4 submercados) |
| `staging.clima_horario` | 16.056 por usina (144.504 com as 9 usinas válidas) |

### Controles Implementados no Pipeline

* **Paginação CKAN:** Consulta a API da CCEE usando `limit` e `offset` até atingir o total informado pelo servidor, interrompendo também em caso de página vazia.
* **Carga Incremental (Idempotência):** Antes de baixar, compara o total de registros da API com o que já está salvo em `raw`. Se o ano já estiver completo, encerra com `status = 'JA_COMPLETO'` sem refazer downloads.
* **Saneamento Cadastral Prévio:** Filtra cadastros duplicados fora do padrão (`CRE-EOL-07`) e corrige latitude com sinal invertido antes de consultar a API do Open-Meteo, garantindo a extração apenas para as 9 usinas válidas.
* **Resiliência e Tratamento de Erros:** Três tentativas com espera exponencial (*backoff*), controle de tempo limite (*timeout*), validação de resposta vazia e detecção de mudança de nomes de colunas.
* **Contorno de Bloqueio WAF e Rate Limit:** Uso de `curl_cffi` (emulação TLS de navegador) para evitar bloqueio `HTTP 403` na CCEE e pausa configurável (`pausa_entre_usinas`) entre chamadas no Open-Meteo.

---

## 6. Comportamento em Caso de Falha na Fonte

Quando uma API externa está indisponível ou bloqueando requisições, o extrator captura a exceção, registra o detalhe técnico em `raw.log_extracao` com `status = 'ERRO'` e mantém intactos os dados já gravados em `raw` e `staging`. Na execução seguinte em modo normal, o processo retoma de onde parou ou finaliza como `JA_COMPLETO`.

* **Incidente real registrado:** Durante o desenvolvimento, o portal da CCEE bloqueou clientes HTTP padrão com `HTTP 403 Forbidden`. O erro foi capturado na tabela de auditoria e solucionado com emulação de navegador via `curl_cffi`.
* **Simulação de indisponibilidade:** Para testar o tratamento de queda de rede/DNS sem afetar os dados do banco, execute:

```bash
python -m src.extracao.ccee --simular-falha
```

* **CSV de reserva:** quando a fonte permanece indisponível, o uso do arquivo de reserva é registrado em `docs/evidencias/falha_fonte.md` (data, fonte, erro, arquivo usado e linhas carregadas).
