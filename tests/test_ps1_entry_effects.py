"""Efeitos de entrada com animações das mágicas (ps1_entry_effects) no intérprete MIPS."""
import struct
import unittest

from fmstudio import ps1_entry_effects as ee
from tests.mini_mips import MiniCpu

HOOK = 0x80030400
FOLLOW = 0x801CFDF8
PENDING = 0x80031F00
RETURN = 0x80000100
M = 0x1FFFFF


def u16(cpu, address):
    return struct.unpack_from('<H', cpu.mem, address & M)[0]


def s16(cpu, address):
    return struct.unpack_from('<h', cpu.mem, address & M)[0]


def card_address(slot):
    return ee.CARDS + slot * 28


class Game:
    """Estado mínimo do duelo + simulação das rotinas do jogo chamadas pelo bloco."""

    def __init__(self, turn=0, ops=frozenset(ee.ENTRY_CODES)):
        self.cpu = cpu = MiniCpu()
        follow = FOLLOW if ops else None
        cpu.load(HOOK, ee.code(HOOK, 722, follow, PENDING, ops))
        self.marks = ee.labels(HOOK, 722, follow, PENDING, ops)
        self.data = self.marks['data']
        cpu.load(ee.TURN, bytes([turn]))
        cpu.load(ee.SCENE, struct.pack('<H', ee.FIELD))
        # tabela de posições: lado*20 + posição → slot (como no jogo)
        for side in (0, 1):
            enemy = side ^ 1
            for k in range(5):
                cpu.load(ee.SLOT_TABLE + side * 20 + 5 + k, bytes([enemy * 15 + 5 + k]))
        for i in range(15):
            cpu.load(ee.HANDLERS + i * 8 + 4, struct.pack('<I', 0x80070000 + i * 0x100))
        self.objects = []
        self.calls = []
        self.stock_frames = {}
        self.rotations = []
        self.sounds = []

    # cartas e regras
    def card(self, slot, cid, *, atk=1000, defense=1000, flags=0x8000, obj=None, kind=0):
        at = card_address(slot)
        obj = obj or 0x80150000 + slot * 0x100
        self.cpu.load(at, struct.pack('<I', obj))
        self.cpu.load(at + 0x0C, struct.pack('<HhhhhH', cid, atk, defense, 0, 0, flags))
        self.cpu.load(obj + 0x30, struct.pack('<hhh', 10 + slot, 20, 30))
        self.stats = getattr(self, 'stats', {})
        self.stats[at] = (atk, defense)
        self.cpu.load(ee.STATS + 4 * (cid - 1), struct.pack('<I', kind << 26))

    def rules(self, cid, bonuses):
        rules_at = 0x400 + cid * 0x40
        self.cpu.load(ee.CONFIG + 2 + 2 * cid, struct.pack('<H', rules_at))
        self.cpu.load(ee.CONFIG + rules_at, bytes([0, 0, 0, len(bonuses)]) + bytes(4) + b''.join(bonuses))

    # rotinas do jogo simuladas
    def _create(self, kind):
        def create(c):
            obj = 0x800EAD88 + 0x20 * len(self.objects)
            c.load(obj, bytes(0x20))
            c.load(obj + 0x14, struct.pack('<I', 0x80100000))
            c.load(obj + 0x1C, bytes([0x80]))
            self.objects.append((kind or c.r[4], obj))
            c.r[2] = obj
        return create

    def _stock(self, kind):
        def handler(c):
            frames = self.stock_frames.get(kind, 0) + 1
            self.stock_frames[kind] = frames
            visible = [slot for slot in range(20, 25) if u16(c, card_address(slot) + 0x16) & 0x8000]
            self.calls.append((kind, u16(c, ee.EFFECT_ID), tuple(visible)))
            if frames == 1 and kind == ee.TERRAIN_KIND:
                obj = 0x800EAE88
                c.load(obj + 0x1A, struct.pack('<h', u16(c, ee.EFFECT_ID) - 0x149 - 1))
                c.load(ee.EFFECT_OBJ, struct.pack('<I', obj))
            if frames == 1 and kind == ee.CRUSH_KIND:
                c.load(ee.REMOVAL_THRESHOLD, struct.pack('<H', 1500))
            if frames >= 3:
                c.load(ee.EFFECT_FLAGS, struct.pack('<H', 0))
                self.stock_frames[kind] = 0
        return handler

    def _calc(self, c):
        at = c.r[4]
        atk, defense = self.stats[at]
        modifier = s16(c, at + 0x12)
        c.r[2] = ((defense + modifier) & 0xFFFF) << 16 | ((atk + modifier) & 0xFFFF)

    def _rotate(self, c):
        self.rotations.append((c.r[4], c.r[5], c.r[6], c.r[7]))

    def _sound(self, c):
        self.sounds.append(c.r[4])

    def calls_map(self):
        calls = {ee.CREATE: self._create(None), ee.CREATE_REQUEST: self._create(5),
                 ee.CALC: self._calc, ee.ROTATE: self._rotate, ee.SE_PLAY: self._sound,
                 ee.RUN_EFFECT: lambda c: setattr(self, 'ran', True)}
        for i in range(15):
            calls[0x80070000 + i * 0x100] = self._stock(i)
        return calls

    def call(self, label, a0=0):
        cpu = self.cpu
        cpu.r[29], cpu.r[31], cpu.r[4], cpu.r[28] = 0x801FFF00, RETURN, a0, ee.GP
        stop = {RETURN, FOLLOW}
        end = cpu.run(self.marks[label], stop=stop, limit=5000, calls=self.calls_map())
        assert cpu.r[29] == 0x801FFF00
        return end

    def frames(self, limit=200):
        """Roda o tratador quadro a quadro até o efeito acabar (flags = 0)."""
        for count in range(limit):
            self.call('handler')
            for _, obj in self.objects:     # objetos terminam depois de 2 quadros
                state = self.cpu.mem[(obj + 0x1E) & M] + 1
                self.cpu.mem[(obj + 0x1E) & M] = state
                if state >= 2:
                    self.cpu.mem[(obj + 0x1D) & M] = 1
                if state >= 4:
                    self.cpu.mem[(obj + 0x1C) & M] = 0
            if not u16(self.cpu, ee.EFFECT_FLAGS):
                return count + 1
        raise AssertionError('efeito não terminou')

    def queue(self):
        return struct.unpack_from('<I', self.cpu.mem, (self.data + ee.D_COUNT) & M)[0]


