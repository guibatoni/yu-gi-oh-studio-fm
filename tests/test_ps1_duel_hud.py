"""HUD de duelo novo: a rotina MIPS roda no intérprete e os pacotes de GPU que ela
enfileira são desenhados e comparados com a prévia do layout."""
import struct
import unittest

from fmstudio import ps1_duel_hud as hud
from fmstudio.duel_hud_layout import SIDES, bar_fill, render_preview
from tests.mini_mips import M, MiniCpu

try:
    from PIL import Image, ImageDraw
except ImportError:          # pragma: no cover
    Image = None

HOOK = 0x80030400
RANK = 0x801CF18C
OWNER, PANEL = 0x800F0600, 0x800F0700
OT, OT_ENTRIES = 0x800F1000, 0x800F2000
PACKETS = 0x800F4000
RETURN = 0x80000100


def run(lp=(1000, 7000), start=(8000, 8000), drawn=(5, 0), *, rank=True, panel_xy=(281, 28)):
    cpu = MiniCpu()
    cpu.load(HOOK, hud.code(HOOK, RANK if rank else None))
    for side in (0, 1):
        state = hud.SIDE_STATES + 0x20 * side
        cpu.load(state + 0x12, struct.pack('<HHHb', lp[side], lp[side], start[side], drawn[side]))
    cpu.load(OWNER + 0x50, struct.pack('<I', PANEL))
    cpu.load(PANEL + 8, struct.pack('<H', 0xC0))
    cpu.load(PANEL + 0x14, struct.pack('<H', 3))                  # profundidade
    cpu.load(PANEL + 0x17, bytes([1]))                           # ot_index
    cpu.load(PANEL + 0x30, struct.pack('<hh', *panel_xy))
    cpu.load(hud.ORDERING_TABLES + 4, struct.pack('<I', OT))
    cpu.load(OT, struct.pack('<III', 8, OT_ENTRIES, 0))          # length, org, offset
    cpu.load(OT_ENTRIES + 3 * 4, struct.pack('<I', 0x00FFFFFF))  # entrada vazia (fim da lista)
    cpu.load(hud.PACKET_POINTER, struct.pack('<I', PACKETS))
    cpu.load(hud.DRAW_OFFSET, struct.pack('<hh', 0, 0))
    calls, rank_calls = [], []

    def update(c):
        calls.append(c.r[4])

    def live_rank(c):
        rank_calls.append((c.r[4], c.r[5], c.r[6], c.r[7],
                           struct.unpack_from('<hh', c.mem, (PANEL + 0x30) & M),
                           struct.unpack_from('<I', c.mem, (hud.SCRATCH_SPRITE + 8) & 0x1FFFFF)[0]
                           if False else None))
    cpu.r[29], cpu.r[31] = 0x801FFF00, RETURN
    saved = [0x5A5A0000 + i for i in range(8)]
    for i, reg in enumerate(range(16, 24)):
        cpu.r[reg] = saved[i]
    cpu.r[4] = OWNER
    end = cpu.run(HOOK, stop={RETURN}, limit=200000, calls={hud.UPDATE_LP: update, RANK: live_rank})
    assert end == RETURN
    assert cpu.r[29] == 0x801FFF00
    assert [cpu.r[r] for r in range(16, 24)] == saved, 'registradores s0-s7 não preservados'
    return cpu, calls, rank_calls


def packets(cpu):
    """Segue a entrada da OT como a GPU: do pacote mais novo ao mais antigo."""
    out = []
    pointer = struct.unpack_from('<I', cpu.mem, (OT_ENTRIES + 12) & M)[0]
    while pointer & 0xFFFFFF != 0xFFFFFF:
        address = 0x80000000 | (pointer & 0xFFFFFF)
        tag = struct.unpack_from('<I', cpu.mem, address & M)[0]
        length = tag >> 24
        words = struct.unpack_from(f'<{length}I', cpu.mem, (address + 4) & M)
        out.append(words)
        pointer = tag & 0xFFFFFF
        assert len(out) < 2000
    return out


