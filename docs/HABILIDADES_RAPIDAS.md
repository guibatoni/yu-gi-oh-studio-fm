# Habilidades rápidas — Studio FM

O Studio traz uma faixa de **Habilidades rápidas** na aba **Efeitos**. Selecione uma criatura e marque os recursos desejados. As opções passam a ser rascunhos automaticamente; **Salvar projeto** ou **Ctrl+S** grava tudo de uma vez. Navegar entre cartas não abre perguntas de salvar.

## Habilidades disponíveis

| Habilidade | Regra |
|---|---|
| Ataca 1x, 2x ou 3x | Define o máximo de ataques por monstro a cada turno. Atacante deve estar virado para cima. |
| Indestrutível | Preserva o monstro virado para cima contra destruição. A perda de LP do combate continua valendo. |
| Imune a mágicas | Protege um monstro virado para cima de efeitos como Dark Hole, redução de atributos e Swords of Revealing Light. |
| Imune a armadilhas | Protege um monstro virado para cima de armadilhas de ataque e de Reverse Trap ao equipar. |
| Dano perfurante | Quando ATK da criatura excede DEF do alvo em posição de defesa, causa a diferença aos LP do jogador defensor. |
| Não pode ser bloqueada | Permite ataque direto aos LP mesmo quando o oponente tem monstros em campo. |
| Ataca no primeiro turno | Libera o ataque para esse monstro quando o jogo bloquearia o ataque no turno de abertura. |
| Cada ataque perde X LP | O controlador perde os LP definidos a cada ataque realizado, inclusive em ataque direto, até zero. O gatilho aplica-se por ataque, não na atualização da tela. |
| Sem limite de cópias no deck | O deck de 40 espaços pode ser preenchido com cópias da mesma carta. |

No Drop x15, salve o projeto e use **Gerar jogo BIN/CUE** para aplicar as
habilidades à cópia do jogo.

## Exemplo de uso

Selecione a carta nº 001 → aba Efeitos → selecione `3x`, marque `Dano perfurante` e informe `500` em `Perde LP a cada ataque`. Clique em **Salvar projeto**.

Abra **Laboratório: campo, decks e equips**, escolha o monstro do jogador no primeiro slot e um alvo no lado adversário. Clique em `Atacar alvo`, até três vezes. Para reiniciar a quantidade, clique em `Novo turno (origem)`. Para dano direto use `Ataque direto`; se o oponente controla criaturas, a carta precisa ter `Não bloqueável`.

O laboratório trata o combate **ATK contra DEF** ou **ATK contra ATK**, conforme a caixa escolhida. Seus cálculos são um protótipo inspirado nas regras de PS1, não um emulador de combate completo.

## Compatibilidade

Projetos antigos continuam usando `schema: 1`. O Studio preserva os efeitos personalizados existentes ao trocar os presets de habilidades rápidas. O pacote não inclui ROMs, BIOS, artes extraídas nem backups pessoais.
