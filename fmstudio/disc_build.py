"""Constrói cópia de teste MODE2/2352 sem reempacotar XA/MDEC e sem alterar originais.

Somente substitui bytes da ISO9660 SLUS_014.11 quando o executável gerado
mantém o mesmo tamanho. Atualiza EDC+ECC para cada setor Mode2/Form1 alterado.
Aplica regras compatíveis com o perfil PS1 e verifica os dados da cópia.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
import tempfile
import hashlib
import json
from pathlib import Path
import shutil
import struct

from .core import ModError, legacy_god_description_icon_card, ps1_god24_card_ids
from .disc import DiscReader, DiscError, SYNC
from .tables import CARD_COUNT, EXE_DELTA

class DescriptionCompatibilityError(ModError):
    """Edited descriptions cannot all be written to the supplied PS1 image.

    Failures remain attached for a deliberate GUI choice; no prior BIN is changed.
    """

    def __init__(self, failures):
        self.failures = tuple(failures)
        details = '\n'.join('• ' + item for item in self.failures[:12])
        if len(self.failures) > 12:
            details += f'\n• ... e mais {len(self.failures) - 12} descrição(ões)'
        super().__init__(
            'As descrições abaixo NÃO foram gravadas no jogo:\n'
            + details
            + '\n\nO BIN/CUE anterior foi preservado. '
              'A exportação com descrições compatíveis mantém o texto original '
              'nas cartas de base e usa uma prévia ou um texto vazio para cartas novas. '
              'Os textos completos continuam no projeto.'
        )


RAW_SECTOR = 2352
PAYLOAD = 2048
_EDC_POLY = 0xD8018001


def _tables():
    fwd = []
    bwd = [0] * 256
    edc = []
    for v in range(256):
        f = ((v << 1) ^ (0x1D if v & 0x80 else 0)) & 0xFF
        fwd.append(f)
        bwd[v ^ f] = v
        x = v
        for _ in range(8):
            x = (x >> 1) ^ (_EDC_POLY if x & 1 else 0)
        edc.append(x)
    return fwd, bwd, edc


_ECC_F, _ECC_B, _EDC_TABLE = _tables()


def _edc(buf: bytes) -> int:
    result = 0
    for item in buf:
        result = (result >> 8) ^ _EDC_TABLE[(result ^ item) & 0xFF]
    return result


def _ecc_block(data: bytes, majors: int, minors: int, mult: int, inc: int) -> bytes:
    size = majors * minors
    if len(data) < size:
        raise ValueError('Bloco ECC menor do que o esperado')
    parity = bytearray(majors * 2)
    for major in range(majors):
        offset = ((major >> 1) * mult) + (major & 1)
        a = b = 0
        for _ in range(minors):
            v = data[offset]
            offset += inc
            if offset >= size:
                offset -= size
            a ^= v
            b ^= v
            a = _ECC_F[a]
        a = _ECC_B[_ECC_F[a] ^ b]
        parity[major] = a
        parity[major + majors] = a ^ b
    return bytes(parity)


def regenerate_form1(sector: bytes) -> bytes:
    """Recalcula EDC/ECC Mode2 Form1 sem trocar header, subheader ou dados."""
    if (len(sector) != RAW_SECTOR or sector[:12] != SYNC or sector[15] != 2
            or sector[18] & 0x20 or sector[16:20] != sector[20:24]):
        raise ModError('Setor não é Mode2 Form1 válido; patch abortado')
    out = bytearray(sector)
    struct.pack_into('<I', out, 2072, _edc(out[16:2072]))
    # Em Mode2, os 4 bytes de endereço entram zerados no cálculo ECC.
    psource = bytes(4) + out[16:2076]
    out[2076:2248] = _ecc_block(psource, 86, 24, 2, 86)
    qsource = bytes(4) + out[16:2248]
    out[2248:2352] = _ecc_block(qsource, 52, 43, 86, 88)
    return bytes(out)


def _write_file_patches(out, entry, original: bytes, patched: bytes) -> list[int]:
    """Atualiza arquivo ISO9660 in-place; tamanho e bytes-base devem coincidir."""
    if len(original) != entry.size or len(patched) != entry.size:
        raise ModError(f'{entry.path}: alteração de tamanho não é permitida.')
    changed=[]
    for i in range((entry.size + PAYLOAD-1)//PAYLOAD):
        start=i*PAYLOAD
        before=original[start:start+PAYLOAD]
        after=patched[start:start+PAYLOAD]
        if before == after: continue
        lba=entry.extent+i
        out.seek(lba*RAW_SECTOR)
        raw=out.read(RAW_SECTOR)
        if len(raw)!=RAW_SECTOR or raw[24:24+len(before)]!=before:
            raise ModError(f'{entry.path} não coincide com bytes extraídos no LBA {lba}.')
        fixed=bytearray(raw)
        fixed[24:24+len(after)]=after
        out.seek(lba*RAW_SECTOR)
        out.write(regenerate_form1(bytes(fixed)))
        changed.append(lba)
    return changed


def _apply_card_descriptions(exe: bytes, changes: dict[int, str], cards: dict,
                             *, native_profile: bool, start: int, end: int,
                             policy: str = 'strict', regions=None):
    """Grava textos compatíveis e informa os demais sem ocultar perda de dados.

    'strict': bloqueia se qualquer descrição editada não couber.
    'preserve_incompatible': mantém textos originais do PS1 onde falhou.
    Para cartas novas, usa uma prévia ou mantém o texto vazio da base.
    """
    if policy not in ('strict', 'preserve_incompatible'):
        raise ModError('Política de exportação de descrições desconhecida.')
    if not changes:
        return exe, [], set(), []
    failures = []
    written = []
    icons = set()
    patched = exe
    if native_profile:
        from .ps1_text import patch_descriptions
        patched, written, icons, failures = patch_descriptions(
            exe, changes, cards, start=start, end=end, regions=regions,
            preview_new=policy == 'preserve_incompatible')
    else:
        from .ps1_content import patch_descriptions
        for cid, description in sorted(changes.items()):
            try:
                patched, entries = patch_descriptions(
                    patched, {cid: description}, cards)
                written.extend(entries)
            except ModError as exc:
                failures.append(f'#{cid}: descrição: {exc}')
    if failures and policy == 'strict':
        raise DescriptionCompatibilityError(failures)
    return patched, written, icons, failures


def build_test_disc(project, source_image: Path, *, require_complete: bool=False,
                    description_policy: str = 'strict') -> dict:
    """Cópia segura de BIN com atributos e, quando compatíveis, nomes e imagens.

    Para exigir todos os efeitos e cartas extras, use require_complete=True. Isso
    bloqueará construções parciais ao invés de publicar uma imagem enganosa.
    """
    if description_policy not in ('strict', 'preserve_incompatible'):
        raise ModError('Política de exportação de descrições desconhecida.')
    source_image=Path(source_image).resolve()
    from .ps1_runtime import SOURCE_SHA256, compile_effects, install_runtime
    from .ps1_mod import (
        LP_BANK_END, LP_CODE, compile_mod, inspect_chest_catalog, patch_chest_catalog,
        patch_executable, patch_wa, wa_sha,
    )
    from .passwords import validate_ps1_prefix, choose_ps1_prefix, PS1_ID_PREFIX
    from .tables import PASSWORD_BASE
    from .ps1_economy import (
        chest_show_all, price_overrides, fixed_win_reward, apply_password_prices,
        patch_win_reward, reward_status, read_prices,
    )
    show_all_chest = chest_show_all(project)
    prices_requested = price_overrides(project)
    win_reward_requested = fixed_win_reward(project)
    from .ps1_drop_count import apply as apply_cards_per_win, cards_per_win, status as cards_per_win_status
    cards_per_win_requested = cards_per_win(project)
    from .ps1_equip_bonus import (apply as apply_equip_bonus, block_size as equip_bonus_size,
                                  equip_bonuses, reserve_block, status as equip_bonus_status)
    equip_bonus_requested = equip_bonuses(project)
    from .ps1_magic_values import (apply as apply_magic_values, is_empty as magic_values_empty,
                                   magic_values, matches as magic_values_match)
    magic_values_requested = magic_values(project)
    from .ps1_frame_colors import (apply as apply_frame_colors, block_size as frame_block_size,
                                   card_classes, frame_settings, status as frame_status)
    frames_requested = frame_settings(project)
    from .ps1_life_splash import (apply as apply_life_splash, block_size as splash_block_size,
                                  has_summon_life, wants_splash)
    splash_wanted = wants_splash(project)
    frames_enabled = frames_requested['ativado'] and any(frames_requested['cores'].values())
    from .ps1_expansion import (EXPANDED_LEVELS, PS1_CARD_CAPACITY, compile_expansion, expand_archive,
                                patch_expansion, inspect_expansion, retail_archive_view)
    from .ps1_campaign_quests import (QUEST_SCENE_SECTORS, append_quest_scene, build_quest_overlay, inspect_quest_overlay,
                                     install_quest_handlers, project_quest_catalog, quest_settings,
                                     reserve_quest_handlers, validate_quest_source)
    from .ps1_supreme import patch_supreme, supreme_cards, validate_slot
    from .tables import LEVEL_ADDR
    quests = quest_settings(project)
    quest_enabled = quests['ativado']
    texts={int(cid):project.get(int(cid)).get('descricao','')
           for cid,rows in getattr(project,'edits',{}).items()
           if 'descricao' in rows and 1<=int(cid)<=722}
    names={int(cid):project.get(int(cid)).get('nome','')
           for cid,rows in getattr(project,'edits',{}).items()
           if 'nome' in rows and 1<=int(cid)<=CARD_COUNT}
    descriptions_studio_only=sorted(
        {int(cid) for cid,rows in getattr(project,'edits',{}).items()
         if 'descricao' in rows and int(cid)>722}
        | {int(cid) for cid in getattr(project,'new_cards',{})
           if int(cid)>722 and project.get(int(cid)).get('descricao')})
    god_cards=ps1_god24_card_ids(project)
    god_icon_card=legacy_god_description_icon_card(project)
    try:
        with DiscReader(source_image) as reader:
            if reader.mode!='MODE2/2352':
                raise ModError('Use BIN/CUE original MODE2/2352 para preservar XA/MDEC.')
            original_bin=reader.path.resolve()
            entries={e.path.upper():e for e in reader.files() if not e.is_dir}
            exe=entries.get('SLUS_014.11')
            if exe is None:
                raise ModError('SLUS_014.11 não encontrado na imagem.')
            original_exe=b''.join(reader.read_entry(exe))
            source_digest=hashlib.sha256(original_exe).hexdigest()
            native_profile=source_digest==SOURCE_SHA256
            god24_enabled=native_profile and bool(god_cards)
            expansion = compile_expansion(project, profile=native_profile)
            capacity = PS1_CARD_CAPACITY if expansion.enabled else CARD_COUNT
            if (prices_requested or win_reward_requested is not None or equip_bonus_requested
                    or not magic_values_empty(magic_values_requested) or frames_enabled
                    or cards_per_win_requested is not None) and not native_profile:
                raise ModError(
                    'Economia PS1 personalizada exige o SLUS Drop x15 original vinculado.')
            invalid_extra = [cid for cid in prices_requested
                             if cid > CARD_COUNT and (not expansion.enabled or cid not in expansion.ids)]
            if invalid_extra:
                raise ModError(
                    'Preço de Password não gravável no PS1: '
                    + ', '.join('#'+str(cid) for cid in sorted(invalid_extra))
                    + '. Somente cartas expandidas 723–740 presentes no BIN são suportadas.')
            supreme_ids = supreme_cards(project, capacity) if native_profile else []
            if supreme_ids:
                validate_slot(project, capacity)
            wa_entry=entries.get('DATA/WA_MRG.MRG')
            requested_art={int(k):v for k,v in getattr(project,'arts',{}).items() if int(k)<=722}
            metadata=getattr(project,'metadata',{})
            expected_wa=wa_sha(project) if metadata.get('edicao_mod') else None
            mod_plan=compile_mod(project,profile=native_profile,wa_verified=bool(expected_wa))
            native_plan=compile_effects(project,native_profile,fixed_decks=mod_plan.fixed_decks,
                                        fusions=mod_plan.fusions)
            equip_mode=metadata.get('ps1_equip_mode','adicionar')
            if equip_mode not in ('adicionar','substituir'):
                raise ModError('Modo de equipamento inválido no projeto.')
            native_equips=(metadata.get('ps1_equip_additions',{})
                           if equip_mode=='adicionar' else {})
            if equip_mode=='adicionar' and native_profile:
                # Sub-tipo: acrescenta a carta aos equipamentos que servem no 2º tipo.
                from .card_subtypes import equip_additions
                from .mod_data import base_tables
                _, _, stock_equips, _ = base_tables(project)
                merged = {int(k): set(map(int, v)) for k, v in stock_equips.items()}
                for k, v in native_equips.items():
                    merged.setdefault(int(k), set()).update(map(int, v))
                extra = equip_additions({cid: project.get(cid) for cid in getattr(project, 'cards', {})}, merged)
                if extra:
                    combined = {int(k): set(map(int, v)) for k, v in native_equips.items()}
                    for equip, targets in extra.items():
                        combined.setdefault(equip, set()).update(targets)
                    native_equips = {str(k): sorted(v) for k, v in combined.items()}
            replacements=(metadata.get('ps1_equip_replacements',{})
                          if equip_mode=='substituir' else {})
            # Rituais em pausa a pedido do usuário. Guardamos planos anteriores
            # no projeto, mas não os escrevemos no BIN sem reativação explícita.
            native_rituals=(metadata.get('ps1_ritual_recipes',{})
                            if metadata.get('ps1_rituals_enabled',False) else {})
            native_traps=metadata.get('ps1_trap_thresholds',{})
            native_terrain=metadata.get('ps1_terrain_boosts',{})
            from .ps1_starter_choice import settings as starter_choice_settings
            starter_choice_on = bool(native_profile) and starter_choice_settings(project)['ativado']
            if starter_choice_on and mod_plan.starters:
                # Os pools de sorteio dão lugar à rotina da escolha (mesma área do overlay).
                mod_plan.starters = []
            needs_wa=(starter_choice_on or quest_enabled or expansion.enabled or requested_art or bool(prices_requested) or native_equips or replacements or native_rituals or mod_plan.needs_wa
                      or god_icon_card or god24_enabled or supreme_ids or native_plan.password_prefix is not None
                      or (native_profile and names)
                      or (native_profile and any('{icon:' in desc for desc in texts.values())))
            original_wa=b''.join(reader.read_entry(wa_entry)) if needs_wa and wa_entry else None
            # Papel de parede do menu principal: só dados do SU.MRG (setores 80-97).
            from .ps1_menu_wallpaper import SU_PATH, apply as apply_wallpaper, requested_wall
            wallpaper = requested_wall(project)
            su_entry = entries.get(SU_PATH) if wallpaper is not None else None
            if wallpaper is not None and su_entry is None:
                raise ModError('Papel de parede: DATA/SU.MRG não encontrado na imagem.')
            original_su = b''.join(reader.read_entry(su_entry)) if su_entry else None
            if expansion.enabled:
                if original_wa is None or source_digest != metadata.get('base_sha256', {}).get('slus'):
                    raise ModError('Expansão exige SLUS e WA_MRG da imagem vinculada.')
                if metadata.get(PS1_ID_PREFIX) is None:
                    from .tables import decode_passwords
                    prefix = choose_ps1_prefix(row['password'] for row in decode_passwords(original_wa))
                    project.metadata = {**project.metadata, PS1_ID_PREFIX: prefix}
                    project.save()
                    metadata = project.metadata
                    native_plan = compile_effects(project, native_profile, fixed_decks=mod_plan.fixed_decks,
                                                  fusions=mod_plan.fusions)
    except DiscError as exc:
        raise ModError(f'Imagem original inválida: {exc}') from exc

    expected=getattr(project,'metadata',{}).get('base_sha256',{}).get('slus')
    if not expected or source_digest!=expected:
        raise ModError('SLUS da imagem não corresponde ao executável vinculado ao projeto.')
    if quest_enabled:
        validate_quest_source(project, original_wa, native_profile=native_profile)
    if native_plan.password_prefix is not None:
        if original_wa is None:
            raise ModError('Passwords por ID exigem o DATA/WA_MRG.MRG da imagem de origem.')
        linked_wa = wa_sha(project)
        if linked_wa and hashlib.sha256(original_wa).hexdigest() != linked_wa:
            raise ModError('O WA_MRG da imagem de passwords diverge do projeto.')
        validate_ps1_prefix(original_wa, native_plan.password_prefix)
    desc_bank_end=min(native_plan.bank_end, LP_CODE if mod_plan.has_lp else LP_BANK_END)
    if native_plan.data_end>desc_bank_end:
        raise ModError('As regras nativas excedem a área reservada para esta cópia.')

    audit_report=None
    if hasattr(project,'edits') and hasattr(project,'new_cards'):
        from .ps1_compat import audit
        audit_report=audit(project)
        if require_complete and audit_report['pendente_de_motor']:
            raise ModError('Build completo bloqueado: recursos ainda sem suporte PS1. Consulte compatibilidade_ps1.json.')

    output, manifest=project.export()
    source_patched=(output/'build_local'/'SLUS_014.11')
    if manifest.get('slus_modificado_sha256') and source_patched.is_file():
        patched_exe=source_patched.read_bytes()
        if hashlib.sha256(patched_exe).hexdigest()!=manifest['slus_modificado_sha256']:
            raise ModError('Executável exportado não coincide com o manifesto SHA-256.')
    else:
        patched_exe=original_exe
    if len(patched_exe)!=exe.size:
        raise ModError('Executável mudou de tamanho; gravação de disco bloqueada.')
    written_names=[];written_descriptions=[]
    if names:
        from .ps1_content import patch_names
        # Nomes que não cabem ficam apenas no projeto; cada tentativa gera
        # relatório separado sem gravar parcialmente uma string inválida.
        for cid,name in sorted(names.items()):
            try:
                patched_exe,items=patch_names(patched_exe,{cid:name})
                written_names.extend(items)
            except ModError:
                continue

    if expansion.enabled:
        descriptions_studio_only = [cid for cid in descriptions_studio_only if cid not in expansion.ids]
        # The unused IDs already share the original empty description (D100).
        texts.update({cid: project.get(cid).get('descricao', '') for cid in expansion.ids})

    description_icons=set()
    descriptions_not_written=[]
    regions = None
    splash_requested = bool(native_profile) and splash_wanted
    lp_hud_initial=mod_plan.player_lp if mod_plan.has_lp else 8000
    lp_hud_wide = bool(native_profile) and lp_hud_initial > 9999
    lp_hud_hook = None
    from .ps1_lifelink import (apply as apply_lifelink, block_size as lifelink_block_size,
                               wants_lifelink)
    lifelink_wanted = bool(native_profile) and wants_lifelink(native_plan)
    lifelink_hook = None
    from .ps1_runtime import BONUS_CODES
    from .ps1_subtypes import apply as apply_subtypes, block_size as subtype_block_size, pairs_for
    subtype_pairs = (pairs_for({cid: project.get(cid) for cid in getattr(project, 'cards', {})},
                               native_plan.capacity)
                     if native_profile else [])
    subtype_wanted = bool(subtype_pairs) and any(action in BONUS_CODES for _, action in native_plan.accepted)
    subtype_hook = None
    hand_bonus_wanted = bool(native_profile) and (
        any(action == 'bonus_mao_tipo' for _, action in native_plan.accepted)
        or any(raw.get('acao') == 'bonus_por_carta_id' and raw.get('origem_contagem') == 'mao'
               for effects in getattr(project, 'effects', {}).values() for raw in effects))
    hand_bonus_hook = None
    from .ps1_entry_effects import plan_ops as _entry_ops
    entry_ops = _entry_ops(native_plan) if native_profile else frozenset()
    entry_effects_wanted = bool(entry_ops) or lifelink_wanted
    entry_effects_hook = None
    entry_effects_report = ({'status': 'sem_efeitos'} if native_profile else {'status': 'perfil_incompativel'})
    hand_bonus_report = ({'status': 'sem_efeitos'} if native_profile else {'status': 'perfil_incompativel'})
    subtype_report = ({'status': 'sem_subtipos'} if native_profile else {'status': 'perfil_incompativel'})
    starter_choice_hook, starter_choice_texts, starter_choice_decks = None, [], []
    starter_choice_report = ({'status': 'desativado'} if native_profile else {'status': 'perfil_incompativel'})
    if starter_choice_on:
        from .mod_data import CONFIG_KEY
        from .deep_extract import glyph_map
        from .ps1_starter_choice import resolve_decks, text_sizes
        starter_choice_decks = resolve_decks(
            project, (project.metadata.get(CONFIG_KEY) or {}).get('iniciais', {}))
        starter_choice_cmap, _ = glyph_map(original_exe)
        starter_choice_sizes = text_sizes(starter_choice_decks, starter_choice_cmap, project.cards)
    lifelink_report = ({'status': 'sem_efeitos'} if native_profile else {'status': 'perfil_incompativel'})
    from .mod_data import CONFIG_KEY as _MOD_CONFIG_KEY
    from .ps1_fixed_drop import (apply as apply_fixed_drop, block_size as fixed_drop_block_size,
                                 fixed_drops)
    fixed_drop_map = (fixed_drops(project.metadata.get(_MOD_CONFIG_KEY) or {}, native_plan.capacity)
                      if native_profile else {})
    fixed_drop_hook = None
    duel_hud_wanted = bool(native_profile and
                           (project.metadata.get(_MOD_CONFIG_KEY) or {}).get('hud_ps1') == 'novo')
    duel_hud_rules = (project.metadata.get(_MOD_CONFIG_KEY) or {}) if duel_hud_wanted else {}
    duel_hud_portrait = (int(duel_hud_rules.get('retrato_jogador_ps1', 0))
                         if duel_hud_rules.get('retratos_hud_ps1', True) else None)
    duel_hud_hook = None
    duel_hud_report = ({'status': 'original'} if native_profile else {'status': 'perfil_incompativel'})
    fixed_drop_report = ({'status': 'sem_drops_fixos'} if native_profile else {'status': 'perfil_incompativel'})
    if native_profile and (texts or quest_enabled or equip_bonus_requested or frames_enabled
                           or splash_requested or lp_hud_wide or lifelink_wanted or starter_choice_on
                           or subtype_wanted or hand_bonus_wanted or fixed_drop_map or duel_hud_wanted
                           or entry_effects_wanted):
        from .ps1_text import description_regions
        regions = description_regions(native_plan, has_lp=mod_plan.has_lp)
    code_space = []
    debug_space_report = {'status': 'nao_usado'}

    def reserve_code(size):
        """Rotinas do mod: menu de debug e Link Duel; depois, o banco de textos."""
        nonlocal patched_exe, regions, code_space, debug_space_report
        if native_profile and not code_space and debug_space_report['status'] == 'nao_usado':
            from .ps1_debug_space import claim as claim_debug_space
            patched_exe, code_space, debug_space_report = claim_debug_space(patched_exe)
            # Área do Link Duel (desligado): depois das regras extras de efeitos.
            from .ps1_link_space import LINK_END, claim as claim_link_space
            from .ps1_runtime import FAR_ADDRESS
            claimed, link_report = claim_link_space(patched_exe)
            if link_report['status'] == 'liberado':
                patched_exe = claimed
                code_space = list(code_space) + [((native_plan.far_end + 15) & ~15, LINK_END)]
                debug_space_report = dict(debug_space_report, area_link_duel=link_report)
        try:
            address, code_space = reserve_block(patched_exe, code_space, size)
            return address
        except ModError:
            address, regions = reserve_block(patched_exe, regions, size)
            return address
    if quest_enabled:
        quest_handlers, regions = reserve_quest_handlers(patched_exe, regions)
    equip_bonus_report = {'status': 'original'} if native_profile else {'status': 'perfil_incompativel'}
    if native_profile and equip_bonus_requested:
        equip_hook = reserve_code(equip_bonus_size(equip_bonus_requested))
        patched_exe, equip_bonus_report = apply_equip_bonus(patched_exe, equip_bonus_requested, equip_hook)
    frames_report = {'status': 'desativado'} if native_profile else {'status': 'perfil_incompativel'}
    if native_profile and frames_enabled:
        frame_hook = reserve_code(frame_block_size())
        cards_for_frames = {cid: project.get(cid) for cid in getattr(project, 'cards', {})}
        patched_exe, frames_report = apply_frame_colors(
            patched_exe, frames_requested['cores'], card_classes(cards_for_frames), frame_hook)
    splash_hook = None
    splash_report = ({'status': 'sem_efeitos'} if native_profile else {'status': 'perfil_incompativel'})
    if splash_requested:
        # Reserva agora (antes dos textos); instala depois do runtime, que cria o salto a trocar.
        splash_hook = reserve_code(splash_block_size())
    if lp_hud_wide:
        # Dígitos reduzidos de LP (POLY_FT4 sem GTE): bloco próprio, reservado antes dos textos.
        from .ps1_lp_hud import block_size as lp_hud_block_size
        lp_hud_hook = reserve_code(lp_hud_block_size())
    if lifelink_wanted:
        # Vínculo com Vida: a cena de batalha passa por esta rotina (instalada após o runtime).
        lifelink_hook = reserve_code(lifelink_block_size())
    if hand_bonus_wanted:
        # Bônus por cartas na mão: desvio da chamada de count_bonus (após o runtime).
        from .ps1_hand_bonus import block_size as hand_bonus_block_size
        hand_bonus_hook = reserve_code(hand_bonus_block_size())
    if entry_effects_wanted:
        # Efeitos de entrada com animações das mágicas + animação de cura do Vínculo com Vida.
        from .ps1_entry_effects import block_size as entry_effects_block_size
        entry_effects_hook = reserve_code(entry_effects_block_size(
            entry_ops, entries=bool(entry_ops), heal=lifelink_wanted))
    if duel_hud_wanted:
        from .ps1_duel_hud import block_size as duel_hud_block_size
        duel_hud_hook = reserve_code(duel_hud_block_size(True, duel_hud_portrait is not None))
    if fixed_drop_map:
        # Drop fixo por duelista: desvio na entrada de Duel_SelectCardDrop (após o runtime).
        fixed_drop_hook = reserve_code(fixed_drop_block_size())
    if subtype_wanted:
        # Sub-tipo: trampolim em matches_bonus (instalado após o runtime).
        subtype_hook = reserve_code(subtype_block_size(len(subtype_pairs)))
    if starter_choice_on:
        # Escolha do deck inicial: rotina+dados e um texto por página no banco de descrições.
        starter_choice_hook = True        # rotina e decks vão no overlay de nome (sem espaço do SLUS)
        for size in starter_choice_sizes:
            address, regions = reserve_block(patched_exe, regions, size)
            starter_choice_texts.append(address)
    if texts:
        catalog={i:project.get(i) for i in project.cards} if hasattr(project,'cards') else {}
        (patched_exe, written_descriptions, description_icons,
         descriptions_not_written) = _apply_card_descriptions(
            patched_exe, texts, catalog, native_profile=native_profile,
            start=native_plan.data_end, end=desc_bank_end, policy=description_policy,
            regions=regions)
    written_ids = {row['id'] for row in written_descriptions}
    new_without_text = [cid for cid in expansion.ids if cid not in written_ids]

    from .ps1_native import patch_trap_thresholds, patch_terrain_boosts, patch_rituals
    patched_exe, traps_written = patch_trap_thresholds(patched_exe, native_traps)
    patched_exe, terrain_written = patch_terrain_boosts(patched_exe, native_terrain)
    from .ps1_effects_lab import patch_deck_global_limit
    deck_copies_written=[]
    if not native_plan.copy_rules:
        patched_exe, deck_copies_written = patch_deck_global_limit(
            patched_exe, metadata.get('ps1_deck_global_limit'))

    from .ps1_effects_lab import patch_initial_duel_lp
    # A configuração global da aba Config. MOD é a única fonte quando presente.
    # Não permitir que o patch legado de teste altere novamente os mesmos LP.
    patched_exe, lp_written = patch_initial_duel_lp(
        patched_exe, None if mod_plan.has_lp else metadata.get('ps1_starting_lp'))

    written_arts=[]
    written_titles=[]
    patched_wa=None
    patched_su, wallpaper_report = None, {'status': 'original'}
    if wallpaper is not None:
        patched_su, wallpaper_report = apply_wallpaper(original_su, wallpaper)
    if requested_art:
        if original_wa is None or wa_entry is None:
            raise ModError('DATA/WA_MRG.MRG não encontrado para aplicar artes.')
        provenance=project.folder/'base'/'resumo.json'
        from_original=''
        if provenance.is_file():
            from_original=(json.loads(provenance.read_text(encoding='utf-8')).get('source_sha256') or {}).get('DATA/WA_MRG.MRG','')
        if not from_original or hashlib.sha256(original_wa).hexdigest()!=from_original:
            raise ModError('Artes não podem ser gravadas: hash de WA_MRG.MRG ausente ou divergente. '
                           'Reimporte os dados da mesma imagem para fixar a origem.')
        from .ps1_content import patch_card_art
        patched_wa=original_wa
        for cid,rel in sorted(requested_art.items()):
            # Só aceita o caminho cadastrado no projeto; evita leitura externa.
            path=(project.folder/rel).resolve()
            if not path.is_relative_to(project.folder.resolve()):
                raise ModError('Referência de arte fora da pasta do projeto.')
            if not path.is_file():
                raise ModError(f'PNG não encontrado para carta #{cid}: {path.name}')
            patched_wa,regions=patch_card_art(
                patched_wa,cid,path,
                options=project.metadata.get('ps1_image_optimizer'),
                verified_layout=native_profile)
            written_arts.extend(regions)

    if native_profile and written_names and original_wa is not None:
        if requested_art or hashlib.sha256(original_wa).hexdigest() == wa_sha(project):
            from .ps1_content import patch_card_titles
            patched_wa, written_titles = patch_card_titles(
                patched_wa if patched_wa is not None else original_wa,
                {row['id']: names[row['id']] for row in written_names})

    native_written=[]
    if native_equips or replacements:
        if original_wa is None or wa_entry is None:
            raise ModError('DATA/WA_MRG.MRG é necessário para alterar equipamentos.')
        if not requested_art:
            provenance=project.folder/'base'/'resumo.json'
            origin_hash=''
            if provenance.is_file():
                origin_hash=(json.loads(provenance.read_text(encoding='utf-8')).get('source_sha256') or {}).get('DATA/WA_MRG.MRG','')
            if not origin_hash or hashlib.sha256(original_wa).hexdigest()!=origin_hash:
                raise ModError('WA_MRG.MRG não corresponde à origem do projeto; '
                               'não é seguro alterar equipamentos.')
        if equip_mode=='substituir':
            from .ps1_equip import replace_equipment_targets
            patched_wa,native_written=replace_equipment_targets(
                patched_wa if patched_wa is not None else original_wa,
                replacements)
            equip_strategy='troca-u16-original'
        else:
            from .ps1_equip_bitmap import patch_bitmap_equips
            bitmap=patch_bitmap_equips(
                original_exe,
                patched_wa if patched_wa is not None else original_wa,
                native_equips)
            if bitmap is not None:
                patched_wa,native_written=bitmap
                equip_strategy='bitmap-mips-94'
            else:
                from .ps1_equip import patch_equipment_targets
                patched_wa,native_written=patch_equipment_targets(
                    patched_wa if patched_wa is not None else original_wa,
                    native_equips)
                equip_strategy='tabela-stock'

    ritual_written=[]
    if native_rituals:
        if original_wa is None or wa_entry is None:
            raise ModError('DATA/WA_MRG.MRG necessário para alterar rituais.')
        provenance=project.folder/'base'/'resumo.json'
        pinned=''
        if provenance.is_file():
            pinned=(json.loads(provenance.read_text(encoding='utf-8')).get('source_sha256') or {}).get('DATA/WA_MRG.MRG','')
        if not pinned or hashlib.sha256(original_wa).hexdigest()!=pinned:
            raise ModError('Rituais: hash de WA_MRG não corresponde à origem do projeto.')
        patched_wa,ritual_written=patch_rituals(
            patched_wa if patched_wa is not None else original_wa,native_rituals)

    god_icon_report=None
    if god_icon_card and not any(row['id']==god_icon_card and row.get('icones')
                                 for row in written_descriptions):
        from .ps1_god_icon import try_patch_god_icon, god_icon_asset
        if original_wa is None:
            raise ModError('O teste de ícone Deus exige DATA/WA_MRG.MRG no BIN de origem.')
        provenance=project.folder/'base'/'resumo.json'
        origin_hash=''
        if provenance.is_file():
            origin_hash=(json.loads(provenance.read_text(encoding='utf-8'))
                         .get('source_sha256') or {}).get('DATA/WA_MRG.MRG','')
        if not origin_hash or hashlib.sha256(original_wa).hexdigest()!=origin_hash:
            raise ModError('Teste God: WA_MRG.MRG não corresponde ao arquivo importado '
                           'ou o hash de origem está ausente.')
        patched_wa,patched_exe,god_icon_report=try_patch_god_icon(
            patched_wa if patched_wa is not None else original_wa,
            patched_exe,god_icon_card,god_icon_asset())

    god_chest_report=None
    god_display_report=None
    god_duel_report=None
    if god24_enabled:
        from .ps1_god24_chest import patch_god24_chest_preview
        from .ps1_god24_row_patch import apply as patch_real_list
        from .ps1_god24_display import apply as patch_god_display
        from .ps1_god24_play import apply as patch_duel
        kinds=[int(project.get(cid)['tipo_id']) for cid in project.cards if 1<=cid<= (740 if expansion.enabled else CARD_COUNT)]
        patched_exe,god_chest_report=patch_god24_chest_preview(
            original_exe,patched_exe,kinds)
        patched_exe,row_report=patch_real_list(original_exe,patched_exe,kinds)
        god_chest_report['renderizador_lista_bau']=row_report
        if original_wa is None:
            raise ModError('Tipo God: DATA/WA_MRG.MRG é necessário para exibir o ícone.')
        patched_exe,patched_wa,god_display_report=patch_god_display(
            original_exe,patched_exe,patched_wa if patched_wa is not None else original_wa)
        patched_exe,god_duel_report=patch_duel(
            original_exe,patched_exe,kinds)

    if description_icons:
        if original_wa is None:
            raise ModError('Ícones de descrição exigem DATA/WA_MRG.MRG no BIN de origem.')
        from .ps1_text import patch_icons
        patched_wa=patch_icons(patched_wa if patched_wa is not None else original_wa,description_icons)
    patched_exe,native_report=install_runtime(
        original_exe,patched_exe,native_plan,description_icons=bool(description_icons))
    patched_exe=patch_executable(patched_exe,mod_plan,profile=native_profile)
    chest_catalog_report = {'status': 'perfil_incompativel', 'cartas': 0}
    if native_profile:
        patched_exe = patch_chest_catalog(patched_exe, show_all=show_all_chest)
        chest_catalog_report = inspect_chest_catalog(patched_exe)
    from .ps1_lp_hud import patch_lp_hud, verify_lp_hud
    # O HUD é um patch separado da RAM: 20000 LP na memória requer também
    # cinco dígitos no painel para os dois lados.
    if native_profile:
        patched_exe,lp_hud_report=patch_lp_hud(
            original_exe,patched_exe,initial_lp=lp_hud_initial,hook=lp_hud_hook)
    else:
        lp_hud_report={'status':'perfil_incompativel' if lp_hud_initial>9999 else 'original',
                       'digitos':4,'lp_inicial':lp_hud_initial,'validado_epsxe':False}
    # A única instrução alterada fica no resultado de vitória; a regra
    # original por RANK continua intacta se a opção não estiver configurada.
    reward_report = ({'status': 'original_por_rank', 'estrelas': None}
                     if native_profile else {'status': 'perfil_incompativel', 'estrelas': None})
    if native_profile and win_reward_requested is not None:
        patched_exe, reward_report = patch_win_reward(patched_exe, win_reward_requested)
    from .ps1_rank_hud import inspect_rank_hud, patch_rank_hud
    rank_hud_report = {'status': 'perfil_incompativel'}
    if native_profile:
        patched_exe, rank_hud_report = patch_rank_hud(
            original_exe, patched_exe, occupied_until=native_plan.data_end)
    if duel_hud_hook is not None:
        # HUD novo: substitui a função do painel; o rank ao vivo é chamado por ele.
        from .ps1_duel_hud import apply as apply_duel_hud
        from .ps1_runtime_blob import ENTRY_POINTS as _RUNTIME_ENTRIES
        patched_exe, duel_hud_report = apply_duel_hud(
            patched_exe, duel_hud_hook,
            _RUNTIME_ENTRIES['DrawLiveRank'] if rank_hud_report.get('status') == 'aplicado' else None,
            duel_hud_portrait)
    from .ps1_ai import mode_for, patch_hard_ai, verify_hard_ai
    ai_mode=mode_for(project)
    if native_profile:
        patched_exe,ai_report=patch_hard_ai(original_exe,patched_exe,mode=ai_mode)
    else:
        ai_report={'modo':ai_mode,'status':'perfil_incompativel' if ai_mode!='normal'
                   else 'original', 'rotinas':[], 'validado_epsxe':False}
    if mod_plan.needs_wa:
        if original_wa is None or hashlib.sha256(original_wa).hexdigest()!=expected_wa:
            raise ModError('As tabelas de duelistas exigem o WA_MRG vinculado ao projeto.')
        patched_wa=patch_wa(patched_wa if patched_wa is not None else original_wa,mod_plan)

    price_report = []
    if prices_requested:
        price_source = wa_sha(project)
        if not original_wa or not price_source or hashlib.sha256(original_wa).hexdigest() != price_source:
            raise ModError('Alterar custos de Password exige o WA_MRG original vinculado e validado.')
        patched_wa, price_report = apply_password_prices(
            patched_wa if patched_wa is not None else original_wa,
            {cid: cost for cid, cost in prices_requested.items() if cid <= CARD_COUNT})

    if supreme_ids:
        if original_wa is None:
            raise ModError('Supreme exige DATA/WA_MRG.MRG do BIN de origem para gravar o ícone.')
        linked_wa = wa_sha(project)
        if linked_wa and hashlib.sha256(original_wa).hexdigest() != linked_wa:
            raise ModError('Supreme: o WA_MRG da imagem escolhida diverge do projeto vinculado.')
        patched_exe, patched_wa = patch_supreme(
            original_exe, patched_exe, patched_wa if patched_wa is not None else original_wa)

    magic_values_report = {'status': 'original'} if native_profile else {'status': 'perfil_incompativel'}
    if native_profile and not magic_values_empty(magic_values_requested):
        patched_exe, magic_values_report = apply_magic_values(patched_exe, magic_values_requested)

    cards_per_win_report = {'status': 'original_do_mod', 'cartas': 5} if native_profile else {
        'status': 'perfil_incompativel'}
    if native_profile and cards_per_win_requested is not None:
        patched_exe, patched_wa, cards_per_win_report = apply_cards_per_win(
            patched_exe, patched_wa if patched_wa is not None else original_wa, cards_per_win_requested)

    if quest_enabled:
        wa = patched_wa if patched_wa is not None else original_wa
        if len(wa) != len(original_wa) or len(wa) % PAYLOAD:
            raise ModError('Quests PS1 exigem o WA_MRG em setores de dados completos.')
        quest_scene_sector = len(wa) // PAYLOAD
        levels = EXPANDED_LEVELS if expansion.enabled else LEVEL_ADDR
        quest_catalog = project_quest_catalog(project, wa, exe=patched_exe, supreme=bool(supreme_ids))
        quest_payload, quest_config, quest_table = build_quest_overlay(
            patched_exe, quest_catalog, quests, level_address=levels)
        # The existing transfer adapter shifts subsequent requests by 18
        # thumbnails. Keep the quest scene before the extra full-art blocks.
        patched_wa = append_quest_scene(wa, quest_payload)

    expansion_report = expansion.report()
    if expansion.enabled:
        if not expected_wa:
            expected_wa = wa_sha(project)
        if not expected_wa or hashlib.sha256(original_wa).hexdigest() != expected_wa:
            raise ModError('Expansão: WA_MRG precisa ter o hash de origem registrado pelo extrator.')
        art_reports = {}
        patched_wa = expand_archive(patched_wa if patched_wa is not None else original_wa,
                                    project, expansion, prefix=native_plan.password_prefix,
                                    art_reports=art_reports)
        patched_exe = patch_expansion(original_exe, patched_exe, project, expansion,
                                      wa_sectors=len(original_wa) // PAYLOAD + (QUEST_SCENE_SECTORS if quest_enabled else 0))
        expansion_report.update(inspect_expansion(patched_exe))
        expansion_report['titulos_gravados'] = list(expansion.ids)
        written_titles.extend(expansion.ids)
        expansion_report['artes_proprias'] = list(art_reports)
        expansion_report['otimizacao_artes'] = art_reports
        # Os preços 723–740 foram gravados diretamente nos registros adicionais.
        price_report.extend({
            'id': cid, 'estrelas': prices_requested[cid],
            'offset_wa': PASSWORD_BASE + 18 * 2048 + cid * 8,
            'expandido': True,
        } for cid in sorted(prices_requested) if cid > CARD_COUNT)
        if expansion_report['status'] != 'aplicado':
            raise ModError('Expansão incompleta após instalar as tabelas e os adaptadores nativos.')
        chest_catalog_report = inspect_chest_catalog(patched_exe)
    if quest_enabled:
        patched_exe = install_quest_handlers(patched_exe, quest_handlers, quest_scene_sector)
    if splash_hook is not None:
        if has_summon_life(patched_exe):
            patched_exe, splash_report = apply_life_splash(patched_exe, splash_hook)
        else:
            splash_report = {'status': 'sem_efeitos_no_runtime'}
    if lifelink_hook is not None:
        patched_exe, lifelink_report = apply_lifelink(patched_exe, lifelink_hook, native_plan.capacity)
    if fixed_drop_hook is not None:
        patched_exe, fixed_drop_report = apply_fixed_drop(patched_exe, fixed_drop_hook, fixed_drop_map)
    if subtype_hook is not None:
        patched_exe, subtype_report = apply_subtypes(patched_exe, subtype_hook, subtype_pairs)
    if hand_bonus_hook is not None:
        from .ps1_hand_bonus import apply as apply_hand_bonus
        patched_exe, hand_bonus_report = apply_hand_bonus(patched_exe, hand_bonus_hook)
    if entry_effects_hook is not None:
        # Por último: encadeia no salto de entrada em campo deixado pelas rotinas acima.
        from .ps1_entry_effects import apply as apply_entry_effects
        from .ps1_lifelink import pending_address as lifelink_pending
        patched_exe, entry_effects_report = apply_entry_effects(
            patched_exe, entry_effects_hook, native_plan.capacity, ops=entry_ops,
            heal_pending=(lifelink_pending(lifelink_hook, native_plan.capacity)
                          if lifelink_hook is not None else None))

    # O Drop x15 pode substituir uma cópia anterior com a trava de abertura removida.
    if starter_choice_hook is not None:
        # Depois de quests/expansão: a área dos pools do overlay de nome recebe a rotina.
        from .ps1_starter_choice import apply as apply_starter_choice
        patched_exe, patched_wa, starter_choice_report = apply_starter_choice(
            patched_exe, patched_wa if patched_wa is not None else original_wa, starter_choice_decks,
            text_at=starter_choice_texts, cmap=starter_choice_cmap, cards=project.cards)

    if (not native_profile and patched_exe==original_exe and (patched_wa is None or patched_wa==original_wa)
            and patched_su is None):
        if audit_report is not None:
            from .ps1_compat import save_audit, explain_no_writable_changes
            dest = save_audit(project)
            raise ModError(explain_no_writable_changes(project, audit_report)
                           + f'\n\nRelatório salvo em: {dest}')
        raise ModError('Nenhuma diferença binária compatível foi encontrada para gerar o jogo.')

    base=output/'teste_ps1'
    base.mkdir(parents=True,exist_ok=True)

    # Mesmo nome de BIN de origem => mesmo arquivo de teste. O digest impede
    # colisões se dois nomes diferentes só variam em maiúsculas/caracteres
    # removidos pelo Windows (inclusive quando o nome precisa ser encurtado).
    safe_name=re.sub(r'[^A-Za-z0-9À-ÿ()\[\] .,_+-]', '_', original_bin.stem)
    safe_name=safe_name.strip(' .')[:96].rstrip(' .') or 'JOGO'
    name_id=hashlib.sha256(original_bin.name.encode('utf-8')).hexdigest()[:10]
    suffix = '_QUESTS' if quest_enabled else ''
    bin_file=base/f'FM_STUDIO_TESTE_{safe_name}_{name_id}{suffix}.bin'
    cue_file=bin_file.with_suffix('.cue')
    meta_file=bin_file.with_suffix('.json')
    quest_paths = (bin_file.with_suffix('.quests.json'), bin_file.with_suffix('.quests.bin')) if quest_enabled else ()
    target_paths=(bin_file,cue_file,meta_file,*quest_paths)
    if source_image in target_paths or original_bin in target_paths:
        raise ModError('A imagem original não pode ser usada como arquivo de saída.')
    if any(target.is_symlink() for target in target_paths):
        raise ModError('Destino de teste contém atalho/link simbólico; substituição bloqueada.')
    if any(target.is_dir() for target in target_paths):
        raise ModError('Destino de teste é uma pasta, não um arquivo.')
    replacing=bin_file.exists()
    changed=[]

    # Montagem e validação ocorrem em uma pasta temporária. Um erro de leitura
    # ou patch jamais apaga a última ISO de teste que funcionava.
    with tempfile.TemporaryDirectory(prefix='.fmstudio_build_',dir=base) as work:
        workspace=Path(work)
        stage_bin=workspace/bin_file.name
        stage_cue=workspace/cue_file.name
        stage_meta=workspace/meta_file.name
        with original_bin.open('rb') as origin,stage_bin.open('wb') as dest:
            shutil.copyfileobj(origin,dest,8*1024*1024)
        if stage_bin.stat().st_size!=original_bin.stat().st_size:
            raise ModError('Cópia do disco incompleta. BIN anterior preservado.')

        with stage_bin.open('r+b') as out:
            changed+=_write_file_patches(out,exe,original_exe,patched_exe)
            if patched_wa is not None and patched_wa!=original_wa:
                if len(patched_wa) == len(original_wa):
                    changed+=_write_file_patches(out,wa_entry,original_wa,patched_wa)
                else:
                    from .disc_append import append_iso_file
                    changed+=append_iso_file(out,wa_entry,original_wa,patched_wa)
            if patched_su is not None and patched_su != original_su:
                changed+=_write_file_patches(out,su_entry,original_su,patched_su)

        # A releitura confere o SLUS e, quando necessário, o arquivo WA gravado.
        with DiscReader(stage_bin) as verify:
            files={e.path.upper():e for e in verify.files() if not e.is_dir}
            reread_exe=b''.join(verify.read_entry(files['SLUS_014.11']))
            if reread_exe!=patched_exe:
                raise ModError('SLUS não corresponde após reempacotamento.')
            # Confirmar texto compilado de cada carta, não apenas ponteiro e FF.
            # Falha interrompe o build na pasta temporária, sem tocar no BIN anterior.
            confirmed_descriptions = []
            if written_descriptions:
                from .ps1_description_verify import inspect_exe_description
                catalog = {i:project.get(i) for i in project.cards} if hasattr(project, 'cards') else {}
                for row in written_descriptions:
                    checked = inspect_exe_description(
                        reread_exe, row['id'], texts[row['id']], catalog,
                        original_exe=original_exe, native_profile=native_profile)
                    expected_status = 'resumida' if row.get('resumida') else 'aplicada'
                    if (checked['status'] != expected_status or
                            'sha256_texto' in row and checked['sha256_texto_bin'] != row['sha256_texto']):
                        raise ModError(
                            f'Carta #{row["id"]}: texto do BIN não corresponde ao salvo no Studio: '
                            f'{checked["motivo"]} O BIN/CUE anterior foi preservado.')
                    if checked['offset_exe'] != row['offset_exe']:
                        raise ModError(
                            f'Carta #{row["id"]}: ponteiro da descrição difere do manifesto. '
                            'O BIN/CUE anterior foi preservado.')
                    confirmed_descriptions.append({
                        'id': row['id'],
                        'ponteiro': checked['ponteiro'],
                        'sha256_texto': checked['sha256_texto_bin'],
                        'status': checked['status'],
                    })
            if expansion.enabled:
                from .ps1_description_verify import _description_bytes
                empty_ids = set(range(CARD_COUNT + 1, PS1_CARD_CAPACITY + 1)) - written_ids
                for cid in sorted(empty_ids):
                    text, _, _ = _description_bytes(reread_exe, cid)
                    if text:
                        raise ModError(f'Carta #{cid}: a descrição vazia diverge no BIN final.')
            if native_profile and ai_mode!='normal' and not verify_hard_ai(original_exe,reread_exe,mode=ai_mode):
                raise ModError('IA PS1: patch incompleto após reempacotamento; BIN antigo preservado.')
            if native_profile and lp_hud_initial>9999 and not verify_lp_hud(
                    original_exe,reread_exe,initial_lp=lp_hud_initial):
                raise ModError('Contador de LP: cinco dígitos divergentes no BIN final. '
                               'A imagem anterior foi preservada.')
            if rank_hud_report['status'] == 'aplicado' and inspect_rank_hud(reread_exe)['status'] != 'aplicado':
                raise ModError('Rank no HUD: a extensão diverge no BIN final.')
            if duel_hud_report.get('status') == 'aplicado':
                from .ps1_duel_hud import installed as duel_hud_installed
                if duel_hud_installed(reread_exe) != duel_hud_hook:
                    raise ModError('HUD de duelo: a rotina diverge no BIN final.')
            if patched_wa is not None:
                reread_wa = b''.join(verify.read_entry(files['DATA/WA_MRG.MRG']))
                if reread_wa != patched_wa:
                    raise ModError('WA_MRG não corresponde após reempacotamento.')
            if patched_su is not None:
                if b''.join(verify.read_entry(files[SU_PATH])) != patched_su:
                    raise ModError('SU.MRG (fundo do menu) não corresponde após reempacotamento.')
            quest_report = {'status': 'desativado'}
            if quest_enabled:
                quest_report = inspect_quest_overlay(reread_exe, reread_wa, expanded=expansion.enabled)
                if (quest_report['status'] != 'aplicado'
                        or quest_report['sha256_tabela'] != hashlib.sha256(quest_table).hexdigest()):
                    raise ModError('O código e os requisitos de campanha divergem no BIN final.')
                reread_catalog = project_quest_catalog(
                    project, retail_archive_view(reread_wa) if expansion.enabled else reread_wa,
                    exe=reread_exe, level_address=levels, supreme=bool(supreme_ids))
                if reread_catalog.fingerprint() != quest_config['sha256_dados']:
                    raise ModError('As fontes de doação diferem dos drops, cartas ou pools do BIN final.')
                quest_report.update(seed=quest_config['seed'], requisitos=str(quest_paths[0]),
                                    tabela=str(quest_paths[1]))

        stage_cue.write_text(
            f'FILE "{bin_file.name}" BINARY\n'
            '  TRACK 01 MODE2/2352\n'
            '    INDEX 01 00:00:00\n',
            encoding='ascii'
        )
        result={'formato':'MODE2/2352','status':'PS1_PARCIAL_ATRIBUTOS_TEXTOS_ARTES',
                'bin':str(bin_file),'cue':str(cue_file),
                'nome_iso_origem':original_bin.name,
                'acao_arquivo':'substituido' if replacing else 'criado',
                'gerado_em':datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'sha256_slus_original':hashlib.sha256(original_exe).hexdigest(),
                'sha256_slus_modificado':hashlib.sha256(patched_exe).hexdigest(),
                'setores_modificados':len(changed),'lbas':sorted(changed),
                'nomes_aplicados':written_names,
                'titulos_gravados_ps1':written_titles,
                'descricoes_aplicadas':written_descriptions,
                'descricoes_confirmadas_no_bin':confirmed_descriptions,
                'descricoes_nao_gravadas':descriptions_not_written,
                'descricoes_resumidas_ps1':[{'id': row['id'], 'motivo': row['motivo']}
                                          for row in written_descriptions if row.get('resumida')],
                'cartas_novas_sem_descricao_ps1': new_without_text,
                'politica_descricoes_ps1':description_policy,
                'descricoes_somente_studio':descriptions_studio_only,
                'icones_de_descricao_ps1':sorted(description_icons),
                'efeitos_nativos_ps1':native_report,
                'ia_nativa_ps1':ai_report,
                'contador_lp_ps1':lp_hud_report,
                'rank_hud_ps1':rank_hud_report,
                'quests_campanha_ps1':quest_report,
                'catalogo_bau_ps1':chest_catalog_report,
                'catalogo_bau_completo_ativado':show_all_chest,
                'precos_password_ps1':price_report,
                'estrelas_por_vitoria_ps1':reward_report,
                'cartas_por_vitoria_ps1':cards_per_win_report,
                'bonus_equipamentos_ps1':equip_bonus_report,
                'valores_magicas_ps1':magic_values_report,
                'molduras_por_raridade_ps1':frames_report,
                'animacao_lp_ao_entrar_ps1':splash_report,
                'papel_parede_menu_ps1':wallpaper_report,
                'vinculo_com_vida_ps1':lifelink_report,
                'drop_fixo_ps1':fixed_drop_report,
                'espaco_menu_debug_ps1':debug_space_report,
                'hud_duelo_ps1':duel_hud_report,
                'subtipos_ps1':subtype_report,
                'bonus_mao_ps1':hand_bonus_report,
                'efeitos_entrada_ps1':entry_effects_report,
                'escolha_deck_inicial_ps1':starter_choice_report,
                'expansao_cartas_ps1':expansion_report,
                'edicao_do_mod_ps1':{'bloqueio_turno_inicial':native_profile,'aplicado':mod_plan.applied,
                                    'pendente':mod_plan.pending,
                                    'decks_fixos':list(native_plan.fixed_decks)},
                'artes_aplicadas':written_arts,
                'equipamentos_ps1_aplicados':native_written,
                'rituais_ps1_aplicados':ritual_written,
                'armadilhas_ps1_aplicadas':traps_written,
                'terrenos_ps1_aplicados':terrain_written,
                'limite_global_copias_ps1_aplicado':deck_copies_written,
                'lp_inicial_mips_aplicado':lp_written,
                'teste_visual_icone_deus':god_icon_report,
                'exibicao_tipo_god24':god_display_report,
                'teste_god24_atk_def_bau':god_chest_report,
                'teste_god24_roteamento_duelo':god_duel_report,
                'god24_cartas':god_cards if god24_enabled else [],
                'teste_tipo_god24':({'carta_id':god_cards[0],
                                      'cartas_ids':god_cards,
                                      'status':'TIPO_24_COM_NOME_E_ICONE',
                                      'aviso':'Roteamento de monstro conferido na cópia.',
                                      'atk_def_visiveis_no_bau':False,
                                      'tipo_deus_funcional_no_epsxe':False,
                                      'icone_de_tipo_instalado':True}
                                     if god24_enabled else None),
                'modo_equip_ps1':equip_mode,
                'estrategia_equip_ps1':equip_strategy if (native_equips or replacements) else 'sem-equip',
                'tamanho_bin':stage_bin.stat().st_size,
                'recursos_pendentes':audit_report['pendente_de_motor'] if audit_report else [],
                'aviso':'Confira os recursos aplicados e as pendências desta cópia PS1.'}

        if hasattr(project,'edits') and hasattr(project,'cards') and hasattr(project,'get'):
            from .disc_verify import verify_image_stats
            checked=verify_image_stats(project,stage_bin)
            if supreme_ids and (checked['supreme_ps1']['status'] != 'aplicado'
                                or checked['supreme_ps1']['ids'] != supreme_ids):
                raise ModError('Supreme: Guardian Stars, código ou textura divergentes no BIN final. '
                               'A cópia anterior foi preservada.')
            if checked['divergentes'] or not checked['god24_tipos_conferem']:
                raise ModError('BIN de teste diverge dos atributos do projeto. '
                               'A cópia anterior foi preservada.')
            if native_plan.data and checked['efeitos_nativos_ps1']['status']!='aplicado':
                raise ModError('As regras nativas do BIN divergem do projeto. '
                               'A cópia anterior foi preservada.')
            if native_profile and not all(checked['edicao_do_mod_ps1'].values()):
                raise ModError('As regras de duelo do BIN divergem do projeto. A cópia anterior foi preservada.')
            if native_profile and checked['catalogo_bau_ps1']['status'] != (
                    'aplicado' if show_all_chest else 'ausente'):
                raise ModError('A opção de visualização do baú não coincide com o BIN gerado. '
                               'A cópia anterior foi preservada.')
            if native_profile and frames_enabled and frame_status(reread_exe).get('status') != 'aplicado':
                raise ModError('Molduras por raridade ausentes no SLUS final. '
                               'A cópia anterior foi preservada.')
            if (native_profile and not magic_values_empty(magic_values_requested)
                    and not magic_values_match(reread_exe, magic_values_requested)):
                raise ModError('Valores das mágicas divergentes no SLUS final. '
                               'A cópia anterior foi preservada.')
            if native_profile and equip_bonus_requested and equip_bonus_status(reread_exe).get('bonus') != {
                    str(k): v for k, v in sorted(equip_bonus_requested.items())}:
                raise ModError('Bônus de equipamentos divergentes no SLUS final. '
                               'A cópia anterior foi preservada.')
            if native_profile and cards_per_win_requested is not None and (
                    cards_per_win_status(reread_exe).get('cartas') != cards_per_win_requested):
                raise ModError('Cartas por vitória divergentes no SLUS final. '
                               'A cópia anterior foi preservada.')
            if native_profile and win_reward_requested is not None:
                observed_reward = reward_status(reread_exe)
                if observed_reward != reward_report:
                    raise ModError('Estrelas por vitória divergentes no SLUS final. '
                                   'A cópia anterior foi preservada.')
            if prices_requested:
                with DiscReader(stage_bin) as price_disc:
                    price_entries = {e.path.upper(): e for e in price_disc.files() if not e.is_dir}
                    written_wa = b''.join(price_disc.read_entry(price_entries['DATA/WA_MRG.MRG']))
                observed_prices = read_prices(written_wa, prices_requested, expanded=expansion.enabled)
                if observed_prices != prices_requested:
                    raise ModError('Custos de Password divergentes no WA_MRG do BIN final. '
                                   'A cópia anterior foi preservada.')
            if god24_enabled:
                if (checked['god24_mascaras_bau']['status']!='aplicado_2_de_2'
                        or checked['god24_renderizador_lista_bau']
                        ['god24_patch_lista']['status']!='aplicado_3_de_3'):
                    raise ModError('God24: falta confirmação de 2/2 máscaras ou '
                                   '3/3 opcodes do renderizador no BIN final. '
                                   'A cópia anterior foi preservada.')
                if checked['god24_exibicao_tipo']['status']!='aplicado':
                    raise ModError('God24: nome ou ícone divergente na releitura do '
                                   'BIN final. Cópia anterior preservada.')
            if god_duel_report and checked['god24_roteamento_duelo']['status']!='aplicado':
                raise ModError('God24 em duelo: faltam instruções na releitura '
                               'do BIN final. Cópia anterior preservada.')
            checked['imagem']=str(bin_file)
            result['verificacao_atributos']=checked
            result['supreme_ps1'] = checked['supreme_ps1']
        stage_meta.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')

        # CUE e manifesto são pequenos: preservamos cópias deles para rollback.
        # O BIN novo só substitui o antigo no ÚLTIMO passo, via replace atômico
        # no mesmo volume. Se o ePSXe mantiver o BIN travado, não perdemos a
        # última versão de teste.
        sidecars=((cue_file,stage_cue),(meta_file,stage_meta))
        if quest_enabled:
            rules_path, table_path = (workspace / path.name for path in quest_paths)
            rules_path.write_text(json.dumps(quest_config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            table_path.write_bytes(quest_table)
            sidecars += tuple(zip(quest_paths, (rules_path, table_path)))
        old_sidecars={}
        for dest,_ in sidecars:
            backup=workspace/(dest.name+'.anterior')
            if dest.exists():
                shutil.copy2(dest,backup)
                old_sidecars[dest]=backup
            else:
                old_sidecars[dest]=None

        installed=[]
        try:
            for dest,prepared in sidecars:
                prepared.replace(dest)
                installed.append(dest)
            stage_bin.replace(bin_file)
        except OSError as exc:
            rollback_failures=[]
            for dest in reversed(installed):
                try:
                    backup=old_sidecars[dest]
                    if backup is not None:
                        backup.replace(dest)
                    else:
                        dest.unlink(missing_ok=True)
                except OSError as rollback_error:
                    rollback_failures.append(str(rollback_error))
            if rollback_failures:
                raise ModError('Falha ao substituir o BIN e restaurar arquivos auxiliares: '
                               + '; '.join(rollback_failures)) from exc
            raise ModError('Não foi possível substituir a imagem de teste. Feche o '
                           'jogo no ePSXe e tente novamente. A imagem anterior foi preservada.') from exc

    if audit_report:
        (output/'compatibilidade_ps1.json').write_text(
            json.dumps(audit_report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'
        )
    return result
