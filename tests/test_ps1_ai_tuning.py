"""IA Agressiva/Máxima: parâmetros por oponente (0x800917F0)."""
import unittest

from fmstudio.ps1_ai_tuning import ROW, TABLE, apply, looks_like_table, tuned_row
from fmstudio.tables import EXE_DELTA
from fmstudio.core import ModError

# Linhas reais do Drop x15 (dump de RAM): Simon, Teana, Seto, Pegasus, Duel Master K
REAL = {1: [5, 20, 10, 1, 1, 0, 0, 25, 50], 2: [5, 30, 20, 1, 2, 0, 0, 25, 25],
        7: [10, 20, 10, 3, 3, 2, 2, 50, 50], 15: [16, 20, 10, 3, 3, 3, 3, 75, 0],
        39: [15, 20, 10, 3, 3, 5, 5, 50, 25]}


def exe_with_table():
    data = bytearray(TABLE - EXE_DELTA + ROW * 40 + 16)
    for opp in range(1, 40):
        row = REAL.get(opp, [8, 20, 10, 2, 2, 0, 0, 50, 25])
        data[TABLE - EXE_DELTA + ROW * opp:TABLE - EXE_DELTA + ROW * (opp + 1)] = bytes(row)
    return bytes(data)


class AiTuningTests(unittest.TestCase):
    def test_rows(self):
        simon = tuned_row(bytes(REAL[1]), 'agressiva')
        self.assertEqual(list(simon), [10, 10, 5, 3, 3, 0, 0, 50, 50])
        pegasus = tuned_row(bytes(REAL[15]), 'maxima')
        self.assertEqual(list(pegasus), [20, 10, 5, 3, 3, 3, 3, 75, 75])
        self.assertEqual(tuned_row(bytes(REAL[7]), 'original'), bytes(REAL[7]))

    def test_apply_only_touches_table(self):
        exe = exe_with_table()
        self.assertTrue(looks_like_table(exe))
        out, report = apply(exe, 'maxima')
        self.assertEqual(report['status'], 'aplicado')
        start = TABLE - EXE_DELTA
        self.assertEqual(out[:start + ROW], exe[:start + ROW])          # linha 0 intacta
        self.assertEqual(out[start + ROW * 40:], exe[start + ROW * 40:])
        self.assertTrue(all(out[start + ROW * o] == 20 for o in range(1, 40)))

    def test_unknown_table_refused(self):
        exe = bytearray(exe_with_table())
        exe[TABLE - EXE_DELTA + ROW * 3 + 3] = 9                         # profundidade impossível
        with self.assertRaises(ModError):
            apply(bytes(exe), 'agressiva')


if __name__ == '__main__':
    unittest.main()
