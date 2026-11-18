# Studio FM v1.9.2 — Descrições das cartas novas no PS1

Ao gerar o BIN/CUE do **Original Drop x15**, o Studio ajusta as quebras de
linha de textos que excedem a altura do visor. O banco de descrições usa
os intervalos livres entre as rotinas nativas e compartilha textos
idênticos. Os IDs ainda sem carta usam o texto vazio de origem.

O visor PS1 continua limitado a 9 linhas de 21 colunas. Quando o texto
completo não cabe, a opção **Gerar o BIN/CUE com as descrições compatíveis**
grava uma prévia com reticências nas cartas novas quando há espaço. Para
uma carta nova sem prévia possível, a cópia exibe a descrição vazia. As
cartas originais incompatíveis mantêm o texto de origem. Os textos completos
continuam no projeto. **Conferir descrições no BIN/CUE** indica o que foi
gravado e quais cartas usam prévia ou estão sem descrição na cópia.

---

# Studio FM v1.9.1 — Supreme no PS1

O botão **Gerar jogo BIN/CUE** aceita Supreme nos dois campos de Guardian Star
de cartas originais e das novas **#723–#740**. No **Original Drop x15** reconhecido
pelo Studio, o BIN recebe nome, ícone e bônus de **+700** em ATK/DEF no confronto
com as dez estrelas originais. Supreme contra Supreme tem bônus zero. O
projeto mantém a seleção existente e **Verificar BIN/CUE** confirma a gravação.

A extensão PS1 é experimental. A geração da imagem e as rotinas MIPS foram
conferidas, com validação de partida completa no ePSXe pendente.

---

# Studio FM v1.9.0 — Expansão PS1 experimental até #740

O **Original Drop x15** pode receber **18 cartas adicionais reais**, com IDs
**#723–#740**. O baú usa 740 posições, mantém as quantidades no save existente
e aceita novos monstros, magias, traps, equips e rituais com modelos de
comportamento originais.

Em **Nova carta**, escolha o tipo e o **Modelo de comportamento / animação
no PS1**. Salve e gere um novo **BIN/CUE** da imagem original. A seção
**Passwords e baú** mostra o código PS1 para obter a carta no jogo por 1 Star Chip.
Use **Verificar BIN/CUE** para conferir os IDs e os atributos aplicados.

A expansão foi testada por releitura da imagem e execução de rotinas MIPS;
a partida completa no ePSXe ainda precisa ser validada. #741+ segue no Studio.
Pools ponderados/drops e o álbum Library do PS1 conservam 722 entradas.

