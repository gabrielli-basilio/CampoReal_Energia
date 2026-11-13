# Evidências de Falha na Fonte

Cada ocorrência também fica em `raw.log_extracao` com `status = 'ERRO'`.

## 1. Incidente real: HTTP 403 na CCEE
- **Sintoma:** `HTTP 403 Forbidden` com cliente HTTP padrão.
- **Tratamento:** erro gravado em `raw.log_extracao`; dados já carregados mantidos.
- **Solução:** emulação TLS de navegador com `curl_cffi`.

## 2. Simulação de indisponibilidade
- **Comando:** `python -m src.extracao.ccee --simular-falha`
- **Data:** <AAAA-MM-DD>
- **Mensagem gravada no log:** <cole de raw.log_extracao>
- **Dados em raw/staging:** inalterados (<antes> = <depois>)