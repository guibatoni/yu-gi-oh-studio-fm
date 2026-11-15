# Publica apenas arquivos do Studio, sem jogos, saves, mods pessoais ou backups.
# Compatível com PowerShell 5.1 e PowerShell 7. Usa clone limpo para evitar históricos divergentes.
$ErrorActionPreference = 'Continue' # PowerShell 5.1 pode tratar stderr normal de gh/git como NativeCommandError; cada chamada é checada por exit code
Set-Location -LiteralPath $PSScriptRoot
$repo = 'guibatoni/yu-gi-oh-studio-fm'
$tag = 'studio-v0.6.2'
Write-Host "Yu-Gi-Oh Studio Card FM $tag" -ForegroundColor Cyan
Write-Host "GitHub: https://github.com/$repo"
Write-Warning 'O repositório é público. Publicaremos apenas CÓDIGO, sem ROMs, BIOS, dados extraídos, imagens de cartas ou projetos privados.'
$ok = Read-Host 'Publicar código e criar GitHub Release? (S/N)'
if ($ok -notin @('S', 's', 'SIM', 'sim')) { Write-Host 'Cancelado.'; exit 0 }
if (-not (Get-Command gh.exe -ErrorAction SilentlyContinue)) { throw 'Instale GitHub CLI: https://cli.github.com/' }
if (-not (Get-Command git.exe -ErrorAction SilentlyContinue)) { throw 'Instale Git for Windows: https://git-scm.com/' }
& gh auth status
if ($LASTEXITCODE -ne 0) {
    & gh auth login --web
    if ($LASTEXITCODE -ne 0) { throw 'Autenticação do GitHub não concluída.' }
}
& gh repo view $repo --json name --jq .name
if ($LASTEXITCODE -ne 0) { throw 'O repositório indicado não está disponível. Verifique sua conta e o nome.' }
$arquivos = @(
  '.gitignore', '.github/workflows/windows-exe.yml',
  'README.md', 'LEIA-ME.txt', 'INICIAR.bat', 'INICIAR_FM_MOD_STUDIO.bat',
  'FM_Mod_Studio.pyw', 'app.py', 'updater_main.py', 'CRIAR_EXE_WINDOWS.bat',
  'PUBLICAR_GITHUB.bat', 'PUBLICAR_GITHUB.ps1', 'INSTALAR_CORRECAO_NO_STUDIO_ATUAL.bat',
  'fmstudio/__init__.py', 'fmstudio/core.py', 'fmstudio/disc.py',
  'fmstudio/drafts.py', 'fmstudio/gui.py', 'fmstudio/updates.py',
  'fmstudio/deep_extract.py', 'fmstudio/tables.py',
  'tools/package_source.py', 'tools/instalar_correcao.py',
  'tests/test_core.py', 'tests/test_deep_extract.py',
  'tests/test_drafts.py', 'tests/test_updates.py', 'tests/gui_smoke.py',
  'docs/HISTORICO.md', 'docs/ORIGEM_E_VALIDACAO.md',
  'docs/ROADMAP_EFEITOS.md', 'docs/ATUALIZACOES_GITHUB.md',
  'docs/MIGRACAO_REPOSITORIO.md'
)
$temporario = Join-Path $env:TEMP ('fmstudio-publicacao-' + [guid]::NewGuid().ToString('N'))
try {
    & gh repo clone $repo $temporario -- --depth 1
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível clonar o repositório.' }
    foreach ($rel in $arquivos) {
        $origem = Join-Path $PSScriptRoot ($rel.Replace('/', [IO.Path]::DirectorySeparatorChar))
        $destino = Join-Path $temporario ($rel.Replace('/', [IO.Path]::DirectorySeparatorChar))
        if (-not (Test-Path -LiteralPath $origem -PathType Leaf)) {
            throw "Arquivo de código obrigatório ausente: $rel"
        }
        $pasta = Split-Path -Parent $destino
        if (-not (Test-Path -LiteralPath $pasta)) { New-Item -ItemType Directory -Path $pasta -Force | Out-Null }
        Copy-Item -LiteralPath $origem -Destination $destino -Force
    }
    & git -C $temporario add -- $arquivos
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível preparar os arquivos.' }
    & git -C $temporario diff --cached --quiet
    if ($LASTEXITCODE -eq 1) {
        & git -C $temporario commit -m 'release: Studio v0.6.2 e atualizador GitHub'
        if ($LASTEXITCODE -ne 0) { throw 'Commit falhou. Configure git user.name e user.email.' }
        & git -C $temporario push origin HEAD:main
        if ($LASTEXITCODE -ne 0) { throw 'Push falhou. Verifique permissão ou alterações remotas.' }
    } elseif ($LASTEXITCODE -ne 0) { throw 'Falha ao verificar as alterações.' }
    $tagExiste = & git -C $temporario ls-remote --tags origin "refs/tags/$tag"
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao verificar tag remota.' }
    if ($tagExiste) {
        Write-Host "Tag $tag já existe; não será recriada." -ForegroundColor Yellow
    } else {
        & git -C $temporario tag $tag
        if ($LASTEXITCODE -ne 0) { throw 'Não foi possível criar a tag.' }
        & git -C $temporario push origin $tag
        if ($LASTEXITCODE -ne 0) { throw 'Não foi possível publicar a tag.' }
    }
    Write-Host "Código enviado: https://github.com/$repo" -ForegroundColor Green
    Write-Host "Build: https://github.com/$repo/actions"
    Write-Host "Releases: https://github.com/$repo/releases"
    Write-Host 'Aguarde a compilação no GitHub Actions antes de usar Atualizar.' -ForegroundColor Yellow
} finally {
    if (Test-Path -LiteralPath $temporario) {
        Remove-Item -LiteralPath $temporario -Recurse -Force -ErrorAction SilentlyContinue
    }
}
