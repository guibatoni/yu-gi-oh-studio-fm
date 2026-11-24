"""Escolha do deck inicial depois do nome (New Game) no PS1.

Fluxo retail (overlay de nome, WA_MRG setores 7968-7983, carregado em
0x80168000): ``NameEntry_Main`` repete ``Main_AdvanceFrame`` +
``NameEntry_PollCompletion`` (que chama ``NameEntry_UpdateDialog``) até o nome
ser aceito; depois chama ``NameEntry_BuildStarterDeck``, que sorteia as 40
cartas dos sete pools para ``gDuel_awPlayerDeck`` (0x801D0200).

Com a escolha ativada, duas chamadas do overlay passam por uma rotina
residente (bloco reservado no SLUS):

* ``poll`` (no lugar do ``jal NameEntry_UpdateDialog`` de PollCompletion):
  quando o nome já foi aceito (flag 0x20) e a caixa de confirmação fechou, em
  vez de deixar o jogo escurecer a tela abre uma caixa de texto com até 4
  opções (``FB 44`` do próprio sistema de diálogo do jogo: o cursor e o X são
  os do jogo). Com mais de 4 decks, cada página mostra 3 decks + "Mais
  decks…". A escolha é obrigatória (o diálogo do jogo não aceita cancelar).
  Escolhido o deck, devolve o controle ao jogo, que escurece e conclui.
* ``build`` (no lugar do ``jal NameEntry_BuildStarterDeck`` de Main): copia
  as 40 cartas do deck escolhido e marca cada uma como vista na Biblioteca
  (``Library_UpdateCardUsedFlag(id + 288)``, como o retail).

Rotina e decks ficam DENTRO do overlay de nome, no lugar dos sete pools de
sorteio (0x8016ABD4, 10 KB), que não são usados com a escolha obrigatória: não
gastam o espaço livre do SLUS. Só os textos das páginas vão para o SLUS.

Os textos das páginas ficam no banco de descrições (IDs 0xD3F0..), cuja área
livre o Studio já administra; a tabela de strings recebe os offsets.
"""
from __future__ import annotations

import struct

from .core import ModError
from .deep_extract import BANK_DESC, STRING_TABLE, exe_pos
from .mips_asm import Asm, hi_lo
from .tables import CARD_COUNT, DECK_SIZE

SETTINGS_KEY = 'ps1_escolha_deck_inicial'
MAX_DECKS = 8
MAX_NAME = 22
OVERLAY_SECTOR = 7968                  # fase executável do overlay de nome
OVERLAY_BASE = 0x80168000
OVERLAY_SIZE = 0x7800
POLL_RANGE = (0x80169C08, 0x80169C30)  # NameEntry_PollCompletion
MAIN_RANGE = (0x8016AA6C, 0x8016AB38)  # NameEntry_Main
UPDATE_DIALOG = 0x80169734
BUILD_STARTER = 0x8016A930
FLAGS = 0x8016D400                     # D_8016D400 (0x20 = nome aceito)
DIALOG_ID = 0x8016D4D2                 # D_8016D4D2 (caixa do overlay ativa)
CHOICE = 0x8009B34D                    # gDialog_bChoice
TEXT_BOX_CREATE = 0x80035BE4
TEXT_BOX_DESTROY = 0x80035B7C
TEXT_UPDATE = 0x80039794               # func_80039794: avança a caixa de texto
FIND_FREE_SLOT = 0x8004002C             # DisplayObject_FindFreeGeneralSlot
ACQUIRE_SLOT = 0x800400AC               # DisplayObject_AcquireSlot(slot, 2)
CONFIGURE_SPRITE = 0x800404CC           # DisplayObject_ConfigureSpriteAtPosition
SELECT_OT1 = 0x80042918                 # DisplayObject_SelectOrderingTable1
SET_DEPTH = 0x800428EC                  # DisplayObject_SetDepthOffset
RANGE_LAYOUT = 0x8003B6AC              # DuelEffect_SetEntryRangeLayout(2, 2): moldura/fundo da caixa
LIBRARY_SEEN = 0x8002CCE4              # Library_UpdateCardUsedFlag
PLAYER_DECK = 0x801D0200               # gDuel_awPlayerDeck
OVERLAY_BLOCK = 0x8016ABD4             # gNameEntry_aStarterDeckPools: 7 pools sem uso com a escolha
OVERLAY_BLOCK_SIZE = 7 * 0x5B8
FIRST_TEXT_ID = 0x3F0                  # índices livres da tabela (texto 0xD3F0+)
BOX = (2, 16, 176, 288, 48)            # canal e retângulo da caixa do overlay de nome
DONE_MASK, DONE = 0x2008, 0x2000
MORE_LABEL = 'Mais decks...'


