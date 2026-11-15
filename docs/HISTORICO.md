## v1.1.0 — BIN/CUE parcial: atributos, textos curtos e artes
- Novo relatório de compatibilidade por projeto, com recursos de motor pendentes explicitados.
- Grava nomes e descrições que cabem no espaço original e usam glifos/códigos F8 nativos.
- Regrava arte 102×96 e miniatura 40×32 das cartas existentes com paleta original.
- Altera apenas setores ISO9660 conhecidos; EDC/ECC refeito, hashes e releitura verificados.
- Todos os recursos que dependem de MIPS (cartas extras, God, efeitos, novos ícones) permanecem somente no Studio.

## v1.0.2 — Raridades/classes e cores automáticas do nome
- Criaturas: Comum (cinza claro), Incomum (branco), Rara (amarelo), Épica (roxo), Lendária (vermelho), Deus (azul-marinho).
- Magic (verde), Trap (rosa), Equip (azul) e tipo God (azul-marinho) têm cor automática pela categoria.
- Seletor de raridade substitui os botões de cor livre; biblioteca e prévia apresentam a mesma classe.
- Projetos antigos mantêm `cor_nome` legado nos dados, e a nova classe `raridade` é salva com Ctrl+S.
- Para legibilidade do azul-marinho, a classe Deus tem fundo claro na lista e no nome da prévia.
- Metadados exportados em `classes_cartas.json`. Não aplica cores ao executável PS1 nem altera fusões.

## v1.0.1 — Correção do atualizador Python
- Reconhecimento de novos módulos e ícones de fonte, mantendo rejeição de arquivos ROM, traversal e pastas do usuário.
- Script de migração sem ZIP manual compatível com ícones em assets/icons.

## v1.0.0 — Cartas virtuais, God e descrições aprimoradas
- Suporte no editor a IDs a partir de 723 (até 32766 no projeto), sem repack PS1.
- Tipo God (ID 24) no Studio, salvo como metadado; não gravado no executável PS1.
- Seletor de ícones nativos de 16×16 e 9 ícones personalizados em PNG transparente, com paleta reduzida.
- Trechos coloridos em descrições, conversão das cores conhecidas aos códigos F8 em exportação auxiliar.
- Bônus dinâmico por ID de carta com nome resolvido em prévia/descrição, por campo ou deck.
- Projetos antigos, fusões e backups preservados.
- Duelos reais e expansões binárias do PS1 ainda pendentes.

## v0.7.0 — Efeitos contínuos e campo visual
- Aura para todos os aliados face-up do tipo escolhido (+ATK/+DEF).
- Bônus para fonte por quantidade de aliados face-up do tipo escolhido.
- Recalcula na saída/destruição/virada para baixo, soma auras, sem buff persistente.
- Editor de efeitos expandido e simulador visual 5x5; 43 testes unitários locais.
- Fusões originais preservadas; efeitos continuam só no Studio, não no PS1.

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

## v0.8.0 — Decks, encantamentos, alvos e auras genéricas
- Implementado motor de simulação com deck, mão, LP e HP experimental de monstro; equipamentos e efeitos passivos; sem mudanças no PS1.
- Implementado novo laboratório gráfico com campo 5x5, decks e gatilhos explícitos.
- Suporte a qualquer TIPO e escopos aliados, inimigos ou ambos.
- Publicação planejada na tag `studio-v0.8.0` do GitHub oficial; verifique o Release.

## v0.9.0
- Editor de habilidades rápidas por carta e simulação de combate 2x/3x com custo LP e proteção.
- Regra de cópias no deck (até 40 ao todo) e preservação de projetos.

## v1.0.3 — Cemitério, ataque no primeiro turno e teste BIN/CUE

- Novo efeito contínuo `bonus_cemiterio_tipo`: ATK/DEF por carta de tipo selecionado no cemitério, recalculado a cada destruição/remoção ou mudança da pilha, escopos aliados/inimigos/ambos.
- Cemitério separado para cada jogador no Laboratório; botão para aplicar IDs e destruição de monstros envia-os automaticamente à pilha.
- Habilidade rápida `ataque_primeiro_turno` com ícone de bota alada (16×16 indexado). O laboratório diferencia criaturas recém-invocadas de criaturas prontas para atacar; o PS1 ainda não interpreta essa habilidade.
- Primeira construção experimental de **BIN/CUE MODE2/2352** de teste, preservando inteiramente a imagem-base e XA/STR. Substitui somente setores do SLUS de MESMO TAMANHO, recalcula EDC/ECC e lê a cópia para verificar.
- Apenas estatísticas de cartas já existentes e compatíveis com o PS1 são gravadas. Nenhuma modificação ao motor dos efeitos, textos, ícones, God, cartas acima de 722 ou fusões é aplicada.
- Hash SHA-256 da base importada é obrigatório: o disco deve ser exatamente o da importação; nunca sobrescreve a imagem original.
- Rotina CD-ROM Mode2/Form1 baseada na descrição pública de PSX-SPX: https://psx-spx.consoledev.net/dev/ps1/cdr/cdromformat/
- Construção testada com **setores sintéticos**; a compatibilidade do BIN gerado no ePSXe ainda depende de teste com a imagem legítima do usuário.
