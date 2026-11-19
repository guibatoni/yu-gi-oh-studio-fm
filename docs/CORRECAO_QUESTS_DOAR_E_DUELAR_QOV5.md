# Quests PS1 — correção do travamento ao abrir o baú/deck (QOV5)

## Sintoma reproduzido pelo usuário

A opção **Ir ao Card Shop** retorna ao mapa sem travamento, mas a opção
**Doar e duelar** provoca tela preta no ePSXe:

- v1.9.13: `unknown opcode 74410036 at 801AAE80`
- v1.9.14: `unknown opcode 63697473 at 801AAE78`

Ambos os endereços ficam na **tabela de dados das quests**, na região
dinâmica `0x801A9000..0x801AC000`, e não em instruções MIPS válidas.
A evidência é compatível com fluxo de controle/retorno inseguro para uma
região temporária, embora o salto exato não tenha sido observado com
um trace de execução real do ePSXe.

## Fluxo original correto

A rotina original `Text_StartCampaignDuel` (`F8 0D` em
`0x80038530`) lê seis bytes do registro de duelo: ID do oponente,
destinos pós-vitória/derrota, terreno e música. Ela configura o modo
do jogo em `3`. A função nativa `Main_RunDuel` inicia no estado
`0` e **abre a edição do deck/baú** antes do combate. Portanto a quest
não precisa abrir uma janela própria de baú nem saltar direto para
as rotinas de campo.

Referência decompilada com matching de código original:
`krystalgamer/Yu-Gi-Oh-Forbidden-Memories-Recompiled`,
`src/game/text_start_campaign_duel.c` e
`src/game/main_run_duel.c`.

## Falha do fluxo anterior

O QOV3 chamava `GAME_DUEL(channel)` diretamente no callback da quest.
O QOV4 tentava voltar dois bytes no interpretador de texto e
**reexecutar** o comando `F8 0D` em outro tick. Ambos dependiam do
gerenciamento de cursor e stack do interpretador de texto no interior
do overlay temporário de script. Os testes anteriores usavam um
`jr ra` para a rotina nativa e não validavam a abertura do modo 3,
a leitura dos seis operandos ou a invalidação da área do overlay.

## Correção QOV5

1. O jogador seleciona **Doar e duelar**; `QuestAnswer` confirma os
   requisitos por `QuestCountMissing` (cópias livres no baú menos
   as reservadas nas 40 posições do deck).
2. `take_claimed_cards` consome as cópias elegíveis sem remover
   cartas do deck. É gravada a flag de conclusão e removido o
   checkpoint temporário da loja.
3. `QuestAnswer` deixa o cursor no **primeiro operando nativo**,
   `active.resume`, sem reiniciar `F8 0D`, marca o handoff transitório
   `0x44` no bloco `PENDING` e retorna.
4. O `QuestAnswerLoader` **residente** espera a conclusão do
   callback usando `jal` e uma pilha fora do overlay. Ao retornar,
   valida modo de campanha, banco do script, offset e oponente.
5. O carregador consome o marcador antes da transição e faz
   `j 0x80038530`, preservando o endereço de retorno do próprio
   interpretador nativo. Não resta nenhum frame de C executando no
   overlay descartável.
6. O PS1 prepara o duelo normal (`MODE=3`); no próximo frame,
   `Main_RunDuel` apresenta a tela de baú/deck. Depois inicia o
   duelo normalmente.

O marcador de handoff é transitório. Não altera o arquivo de Memory
Card nem cria um novo formato de save.

## Testes automáticos

O teste Unicorn agora verifica:

- Inventário insuficiente, categorias sobrepostas e exclusão das
  cópias reservadas no deck;
- Cancelamento e retorno ao Card Shop;
- Um único débito, conclusão da flag e retorno idempotente;
- Chamada ao handler nativo com os seis operandos originais;
- Modo nativo 3 e preservação de terreno, música e destinos pós-duelo;
- Retorno do handler para código residente (não para o overlay);
- Sobrescrita integral de `0x801A9000..0x801AC000` após a
  transição: o handler deve retornar com segurança;
- Rejeição de script/cursor inválidos e de marcadores obsoletos QOV4;
- O compilador Zig 0.13 produz o mesmo blob MIPS que foi versionado
  (comparação byte a byte por GitHub Actions).

Os testes usam um stub dos estados nativos para validar parâmetros e
transição. Não executam o renderizador completo do ePSXe.

## Teste de integração necessário

1. Faça backup do `.mcr`.
2. Atualize o Studio e **gere novo BIN/CUE a partir do Original Drop
   x15 não modificado**, vinculado ao projeto. Não use o BIN de
   quests da versão que travava como base de exportação.
3. Feche completamente o ePSXe, reinicie o jogo por boot limpo e
   carregue o progresso do Memory Card (não de save state antigo).
4. Com cartas suficientes, escolha **Doar e duelar**. O resultado
   correto é abrir a **tela nativa do baú/deck**.
5. Altere ou confira as 40 cartas, entre no combate, termine o duelo
   e verifique a cena seguinte.
6. Reinicie de novo e confira as flags e quantidades após salvar
   pelo menu nativo. Reabrir a quest concluída não pode descontar
   cartas novamente.
7. Confirme a opção **Ir ao Card Shop** com quest pendente, inclusive
   em fases do torneio e no mapa egípcio.

**A ausência de erro no teste MIPS não é comprovação de funcionamento
em ePSXe.** Se ocorrer outra falha, coletar o BIN/CUE gerado ou seu
`SLUS_014.11`, relatório de exportação e trace PC/RA/SP e memória
ao redor do PC no momento do erro.