def settings(project) -> dict:
    raw = (getattr(project, 'metadata', None) or {}).get(SETTINGS_KEY) or {}
    decks = [str(name) for name in raw.get('decks', []) if str(name).strip()][:MAX_DECKS]
    return {'ativado': bool(raw.get('ativado')), 'decks': decks}


def save_settings(project, *, enabled: bool, decks: list[str]) -> dict:
    clean = {'ativado': bool(enabled), 'decks': [str(d) for d in decks][:MAX_DECKS]}
    if clean['ativado'] and len(clean['decks']) < 2:
        raise ModError('Escolha pelo menos 2 perfis para o jogador escolher.')
    before = project.metadata
    project.metadata = {**before, SETTINGS_KEY: clean}
    try:
        project.save()
    except OSError:
        project.metadata = before
        raise
    return clean


def resolve_decks(project, profiles: dict) -> list[tuple[str, list[int]]]:
    """[(nome, 40 IDs)] na ordem escolhida; erro claro se algo não serve."""
    chosen = settings(project)
    out = []
    for name in chosen['decks']:
        profile = profiles.get(name)
        if profile is None:
            raise ModError(f'Escolha de deck: o perfil "{name}" não existe mais.')
        cards = [int(cid) for cid in profile.get('cartas', [])]
        if profile.get('pools') or len(cards) != DECK_SIZE:
            raise ModError(f'Escolha de deck: o perfil "{name}" precisa ter exatamente 40 cartas fixas '
                           '(sem pools ponderados).')
        if any(not 1 <= cid <= CARD_COUNT for cid in cards):
            raise ModError(f'Escolha de deck: o perfil "{name}" usa cartas fora de #001–#{CARD_COUNT}.')
        out.append((name, cards))
    if len(out) < 2:
        raise ModError('Escolha de deck: selecione pelo menos 2 perfis.')
    return out


def pages(count: int) -> list[tuple[int, int, bool]]:
    """[(primeiro deck, quantidade, tem "Mais")] por página."""
    if count <= 4:
        return [(0, count, False)]
    out = []
    for first in range(0, count, 3):
        out.append((first, min(3, count - first), True))
    return out


def page_text(lines: list[bytes], terminator_offset: int, header: int = 0) -> bytes:
    """FB (cabeçalho<<4 | linhas) + linhas (FE) + FB 80 com saltos para o FF final + FF.

    Sem o bit 0x40: ao confirmar, o jogo solta o destaque e encerra a caixa.
    Com cabeçalho (1-3 linhas antes das opções) o jogo usa exatamente 2 opções.
    """
    count = len(lines)
    choices = count - header
    body = bytes((0xFB, (header << 4) | count)) + b''.join(line + b'\xfe' for line in lines)
    jumps = struct.pack(f'<{choices}H', *([terminator_offset] * choices))
    return body + b'\xfb\x80' + jumps + b'\xff'


def page_layout(raw_lines: list[bytes], header: int = 0) -> int:
    """Tamanho em bytes de uma página (para reservar antes de saber o offset)."""
    return 2 + sum(len(line) + 1 for line in raw_lines) + 2 + 2 * (len(raw_lines) - header) + 1


CONFIRM_LINES = ('Iniciar o jogo com', '{deck}?', 'Sim', 'Nao, escolher outro')


def confirm_lines(name: bytes, cmap: dict, cards: dict) -> list[bytes]:
    first, _, yes, no = (encode_name(text, cmap, cards) for text in
                         (CONFIRM_LINES[0], 'x', CONFIRM_LINES[2], CONFIRM_LINES[3]))
    question = encode_name('?', cmap, cards)
    return [first, name + question, yes, no]


def _data_words(data: bytes) -> list[int]:
    data = data + bytes(-len(data) % 4)
    return list(struct.unpack(f'<{len(data) // 4}I', data))


HELD = 0x8009B3A4                      # botões segurados (pad 1)
STATE_PAGE, STATE_CHOSEN, STATE_CONFIRM, STATE_PENDING = 1, 2, 4, 5


