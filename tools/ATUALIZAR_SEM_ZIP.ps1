# Migração inicial sem ZIP manual para versões antigas do Studio FM.
# Requer PowerShell 5.1+, conexão ao GitHub e Studio fechado.
param([string]$Pasta = (Get-Location).Path)
$ErrorActionPreference = 'Stop'
$repo = 'guibatoni/yu-gi-oh-studio-fm'
$Pasta = [IO.Path]::GetFullPath($Pasta)
if (-not (Test-Path -LiteralPath $Pasta -PathType Container)) { throw "Pasta não existe: $Pasta" }
$python = Test-Path -LiteralPath (Join-Path $Pasta 'app.py') -PathType Leaf
$windows = Test-Path -LiteralPath (Join-Path $Pasta 'FM-Mod-Studio.exe') -PathType Leaf
if (-not ($python -or $windows)) {
  throw "A pasta não parece conter o Studio. Informe -Pasta 'C:\\caminho\\do\\Studio'."
}
if ($python) { $nome = 'FM-Mod-Studio-Source.zip' }
else { $nome = 'FM-Mod-Studio-Windows.zip' }
Write-Host "Atualizando: $Pasta" -ForegroundColor Cyan
Write-Host "Modo: $nome. Nenhum arquivo BIN/CUE, projeto ou backup será copiado para a atualização."
$confirm = Read-Host 'O Studio está fechado? Deseja instalar a versão estável mais recente? (S/N)'
if ($confirm -notin @('S', 's', 'SIM', 'sim')) { Write-Host 'Cancelado'; exit 0 }
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$headers = @{ 'User-Agent' = 'FM-Studio-Migrador/1.0.0' }
$release = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/releases/latest" -Headers $headers
if ($release.draft -or $release.prerelease -or ($release.tag_name -notmatch '^studio-v[0-9]+\.[0-9]+\.[0-9]+$')) { throw 'Release não é uma versão estável válida.' }
$assets = @($release.assets)
$pack = $assets | Where-Object { $_.name -eq $nome } | Select-Object -First 1
$checksum = $assets | Where-Object { $_.name -eq ($nome + '.sha256') } | Select-Object -First 1
if (-not $pack -or -not $checksum) { throw "Release sem o pacote $nome ou SHA-256." }
$prefix = "https://github.com/$repo/releases/download/$($release.tag_name)/"
if (-not $pack.browser_download_url.StartsWith($prefix) -or -not $checksum.browser_download_url.StartsWith($prefix)) {
  throw 'URLs da versão não correspondem ao repositório oficial.'
}
$temp = Join-Path ([IO.Path]::GetTempPath()) ('fmstudio-migrar-' + [guid]::NewGuid().ToString('N'))
New-Item -Path $temp -ItemType Directory -Force | Out-Null
try {
  $zip = Join-Path $temp $nome
  $shaFile = Join-Path $temp ($nome + '.sha256')
  Invoke-WebRequest -Uri $pack.browser_download_url -Headers $headers -OutFile $zip -UseBasicParsing
  Invoke-WebRequest -Uri $checksum.browser_download_url -Headers $headers -OutFile $shaFile -UseBasicParsing
  $line = (Get-Content -LiteralPath $shaFile -Raw).Trim()
  if ($line -notmatch '^([a-fA-F0-9]{64})(\s+\*?[-.A-Za-z0-9]+)?$') { throw 'Manifesto SHA-256 inválido.' }
  if ($Matches[2] -and $Matches[2].TrimStart(' ', '*') -ne $nome) { throw 'Checksum pertence a outro arquivo.' }
  $expected = $Matches[1].ToLowerInvariant()
  $actual = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($expected -ne $actual) { throw 'Falha no SHA-256. Instalação cancelada.' }
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $archive = [IO.Compression.ZipFile]::OpenRead($zip)
  try {
    $names = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $entries = @($archive.Entries)
    if ($entries.Count -gt 150) { throw 'Pacote possui arquivos demais.' }
    $rootFull = [IO.Path]::GetFullPath((Join-Path $temp 'stage'))
    foreach ($entry in $entries) {
      $name = $entry.FullName.Replace('\','/')
      if (-not $name -or $name.EndsWith('/') -or $name.StartsWith('/') -or $name.Contains('..') -or $name.Contains(':')) {
        throw "Entrada inválida: $name"
      }
      if (-not $names.Add($name)) { throw "Entrada duplicada: $name" }
      if ($name -match '\.(bin|cue|iso|img|sav|mcr|mcd)$' -or $name -match '(^|/)(projetos|backups|assets|base|exportacao)/') {
        throw "Conteúdo de usuário não é permitido: $name"
      }
      if ($python -and $name -notmatch '^(app\.py|FM_Mod_Studio\.pyw|updater_main\.py|fmstudio/[a-z_]+\.py|tools/[a-z_]+\.py|docs/[A-Za-z0-9_]+\.md|[A-Za-z0-9_-]+\.(bat|ps1|md|txt))$') {
        throw "Arquivo desconhecido: $name"
      }
      if ($windows -and $name -notin @('FM-Mod-Studio.exe','FM-Mod-Studio-Updater.exe','INICIAR.bat','LEIA-ME.txt')) {
        throw "Arquivo desconhecido: $name"
      }
    }
    if ($python -and (-not $names.Contains('app.py') -or -not $names.Contains('fmstudio/gui.py'))) { throw 'Pacote de fontes incompleto.' }
    if ($windows -and (-not $names.Contains('FM-Mod-Studio.exe') -or -not $names.Contains('FM-Mod-Studio-Updater.exe'))) { throw 'Pacote Windows incompleto.' }
  } finally { $archive.Dispose() }
  $stage = Join-Path $temp 'stage'
  Expand-Archive -LiteralPath $zip -DestinationPath $stage -Force
  $backup = Join-Path $Pasta ('.studio-app-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
  New-Item -Path $backup -ItemType Directory -Force | Out-Null
  $modified = @()
  try {
    foreach ($name in $names) {
      $rel = $name.Replace('/', [IO.Path]::DirectorySeparatorChar)
      $src = Join-Path $stage $rel
      $dst = Join-Path $Pasta $rel
      $old = Join-Path $backup $rel
      $parent = Split-Path $dst -Parent
      if (-not (Test-Path -LiteralPath $parent)) { New-Item -Path $parent -ItemType Directory -Force | Out-Null }
      $wasThere = Test-Path -LiteralPath $dst
      if ($wasThere) {
        $oldParent = Split-Path $old -Parent
        if (-not (Test-Path -LiteralPath $oldParent)) { New-Item -Path $oldParent -ItemType Directory -Force | Out-Null }
        Copy-Item -LiteralPath $dst -Destination $old -Force
      }
      Copy-Item -LiteralPath $src -Destination $dst -Force
      $modified += [PSCustomObject]@{ dest = $dst; old = $old; existed = $wasThere }
    }
  } catch {
    [array]::Reverse($modified)
    foreach ($m in $modified) {
      if ($m.existed) { Copy-Item -LiteralPath $m.old -Destination $m.dest -Force }
      else { Remove-Item -LiteralPath $m.dest -Force -ErrorAction SilentlyContinue }
    }
    throw
  }
  Write-Host "Atualizado: $($release.tag_name)" -ForegroundColor Green
  Write-Host "Backup do aplicativo anterior: $backup"
  Write-Host 'A partir de agora use o botão Atualizar; não será preciso baixar ZIP manualmente.'
} finally {
  Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}
