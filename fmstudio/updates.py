"""Atualizações estáveis via GitHub Releases para Windows EXE e código Python.

O aplicativo usa um instalador externo; projetos/ROMs nunca entram no pacote.
Pacotes são verificados por SHA-256 e lista explícita de caminhos aceitos.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import __version__

REPO = 'guibatoni/yu-gi-oh-studio-fm'
API = f'https://api.github.com/repos/{REPO}/releases/latest'
REPO_URL = f'https://github.com/{REPO}'
BUNDLE_NAME = 'FM-Mod-Studio-Windows.zip'
SUM_NAME = BUNDLE_NAME + '.sha256'
SOURCE_BUNDLE_NAME = 'FM-Mod-Studio-Source.zip'
SOURCE_SUM_NAME = SOURCE_BUNDLE_NAME + '.sha256'
PROGRAM_NAME = 'FM-Mod-Studio.exe'
UPDATER_NAME = 'FM-Mod-Studio-Updater.exe'
WINDOWS_FILES = frozenset({PROGRAM_NAME, UPDATER_NAME, 'INICIAR.bat', 'LEIA-ME.txt'})
SOURCE_FILES = frozenset({
    'fmstudio/campaign_quests.py', 'fmstudio/ps1_campaign_quests.py', 'fmstudio/ps1_drop_count.py', 'fmstudio/ps1_equip_bonus.py', 'fmstudio/ps1_magic_values.py', 'fmstudio/magic_gui.py', 'fmstudio/ps1_frame_colors.py', 'fmstudio/frame_gui.py', 'fmstudio/ui_theme.py', 'fmstudio/ui_prefs.py', 'fmstudio/ui_nav.py', 'fmstudio/ui_shell.py', 'fmstudio/card_batch.py', 'fmstudio/card_batch_gui.py', 'fmstudio/deck_summary.py', 'fmstudio/build_info.py', 'fmstudio/card_search.py', 'fmstudio/card_picker.py', 'fmstudio/mips_asm.py', 'fmstudio/ps1_life_splash.py', 'fmstudio/ps1_lifelink.py', 'fmstudio/ps1_menu_wallpaper.py', 'fmstudio/wallpaper_gui.py', 'fmstudio/themed_deck.py', 'fmstudio/themed_deck_gui.py', 'fmstudio/ps1_starter_choice.py', 'fmstudio/card_subtypes.py', 'fmstudio/ps1_ai_tuning.py', 'fmstudio/ps1_hand_bonus.py', 'fmstudio/ps1_subtypes.py', 'fmstudio/ps1_fixed_drop.py', 'fmstudio/ps1_debug_space.py', 'fmstudio/ps1_duel_hud.py', 'fmstudio/duel_hud_layout.py', 'fmstudio/starter_choice_gui.py', 'fmstudio/translate.py', 'fmstudio/translate_gui.py', 'fmstudio/i18n.py', 'fmstudio/ui_i18n.py', 'fmstudio/i18n_cat_a.py', 'fmstudio/i18n_cat_b.py', 'fmstudio/i18n_cat_c.py', 'fmstudio/i18n_cat_d.py', 'fmstudio/i18n_cat_e.py', 'fmstudio/i18n_cat_f.py', 'fmstudio/i18n_cat_g.py', 'fmstudio/i18n_cat_h.py',
    'fmstudio/ps1_campaign_quest_overlay_blob.py', 'fmstudio/quest_gui.py',
    'docs/QUESTS_CAMPANHA_PS1.md',
    'app.py', 'FM_Mod_Studio.pyw', 'updater_main.py',
    'fmstudio/png_pixels.py', 'fmstudio/ps1_image_optimizer.py', 'fmstudio/ps1_image_preview.py', 'fmstudio/ps1_card_title.py',
    'fmstudio/__init__.py', 'fmstudio/abilities.py', 'fmstudio/core.py', 'fmstudio/continuous.py', 'fmstudio/duel_engine.py', 'fmstudio/expanded.py', 'fmstudio/richtext.py', 'fmstudio/rarities.py',
    'assets/icons/perfurar.png', 'assets/icons/ataque_2x.png', 'assets/icons/ataque_3x.png',
    'assets/icons/nao_bloqueavel.png', 'assets/icons/infinito.png', 'assets/icons/anti_trap.png',
    'assets/icons/anti_magia.png', 'assets/icons/indestrutivel.png', 'assets/icons/god.png',
    'assets/icons/atlas_16x16.png', 'assets/icons/ataque_primeiro_turno.png',
    'fmstudio/disc_append.py', 'fmstudio/ps1_expansion.py', 'fmstudio/ps1_expansion_profile.py',
    'fmstudio/ps1_expanded_runtime_blob.py',
    'fmstudio/ps1_supreme.py', 'fmstudio/ps1_supreme_blob.py',
    'assets/icons/vinculo_vida.png', 'assets/icons/restaurar_lp.png',
    'fmstudio/disc_build.py', 'fmstudio/ps1_description_verify.py', 'fmstudio/ps1_content.py', 'fmstudio/ps1_compat.py', 'fmstudio/ps1_god_icon.py', 'fmstudio/ps1_god24_hook.py', 'fmstudio/ps1_god24_chest.py', 'fmstudio/ps1_god24_row_patch.py', 'fmstudio/ps1_god24_duel.py', 'fmstudio/ps1_god24_hand.py', 'tools/gerar_bin_teste.py', 'fmstudio/lab_gui.py', 'fmstudio/drafts.py',
    'fmstudio/disc.py', 'fmstudio/disc_verify.py', 'fmstudio/ps1_equip.py', 'fmstudio/ps1_equip_bitmap.py', 'fmstudio/ps1_native.py', 'fmstudio/ps1_effects_lab.py', 'fmstudio/tables.py', 'fmstudio/deep_extract.py',
    'fmstudio/gui.py', 'fmstudio/updates.py',
    'fmstudio/ps1_god24_play.py', 'fmstudio/ps1_god24_display.py',
    'fmstudio/ps1_runtime.py', 'fmstudio/ps1_runtime_blob.py', 'fmstudio/ps1_text.py',
    'fmstudio/duel_match.py', 'fmstudio/duel_ai.py', 'fmstudio/duel_gui.py', 'fmstudio/duel_rank.py', 'fmstudio/guardian.py',
    'fmstudio/mod_data.py', 'fmstudio/mod_gui.py', 'fmstudio/original_opponent_decks.py', 'fmstudio/campaign_generator.py', 'fmstudio/opponent_presets_39.py', 'fmstudio/ps1_mod.py', 'fmstudio/ps1_ai.py', 'fmstudio/ps1_lp_hud.py',
    'fmstudio/deck_generator.py', 'fmstudio/mod_tools_gui.py', 'fmstudio/passwords.py', 'fmstudio/ps1_economy.py', 'fmstudio/bulk_editor.py', 'fmstudio/bulk_gui.py', 'fmstudio/effects_transfer.py', 'fmstudio/icon_composer.py', 'fmstudio/ps1_rank_hud.py',
    'INICIAR.bat', 'INICIAR_FM_MOD_STUDIO.bat', 'CRIAR_EXE_WINDOWS.bat',
    'PUBLICAR_GITHUB.bat', 'PUBLICAR_GITHUB.ps1', 'LEIA-ME.txt',
    'docs/EXPANSAO_PS1_740.md', 'tools/verify_expanded_bau_mips.py',
    'README.md', 'docs/HISTORICO.md', 'docs/CORRECAO_DOACAO_QUESTS_PS1.md', 'docs/CORRECAO_QUESTS_DOAR_E_DUELAR_QOV5.md', 'docs/CORRECAO_QUESTS_QOV7_DROP_X15.md', 'docs/ATUALIZACOES_GITHUB.md',
    'docs/ORIGEM_E_VALIDACAO.md', 'docs/ROADMAP_EFEITOS.md',
    'docs/MIGRACAO_REPOSITORIO.md', 'docs/COMPAT_PS1.md', 'docs/EXPANSAO_722_GOD_TEXTO.md', 'docs/CLASSES_E_CORES.md', 'docs/EFEITOS_EXEMPLOS.md', 'docs/HABILIDADES_RAPIDAS.md', 'docs/OTIMIZACAO_PS1_PILLOW.md', 'docs/ECONOMIA_PS1.md', 'docs/EDITOR_MULTIPLO_PS1.md',
})
SOURCE_REQUIRED = frozenset({
    'fmstudio/campaign_quests.py', 'fmstudio/ps1_campaign_quests.py', 'fmstudio/ps1_drop_count.py', 'fmstudio/ps1_equip_bonus.py', 'fmstudio/ps1_magic_values.py', 'fmstudio/magic_gui.py', 'fmstudio/ps1_frame_colors.py', 'fmstudio/frame_gui.py', 'fmstudio/ui_theme.py', 'fmstudio/ui_prefs.py', 'fmstudio/ui_nav.py', 'fmstudio/ui_shell.py', 'fmstudio/card_batch.py', 'fmstudio/card_batch_gui.py', 'fmstudio/deck_summary.py', 'fmstudio/build_info.py', 'fmstudio/card_search.py', 'fmstudio/card_picker.py', 'fmstudio/mips_asm.py', 'fmstudio/ps1_life_splash.py', 'fmstudio/ps1_lifelink.py', 'fmstudio/ps1_menu_wallpaper.py', 'fmstudio/wallpaper_gui.py', 'fmstudio/themed_deck.py', 'fmstudio/themed_deck_gui.py', 'fmstudio/ps1_starter_choice.py', 'fmstudio/card_subtypes.py', 'fmstudio/ps1_ai_tuning.py', 'fmstudio/ps1_hand_bonus.py', 'fmstudio/ps1_subtypes.py', 'fmstudio/ps1_fixed_drop.py', 'fmstudio/ps1_debug_space.py', 'fmstudio/ps1_duel_hud.py', 'fmstudio/duel_hud_layout.py', 'fmstudio/starter_choice_gui.py', 'fmstudio/translate.py', 'fmstudio/translate_gui.py', 'fmstudio/i18n.py', 'fmstudio/ui_i18n.py', 'fmstudio/i18n_cat_a.py', 'fmstudio/i18n_cat_b.py', 'fmstudio/i18n_cat_c.py', 'fmstudio/i18n_cat_d.py', 'fmstudio/i18n_cat_e.py', 'fmstudio/i18n_cat_f.py', 'fmstudio/i18n_cat_g.py', 'fmstudio/i18n_cat_h.py',
    'fmstudio/ps1_campaign_quest_overlay_blob.py', 'fmstudio/quest_gui.py',
    'fmstudio/png_pixels.py', 'fmstudio/ps1_image_optimizer.py', 'fmstudio/ps1_image_preview.py', 'fmstudio/ps1_card_title.py',
    'fmstudio/disc_append.py', 'fmstudio/ps1_expansion.py', 'fmstudio/ps1_expansion_profile.py',
    'fmstudio/ps1_expanded_runtime_blob.py',
    'fmstudio/ps1_supreme.py', 'fmstudio/ps1_supreme_blob.py',
    'fmstudio/ps1_god24_play.py', 'fmstudio/ps1_god24_display.py',
    'fmstudio/ps1_runtime.py', 'fmstudio/ps1_runtime_blob.py', 'fmstudio/ps1_text.py',
    'fmstudio/duel_match.py', 'fmstudio/duel_ai.py', 'fmstudio/duel_gui.py', 'fmstudio/duel_rank.py', 'fmstudio/guardian.py',
    'fmstudio/mod_data.py', 'fmstudio/mod_gui.py', 'fmstudio/original_opponent_decks.py', 'fmstudio/campaign_generator.py', 'fmstudio/opponent_presets_39.py', 'fmstudio/ps1_mod.py', 'fmstudio/ps1_ai.py', 'fmstudio/ps1_lp_hud.py',
    'fmstudio/deck_generator.py', 'fmstudio/mod_tools_gui.py', 'fmstudio/passwords.py', 'fmstudio/ps1_economy.py', 'fmstudio/bulk_editor.py', 'fmstudio/bulk_gui.py', 'fmstudio/effects_transfer.py', 'fmstudio/icon_composer.py', 'fmstudio/ps1_rank_hud.py',
    'app.py', 'updater_main.py', 'fmstudio/__init__.py', 'fmstudio/gui.py',
    'fmstudio/core.py', 'fmstudio/abilities.py', 'fmstudio/continuous.py', 'fmstudio/duel_engine.py', 'fmstudio/expanded.py', 'fmstudio/richtext.py', 'fmstudio/rarities.py',
    'assets/icons/perfurar.png', 'assets/icons/ataque_2x.png', 'assets/icons/ataque_3x.png',
    'assets/icons/nao_bloqueavel.png', 'assets/icons/infinito.png', 'assets/icons/anti_trap.png',
    'assets/icons/anti_magia.png', 'assets/icons/indestrutivel.png', 'assets/icons/god.png',
    'assets/icons/atlas_16x16.png', 'assets/icons/ataque_primeiro_turno.png',
    'assets/icons/vinculo_vida.png', 'assets/icons/restaurar_lp.png',
    'fmstudio/disc_build.py', 'fmstudio/ps1_description_verify.py', 'fmstudio/disc_verify.py', 'fmstudio/ps1_god_icon.py', 'fmstudio/ps1_god24_hook.py', 'fmstudio/ps1_god24_chest.py', 'fmstudio/ps1_god24_row_patch.py', 'fmstudio/ps1_god24_duel.py', 'fmstudio/ps1_god24_hand.py', 'fmstudio/ps1_equip.py', 'fmstudio/ps1_equip_bitmap.py', 'fmstudio/ps1_native.py', 'fmstudio/ps1_effects_lab.py', 'fmstudio/ps1_content.py', 'fmstudio/ps1_compat.py', 'tools/gerar_bin_teste.py', 'fmstudio/lab_gui.py', 'fmstudio/updates.py', 'INICIAR_FM_MOD_STUDIO.bat',
})
MAX_ARCHIVE_BYTES = 200 * 1024 * 1024
MAX_FILE_BYTES = 200 * 1024 * 1024
MAX_EXTRACT_BYTES = 250 * 1024 * 1024
USER_AGENT = f'FM-Mod-Studio/{__version__}'
VERSION_RE = re.compile(r'^studio-v(\d+)\.(\d+)\.(\d+)$')


class UpdateError(Exception):
    pass


@dataclass(frozen=True)
class Release:
    version: str
    title: str
    notes: str
    zip_url: str
    hash_url: str
    kind: str = 'windows'


def installed_kind() -> str:
    """Detecta execução do EXE em oposição ao modo Python (.bat/.pyw)."""
    return 'windows' if getattr(sys, 'frozen', False) else 'source'


def asset_names(kind: str) -> tuple[str, str]:
    if kind == 'windows':
        return BUNDLE_NAME, SUM_NAME
    if kind == 'source':
        return SOURCE_BUNDLE_NAME, SOURCE_SUM_NAME
    raise UpdateError('Modalidade de instalação desconhecida.')


def parse_version(tag: str) -> tuple[int, int, int] | None:
    match = VERSION_RE.fullmatch(tag)
    return tuple(map(int, match.groups())) if match else None


def safe_github_asset_url(url: str) -> bool:
    from urllib.parse import urlsplit
    try:
        parts = urlsplit(url)
    except (ValueError, TypeError):
        return False
    return (parts.scheme == 'https' and parts.netloc == 'github.com' and
            parts.path.startswith(f'/{REPO}/releases/download/') and
            not parts.username and not parts.password and
            not parts.query and not parts.fragment)


def github_request(url: str, timeout: int = 12):
    req = urllib.request.Request(url, headers={
        'User-Agent': USER_AGENT, 'Accept': 'application/vnd.github+json',
        'Cache-Control': 'no-cache'})
    return urllib.request.urlopen(req, timeout=timeout)


def read_latest(fetch: Callable | None = None, *, kind: str | None = None) -> Release | None:
    """Obtém release mais recente, sem confundí-la com sucesso quando GitHub não existe."""
    fetch = fetch or github_request
    kind = kind or installed_kind()
    bundle, sum_name = asset_names(kind)
    try:
        with fetch(API) as response:
            data = json.loads(response.read(512 * 1024))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError(
                'Nenhuma versão foi encontrada no GitHub Releases.\n\n'
                'O código e a compilação precisam ser publicados no repositório oficial.\n'
                'Consulte: ' + REPO_URL + '/releases') from exc
        raise UpdateError(f'GitHub respondeu HTTP {exc.code}.') from exc
    except (ValueError, OSError, TimeoutError, json.JSONDecodeError) as exc:
        raise UpdateError(f'Não foi possível consultar o GitHub: {exc}') from exc
    if not isinstance(data, dict):
        raise UpdateError('Resposta inesperada da API GitHub.')
    if data.get('draft') or data.get('prerelease'):
        return None
    tag = data.get('tag_name', '')
    latest = parse_version(tag)
    if latest is None:
        raise UpdateError(f'Versão remota não reconhecida: {tag!r}.')
    if latest <= tuple(map(int, __version__.split('.'))):
        return None
    urls = {item.get('name'): item.get('browser_download_url') for item in data.get('assets', [])}
    zip_url, hash_url = urls.get(bundle), urls.get(sum_name)
    if not zip_url or not hash_url:
        raise UpdateError(
            f'A versão {tag} não possui {bundle} e seu .sha256. '
            'É necessário publicar novamente pelo workflow do GitHub Actions.')
    if not all(map(safe_github_asset_url, (zip_url, hash_url))):
        raise UpdateError('URLs da versão não correspondem ao repositório oficial.')
    return Release(tag, str(data.get('name', tag)), str(data.get('body') or ''),
                   zip_url, hash_url, kind)


def parse_checksum(content: str, *, bundle: str = BUNDLE_NAME) -> str:
    match = re.fullmatch(r'([0-9a-fA-F]{64})(?:\s+\*?' + re.escape(bundle) + r')?', content.strip())
    if match is None:
        raise UpdateError('Manifesto SHA-256 malformado.')
    return match.group(1).lower()


def allowed_source_member(name: str) -> bool:
    """Permite módulos futuros em pastas controladas; nunca arquivos pessoais/ROMs.

    Regex ancorada proíbe '..', barras invertidas, duplicatas e nomes arbitrários.
    A lista SOURCE_FILES continua explícita para gerar pacotes de Release.
    """
    if name in SOURCE_FILES:
        return True
    return bool(re.fullmatch(r'(?:fmstudio/[a-z][a-z0-9_]{0,63}\.py|'
                             r'assets/icons/[a-z0-9_-]{1,64}\.png|'
                             r'docs/[A-Za-z0-9_-]{1,80}\.md|'
                             r'tools/[a-z][a-z0-9_]{0,63}\.py)', name))


def validate_archive(archive: Path, kind: str = 'windows') -> set[str]:
    allow = WINDOWS_FILES if kind == 'windows' else SOURCE_FILES if kind == 'source' else None
    if allow is None:
        raise UpdateError('Tipo de pacote desconhecido.')
    required = {PROGRAM_NAME, UPDATER_NAME} if kind == 'windows' else SOURCE_REQUIRED
    try:
        with zipfile.ZipFile(archive, 'r') as zipped:
            seen: set[str] = set()
            seen_folded: set[str] = set()
            total = 0
            for info in zipped.infolist():
                name = info.filename
                # ZIP com links simbólicos não é permitido, inclusive em máquinas Windows.
                symlink = ((info.external_attr >> 16) & 0o170000) == 0o120000
                if (info.is_dir() or symlink or
                        (name not in allow and not (kind == 'source' and allowed_source_member(name))) or
                        name.casefold() in seen_folded or info.file_size > MAX_FILE_BYTES):
                    raise UpdateError(f'Conteúdo inesperado no ZIP: {name}')
                total += info.file_size
                if total > MAX_EXTRACT_BYTES:
                    raise UpdateError('ZIP excede o limite de arquivos descompactados.')
                seen.add(name)
                seen_folded.add(name.casefold())
            if not required.issubset(seen):
                raise UpdateError('Pacote incompleto: arquivos obrigatórios ausentes.')
            if zipped.testzip() is not None:
                raise UpdateError('Pacote danificado.')
            return seen
    except (OSError, zipfile.BadZipFile) as exc:
        raise UpdateError(f'Não foi possível validar o ZIP: {exc}') from exc


def download_verified_release(release: Release, folder: Path) -> Path:
    """Baixa a release selecionada, confere checksum e conteúdo permitido."""
    bundle, _ = asset_names(release.kind)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        with github_request(release.hash_url) as resp:
            expected = parse_checksum(resp.read(512).decode('ascii'), bundle=bundle)
        target = folder / bundle
        digest = hashlib.sha256()
        length = 0
        with github_request(release.zip_url, timeout=60) as resp, target.open('wb') as out:
            while chunk := resp.read(1024 * 1024):
                length += len(chunk)
                if length > MAX_ARCHIVE_BYTES:
                    raise UpdateError('Pacote de atualização maior que o limite permitido.')
                digest.update(chunk)
                out.write(chunk)
    except (OSError, ValueError) as exc:
        raise UpdateError(f'Falha ao baixar atualização: {exc}') from exc
    if digest.hexdigest() != expected:
        raise UpdateError('Checksum SHA-256 inválido. Nenhum arquivo do app foi alterado.')
    validate_archive(target, kind=release.kind)
    return target


def wait_until_exit(pid: int, seconds: int = 90) -> None:
    """Aguarda o aplicativo que está sendo atualizado fechar, no Windows."""
    if os.name != 'nt':
        raise UpdateError('Atualização automática suportada apenas no Windows.')
    from ctypes import wintypes
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    h = kernel.OpenProcess(0x00100000, False, pid)
    if not h:
        return  # processo já saiu
    try:
        result = kernel.WaitForSingleObject(h, seconds * 1000)
        if result != 0:
            raise UpdateError('Editor não encerrou. Nenhum arquivo alterado.')
    finally:
        kernel.CloseHandle(h)


def install_archive(archive: Path, destination: Path, kind: str = 'windows') -> None:
    """Atualização transacional, limitada a arquivos do app; nunca limpa projetos."""
    destination = destination.resolve()
    if kind == 'windows':
        installed = (destination / PROGRAM_NAME).is_file()
    elif kind == 'source':
        installed = (destination / 'app.py').is_file() and (destination / 'fmstudio/gui.py').is_file()
    else:
        raise UpdateError('Formato de instalação inválido.')
    if not installed:
        raise UpdateError('Pasta de instalação não corresponde ao pacote selecionado.')
    members = validate_archive(archive, kind=kind)
    # Cria estrutura preparada em um único filesystem, para substituições atômicas.
    with tempfile.TemporaryDirectory(prefix='.fmstudio-stage-', dir=destination) as temp:
        staged = Path(temp)
        backups = staged / 'old'
        backups.mkdir()
        with zipfile.ZipFile(archive, 'r') as zipped:
            for name in sorted(members):
                target = staged / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(name) as source, target.open('wb') as out:
                    shutil.copyfileobj(source, out)
        replaced: list[tuple[Path, Path]] = []
        try:
            for name in sorted(members):
                dest = destination / name
                saved = backups / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                saved.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    shutil.copy2(dest, saved)
                os.replace(staged / name, dest)
                replaced.append((dest, saved))
        except Exception as exc:
            for dest, saved in reversed(replaced):
                if saved.is_file():
                    os.replace(saved, dest)
                else:
                    dest.unlink(missing_ok=True)
            raise UpdateError(f'Instalação falhou; arquivos anteriores restaurados: {exc}') from exc


def start_updater(release: Release) -> None:
    """Inicia um instalador em TEMP; pode atualizar fontes Python ou EXEs."""
    if os.name != 'nt':
        raise UpdateError('Atualização automática disponível somente no Windows.')
    folder = (Path(sys.executable).resolve().parent if release.kind == 'windows'
              else Path(__file__).resolve().parent.parent)
    scratch = Path(tempfile.mkdtemp(prefix='fmstudio-updater-'))
    python_exe = sys.executable
    if release.kind == 'windows':
        helper = folder / UPDATER_NAME
        if not helper.is_file():
            raise UpdateError('Instalação Windows incompleta: atualizador auxiliar não encontrado.')
        launcher = scratch / UPDATER_NAME
        shutil.copy2(helper, launcher)
        command = [str(launcher)]
    else:
        if not (folder / 'updater_main.py').is_file():
            raise UpdateError('Instalação Python incompleta: updater_main.py não encontrado.')
        # Copia o atualizador e suas dependências. Nenhum módulo é executado da pasta
        # que será modificada, evitando travamentos / imports durante a atualização.
        (scratch / 'fmstudio').mkdir()
        for rel in ('updater_main.py', 'fmstudio/__init__.py', 'fmstudio/updates.py'):
            dest = scratch / rel
            shutil.copy2(folder / rel, dest)
        command = [str(python_exe), str(scratch / 'updater_main.py')]
    flags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    command += ['--install-dir', str(folder), '--pid', str(os.getpid()),
                '--version', release.version, '--zip-url', release.zip_url,
                '--hash-url', release.hash_url, '--kind', release.kind]
    if release.kind == 'source':
        command += ['--python-exe', str(python_exe)]
    try:
        subprocess.Popen(command, cwd=str(scratch), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=flags, close_fds=True)
    except Exception as exc:
        raise UpdateError(f'Falha ao abrir instalador externo: {exc}') from exc


def run_updater_cli(argv: list[str] | None = None) -> int:
    """Chamado pelo atualizador externo, que já foi copiado para TEMP."""
    import argparse
    parser = argparse.ArgumentParser(description='Atualizador externo FM Mod Studio')
    parser.add_argument('--install-dir', required=True)
    parser.add_argument('--pid', required=True, type=int)
    parser.add_argument('--version', required=True)
    parser.add_argument('--zip-url', required=True)
    parser.add_argument('--hash-url', required=True)
    parser.add_argument('--kind', choices=['windows', 'source'], default='windows')
    parser.add_argument('--python-exe', default='')
    args = parser.parse_args(argv)
    if (not parse_version(args.version) or
            not safe_github_asset_url(args.zip_url) or
            not safe_github_asset_url(args.hash_url)):
        raise UpdateError('Versão ou URLs não confiáveis.')
    bundle, checksum_name = asset_names(args.kind)
    if not args.zip_url.endswith('/' + bundle) or not args.hash_url.endswith('/' + checksum_name):
        raise UpdateError('Pacotes da modalidade errada ou não autorizados.')
    if args.kind == 'source' and (not args.python_exe or not Path(args.python_exe).is_file()):
        raise UpdateError('Interpretador Python original não localizado.')
    folder = Path(args.install_dir).resolve()
    if folder == Path(folder.anchor):
        raise UpdateError('A pasta raiz do disco não é uma instalação válida.')
    with tempfile.TemporaryDirectory(prefix='fmstudio-download-') as temp:
        release = Release(args.version, args.version, '', args.zip_url, args.hash_url, args.kind)
        archive = download_verified_release(release, Path(temp))
        wait_until_exit(args.pid)
        install_archive(archive, folder, kind=args.kind)
    if args.kind == 'windows':
        cmd = [str(folder / PROGRAM_NAME)]
    else:
        cmd = [args.python_exe, str(folder / 'app.py')]
    subprocess.Popen(cmd, cwd=str(folder), close_fds=True)
    return 0