def _assemble(base: int, page_rows, decks, confirm_ids=None) -> Asm:
    """poll / open_box / build + dados (estado, páginas, confirmações, decks).

    Estado (+0): 0 parado, 1 página aberta, 4 confirmação aberta, 5 esperando
    soltar os botões para abrir a próxima caixa (tipo em +3), 2 escolhido.
    +1 página, +2 deck escolhido, +3 próxima caixa, +4 ponteiro da caixa.
    """
    n_pages = len(page_rows)
    confirm_ids = list(confirm_ids or [0] * len(decks))
    a = Asm(base)
    ch, cl = hi_lo(CHOICE)
    # --- poll: no lugar do jal NameEntry_UpdateDialog em PollCompletion
    a.label('poll')
    a.addiu('sp', 'sp', -0x28)
    a.sw('ra', 0x24, 'sp'); a.sw('s0', 0x20, 'sp'); a.sw('s1', 0x1C, 'sp')
    a.la('s0', 'state')
    a.lbu('t0', 0, 's0')
    fh, fl = hi_lo(FLAGS)
    a.lui('t2', fh)
    a.lbu('t3', fl, 't2')
    a.lhu('t4', fl + (DIALOG_ID - FLAGS), 't2')
    a.andi('t3', 't3', 0x20)                    # nome aceito?
    a.ori('t1', 'zero', STATE_PAGE)
    a.beq('t0', 't1', 'showing')
    a.ori('t1', 'zero', STATE_CONFIRM)
    a.beq('t0', 't1', 'showing')
    a.ori('t1', 'zero', STATE_PENDING)
    a.beq('t0', 't1', 'pending')
    a.ori('t1', 'zero', STATE_CHOSEN)
    a.bne('t0', 't1', 'idle')
    a.nop()
    a.bnez('t3', 'orig')                        # escolhido: o jogo escurece e conclui
    a.nop()
    a.b('orig')
    a.sb('zero', 0, 's0')
    a.label('idle')
    a.beqz('t3', 'orig')
    a.nop()
    a.bnez('t4', 'orig')                        # caixa do jogo ainda aberta
    a.nop()
    a.sb('zero', 1, 's0')                       # página 0
    a.b('go_page')
    a.nop()

    a.label('pending')                          # espera soltar o X que fechou a caixa anterior
    hh, hl = hi_lo(HELD)
    a.lui('t0', hh)
    a.lhu('t0', hl, 't0')
    a.nop()
    a.bnez('t0', 'out')
    a.lbu('a1', 3, 's0')                        # delay: tipo da próxima caixa
    a.ori('t1', 'zero', STATE_CONFIRM)
    a.beq('a1', 't1', 'open_confirm')
    a.nop()
    a.lbu('t0', 1, 's0')                        # página
    a.nop()
    a.sll('t0', 't0', 3)
    a.addu('t0', 't0', 's0')
    a.jal('open_box')
    a.lhu('a0', 8, 't0')                        # delay: id do texto da página
    a.b('out')
    a.nop()
    a.label('open_confirm')
    a.lbu('t0', 2, 's0')                        # deck escolhido
    a.la('t1', 'confirms')
    a.sll('t0', 't0', 1)
    a.addu('t0', 't0', 't1')
    a.jal('open_box')
    a.lhu('a0', 0, 't0')                        # delay: id do texto de confirmação
    a.b('out')
    a.nop()

    a.label('showing')
    a.jal(TEXT_UPDATE)
    a.nop()
    a.lw('s1', 4, 's0')
    a.nop()
    a.lhu('t0', 0x34, 's1')
    a.nop()
    a.andi('t0', 't0', DONE_MASK)
    a.ori('t1', 'zero', DONE)
    a.bne('t0', 't1', 'out')
    a.nop()
    a.lui('t0', ch)
    a.lb('s1', cl, 't0')                        # opção escolhida
    a.jal(TEXT_BOX_DESTROY)
    a.lw('a0', 4, 's0')
    a.lbu('t0', 0, 's0')
    a.ori('t1', 'zero', STATE_CONFIRM)
    a.bne('t0', 't1', 'page_answer')
    a.nop()
    a.bnez('s1', 'go_page')                     # "Não": volta para a mesma página
    a.ori('t1', 'zero', STATE_CHOSEN)
    a.b('out')
    a.sb('t1', 0, 's0')                         # "Sim": escolhido
    a.label('page_answer')
    a.lbu('t0', 1, 's0')
    a.nop()
    a.sll('t0', 't0', 3)
    a.addu('t0', 't0', 's0')
    a.lbu('t1', 8 + 2, 't0')                    # primeiro deck da página
    a.lbu('t2', 8 + 3, 't0')                    # decks na página
    a.lbu('t3', 8 + 4, 't0')                    # tem "Mais"
    a.sltu('t4', 's1', 't2')
    a.beqz('t4', 'not_deck')
    a.addu('t1', 't1', 's1')
    a.sb('t1', 2, 's0')                         # deck escolhido: pede confirmação
    a.ori('t1', 'zero', STATE_CONFIRM)
    a.b('set_pending')
    a.nop()
    a.label('not_deck')
    a.beqz('t3', 'go_page')                     # resposta inválida: mostra de novo
    a.nop()
    a.bne('s1', 't2', 'go_page')
    a.nop()
    a.lbu('t0', 1, 's0')                        # "Mais decks": próxima página (circular)
    a.nop()
    a.addiu('t0', 't0', 1)
    a.sltiu('t1', 't0', n_pages)
    a.bnez('t1', 'set_page')
    a.nop()
    a.move('t0', 'zero')
    a.label('set_page')
    a.sb('t0', 1, 's0')
    a.label('go_page')
    a.ori('t1', 'zero', STATE_PAGE)
    a.label('set_pending')
    a.sb('t1', 3, 's0')
    a.ori('t1', 'zero', STATE_PENDING)
    a.b('out')
    a.sb('t1', 0, 's0')
    a.label('orig')
    a.jal(UPDATE_DIALOG)
    a.nop()
    a.label('out')
    a.lw('ra', 0x24, 'sp'); a.lw('s0', 0x20, 'sp'); a.lw('s1', 0x1C, 'sp')
    a.jr('ra')
    a.addiu('sp', 'sp', 0x28)

    # --- open_box(a0 = id do texto, a1 = estado) com s0 = estado
    a.label('open_box')
    a.addiu('sp', 'sp', -0x30)
    a.sw('ra', 0x2C, 'sp')
    a.sw('s1', 0x28, 'sp')
    a.sw('s2', 0x24, 'sp')
    a.move('s1', 'a0')
    a.move('s2', 'a1')
    a.ori('a0', 'zero', BOX[0])                 # layout do canal 2, como o overlay de nome
    a.jal(RANGE_LAYOUT)
    a.ori('a1', 'zero', 2)
    a.move('a1', 's1')
    channel, x, y, w, h = BOX
    a.ori('t1', 'zero', w); a.sw('t1', 0x10, 'sp')
    a.ori('t1', 'zero', h); a.sw('t1', 0x14, 'sp')
    a.ori('a0', 'zero', channel)
    a.ori('a2', 'zero', x)
    a.jal(TEXT_BOX_CREATE)
    a.ori('a3', 'zero', y)
    a.sw('v0', 4, 's0')
    a.ori('t0', 'zero', 20)
    a.sb('t0', 0x59, 'v0')
    a.lui('t1', ch)
    a.sb('zero', cl, 't1')                      # gDialog_bChoice = 0
    a.lhu('t0', 0x34, 'v0')
    a.nop()
    a.ori('t0', 't0', 8)
    a.sh('t0', 0x34, 'v0')
    # Moldura/fundo (sprite 23, 257) em box->field_2C, como o overlay de nome.
    a.jal(FIND_FREE_SLOT)
    a.nop()
    a.move('a0', 'v0')
    a.jal(ACQUIRE_SLOT)
    a.ori('a1', 'zero', 2)
    a.lw('t0', 4, 's0')
    a.move('s1', 'v0')
    a.sw('v0', 0x2C, 't0')
    a.sw('zero', 0x10, 'sp')
    a.sw('zero', 0x14, 'sp')
    a.ori('t1', 'zero', 23); a.sw('t1', 0x18, 'sp')
    a.ori('t1', 'zero', 257); a.sw('t1', 0x1C, 'sp')
    a.move('a0', 's1')
    a.ori('a1', 'zero', x)
    a.ori('a2', 'zero', y)
    a.jal(CONFIGURE_SPRITE)
    a.move('a3', 'zero')
    a.jal(SELECT_OT1)
    a.move('a0', 's1')
    a.move('a0', 's1')
    a.jal(SET_DEPTH)
    a.ori('a1', 'zero', 19)
    a.lhu('t0', 8, 's1')
    a.nop()
    a.ori('t0', 't0', 8)                        # DISPLAY_OBJECT_FLAG_SCREEN_SPACE
    a.sh('t0', 8, 's1')
    a.label('layout')
    a.jal(TEXT_UPDATE)
    a.nop()
    a.lw('t0', 4, 's0')
    a.nop()
    a.lw('t0', 0x30, 't0')
    a.nop()
    a.beqz('t0', 'layout')
    a.nop()
    a.sb('s2', 0, 's0')                         # estado = página ou confirmação
    a.lw('ra', 0x2C, 'sp')
    a.lw('s1', 0x28, 'sp')
    a.lw('s2', 0x24, 'sp')
    a.jr('ra')
    a.addiu('sp', 'sp', 0x30)

    # --- build: no lugar de NameEntry_BuildStarterDeck
    a.label('build')
    a.la('t0', 'state')
    a.lbu('t1', 0, 't0')
    a.ori('t2', 'zero', 2)
    a.beq('t1', 't2', 'chosen')
    a.nop()
    a.sb('zero', 2, 't0')                       # sem escolha (não deveria ocorrer): 1º deck
    a.label('chosen')
    a.addiu('sp', 'sp', -0x20)
    a.sw('ra', 0x1C, 'sp'); a.sw('s0', 0x18, 'sp'); a.sw('s1', 0x14, 'sp'); a.sw('s2', 0x10, 'sp')
    a.sb('zero', 0, 't0')                       # consome a escolha
    a.lbu('t1', 2, 't0')
    a.la('s0', 'decks')
    a.sll('t2', 't1', 6)                        # índice * 80 bytes (40 x u16)
    a.sll('t1', 't1', 4)
    a.addu('t1', 't1', 't2')
    a.addu('s0', 's0', 't1')
    dh, dl = hi_lo(PLAYER_DECK)
    a.lui('s1', dh); a.addiu('s1', 's1', dl)
    a.ori('s2', 'zero', DECK_SIZE)
    a.label('copy')
    a.lhu('a0', 0, 's0')
    a.addiu('s0', 's0', 2)
    a.sh('a0', 0, 's1')
    a.addiu('s1', 's1', 2)
    a.jal(LIBRARY_SEEN)
    a.addiu('a0', 'a0', 288)                    # bandeira "vista" = id + 288
    a.addiu('s2', 's2', -1)
    a.bnez('s2', 'copy')
    a.nop()
    a.lw('ra', 0x1C, 'sp'); a.lw('s0', 0x18, 'sp'); a.lw('s1', 0x14, 'sp'); a.lw('s2', 0x10, 'sp')
    a.jr('ra')
    a.addiu('sp', 'sp', 0x20)

    # --- dados
    # Sem align(8): o tamanho do bloco não pode depender do endereço reservado
    # (block_size é calculado antes). Código já termina alinhado a 4.
    a.label('state')
    a.word(0); a.word(0)                        # estado, página, escolhido, pad | caixa
    table = b''.join(struct.pack('<HBBB3x', text_id, first, count, int(more))
                     for text_id, first, count, more in page_rows)
    for value in _data_words(table):
        a.word(value)
    a.label('confirms')
    for value in _data_words(struct.pack(f'<{len(confirm_ids)}H', *confirm_ids)):
        a.word(value)
    a.label('decks')
    for deck in decks:
        for value in _data_words(struct.pack(f'<{DECK_SIZE}H', *deck)):
            a.word(value)
    return a