def bonus(op, kind=0, match=0, attack=0):
    return struct.pack('<BBHHH', op, kind, match, attack, 0)


class EntryEffectsTests(unittest.TestCase):
    def start(self, game):
        self.assertEqual(game.call('run'), RETURN)
        self.assertEqual(u16(game.cpu, ee.EFFECT_FLAGS), 0xC000)
        self.assertEqual(u16(game.cpu, ee.EFFECT_ID), ee.OWN_ID)

    def test_entry_queues_codes_and_follows_previous_jump(self):
        game = Game()
        game.card(7, 500)
        game.rules(500, [bonus(1, 0, 3, 100), bonus(ee.OP_SPELL, 8, 350),
                         bonus(ee.OP_TERRAIN, 1, 4), bonus(7, 1, 0, 300)])
        self.assertEqual(game.call('entry', 7), FOLLOW)
        self.assertEqual(game.cpu.r[4], 7)
        self.assertEqual(game.queue(), 2)
        first = bytes(game.cpu.mem[(game.data + ee.D_QUEUE) & M:(game.data + ee.D_QUEUE + 8) & M])
        self.assertEqual(first, struct.pack('<BBBBHH', ee.OP_SPELL, 0, 8, 0, 350, 0))

    def test_run_only_starts_in_field_with_queue(self):
        game = Game()
        game.call('run')
        self.assertEqual(u16(game.cpu, ee.EFFECT_FLAGS), 0)
        game.card(7, 500); game.rules(500, [bonus(ee.OP_TOGGLE)]); game.call('entry', 7)
        game.cpu.load(ee.SCENE, struct.pack('<H', 8))
        game.call('run')
        self.assertEqual(u16(game.cpu, ee.EFFECT_FLAGS), 0)
        game.cpu.load(ee.SCENE, struct.pack('<H', ee.FIELD))
        self.start(game)
        game.cpu.load(ee.SCENE, struct.pack('<H', ee.STARTUP))
        game.cpu.load(ee.EFFECT_FLAGS, struct.pack('<H', 0))
        game.call('run')
        self.assertEqual(game.queue(), 0)

    def test_reveal_then_swords_for_two_turns(self):
        game = Game(turn=0)
        game.card(7, 500)
        game.rules(500, [bonus(ee.OP_SPELL, 8, 350), bonus(ee.OP_SPELL, 10, 348, 2)])
        game.call('entry', 7)
        self.start(game)
        game.frames()
        self.assertEqual([call[:2] for call in game.calls],
                         [(8, 350)] * 3 + [(10, 348)] * 3)
        self.assertEqual(game.cpu.mem[(ee.SIDES + 32 + 0x19) & M], 3)   # 2 turnos do oponente
        self.assertEqual(u16(game.cpu, ee.EFFECT_ID), ee.OWN_ID)

    def test_terrain_normal_uses_id_329_and_fixes_variant(self):
        game = Game()
        game.card(7, 500)
        game.rules(500, [bonus(ee.OP_TERRAIN, 1, 0)])
        game.call('entry', 7)
        self.start(game)
        game.frames()
        self.assertEqual(game.calls[0][:2], (1, 329))
        self.assertEqual(s16(game.cpu, 0x800EAE88 + 0x1A), 0)

    def test_damage_shows_number_on_strongest(self):
        game = Game(turn=0)
        game.card(7, 500)
        game.card(21, 11, atk=1200, defense=900)
        game.card(22, 12, atk=1800, defense=1500)
        game.rules(500, [bonus(ee.OP_DAMAGE, 0, 0xFFFF, 600)])
        game.call('entry', 7)
        self.start(game)
        game.frames()
        self.assertEqual(s16(game.cpu, card_address(22) + 0x12), -600)
        self.assertEqual(s16(game.cpu, card_address(21) + 0x12), 0)
        kind, obj = game.objects[0]
        self.assertEqual(kind, 0x0D)
        self.assertEqual(s16(game.cpu, obj + 0x12), -600)
        self.assertEqual(s16(game.cpu, obj + 0x1A), 2)
        self.assertEqual(struct.unpack_from('<hhh', game.cpu.mem, obj & M), (32, 20, 30))
        self.assertEqual(struct.unpack_from('<I', game.cpu.mem, (obj + 0x14) & M)[0],
                         0x80100000 + (2 << 14))   # posição 2 do oponente
        self.assertIn(0x21, game.sounds)
        self.assertEqual(game.calls, [])

    def test_damage_filters_by_type(self):
        game = Game(turn=0)
        game.card(7, 500)
        game.card(21, 11, atk=1200, defense=900, kind=7)
        game.card(22, 12, atk=1800, defense=1500, kind=1)
        game.rules(500, [bonus(ee.OP_DAMAGE, 0, 7, 600)])
        game.call('entry', 7)
        self.start(game)
        game.frames()
        self.assertEqual(s16(game.cpu, card_address(21) + 0x12), -600)
        self.assertEqual(s16(game.cpu, card_address(22) + 0x12), 0)

    def test_fatal_damage_becomes_crush_on_target_only(self):
        game = Game(turn=0)
        game.card(7, 500)
        game.card(21, 11, atk=1200, defense=900)
        game.card(23, 12, atk=1800, defense=700)
        game.rules(500, [bonus(ee.OP_DAMAGE, 0, 0xFFFF, 800)])
        game.call('entry', 7)
        self.start(game)
        game.frames()
        self.assertTrue(game.calls)
        for kind, effect_id, visible in game.calls:
            self.assertEqual((kind, effect_id, visible), (5, 661, (23,)))
        self.assertEqual(u16(game.cpu, ee.REMOVAL_THRESHOLD), 0)
        for slot in (21, 23):   # quem foi escondido volta
            self.assertTrue(u16(game.cpu, card_address(slot) + 0x16) & 0x8000)
        self.assertEqual(s16(game.cpu, card_address(23) + 0x12), 0)

    def test_toggle_turns_attack_and_defense(self):
        game = Game(turn=1)
        game.card(22, 500)
        game.card(5, 11, flags=0x8000)
        game.card(8, 12, flags=0x8800)
        game.rules(500, [bonus(ee.OP_TOGGLE)])
        game.call('entry', 22)
        self.start(game)
        game.frames()
        self.assertEqual(u16(game.cpu, card_address(5) + 0x16), 0x8800)
        self.assertEqual(u16(game.cpu, card_address(8) + 0x16), 0x8000)
        self.assertEqual(game.rotations, [(0x80150500, 0, 0xC0, 6), (0x80150800, 0xC0, 0, 6)])
        self.assertEqual(game.sounds, [0x20])

    def test_lifelink_only_block(self):
        game = Game(ops=frozenset())
        game.cpu.load(ee.HEAL_NUMBERS, struct.pack('<i', 500))
        game.cpu.load(PENDING, struct.pack('<I', 1800))
        self.start(game)
        game.frames()
        self.assertEqual(struct.unpack_from('<i', game.cpu.mem, ee.HEAL_NUMBERS & M)[0], 500)
        self.assertEqual(game.objects[0][0], 5)
        self.assertEqual(struct.unpack_from('<I', game.cpu.mem, PENDING & M)[0], 0)
        game.call('run')                       # nada mais pendente: não liga de novo
        self.assertEqual(u16(game.cpu, ee.EFFECT_FLAGS), 0)

    def test_lifelink_heal_animation_swaps_bank_number(self):
        game = Game()
        game.cpu.load(ee.HEAL_NUMBERS, struct.pack('<i', 500))
        game.cpu.load(PENDING + 4, struct.pack('<I', 2550))
        self.start(game)
        seen = []
        original = game._create(5)

        def spy(c):
            seen.append(struct.unpack_from('<i', c.mem, ee.HEAL_NUMBERS & M)[0])
            original(c)
        game.calls_map = (lambda base=game.calls_map: lambda: {**base(), ee.CREATE_REQUEST: spy})()
        game.frames()
        self.assertEqual(seen, [2550])
        self.assertEqual(struct.unpack_from('<i', game.cpu.mem, ee.HEAL_NUMBERS & M)[0], 500)
        self.assertEqual(struct.unpack_from('<I', game.cpu.mem, (PENDING + 4) & M)[0], 0)
        self.assertIn(0x14, game.sounds)

    def test_apply_and_views(self):
        from fmstudio.deep_extract import exe_pos
        exe = bytearray(0x1D0800)
        exe[:8] = b'PS-X EXE'
        struct.pack_into('<II', exe, 0x18, 0x80010000, 0x1D0000)

        def put(address, word):
            struct.pack_into('<I', exe, exe_pos(address, bytes(exe), 4), word)
        put(ee.RUN_SITE, ee._jal(ee.RUN_EFFECT))
        put(ee.OWN_SLOT, ee.EMPTY_HANDLER)
        put(ee.ENTRY_SITE, ee._j(FOLLOW))
        original = bytes(exe)
        ops = frozenset(ee.ENTRY_CODES)
        out, report = ee.apply(original, HOOK, 722, ops=ops, heal_pending=PENDING)
        self.assertEqual(report['status'], 'aplicado')
        self.assertTrue(ee.installed(out, 722, ops=ops, heal_pending=PENDING))
        self.assertEqual(ee.runtime_view(out)[:HOOK - 0x80010000 + 0x800],
                         original[:HOOK - 0x80010000 + 0x800])
        # só o Vínculo com Vida: bloco pequeno, sem desvio na entrada em campo
        small, report = ee.apply(original, HOOK, 722, ops=frozenset(), heal_pending=PENDING)
        self.assertLess(report['bytes'], 600)
        self.assertEqual(ee._word(small, ee.ENTRY_SITE), ee._j(FOLLOW))
        self.assertTrue(ee.installed(small, 722, ops=frozenset(), heal_pending=PENDING))
        self.assertEqual(ee.runtime_view(out)[:HOOK - 0x80010000 + 0x800],
                         original[:HOOK - 0x80010000 + 0x800])


if __name__ == '__main__':
    unittest.main()
