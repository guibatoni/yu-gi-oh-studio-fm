# Recriar deck do oponente a partir da ISO original

Na aba **Edição do Mod → Deck do oponente**, selecione um dos 39
duelistas e clique em **Criar deck da ISO original**.

A janela mostra todos os IDs encontrados, nomes, pesos e probabilidade
teórica por sorteio. O editor usa **somente**
`<projeto>/base/decks_drops.csv`, extraído pelo Studio do
`DATA/WA_MRG.MRG` da imagem importada, no grupo `deck` do
adversário selecionado. O conteúdo editado de `metadata`,
dos drops, ou de outro oponente **nunca** é usado para reconstruir a
tabela de origem.

Um deck original não é uma lista fixa: são **40 compras de um pool
ponderado**, inclusive quando existem menos de 40 IDs distintos.
Não transformar peso 500 em 500 cópias ou gerar arbitrariamente um deck
aleatório. A soma retail esperada é 2048; em ISO modificada, qualquer
soma positiva não-padrão é mostrada com aviso e os pesos exatos são
preservados.

## Como funciona o botão

1. Escolha o rival e clique no botão.
2. Revise a tabela com as probabilidades e pressione
   **Criar deck da ISO original** para confirmar.
3. O Studio remove apenas a substituição do deck
   (`mod_editor.duelistas[ID].deck`) e o antigo selo
   `campanha_dificil` desse duelista.
4. O editor carrega o pool original, selecionando a aba
   **Pools ponderados**. O projeto é salvo com backup rotativo.
5. O sistema de exportação de PS1 deixa a tabela original do
   `WA_MRG.MRG` intacta para esse adversário: sem override,
   o jogo continua usando os pesos importados da ISO.
6. Se você alterar qualquer peso e clicar **Salvar deck**, o
   Studio salva uma regra personalizada (sujeita a validação
   de limite de cartas/compatibilidade PS1). Se salvar a
   configuração exatamente igual à original, mantém
   o comportamento herdado sem patch redundante.

A função não toca a ISO de origem, não altera as cartas,
efeitos, fusões, recompensas ou drops individuais por RANK
dos outros duelistas. Pesos de drops configurados a partir
do próprio deck também ficam salvos; convém revisá-los caso
a lista de candidatos se modifique.

## Limitações e validação

- O botão depende da extração original já presente em
  `base/decks_drops.csv`. Se ela não existir, é necessário
  importar ou reextrair a ISO original associada ao projeto.
- Uma ISO sem registros de deck para aquele rival retorna erro:
  não se criam pesos fictícios ou cartas aleatórias.
- Em mods com pools não usuais, o editor do Studio e o
  simulador podem impor limites de cópias diferentes da
  rotina PS1 original. A restauração preserva a tabela do jogo;
  **não regrava os pesos do WA**.
- Testes automatizados conferem o CSV, os IDs, pesos exatos,
  o isolamento dos demais duelistas e a persistência após salvar.
  Para gameplay, testar um duelo contra o adversário no ePSXe.
