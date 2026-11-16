## v1.4.24 — Exibição do tipo God 24

No perfil Drop x15, a opção **PS1: Tipo God no baú (teste)** ativa o
rótulo God e o ícone 16×16 nos detalhes da carta. O interpretador separa
os comandos de tipo dos comandos de estrela guardiã. O exportador usa
uma célula vazia da textura de boot e confirma a exibição por releitura
do SLUS e do WA_MRG na cópia BIN/CUE. A fonte do rótulo é a do jogo.

## v1.4.10 — Fonte de glifos de mods

Os endereços gráficos no WA_MRG não possuem garantia de slots livres em
qualquer MOD. O exportador considera apenas códigos 0x27–0x30 para teste
visual, verifica todos os 16×16 pixels zerados e não sobregrava conteúdo
ocupado. Falta de espaço omite o glifo, sem bloquear patches independentes
de estatísticas ou o valor experimental de tipo God 24. A UI deixa claro
que o desenho ainda é experimental e não substitui o ícone de tipo.

## v1.4.8 — Experiência de campo God24 no BIN

A tabela codifica cada tipo em cinco bits e portanto permite escrever o
número **24**. A interface solicita autorização explícita para UMA carta
#001–#722: gravação e readback são verificáveis (incluindo ATK/DEF).
A categoria Deus permanece experimental: o motor original foi concebido
para vinte tipos de monstros mais quatro categorias especiais e não foi
modificado para garantir que 24 atue como criatura. Ícone experimental
continua na descrição, não no rótulo do tipo. A experiência pode não
funcionar no ePSXe; não substitua a fonte do jogo.

## v1.4.0 — Motor de habilidades inéditas e deck experimental

- Confirmado no ePSXe: alteração ATK/DEF e compatibilidade de Equip no Drop X15.
- Simulador apenas: auras, cemitério por tipo, imunidades, indestrutibilidade,
  ataques 2x/3x, perfuração, ataque direto mesmo com campo inimigo e limites
  individuais de cópias de 1–40.
- Experimental no BIN: limite GLOBAL de cópias por ID 1–40, somente quando
  há uma comparação MIPS única slti/sltiu <3 seguida de branch. Não modifica
  o tamanho físico de 40 cartas, nem regras especiais de Exodia; sem teste real.
- Rituais: controles ocultos nesta etapa. Planos anteriores preservados e
  não exportados sem ativação explícita pela configuração ps1_rituals_enabled.
- Diagnóstico MIPS: analisa regiões e hashes e lista efeitos cadastrados;
  não instala handlers de habilidades.

---

## v1.3.0 — Efeitos nativos adicionais

O Studio pode gravar diretamente alguns efeitos existentes no motor de Forbidden Memories:

| Efeito | Formato | Status |
| --- | --- | --- |
| Alvos para Equip original | WA_MRG.MRG, tabelas por terreno | Confirmado no ePSXe no Drop X15 |
| Ritual original (3 tributos + resultado) | WA_MRG.MRG +0x34800, registros de 5 u16 | Testado em BIN sintético; jogo real pendente |
| Limites de ATK das Traps #681–686 | SLUS_014.11, seis bytes em 0x8B724 | Apenas layout retail; jogo real pendente |
| Bônus por terreno/tipo original | SLUS_014.11, s8[20x6] em 0x811D4 | Apenas tabela stock ±500; jogo real pendente |

Cada modificação é conferida por releitura. A escrita de bytes não prova
execução: um MOD com rotina MIPS modificada pode ignorar a tabela.

Para Ritual, escolha uma carta Ritual com receita presente na base e informe
três tributos e o resultado. Para Trap, selecione #681–#686 e configure o
máximo de ATK em múltiplos de 100 mantendo os limites em ordem. Para terreno,
escolha Forest, Wasteland, Mountain, Sogen, Umi ou Yami, tipo original (0–19)
e bônus de ATK/DEF em múltiplos de 10.

As fusões originais são preservadas. Efeitos personalizados inéditos seguem
somente no simulador, aguardando rotinas MIPS.

---

# Compatibilidade PlayStation 1 — Studio FM v1.1.0

## Objetivo

O objetivo final é que um projeto Studio possa gerar uma imagem **BIN/CUE** de Yu-Gi-Oh! Forbidden Memories (NTSC-U, SLUS-01411) executável no **ePSXe**, com o maior número possível de recursos. A implementação é **incremental e verificável**; gerar uma imagem que inicializa não prova que todos os efeitos funcionam.

A imagem original precisa ser fornecida localmente pelo usuário. Nunca enviamos BIN/CUE/SLUS/WA para GitHub. O Studio cria uma nova cópia da imagem preservando setores XA/MDEC e as fusões. Não extrapola espaço na tabela original nem altera o tamanho dos arquivos ISO9660.

## Recursos gravados no BIN/CUE experimental da v1.1.0