def code(base: int, page_rows, decks, confirm_ids=None) -> bytes:
    return _assemble(base, page_rows, decks, confirm_ids).bytes()


def _entries(base: int, page_rows=None, decks=None, confirm_ids=None) -> dict:
    page_rows = page_rows or [(0xD3F0, 0, 2, False)]
    decks = decks or [[1] * DECK_SIZE] * 2
    asm = _assemble(base, page_rows, decks, confirm_ids)
    asm.bytes()
    return {'poll': asm.labels['poll'], 'build': asm.labels['build']}


def block_size(n_decks: int) -> int:
    rows = [(0, 0, 0, False)] * len(pages(n_decks))
    return len(code(0x80100000, rows, [[1] * DECK_SIZE] * n_decks))


def _jal(target: int) -> int:
    return 0x0C000000 | ((target & 0x0FFFFFFF) >> 2)


def _overlay_offset(address: int) -> int:
    return OVERLAY_SECTOR * 0x800 + (address - OVERLAY_BASE)


def _find_call(wa: bytes, span: tuple[int, int], target: int) -> int:
    word = struct.pack('<I', _jal(target))
    hits = [address for address in range(span[0], span[1], 4)
            if wa[_overlay_offset(address):_overlay_offset(address) + 4] == word]
    if len(hits) != 1:
        raise ModError('Escolha de deck: o overlay de nome deste WA_MRG não é o esperado; '
                       'o jogo mantém o deck sorteado.')
    return hits[0]


