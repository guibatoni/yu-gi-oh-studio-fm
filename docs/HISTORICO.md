## v0.6.2 — GitHub oficial
- Atualizador agora consulta guibatoni/yu-gi-oh-studio-fm.
- Publicador clona o repositório existente e envia apenas arquivos de código, evitando histórico divergente.
- Preparação para Release v0.6.2 e atualização de dependências GitHub Actions.

## v0.6.2 — Correção do botão Atualizar

- Atualizador independente também no modo Python, via `.bat`/`.pyw`.
- Pacotes Source e Windows com SHA256 no GitHub Actions.
- Informa quando o repositório ou Release não existem.
- Preserva `projetos/`, backups, edições, cores e fusões.
- Verifica atualizações em thread secundária, sem travar a interface.

# Histórico de desenvolvimento

## v0.3.0 — Primeiro editor gráfico Windows

- Interface escura em português com biblioteca, filtro e detalhes da carta.
- Importação de `analysis/tabelas` ou diretamente de BIN/CUE/ISO suportados.
- Editor de ATK/DEF, tipo, atributo, nível, estrelas guardiãs, nome e descrição.
- Cadastro de efeitos por gatilho, alvo e ação; simulação local de ATK/DEF e LP.
- Preservação da tabela de fusões em modo somente leitura com hash.
- Exportação JSON e SLUS auxiliar com edição binária de estatísticas verificada.
- Backups rotativos de projeto e validação de integridade.
- Script de início Windows, script PyInstaller e workflow opcional de build.
- Sem imagem de jogo, ROM ou outros dados do jogo no pacote.

**Limites:** não exporta BIN/CUE jogável; efeitos e textos ainda não são gravados no jogo; imagem real X15 ainda não foi executada nesse editor nesta sessão.
- Importação de artes PNG de referência por carta, com prévia no painel do editor; ainda não são gravadas no jogo.

## v0.4.0 — GitHub Releases e atualização no aplicativo

- Novo nome de vitrine: **Yu-Gi-Oh Studio Card FM**.
- Botão `⟳ Atualizar` na barra superior, consultando GitHub Releases em background.
- Atualizador externo Windows com progresso visual, SHA-256 e validação de arquivos ZIP.
- Atualização na mesma pasta, com rollback ao falhar na substituição e preservação dos projetos pessoais.
- GitHub Actions: testes, compilação do editor e auxiliar, publicação de ZIP e checksum por tag.
- `PUBLICAR_GITHUB.bat` / `.ps1` para criar e publicar o repositório usando GitHub CLI.
- Fusões originais continuam protegidas; efeitos ainda são protótipos no simulador.

## v0.5.0 — Extração avançada de conteúdo do disco

- Botão **Extrair máximo** e aba **Dados extraídos** com progresso em segundo plano.
- Recuperação de nomes, descrições, menus e diálogos dos bancos de texto originais.
- Recuperação das artes de cartas, miniaturas, faixas, retratos e prévias de cenas.
- Cruzamento de todos os CSVs existentes com os nomes encontrados para leitura amigável.
- Preservação das edições do usuário em `projeto.json`, backup de `cartas.csv` e verificação da base.
- Índices de proveniência, hashes e avisos da extração; 22 testes de unidade aprovados em dados sintéticos.
- Fusões e rituais originais permanecem somente leitura. Sem execução de efeitos novos no jogo.

## v0.6.0 — Cores personalizadas e salvamento em lote

- Seletor RGB para nome de cartas, com botão para retornar à cor padrão. A cor aparece na prévia e na biblioteca (metadado local, não no PS1).
- Alternância entre cartas sem diálogo de salvar/descartar. Rascunhos conservados na memória inclusive ao navegar por outras cartas.
- Novo botão **Salvar projeto** com `Ctrl+S` e persistência de todas as cartas/efeitos pendentes em um único arquivo e backup.
- Indicador de cartas pendentes; rejeição de valores inválidos preserva rascunhos.
- Compatibilidade com projetos antigos e fusões originais preservadas.
- 28 testes unitários e verificação gráfica sob tela virtual com dados sintéticos.
