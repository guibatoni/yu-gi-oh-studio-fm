# Exemplos de efeitos no Studio FM

## 1. Aura: concede +500 ATK / +300 DEF a todos os aliados do tipo Fada

- Quando ativa: `continuo` · Ação: `aura_tipo` · Alvo: `aliados_tipo`
- Valor ATK: `500` · Valor DEF: `300` · Tipo: `08 (Fairy/Fada)` · Escopo: `aliados`
- Fonte precisa estar virada para cima; ao sair do campo o bônus desaparece.

## 2. Aura para qualquer monstro que você controla

- Quando ativa: `continuo` · Ação: `aura_tipo` · Alvo: `aliados_tipo`
- Valor ATK: `100` · Valor DEF: `100` · Tipo: `-1 Todos` · Escopo: `aliados`

## 3. Recebe +200 ATK por Fada no campo (inclusive outra carta da mesma família)

- Quando ativa: `continuo` · Ação: `bonus_por_tipo` · Alvo: `proprio`
- Valor ATK: `200` · Valor DEF: `0` · Tipo: `08 (Fairy/Fada)` · Escopo: `aliados`

## 4. Recebe +100 ATK e +50 DEF por Fada no seu deck

- Quando ativa: `continuo` · Ação: `bonus_deck_tipo` · Alvo: `proprio`
- Valor ATK: `100` · Valor DEF: `50` · Tipo: `08 (Fairy/Fada)` · Escopo: `aliados`
- O cálculo conta o deck completo de 40 cartas, incluindo as cartas compradas.

## 5. Ao invocar, recuperar 150 LP por Fada no deck

- Quando ativa: `invocar` · Ação: `cura_lp_deck_tipo` · Alvo: `proprio`
- Valor: `150` · Tipo: `08 (Fairy/Fada)`
- Para ativar: aba **Deck, mão e gatilhos** → selecionar origem → **Aplicar gatilho uma vez**.

## 6. Ao invocar, causar 100 de dano aos LP por Dragão no deck

- Quando ativa: `invocar` · Ação: `dano_lp_deck_tipo` · Alvo: `inimigo`
- Valor: `100` · Tipo: `00 (Dragon/Dragão)`

## 7. Ao invocar, descartar 2 cartas do adversário

- Quando ativa: `invocar` · Ação: `descartar_alvo` · Alvo: `inimigo` · Valor: `2`
- Cadastre mão do adversário (até 5 cartas). Quando vazia, nenhum descarte adicional.

## 8. Ao invocar, causar 300 de dano a um monstro alvo

- Quando ativa: `invocar` · Ação: `dano_monstro_alvo` · Alvo: `monstro_alvo` · Valor: `300`
- Na aba de duelo, selecione alvo antes de executar.
- Aviso: a "resistência" do laboratório (HP=DEF-base, mínimo 1) é experimental.

## 9. Equipamentos que funcionam como encantamentos

Para a carta de equipamento, configure `evento=equipado`, `alvo=monstro_equipado` e uma das ações:

- `equip_imune_armadilha`: Valor = `0`.
- `equip_imune_magia_armadilha`: Valor = `0`.
- `equip_indestrutivel`: Valor = `0`.
- `equip_atk`: Valor = `500` (ou outro X).

Na aba Campo, anexe essa carta ao slot do monstro. No PS1, aplique uma
carta de Equipamento compatível ao monstro durante o duelo. A proteção
acompanha o monstro equipado até ele sair do campo.

## Importante

No perfil Drop x15, a opção **Gerar jogo BIN/CUE** grava os exemplos
1 a 4 e o 9 na cópia do jogo. Os gatilhos dos exemplos 5 a 8 são
executados pelo laboratório do Studio.
