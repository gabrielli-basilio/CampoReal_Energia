# Painel

Salve aqui a pasta de trabalho do Tableau como `campo_real.twbx` (empacotada, com o extract). O passo a passo, o modelo de
relações e os campos calculados estão em `docs/painel_tableau.md`. O painel lê somente o schema `dw_campo_real`.

Use extract, não conexão ao vivo: assim a senha e o host do Neon não vão dentro do arquivo. Antes de subir no
repositório, confira em Fonte de Dados que não há credenciais salvas.
