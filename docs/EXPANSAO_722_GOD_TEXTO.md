> Registro histórico da v1.0.0. Para o estado atual, consulte
> [Expansão PS1 #723–#740](EXPANSAO_PS1_740.md) e [Compatibilidade](COMPAT_PS1.md).

# Studio FM v1.0.0 — Expansão, God e texto com ícones

## Estado real do PS1

O jogo original possui 722 cartas. O Studio permite **criar cartões virtuais #723–#32766 dentro do projeto** para planejamento e simulação; isso **não aumenta a contagem do BIN original**. O limite de 32766 foi escolhido por ser documentado para a versão PC recompilada, NÃO para o ePSXe/PS1. Uma versão jogável PS1 exige alterações nas rotinas de indexação, acesso à memória, dados, salvamentos, deck, fusões, drops e recursos de GPU.

O tipo **God**, ID 24, está disponível no editor e simulador. Não modificamos o `SLUS` de cartas God porque o retail não comprova suporte ao novo tipo. Criar ou editar cartas continua sem sobrescrever o BIN; as fusões continuam somente leitura e são verificadas por hash.

## Criar cartas

Selecione uma carta base e clique **+ Criar nova carta (ID acima de 722)**. O Studio usa a carta selecionada como referência de atributos e registra `modelo_base_id`, mas cria uma identidade nova com nome e descrição próprios. A primeira recebe #723, a seguinte #724 etc. Após criar, as mudanças nos campos seguem o fluxo de **Salvar projeto / Ctrl+S**. A criação da identidade é gravada imediatamente no `projeto.json` com backup; o restante é rascunho.

O exportador gera `novas_cartas.json` e `textos_e_codigos.json`. Nenhum registro acima de #722 é escrito no SLUS auxiliar.

## Ícones originais do jogo

A pesquisa `notes/more-cards.md` do projeto Yu-Gi-Oh-Forbidden-Memories-Recompiled documenta os códigos usados em textos: `{f8 0B XX}` são **ícones nativos 16×16 px**, tipo `{f8 0B 08}` (Fairy); `{f8 0A XX}` muda a cor do texto, sendo `00` branco, `01` amarelo, `02` azul, `03` verde, `04` cinza, `05` laranja e `06` vermelho. Os ícones nativos incluem tipos de monstros, Magic, Trap, Ritual, Equip, estrelas guardiãs e símbolos de botões.

Origem pesquisada: https://github.com/Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled/blob/master/notes/more-cards.md

## Ícones adicionais criados para o Studio

`assets/icons` contém PNGs 16×16 com paleta limitada e transparência. Códigos internos: `{icon:perfurar}`, `{icon:ataque_2x}`, `{icon:ataque_3x}`, `{icon:nao_bloqueavel}`, `{icon:infinito}`, `{icon:anti_trap}`, `{icon:anti_magia}`, `{icon:indestrutivel}`, `{icon:god}`.

Eles aparecem na prévia do Studio, **não** no jogo PS1. Inserção real exigiria reservar células de sprites no banco da fonte/VRAM, apontar novos códigos, atualizar empacotamento e evitar conflito com ícones já usados. O pacote de imagens é um conjunto de recursos para essa futura etapa; não deve ser colado cegamente no BIN.

## Texto colorido

Use **Cor no trecho** e selecione texto para gerar `{color:vermelho}...{/color}`; a prévia mostra a cor. A exportação converte cores conhecidas para o código nativo `{f8 0A XX}` em `textos_e_codigos.json`, mas **ainda não recompõe o banco de textos PS1**. A descrição pode usar também o código nativo diretamente.

## Bônus por uma carta específica

Na aba Efeitos, clique **+ Bônus por carta**, escolha um nome na lista e defina quantidade de ATK/DEF por cópia. Conte por cartas face-up em campo ou por cópias da lista do deck, com escopo aliados, inimigos ou ambos. Os valores são recalculados; saindo do campo, o buff diminui. A descrição gravada usa um marcador interno `{card:1}` para continuar apontando para a mesma carta mesmo se ela for renomeada; a **prévia e o texto exportado mostram o nome da carta**.

## Compatibilidade

- Mantidos projeto.json de versões anteriores, backup rotativo, fusões imutáveis, salvamento em lote, atualizador GitHub.
- Recursos novos: projeto e laboratório; **não implementados em duelos reais no ePSXe**.
- Não distribua ROMs ou arquivos originais do jogo no GitHub. O aplicativo gera somente patches ou metadados de sua autoria quando essas funções estiverem prontas.