def rasterize(words_list, base):
    img = base.copy()
    draw = ImageDraw.Draw(img)

    def xy(word):
        x, y = word & 0xFFFF, word >> 16
        return (x - 0x10000 if x & 0x8000 else x, y - 0x10000 if y & 0x8000 else y)
    for words in words_list:
        code, color = words[0] >> 24, words[0] & 0xFFFFFF
        rgb = (color & 0xFF, color >> 8 & 0xFF, color >> 16 & 0xFF)
        if code == 0x28:
            v = [xy(w) for w in words[1:5]]
            draw.polygon([v[0], v[1], v[2]], fill=rgb)
            draw.polygon([v[1], v[3], v[2]], fill=rgb)
        elif code == 0x60:
            x, y = xy(words[1])
            w, h = words[2] & 0xFFFF, words[2] >> 16
            draw.rectangle([x, y, x + w - 1, y + h - 1], fill=rgb)
        else:
            raise AssertionError(f'primitiva inesperada {code:#x}')
    return img


@unittest.skipIf(Image is None, 'Pillow ausente')
class DuelHudMipsTests(unittest.TestCase):
    def test_draws_the_same_picture_as_the_preview(self):
        for lp, start, deck in (((1000, 7000), (8000, 8000), (35, 40)),
                                ((65535, 0), (8000, 4000), (0, 40)),
                                ((8000, 12345), (8000, 20000), (40, 1))):
            cpu, calls, ranks = run(lp, start, tuple(40 - d for d in deck))
            base = Image.new('RGB', (320, 240), (10, 20, 30))
            got = rasterize(packets(cpu), base)          # a GPU segue a cadeia: mais novo primeiro
            want = render_preview(base, lp=lp, start=start, deck=deck)
            diff = sum(a != b for a, b in zip(got.getdata(), want.getdata()))
            if diff:
                got.resize((960, 720)).save('/tmp/hud_got.png')
                want.resize((960, 720)).save('/tmp/hud_want.png')
            self.assertEqual(diff, 0, f'{diff} pixels diferentes para LP {lp}')
            self.assertEqual(calls, [hud.SIDE_STATES, hud.SIDE_STATES + 0x20])

    def test_hides_old_panel_and_restores_packet_pointer(self):
        cpu, _, ranks = run()
        self.assertEqual(struct.unpack_from('<H', cpu.mem, (PANEL + 8) & M)[0], 0x80)
        end = struct.unpack_from('<I', cpu.mem, hud.PACKET_POINTER & M)[0]
        self.assertEqual(end - PACKETS, sum(4 * (len(w) + 1) for w in packets(cpu)))
        self.assertEqual(len(ranks), 1)
        owner, sprite, value, count, xy, _ = ranks[0]
        self.assertEqual((owner, sprite, value, count), (PANEL, hud.SCRATCH_SPRITE, 0, 0))
        self.assertEqual(xy, (hud.RANK_X + 35, hud.RANK_Y - 23))
        # posição do painel volta ao normal depois do rank
        self.assertEqual(struct.unpack_from('<hh', cpu.mem, (PANEL + 0x30) & M), (281, 28))

    def test_without_rank(self):
        _, _, ranks = run(rank=False)
        self.assertEqual(ranks, [])

    def test_bar_fill_rules(self):
        side = SIDES[0]
        width = side.bar[2] - side.bar[0] + 1
        self.assertEqual(bar_fill(side, 8000, 8000), width)
        self.assertEqual(bar_fill(side, 9000, 8000), width)      # cura acima do inicial: cheia
        self.assertEqual(bar_fill(side, 0, 8000), 0)
        self.assertEqual(bar_fill(side, 4000, 8000), width // 2)


class DuelHudPatchTests(unittest.TestCase):
    def exe(self):
        data = bytearray(0x800 + 0x40000)
        data[:8] = b'PS-X EXE'
        struct.pack_into('<I', data, 0x18, 0x80010000)
        struct.pack_into('<I', data, 0x1C, len(data) - 0x800)
        struct.pack_into('<II', data, 0x800 + hud.ENTRY - 0x80010000, *hud.ENTRY_WORDS)
        return bytes(data)

    def test_apply_view_installed(self):
        exe = self.exe()
        out, report = hud.apply(exe, HOOK, RANK)
        self.assertEqual(report['status'], 'aplicado')
        self.assertEqual(hud.installed(out), HOOK)
        self.assertEqual(hud.runtime_view(out)[0x800 + hud.ENTRY - 0x80010000:][:8],
                         struct.pack('<II', *hud.ENTRY_WORDS))
        self.assertIsNone(hud.installed(exe))
        self.assertEqual(len(hud.code(HOOK, RANK)), hud.block_size(True))


if __name__ == '__main__':
    unittest.main()
