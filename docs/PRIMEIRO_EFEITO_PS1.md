# Efeitos PS1 — etapa inicial

O primeiro efeito modificável com segurança aproveita o motor original de
**Equipamentos** (Equip). Você escolhe que monstro existente poderá usar um
equipamento existente, e o jogo aplica seu efeito clássico (+500 ATK na maioria
das cartas Equip; algumas possuem regras próprias).

## Teste no ePSXe
1. Abra o projeto cujos BIN/CUE e WA_MRG foram importados e tiveram hash salvo.
2. Na aba Efeitos, selecione uma carta do tipo Equip.
3. Clique "PS1: permitir Equip em criatura" e informe o ID do monstro.
4. Clique "Gerar jogo BIN/CUE" e selecione a imagem original usada no projeto.
5. Abra o novo FM_STUDIO_TESTE_*.bin no ePSXe e tente equipar a criatura.

Os alvos são guardados em projeto.json, em metadata.ps1_equip_additions.
A exportação só mexe no bloco de equipamentos original de WA_MRG.MRG.
Ela recusa versões com sete cópias divergentes, dados desconhecidos
ou espaço insuficiente. Não modifica as fusões.

O primeiro efeito **inédito**, bônus por tipo no cemitério, ainda requer
pontos de entrada MIPS para destruição, cemitério, atualização de ATK/DEF
e descarregamento de overlays. Esta etapa não executa auras nem novos
efeitos no motor do PS1.
