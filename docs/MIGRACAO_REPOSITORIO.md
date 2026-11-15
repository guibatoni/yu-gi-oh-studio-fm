# Migração para o repositório correto

O GitHub do Studio agora é `guibatoni/yu-gi-oh-studio-fm`. Versões até v0.6.1 consultam o nome incorreto `guibatoni/yu-gi-oh-studio-card-fm` e **não conseguem receber a primeira correção pelo botão**.

Faça uma atualização manual apenas uma vez: feche o Studio, preserve `projetos/` e `backups/`, extraia o pacote v0.6.2 ou execute o instalador local. Depois disso, o botão Atualizar verificará somente o novo GitHub Releases.

**Publicar**: execute `PUBLICAR_GITHUB.bat` v0.6.2, confirme a publicação do código (público) e acompanhe a execução de GitHub Actions. A tag `studio-v0.6.2` criará um Release com fontes e executável de Windows quando o workflow passar. Não inclua arquivos BIN/ISO, BIOS, saves, mods ou backups no repositório.
