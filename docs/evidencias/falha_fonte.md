# Evidências de Falha na Fonte

Registro das falhas de fontes externas (CCEE e Open-Meteo) e de como o pipeline reagiu.
Cada ocorrência também fica em `raw.log_extracao` com `status = 'ERRO'`.

---

## 1. Incidente real: HTTP 403 na CCEE

- **Fonte:** CCEE · Dados Abertos (API CKAN).
- **Sintoma:** `HTTP 403 Forbidden` com cliente HTTP padrão.
- **Causa provável:** bloqueio do portal a clientes sem assinatura TLS de navegador (WAF).
- **Tratamento:** erro capturado e gravado em `raw.log_extracao`; dados já carregados em `raw` e `staging` mantidos intactos.
- **Solução:** emulação TLS de navegador com `curl_cffi`.

Consulta para recuperar a ocorrência na auditoria:

```sql
SELECT * FROM raw.log_extracao WHERE status = 'ERRO' ORDER BY 1 DESC;
```

---

## 2. Simulação de indisponibilidade

Teste de queda de rede/DNS sem alterar os dados do banco:

```bash
python -m src.extracao.ccee --simular-falha
```

| Campo | Valor |
| :--- | :--- |
| **Data da simulação** | `<AAAA-MM-DD>` |
| **Status gravado** | `ERRO` |
| **Mensagem registrada em `raw.log_extracao`** | `<mensagem real do log>` |
| **Dados em `raw`/`staging`** | Inalterados (`<n>` linhas antes e `<n>` depois) |

---

## 3. Uso de CSV de reserva

Quando a fonte permanece indisponível, o CSV de reserva é usado e a ocorrência é registrada aqui.

| Data | Fonte | Erro | Arquivo de reserva | Linhas carregadas |
| :--- | :--- | :--- | :--- | :---: |
| `<AAAA-MM-DD HH:MM>` | `<CCEE ou Open-Meteo>` | `<erro real ou "falha simulada">` | `<caminho/arquivo.csv>` | `<n>` |