| Recurso | Condição de gravação | Validação feita |
| --- | --- | --- |
| ATK/DEF, nível, atributo, estrelas e tipos originais | Carta #1..#722; sem expansão God e sem tipos desconhecidos | Hash SLUS, bytes antes, tamanho |
| Nome da carta | Texto menor ou igual ao slot original; fonte original; string linear sem aliases | Mapa de glifos e terminador, sem realocação |
| Descrição | Texto curto com glifos originais, quebra de linha, `{f8 0A XX}` e `{f8 0B XX}` nativos; sem controles complexos | Banco e ponteiros originais, sem realocação |
| Arte principal e miniatura | PNG registrado de #1..#722, WA_MRG com SHA-256 conhecido; paletas originais preservadas | Pixels 8bpp e verificação por releitura |
| Disco | Imagem fonte MODE2/2352, executável corresponde ao projeto | EDC/ECC, reextração ISO9660, tamanho e setor |
| Fusões originais | Tabelas preservadas | Hash do arquivo de fusões do projeto |

**Importante:** o ajuste de arte usa cores aproximadas à paleta da carta já presente no jogo, para não recolorir faixas laterais e inferiores que compartilham a mesma paleta. A qualidade pode diferir da prévia PNG.

## Recursos que ainda NÃO executam no PS1

- Novas cartas #723+, novas tabelas de cartas e fonte/sprite para novas IDs.
- Tipo God como tipo jogável extra com regras e interface próprias.
- Cores de nome por raridade, customização visual completa de texto, ícones não nativos.
- Auras de ATK/DEF, efeitos dinâmicos por campo/deck/cemitério, descarte e dano a monstro.
- Múltiplos ataques, dano perfurante, não bloqueável, ataque no primeiro turno, perda de LP por ataque.
- Imunidade a mágicas/armadilhas, indestrutível, encantamentos e regras especiais de deck.
- Mudanças de rituais, equipamentos, drops, IA e novas receitas de fusão (as atuais continuam originais).

O relatório **`exportacao/compatibilidade_ps1.json`** discrimina por projeto o que é gravável e o que exige novas rotinas de motor. O `*.json` ao lado de cada BIN/CUE também lista exatamente os setores, os nomes, as descrições e as regiões de arte alterados. Nada marcado como pendente é tratado como recurso jogável.

## Como testar no ePSXe

1. Abra seu projeto; salve todas as alterações com **Ctrl+S**.
2. Selecione **Projeto / Exportação → Compatibilidade PS1** e verifique o relatório. Na v1.1.1, após **Exportar alterações**, o Studio oferece a geração imediata do BIN/CUE; você também pode usar **Gerar jogo BIN/CUE** na barra principal.
3. Clique **Gerar BIN/CUE de teste**, escolha o **mesmo disco** importado para o projeto e confirme a geração **parcial**.
4. Abra o `.cue` da pasta `exportacao/teste_ps1` no emulador; dependendo do menu do ePSXe, pode ser necessário selecionar o `.bin` correspondente.
5. Teste primeiro uma carta original com ATK/DEF alterado, depois o nome curto e sua arte. Revise nomes/descritivos e animações in-game; o teste automatizado não substitui o teste do emulador.

O botão **Atualizar** baixa o programa pelo GitHub Releases; não distribui dados de jogo.

## Próximas fases do motor PS1

1. **Identidade binária:** comparar e identificar todos os desvios do `SLUS_014.11` da imagem Drop X15 em relação à versão base, incluindo overlays, segmentos de RAM e limites de memória. Recusar patches MIPS em builds desconhecidas sem guardas de bytes.
2. **Instrumentar combate:** documentar callbacks de entrada/saída de campo, cemitério, compra, ataque e destruição, com testes controlados no ePSXe.
3. **Interpretador de efeitos MIPS:** compilar definições declarativas do Studio em dados carregáveis, preservar estado de buffs sem acumulação, recalcular após eventos e aplicar proteção/ataques com regras explícitas.
4. **Expandir tabelas/IDs:** realocar estatísticas, artes, nomes, deckbuilder, biblioteca e referências de fusão, com IDs >722, tipos extras e save compatibility. Demandará mudança de código, espaço de RAM, CD e limites de UI.
5. **Ícones/fontes e cores:** adicionar glifos 16×16, mapear controle de texto, garantir que cada elemento suporte cores/paleta sem interferir em outros textos.
6. **Release jogável completa:** validar no emulador, produzir testes de regressão por tipo de efeito, salvar/restaurar partidas e somente então habilitar build completa.

### Pesquisas técnicas de referência

- `https://github.com/Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled/blob/master/notes/more-cards.md` — reestruturação das tabelas no port PC (não compatível diretamente com PS1).
- `https://github.com/Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled/blob/master/tools/pc/text_listing.py` — banco de textos e comandos de formatação.
- `https://github.com/Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled/blob/master/tools/pc/extract_images.py` — layout de artes e paletas.
- `https://github.com/gonzaloberteri/ygofm-decomp` — referência de builds correspondentes do PS1.

Nada aqui autoriza distribuir o jogo comercial. Sempre distribua apenas código e patches sobre cópias legítimas do usuário.