def patch_overlay(wa: bytes, hook: int) -> bytes:
    labels = _entries(hook)
    if len(wa) < _overlay_offset(OVERLAY_BASE + OVERLAY_SIZE):
        raise ModError('Escolha de deck: WA_MRG truncado no overlay de nome.')
    poll_site = _find_call(wa, POLL_RANGE, UPDATE_DIALOG)
    main_site = _find_call(wa, MAIN_RANGE, BUILD_STARTER)
    out = bytearray(wa)
    struct.pack_into('<I', out, _overlay_offset(poll_site), _jal(labels['poll']))
    struct.pack_into('<I', out, _overlay_offset(main_site), _jal(labels['build']))
    return bytes(out)


def encode_name(name: str, cmap: dict, cards: dict) -> bytes:
    from .ps1_text import compile_description
    raw, _, _ = compile_description(name.strip()[:MAX_NAME], cmap, cards)
    raw = raw.split(b'\xfe')[0].replace(b'\xff', b'')
    if not raw:
        raise ModError(f'Escolha de deck: o nome "{name}" não tem letras que o PS1 mostre.')
    return raw


def _texts(decks, cmap, cards):
    """[(linhas, cabeçalho)] das páginas e depois das confirmações (uma por deck)."""
    names = [encode_name(name, cmap, cards) for name, _ in decks]
    more = encode_name(MORE_LABEL, cmap, cards)
    out = [(names[first:first + count] + ([more] if has_more else []), 0)
           for first, count, has_more in pages(len(decks))]
    out += [(confirm_lines(name, cmap, cards), 2) for name in names]
    return out


