## v1.4.22 — God24 experimental na colocação e confirmação

- O teste já marcado para God24 na mão também cobre colocação e estrela
  guardiã ao gerar outra cópia do Drop x15.
- Quatro decisões da mão, sete de colocação e duas de confirmação agora
  reconhecem o tipo 24 como monstro e preservam os tipos originais.
- A releitura exige os 13 pontos na cópia antes de concluir a exportação.
  O verificador ainda reconhece imagens com o teste da mão da v1.4.21.
- A escolha de posição, a estrela guardiã e o ataque precisam de um duelo
  no ePSXe para validação de ponta a ponta.

## v1.4.21 — Corrigidos os quatro offsets do patch de God24 na mão

- Corrigido erro de -0x800 na conversão de RAM para SLUS:
  C214/ C400/ C9FC/ CD34 -> CA14/ CC00/ D1FC/ D534.
- Assinaturas MIPS continuam obrigatórias; falha detalha offset/opcode.
- Testes de regressão com PC RAM, EXE_DELTA e sequência completa
  do patch de baú + renderizador + mão.
- Não libera instalação em MODs diferentes nem patch já aplicado.
- Invocação e combate God24 permanecem testes experimentais.

## v1.4.20 — Primeiro patch opt-in do God24 na mão do duelo

- Usa o diagnóstico real da v1.4.19 para corrigir quatro máscaras
  MIPS, com SHA original e cinco opcodes de contexto obrigatórios.
- Classificação monstro/especial preservada para 0–23; a máscara
  modifica temporariamente 8–15 para 0–7 no registrador local,
  e God24 para 16. Possíveis efeitos indiretos exigem teste no emulador.
- Tipo real no BIN continua 24; nenhum SLUS original é sobrescrito.
- Novo botão de ativação; sem ativação automática.
- Readback no BIN exige 4/4 modificações ou mantém imagem anterior.
- Testes sintéticos para 0–24, falha de assinatura, patch parcial
  e isolamento exato de 16 bytes modificados.
- A jogabilidade ainda exige validação emulador e correções adicionais
  na colocação do monstro. Ícone Deus continua pendente.

## v1.4.19 — Fluxo de God24 como magia no duelo

- Confirmado o problema depois de v1.4.18: valores ATK/DEF aparecem,
  mas o motor continua tratando God24 como carta especial.
- Adicionado diagnóstico read-only das decisões de mão, colocação,
  ativação especial, campo e criação de registro.
- Coletados limites de tipo, máscaras, saltos e contexto MIPS,
  preservando o SLUS original.
- Novos testes sintéticos sem alterações na jogabilidade atual.
- Não corrige invocação/combat; testes em ePSXe para isso pendentes.

## v1.4.18 — Patch experimental do renderizador verdadeiro do baú

- Função func_80031874 corrigida na cópia BIN: três instruções MIPS.
- Offset 0x222F8: LBU do tipo em $at; 0x22304: ANDI $at,0x17;
  0x2230C: SLTIU $v0,$at,20.
- Load delays, SH do sprite, branch e delay slot preservados.
- 0–23 classificados como no PS1 original; 24 ganha teste visual.
- Tipos 25–31 bloqueados; assinatura exata dos 11 opcodes obrigatória.
- Verificador do BIN informa readback 3/3 além das máscaras anteriores 2/2.
- Sem alteração de ícone, invocação ou combate; ePSXe pendente.

## v1.4.17 — Alvo real de ATK/DEF do baú

