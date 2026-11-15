# Botão Atualizar — v0.6.2

## Pré-requisitos

1. O repositório público `guibatoni/yu-gi-oh-studio-fm` já foi criado e precisa receber o código.
2. Deve existir pelo menos um Release estável publicado por tag `studio-vX.Y.Z`.
3. A release deve conter **4 arquivos**:
   - `FM-Mod-Studio-Windows.zip`
   - `FM-Mod-Studio-Windows.zip.sha256`
   - `FM-Mod-Studio-Source.zip`
   - `FM-Mod-Studio-Source.zip.sha256`

`PUBLICAR_GITHUB.bat` envia o código e uma tag a partir de um clone limpo; só publica código após confirmação explícita. Não coloca ROMs, BIOS ou arquivos de jogo no repositório.

## Funcionamento

O Studio verifica `https://api.github.com/repos/guibatoni/yu-gi-oh-studio-fm/releases/latest` em uma thread secundária. Detecta automaticamente seu tipo de instalação: executável (`.exe`) ou Python (`.bat`, `.pyw`). Baixa **somente** o ZIP correspondente, verifica o SHA-256, limita tamanho, rejeita qualquer nome de arquivo não listado no aplicativo, rejeita caminhos relativos e links e realiza substituição com backup e restauração em caso de erro. O instalador roda separadamente em pasta temporária, espera o editor encerrar e depois o reabre.

**Dados protegidos:** `projetos/`, `base/`, `analysis/`, `original/`, `exportacao/`, `backups/`, imagens importadas, ROMs e saves. Somente arquivos de código do editor são substituídos.

## Erros comuns

- `404`: repositório ou primeiro Release ainda não publicado — criar e publicar com `PUBLICAR_GITHUB.bat` e aguardar o workflow.
- `Pacote ... não possui`: GitHub Release incompleto, conferir 4 anexos.
- `SHA-256 inválido`: download divergente, atualização cancelada sem alterar a instalação.
- `Pasta inválida`: ZIP do tipo errado para a instalação, ou arquivo do aplicativo ausente.

## Primeira instalação

Quem já usa v0.6.0 via Python precisará **aplicar esta v0.6.2 manualmente uma vez**, porque a v0.6.0 não possuía instalador Python. Feche o aplicativo; faça backup; extraia a nova versão por cima da pasta do aplicativo, sem apagar suas pastas de projeto. Depois disso, o botão estará preparado para atualizações seguintes, **desde que o GitHub Release esteja disponível**.

## Publicação de versões seguintes

Altere a versão de `fmstudio/__init__.py`, atualize `$tag` em `PUBLICAR_GITHUB.ps1`, faça commit e envie a tag. O workflow compila os EXEs e cria os dois pacotes com SHA-256. A atualização do código em si continua dependente de um workflow publicado com sucesso. Não é compatível com Releases privados sem autenticação.
