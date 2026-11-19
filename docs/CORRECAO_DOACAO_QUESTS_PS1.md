# Auditoria de travamento das quests durante "Doar e duelar" (PS1)

## Evidência

Em ePSXe, o diálogo finaliza ao confirmar a doação e o jogo para com:

```
unknown opcode 74410036 at 801AAE80
```

O endereço `0x801AAE80` cai na arena de script carregada pelo
`WA_MRG.MRG`, 0x580 bytes após a configuração das quests da versão
1.9.13 (`QuestConfiguration=0x801AA900`). Essa região é **dados**
(requisitos, rótulos e pesos), não o corpo executável do MIPS.
O erro é consistente com execução de dados após um salto/retorno
incorreto. Sem trace de instruções real e o BIN que falhou, não é
possível afirmar qual instrução produziu o salto; a investigação do
código encontrou um percurso de controle incompatível com o ciclo
de vida da cena.

## Origem auditada

`tools/ps1/campaign_quests.c::QuestAnswer` consumia as cartas e
chamava `GAME_DUEL(channel)` diretamente dentro do handler de
resposta `F8 12`. O comando de duelo pode trocar os dados da arena
`0x801A9000..0x801AC000` **antes de o handler retornar**.
Assim, a continuação de `QuestAnswer` ou do despachante pode
executar bytes substituídos. Os testes anteriores usavam um stub
`jr ra` para o nativo, que não reproduzia a troca de cena.

## Fluxo corrigido

1. Verificar ponteiro do canal, modo de campanha e se a resposta é
   uma ação esperada da janela atual (REVIEW, DONATE ou RETREAT).
2. Antes de doar, refazer `QuestCountMissing`. Inventário
   temporário = baú de 722 IDs menos as 40 posições do deck.
   Os requisitos sobrepostos são resolvidos por caminhos
   aumentantes: a mesma cópia não atende a dois requisitos.
3. Caso falte alguma carta, redesenhar a quest e não alterar
   nem baú nem flags.
4. Com todas as cópias disponíveis, `take_claimed_cards` desconta
   exclusivamente as cópias livres do baú. O deck permanece igual.
5. Marcar `QUEST_FLAG_BASE + opponent` como concluída e limpar o
   marcador temporário de retorno da loja, sem salvar .mcr diretamente.
6. Desativar o callback ativo, limpar o botão de confirmação,
   reinicializar o estado da escolha, voltar o cursor a
   `resume - 2` (o opcode nativo `F8 0D`) e dar
   `TEXT_YIELD=1` para encerrar a execução do callback no frame atual.
7. No próximo tick do interpretador nativo, `F8 0D` chama
   `QuestBeforeDuel`. A flag concluída faz o hook seguir o
   handler original, carregando o duelo fora do stack da doação.

Não há recompensa extra de quest neste código: a recompensa
por vitória é do motor original e ocorre após o duelo. Também
não há gravador próprio de Memory Card: a persistência de
baú/flags continua utilizando os salvamentos normais do jogo.

O marcador do overlay foi elevado de `QOV3` para `QOV4`.
O carregador residente exige a versão atual para não entrar no código
antigo que possa permanecer em um save state ou no cache da cena.
Esta verificação NÃO torna save states de versões antigas compatíveis:
é obrigatório iniciar o jogo por boot limpo e carregar somente o
Memory Card previamente copiado.

## Alterações versionadas

- `tools/ps1/campaign_quests.c`: remove entrada direta em GAME_DUEL
  pelo callback, substitui por retomada adiada do comando nativo.
- `fmstudio/ps1_campaign_quest_overlay_blob.py`: overlay MIPS
  recompilado com Zig 0.13. **É o arquivo utilizado no BIN/CUE**.
- `tests/test_campaign_quests.py`: MIPS/Unicorn verifica
  a ordem de eventos, a ausência de entrada síncrona no duelo,
  o cursor `F8 0D`, yield, inventário/deck/flags e repetição
  sem consumir uma segunda vez.
- `.github/workflows/studio-quest-donation-fix.yml`:
  recompila o C em MIPS1, executa testes e bloqueia o PR caso
  o blob versionado não corresponda aos bytes reprodutíveis.

## Verificação manual obrigatória no ePSXe

Faça backup do Memory Card e mantenha a ISO original intocada.
A partir da imagem **Original Drop x15 vinculada ao projeto**,
gere um **novo** BIN/CUE. NÃO use a imagem de quests defeituosa
v1.9.13 como entrada do construtor.

- Sem cartas suficientes: botão Rever requisitos, sem desconto
  nem conclusão da quest.
- Cartas suficientes e duplicadas do mesmo ID: consumir
  exatamente as cópias livres, preservando todas as cartas do deck.
- Categorias sobrepostas: a mesma cópia não pode ser contada
  em dois requisitos distintos.
- Cancelar, retornar ao Card Shop e reabrir: manter os
  requisitos e o estado temporário sem perda de cartas.
- Doar e duelar: sem tela preta, sem "unknown opcode", sem duplo
  desconto; as 40 cartas do deck permanecem iguais.
- Vitória ou derrota: o status da quest deve seguir a regra
  de conclusão antes do duelo, sem iniciar outra doação.
- Salvar no jogo, fechar e reabrir com Memory Card (sem save state
  antigo): testar flags e quantidade de cartas. Não tratar a
  RAM do ePSXe como salvamento automático.
- Retornar ao Card Shop e continuar a campanha, inclusive o
  caminho em que Simon Muran não exige quest.

Ainda não foi executado um BIN real no ePSXe pelo CI. Os testes
Zig/Unicorn validam instruções e estados no cenário emulado,
não substituem a execução do jogo com cenas completas.
