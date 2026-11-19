# Auditoria e reformulação da interface (1.10)

## Situação encontrada (1.9.20)

- **Framework:** Tkinter + ttk (tema `clam`), sem dependências externas na interface.
  O Pillow é opcional e só serve para imagens. A troca de framework foi descartada:
  são cerca de 7.600 linhas de GUI e 16 testes de interface que dependem do Tkinter.
- **Janela principal (`gui.py`, `Studio`):** cabeçalho com logo e botão Atualizar; barra
  com menus Projeto/Importar e os botões Salvar, Exportar e Gerar BIN; biblioteca de
  cartas fixa à esquerda (busca, tipo, Guardian Star, faixa de IDs); `ttk.Notebook` com
  6 abas: Cartas, Efeitos, Fusões originais, Edição do Mod, Exportação e Dados extraídos.
- **Edição do Mod (`mod_gui.py`):** um segundo notebook dentro da aba, com 7 sub-abas:
  Deck oponente, Drops, Decks iniciais, Config. MOD, Quests, Mágicas/Traps e Molduras.
  O seletor de duelista ficava visível em todas, inclusive onde não tem efeito
  (Molduras, Mágicas, Config.).
- **Janelas secundárias:** EffectDialog, SpecificCardEffectDialog, FieldDialog,
  CardRelationsDialog, NewCardDialog, PasswordsDialog, DeckGeneratorDialog,
  BulkEditDialog (baú/preço), QuestRequirementsDialog, MatchDialog e AdvancedFieldDialog.

### Problemas

1. **Navegação em dois níveis de abas.** Para ir de Cartas até Molduras eram dois cliques
   (Edição do Mod e depois Molduras), e as abas não cabiam na janela, o que já tinha exigido
   encurtar os nomes na 1.9.20. Não havia busca de telas nem histórico.
2. **Biblioteca sempre visível**, ocupando cerca de 330 px até em telas que não usam cartas
   (Quests, Config., Exportação, Dados extraídos).
3. **Sem barra de status de verdade:** só uma linha de texto. Não mostrava o projeto, o
   BIN/SLUS, o estado salvo/pendente nem a operação em andamento.
4. **Geração do BIN/CUE congelava a janela.** Rodava na thread da interface, e o Windows
   chegava a marcar o programa como "Não respondendo".
5. **Nada era lembrado entre sessões:** tamanho da janela, largura da biblioteca, última
   tela e projetos recentes.
6. **Atalhos limitados** (Ctrl+F/S/O). Também não havia edição em lote de atributos de
   cartas; a edição em lote existente só cobria baú e preço de password.
7. **Estilos espalhados:** paleta e estilos ttk definidos dentro do `gui.py`.

## O que mudou

| Antes | Depois |
|---|---|
| 6 abas + 7 sub-abas | Barra lateral com 13 telas em 4 grupos (Cartas, Oponentes, Mod PS1, Disco) e a tela Início |
| 2 cliques até Molduras/Quests | 1 clique, ou Ctrl+K e algumas letras |
| Sem histórico | Voltar/avançar (botões ◀ ▶, Alt+←/→) |
| Biblioteca fixa | Biblioteca só nas telas que usam cartas; Ctrl+L mostra/oculta; largura lembrada |
| Linha de status | Barra de status: projeto, base/SLUS, ● pendentes / ✓ salvo, operação com barra de progresso |
| Gerar BIN congelava | Geração em segundo plano; a janela continua redesenhando, com progresso indeterminado (o gerador não informa porcentagem, então nenhuma porcentagem é inventada) |
| Nada persistia | Janela, maximizado, menu recolhido, largura da biblioteca, última tela e 8 projetos recentes |
| — | Tela Início: resumo do projeto, ações rápidas, projetos recentes, fluxo de trabalho e atalhos |
| — | Edição em lote de cartas (ATK/DEF por definir/somar/subtrair/%, tipo, atributo, nível, raridade, Guardian Stars) com prévia; vai para as pendências e só grava ao salvar |

As preferências ficam em `%APPDATA%\FM Studio\interface.json`, fora do projeto. O formato
do projeto (`projeto.json`, CSVs, metadados) **não mudou**.

### Compatibilidade preservada

- Os dois notebooks continuam existindo, só com as abas ocultas (estilo `Hidden.TNotebook`).
  Por isso todo código e todo teste que chama `tabs.select(...)` continua funcionando, e a
  barra lateral acompanha essas trocas pelo evento `<<NotebookTabChanged>>`.
- Os nomes de widgets usados pelo resto do código (`tree`, `save_button`, `build_button`,
  `export_button`, `status`, `proj_title`, `mod_editor` etc.) foram mantidos.
- Nenhuma regra de jogo, de geração de deck, de drop ou de quest foi tocada.

## Atalhos

| Atalho | Ação |
|---|---|
| Ctrl+K | Buscar tela ou ação |
| Ctrl+S / Ctrl+O / Ctrl+N | Salvar / abrir / novo projeto |
| Ctrl+B | Gerar BIN/CUE |
| Ctrl+F | Buscar carta |
| Ctrl+1…6 | Cartas, Efeitos, Deck, Drops, Iniciais, Quests |
| Alt+← / Alt+→ | Voltar / avançar |
| Ctrl+L | Mostrar/ocultar biblioteca |
| Ctrl+\ | Recolher/expandir o menu |
| F1 | Início |
| Biblioteca: Ctrl+A, Ctrl+C, Ctrl+E, Enter | Selecionar visíveis, copiar linhas, edição em lote, abrir no editor |
| Lista de efeitos: Delete, Ctrl+C, Ctrl+V | Excluir (com confirmação), copiar, colar |

## Pendências conhecidas e próximas fases

- **DPI:** o Studio continua sem o modo "DPI aware". O Windows amplia a janela inteira, o
  que deixa o texto levemente desfocado em 125–150 %, mas sem cortar controles. Ativar o
  modo nítido exige revisar os tamanhos fixos em pixels (prévia da carta, colunas e
  janelas secundárias); isso ficou para uma fase própria.
- **Desfazer/refazer global:** não implementado. Ctrl+Z funciona nos campos de texto
  (nativo do Tk), e "Restaurar os valores originais" desfaz a carta inteira.
- **Biblioteca em grade com miniaturas e inspetor à direita:** não implementados nesta fase.
- **Probabilidade de drop calculada** e **resumo da composição do deck** nas tabelas de
  peso: próxima fase (Editores).
- A tela de Exportação ainda usa o painel de texto antigo.