def apply(exe: bytes, wa: bytes, decks: list[tuple[str, list[int]]], *, text_at: list[int],
          hook: int = OVERLAY_BLOCK,
          cmap: dict, cards: dict) -> tuple[bytes, bytes, dict]:
    """Grava rotina+dados no overlay, os textos em ``text_at`` e liga o overlay."""
    layout = pages(len(decks))
    texts = _texts(decks, cmap, cards)
    if len(text_at) != len(texts):
        raise ModError('Escolha de deck: espaço de texto reservado incorreto.')
    out = bytearray(exe)
    ids = []
    for index, ((lines, header), address) in enumerate(zip(texts, text_at)):
        size = page_layout(lines, header)
        if not (BANK_DESC <= address and address + size <= BANK_DESC + 0x10000):
            raise ModError('Escolha de deck: texto fora do banco de descrições.')
        text = page_text(lines, address + size - 1 - BANK_DESC, header)
        at = exe_pos(address, exe, len(text))
        if any(out[at:at + len(text)]):
            raise ModError('Escolha de deck: a área de texto reservada não está livre.')
        out[at:at + len(text)] = text
        text_id = FIRST_TEXT_ID + index
        struct.pack_into('<H', out, exe_pos(STRING_TABLE + 2 * text_id, exe, 2), address - BANK_DESC)
        ids.append(0xD000 + text_id)
    rows = [(ids[page], first, count, has_more) for page, (first, count, has_more) in enumerate(layout)]
    block = code(hook, rows, [cards_ for _, cards_ in decks], ids[len(layout):])
    if len(block) > OVERLAY_BLOCK_SIZE:
        raise ModError('Escolha de deck: rotina maior que a área dos pools do overlay.')
    patched_wa = bytearray(patch_overlay(wa, hook))
    at = _overlay_offset(hook)
    patched_wa[at:at + OVERLAY_BLOCK_SIZE] = block + bytes(OVERLAY_BLOCK_SIZE - len(block))
    return bytes(out), bytes(patched_wa), {
        'status': 'aplicado', 'decks': [name for name, _ in decks], 'paginas': len(layout),
        'confirmacao': True, 'rotina': f'0x{hook:08X}', 'textos': [f'0x{i:04X}' for i in ids],
        'validado_epsxe': False}


def text_sizes(decks: list[tuple[str, list[int]]], cmap: dict, cards: dict) -> list[int]:
    return [page_layout(lines, header) for lines, header in _texts(decks, cmap, cards)]
