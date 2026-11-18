# Editor múltiplo, efeitos e ícones PS1 — Studio FM

## Entrega e escopo

### Edição em massa do baú

Em **Edição do Mod → Passwords e baú**, as tabelas Baú e Estrelas por carta
aceitam `Ctrl+clique`, `Shift+clique`, `Ctrl+A`, **Selecionar todas**,
**Limpar seleção** e **Editar selecionadas**. A seleção respeita a filtragem.

A janela de edição em massa suporta **Definir**, **Adicionar**,
**Subtrair** e **Zerar** para dois campos independentes:

- **Cópias no baú do Studio:** 0–9.999, apenas no projeto e simulador.
  Não edita os inventários do Memory Card PS1 (arquivo .mcr).
- **Preço de Password:** 0–999.999 Star Chips, IDs #001–#722 e
  #723–#740 que estejam efetivamente presentes na expansão PS1.
  Não há edição fictícia para cartas acima do limite.

A tabela apresenta **antes e depois** para cada ID. Confirmar gera uma
única alteração atômica em `projeto.json`; o mecanismo de `Project.save`
cria um backup da versão anterior. Modificações inválidas (valores negativos,
preços sem dados de origem, duplicatas, carta fora do limite) bloqueiam
toda a operação. O CSV de passwords original é preservado.
Para o PS1, custos mudados no projeto só chegam ao jogo após gerar BIN/CUE
e a releitura do WA_MRG de teste. Os códigos BCD permanecem intactos.

### Efeitos

Na aba **Efeitos**, a ação **+ Adicionar efeito** abre uma única janela
com busca e filtro por categoria. **Aplicar** acrescenta uma configuração
validada à lista temporária, mantendo a janela aberta; **Remover selecionados**
retira entradas da lista. **OK** adiciona o conjunto ao rascunho em uma única
operação; **Cancelar** não modifica rascunhos nem projetos.

Na tabela, `Ctrl+C` copia um ou mais efeitos selecionados, `Ctrl+V`
cola na carta atual, e o menu de contexto oferece copiar o selecionado,
copiar todos e colar. Na colagem, escolha entre **acrescentar** e **substituir**,
com validação de todos os campos (evento, gatilho, valor, alvo, tipo,
atributo, escopo, referência de carta). Referências ao ID de origem
são explicitamente sinalizadas: não há troca silenciosa da carta
referenciada. Os atalhos só existem na tabela; cópia/cola de campos
de texto mantém seu comportamento original.

Os efeitos são cadastrados no Studio; o motor PS1 continua sujeito às
regras de compatibilidade de `compile_effects`. A colagem de um efeito
não implica que uma rotina MIPS inexistente tenha sido implementada.

### Ícones

**Inserir ícone** abre a composição de vários símbolos com busca,
prévia e **Aplicar** (não fecha). **OK** insere todos na posição do cursor
da descrição, mantendo os tokens `{icon:...}`/`{f8 0B XX}`.
**Cancelar** descarta a composição.

No perfil **Drop x15 com código original verificado**, os tokens
`{icon:vinculo_vida}` e `{icon:restaurar_lp}` passaram a mapear para
`F8 0B 49` e `F8 0B 4A`. O hook MIPS original aceitava nove ícones;
a comparação imediata foi ampliada para onze em ambos os runtimes
(722 e 740 IDs). A gravação de cada sprite e de sua CLUT exige
**células vazias ou previamente idênticas**, falhando em qualquer colisão.
Os ícones são exclusivamente glifos de **descrição**; não implementam por
si só curas ou o efeito Vínculo de Vida. Esses efeitos dependem de
suporte independente do motor de duelo.

### Estado de drops e descrições

O BIN de origem é um Drop x15 específico com hooks em endereços de
MIPS conhecidos. Os multiplicadores `x1`, `x3`, `x5`, `x15`,
`x30` **não foram liberados como controles funcionais** nesta etapa:
os hooks existentes selecionam e entregam várias recompensas usando
buffers RAM e rotinas de interface com limites próprios. Trocar uma
constante sem revisar armazenamento, UI, sorteio ponderado e rotina de
entrega não prova que 30 cartas sejam realmente concedidas.

No sistema atual de descrições, `build_test_disc` usa a política
**strict** por padrão. Um erro de armazenamento bloqueia a geração;
o usuário só pode escolher explicitamente a alternativa que preserva
descrições incompatíveis. No modo alternativo, cartas novas podem
receber texto abreviado; isso é indicado no manifesto e **não equivale
a uma exportação fiel**. É necessário validar a janela de descrição
em ePSXe com uma imagem BIN/CUE real e verificar relatórios de
ponteiros, comprimentos e diferenças por ID.

## Testes e riscos pendentes

Os testes automáticos verificam persistência, edição em massa atômica,
rollback em falha de IO, validação de preços e seleção, transferência
de efeitos, integridade dos tokens e configuração do hook MIPS para
dois glifos novos. A suíte completa do GitHub Actions cobre as rotinas
existentes, mas **não prova o comportamento em PS1**.

Para declarar os glifos funcionais em jogo, testar um BIN gerado com
ambos os ícones, conferir `WA_MRG.MRG` e visualizá-los na descrição
no ePSXe. Para drops `x30`, será necessário ampliar o sistema de
sorteio, inventário e apresentação com verificação dinâmica.
