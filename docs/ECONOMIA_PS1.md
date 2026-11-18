# Economia PS1 — baú, Passwords e estrelas por vitória

## Onde editar

No **Studio FM → Edição do Mod → Passwords e baú**:

- **Baú:** checkbox **Mostrar todas as cartas no baú do PS1, inclusive as que não possuo**. Ativado conserva o comportamento das versões recentes; desativado restaura a visualização original (apenas cartas obtidas) ao gerar a próxima cópia BIN/CUE. O controle “Mostrar todas as cartas no Studio” modifica somente a lista do Studio.
- **Estrelas por carta:** selecione uma carta, clique **Editar custo da carta** e informe de 0 a 999.999 Star Chips. Para desfazer, clique **Restaurar preço original**. A tabela extraída em `base/senhas.csv` nunca é modificada.
- **Estrelas por duelo:** escolha **Original por rank** (S=5, A=4, B=3, C=2, D=1) ou **Quantidade fixa por vitória** (1–255). O valor fixo não altera drops nem a nota/rank.

## Como funciona no PS1

O botão **Gerar jogo BIN/CUE** lê os campos salvos no `projeto.json`, usa o
SLUS/WA da imagem *original vinculada* e escreve somente na cópia temporária.
O jogo continua usando a mesma conta/sistema de Star Chips, sem truques de
memória nem plugins do emulador.

- O catálogo completo muda uma instrução no SLUS USA Drop x15, sem conceder
  cartas ou modificar a quantidade em memória/Memory Card. Desativado, a
  instrução original é preservada.
- Os preços originais estão em `WA_MRG.MRG`, em
  `PASSWORD_BASE + 8 * ID`. Apenas o primeiro `u32` (custo) de cada
  registro é alterado. O `u32` seguinte (código Password BCD) fica intacto.
- Cartas nativas expandidas #723–740 recebem seus custos ao criar os
  registros na expansão já existente. Nenhuma alteração é permitida em IDs
  acima do limite PS1 ou em buracos sem registro de carta.
- O motor Drop x15 contém em `0x80021C34` a instrução
  `addiu v0,v0,1`, que transforma rank em quantidade de Star Chips. Para
  configurar um valor fixo, somente essa instrução é trocada por
  `addiu v0,zero,N`; a instrução seguinte grava o byte de recompensa em
  `+0x3A` e a rotina de fim de duelo lê esse byte. O campo do jogo é de
  **8 bits**, portanto o intervalo de valores fixos é 1 a 255.
  Outros métodos (por exemplo, 1000 estrelas por vitória) exigem uma
  expansão do motor e não foram implementados.

## Compatibilidade e segurança

- Somente SLUS Drop x15 com o SHA-256 reconhecido.
- O custo no projeto não substitui o código BCD original nem habilita uma
  carta que não tenha Password ativo. Para cartões expandido é necessário
  que o ID faça parte da expansão nativa existente.
- O compilador compara a tabela WA com o hash da origem do projeto,
  verifica os opcodes antes de substituí-los, relê a tabela e o SLUS do
  **BIN/CUE gerado**, e falha preservando o BIN anterior caso algo difira.
- O editor mantém os projetos anteriores sem mudanças: catálogo completo
  ligado por padrão, nenhum preço modificado e estrelas originais por rank.
- Cada alteração salva recebe o backup rotativo `backups/projeto_*.json`
  da configuração anterior. Nunca escrevemos no BIN de origem nem nos
  arquivos .mcr do ePSXe.

## Validação

Os testes unitários verificam mudança exata de instrução, permissão por
valor, preço em `u32` sem alteração do password BCD, deslocamento da
tabela na expansão, persistência no projeto, restauração e rollback.
A passagem no GitHub Actions valida a lógica em dados sintéticos.
A execução real no ePSXe exige jogar um duelo completo, obter
Star Chips e comprar uma carta por Password usando a cópia exportada.
