## v1.4.14 — Sequência do patch God24 real

1. Inspecionar predicados em CardList_RenderDeckBoxStats e
   func_80060E70 para corrigir apresentação de ATK/DEF e layout.
2. Preservar Magia(20), Armadilha, Ritual e Equip(23) em todos os
   ramos; **jamais** trocar a comparação 20 por 25.
3. Rastrear chamadas de colocação de carta, registro de duelo,
   terreno e ações de campo para permitir invocação e combate.
4. Colocar novo sprite de tipo numa região gráfica e memória
   verificada; não sobrescrever Guardian Stars.
5. Ativar hooks MIPS apenas para assinatura SLUS e cave comprovadamente
   livres, numa cópia BIN, com readback e testes reais ePSXe.

O relatório inclui offsets de possíveis predicados e seus opcodes
para análise, mas não instala hooks automaticamente.

## v1.4.3 — Inspeção de instruções das rotinas de duelo

O diagnóstico do usuário passa a registrar as primeiras 20 instruções de
cada uma das nove regiões MIPS, com endereço RAM, offset SLUS, opcode,
mnemônico de classe, destinos de J/JAL/branch e marcação de *delay slot*.
Esses dados ajudam a localizar pontos para protótipos de bônus de cemitério
e ataques múltiplos; não constituem descompilação completa nem prova de hook.
O código de origem e o BIN não são alterados por esse diagnóstico.

Critérios para qualquer futuro patch de efeito: assinatura MIPS do MOD,
ABI e registradores preservados, endereço da função validado, trecho de
código livre efetivo, ramo com delay slot íntegro, verificação por readback,
cópia isolada do disco e ensaio em ePSXe.

## v1.4.2 — Teste do pipeline de patch MIPS

Primeira prova opt-in de mudança real de instrução MIPS: LP inicial do
duelo normal (retail; 8000 -> 9000). Não implementa efeitos customizados,
mas exercita a escrita do SLUS e a regeneração dos setores de disco em
uma cópia, com verificação e bloqueio para assinatura incompatível.

