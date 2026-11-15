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

# Yu-Gi-Oh Studio Card FM v0.9.0 — Editor visual de Forbidden Memories (PS1)

Editor gráfico para **Windows**, em português, para criar projetos de MOD de *Yu-Gi-Oh! Forbidden Memories* sem alterar sua imagem original. Desenvolvido em Python/Tkinter e sem dependências externas para executar.

**Status real:** aplicativo editor funcional, porém **ainda NÃO produz um BIN/CUE jogável**. Estatísticas podem ser exportadas em uma cópia auxiliar do `SLUS_014.11`; os efeitos personalizados são **planejados e simulados no editor**, não executados pelo motor de PS1. Nomes/descrições também são metadados até termos o encoder de texto do jogo. Esta distinção é intencional para evitar corromper sua imagem X15.

## Abrir o aplicativo

1. Extraia todo o ZIP para uma pasta de sua escolha no Windows.
2. Dê dois cliques em `INICIAR_FM_MOD_STUDIO.bat` (recomendado; mostra erros se houver). Outra opção é `FM_Mod_Studio.pyw`.
3. Clique **Novo projeto**, informe um nome e escolha onde salvá-lo.
4. Clique **Importar CSVs** e escolha a pasta que já geramos na etapa anterior:

   `D:\Downloads\FM_Original_PS1_v0.1.0_Kit_Desenvolvimento\analysis\tabelas`

   Precisa conter `cartas.csv` e `fusoes.csv`. A importação leva também outras tabelas presentes na mesma pasta. Se preferir, use **Importar BIN / CUE** e selecione sua cópia do jogo; o aplicativo fará a extração diretamente.
5. Clique nas cartas e edite livremente. **Não aparece mais pergunta de salvamento ao trocar de carta.** Os valores ficam pendentes na memória, inclusive se você visitar outras abas. Escolha uma cor em **Cor do nome** para colorir a prévia e a biblioteca. Ao terminar, clique em **Salvar projeto** (ou `Ctrl+S`) para gravar todas as cartas e efeitos de uma vez com backup.
6. Na aba **Efeitos**, selecione **+ Adicionar efeito**. Exemplo: `Ao invocar` → `Aumentar ATK` → `Próprio monstro` → `500`; experimente no **Simulador**.
7. Opcionalmente, use **Importar arte PNG (prévia)** para associar uma imagem local à carta. Ela não será gravada no PS1.
8. Na aba **Fusões originais**, veja as fusões relacionadas à carta. As receitas são **somente leitura** e preservadas com verificação de hash.
9. Use **Salvar projeto** antes de **Exportar alterações**. Abra a pasta `exportacao/` criada dentro de seu projeto.

### Para exportar também uma cópia auxiliar do executável

Ao importar diretamente um `.BIN/.CUE`, o programa extrai e vincula automaticamente o SLUS para o projeto. Se você importou **somente CSVs**, clique **Vincular SLUS** e selecione o arquivo **da mesma imagem utilizada na extração**, por exemplo:

`D:\Downloads\FM_Original_PS1_v0.1.0_Kit_Desenvolvimento\FM_Original_PS1_v0.1\analysis\extracted\SLUS_014.11`

Antes de permitir alterações binárias, o programa verifica todos os 722 registros e, quando disponível, o SHA-256 do relatório de extração. Se houver divergência, a operação é bloqueada.

### O que é editável hoje

| Recurso | Estado na v0.9.0 |
|---|---|
| Buscar as 722 cartas | Funcional por número e nome personalizado |
| ATK / DEF | Editável, valida múltiplos de 10 e pode gerar SLUS auxiliar |
| Tipo / atributo / nível / estrelas guardiãs | Editáveis, exportáveis em SLUS auxiliar |
| Nome / descrição / cor do nome | Editável como metadado; cor em prévia e biblioteca, **sem gravação no jogo** |
| Arte PNG | Importação e prévia local; **sem gravação no jogo** |
| Eventos/efeitos | Edição pendente até salvar, simulação local; **sem execução no jogo** |
| Fusões | Consultáveis, preservadas; **não editáveis** |
| Importar `.BIN/.CUE` ou CSVs | Funcional para estrutura alvo `SLUS-01411`, sujeita a modificação X15 |
| Exportar BIN/CUE jogável | **Não implementado** |
| Gerar EXE Windows | Script fornecido; o ZIP **não contém EXE pré-compilado** |

### O que há na pasta `exportacao/`

- `alteracoes_cartas.json` — diferenças em cartas (inclui campos de texto e numéricos).
- `efeitos_planejados.json` — definições dos efeitos; declara que são apenas para simulação.
- `artes_referencia.json` — relação das imagens PNG vinculadas, somente como referência visual.
- `manifesto.json` — resumo da exportação e aviso de compatibilidade.
- `mudancas_binarias.json` — **apenas se** houve alterações numéricas e SLUS foi vinculado, com offsets e bytes antes/depois.
- `build_local/SLUS_014.11` — **apenas se** houve alterações numéricas e SLUS foi vinculado. Cópia local para posterior repack do disco; **não é imagem jogável** e não deve ser distribuída como jogo.

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
