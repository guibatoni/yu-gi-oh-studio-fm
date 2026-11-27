# Mod "Eclipse do Faraó" (PS1, Original Drop x15)

Mod completo feito só com recursos que o Studio FM já grava no BIN/CUE:
efeitos nativos, fusões #001–#722, pools dos 39 oponentes, drops POW/TEC/B-C-D,
quests de doação, pools do deck inicial, IA difícil e a tabela de destruição
por tipo das mágicas.

O mod é um **pacote por nomes** (`mods/eclipse_do_farao/mod.json`). Ele não
tem IDs fixos: o aplicador procura cada carta pelo nome no catálogo do seu
projeto e confere tipos e ATK com os dados reais do seu disco.

## Como aplicar

1. Feche o Studio.
2. Confira (não grava nada):

   ```powershell
   cd D:\caminho\yu-gi-oh-studio-fm; python tools\aplicar_mod.py "D:\caminho\do\projeto"
   ```

   O relatório lista decks, drops, quests e **avisos de nomes não encontrados**
   com sugestões parecidas. Corrija o nome no `mod.json` se aparecer algum.
3. Aplique (faz backup `backups\projeto_antes_eclipsedofarao_*.json`):

   ```powershell
   cd D:\caminho\yu-gi-oh-studio-fm; python tools\aplicar_mod.py "D:\caminho\do\projeto" --aplicar --inicial 1
   ```

   `--inicial` escolhe qual dos 6 decks iniciais vai para o PS1 (1–6 ou nome).
   `--estrito` recusa aplicar se algum nome não existir no projeto.
4. Abra o projeto no Studio → **Gerar jogo BIN/CUE** (gera a cópia `_QUESTS`).

## Regras de design

- **Efeitos** só em monstros com ATK ≥ 1901, ou ≥ 1801 se forem resultado de
  fusão. O aplicador confere isso com o ATK real de cada carta.
- **Taxa de poder:** monstros de arquétipo com ATK ≥ 2800 perdem 300 LP por
  ataque; ATK ≥ 3000, 500 LP.
- **Decks dos oponentes:** 1 ou 2 tipos. Monstros fora dos tipos são recusados.
- **Relíquias** (Time Wizard, Dark Elf, Dark Magician, Blue-eyes, Gate Guardian
  e outras) nunca entram por preenchimento automático: só onde o mod pede.
- Se as regras nativas não couberem na área do Drop x15, o aplicador corta os
  arquétipos de menor ATK primeiro (assinaturas nunca são cortadas) e avisa.

## Arquétipos (todo monstro forte do tipo)

| Tipo | Nome | Efeito |
| --- | --- | --- |
| Dragon | Fúria Dracônica | +150 ATK por Dragão aliado em campo |
| Spellcaster | Círculo Arcano | Imune a mágicas; aura +200/+200 nos Spellcasters aliados |
| Zombie | Legião dos Mortos | +200/+200 por Zombie no cemitério |
| Warrior | Grito de Guerra | Aura +200 ATK nos Warriors aliados |
| Beast-Warrior | Domador | Perfurante; +200 ATK por Beast aliada |
| Beast | Matilha | Ataca no 1º turno; +150 ATK por Beast aliada |
| Winged Beast | Rasante | Ataque direto; perde 300 LP por ataque |
| Fiend | Pacto Sombrio | Ao entrar, inimigos −300/−300; perde 200 LP por ataque |
| Fairy | Bênção | Ao entrar, cura 800 LP; imune a armadilhas |
| Insect | Enxame | +150/+150 a cada Insect aliado que entra |
| Dinosaur | Predador Primitivo | Ataca no 1º turno; perfurante; perde 200 LP por ataque |
| Reptile | Escamas Antigas | Imune a mágicas; +150/+150 por Reptile no cemitério |
| Fish | Cardume | Aura +200/+200 nos aliados de WATER |
| Sea Serpent | Maré Alta | +250 ATK por Aqua aliado; imune a armadilhas |
| Machine | Protocolo Duplo | Ataca 2x; perde 400 LP por ataque |
| Thunder | Descarga | Ao entrar, 500 de dano |
| Aqua | Corrente | Imune a armadilhas; aura +200 nos Sea Serpents |
| Pyro | Combustão | Ao entrar, 700 de dano; perde 200 LP por ataque |
| Rock | Muralha | Imune a mágicas; +400 DEF por Rock aliado |
| Plant | Raízes | Ao entrar, cura 500; +150/+150 por Plant no cemitério |