Próximo passo para a primeira habilidade inédita: localizar pontos de
chamada \`Duel_CalcCardStats\` e o estado de cemitério, validar ABI/registradores,
identificar área de código com segurança e testar a primeira rotina de bônus
sem alterar as fusões ou o executável original.

## v1.4.1 — Referências JAL verificáveis (somente leitura)

O relatório MIPS agora faz varredura de JAL estáticos para as nove rotinas
mapeadas, *somente* quando o cabeçalho PS-X EXE declara endereço e tamanho
de segmento coerentes com o SLUS importado. Informa o número de chamadas,
até 16 endereços de origem por rotina, e se o primeiro opcode parece um
prólogo clássico (`addiu sp,sp,-N`). Endereços sem prólogo podem ser
funções folha legítimas; ausência de JAL pode significar JALR, inlining,
redirecionamento ou região não utilizada.

**É um diagnóstico, não um patch:** uma referência JAL, mesmo única,
não comprova que ela possa ser substituída por hook, que existe espaço
seguro para código novo ou que um efeito tenha sido instalado. Até o
momento não há nova habilidade inédita executável no PS1. Testes no ePSXe
continuam indispensáveis.

## v1.4.0 — Preparação de efeitos MIPS sem falsos positivos

**Estado:** aura, cemitério, imunidades, indestrutibilidade, ataques 2x/3x,
perfuração, ataque direto com monstros inimigos e limites de cópias POR CARTA
funcionam no simulador, mas ainda NÃO como novas rotinas MIPS gravadas no PS1.

### Endereços de referência da recompilação do SLUS_014.11

| Objetivo | Rotina | RAM |
| --- | --- | --- |
| Recalcular bônus contínuos | Duel_CalcCardStats | 0x800170C8 |
| Remoção de campo | DuelCard_RemoveFromField | 0x80024954 |
| Já agiu no turno | DuelCard_CanActThisTurn | 0x8001700C |
| ATK da batalha | Duel_CalcBattleAttack | 0x8001EF1C |
| Resultado do combate | DuelScene_UpdateBattle | 0x8001F55C |
| Seleção de ataque/campo | DuelScene_UpdateFieldActions | 0x8001D670 |
| Colocar/equipar cartas | DuelScene_UpdateCardPlacement | 0x80019D18 |
| Cópias por ID no construtor | BuildDeck_UpdateChestPaneInput | 0x800336F0 |

Esses locais correspondem ao SLUS original; MODs podem realocar ou
redirecionar funções. O Studio calcula hashes das regiões presentes no
executável de cada projeto e indica entradas com saltos, sem tratá-los
automaticamente como hooks seguros.

### Sequência técnica

1. Aura e cemitério: contagem dinâmica por tipo/lado, detectar envio ao
   cemitério e atualizar ATK/DEF sem acumular bônus duplicados. Distinguir
   destruição, fusão, retorno e descarte, inclusive mudanças fora de batalha.
2. Imunidades/indestrutibilidade: interceptar resolução de magia, trap e
   resultado de batalha em ambos os lados; imunidade não é só preservar HP.
3. 2x/3x ataques: contador por criatura/turno, reset, seleção repetida e
   reprodução de ataques, preservando trocas de slot e fusões.
4. Perfuração/negação de bloqueio: seleção de alvo e cálculo de dano em defesa
   ou direto apesar do campo adversário.
5. Deck: alteração global de cópias 1–40 com comparação MIPS específica.
   Limites diferentes por ID exigem uma nova tabela no runtime; capacidade
   física maior que 40 exige rever mais estruturas de armazenamento.

Nenhum novo handler de duelo foi injetado no BIN nesta versão. A ferramenta
de diagnóstico gera exportacao/diagnostico_motor_efeitos_mips.json para
fundamentar os próximos patches, sem copiar ou publicar a ROM.

---

# Roadmap de efeitos sem quebrar o PS1

## Fase inicial — concluída no editor

1. Efeitos são dados estruturados por carta: `evento`, `acao`, `alvo`, `valor`.
2. Eventos suportados: invocação, ataque, defesa, destruir, ser destruído, início/fim de turno.
3. Ações simuladas: alterar ATK, alterar DEF, dano LP e cura LP.
4. Simulação de único gatilho, cenário-base de LP=8000 e monstro rival ATK=1800 DEF=1500.
5. Fusões congeladas para conservar a compatibilidade com o jogo original.

## Próxima fase — engenharia reversa de execução no PS1

1. Verificar o motor de efeitos do executável `SLUS_014.11` original retail, em contraste com a versão Drop X15.
2. Identificar rotinas e eventos que realmente existem e os estados de duelo associados.
3. Escolher um efeito pequeno e reproduzível para prototipagem, inicialmente alteração de ATK/DEF por uma ação existente.
4. Implementar código MIPS ou redirecionamento de rotina com verificação dos bytes originais, sem supor espaços livres no executável.
5. Criar teste no ePSXe para as fases de duelo, monstros face-up/down, fusões originais e saves.
6. Depois de validar os efeitos no jogo, criar exportação de patch delta para imagem de PS1. A geração de BIN/CUE também exige estrutura de setores e correção EDC/ECC quando aplicável.
7. Só então mudar o estado de `efeitos_planejados.json` de simulável para jogável em builds validadas.

## Limitação atual

Adicionar qualquer efeito a qualquer carta no PS1 original NÃO acontece somente escrevendo JSON. Mesmo que uma versão de PC recompilada permita efeitos genéricos, isso não os torna jogáveis no ePSXe. São motores e formatos de execução diferentes.

## Referências técnicas de consulta

- https://github.com/Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled/blob/master/notes/modding-tutorial-evidence.md
- https://github.com/Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled/blob/master/tools/pc/fm_editor/README.md
- https://github.com/Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled/blob/master/notes/more-cards.md

## v0.7.0 — Camada contínua do simulador
- `aura_tipo`: +`valor` ATK e +`valor_def` DEF a aliados face-up do `tipo_id` enquanto fonte permanece face-up no campo.
- `bonus_por_tipo`: carta-fonte recebe `quantidade_de_aliados_face_up_tipo_id * (valor, valor_def)`.
- Reavaliação pura do campo, sem repetição/empilhamento indevido ao destruir/invocar. Várias fontes somam efeitos.
- Contabiliza apenas o próprio campo, exclui oponentes. Fonte conta como um monstro quando tiver o tipo.
- O comportamento é **somente protótipo em Python**. PS1 exigirá descoberta dos pontos de atualização de campo, UI de ATK/DEF, ciclo de batalha, memória e formas de preservar fusões.

## v0.8.0 — Efeitos baseados em deck e equipamentos

- `bonus_deck_tipo` (contínuo, alvo próprio): count(TIPO no deck completo configurado) × (ATK/DEF).
- `cura_lp_deck_tipo`, `dano_lp_deck_tipo`, `descartar_alvo`, `dano_monstro_alvo` (efeitos ativados por clique).
- `equip_imune_armadilha`, `equip_imune_magia_armadilha`, `equip_indestrutivel`, `equip_atk` (passivos do equipamento anexado).
- `aura_tipo` e `bonus_por_tipo`: `tipo_id=-1` significa todos os tipos; `escopo` define aliados, inimigos ou ambos.
- Contagem do deck fixo, sem repetir gatilhos na atualização de campo. Configuração de até 40 cartas por lado.
- Campo de simulação 5×5, com um seletor visual de equipamento por monstro. Dados de projeto antigos seguem compatíveis.
- **Limitação importante:** criaturas do Forbidden Memories original não possuem HP. Dano a monstro usa resistência experimental igual à DEF-base (mínimo 1) exclusivamente no Studio.
- **Não há patch jogável** nem efeitos em execução no ePSXe nessa etapa; só o código do simulador foi implementado.
