# Habilidades rápidas — FM Studio v0.9.0

O Studio traz uma faixa de **Habilidades rápidas** na aba **Efeitos**. Selecione uma criatura e marque os recursos desejados. As opções passam a ser rascunhos automaticamente; **Salvar projeto** ou **Ctrl+S** grava tudo de uma vez. Navegar entre cartas não abre perguntas de salvar.

## Habilidades disponíveis

| Habilidade | Regra no simulador |
|---|---|
| Ataca 1x, 2x ou 3x | Número máximo de ataques por monstro **por turno simulado**; 1x é padrão. Atacante deve estar virado para cima. `Novo turno` reinicia ataques do lado escolhido. |
| Indestrutível | Impede destruição por dano letal simulado e por resultado de combate; remoção explícita do campo ainda é possível. |
| Imune a mágicas | Bloqueia dano de efeitos categorizados como `magia` no simulador. Outras interações de magias ainda não implementadas. |
| Imune a armadilhas | Bloqueia dano de efeitos categorizados como `armadilha` no simulador. Outras interações de armadilhas ainda não implementadas. |
| Dano perfurante | Quando ATK da criatura excede DEF do alvo em posição de defesa, causa a diferença aos LP do jogador defensor. |
| Não pode ser bloqueada | No laboratório, permite ataque direto aos LP mesmo quando o oponente tem criaturas em campo; não implementa o modelo de bloqueadores do MTGA no PS1. |
| Cada ataque perde X LP | O controlador perde os LP definidos a cada ataque realizado, inclusive em ataque direto, até zero. O gatilho aplica-se por ataque, não na atualização da tela. |
| Sem limite de cópias no deck | A carta pode aparecer mais de 3 vezes no deck configurado; **o total do deck continua limitado a 40 cartas**. |

Todas são capacidades do **simulador do Studio**; não estão aplicadas ao executável original de PlayStation 1. As receitas de fusão não são alteradas.

## Exemplo de uso

Selecione a carta nº 001 → aba Efeitos → selecione `3x`, marque `Dano perfurante` e informe `500` em `Perde LP a cada ataque`. Clique em **Salvar projeto**.

Abra **Laboratório: campo, decks e equips**, escolha o monstro do jogador no primeiro slot e um alvo no lado adversário. Clique em `Atacar alvo`, até três vezes. Para reiniciar a quantidade, clique em `Novo turno (origem)`. Para dano direto use `Ataque direto`; se o oponente controla criaturas, a carta precisa ter `Não bloqueável`.

O laboratório trata o combate **ATK contra DEF** ou **ATK contra ATK**, conforme a caixa escolhida. Seus cálculos são um protótipo inspirado nas regras de PS1, não um emulador de combate completo.

## Compatibilidade

Projetos antigos continuam usando `schema: 1`. O Studio preserva os efeitos personalizados existentes ao trocar os presets de habilidades rápidas. O pacote não inclui ROMs, BIOS, artes extraídas nem backups pessoais.
