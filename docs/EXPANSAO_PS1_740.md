# Cartas nativas #723–#740 — Studio FM 1.9.0

Esta versão implementa uma expansão **experimental** do perfil **Original Drop x15**
cujo SLUS corresponde ao SHA-256 conhecido pelo Studio. O baú passa a ter 740
posições, com **18 IDs adicionais reais**, mantendo as cartas #001–#722.
740 é a capacidade desta implementação compatível com a estrutura existente do
save. Não é uma afirmação sobre o limite absoluto do hardware do PS1.

## Criar e jogar

1. Abra o projeto que usa o BIN/CUE original vinculado e clique em **Nova carta**.
2. Use um ID livre entre **#723 e #740**, escolha o tipo e o **Modelo de
   comportamento / animação no PS1**. A criação já salva a identidade da carta.
3. Edite nome, atributos, descrição, arte e relações. Salve o projeto.
   O modelo pode ser trocado em **Fusões, ritual e equipamentos → Modelo PS1**.
4. Gere um novo **BIN/CUE** a partir da imagem original. O Studio realoca o
   arquivo WA_MRG para um novo extent ISO9660 e atualiza diretório, volume e
   EDC/ECC, conservando as posições dos outros arquivos, XA e vídeos.
5. Use **Verificar BIN/CUE**. A cópia expandida é destinada à execução e à
   verificação; para continuar editando, use **Abrir projeto**, mantendo o BIN
   original como base. O relatório inclui expansão, IDs efetivamente
   criados, capacidade do baú e atributos de cada carta adicional.
6. Abra a cópia no ePSXe. Consulte o **Código PS1** em **Passwords e baú** e
   digite os oito dígitos no Password do jogo. O resgate custa 1 Star Chip.
   Os códigos originais continuam disponíveis. Resgatar no baú do Studio
   continua sendo uma operação separada do save do emulador.

Continue usando o save com a cópia expandida correspondente. Para voltar ao
BIN original, retire antes do deck os IDs adicionais.

Slots ainda não cadastrados mostram **Reservado**, com descrição vazia. Eles
não recebem um password válido. Cartas sem cópias aparecem com **0/0** no baú;
o controle de inventário ainda exige uma cópia para colocar no deck.

## Tipos e comportamentos

| Tipo novo | Implementação nativa |
| --- | --- |
| Monstro, incluindo God | ID, ATK/DEF, nível, atributo, estrelas, nome, descrição e arte próprios; animação/modelo 3D do modelo original escolhido |
| Magia | Encaminhamento para o comportamento original da magia escolhida como modelo |
| Armadilha | Reconhecimento do comportamento herdado nas seleções de traps de ataque, contramedidas e Fake Trap, mantendo a identidade da carta nova |
| Equipamento | Registro de compatibilidade próprio, alvos adicionais, animações herdadas e ramo especial de Megamorph |
| Ritual | Registro próprio com três tributos e resultado, configurável nas relações; sem receita própria, herda a receita do modelo |

As tabelas de equipamentos e rituais são escritas nas sete cópias de terreno.
Se não houver espaço para os registros, a geração é recusada, preservando a
imagem de teste anterior. Receitas antigas de ritual marcadas como suspensas
continuam suspensas; cadastrar um ritual adicional usa o fluxo acima.

Fusões personalizadas e decks **fixos de 40 cartas** dos oponentes aceitam
os novos IDs. Regras de cópias, cores de tier e efeitos já compiláveis também
usam o diretório expandido. O fallback de fusões recusa pares adicionais não
configurados antes de consultar a tabela original de 722 cartas.

## Save e memória

- As quantidades adicionais ocupam os 18 bytes entre o fim das 722 quantidades
  originais e o código do duelista: `save+0x322` até `save+0x334`, exclusivo.
  O deck continua com 40 IDs de 16 bits e o estado persistente com `0x680` bytes.