Detalhes e limites: [Expansão PS1 #723–#740](docs/EXPANSAO_PS1_740.md).
As seções seguintes registram recursos e limitações das versões anteriores.

---

# Studio FM v1.8.15 — Conferir descrições gravadas no BIN/CUE

Na aba **Cartas**, use **Conferir descrições no BIN/CUE** após salvar
as alterações. Escolha a imagem realmente carregada no ePSXe. O Studio
lê o SLUS dentro dessa imagem e compara os bytes da descrição da carta
com o texto do projeto, indicando aplicado, ainda original, divergente
ou incompatível. Também gera o relatório local
`exportacao/diagnostico_descricoes_ps1.json`, com ID, ponteiro e SHA-256
dos textos conferidos. A verificação é somente leitura e não altera
seu BIN ou o projeto.

ATENÇÃO: a confirmação de bytes não garante que a tela de informações
esteja acessível no emulador ou no MOD. Descrições acima do ID 722
continuam apenas no Studio. Ícones personalizados sem suporte no PS1
não são inseridos no jogo.

---

# Studio FM v1.8.14 — Exportação BIN/CUE com descrição incompatível

Se alguma descrição editada ultrapassar a capacidade do executável PS1 (9 linhas de 21 colunas, slot original), usar caractere indisponível na fonte ou um ícone sem extensão MIPS, o Studio continua avisando antes de alterar o BIN. Agora é possível escolher **Gerar mantendo as descrições originais do PS1 apenas nas cartas incompatíveis**, sem descartar as edições no projeto. Descrições compatíveis continuam sendo escritas, e o manifesto JSON ao lado do BIN lista todas as falhas em `descricoes_nao_gravadas` e a política aplicada. O modo padrão segue rigoroso; sem consentimento nada será substituído.

**Observação:** esta alternativa não habilita os ícones novos nem aumenta o espaço da tela PS1. Para que uma descrição extensa apareça no jogo, ela precisa caber na fonte/tela/slot ou haver extensão comprovadamente compatível. A solução permite gerar o BIN/CUE para testar decks, efeitos e outras edições sem perder o texto salvo no Studio.

---

# Studio FM v1.8.13 — Geração de campanha difícil

Em **Edição do Mod → Deck do oponente**, selecione **Gerar Decks Difíceis (3/5 → 5/5)** para construir todos os 39 decks ou regenerar somente o adversário selecionado. A dificuldade sobe de 3,0 a 5,0; o cabeçalho e o seletor exibem o nível e o foco de efeito. A IA recebe decks baseados nas cartas e efeitos *existentes*, rotas de fusão encadeadas (até três etapas), materiais com 1500 ATK/DEF base no máximo, equips realmente compatíveis e pools ponderadas com total 2048.

**Compatibilidade:** o modo PS1 usa apenas IDs até 720 nos pools de deck (limite de leitura retail); com limites de cópias 1–2, o gerador converte a lista em deck fixo para o perfil Drop x15, guardando os pesos sugeridos nos metadados. A opção de cartas **#723+** é exclusiva do simulador Studio e não significa que o motor PS1 poderá executá-las. Efeitos inéditos do Studio também dependem do suporte específico do motor PS1 e podem não funcionar no ePSXe. Quando não houver fusões 3000+ viáveis ou monstros com efeito suficientes na ISO, o gerador apresenta aviso e não inventa conteúdo.

A geração valida todos os decks antes de gravar, pede confirmação, mantém os drops e todas as demais configurações, e usa a rotina de backup existente no projeto. Para instalações Windows, o GitHub Actions gera o executável e publica o release.

---

# Studio FM v1.8.12 — 39 decks ponderados de oponentes

Na aba **Edição do Mod → Deck do oponente**, use **Aplicar 39 decks (3/5–5/5)** para instalar as 39 pools ponderadas (40 compras, 2048 pontos cada). A aplicação exige confirmação e mantém outros ajustes do projeto. Os materiais de fusão respeitam o limite base de 1500 ATK/DEF; fusões e equipamentos podem superá-lo. O botão não altera o projeto até o usuário confirmar. Faça backup antes de aplicar; dados de cartas customizadas, receitas e drops que não dependem do deck continuam preservados.

---

# Studio FM v1.8.11 — Conferência de descrições no jogo

As descrições salvas no projeto somente são gravadas no PlayStation ao usar
**Gerar jogo BIN/CUE**. O novo processo não ignora silenciosamente descrições
que não cabem no mod: lista as cartas e o motivo da incompatibilidade,
preservando a última cópia BIN/CUE. Descrições escritas são conferidas pelos
ponteiros de texto na imagem gerada. Cartas com IDs acima de 722 permanecem
apenas no Studio enquanto não houver suporte nativo no motor PS1.

Se o jogo continuar com texto antigo, carregue no ePSXe a cópia BIN/CUE
gerada na pasta do projeto (não o arquivo original). Alguns mods somente
aceitam textos curtos porque não têm o banco de realocação do Drop x15.

---

# Studio FM v1.8.10 — Efeitos de vida e editor de descrições

Esta atualização reúne o Vínculo com Vida (no simulador), a seleção de carta
específica para bônus por deck, os ícones de coração e espada/coração na prévia,
e o editor de descrição com altura ajustável, rolagem própria e janela de
ícones redimensionável. Os dois ícones novos e o efeito Vínculo com Vida ainda
não são exportáveis para o motor PS1; a exportação preserva essa limitação.

---

# Studio FM v1.8.9 — Vínculo com Vida e seleção de carta no deck

No Studio, em **Cartas → Efeitos e bônus → Adicionar efeito**, escolha
**Ao atacar → ⚔♥ Vínculo com Vida**. Ao declarar um ataque, o controlador
recupera LP equivalentes ao ATK efetivo (incluindo bônus). Isso também
funciona contra monstros em defesa; a cura pode coexistir com custos de LP.
O campo de valor é automático e não exige digitação.

**♥ Recuperar LP** facilita a identificação do efeito de restauração.
Para **Enquanto no campo → Recebe bônus por cartas no deck**, clique
**Escolher carta específica do deck…** para selecionar ID ou nome;
o bônus considera cada cópia exata daquela carta na composição inicial.

**Compatibilidade:** Vínculo com Vida funciona no simulador do Studio.
O patch de runtime do PS1 ainda não implementa essa habilidade; gerar BIN/CUE
não ativará a cura por ataque no ePSXe. A interface deve indicar essa limitação.

---

# Studio FM v1.8.8 — Catálogo completo no baú

Abra **Passwords e baú → Baú** para consultar todas as cartas do projeto,
inclusive as personalizadas. A lista mostra **0/0** quando você ainda não
tem nenhuma cópia, e pode ser ordenada pela quantidade no baú.

Ao gerar um novo **BIN/CUE** do **Drop x15**, a tela **Montar deck** passa
a mostrar as 722 cartas. Os contadores do baú e do deck mostram zero
para as cartas ainda ausentes da coleção. Use **Triângulo** para ver a ficha.

---

# Studio FM v1.8.6 — Bônus por tipo ou atributo

Em **Cartas → Efeitos e bônus**, configure **Tipo**, **Atributo** e **Combinar
filtros** para as auras, os bônus por contagem e os marcadores de entrada.
Para usar só o atributo, deixe **Tipo** em **Todos os tipos**. Com os dois
selecionados, **Tipo ou atributo** aceita qualquer um dos filtros e conta
cada carta uma vez. **Tipo e atributo** exige os dois.

Para jogar com os novos filtros no **Drop x15**, salve o projeto e gere um
novo **BIN/CUE**. Os bônus por cartas na mão funcionam no simulador do Studio.

---

# Studio FM v1.8.5 — Marcadores de entrada

Em **Cartas → Efeitos e bônus → Adicionar efeito**, escolha uma das ações.

- **Acumular ATK/DEF quando o tipo entra** soma o valor à carta a cada entrada
  de um monstro do tipo escolhido. O bônus permanece até a carta sair do campo.
- **Ao entrar, reduzir ATK/DEF por tipo** subtrai o valor de cada monstro do tipo
  nos campos escolhidos. A redução dura até cada alvo sair do campo. Um alvo
  afetado é destruído se o ATK e a DEF efetivos ficarem em zero.

Escolha o tipo e os lados que participam. Deixe a DEF em branco para repetir
o valor do ATK. A colocação virada para baixo também conta. Para jogar no
PlayStation, salve o projeto e gere um novo **BIN/CUE** do Drop x15 compatível.

---

# Studio FM v1.8.3 — Rank no HUD do PlayStation

Em duelos contra o computador no **Drop x15**, a projeção aparece abaixo
dos LP do jogador no formato **S-POW 99**. O contador usa as ações e a
tabela de pontuação do próprio jogo.

Atualize o Studio e gere outro **BIN/CUE** a partir da imagem original.
Abra a nova cópia no ePSXe e inicie um duelo novo. **Verificar BIN/CUE**
confirma que a rotina foi gravada na imagem selecionada.

---

# Studio FM v1.8.0 — Rank, banlist e decks temáticos

- Em **Cartas → Habilidades rápidas**, defina o **Limite de cópias no deck**.
  Digite **0** para banir, **1–40** para um limite individual ou deixe vazio
  para herdar o padrão. Salve o projeto para aplicar a regra.
- Em **Edição do Mod → Gerar Deck Aleatório**, aplique o tema do duelista ou
  escolha o máximo de ATK/DEF e a composição. O teto vale para cartas base.
  Nos decks iniciais, **Sortear trio inicial** combina três tipos por suas
  fusões dentro do máximo original de 2.450 ATK + DEF por monstro.
- No simulador, a HUD mostra o rank projetado abaixo dos LP. Ao vencer,
  **Receber recompensa** usa o rank conquistado e os pesos do grupo ou rank.
- Em **Drops do oponente**, cole IDs separados por vírgula e aplique um
  peso ao lote. Dê duplo clique em **Peso** ou **Chance** e pressione Enter.
  Ao digitar uma porcentagem, o editor conserva a proporção entre os demais
  pesos. Os cabeçalhos alternam ordem ascendente e descendente.

O rank ao vivo, a IA Expert, a Supreme e as cartas #723 em diante funcionam
no simulador. Veja as regras aplicáveis ao [BIN/CUE](docs/COMPAT_PS1.md).

---

# Studio FM v1.7.2 — Fusões personalizadas no Drop x15

As fusões salvas em **Relações → Fusões** vão para o próximo BIN/CUE do
Drop x15 quando os materiais e o resultado usam os IDs originais #001–#722.
O jogo resolve a combinação com os materiais em qualquer ordem,
e a IA também consulta a receita. Use **Verificar BIN/CUE** para conferir
as fusões gravadas na cópia.

---

# Studio FM v1.7.1 — Decks fixos no Drop x15 e nomes por tier

Em **Edição do Mod → Deck do oponente**, escolha o duelista e salve **40/40**
cartas fixas. **Cópias a inserir** controla as cópias adicionadas a cada
clique. Gere o BIN/CUE a partir do Drop x15 original e confira os duelistas
aplicados pelo botão **Verificar BIN/CUE**.

Com **Dropar Cartas do Próprio Deck** ativo, o sorteio usa a composição
carregada no começo do duelo. As cópias já compradas ou descartadas
continuam no conjunto de recompensas.

Defina a raridade no editor da carta para colorir seu nome nas listas do
Studio e no visualizador de cartas do Drop x15. Magias, armadilhas,
equipamentos e God usam suas cores de tipo.

---

# Studio FM v1.7.0 — Cartas, decks e recompensas

Crie e salve uma carta com ID livre em **Nova carta**. Em **Edição do Mod →
Deck do oponente**, busque a carta pelo ID, nome ou tipo, ajuste as cópias e
salve. Use **Novo deck fixo** para começar uma lista manual ou **Gerar Deck
Aleatório** para montar uma composição por tipo.

Abra **Passwords e baú** durante o duelo do Studio para resgatar um código de
oito dígitos ou escolher uma carta pelo ID, inclusive cartas God e IDs acima
de 722. Para jogar com a carta na próxima partida, marque **Adicionar também
ao deck inicial** e escolha um perfil.

Em **Drops do oponente**, **Dropar Cartas do Próprio Deck** usa as cartas que
entraram no baralho do adversário naquela partida. Cada cópia tem uma chance
no sorteio e a recompensa da vitória vai para o baú.

No **Drop x15**, use **Ativar passwords por ID no BIN/CUE Drop x15** após
carregar a tabela de códigos originais. Gere o BIN/CUE e use os oito dígitos
da coluna **Código PS1** na tela de passwords. O resgate custa 1 Star Chip
e segue as regras originais de compra. Os IDs disponíveis no BIN/CUE são
#001–#722. As cartas adicionais usam o simulador do Studio.

---

# Studio FM v1.6.1 — Ataque no primeiro turno

No turno de abertura, só monstros com **Ataca no 1º turno** podem atacar.
Em uma fusão, vale a habilidade da carta resultante. Os turnos seguintes
usam as regras normais de combate. Gere outro BIN/CUE do Drop x15 a
partir da imagem original para aplicar a regra no PS1.

---

# Studio FM v1.6.0 — Passwords e geração de decks

Na aba **Edição do Mod**, abra **Passwords de Cartas** para buscar os códigos
originais de oito dígitos ou usar um código por ID, como `FM-00000723`, no Studio.
A leitura de um BIN/CUE vinculado recupera a tabela para projetos mais antigos.

Use **Gerar Deck Aleatório** em **Decks de oponentes** ou **Decks iniciais**.
Distribua as 40 vagas nas abas **Composição** e **Tipos de Monstro**.
O limite de ATK/DEF afeta as cartas incluídas no deck. As fusões podem levar
a monstros mais fortes. A prévia mostra as combinações encontradas e permite
enviar a composição ao editor. Os decks fixos gerados são usados nas partidas
do Studio.

As auras incluem monstros virados para baixo. Bônus de ATK/DEF por deck usam
a composição inicial, desde a primeira compra. No Drop x15, o dano direto de
entrada em campo e essas regras de bônus são gravados para monstros originais
dentro dos limites do PS1.

---

# Studio FM v1.5.1 — God 24 na seleção de tipo

Em **Cartas**, escolha **24 — God** no campo **Tipo** e salve o
projeto. Ao gerar o BIN/CUE a partir do Drop x15, o Studio inclui
automaticamente o nome, o ícone e o suporte de monstro em duelo.
Para voltar ao tipo original do Time Wizard, selecione **01 — Spellcaster**,
salve e gere outra cópia do jogo.

---

# Studio FM v1.5.0 — Partidas contra IA e Edição do Mod

Em **Edição do Mod**, selecione um duelista para editar drops por rank,
deck ou pools e LP inicial. Em **Decks iniciais** você pode montar
perfis fixos, combinar cartas fixas com sorteios ponderados ou editar
os pools lidos da imagem. Use **Simular duelo** para jogar com essas
configurações. Projetos antigos podem carregar os pools iniciais com
**Ler pools do BIN/CUE** na mesma aba.

**Cartas** tem filtros por tipo, Guardian Star e faixa de ID.
**Nova carta** usa o primeiro ID livre acima de 722. A estrela
✦ **Supreme** dá +700 de ATK e DEF no combate contra qualquer uma das
dez estrelas originais. Os atributos na mão, no campo e no monte
acompanham as mudanças nas zonas. LP, ATK e DEF usam inteiros sem
teto fixo no Studio.

Para jogar no ePSXe, exporte a cópia a partir do Drop x15 original.
O relatório da geração mostra quais regras cabem nas tabelas do
console. Veja [compatibilidade do BIN/CUE](docs/COMPAT_PS1.md).

---

# Studio FM v1.4.26 — Exportação de ícones sem Pillow

A geração de BIN/CUE com ícones de descrição funciona no modo Python
com as bibliotecas padrão. Atualize o Studio e gere novamente a cópia
a partir da imagem original usada no projeto.

---

# Studio FM v1.4.25 — Efeitos de duelo e descrições no PS1

No **Yu-Gi-Oh! FM Original (Drop x15)**, o Studio grava as habilidades
compatíveis ao gerar o BIN/CUE do projeto. Os ataques 2x/3x, as
proteções, as auras, os bônus de ATK/DEF e os limites por carta passam
a ser lidos pelo jogo. O limite por carta pode ser de 1 a 40 cópias
e o deck tem 40 espaços.

O editor de descrição exporta as sete cores do jogo e os dez ícones
do Studio. A tela de detalhes aberta com **Triângulo** comporta até
nove linhas de 21 colunas. Letras acentuadas ausentes na fonte do
PS1 são simplificadas na cópia e anotadas no relatório de geração.

Abra o projeto, salve as edições e selecione **Gerar jogo BIN/CUE**.
Escolha a imagem original usada para importar o projeto. Abra a cópia
gerada e comece um duelo novo. O relatório indica as rotinas conferidas
e as ações que ainda dependem de implementação. Veja
[Compatibilidade PS1](docs/COMPAT_PS1.md).

---

# Studio FM v1.4.24 — Nome e ícone do tipo God no PS1

As cartas de tipo 24 mostram o ícone dourado do Studio na lista do baú
e do deck. A tela de detalhes, acessível com **Triângulo** no baú, no deck
e no duelo, mostra o ícone ao lado do nome **God**.
O tipo numérico 24 continua a usar a fileira de monstros quando a opção
**PS1: God24 em duelo (teste)** está ativa. Marte continua disponível como
estrela guardiã com seu nome e símbolo originais.

O projeto que já usava God24 no baú recebe a exibição ao gerar uma nova
cópia BIN/CUE a partir da imagem Drop x15 usada na importação. Para novos
testes, use **PS1: Tipo God no baú (teste)** na carta salva com tipo 24.
**Verificar BIN/CUE** confere o nome e a textura na imagem gerada.

---

# Studio FM v1.4.23 — God24 na fileira de monstros (teste)

A seleção da fileira ainda usava o limite dos tipos originais. Se o
God24 fosse baixado virado para baixo, essa rotina podia colocá-lo na
fileira de magias e armadilhas. Agora o tipo 24 passa pela mesma regra de
colocação dos monstros nas duas posições da carta.

O painel de atributos da mesa e a tela ampliada também passam a usar
o layout de monstro para God24. A carta mantém o tipo 24 gravado no BIN.

Com **PS1: God24 em duelo (teste)** ativo, gere outra cópia usando o
Drop x15 original do projeto. **Verificar BIN/CUE** deve confirmar
18/18 pontos, incluindo **fileira de monstros 1/1**. Abra a nova cópia
e comece um duelo no ePSXe para conferir a colocação.

---

# Studio FM v1.4.22 — God24 da mão ao campo (teste)

**PS1: God24 em duelo (teste)** prepara o tipo 24 para seguir o caminho de
monstro na mão, na colocação e na confirmação da estrela guardiã. A
configuração de teste da mão já salva no projeto vale para esta versão.

Gere uma nova cópia BIN/CUE a partir do Drop x15 usado na importação.
Em **Verificar BIN/CUE**, confira mão **4/4**, colocação **7/7** e confirmação
**2/2**. Abra a cópia em um duelo novo no ePSXe e teste jogar a carta,
escolher a estrela guardiã e atacar depois que o jogo permitir.

A cópia mantém o tipo 24 e os atributos gravados de cada carta. As
comparações do duelo preservam o número dos tipos originais e os desvios
de Magia, Armadilha, Ritual e Equip. A versão continua experimental até
validar a jogada inteira no ePSXe. Ícone de tipo e efeitos inéditos
seguem pendentes.

---

# Studio FM v1.4.21 — Correção do erro "God24 mão: janela MIPS"

Na v1.4.20, os quatro offsets do patch da mão estavam **0x800 bytes
antes das instruções reais**, por falta do deslocamento do cabeçalho
PS-X EXE no mapeamento RAM -> SLUS. A proteção de cinco opcodes
bloqueava a geração corretamente em vez de modificar endereços errados.

Corrigidos os offsets, confrontados com o relatório enviado:
- RAM 0x8001C214 -> SLUS 0xCA14;
- RAM 0x8001C400 -> SLUS 0xCC00;
- RAM 0x8001C9FC -> SLUS 0xD1FC;
- RAM 0x8001CD34 -> SLUS 0xD534.

O executável de origem continua exigindo SHA e cinco opcodes exatos
em cada ponto. O Studio agora informa o endereço e o opcode divergente
se a verificação recusar outro MOD ou uma imagem já modificada.
Foram adicionados testes dos quatro endereços com EXE_DELTA, de
preservação dos antigos endereços incorretos e da cadeia completa
de patch do baú -> renderizador -> seleção da mão.

**Atenção:** a correção restaura a geração experimental do BIN,
não comprova a invocação. O teste altera temporariamente valores
8–15 no registrador da mão, apesar de conservar sua classificação
como monstros. O símbolo Deus e o caminho de colocação/combate
continuam sem validação no ePSXe. Teste em cópia do jogo e
reinicie sem save state antigo.

---

# Studio FM v1.4.20 — God24 na mão do duelo (TESTE EXPERIMENTAL)

O diagnóstico do usuário identificou quatro máscaras `0x1F` seguidas
de comparação com 20 em DuelScene_UpdateHandActions, nos offsets
0xC214, 0xC400, 0xC9FC e 0xCD34 do SLUS original validado.

Foi incluído o botão opcional **PS1: God24 na mão (teste)**. Ative
primeiro **PS1: ATK/DEF God no baú (teste)**. A gravação exige SHA-256
exato do SLUS e cinco opcodes de contexto por instrução; converte
somente o operando imediato das quatro instruções ANDI de `0x1F`
para `0x17`, sem tocar em saltos, tabelas ou delay slots.

Este filtro preserva a CLASSIFICAÇÃO dos tipos 0–23: 0–19 continuam
monstros e 20–23 mantêm suas categorias especiais. Dentro da rotina
da mão, a operação ANDI também normaliza temporariamente os valores
8–15 para 0–7; não altera o tipo gravado na carta, mas requer testes de
possíveis efeitos colaterais. God24 vira tipo local 16 para as decisões
da mão, permanecendo tipo 24 no BIN. Por precaução, tipos 25–31 são
recusados e a função é opt-in.

O gerador reabre o BIN/CUE final e exige a presença das quatro
instruções antes de substituir a cópia anterior. O verificador
indica `aplicado_4_de_4` e seus opcodes.

**ATENÇÃO**: É apenas um teste de roteamento na mão! Não foi
validado no ePSXe; DuelScene_UpdateCardPlacement ainda contém
sete comparações <20 e o motor pode continuar rejeitando God24
ao invocar/atacar. O símbolo de Deus e o combate continuam
pendentes, sem regressões intencionais dos tipos originais.

---

# Studio FM v1.4.19 — God24 tratado como magia no duelo

O teste no ePSXe confirmou que o tipo God (24) agora exibe ATK/DEF no
baú, mas ainda é tratado como carta especial quando usado na mão. A
correção de renderização v1.4.18 não alterou o motor do duelo.

O novo módulo ps1_god24_duel.py investiga cinco regiões do executável:
DuelScene_UpdateHandActions, DuelScene_UpdateCardUse,
DuelScene_UpdateCardPlacement, DuelScene_UpdateFieldActions e
Duel_SetupCardRecord. O relatório Efeitos > Diagnosticar motor MIPS
agora inclui a seção diagnostico_god24_fluxo_duelo com endereços,
instruções, branches e seu contexto para cada rotina, até 48
amostras por região. Nenhuma alteração é gravada por essa análise.

O objetivo técnico é manter os tipos 00–19 como monstros, 20–23
como Magia/Equip/Armadilha/Ritual e permitir SOMENTE God24 como
monstro adicional na mão, campo e batalha. A alteração do limite
20 diretamente para 25 não é segura. O patch de jogabilidade ainda
não foi implantado e requer validação dos opcodes reais do mod.

Referência:
https://github.com/Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled

---

# Studio FM v1.4.18 — God24 na lista real do baú (teste experimental)

O diagnóstico do usuário confirmou que as duas máscaras antigas estavam
presentes no BIN, mas a função func_80031874 ainda escondia ATK/DEF do
Time Wizard tipo 24. A opção de teste do baú agora inclui um patch de
três instruções nessa rotina, nos offsets 0x222F8, 0x22304 e 0x2230C.

A sequência usa o registrador temporário $at e respeita o load delay
do processador MIPS R3000A. Mantém o store de posição do sprite,
branch e branch delay inalterados. O resultado lógico deve mostrar
ATK/DEF dos tipos 0–19 e 24, sem mudar a classificação dos tipos 20–23.
Tipos 25–31 continuam proibidos neste experimento.

O patch exige SHA-256 idêntico ao SLUS importado e sequência exata
de 11 opcodes; modifica apenas três palavras no executável copiado.
O BIN é relido antes de substituir a última imagem: exige as duas
máscaras originais e as três instruções novas. O verificador informa
aplicado_3_de_3, ausente, parcial ou divergente.

ATENÇÃO: não é validação no ePSXe. É um patch experimental da tela
do baú, sem ícone próprio e sem mudanças nas regras de invocação,
fusões ou combate. A imagem original permanece intacta.

---

# Studio FM v1.4.17 — Investigar renderizador REAL do baú

Após as capturas de God24 sem ATK/DEF, identificamos a causa da
falha de cobertura das máscaras anteriores. A tela de lista do baú
é desenhada pela função PS1 \`func_80031874\`, região de 0x460 bytes
no SLUS. Ela verifica \`row[2] < 20\` antes de desenhar os atributos.
A v1.4.15 modificava outras funções de apresentação (0x51500 e
0x51728), que não corrigem esse renderizador.

O comando **Verificar BIN/CUE** agora acrescenta ao relatório
\`god24_renderizador_lista_bau\`: SHA da região, candidatos de
SLTI/SLTIU 20, instruções LBU, branches, delay slots e offsets
SLUS. Isso diferencia a função real do histórico de dois patches.
O diagnóstico examina o SLUS extraído da imagem escolhida e não
grava nenhum código ou textura.

**Nenhum patch de tipo foi instalado em func_80031874 nesta versão.**
Não é seguro trocar o limiar de 20 para 25: isso converteria Magic,
Trap, Equip e Ritual em monstros. É necessária a condição específica
\`tipo<20 OU tipo==24\` com opcodes/cave e compatibilidade validados.
O ícone God24 e os caminhos de duelo continuam pendentes.

---

# Studio FM v1.4.16 — Auditar o BIN real antes de outro patch God24

Após a captura do baú sem ATK/DEF, não é possível confirmar apenas
pela imagem se o usuário executou um BIN que contém o patch da v1.4.15.

O comando **Projeto / Exportação > Verificar BIN/CUE** agora faz
readback do SLUS da imagem selecionada e identifica o estado exato de
duas instruções MIPS, nos offsets 0x51500 e 0x51728:
`aplicado_2_de_2`, `nao_aplicado_0_de_2`, `parcial_1_de_2`
ou `opcodes_desconhecidos`. Mostra também tipo, ATK e DEF
da carta marcada para teste, e salva `verificacao_bin_ps1.json`.

O botão **Gerar jogo BIN/CUE** oferece confirmação para ligar
o teste experimental do baú quando a carta for God24 e o usuário
esquecer de ativá-lo. A mensagem final informa se as duas máscaras
foram aplicadas, e a releitura aborta a substituição do último BIN
caso haja diferença entre solicitado e gravado.

**Nenhum hook MIPS novo**: esta versão investiga se o jogo recebeu
a modificação da v1.4.15. Se o arquivo contém 2/2 máscaras e
ATK/DEF corretos mas o ePSXe permanece sem poder, ainda existem
rotinas de exibição ou caminhos de execução a localizar. O ícone
God24 e as regras de batalha continuam pendentes.

---

# Studio FM v1.4.15 — God24 ATK/DEF no baú (teste opcional)

Primeiro patch MIPS do God24 aplicado à CÓPIA do SLUS: a opção
**PS1: ATK/DEF God no baú (teste)**, na aba Cartas, modifica apenas duas
instruções ANDI: 0x51500 e 0x51728. A máscara muda de 0x1F para 0x17
antes da comparação SLTI com 20. Assim o tipo 24 passa na verificação
visual de monstro, mantendo classes 0–23 idênticas. O tipo original
da tabela continua sendo 24. O patch exige SHA exato do executável
de origem, assinaturas de cinco opcodes em cada posição e recusa
qualquer mod com tipos 25–31. A releitura prova que só duas palavras
MIPS foram alteradas. Não altera branches, delay slots nem cave.

**Não é o patch de jogabilidade**: invocação, ataques, efeitos,
ícone do tipo e outras telas continuam pendentes. A exibição
de ATK/DEF no baú precisa de confirmação no ePSXe. A imagem
BIN original permanece intacta.

---

# Studio FM v1.4.14 — Diagnóstico de God24 como monstro real

Identificamos por que Time Wizard #016, definido como God (24), aparece
sem ATK/DEF e sem ícone no baú do ePSXe:

- O motor PS1 original considera monstros somente os tipos **0–19**.
- A rotina \`CardList_RenderDeckBoxStats\`, RAM \`0x80060B38\`, oculta
  os valores numéricos de cartas de tipo maior ou igual a 20.
- Outros caminhos de classificação e invocação também precisam de
  suporte a God24, senão um ícone isolado não resolve o duelo.
- O protótipo de glifo anterior escreve somente na **descrição**,
  não no campo de tipo; não há hook MIPS nativo instalado para isso.

O botão **Efeitos → Diagnosticar motor MIPS** agora inclui
\`diagnostico_god24_classe_monstro\` (perfil 4) no JSON exportado.
A análise examina oito janelas de referência do executável (baú,
classificação, registro de duelo, terreno, colocação e ações de campo,
ícone de carta e ícone de texto), calcula hashes e procura comparações
MIPS do limiar 20, incluindo endereços e contexto ao redor.
A presença de opcodes com imediato 20 não valida a segurança de um
patch; pode haver caminhos indiretos e dados que se parecem com código.

**Não aplicar** uma mudança simples \`tipo < 25\`: isso incluiria
Magia/Armadilha/Ritual/Equip como monstros e quebraria o jogo.
Um patch correto exige \`tipo < 20 OU tipo == 24\` em cada
caminho relevante e um sprite exclusivo, com espaço de código e
ABI verificados no SLUS importado.

A geração experimental do valor 24 permanece opt-in e avisa explicitamente
que ATK/DEF podem ficar ocultos e a invocação pode falhar.
A nova versão é uma etapa real de diagnóstico e **ainda não implementa
God24 funcional ou ícone de tipo** no ePSXe.

---

# Studio FM v1.4.13 — Protótipo de trampoline God24 (desativado por segurança)

A partir do relatório MIPS v1.4.12 foi preparado um trampoline de
22 instruções R3000A para o ponto `SLUS+0x287F4`.
A intenção é redirecionar apenas o ícone de tipo 24:
lê o opcode do stream no canal, verifica **kind=0** e **ID=24**
e encaminha para um slot gráfico próprio 0x27–0x30.
**kind=1/2 (Guardian Stars) é encaminhado sem mudanças**.
O código preserva o delay slot original do JAL, mantém $ra
com um tail jump e usa NOPs para os load-delay hazards do PS1.

**Não é uma funcionalidade ativada no BIN.** O módulo
`fmstudio/ps1_god24_hook.py` oferece construção e testes do
trampoline, leitura de SHA/assinatura e verificações conservadoras
de offsets. A gravação é bloqueada sem uma auditoria externa do
espaço de código (cave) específico do SLUS; uma sequência de zeros
não prova que o espaço seja livre. Não foi feito teste no ePSXe.
As funções públicas só trabalham em bytes em memória e não são
chamadas pelo gerador de jogo. No PS1, o tipo God 24 ainda pode
não ser reconhecido como monstro no combate.

O SLUS enviado tem SHA-256
`7412689c12618f90144e8b90839f1f47d2813cc20b42675f2506d8e125fa6b03`.
O alvo compartilhado da chamada é `func_80036C14` e o delay slot
`0x02002021`; quaisquer diferenças interrompem a preparação.
A implementação completa exigirá reservar um endereço MIPS seguro,
selecionar o sprite efetivamente livre no WA do MOD e validar no emulador.

---

# Studio FM v1.4.12 — Inventário das chamadas MIPS do ícone Deus

O botão Efeitos > Diagnosticar motor MIPS agora registra no JSON o inventário de chamadas JAL a func_80036C14 nas três regiões envolvidas na exibição dos ícones. Cada ocorrência inclui endereço RAM, offset SLUS, opcode, delay slot e instruções próximas. A análise também compara hashes das janelas com o diagnóstico enviado do projeto yugioh teste e recusa mapear código quando t_addr/t_size do cabeçalho não correspondem à base PS1. Nenhum byte do executável ou do projeto é modificado.

Essa verificação ainda não instala o ícone God24 no baú: identificar uma chamada não basta para inserir um desvio, pois tipo 24 e Guardian Star 1 compartilham o índice do ícone. São necessários testes MIPS de contexto, ABI, espaço de código e renderização no ePSXe.

---

# Studio FM v1.4.11 — Diagnóstico de ícone de tipo God

O Time Wizard #016 continua sem ícone Deus no campo de tipo do baú: o teste anterior de glifo modifica apenas a descrição. No motor retail o valor 24 também é o índice da primeira Guardian Star (0x17+1), então sobrescrever essa textura afetaria outros símbolos. A função Efeitos > Diagnosticar motor MIPS agora grava diagnostico_icone_tipo_god no JSON, com regiões e hashes de três rotinas retail. Não injeta hook nem promete que o ícone já está no ePSXe. Para instalar um ícone correto será necessário redirecionar especificamente o tipo God24, com sprite próprio e assinatura validada no SLUS do mod.

---

# Studio FM v1.4.10 — Não substituir ícones existentes no mod

A célula 0x29 pode estar ocupada por gráficos de mods. Agora o Studio
procura a primeira célula 16×16 integralmente zerada entre os códigos
endereçáveis 0x27–0x30 (sem usar os ícones retail de 0x00–0x26). O código
gráfico escolhido é refletido no token F8 0B XX da descrição. A faixa
foi verificada na rotina de renderização de sprites do jogo.

Se TODAS as células estiverem ocupadas, nenhum byte gráfico ou texto
será alterado. O manifesto relata explicitamente
`icone_nao_inserido_sem_espaco_livre`; o Studio pode continuar gerando
o BIN para testar **God 24 e ATK/DEF**, desde que sejam modificações
válidas e autorizadas de forma independente. Nunca sobrescreve gráficos
de terceiros ou tenta desenhar em regiões não mapeadas.

O resultado continua experimental: célula zerada no arquivo não garante
que outros sistemas do motor não referenciem essa célula. O símbolo
aparece apenas na descrição, não substitui o ícone de tipo. God 24
ainda necessita validação MIPS e testes no ePSXe.

---

# Studio FM v1.4.9 — Corrigida exportação de ícone Deus sem Pillow

O erro "A exportação do ícone God necessita de Pillow" foi corrigido.
O PNG God (RGBA 16×16) agora é decodificado com bibliotecas padrão de
Python, sem exigir instalação adicional no executável Windows. O leitor
confere cabeçalho, CRC, filtros, dimensões e limites da descompressão
antes de gravar o glifo no BIN de teste.

Pillow ainda é usado na importação de artes maiores, e a compilação
Windows agora o inclui explicitamente. A CI testa o ícone também
com Python -S (sem bibliotecas de terceiros).

Nenhum patch novo de motor MIPS: tipo God 24 e símbolo na descrição
continuam testes experimentais no ePSXe. O BIN original e os
projetos existentes são preservados.

---

# Studio FM v1.4.8 — Gravação experimental do tipo real God 24

Corrige o bloqueio mostrado ao tentar gerar BIN da carta Time Wizard #016
definida como tipo 24. Agora, ao clicar **Gerar jogo BIN/CUE**, o Studio
pergunta se autoriza explicitamente **gravar 24 no campo original de 5 bits**
da carta selecionada. A escolha do usuário é preservada: não reclassifica
a carta como Spellcaster, Dragon, Equip ou qualquer outra.

A autorização fica no projeto em \`ps1_god_type_test_card_id\` e é restrita
a UMA carta #001–#722 cujo tipo é 24. Números 25–31, atributos incompatíveis,
ATK/DEF fora do campo de 9 bits e outras cartas God sem autorização ainda são
bloqueados. A exportação, a regravação de setores BIN/CUE e a verificação da
imagem confirmam **tipo 24 / ATK / DEF efetivamente presentes**. A auditoria
registra explicitamente que o comportamento em duelo ainda é desconhecido.

O botão **Teste no BIN: símbolo Deus** também aceita tipo 24, com aviso
específico, e ativa o opt-in do tipo junto ao teste de glifo. O ícone
continua sendo um **protótipo inserido na descrição**, não o novo ícone
definitivo de tipo.

**ATENÇÃO: registro de cinco bits ≠ novo tipo jogável!** O motor retail
foi criado com tipos 00–23. Gravar 24 pode fazê-lo interpretar a carta
incorretamente, tratá-la como não-monstro, exibir ícone Dragon ou falhar.
Não há hook God24 validado no ePSXe e nenhum foi afirmado aqui.
Teste em uma cópia e mantenha seu BIN original e saves preservados.
Se a gravação passar mas God24 não for criatura, os dados de diagnóstico
orientarão o desenvolvimento da classificação MIPS nativa.

---

# Studio FM v1.4.7 — Primeiro teste de ícone Deus dentro do BIN/CUE

O ícone \`assets/icons/god.png\` já existia, mas só funcionava no Studio.
Agora ele aparece na prévia da carta de raridade Deus, ao lado do tipo.

O botão **Cartas > Teste no BIN: símbolo Deus** cria um teste experimental
*opt-in* de um glifo 16×16 na fonte original do jogo. O Studio converte
o PNG para 4bpp usando a paleta que já está no WA_MRG.MRG. Tenta inserir
na célula \`0x29\` da segunda página da fonte, e **recusa gravar** se
qualquer byte do slot estiver ocupado. O código de texto \`F8 0B 29\` é
inserido na descrição da carta selecionada, substituindo os 3 primeiros
caracteres somente na cópia BIN/CUE experimental.

A descrição do projeto, os dados de ATK/DEF, a ISO de origem, os outros
ícones e as imagens anteriores não são sobrescritos. A cópia recebe
manifestações do glifo e do texto modificados e é relida após a escrita.

**Escopo limitado e explícito:** o símbolo deve ser procurado na
*descrição da carta* no ePSXe. Ainda não é o ícone permanente do tipo
na interface nem um tipo God 24 jogável. O código de desenho existente
sugere que a célula 0x29 é endereçável, mas isso precisa de confirmação
visual real no ePSXe. Se a célula não estiver vazia, o Studio cancela o
BIN sem afetar a última cópia.

O jogo deve ser aberto novamente a partir da cópia gerada, sem save state.

---

# Studio FM v1.4.6 — Tipo personalizado de monstro, sem voltar ao original

O Studio não obriga mais o Time Wizard #016 a ser Spellcaster (tipo 01).
O botão **Escolher tipo jogável (PS1)** permite selecionar qualquer tipo
de criatura 00–19, como Dragon (00), Warrior (03), Machine (14), etc.
A escolha é salva no projeto e exportada para a imagem de teste, com o
ATK/DEF da carta preservados. Os efeitos planejados do Studio não são
apagados.

A opção **Manter visual Deus no Studio** define a raridade visual \`deus\`
de forma independente do tipo jogável (PS1). Assim a carta pode ter
aparência Deus no editor, mas ser classificada como Dragon ou outro tipo
de monstro no motor original.

**Limitação nativa:** God (24) não é um tipo de criatura suportado e
validado no jogo PS1 original. O seu campo na tabela tem 5 bits,
mas gravar o valor 24 não transforma por si só a carta em um novo tipo
de monstro jogável; exigiria alterações nas rotinas do motor, gráficos
e validação com ePSXe. A geração continua protegida contra gravação
enganosa de God 24; não será feito mapeamento silencioso para Spellcaster.

Para testar: escolha o tipo de criatura desejado, marque visual Deus
se preferir, salve o projeto, gere o BIN/CUE e execute a cópia nova no ePSXe.
Confira os atributos com **Verificar imagem**.

---

# Studio FM v1.4.5 — Correção do Time Wizard #016 / ATK do BIN

- Corrigido erro da v1.4.4: tipo God (24) podia ser exibido no Studio,
  mas era descartado silenciosamente pelo exportador, mantendo os atributos
  originais no ePSXe mesmo com valores editados.
- A exportação numérica PS1 agora é **bloqueada com erro explícito** quando
  tipo 24+ ou atributo não suportado impediria o patch. A auditoria do BIN
  também recusa omitir uma edição numérica incompatível.
- **Restaurar tipo original** usa **Spellcaster (01)** no Time Wizard #016,
  mesmo que uma ISO modificada o tenha classificado como Equip/God.
  Outras cartas continuam usando o tipo importado de sua ISO.
- ATK/DEF, efeitos e arte não são alterados ao restaurar somente o tipo.
- A interface destaca o alerta quando Time Wizard não está em Spellcaster.
- Após salvar e gerar BIN/CUE, o resultado exibe quantas cartas tiveram
  atributos verificados na imagem realmente construída.
- Uma imagem antiga ainda aberta no ePSXe não se atualiza por conta própria;
  feche o jogo e carregue explicitamente o BIN gerado.

---

# Studio FM v1.4.4 — Recuperação de tipo e números grandes no simulador

- Na aba **Cartas**, **Restaurar somente tipo da ISO** reverte a classificação
  da carta selecionada ao tipo da imagem de origem. ATK/DEF, arte, nome e
  efeitos são preservados; confirme em **Salvar projeto**.
- Os comboboxes do editor não mudam mais ao usar a roda do mouse sobre eles.
- ATK/DEF do Studio e LP inicial do Laboratório aceitam inteiros não negativos
  com até 64 dígitos (limite de entrada técnica, não de mecânica do duelo).
- **Efeitos > LP alto (simulador)** define o LP inicial do laboratório;
  ataques, cura e bônus não são truncados no teto antigo de 99999.
- **Não significa valores ilimitados no jogo PS1.** A tabela base de cartas
  contém 9 bits para ATK e 9 bits para DEF: 0–5110 em múltiplos de 10.
  Exportações que exigem números fora dessa faixa são bloqueadas com
  aviso explícito, preservando o projeto, BIN original e valores simulados.
- O teste MIPS de LP inicial do PS1 permanece separado, ainda experimental.

---

# Studio FM v1.4.3 — Análise de instruções do motor PS1

**Efeitos > Diagnosticar motor MIPS** agora inclui no relatório
\`amostras_instrucoes_mips\`, com até 20 instruções, endereços, instruções
J/JAL, ramificações, delay slots, loads/stores e JR. Também apresenta
a contagem de chamadas diretas para \`Duel_CalcCardStats\`, quando
o cabeçalho PS-X EXE permite a análise.

**Limite:** é uma inspeção estática parcial, não um patch de habilidade,
não prova espaço livre e não valida um hook para o ePSXe.

---

# Studio FM v1.4.2 — Teste de escrita de instrução MIPS (LP inicial)

Na aba **Efeitos**, o botão **Teste MIPS: LP inicial** permite opcionalmente
gerar uma cópia BIN/CUE com 9000 LP iniciais em duelos normais, em vez de
8000. Outros valores: múltiplos de 500 entre 500 e 9500.

Somente a instrução retail \`addiu $v0,$zero,8000\` do
\`Duel_InitSideStates\` em offset SLUS \`0x7DD0\` é alterada quando os
quatro bytes originais conferem. Imagens com código incompatível são
bloqueadas. O modo 2 jogadores não é alterado; a origem nunca é sobrescrita.

É um **teste de execução MIPS no PS1 ainda não validado em ePSXe**, não
uma habilidade inédita. Consulte
https://github.com/Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled/blob/master/notes/modding-tutorial-evidence.md#initial-duel-life-points

---

# Studio FM v1.4.1 — Referências MIPS de chamadas (diagnóstico)

O botão **Efeitos > Diagnosticar motor MIPS** agora registra, para cada
rotina de efeitos conhecida, referências diretas `JAL` encontradas no
segmento declarado pelo cabeçalho do `SLUS_014.11`, até 16 locais de
chamada por função, total de ocorrências, e indício de prólogo clássico.
O resultado fica em `exportacao/diagnostico_motor_efeitos_mips.json`.

O scanner **recusa concluir** quando a base de carregamento, o tamanho do
segmento ou o cabeçalho são incompatíveis. Uma chamada estática não
prova que a função está correta e **não instala habilidades inéditas**.
Não altera BIN/CUE, arquivo SLUS ou projetos. O primeiro efeito nativo
continua sendo a compatibilidade Equip validada no ePSXe.

---

# Studio FM v1.4.0 — Preparação do motor de efeitos inéditos (MIPS)

**Prioridade: habilidades inéditas, não rituais.** A aba Efeitos destaca auras, bônus por cemitério, imunidades, indestrutibilidade, ataques múltiplos, dano perfurante e ataque direto mesmo com monstros adversários. Esses presets seguem configuráveis e simuláveis; ainda NÃO são novas rotinas executáveis no PS1.

**Novidades desta versão:**
- Laboratório MIPS gera perfil do SLUS vinculado com hashes SHA-256 de funções de atributos, combate, destruição, ações de campo e deck.
- Limites personalizados de **1–40 cópias por carta no simulador**, além do modo ∞ (até 40 do mesmo ID em um deck físico de 40).
- Limite GLOBAL de cópias de 1–40 no PS1, experimental e gravável no SLUS apenas quando uma única comparação MIPS reconhecível é encontrada. Sem validação real em ePSXe ainda.
- Edição de rituais, traps e terrenos retirada da interface Efeitos enquanto focamos habilidades novas. Planos de Ritual anteriores permanecem salvos e sua exportação está suspensa.
- Equip, ATK/DEF, backup e BIN/CUE de teste reaproveitado por nome da origem continuam disponíveis.

**Limitações:** o deck físico do PS1 tem 40 cartas. Aumentar essa capacidade exige rever buffers, menus, memória card e interface. O patch global de cópias não habilita regras diferentes por carta no console e não altera regras especiais de Exodia. Todas as habilidades inéditas de duelo ainda precisam de hooks/eventos MIPS comprovados.

**Diagnóstico:** abra projeto com imagem original importada, vá a Efeitos > Diagnosticar motor MIPS. É gerado exportacao/diagnostico_motor_efeitos_mips.json. Isso não altera o jogo.

---

# Yu-Gi-Oh Studio FM v1.3.0 — Efeitos nativos PS1

**Efeitos exportáveis para BIN/CUE, sem criar novos handlers MIPS:** compatibilidade de equipamentos (já validada no ePSXe pelo usuário), receitas dos rituais originais (3 tributos + resultado), limiares das seis armadilhas de ataque (#681–#686) e bônus de terrenos para 20 tipos originais nos seis campos. Os três últimos recursos foram testados com imagens sintéticas, mas ainda precisam de validação no emulador.

**Segurança:** edições vão somente à cópia BIN/CUE, nunca substituem a origem. A exportação exige SLUS/WA da mesma base, recusa layouts desconhecidos, conserva as sete cópias e verifica os arquivos gerados. Rituais exigem registros existentes, traps exigem tabela retail de seis bytes, terrenos exigem tabela stock ±500.

**Habilidades inéditas não implementadas no PS1:** bônus por cemitério, auras, imunidades, indestrutibilidade, ataques 2x/3x, dano perfurante, primeiro turno, cartas extras e tipo God. Elas seguem no simulador, aguardando hooks/eventos MIPS específicos. Não confunda a prévia do Studio com suporte real no console.

**Uso:** atualize, abra seu projeto com BIN importado, salve, vá à aba Efeitos, use os botões em EFEITOS NATIVOS DO PS1 e gere o BIN/CUE para testar no ePSXe.

---

# Yu-Gi-Oh Studio FM v1.0.1 — Expansão de cartas e descrições

## Correção v1.0.1

O atualizador Python e o script de migração reconhecem novos módulos e PNGs de `assets/icons/`, preservando a proteção contra ROMs e diretórios de projeto. Para instalações Python mais antigas que v1.0, use `tools/ATUALIZAR_SEM_ZIP.ps1` uma única vez; para instalações EXE, clique em **Atualizar**. Depois desta migração, as próximas versões podem adicionar módulos e ícones nas pastas permitidas sem pedir ZIP manual.

## Novidades v1.0.0

- **+ Criar nova carta:** IDs virtuais a partir de 723 até 32766, copiados de uma carta-base selecionada. Essas cartas só existem no Studio e no laboratório; não no BIN original do PS1.
- **God (tipo 24)** para novos monstros e filtros de auras; o exportador não injeta esse tipo desconhecido no executável retail.
- **Ícones de descrição:** escolha entre códigos nativos `{f8 0B XX}` documentados no jogo e ícones novos `{icon:...}` de 16×16 px. Ícones novos permanecem na prévia, aguardando patch de fonte do PS1.
- **Texto colorido:** selecione um trecho e clique Cor no trecho. Cores conhecidas convertem para `{f8 0A XX}` na exportação textual, mas não são gravadas no banco do PS1.
- **+ Bônus por carta:** escolha a carta pelo nome; conte cópias viradas para cima no campo ou no deck completo e receba +X ATK/+Y DEF. A descrição exibe o nome, e não o número da carta.
- **Fusões originais intocadas**, salvamento por botão e atualização pelo GitHub mantidos.

Documentação: `docs/EXPANSAO_722_GOD_TEXTO.md`.

O botão **Atualizar** consulta GitHub Releases do repositório `guibatoni/yu-gi-oh-studio-fm`, baixa o pacote correto de forma automática, verifica SHA-256 e instala na mesma pasta, preservando os projetos.

A cada commit novo na branch `main`, o workflow de Windows compila e publica o Release identificado por `fmstudio/__init__.py`. A versão deve ser incrementada antes da publicação.

**Primeira migração:** instalações antigas do modo Python podem bloquear módulos que não existiam na época, como o motor de habilidades. Use a ferramenta em `tools/ATUALIZAR_SEM_ZIP.ps1` apenas uma vez; após instalar esta versão, utilize somente o botão Atualizar.

**Não há patch jogável de efeitos no PS1 nesta versão:** os efeitos funcionam no simulador do editor.

# Yu-Gi-Oh Studio Card FM v1.1.0 — Exportação experimental para PS1

Editor gráfico Windows para criar MODs de *Yu-Gi-Oh! Forbidden Memories*. **Status real:** o Studio mantém um simulador para habilidades novas. A v1.1.0 amplia a geração BIN/CUE parcial para incluir **atributos, nomes curtos, descrições curtas com ícones e cores nativos, artes e miniaturas** de cartas #1..#722, com validação de origem. Isso **não** implementa as habilidades customizadas nem cartas #723+ no motor do PS1. Veja `docs/COMPAT_PS1.md`.

O app usa Python/Tkinter para interface. A gravação de artes na cópia de disco requer **Pillow**, incluído no executável Windows criado pelo GitHub Actions. Se estiver executando via Python, instale com `python -m pip install pillow` quando for gerar artes.

## Abrir o aplicativo

1. Extraia todo o ZIP para uma pasta de sua escolha no Windows.
2. Dê dois cliques em `INICIAR_FM_MOD_STUDIO.bat` (recomendado; mostra erros se houver). Outra opção é `FM_Mod_Studio.pyw`.
3. Clique **Novo projeto**, informe um nome e escolha onde salvá-lo.
4. Clique **Importar CSVs** e escolha a pasta que já geramos na etapa anterior:

   `D:\Downloads\FM_Original_PS1_v0.1.0_Kit_Desenvolvimento\analysis\tabelas`

   Precisa conter `cartas.csv` e `fusoes.csv`. A importação leva também outras tabelas presentes na mesma pasta. Se preferir, use **Importar BIN / CUE** e selecione sua cópia do jogo; o aplicativo fará a extração diretamente.
5. Clique nas cartas e edite livremente. **Não aparece mais pergunta de salvamento ao trocar de carta.** Os valores ficam pendentes na memória, inclusive se você visitar outras abas. Escolha uma classe de **Raridade** para colorir a prévia e a biblioteca (não modifica o renderizador do PS1). Ao terminar, clique em **Salvar projeto** (ou `Ctrl+S`) para gravar todas as cartas e efeitos de uma vez com backup.
6. Na aba **Efeitos**, selecione **+ Adicionar efeito**. Exemplo: `Ao invocar` → `Aumentar ATK` → `Próprio monstro` → `500`; experimente no **Simulador**.
7. Opcionalmente, use **Importar arte PNG (prévia)** para associar uma imagem local à carta. Ela poderá ser gravada em uma cópia BIN/CUE experimental, desde que a origem WA_MRG.MRG esteja validada e a carta esteja entre #1 e #722.
8. Na aba **Fusões originais**, veja as fusões relacionadas à carta. As receitas são **somente leitura** e preservadas com verificação de hash.
9. Use **Salvar projeto** antes de **Exportar alterações**. Abra a pasta `exportacao/` criada dentro de seu projeto.

### Para exportar também uma cópia auxiliar do executável

Ao importar diretamente um `.BIN/.CUE`, o programa extrai e vincula automaticamente o SLUS para o projeto. Se você importou **somente CSVs**, clique **Vincular SLUS** e selecione o arquivo **da mesma imagem utilizada na extração**, por exemplo:

`D:\Downloads\FM_Original_PS1_v0.1.0_Kit_Desenvolvimento\FM_Original_PS1_v0.1\analysis\extracted\SLUS_014.11`

Antes de permitir alterações binárias, o programa verifica todos os 722 registros e, quando disponível, o SHA-256 do relatório de extração. Se houver divergência, a operação é bloqueada.

### O que é editável hoje

| Recurso | Estado na v1.1.0 |
|---|---|
| Buscar as 722 cartas | Funcional por número e nome personalizado |
| ATK / DEF | Editável, valida múltiplos de 10 e pode gerar SLUS auxiliar |
| Tipo / atributo / nível / estrelas guardiãs | Editáveis, exportáveis em SLUS auxiliar |
| Nome / descrição / cor do nome | Nomes e descrições **curtos** graváveis sob guarda de slot e fonte original; classe/cor de nome continuam só no Studio |
| Arte PNG | Gravável em BIN/CUE de teste para #1..#722, usando paleta original e WA hash verificado |
| Eventos/efeitos | Edição pendente até salvar, simulação local; **sem execução no jogo** |
| Fusões | Consultáveis, preservadas; **não editáveis** |
| Importar `.BIN/.CUE` ou CSVs | Funcional para estrutura alvo `SLUS-01411`, sujeita a modificação X15 |
| Exportar BIN/CUE de teste | **Experimental v1.1.0: atributos, textos curtos e artes; depende de validar no ePSXe real** |
| Gerar EXE Windows | Script fornecido; o ZIP **não contém EXE pré-compilado** |

### O que há na pasta `exportacao/`

- `alteracoes_cartas.json` — diferenças em cartas (inclui campos de texto e numéricos).
- `efeitos_planejados.json` — definições dos efeitos; declara que são apenas para simulação.
- `artes_referencia.json` — relação das imagens PNG vinculadas, somente como referência visual.
- `manifesto.json` — resumo da exportação e aviso de compatibilidade.
- `mudancas_binarias.json` — **apenas se** houve alterações numéricas e SLUS foi vinculado, com offsets e bytes antes/depois.
- `build_local/SLUS_014.11` — **apenas se** houve alterações numéricas e SLUS foi vinculado. Cópia isolada do executável; **não é imagem jogável**. Para testar estatísticas, use o botão **Gerar BIN/CUE de teste** em Projeto / Exportação. Não distribua ROMs.

### Novidades v0.9.0 — Habilidades rápidas das criaturas

- Na aba **Efeitos**, configure sem janelas adicionais: 1x/2x/3x ataques, indestrutível, imune a mágicas, imune a armadilhas, dano perfurante, não bloqueável e perda de X LP em cada ataque.
- Marque **Sem limite de cópias** para uma carta superar o limite padrão de três cópias no deck; o deck completo continua com limite de **40 cartas**.
- Todas as escolhas ficam pendentes automaticamente e podem ser gravadas pelo botão **Salvar projeto** / `Ctrl+S`; troque de carta sem confirmação.
- No Laboratório, o botão **Atacar alvo** testa o combate contra ATK ou DEF, **Ataque direto** testa ataque direto e **Novo turno** reinicia a quantidade de ataques. Habilidades não são patches de PS1.
- Cada cartão mantém os efeitos avançados antigos (auras, equipamentos, gatilhos) junto aos presets. Fusões originais não foram alteradas.
- Detalhes e limites: `docs/HABILIDADES_RAPIDAS.md`.

### Novidades v0.8.0 — Efeitos por deck, encantamentos e Laboratório de Duelo

- **Por tipo no deck configurado (até 40 cartas):** a carta ganha `X ATK` e `Y DEF` por cópia do TIPO selecionado. Escolha `Todos os tipos` para contar todas as cartas. O bônus é contínuo, não acumulado a cada turno. O "deck" é a lista completa configurada para simulação, não o monte de compra restante.
- **LP por tipo:** ao invocar, recupera X LP por carta do tipo no deck, ou causa X pontos de dano aos LP do adversário por carta do tipo. Esses gatilhos acontecem apenas quando você pressiona **Aplicar gatilho**, não em cada atualização de tela.
- **Descarte ao invocar:** adversário descarta até X cartas de sua mão; sem cartas na mão, não há descarte. O limite de mão do simulador é 5 cartas.
- **Dano ao monstro alvo:** dano numérico cumulativo experimental. O Forbidden Memories clássico não atribui HP aos monstros, então a resistência deste laboratório começa em DEF-base (mínimo de 1), independente do ATK/DEF de combate. **Não representa uma regra original do PS1.**
- **Equipamentos como encantamentos:** `imune a armadilha`, `imune a mágicas e armadilhas`, `indestrutível` e `+X ATK`. O simulador deixa equipar uma carta em cada slot de monstro; sua estrutura interna aceita múltiplos equipamentos por slot. Proteções abrangem os efeitos de dano simulados de origem mágica/armadilha; imunidade completa a todos os efeitos dessas categorias ainda depende da implementação das outras ações.
- **Aura que concede / aura que recebe:** a primeira concede bônus às cartas do tipo escolhido; a segunda ganha bônus por cada carta correspondente em campo. Ambas aceitam `Todos os tipos` e escopos `aliados`, `inimigos` ou `todos`. Bônus cessam ao remover a fonte e são recalculados do zero.
- **Interface:** na aba **Efeitos**, clique em `+ Adicionar efeito` e escolha a nova ação. Para testar, abra **Laboratório: campo, decks e equips**. Na aba **Campo e equipamentos**, selecione monstros e anexos; em **Deck, mão e gatilhos**, preencha IDs de cartas (ex.: `1x3, 2x2, 16`), selecione origem/alvo e clique **Aplicar gatilho uma vez**.
- **Compatibilidade:** continua com `Salvar projeto`/`Ctrl+S` e fusões originais protegidas. O Studio não injeta esses efeitos no BIN do PS1; são definição e simulação de um novo motor experimental.

### Novidades v0.7.0 — Auras e bônus contínuos (simulador de campo)

- **Aura por tipo:** uma carta em campo concede `+X ATK` e `+Y DEF` a todos os monstros **aliados virados para cima** do tipo selecionado (ex.: Fairy/Fada). A aura termina se a carta-fonte sair do campo ou ficar virada para baixo.
- **Bônus por quantidade:** a carta-fonte ganha `+X ATK` e `+Y DEF` para cada aliado virado para cima do tipo selecionado. Conta a própria carta-fonte quando ela for daquele tipo; mudanças no campo recalculam instantaneamente o bônus.
- **Empilhamento controlado:** múltiplas auras podem somar bônus, mas **não** existe acúmulo permanente ao trocar monstros. A simulação sempre parte dos atributos-base. Bônus ficam limitados no simulador a ATK/DEF 99.999.
- **Editor:** na aba **Efeitos**, use `+ Adicionar efeito`, selecione `Enquanto estiver em campo` e escolha `Aura: aliados do tipo ganham ATK/DEF` ou `Recebe ATK/DEF por monstro do tipo em campo`. Defina os pontos de ATK, DEF e tipo (`08 — Fairy`).
- **Campo visual:** clique em **Simular campo 5×5** para escolher até cinco monstros de cada lado. Retire uma Fada da lista e veja o bônus diminuir na hora. Desmarque `↑` para tratá-la como carta virada para baixo.
- **Salvamento:** mantém o fluxo sem prompts ao trocar de carta; as novas definições entram no projeto com **Salvar projeto** / `Ctrl+S`.
- **Fusões:** originais, intocadas. Nenhuma ROM, executável ou BIN/CUE recebe esses efeitos: **somente o simulador do editor**. Futura implementação no PS1 requer rotinas MIPS, investigação do executável e teste em ePSXe.

### Novidades v0.6.0 — Editar sem interrupções

- Ao trocar entre cartas, nenhuma pergunta aparece. O programa guarda as alterações **na memória** até clicar **Salvar projeto** (ou `Ctrl+S`). A quantidade de cartas com alterações pendentes é mostrada abaixo da biblioteca.
- Nomes podem ter uma cor RGB escolhida pelo seletor de cores. A cor fica registrada no `projeto.json` e no JSON de exportação, além de aparecer na prévia e nas linhas da biblioteca. **Não modifica o texto renderizado pelo PS1** — isso exigirá um patch específico.
- Efeitos novos ou removidos também ficam pendentes até o salvamento em lote; o simulador consulta esses efeitos ainda não salvos.
- Em caso de valor inválido, o botão mostra o problema e mantém os rascunhos na memória para corrigir, sem apagar alterações das outras cartas.
- Uma confirmação é exibida somente ao **fechar, atualizar ou trocar de projeto com mudanças pendentes**, para evitar perda acidental. Exportação e extração exigem salvar antes.
- A associação de PNGs ainda é gravada imediatamente na pasta do projeto por ser uma operação de importação de arquivo.
- Projetos antigos (`schema` 1) continuam compatíveis; sem cor configurada, usa-se o padrão dourado `#F1CF6E`.

### Segurança e backups

- O aplicativo **nunca escreve no `.BIN/.CUE` original**.
- Projetos e alterações são armazenados separadamente em `projeto.json`.
- Cada salvamento mantém até 15 versões anteriores de `projeto.json` em `backups/`.
- Arquivos-base `cartas.csv` e `fusoes.csv` são preservados e auditados por SHA-256.
- A versão importada pode ser um Drop X15. As 15 fusões sinalizadas como `possivel_glitch` não serão removidas nem alteradas.
- O ZIP não inclui jogo, ROM, executável do jogo, artes, BIOS nem cartas protegidas extraídas de ROM.

### Atualizações diretas — v0.8.0

O botão **⟳ Atualizar** agora funciona tanto no **Python** (`INICIAR_FM_MOD_STUDIO.bat` / `.pyw`), quanto no **EXE compilado**. No Python ele instala o pacote `FM-Mod-Studio-Source.zip`; no EXE instala `FM-Mod-Studio-Windows.zip`. Ambos exigem `.sha256` no GitHub Release.

**Condição obrigatória:** o repositório público `guibatoni/yu-gi-oh-studio-fm` precisa existir e ter ao menos um GitHub Release publicado. Antes disso, o botão avisa que falta publicar o projeto, em vez de tentar atualizar arquivos inexistentes. `PUBLICAR_GITHUB.bat` clona o repositório existente, envia o código e a tag `studio-v0.8.0` para iniciar GitHub Actions.

- Ao detectar versão nova, exibe notas e pede confirmação.
- Se houver edição pendente, solicita salvamento antes de fechar o Studio.
- Um instalador independente baixa o pacote, verifica o SHA-256 e arquivos permitidos, encerra o aplicativo, substitui somente componentes conhecidos e reabre o Studio.
- Não sobrescreve `projetos/`, ROMs, dados extraídos, saves, backups, ou arquivos criados por você.
- Os testes usam atualizações simuladas. **Nenhum teste de instalação real via GitHub Release foi possível sem a publicação do repositório.**

Para corrigir a v0.6.0 sem mover projetos: extraia o ZIP v0.6.2 em uma pasta nova, feche o Studio antigo e execute **`INSTALAR_CORRECAO_NO_STUDIO_ATUAL.bat`**. Escolha a pasta onde está o `app.py` antigo. O instalador substitui só os componentes do editor, sem apagar `projetos/`, `base/` ou `backups/`. Você também pode copiar os arquivos manualmente, mas não exclua a instalação anterior antes de fazer backup.

### Requisitos

- Windows 10/11.
- Python 3.10 ou superior com Tkinter (normalmente acompanha o Python para Windows).
- Sem instalação de pacotes adicionais para executar.
- Para gerar um `.exe` local no próprio Windows: execute `CRIAR_EXE_WINDOWS.bat` (precisa instalar `pyinstaller`). O `.exe` gerado ficará em `dist/FM-Mod-Studio.exe`. Também há workflow de GitHub Actions para Windows em `.github/workflows/windows-exe.yml`.

**Não distribua `base/source_SLUS_014.11`, `build_local/SLUS_014.11`, ROMs nem arquivos completos do jogo.** A futura distribuição será por patches que exigem a imagem legalmente obtida pelo usuário.

## Verificar o código

Abra um terminal na pasta e execute:

```powershell
python -m unittest discover -s tests -v
```

O kit inclui testes automatizados com **dados totalmente sintéticos**. Dados da imagem real importada pelo usuário ainda exigem confirmação de compatibilidade e testes no ePSXe.

### Migração especial do atualizador Python v0.6.x/v0.7.0 para v0.8.0

Os atualizadores antigos possuem listas de segurança de arquivos permitidos que **não incluem** os dois novos módulos `fmstudio/duel_engine.py` e `fmstudio/lab_gui.py`; por isso a atualização automática pelo botão pode rejeitar este salto com "conteúdo inesperado". Essa é uma proteção, não corrompimento. **Faça a primeira instalação v0.8.0 localmente:** feche a versão antiga, extraia a v0.8.0 numa pasta separada e execute `INSTALAR_CORRECAO_NO_STUDIO_ATUAL.bat`; selecione a pasta anterior que contém `app.py`. O instalador copia os módulos novos e preserva `projetos/` e `backups/`. A partir da v0.8.0 o whitelist já inclui os novos módulos para futuras atualizações. Em instalações EXE não se aplica essa limitação de nomes de módulos porque os novos módulos vêm dentro do executável.

## Classes de cartas (v1.0.2)

No editor de cartas, selecione **Raridade** para monstros. A classe do nome é automática:
Comum cinza claro; Incomum branca; Rara amarela; Épica roxa; Lendária vermelha; Deus azul-marinho.
Quando o tipo é Magic, Trap, Equip ou God, a categoria tem precedência e a cor fica, respectivamente, verde, rosa, azul ou azul-marinho.
No projeto o campo `raridade` é persistido; o campo `cor_nome` antigo é mantido por compatibilidade.
A saída `classes_cartas.json` permite usar a classificação nos futuros patches, mas ainda não altera o texto do jogo PS1.

## v1.0.3 — Cemitério e primeira cópia BIN/CUE de teste

**Bônus por cemitério:** na aba **Efeitos** escolha `Enquanto no campo` →
`Recebe ATK/DEF por tipo no cemitério`. Informe X ATK, Y DEF, tipo e escopo.
Abra `Laboratório: campo, decks e equips`, use o campo `CEMITÉRIOS` para digitar
IDs ou clique `Destruir alvo → cemitério` para observar o bônus **dinamicamente**.
Um monstro já invocado recebe bônus quando outro do tipo escolhido morre;
se a carta sair do cemitério, a quantidade diminui. Nenhum valor-base é alterado.

**Ataca no primeiro turno:** em `Habilidades rápidas`, marque
`Ataca no 1º turno`. Ícone `ataque_primeiro_turno.png` disponível em
`Inserir ícone` para a descrição `{icon:ataque_primeiro_turno}`. A opção age
no simulador e pode coexistir com 2x/3x. O jogo clássico tem suas próprias
regras de ataque: **a habilidade ainda não altera o PS1**.

### Construir uma imagem jogável de teste (somente estatísticas)

1. Abra seu projeto que foi **importado do BIN/CUE** ou que possui um
   `SLUS_014.11` vinculado e compatível.
2. Escolha uma carta **original** (#001–#722), altere apenas ATK/DEF,
   nível, atributo ou outro dado numérico suportado e clique `Salvar projeto`.
3. Na aba `Projeto / Exportação`, clique `Gerar BIN/CUE de teste (estatísticas)`.
4. Selecione o **mesmo BIN/CUE que foi importado**. O Studio compara o SHA-256
   do SLUS de origem com o salvo na base antes de copiar.
5. Após a geração, procure em `<seu-projeto>/exportacao/teste_ps1/` por
   `FM_STUDIO_TESTE_....bin`, `.cue` e `.json` (registro do que mudou).
6. No ePSXe selecione `File / Run ISO` e abra o **BIN** gerado (ou o CUE se
   sua versão do emulador permitir). Confira o ATK/DEF da carta alterada,
   duelos, fusões e gravação de progresso. Guarde sempre o jogo original.

Não transforme BIN MODE2/2352 em ISO2048 com um editor genérico: ele pode
perder o áudio XA/STR. O par BIN/CUE **já é uma imagem de CD jogável**. Esta
função grava somente estatísticas suportadas, não o interpretador de auras,
cemitério, ícones, God ou cartas extras. Ainda não validamos uma imagem real
no ePSXe; o teste do programa foi feito com setores sintéticos. Um CUE
multifaixas ou um jogo cujo executável diverge da base é recusado.

Também é possível gerar a cópia pelo PowerShell, na pasta do aplicativo:

```powershell
python .\tools\gerar_bin_teste.py --projeto "D:\MeusMods\MeuMod" --bin "D:\Roms\Yu-Gi-Oh Original.bin"
```

**Importante:** o gerador nunca modifica nem distribui a ROM original.


## v1.1.0 — Compatibilidade experimental do BIN/CUE

- O botão **Compatibilidade PS1** produz `exportacao/compatibilidade_ps1.json`, com uma matriz de recursos suportados e pendências de motor.
- O botão **Gerar BIN/CUE de teste** pode alterar, com proteções, estatísticas, nomes/descrições curtos e imagens de cartas originais.
- O motor PS1 não foi expandido: novas cartas, God, auras, imunidades, ataques múltiplos, ícones personalizados, raridades e demais habilidades continuam apenas no editor e laboratório.
- As fusões permanecem imutáveis e a imagem original nunca é sobrescrita.
- Consulte `docs/COMPAT_PS1.md` antes de testar qualquer imagem no ePSXe.
