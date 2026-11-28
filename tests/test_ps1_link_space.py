"""Regras extras de efeitos e rotinas na área do Link Duel."""
import struct
import unittest

from fmstudio import ps1_link_space as link
from fmstudio.ps1_runtime import (CONFIG_ADDRESS, FAR_ADDRESS, FAR_END, NEAR_RULES, compile_effects)


def fake_exe():
    exe = bytearray(0x800 + 0x1D0000)
    exe[:8] = b'PS-X EXE'
    struct.pack_into('<II', exe, 0x18, 0x80010000, 0x1D0000)
    struct.pack_into('<I', exe, 0x800 + link.LINK_SITE - 0x80010000, link.LINK_ORIGINAL)
    return bytes(exe)


class Project:
    metadata = {}
    cards = {}

    def __init__(self, cards):
        self.effects = {str(cid): [{'evento': 'invocar', 'acao': 'dano_lp', 'alvo': 'inimigo',
                                    'valor': 100 + cid}] for cid in cards}

    def get(self, cid):
        return {'tipo_id': 0, 'ataque': 1000, 'defesa': 1000}


class LinkSpaceTests(unittest.TestCase):
    def test_claim_disables_link_duel_once(self):
        exe = fake_exe()
        self.assertEqual(link.status(exe), 'original')
        out, report = link.claim(exe)
        self.assertEqual(report['bytes'], 0x1E00)
        self.assertEqual(link.status(out), 'liberado')
        self.assertEqual(struct.unpack_from('<I', out, 0x800 + link.LINK_SITE - 0x80010000)[0],
                         link.LINK_DISABLED)
        self.assertEqual(link.claim(out)[1]['status'], 'liberado')
        changed = bytearray(exe)
        struct.pack_into('<I', changed, 0x800 + link.LINK_SITE - 0x80010000, 0)
        self.assertEqual(link.claim(bytes(changed))[1]['status'], 'indisponivel')

    def test_few_effects_stay_in_the_original_bank(self):
        plan = compile_effects(Project(range(1, 6)), True)
        self.assertEqual(plan.far, b'')

    def test_many_effects_overflow_to_link_area(self):
        cards = range(1, 301)
        plan = compile_effects(Project(cards), True)
        self.assertEqual(len(plan.accepted), 300)
        self.assertTrue(plan.far)
        self.assertLessEqual(plan.far_end, FAR_END)
        for cid in (1, 300):
            offset = struct.unpack_from('<H', plan.data, 2 + 2 * cid)[0]
            address = CONFIG_ADDRESS + offset
            if address >= FAR_ADDRESS:
                rule = plan.far[address - FAR_ADDRESS:]
            else:
                rule = plan.data[offset:]
            self.assertEqual(struct.unpack_from('<BBHHH', rule, 8)[3], 100 + cid)
        self.assertLessEqual(len(plan.data), 2 + 2 * 723 + NEAR_RULES + 8)


if __name__ == '__main__':
    unittest.main()
