# Yu-Gi-Oh Studio Card FM v0.6.2 — Editor visual de Forbidden Memories (PS1)

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

| Recurso | Estado na v0.3 |
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

### Atualizações diretas — correção v0.6.2

O botão **⟳ Atualizar** agora funciona tanto no **Python** (`INICIAR_FM_MOD_STUDIO.bat` / `.pyw`), quanto no **EXE compilado**. No Python ele instala o pacote `FM-Mod-Studio-Source.zip`; no EXE instala `FM-Mod-Studio-Windows.zip`. Ambos exigem `.sha256` no GitHub Release.

**Condição obrigatória:** o repositório público `guibatoni/yu-gi-oh-studio-fm` precisa existir e ter ao menos um GitHub Release publicado. Antes disso, o botão avisa que falta publicar o projeto, em vez de tentar atualizar arquivos inexistentes. `PUBLICAR_GITHUB.bat` clona o repositório existente, envia o código e a tag `studio-v0.6.2` para iniciar GitHub Actions.

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