As sinergias atravessam tipos de propósito: Beast-Warrior + Beast, Sea Serpent +
Aqua, Fish + qualquer WATER, Curse of Dragon + Warriors (Gaia).

## Caçadores (counters)

Monstros com "ao entrar, enfraquece inimigos de um tipo": Sword Hunter (Dragon),
Zoa (Spellcaster), St. Joan (DARK), Labyrinth Tank (Warrior), Rabid Horseman
(Beast), Kazejin (Winged Beast), Swordstalker (Fiend), Summoned Skull (LIGHT),
Crimson Sunbird (Insect), Tri-horned Dragon (Dinosaur), Sanga (WATER),
Levia-Dragon (Machine), Suijin (Pyro), Great Moth (Plant).

Mágicas de destruição redirecionadas: Crush Card (ATK ≥ 2000), Warrior
Elimination, Eternal Rest (Zombie), Stain Storm (Machine), Eradicating Aerosol
(Insect), **Breath of Light (Fiend)** e **Eternal Drought (Dragon)**.

## A cadeia do Time Wizard (fusões inusitadas)

| Materiais | Resultado |
| --- | --- |
| Time Wizard + Mystical Elf | Dark Elf |
| Time Wizard + Dark Elf | Dark Magician |
| Time Wizard + Dark Magician | Magician of Black Chaos |
| Time Wizard + Cocoon of Evolution | Perfectly Ultimate Great Moth |
| Time Wizard + Petit Moth | Great Moth |
| Time Wizard + Machine King | Perfect Machine King |
| Time Wizard + Celtic Guardian | Gaia the Fierce Knight |
| Time Wizard + Labyrinth Wall | Labyrinth Tank |
| Gaia the Fierce Knight + Dark Magician | Black Luster Soldier |
| Kazejin + Sanga of the Thunder | Gate Guardian |
| Tri-horned Dragon + Blue-eyes White Dragon | Blue-eyes Ultimate Dragon |
| Summoned Skull + Red-eyes B. Dragon | B. Skull Dragon |
| Kuriboh + Summoned Skull | Zoa |
| Levia-Dragon + Sanga of the Thunder | Twin-headed Thunder Dragon |
| Mystical Elf + Dark Elf | St. Joan |
| Baby Dragon + Curse of Dragon | Serpent Night Dragon |

Time Wizard só cai no TEC de Shadi, Pegasus e Labyrinth Mage, com peso baixo.

## Oponentes

