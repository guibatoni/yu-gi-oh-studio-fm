# Atualizações no Studio FM

Repositório: https://github.com/guibatoni/yu-gi-oh-studio-fm

- Cada commit em `main` inicia o GitHub Actions, que executa testes, gera `FM-Mod-Studio-Windows.zip` e `FM-Mod-Studio-Source.zip` e publica GitHub Release com hashes SHA-256.
- O botão Atualizar consulta o último Release, oferece as notas, abre um instalador externo, encerra e reinicia o editor.
- Dados de projetos, MODs, ROMs, backups e arquivos personalizados não fazem parte do pacote nem são apagados.
- Falhas: `%LOCALAPPDATA%\FM-Mod-Studio\logs\atualizador.log`.
- Instalações Python antigas (<0.9.0) podem rejeitar arquivos novos. Para migrar sem baixar ZIP manualmente, feche o Studio e execute uma vez `tools/ATUALIZAR_SEM_ZIP.ps1` do GitHub.
- Para versões posteriores, basta mudar `__version__` no código e publicar main, depois clicar Atualizar.
