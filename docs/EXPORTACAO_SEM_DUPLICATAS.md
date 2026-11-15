# Substituição automática dos BIN/CUE de teste

A partir da v1.2.2, **Gerar jogo BIN/CUE** não cria um nome novo a cada
exportação. O arquivo de saída recebe um nome fixo baseado no nome do BIN de
origem. O Studio mantém o próprio jogo intacto.

Exemplo:

- Origem: Yu-Gi-Oh! FM Original (Drop x15).bin
- Destino: FM_STUDIO_TESTE_Yu-Gi-Oh_ FM Original (Drop x15)_<identificador>.bin
- Próximo build dessa mesma origem: o mesmo arquivo de destino é substituído.
- Origem com nome diferente: outro destino, sem alterar o primeiro.

O identificador é calculado a partir do **nome do arquivo** (não do caminho),
para evitar colisões e preservar distinções entre nomes. Isso também permite
reutilizar o mesmo destino caso a origem mude de pasta.

## Segurança

O Studio monta a nova imagem em pasta temporária dentro de
`exportacao/teste_ps1`, valida seu executável e o banco WA quando houver
alterações, e só então publica o arquivo. Em uma falha antes da publicação,
a versão anterior não é alterada. Se o ePSXe estiver bloqueando o BIN,
encerre a execução do jogo para permitir a substituição no Windows.

Arquivos de teste antigos com nome baseado em timestamp
`FM_STUDIO_TESTE_YYYYMMDD_*.bin` não são excluídos automaticamente
para não apagar versões de teste que você queira comparar.
Podem ser removidos manualmente depois de verificar o novo BIN.
