"""Montador MIPS I mínimo (R3000) para rotinas pequenas relocáveis do Studio.

Uso: ``Asm(base)`` + métodos por instrução + ``label('x')``; ``bytes()`` resolve
saltos e desvios. Os registradores aceitam nomes ($t0, t0, s1, ra...). Não insere
nada sozinho: delay slots e load delays são responsabilidade de quem escreve.
"""
from __future__ import annotations

import struct

REGS = {name: i for i, name in enumerate(
    'zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 t8 t9 k0 k1 gp sp fp ra'.split())}


def reg(name) -> int:
    if isinstance(name, int):
        return name
    return REGS[str(name).lstrip('$')]


def hi_lo(address: int) -> tuple[int, int]:
    """%hi/%lo com correção de sinal (para lui + addiu/lw/sw)."""
    return ((address + 0x8000) >> 16) & 0xFFFF, address & 0xFFFF


class Asm:
    def __init__(self, base: int):
        self.base = base
        self.items: list = []          # int | ('b', op, rs, rt, label) | ('j', op, target/label)
        self.labels: dict[str, int] = {}

    @property
    def here(self) -> int:
        return self.base + 4 * len(self.items)

    def label(self, name):
        if name in self.labels:
            raise ValueError(f'rótulo repetido: {name}')
        self.labels[name] = self.here

    def word(self, value):
        self.items.append(value & 0xFFFFFFFF)

    # tipo I/R
    def _i(self, op, rs, rt, imm):
        self.word(op << 26 | reg(rs) << 21 | reg(rt) << 16 | (imm & 0xFFFF))

    def _r(self, rs, rt, rd, shamt, funct):
        self.word(reg(rs) << 21 | reg(rt) << 16 | reg(rd) << 11 | shamt << 6 | funct)

    def nop(self): self.word(0)
    def addiu(self, rt, rs, imm): self._i(9, rs, rt, imm)
    def andi(self, rt, rs, imm): self._i(12, rs, rt, imm)
    def ori(self, rt, rs, imm): self._i(13, rs, rt, imm)
    def slti(self, rt, rs, imm): self._i(10, rs, rt, imm)
    def lui(self, rt, imm): self._i(15, 0, rt, imm)
    def lw(self, rt, off, rs): self._i(35, rs, rt, off)
    def lh(self, rt, off, rs): self._i(33, rs, rt, off)
    def lhu(self, rt, off, rs): self._i(37, rs, rt, off)
    def lbu(self, rt, off, rs): self._i(36, rs, rt, off)
    def sw(self, rt, off, rs): self._i(43, rs, rt, off)
    def sh(self, rt, off, rs): self._i(41, rs, rt, off)
    def addu(self, rd, rs, rt): self._r(rs, rt, rd, 0, 0x21)
    def subu(self, rd, rs, rt): self._r(rs, rt, rd, 0, 0x23)
    def slt(self, rd, rs, rt): self._r(rs, rt, rd, 0, 0x2A)
    def sll(self, rd, rt, sa): self._r(0, rt, rd, sa, 0)
    def jr(self, rs): self._r(rs, 0, 0, 0, 8)
    def move(self, rd, rs): self.addu(rd, rs, 'zero')
    def li(self, rt, value):
        if -0x8000 <= value < 0x8000:
            self.addiu(rt, 'zero', value)
        elif 0 <= value <= 0xFFFF:
            self.ori(rt, 'zero', value)
        else:
            raise ValueError('li: use la para valores de 32 bits')
    def la(self, rt, address):
        """Carrega um endereço (número ou rótulo, resolvido no fim) em 2 instruções."""
        if isinstance(address, str):
            self.items.append(('hi', reg(rt), address))
            self.items.append(('lo', reg(rt), address))
            return
        high, low = hi_lo(address)
        self.lui(rt, high)
        self.addiu(rt, rt, low)

    def align(self, size: int):
        while self.here % size:
            self.word(0)

    # desvios (alvo = rótulo) e saltos (alvo = rótulo ou endereço)
    def _branch(self, op, rs, rt, target):
        self.items.append(('b', op, reg(rs), reg(rt), target))
    def beq(self, rs, rt, target): self._branch(4, rs, rt, target)
    def bne(self, rs, rt, target): self._branch(5, rs, rt, target)
    def blez(self, rs, target): self._branch(6, rs, 0, target)
    def bgtz(self, rs, target): self._branch(7, rs, 0, target)
    def bltz(self, rs, target): self._branch(1, rs, 0, target)      # REGIMM rt=0
    def bgez(self, rs, target): self._branch(1, rs, 1, target)      # REGIMM rt=1
    def b(self, target): self.beq('zero', 'zero', target)
    def jal(self, target): self.items.append(('j', 3, target))
    def j(self, target): self.items.append(('j', 2, target))

    def _resolve(self, target) -> int:
        return self.labels[target] if isinstance(target, str) else int(target)

    def words(self) -> list[int]:
        out = []
        for index, item in enumerate(self.items):
            pc = self.base + 4 * index
            if isinstance(item, int):
                out.append(item)
            elif item[0] in ('hi', 'lo'):
                _, rt, target = item
                high, low = hi_lo(self._resolve(target))
                out.append((15 << 26 | rt << 16 | high) if item[0] == 'hi'
                           else (9 << 26 | rt << 21 | rt << 16 | low))
            elif item[0] == 'b':
                _, op, rs, rt, target = item
                offset = (self._resolve(target) - (pc + 4)) >> 2
                if not -0x8000 <= offset < 0x8000:
                    raise ValueError('desvio longe demais')
                out.append(op << 26 | rs << 21 | rt << 16 | (offset & 0xFFFF))
            else:
                _, op, target = item
                address = self._resolve(target)
                if (address & 0xF0000000) != (pc & 0xF0000000):
                    raise ValueError('salto fora do segmento')
                out.append(op << 26 | ((address & 0x0FFFFFFF) >> 2))
        return out

    def bytes(self) -> bytes:
        words = self.words()
        return struct.pack(f'<{len(words)}I', *words)