| # | Duelista | Tipos | Nível |
| --- | --- | --- | --- |
| 1 | Simon Muran | Spellcaster + Fairy | inicial |
| 2 | Teana | Fairy + Plant | inicial |
| 3 | Jono | Warrior + Beast-Warrior | inicial |
| 4–6 | Villagers | Beast + Insect / Rock + Reptile / Aqua + Fish | inicial |
| 7 | Seto | Dragon + Machine | médio |
| 8 | Heishin | Fiend + Spellcaster | médio |
| 9 | Rex Raptor | Dinosaur + Dragon | médio |
| 10 | Weevil | Insect + Plant | médio |
| 11 | Mai | Winged Beast + Fairy | médio |
| 12 | Bandit Keith | Machine + Pyro | médio |
| 13 | Shadi | Rock + Spellcaster | médio |
| 14 | Yami Bakura | Zombie + Fiend | médio |
| 15 | Pegasus | Spellcaster + Thunder | médio |
| 16 | Isis | Fairy + Aqua | médio |
| 17 | Kaiba | Dragon | médio |
| 18 | Mage Soldier | Warrior + Spellcaster | avançado |
| 19 | Jono 2nd | Warrior + Beast-Warrior | avançado |
| 20 | Teana 2nd | Fairy + Thunder | avançado |
| 21–30 | Magos | Aqua+Sea Serpent, Sea Serpent+Fish, Plant+Insect, Beast+Plant, Winged Beast+Dragon, Dragon+Thunder, Rock+Zombie, Reptile+Dinosaur, Beast-Warrior+Warrior, Beast-Warrior+Beast | avançado |
| 31 | Labyrinth Mage | Rock + Warrior | avançado |
| 32 | Seto 2nd | Dragon + Machine | final |
| 33 | Guardian Sebek | Pyro + Fiend | final |
| 34 | Guardian Neku | Fiend + Spellcaster | final |
| 35 | Heishin 2nd | Fiend + Dragon | final |
| 36 | Seto 3rd | Dragon | final |
| 37 | DarkNite | Fiend | final |
| 38 | Nitemare | Dragon + Spellcaster | final |
| 39 | Duel Master K | Machine + Thunder | final |

Cada deck recebe os equipamentos dos seus tipos, o campo do tipo principal e
mágicas/armadilhas por nível (Dark Hole a partir do médio; Raigeki e Megamorph
no final). A IA usa o modo **Difícil** do Studio (sem as desistências
aleatórias de fusão, Equip, Trap e Magia).

## Drops que preparam o próximo duelo

Para cada duelista, o mod olha os tipos do **próximo** oponente da história:

- **TEC:** as mágicas/armadilhas que punem esses tipos (peso alto).
- **POW:** a partir do #9, o caçador desses tipos.
- **B/C/D:** monstros do próprio deck e os counters com peso menor.

Exemplo: Heishin entrega Eternal Drought e Crush Card antes de Rex Raptor;
Isis libera Sword Hunter antes de Kaiba.

## Quests

Todos os 37 duelistas da história pedem doação antes do duelo (até 3 requisitos,
limite do overlay QOV7). Os pedidos sobem de 4 cartas no começo para 25 no fim e
usam só fontes que o Studio aceita (drops de antecessores garantidos). Cada
duelista tem sua frase de 2 linhas.

## Decks iniciais

Seis decks de 40 cartas, cada um com 2 tipos, 1 equip triplo, 1 equip duplo,
campo, armadilha, cura e **Dark Hole ou Raigeki**:

1. Chamas do Dragão (Dragon + Pyro, Raigeki)
2. Floresta Selvagem (Beast + Plant, Dark Hole)
3. Lâminas de Sogen (Warrior + Beast-Warrior, Dark Hole)
4. Marés Profundas (Aqua + Fish, Raigeki)
5. Sombras de Yami (Fiend + Zombie, Dark Hole)
6. Tempestade de Aço (Machine + Thunder, Raigeki)

O PS1 tem **um** gerador de deck inicial. O deck escolhido em `--inicial` é
gravado em pools exatos (o jogo recebe as 40 cartas certas); os seis ficam nas
partidas do Studio. Para jogar outro tema no PS1, aplique de novo com outro
`--inicial` e gere outro BIN/CUE.

## Limites conhecidos

- Os nomes seguem a lista em inglês do FM. O relatório aponta qualquer nome que
  o seu disco escreva diferente.
- Time Wizard ainda pode ser comprado por password no PS1 se o preço não for
  alterado em **Passwords e baú**.
- A IA Difícil remove desistências aleatórias; a escolha de Guardian Star da IA
  continua a original do PS1.
- O teste visual completo no ePSXe continua necessário.
