# Quests antes dos duelos da campanha PS1

Simon Muran pode duelar desde o início. Os outros 37 duelistas da história
solicitam a doação quando você escolhe duelar. A entrega fica disponível
quando todos os requisitos têm cópias suficientes no baú. Cada cópia
conta para um critério e o jogo protege as cartas usadas no deck ativo.
A entrega abre o duelo e fica registrada no save.

## Editar no Studio

1. Abra o projeto do **Original Drop x15**.
2. Em **Edição do Mod → Quests da campanha**, marque **Ativar quests no BIN/CUE de teste**.
3. Defina a seed e clique em **Gerar prévia**. A tabela mostra a doação de cada NPC, o duelista que pode dropar a carta e o peso no grupo de rank.
4. Selecione um duelista e clique em **Editar quest**. Você também pode clicar duas vezes na linha da prévia.
5. Escolha até quatro alvos por carta, tipo, atributo, Guardian Star ou raridade. Informe as quantidades e clique em **Aplicar requisitos**. **Usar a seed deste NPC** restaura a geração automática para ele.
6. Gere a prévia para validar as fontes, clique em **Salvar configuração** e use **Gerar jogo BIN/CUE**. Abra o arquivo com sufixo `_QUESTS.bin`.

A seed define cada quest separadamente. Editar um NPC mantém as outras
doações geradas para a mesma seed. A prévia e a exportação usam os
drops configurados no projeto. Cada requisito precisa de uma fonte
que o jogador possa enfrentar antes da quest. O Studio valida também
se o baú comporta as doações com o deck protegido.

## Voltar ao Card Shop

Antes de duelar, escolha **Ir ao Card Shop** para adiar a entrega.
No Egito, o jogo retorna ao mapa. Na reta final, ele posiciona o
jogador no **Hiding**, onde fica o Card Shop. Durante o torneio, ele
abre a loja da rodada atual.

Na loja, você pode salvar, editar o deck ou escolher **Return to Title**
para buscar cartas no **Free Duel**. Simon aparece no Free Duel quando
a primeira quest é apresentada. Ao entrar novamente na campanha,
escolha **Leave Shop** para retomar o duelo pendente. O save conserva o
confronto exato, inclusive no Labirinto, diante de Seto 2nd e na reta final.

## Requisitos em JSON

**Importar requisitos JSON** continua disponível. O exemplo exige 50
cartas do tipo Fairy antes do duelo com Teana:

```json
{
  "2": [{"tipo": "tipo", "alvo": 8, "quantidade": 50}]
}
```

Arquivos de quests da versão anterior podem ser importados. Os requisitos
de Simon são descartados e os demais são revalidados com as fontes
disponíveis antes de cada duelo.

## Verificação

**Verificar BIN/CUE** confirma a tabela das 37 quests e o carregador.
Para substituir um BIN gerado pela v1.9.11, gere novamente pelo Studio atualizado.
Reinicie a imagem no emulador e carregue a campanha pelo memory card.
O teste MIPS usou os 59 descritores de duelo do Original Drop x15
e conferiu a proteção do deck, a saída para a loja, o save e a
retomada com os parâmetros nativos do confronto. A apresentação do
diálogo ainda precisa de uma partida no ePSXe.

O módulo reside no `DATA/WA_MRG.MRG` e carrega junto com a cena.
Os comandos nativos F8 0D e F8 12 ligam a entrada e a
resposta ao módulo. O opcode de saída do mapa reconhece a loja pelo
bytecode verificado. Para recompilar com Zig 0.13 e `nm`, rode
`python tools/compile_ps1_campaign_quests.py --zig caminho/zig`.
