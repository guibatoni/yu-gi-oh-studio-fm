# Diagnóstico do crash "Doar e duelar" — pegador de endereço de retorno

**Estado:** ferramenta de diagnóstico. Não é correção e não deve ir para o
atualizador nem para a `main` como comportamento padrão.

## Evidência

| Versão | Erro no ePSXe | Início de `QuestConfiguration` |
|---|---|---|
| 1.9.13 (QOV3) | `74410036 at 801AAE80` | `0x801AA900` |
| 1.9.14 (QOV4) | `63697473 at 801AAE78` | `0x801AA950` |
| 1.9.15 (QOV5) | `Opcode 1b UNK (PC 001aae78)` (`69727441`) | `0x801AA950` |

Vídeo de 19/11/2026: "Ir ao Card Shop" volta ao Town Plaza normalmente;
"Doar e duelar" leva a uma tela preta e ao erro, **antes** de o baú/deck
nativo aparecer.

Três desenhos diferentes da transição (QOV3 chamava o duelo dentro do
callback; QOV4 reexecutava `F8 0D` no tick seguinte, a partir do adaptador
residente; QOV5 chamava o handler nativo a partir do adaptador residente)
pararam no **mesmo PC físico**, embora a tabela tenha mudado de lugar entre
QOV3 e QOV4. Os bytes executados são texto ASCII dos rótulos ("Arti", "stic").
Conclusão provável: algum código **nativo** salta para um endereço fixo perto
de `0x801AAE70`, que no jogo original não contém os dados das quests. O
caminho da doação não é a origem, e por isso as três correções não resolveram.
Isso ainda precisa ser confirmado com o endereço de retorno.

## Como o pegador funciona

Com `FMSTUDIO_DIAGNOSTICO_QUEST_RA=1`, a tabela de quests ganha um espaço
antes dos registros:

- `QuestConfiguration + 0x384 .. +0x5B0` (≈ `0x801AACD4..0x801AAF00`): zeros,
  que no MIPS são `nop`. O salto que hoje cai em `0x801AAE7x` desliza até o pegador.
- `+0x5B0` (`0x801AAF00`): 9 instruções que pegam o endereço físico de `$ra`,
  gravam ali o opcode inválido `0x6C000000` pelo alias KSEG1 (`0xA0xxxxxx`,
  fora do cache do dynarec) e saltam para ele.
- Os registros das quests começam em `+0x5E0`. O código C das quests não muda.

Resultado esperado no ePSXe: a mesma janela de erro, mas com
`Opcode 1b UNK (PC <endereço de retorno>)`. Esse PC é o `$ra` do salto,
ou seja, a instrução seguinte ao `jal/jalr` que levou ao crash.

## Como usar

1. Faça backup do `.mcr`.
2. Abra o Studio com `DIAGNOSTICO_QUEST_RA.bat` (pacote de teste do CI).
3. Gere um BIN/CUE novo a partir do Original Drop x15, como de costume.
4. Boot limpo no ePSXe, carregue pelo Memory Card, escolha **Doar e duelar**.
5. Anote o PC da janela de erro.

Leitura do resultado:

- **PC diferente de `001aae78`/`001aae80`**: é o retorno do chamador. Envie
  o número; ele aponta a rotina nativa responsável.
- **Mesmo `001aae78`**: o pegador não foi alcançado; o salto entra depois do
  início do espaço, ou o ePSXe ignorou o código novo. Ainda assim, isso descarta
  a hipótese de deslizamento e define o próximo teste.
- **PC dentro de `0x1AA...`/`0x1A9...`**: `$ra` aponta para dentro do overlay
  (retorno para código descartado), o que reabre a hipótese do callback.
- **Sem erro, jogo segue ou trava**: registre o comportamento; a mudança de
  layout pode ter alterado o salto.

## Testes

`tests/test_quest_crash_diagnostic.py`: layout padrão inalterado sem a variável;
espaço de `nop` cobrindo todos os PCs observados; codificação das instruções;
pior caso (37 duelistas × 4 requisitos) dentro dos 6 setores; espaço adulterado
rejeitado por `table_size`.

Não executado em ePSXe por este ambiente.