- \`func_80031874\` confirmado no decompilador PS1 como renderizador
  de oito linhas e seus ATK/DEF.
- \`Verificar BIN/CUE\` inclui hash e análise de SLTI/SLTIU 20,
  cargas LBU, branches e delay slots nesta função.
- Mostra explicitamente que as máscaras v1.4.15 não alteram a
  rotina responsável por ATK/DEF na captura do ePSXe.
- Nenhuma alteração nova de executável, sprite ou regras de duelo.

## v1.4.16 — Diagnóstico do BIN que o usuário executou

- Verificação de 0/2, 1/2 ou 2/2 máscaras reais no SLUS do BIN/CUE escolhido.
- Relatório inclui tipo, ATK e DEF efetivamente gravados para God24.
- Aviso ao gerar imagem quando a opção de patch de baú não estiver ativa.
- Mensagem final informa claramente se o teste estava aplicado.
- Testes sintéticos de máscaras ausentes, presentes e parciais.
- Nenhuma alteração nova nos limites do motor MIPS ou no ícone.

## v1.4.15 — Duas máscaras MIPS para ATK/DEF de God24 no baú

- Opt-in explícito na aba Cartas para apresentação do tipo 24 no baú.
- 0x51500 e 0x51728: ANDI v0,v0,31 passa para ANDI v0,v0,23.
- Tipos 0–23 preservados; somente 24 ganha status de monstro nessa comparação.
- 25–31 proibidos; SHA do SLUS e assinaturas de contexto verificadas.
- Nenhuma intervenção em combate, invocação ou ícone; ePSXe pendente.

## v1.4.14 — Correção do diagnóstico de God24 sem atributos

- Evidência em ePSXe: Time Wizard #016 com tipo 24 aparece sem ATK/DEF
  no deck. A gravação do valor 24 na tabela não torna a carta monstro.
- A rotina CardList_RenderDeckBoxStats (0x80060B38) tem comparação
  de tipo menor que CARD_TYPE_MAGIC (20) para exibir números.
- Relatório MIPS estendido: oito janelas com hashes, limites do
  segmento, comparações slti/sltiu 20 e addiu -20, contexto e ramo.
- Mensagens de geração e manifesto agora não confundem "gravado no BIN"
  com "reconhecido como monstro e renderizado".
- O botão experimental deixa claro que o glifo só vai na descrição.
- Nenhum patch de terreno/invocação/ícone é aplicado sem assinatura
  validada do jogo e sem preservar as categorias não-monstro 20–23.

- Segurança de memória reforçada: stream_58 é s8 assinado; exige 0–21 antes de acessar streams[22].
## v1.4.13 — Engenharia do hook God24 sem escrita automática

- Trampoline MIPS R3000A com filtro tipo 24/kind=0 e preservação das estrelas.
- Branches calculados e load-delay slots explícitos.
- Rejeição de JAL, delay slot, imagem, offset ou região de código diferentes.
- Testes sintéticos de isolamento de bytes e bloqueio até confirmação do cave.
- Não aplicado ao BIN de produção; ícone no baú ainda depende de teste no ePSXe.

## v1.4.12 — Chamadas JAL e delay slots da exibição God24

- Relatório de chamadas para func_80036C14, com opcode, delay slot e contexto.
- Verificação comparativa dos SHA-256 das três regiões do diagnóstico anterior.
- Validação de t_addr/t_size antes de inspecionar o segmento carregado.
- Testes sintéticos de chamada MIPS e arquivo incompatível.
- Nenhuma injeção MIPS no jogo nesta etapa; o BIN original fica intacto.

## v1.4.11 — Diagnóstico da ausência de ícone God24

- Separadas as rotinas de ícone de tipo do glifo da descrição.
- Identificada colisão de índice 24 com a primeira Guardian Star, impeditiva de troca simples de bitmap.
- Relatório MIPS inclui três janelas de referência com hashes e opcodes para orientar um hook seguro.
- Nenhuma alteração de renderização foi aplicada; BIN e sprites originais preservados.

## v1.4.10 — Seleção segura de célula para ícone God

- Diagnóstico de células 0x27–0x30 antes de inserir pixels 4bpp.
- Se 0x29 estiver ocupada, procura uma célula vazia e usa o F8 0B XX correspondente.
- Nunca substitui pixels do mod em uma célula não vazia.
- Quando nenhuma célula está vazia, omite apenas o ícone e mantém teste independente de God 24 / ATK.
- Manifesto e mensagem de geração distinguem claramente ícone omitido de tipo gravado.
- Testes de célula 0x29 ocupada, remapeamento, nenhuma livre e isolamento da descrição.

## v1.4.9 — Correção da dependência do ícone God no Windows

- Leitor PNG RGBA 16×16 sem Pillow, com validação de CRC, limites e filtros.
- Pacote Windows passa a coletar explicitamente Pillow para outras artes.
- CI com Python -S para provar que o ícone funciona sem pacotes externos.
- Testes de PNG corrompido, filtro e preservação de bytes WA_MRG.
- Sem alteração nas regras MIPS nem nos atributos salvos do projeto.

## v1.4.8 — Permitir ensaio do tipo Deus 24 sem converter para outro tipo

- Modal de confirmação explícita ao gerar BIN com God24 na carta selecionada.
- Opt-in limitado a uma carta; exportador grava 24 real nos 5 bits de tipo,
  mantém ATK/DEF e bloqueia qualquer edição fora do escopo autorizado.
- Auditoria e verificador de imagem distinguem bytes realmente gravados
  de comportamento de monstro ainda não implementado no motor original.
- Teste de ícone 16×16 via descrição passa a aceitar God24 autorizado.
- Regressões de hash da imagem original, rejeição sem opt-in, diferença de
  tipo detectada e confirmação do par ATK/tipo no BIN sintético.
- **Ainda não implementa novo ícone fixo de tipo nem novos hooks do motor**.

## v1.4.7 — Teste nativo de símbolo Deus no texto de uma carta

- Usa o PNG \`god.png\` já distribuído pelo Studio.
- Novas rotinas de conversão 16×16 RGBA -> índices 4bpp usando CLUT existente.
- Alvo experimental \`WA_MRG.MRG\`, segunda página de fonte, célula 0x29;
  falha de forma segura caso qualquer byte da célula já esteja em uso.
- Insere \`F8 0B 29\` nos primeiros 3 bytes da descrição de UMA carta,
  somente na cópia gerada; não muda tipo, ATK, DEF nem texto salvo no projeto.
- A prévia agora exibe o símbolo na carta de raridade Deus.
- Novo controle opt-in de ativar/desativar por carta. Exportação verifica hash
  WA original e relê os arquivos gerados antes de substituir imagem anterior.
- Testes sintéticos para isolamento de bytes, slot preenchido e código textual.
- Tipo God 24/ícone permanente de tipo ainda dependem de hooks validados.

## v1.4.6 — Escolha de tipo, sem reversão forçada para Spellcaster

- Removido o botão que fazia o usuário voltar a Spellcaster para poder
  gravar o Time Wizard. Agora pode escolher livremente qualquer tipo
  jogável PS1 (0–19).
- Diálogo para escolher o tipo e manter (opcionalmente) o visual Deus no
  Studio sem injetar tipo God 24 no motor retail.
- Retirado aviso que exigia Spellcaster no Time Wizard.
- Tipo escolhido, ATK 3000, DEF, efeitos e raridade visual ficam preservados.
- Testes de tipo diferente do original, número de ATK gravado e escolhas
  inválidas sem mutação do rascunho.

## v1.4.5 — Evita perda silenciosa do ATK (Time Wizard)

- Reprodução: Time Wizard #016 configurado com 3000 ATK e tipo 24 — God
  mantém 500 ATK no jogo, porque o antigo exportador ignorava o registro.
- Correção: toda edição numérica em tipo God/indefinido ou atributo incompatível
  falha na exportação com orientação explícita, sem substituir BIN anterior.
- Restauração de tipo da carta #016 usa referência retail (01 Spellcaster).
- A verificação da imagem não oculta cartas ignoradas.
- Testes de BIN sintético, restauração preservando efeitos e pré-validação.

## v1.4.4 — Correção de tipo e números de alta precisão no Studio

- Botão para restaurar apenas o tipo original por carta, sem apagar poderes/efeitos.
- Proteção dos seletores de tipo/atributo/estrela/raridade contra rolagem do mouse.
- ATK e DEF editáveis como números inteiros grandes no simulador.
- LP inicial do simulador personalizável e sem antigo teto de 99999.
- Exportação PS1 recusa estatísticas que sofreriam truncamento de 9 bits.
- Testes de restauração seletiva, persistência e não exportação de valores grandes.

## v1.4.3 — Inspeção estática de rotinas MIPS

- Relatório adicional por rotina com até 20 palavras de máquina decodificadas.
- Reconhece chamadas, desvios, retornos, loads/stores e delay slots.
- Interface mostra quantidade de chamadas diretas para cálculo de atributos.
- Testes com instruções sintéticas e garantias de operação somente leitura.
- Sem injeção de novos handlers MIPS, sem modificação da ISO por diagnóstico.

## v1.4.2 — Smoke test executável do motor PS1

- Prova opcional de patch da instrução \`addiu $v0,$zero,8000\` em SLUS+0x7DD0.
- Bloqueio em MODs sem opcode retail idêntico; nenhum código ou tabela realocados.
- Guarda valor no projeto, gera somente cópia BIN/CUE, com manifesto verificável.
- Testes com SLUS sintético, limite de valores e hash original preservado.
- Ainda requer validação ePSXe; habilidades inéditas permanecem só no simulador.

## v1.4.1 — Grafo preliminar de chamadas MIPS

- Adicionada varredura de referências diretas JAL para nove endereços de referência.
- Usa t_addr e t_size do cabeçalho PS-X EXE e recusa endereço base inesperado.
- Registra total e até 16 chamadas por rotina, indício de prólogo clássico e aviso explícito de que nenhuma habilidade inédita foi injetada.
- Testes sintéticos para chamadas válidas, cabeçalho incorreto e segmento fora dos limites.
- Mantém patch global de deck e ferramentas de Equip existentes; novos testes reais no ePSXe ainda são necessários.

## v1.4.0 — Prioridade aos efeitos inéditos e relatório MIPS

- Ferramenta Diagnosticar motor MIPS: mapeamento e hashes das regiões de cálculo,
  batalha, remoção, ação por turno e regras do deck.
- Limites de 1–40 cópias por ID no simulador (∞ significa 40), retrocompatível
  com projetos anteriores.
- Patch MIPS opcional e experimental para limite GLOBAL de cópias no PS1.
  Aplica apenas a comparação slti/sltiu com imediato 3, branch próximo e
  candidato único; recusa entrada redirecionada e candidatos ambíguos.
- Controles de Ritual, Trap e terreno retirados da tela Efeitos por enquanto;
  receitas Ritual anteriores não são apagadas nem gravadas no BIN sem opt-in.
- Testes de scanner MIPS, alteração de instrução, BIN/CUE sintético e limites
  individuais do simulador. Teste real de deck no ePSXe ainda pendente.
- Auras, cemitério, proteções, ataques múltiplos, perfuração e ataque direto
  continuam sem handlers MIPS no PS1, apesar de funcionarem no simulador.

## v1.3.0 — Mais efeitos nativos graváveis em BIN/CUE PS1

- Ritual: altera três tributos e o resultado de um Ritual original em sete tabelas, sem aumentar registros ou tocar nas fusões.
- Armadilhas de ataque #681–#686: altera o limiar em centenas de ATK na tabela de seis bytes do SLUS; rejeita layout alterado e valores fora de ordem.
- Bônus de terreno: configura bônus ATK/DEF dos seis campos por tipo original (0–19), exigindo origem com tabela stock ±500.
- Interface Efeitos recebe os três controles, com auditoria e manifesto de exportação detalhados.
- Testes sintéticos verificam os três grupos no mesmo BIN/CUE, os bytes modificados e a preservação do arquivo original.
- Apenas Equip teve funcionamento em duelo confirmado pelo usuário. Ritual, Trap e terreno ainda precisam de teste real no ePSXe.
- Bônus dinâmicos de cemitério, auras inéditas, imunidades, ataques 2x/3x, perfuração, primeiro turno, cartas extras e tipo God seguem pendentes de programação MIPS.

## Validação no ePSXe — Equip funcionando (15/11/2026)

- **Confirmado pelo usuário:** após atualizar para Studio FM v1.2.8 e testar no ePSXe com o MOD Original Drop X15, a alteração de compatibilidade de Equip funcionou em duelo.
- A correção reconhece o preenchimento homogêneo FF no espaço reservado da tabela Equip e adiciona permissões sem remover alvos existentes nem deslocar fusões.
- O usuário não especificou neste retorno qual equipamento foi utilizado; não registrar como validada uma combinação específica.
- Próximo marco: efeitos novos de motor, especialmente bônus contínuos por tipo no cemitério; **não** considerá-los implementados no PS1 antes de teste real.

## v1.2.8 — Aceitar padding FF verdadeiro na tabela de Equip do Drop X15

- Analisada a imagem real **Yu-Gi-Oh! FM Original (Drop x15)** já compartilhada: suas sete tabelas de equipamentos têm conteúdo idêntico, terminador u16 em 0x201A e, após o terminador, 2020 bytes do valor FF até o fim da região reservada (0x2800).
- O Studio incorretamente tratava todos os FF como dados ocupados e informava zero bytes livres. Agora pode expandir a lista usando o preenchimento homogêneo FF de TODO o restante da área reservada.
- O patch continua preservando dados adicionais não padronizados, bloqueando regiões mistas e verificando estrutura, limites, fusões e as sete cópias.
- Um teste com duas permissões existentes (Equip #302 e #315 para monstro #016) consome 4 bytes desse espaço, deixando os 2016 bytes restantes em FF, sem precisar realocar o ISO.
- O método bitmap MIPS da v1.2.7 permanece para MODs que efetivamente usem esse formato. A nova gravação das permissões ainda requer validação dentro do ePSXe.

## v1.2.7 — Equip: reconhecimento de bitmap MIPS e adições automáticas

- Detecta a rotina Duel_CheckEquip modificada que utiliza registros de 94 bytes (u16 Equip + 92 bytes bitmap de monstros), seguindo endereços presentes no executável, inclusive salto direto para rotina alternativa.
- Se identificada uma tabela única, grava a permissão de Equip ativando apenas o bit do monstro nos sete terrenos, sem precisar ampliar/deslocar arquivos e sem sobrescrever os dados adicionais de MOD.
- Quando a assinatura não está presente, mantém a escrita na tabela stock original somente se houver espaço. Assinatura de bitmap sem referência MIPS válida bloqueia a geração.
- Diagnóstico Equip lê o formato realmente identificado e reporta o tipo de tabela; manifesto BIN/CUE informa a estratégia usada.
- Botão para reativar adições sem apagar substituições antigas.
- Não há realocação de blocos MIPS genérica nesta versão; os testes de execução no ePSXe continuam necessários.

## v1.2.6 — Troca de alvo de Equip sem aumentar o tamanho (experimental)

- MODs com 0 bytes disponíveis na tabela de equipamentos não podem receber alvos novos pelo formato stock sem realocação MIPS.
- Nova opção **PS1: trocar alvo Equip** seleciona uma permissão existente e a troca por outra, com consentimento explícito e sem alterar o tamanho da tabela.
- A troca modifica somente um u16 de monstro por cópia (7 terrenos); bytes após o terminador e fusões são preservados.
- Modo "substituir" suspende adições antigas sem excluí-las; modo "adicionar" continua disponível.
- O app valida hash de WA da origem antes de listar opções, testa releitura e preserva a ISO original. A compatibilidade no ePSXe ainda não foi confirmada: um MOD pode ignorar a tabela por usar lógica MIPS própria.

## v1.2.5 — Correção do terminador e preservação de dados adicionais Equip

- Corrigido terminador da tabela Equip de 4 bytes para **u16(0), apenas 2 bytes**, como o código original do PS1 verifica.
- Dados não nulos após o terminador são reconhecidos como conteúdo auxiliar do MOD e preservados, sem interpretação ou limpeza.
- Novos alvos são gravados apenas se couberem na sequência de zeros imediatamente após a tabela existente; caso contrário, o Studio bloqueia a exportação e exibe os bytes disponíveis e necessários.
- Após modificar, todas as sete cópias são regravadas, a tabela é relida e dados auxiliares são comparados para impedir perda silenciosa.
- Testes com dados auxiliares sintéticos, buffer insuficiente e preservação das fusões. O motor do MOD Drop X15 ainda precisa de validação no ePSXe; alterar a tabela não garante efeito em jogos com código MIPS personalizado.

## v1.2.4 — Diagnóstico da falha de Equip no PS1

- Novo botão Projeto / Exportação > Diagnosticar Equip no BIN/CUE.
- Releitura independente das sete tabelas Equip da imagem escolhida e comparação com o projeto e com a imagem de origem.
- O relatório distingue "não gravado", "já existia" e "adicionado à tabela". Registra SHA-256 da área Duel_CheckEquip para futura comparação com uma imagem retail.
- Alerta que MODs com rotina Duel_CheckEquip alterada podem ignorar a tabela nativa; não apresenta a compatibilidade como efeito validado em emulador.
- Nenhuma mudança nos valores de ATK/DEF, nas fusões ou no BIN original.

## v1.2.2 — Reutilizar ISOs de teste sem acumular duplicatas

- O BIN de teste passa a ter nome estável derivado do nome do BIN de origem, com sufixo identificador para evitar colisões por caracteres semelhantes e nomes longos.
- Gerar novamente da mesma origem substitui o BIN/CUE de teste anterior; origem com outro nome gera um arquivo separado.
- A cópia anterior permanece intacta até o novo BIN ser gerado, validado e pronto para substituir o destino.
- Se o ePSXe bloquear a imagem, o Studio informa para fechar o jogo e tenta restaurar CUE/manifesto anteriores.
- O BIN original permanece intocado; arquivos antigos gerados com nomes por data não são apagados automaticamente.
- Os efeitos ainda não implementados no motor PS1 continuam pendentes normalmente.

## v1.2.1 — Consolidação e teste de gravação de Equip

- Teste integrado de BIN/CUE sintético confirmou a escrita de alvos de equipamentos no WA_MRG.MRG e a preservação do disco original.
- Interface esclarece quais ações de Equip já podem entrar no PS1 e quais efeitos inéditos continuam somente no simulador.
- Formato seguro mantém as sete cópias de tabela, valida cabeçalhos/padding e recusa estruturas desconhecidas.

## v1.2.0 — Primeira alteração de efeito nativo do PS1: Equip

- Na aba Efeitos, selecione carta Equip original e use **PS1: permitir Equip em criatura**.
- O aplicativo adiciona o monstro selecionado às permissões de equipar daquela carta, mantendo seu bônus original do jogo.
- As sete cópias do bloco de equipamentos em WA_MRG.MRG são regravadas com tamanho fixo, hash de origem, validação de estrutura e preservação das fusões.
- Auras, cemitério, imunidades, dano perfurante, ataques múltiplos e outras habilidades inéditas seguem no simulador; ainda exigem patches MIPS para o ePSXe.
- Não altera a ROM original.

## v1.1.4 — Verificação de ATK/DEF no BIN

- Aba Projeto/Exportação tem botão Verificar BIN/CUE para ler do disco selecionado ATK/DEF e demais atributos das cartas editadas.
- Exibe valores originais, do projeto e do BIN; gera exportacao/verificacao_bin_ps1.json.
- A geração de BIN agora valida os atributos gravados antes de concluir.
- Para ePSXe: carregar o novo arquivo FM_STUDIO_TESTE_*.bin e iniciar sem savestate antigo.

## v1.1.3 — Diagnóstico PS1 sem mudanças compatíveis

- A geração BIN/CUE agora verifica os campos editados antes de abrir a escolha da imagem.
- Quando todas as mudanças são apenas raridade/cor/efeitos ou não cabem no banco original, mostra a contagem de pendências e recomenda um teste de ATK/DEF.
- Salva exportacao/compatibilidade_ps1.json mesmo quando não há modificações graváveis.
- As cartas existentes e os efeitos do projeto não são alterados automaticamente.

## v1.1.1 — fluxo de exportação para ePSXe

- Depois de **Exportar alterações**, o Studio pergunta se deseja gerar a cópia BIN/CUE para teste, evitando confundir a exportação dos dados com a imagem jogável.
- Adicionado botão visível **Gerar jogo BIN/CUE** na barra principal.
- A operação continua exigindo o mesmo disco da importação e mantém o original intacto.
- Não adiciona efeitos MIPS nem cartas novas à versão PS1.

## v1.1.0 — BIN/CUE parcial: atributos, textos curtos e artes
- Novo relatório de compatibilidade por projeto, com recursos de motor pendentes explicitados.
- Grava nomes e descrições que cabem no espaço original e usam glifos/códigos F8 nativos.
- Regrava arte 102×96 e miniatura 40×32 das cartas existentes com paleta original.
- Altera apenas setores ISO9660 conhecidos; EDC/ECC refeito, hashes e releitura verificados.
- Todos os recursos que dependem de MIPS (cartas extras, God, efeitos, novos ícones) permanecem somente no Studio.

## v1.0.2 — Raridades/classes e cores automáticas do nome
- Criaturas: Comum (cinza claro), Incomum (branco), Rara (amarelo), Épica (roxo), Lendária (vermelho), Deus (azul-marinho).
- Magic (verde), Trap (rosa), Equip (azul) e tipo God (azul-marinho) têm cor automática pela categoria.
- Seletor de raridade substitui os botões de cor livre; biblioteca e prévia apresentam a mesma classe.
- Projetos antigos mantêm `cor_nome` legado nos dados, e a nova classe `raridade` é salva com Ctrl+S.
- Para legibilidade do azul-marinho, a classe Deus tem fundo claro na lista e no nome da prévia.
- Metadados exportados em `classes_cartas.json`. Não aplica cores ao executável PS1 nem altera fusões.

## v1.0.1 — Correção do atualizador Python
- Reconhecimento de novos módulos e ícones de fonte, mantendo rejeição de arquivos ROM, traversal e pastas do usuário.
- Script de migração sem ZIP manual compatível com ícones em assets/icons.

## v1.0.0 — Cartas virtuais, God e descrições aprimoradas
- Suporte no editor a IDs a partir de 723 (até 32766 no projeto), sem repack PS1.
- Tipo God (ID 24) no Studio, salvo como metadado; não gravado no executável PS1.
- Seletor de ícones nativos de 16×16 e 9 ícones personalizados em PNG transparente, com paleta reduzida.
- Trechos coloridos em descrições, conversão das cores conhecidas aos códigos F8 em exportação auxiliar.
- Bônus dinâmico por ID de carta com nome resolvido em prévia/descrição, por campo ou deck.
- Projetos antigos, fusões e backups preservados.
- Duelos reais e expansões binárias do PS1 ainda pendentes.

## v0.7.0 — Efeitos contínuos e campo visual
- Aura para todos os aliados face-up do tipo escolhido (+ATK/+DEF).
- Bônus para fonte por quantidade de aliados face-up do tipo escolhido.
- Recalcula na saída/destruição/virada para baixo, soma auras, sem buff persistente.
- Editor de efeitos expandido e simulador visual 5x5; 43 testes unitários locais.
- Fusões originais preservadas; efeitos continuam só no Studio, não no PS1.

## v0.6.2 — GitHub oficial
- Atualizador agora consulta guibatoni/yu-gi-oh-studio-fm.
- Publicador clona o repositório existente e envia apenas arquivos de código, evitando histórico divergente.
- Preparação para Release v0.6.2 e atualização de dependências GitHub Actions.

## v0.6.2 — Correção do botão Atualizar

- Atualizador independente também no modo Python, via `.bat`/`.pyw`.
- Pacotes Source e Windows com SHA256 no GitHub Actions.
- Informa quando o repositório ou Release não existem.
- Preserva `projetos/`, backups, edições, cores e fusões.
- Verifica atualizações em thread secundária, sem travar a interface.

# Histórico de desenvolvimento

## v0.3.0 — Primeiro editor gráfico Windows

- Interface escura em português com biblioteca, filtro e detalhes da carta.
- Importação de `analysis/tabelas` ou diretamente de BIN/CUE/ISO suportados.
- Editor de ATK/DEF, tipo, atributo, nível, estrelas guardiãs, nome e descrição.
- Cadastro de efeitos por gatilho, alvo e ação; simulação local de ATK/DEF e LP.
- Preservação da tabela de fusões em modo somente leitura com hash.
- Exportação JSON e SLUS auxiliar com edição binária de estatísticas verificada.
- Backups rotativos de projeto e validação de integridade.
- Script de início Windows, script PyInstaller e workflow opcional de build.
- Sem imagem de jogo, ROM ou outros dados do jogo no pacote.

**Limites:** não exporta BIN/CUE jogável; efeitos e textos ainda não são gravados no jogo; imagem real X15 ainda não foi executada nesse editor nesta sessão.
- Importação de artes PNG de referência por carta, com prévia no painel do editor; ainda não são gravadas no jogo.

## v0.4.0 — GitHub Releases e atualização no aplicativo

- Novo nome de vitrine: **Yu-Gi-Oh Studio Card FM**.
- Botão `⟳ Atualizar` na barra superior, consultando GitHub Releases em background.
- Atualizador externo Windows com progresso visual, SHA-256 e validação de arquivos ZIP.
- Atualização na mesma pasta, com rollback ao falhar na substituição e preservação dos projetos pessoais.
- GitHub Actions: testes, compilação do editor e auxiliar, publicação de ZIP e checksum por tag.
- `PUBLICAR_GITHUB.bat` / `.ps1` para criar e publicar o repositório usando GitHub CLI.
- Fusões originais continuam protegidas; efeitos ainda são protótipos no simulador.

## v0.5.0 — Extração avançada de conteúdo do disco

- Botão **Extrair máximo** e aba **Dados extraídos** com progresso em segundo plano.
- Recuperação de nomes, descrições, menus e diálogos dos bancos de texto originais.
- Recuperação das artes de cartas, miniaturas, faixas, retratos e prévias de cenas.
- Cruzamento de todos os CSVs existentes com os nomes encontrados para leitura amigável.
- Preservação das edições do usuário em `projeto.json`, backup de `cartas.csv` e verificação da base.
- Índices de proveniência, hashes e avisos da extração; 22 testes de unidade aprovados em dados sintéticos.
- Fusões e rituais originais permanecem somente leitura. Sem execução de efeitos novos no jogo.

## v0.6.0 — Cores personalizadas e salvamento em lote

- Seletor RGB para nome de cartas, com botão para retornar à cor padrão. A cor aparece na prévia e na biblioteca (metadado local, não no PS1).
- Alternância entre cartas sem diálogo de salvar/descartar. Rascunhos conservados na memória inclusive ao navegar por outras cartas.
- Novo botão **Salvar projeto** com `Ctrl+S` e persistência de todas as cartas/efeitos pendentes em um único arquivo e backup.
- Indicador de cartas pendentes; rejeição de valores inválidos preserva rascunhos.
- Compatibilidade com projetos antigos e fusões originais preservadas.
- 28 testes unitários e verificação gráfica sob tela virtual com dados sintéticos.

## v0.8.0 — Decks, encantamentos, alvos e auras genéricas
- Implementado motor de simulação com deck, mão, LP e HP experimental de monstro; equipamentos e efeitos passivos; sem mudanças no PS1.
- Implementado novo laboratório gráfico com campo 5x5, decks e gatilhos explícitos.
- Suporte a qualquer TIPO e escopos aliados, inimigos ou ambos.
- Publicação planejada na tag `studio-v0.8.0` do GitHub oficial; verifique o Release.

## v0.9.0
- Editor de habilidades rápidas por carta e simulação de combate 2x/3x com custo LP e proteção.
- Regra de cópias no deck (até 40 ao todo) e preservação de projetos.

## v1.0.3 — Cemitério, ataque no primeiro turno e teste BIN/CUE

- Novo efeito contínuo `bonus_cemiterio_tipo`: ATK/DEF por carta de tipo selecionado no cemitério, recalculado a cada destruição/remoção ou mudança da pilha, escopos aliados/inimigos/ambos.
- Cemitério separado para cada jogador no Laboratório; botão para aplicar IDs e destruição de monstros envia-os automaticamente à pilha.
- Habilidade rápida `ataque_primeiro_turno` com ícone de bota alada (16×16 indexado). O laboratório diferencia criaturas recém-invocadas de criaturas prontas para atacar; o PS1 ainda não interpreta essa habilidade.
- Primeira construção experimental de **BIN/CUE MODE2/2352** de teste, preservando inteiramente a imagem-base e XA/STR. Substitui somente setores do SLUS de MESMO TAMANHO, recalcula EDC/ECC e lê a cópia para verificar.
- Apenas estatísticas de cartas já existentes e compatíveis com o PS1 são gravadas. Nenhuma modificação ao motor dos efeitos, textos, ícones, God, cartas acima de 722 ou fusões é aplicada.
- Hash SHA-256 da base importada é obrigatório: o disco deve ser exatamente o da importação; nunca sobrescreve a imagem original.
- Rotina CD-ROM Mode2/Form1 baseada na descrição pública de PSX-SPX: https://psx-spx.consoledev.net/dev/ps1/cdr/cdromformat/
- Construção testada com **setores sintéticos**; a compatibilidade do BIN gerado no ePSXe ainda depende de teste com a imagem legítima do usuário.