- Esses bytes já fazem parte do checksum primário e da cópia duplicada do save.
  Código do duelista, nome, campanha, LP e Star Chips não são deslocados.
- Os dois painéis do deckbuilder, contadores, cursores e sete modos de ordenação
  usam as dimensões novas; o workspace de cada painel passa a `0x65BC` bytes.
- Estatísticas e chaves de ordenação são realocadas. Nível/atributo usam uma
  tabela separada para preservar a área de trabalho do Password em `0x801D5608`.
- A marcação de cartas vistas da Library original não grava os IDs adicionais
  sobre flags de passwords. O resgate extra também preserva os bits que se
  sobreporiam a flags da campanha.

## Limites explícitos

- **#741 em diante continuam no Studio**, com criação, persistência, receitas e
  simulação. Não são IDs nativos desta expansão.
- Os valores nativos continuam sendo **0–5110, em múltiplos de 10**, para ATK/DEF,
  nível de 0–15 e estrelas de quatro bits. Desde a v1.9.1, o perfil Drop x15
  usa o código nativo reservado 11 para Supreme e mantém o ID 16 no projeto.
  O BIN recebe o ícone, nome e regra de +700 contra estrelas originais.
  Valores maiores são preservados no projeto e impedem a exportação nativa
  daquela configuração, sem truncamento silencioso.
- Nomes usam a fonte do PS1 e o espaço disponível no banco. O gerador simplifica
  acentos compatíveis; nomes que não cabem produzem uma mensagem de erro.
  O título gráfico é recomposto em uma faixa nativa 96×14 de 4 bits por pixel.
  Artes e miniaturas usam as paletas do modelo, como na edição de artes existente.
- A **Library/álbum separado** do jogo continua com 722 entradas; consulte os
  IDs novos no baú e com Triângulo. Não foi ampliada a sua tabela de flags.
- **Pools ponderados de oponentes, pools iniciais e drops PS1 continuam com a
  estrutura original de 722 cartas**. O exportador informa configurações com
  IDs adicionais que essas tabelas não suportam. Não converte IDs novos em
  IDs originais para mascarar essa limitação.
- O modelo fornece comportamento existente. Efeitos inéditos continuam
  sujeitos à auditoria de compatibilidade. Não houve reescrita da seleção de
  magias/rituais da IA para todos os novos comportamentos nesta etapa.

## Validação

Além dos testes unitários e de interface, as regressões em Unicorn executam as
instruções MIPS do compilador: limites de cópias, fusões, dano de invocação,
traps, modelos, equipamentos, transferências e proteção das flags de Password.

Na imagem de origem fornecida foram geradas cartas de todos os cinco tipos,
incluindo #723 e #740, God, ícone na descrição e PNG próprio. A releitura do BIN
confirmou atributos, tabelas e recursos. Também foram executadas as rotinas reais
do SLUS para inicializar os 740 registros do baú, ordenar nas sete modalidades,
gravar a última quantidade, conceder uma cópia e validar os três checksums e a
duplicação do save. Alterar a quantidade de #740 depois de selar o save invalida
o checksum. Seleção de trap, compatibilidade de equip e checagem de ritual foram
executadas com os IDs adicionais. Chamadas gráficas/áudio são isoladas nesses
testes; eles não substituem uma partida completa no ePSXe.

A regressão nativa do baú/save também pode ser repetida com
`PYTHONPATH=. python tools/verify_expanded_bau_mips.py CAMINHO_DO_JOGO.bin`
(com Unicorn instalado). O comando usa a cópia expandida em RAM isolada.

**Ainda não validado por execução completa no ePSXe.** O manifesto registra
`validado_epsxe: false`. A imagem original permanece somente leitura e o último
BIN de teste só é substituído após a validação integral do arquivo novo.

Backup anterior: `backup/studio-v1.8.15-before-ps1-expansion`.
Também foi mantida a referência inicial `backup/studio-v1.8.8-before-ps1-expansion`.
