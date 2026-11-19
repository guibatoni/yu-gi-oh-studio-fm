# Quests PS1 QOV7 — o overlay não sobrescreve mais o código do Drop x15

**Estado: candidato. Precisa de teste no ePSXe antes de ir para a `main` e
para o atualizador.**

## Causa raiz (confirmada com save states do ePSXe)

O Drop x15 mantém código próprio em `0x801AAC40..0x801AAEE0` e usa
`0x801AAC00..0x801AAC3F` como área para salvar registradores. Quatro desvios do
executável do mod apontam para lá:

| Origem | Rotina (decomp) | Destino |
|---|---|---|
| `0x80021834` | `Duel_SelectCardDrop` | `0x801AAE54` |
| `0x80021C6C` | `DuelScene_UpdateResultRewards` | `0x801AAC40` |
| `0x80021F10` | `DuelScene_UpdateResultRewards` | `0x801AAD4C` |
| `0x80037DFC` | `func_80037DA4` (nome de carta em texto) | `0x801AAE74` |

O patch das quests (até QOV5/QOV6) amplia a carga do script de campanha para
`0x801A8000..0x801AC000` e coloca ali o código, o estado (BSS) e a tabela das
quests, apagando o código do mod. Depois da doação, a tela do baú/deck escreve
um nome de carta, salta para `0x801AAE74` e executa a tabela de quests:
`unknown opcode` em `801AAE78`/`801AAE80` nas versões 1.9.13–1.9.15. O fim do
duelo também chamaria o sorteio de drops apagado.

Evidências e ferramentas: `docs/DIAGNOSTICO_QUEST_RA.md` e o pegador de
diagnóstico na branch `claude/diagnostico-quest-ra`.

## Correção

Mapa da arena `0x801A9000..0x801AC000` (QOV7):

| Faixa | Conteúdo |
|---|---|
| `0x801A9000..0x801A9010` | cabeçalho (`QOV7`, endereço dos níveis) |
| `0x801A9010..QuestConfiguration` | código, rodata e data das quests |
| `QuestConfiguration..+0x384` | cabeçalho fixo da tabela (offsets, glifos, raridades) |
| depois do cabeçalho até `0x801AAC00` | registros de quests (1ª janela) |
| `0x801AAC00..0x801AAC40` | área de salvamento do Drop x15 (zeros) |
| `0x801AAC40..0x801AAEE0` | **código do Drop x15, copiado do SLUS** |
| `0x801AAEE0..BSS_END` | estado das quests (`active`, `inventory`) |
| `BSS_END..0x801ABFFC` | registros de quests (2ª janela) |
| `0x801ABFFC` | `QOV7` |

- `tools/ps1/campaign_quests.ld`: o BSS vai para uma seção `NOLOAD` em
  `0x801AAEE0`. `ASSERT`s impedem que código ou tabela cheguem ao mod.
- `fmstudio/ps1_campaign_quests.py`:
  - `resident_mod_code()` lê `0x801AAC40..0x801AAEE0` do SLUS e confere o SHA-256
    `4049fea0…600e`, igual ao medido na RAM do Drop x15 sem quests. Se divergir,
    a exportação é recusada.
  - `foreign_arena_jumps()` varre o executável. Se algum `j/jal` de fora apontar
    para a arena, e não for para o código do Drop x15 nem para as entradas das
    quests, a exportação é recusada com o endereço do conflito.
  - O payload recebe os bytes do mod na posição original.
  - `inspect_quest_overlay()` exige esses bytes intactos na releitura do disco.
- `fmstudio/campaign_quests.py`: `compile_table()`/`table_size()` aceitam uma
  lacuna. Nenhum registro atravessa o código do mod.
- Marcador `QOV5` → `QOV7` (carregadores residentes e overlay). BINs antigos
  são rejeitados.
- O código C das quests e o fluxo de doação **não mudaram**.

## Limite novo

Cabem até 3 requisitos para cada um dos 37 duelistas. Configurações com mais
requisitos são recusadas com a mensagem "As quests não cabem na área livre da
cena do PS1", em vez de gerar um jogo que trava.

## Testes

- `tests/test_campaign_quests.py`: código do mod preservado byte a byte, área de
  salvamento e BSS zerados, tabela dividida nas duas janelas, recusa por SHA
  divergente, detecção de desvio estranho, desvios reais do Drop x15 aceitos,
  limite de requisitos.
- Os testes MIPS/Unicorn existentes rodam no CI com o blob recompilado pelo Zig 0.13
  (`.github/workflows/studio-qov7-preserva-drop15.yml`).

## Teste no ePSXe (pendente)

1. Backup do `.mcr`. Feche outros Studios e o ePSXe.
2. Abra `FM-Studio-QOV7-TESTE.exe` e gere um BIN/CUE novo a partir do Original
   Drop x15.
3. Boot limpo, Memory Card, **Doar e duelar**: o baú/deck deve abrir.
4. Termine o duelo (vitória e derrota) e confira os drops.
5. "Ir ao Card Shop", Simon Muran sem quest, salvar e recarregar.

## Correção adicional: contagem do baú

Os save states do baú no Drop x15 mostram que `gLibrary_abCardChest`
(`0x801D0250`) **não inclui** as cartas do deck: 25 das 31 cartas do deck têm
quantidade 0 no baú. A tela Build Deck (`func_800323F8`) mostra as duas
quantidades separadas. `QuestCountMissing` subtraía as cópias do deck da
contagem do baú, como se ela as incluísse, e por isso exigia cópias a mais.
Agora usa só o baú. O deck continua intocado, porque a doação só debita do baú.

## Pendente: retirada não observada no ePSXe

Teste do usuário com QOV7 (19/11/2026): sem travamento. A quest mostrava
"Jinzo 1/1" e "Doar e duelar" levou ao baú e ao duelo, mas as cartas não
pareceram sair do baú. Aguardando save states (página da quest antes da
escolha / baú depois) para comparar `0x801D0250`, a flag `0x750 + id` e o
estado `active`/`inventory` em `0x801AAEE0..0x801AB650`.
