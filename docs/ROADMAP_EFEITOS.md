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
