# Quests de doação na campanha do PS1

1. Abra o projeto vinculado ao **Original Drop x15**.
2. Entre em **Edição do Mod → Quests da campanha** e marque **Ativar quests no BIN/CUE de teste**.
3. Informe ou sorteie uma seed. **Gerar prévia** mostra os requisitos dos 38 duelistas, sua origem e o peso em 2048 por carta sorteada.
4. Clique em **Salvar configuração → Gerar jogo BIN/CUE**. Selecione o Original Drop x15 vinculado ao projeto.
5. Em **Verificar BIN/CUE**, selecione a cópia de teste com o sufixo `_QUESTS`. Abra essa cópia no ePSXe, inicie uma campanha nova e vença um duelista.

A opção começa desativada. O Studio salva a configuração no projeto e escreve
a cópia com quests em `exportacao/teste_ps1`. Ao lado do BIN/CUE ficam o
manifesto e os arquivos `.quests.json` e `.quests.bin`.

## Ofertas

O diálogo de vitória mostra quantas cópias do baú estão disponíveis para cada
requisito. As cópias usadas no deck ativo ficam protegidas. Quando uma carta
serve para mais de um requisito, cada cópia cobre uma única parte da oferta.
**Rever requisitos** reconta o baú. **Confirmar doação** retira as cópias e
libera o fluxo de história. O save registra a entrega uma vez por duelista.
Para testar outra seed desde o começo, use uma campanha nova.

O gerador usa os drops e as compras iniciais gravados no BIN de teste.
Cada requisito deve ter origem no deck inicial ou em um duelista de ID
menor cuja vitória já é garantida pela rota da campanha. A quantidade
gerada considera a chance da melhor fonte no grupo de rank. Se faltarem
cópias, **Entregar com reserva** usa as sobras disponíveis e completa a
oferta diretamente. A reserva evita que uma campanha fique travada por
um sorteio desfavorável.

A exportação usa os IDs 1–722 para os requisitos e permite combinar o
sistema com a expansão de cartas e os efeitos nativos do Studio.

## Requisitos manuais

Salve um JSON como o abaixo e selecione **Importar requisitos JSON**. A
seed preenche os duelistas que ficaram de fora.

```json
{
  "1": [
    {"tipo": "carta", "alvo": 387, "quantidade": 10},
    {"tipo": "carta", "alvo": 192, "quantidade": 5},
    {"tipo": "carta", "alvo": 123, "quantidade": 20}
  ],
  "2": [
    {"tipo": "tipo", "alvo": 8, "quantidade": 50}
  ]
}
```

Simon exige Mystic Lamp, Key Mace e Dark Plant. Teana aceita 50 Fairy.
Há até quatro requisitos por duelista, com quantidades de 1 a 255. O alvo
pode ser um ID de carta, tipo, atributo, Guardian Star ou raridade. Use
`carta`, `tipo`, `atributo`, `guardian_star` ou `raridade`. Para raridade,
o ID começa em zero na ordem de `fmstudio/rarities.py`. A prévia valida
cada fonte antes da geração.

## Implementação e verificação

| Arquivo | Função |
| --- | --- |
| `fmstudio/campaign_quests.py` | Catálogo, parser CSV, validação de fontes, gerador por seed e tabela binária. |
| `fmstudio/quest_gui.py` | Configuração no editor do mod e prévia. |
| `fmstudio/ps1_campaign_quests.py` | Persistência, instalação e verificação do carregador e da tabela. |
| `fmstudio/disc_build.py` e `fmstudio/disc_verify.py` | Montagem e releitura do BIN/CUE pelo fluxo normal do Studio. |
| `tools/ps1/campaign_quests.c` e `tools/ps1/campaign_quest_loader.S` | Diálogo, contagem, doação e retomada da campanha. |

O Studio insere o módulo no `DATA/WA_MRG.MRG`. O carregador usa a área de
transferência do console somente durante o diálogo de vitória e preserva
as reservas fixas do motor de duelo. Em uma cópia expandida, o módulo fica
antes da arte adicional e o adaptador existente ajusta o setor do pedido.
A releitura verifica os comandos do SLUS, a tabela binária de quests e as
origens gravadas no BIN.

Para recompilar, use Zig 0.13 e `nm` com
`python tools/compile_ps1_campaign_quests.py --zig caminho/zig`.
`python -m unittest discover -s tests -p test_campaign_quests.py` inclui o
teste da CPU MIPS quando Unicorn está instalado. A verificação com os
38 comandos nativos do disco conferiu a leitura do setor, a escolha no
diálogo, as flags de vitória, as cartas adicionais e o retorno no Free Duel.
A apresentação do diálogo e a campanha completa ainda precisam ser
testadas no ePSXe.
