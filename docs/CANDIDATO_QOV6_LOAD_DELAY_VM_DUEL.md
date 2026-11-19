# Quests PS1 QOV6 — candidato de correção para "Doar e duelar"

**Estado: candidato para validação, NÃO confirmado no ePSXe.** Não lançar no atualizador ou substituir a versão estável antes do teste integrado no emulador.

## Reprodução

Versões anteriores:

- QOV3 / Studio 1.9.13: `unknown opcode 74410036 at 801AAE80`;
- QOV4 / Studio 1.9.14: `unknown opcode 63697473 at 801AAE78`;
- QOV5 / Studio 1.9.15: `unknown opcode 69727441 at 801AAE78`.

O PC está na tabela de critérios `QuestConfiguration`, dentro da arena substituível `0x801A9000..0x801AC000`; `0x69727441` corresponde a `Arti` no formato little-endian. Isso não identifica sozinho o salto causador da falha.

## Defeito adicional encontrado: MIPS I load delay

Os adaptadores de `tools/ps1/campaign_quest_loader.S` usam `.set noreorder`. O pipeline original do PS1 não disponibiliza o resultado de um `lw/lbu/lhu` na instrução imediatamente seguinte. Havia cinco usos imediatos dos registradores carregados: **um** em `QuestDuelLoader` e **quatro** em `QuestAnswerLoader`. Eles podem gerar decisões de fluxo incorretas; o teste Unicorn em modo MIPS32 não reproduz de modo confiável essa característica do R3000.

O QOV6 reordena instruções (e usa um `nop` já existente) para eliminar os cinco riscos **sem aumentar o tamanho de nenhum dos carregadores**. Um teste de análise estática verifica a dependência entre `load` e a instrução seguinte em todos os carregadores residentes.

## Transição de doação para duelo

1. `QuestAnswer` verifica os requisitos, debita somente cópias livres do baú, marca a quest concluída, limpa o checkpoint da loja e aponta para os seis operandos originais de `F8 0D`.
2. O callback marca `TEXT_YIELD=1` e entrega o marcador transitório `0x44` ao carregador **residente**.
3. `QuestAnswerLoader` espera a conclusão do C do overlay, consome o marcador, valida modo, banco, offset e ID do oponente e **volta o cursor dois bytes, para `F8 0D`**.
4. O carregador retorna ao interpretador sem entrar em `Text_StartCampaignDuel` nessa chamada de `F8 12`.
5. **No próximo ciclo da VM**, o interpretador processa `F8 0D` do script de campanha. `QuestDuelLoader` reconhece a flag concluída e salta diretamente à rotina de duelo nativa `0x80038530`. O modo 3 deve abrir o baú/deck original.

O C compilado da quest **não foi modificado funcionalmente**; apenas comentários foram atualizados. O `PAYLOAD` da quest mantém bytes e SHA256 idênticos à QOV5; foram alterados os três adaptadores MIPS residentes, o identificador `QOV6` e os testes. O build Zig 0.13 precisa confirmar essa correspondência exata.

## Testes disponíveis

- Testes de análise estática de MIPS I para read-after-load imediato;
- Unicorn para doação única, retorno à VM, replay do `F8 0D` no próximo tick e baú/deck simulado;
- NPCs da campanha, incluindo torneio, Simon isento, retorno ao Card Shop e quest já concluída;
- Teste de preservação de deck/memory state, flags e não repetição de débito;
- CI recompila `campaign_quest_loader.S` e `campaign_quests.c` e exige blob exato byte a byte.

## Checklist ePSXe (ainda pendente)

1. Backup do memory card `.mcr` e do projeto antes de exportar.
2. Gerar **nova** imagem BIN/CUE com Studio atualizado e **Original Drop x15 não modificado** usado na importação; não usar um BIN de versão QOV3–QOV5 como fonte.
3. Fechar completamente o ePSXe, iniciar por boot limpo e usar Memory Card (não save state antigo).
4. Escolher `Doar e duelar` com cartas suficientes. Esperado: **uma** doação, abertura do baú nativo, deck de 40 cartas intacto, duelo funcional.
5. Terminar o duelo, salvar e reiniciar; verificar saldo, flags e nova tentativa sem segundo débito.
6. Testar `Ir ao Card Shop`, voltar à quest e aceitar depois, incluindo o torneio e Egito.
7. Em caso de erro: preservar **SLUS_014.11 e WA_MRG.MRG exportados**, relatório `.json` e registrar PC/RA/SP no debugger. Não adivinhar que a QOV6 está corrigida.

## Segurança de entrega

A branch é propositalmente separada da `main`. Só fazer merge/lançamento depois que a pipeline estiver verde e os cenários acima funcionarem no ePSXe.
