/* Only these hooks enter in the middle of a retail routine. */
.set noreorder
.set noat
.section .text.entry, "ax"

.globl DeckCopyGate
DeckCopyGate:
    addiu $sp, $sp, -24
    sw $ra, 20($sp)
    addu $a0, $s0, $zero
    jal DeckAllowsCopies
    addu $a1, $v0, $zero
    lw $ra, 20($sp)
    addiu $sp, $sp, 24
    bne $v0, $zero, .Lallow
    nop
    j 0x800338C8
    nop
.Lallow:
    j 0x8003387C
    nop

/* v1 is the icon ID, s1 is GsSPRITE*, a2 is the original packed CLUT. */
.globl DescriptionIcon
DescriptionIcon:
    addiu $v0, $v1, -0x40
    sltiu $a0, $v0, 9
    beq $a0, $zero, .Loriginal
    addiu $v0, $v0, 1
    sll $a0, $v0, 20
    lui $v0, 0xc000
    or $a0, $a0, $v0
    ori $a0, $a0, 0xA
    sw $a0, 0xC($s1)
    lw $v0, 0x100($sp)
    lui $a0, 0x0800
    lw $v0, 4($v0)
    lui $a2, 0x0010
    ori $a2, $a2, 0x0010
    or $v0, $v0, $a0
    sw $a2, 8($s1)
    sw $v0, 0($s1)

    /* Nine custom icons. CLUTs 0-6 at (656,251), 7-8 at (640,255). */
    addiu $v0, $v1, -0x40
    sltiu $a0, $v0, 7
    beq $a0, $zero, .Lsecond_clut_row
    sll $v0, $v0, 4
    lui $a2, 251
    addiu $v0, $v0, 656
    j 0x800360E8
    or $a2, $a2, $v0
.Lsecond_clut_row:
    lui $a2, 255
    addiu $v0, $v0, 528
    j 0x800360E8
    or $a2, $a2, $v0

.Loriginal:
    addiu $v0, $zero, 0x31
    beq $v1, $v0, .Lgod
    lui $a0, 0xC000
    j 0x800360C4
    nop
.Lgod:
    j 0x800360B4
    nop

.globl CollectOriginal
CollectOriginal:
    addiu $sp, $sp, -40
    sw $s2, 24($sp)
    j 0x8002C9BC
    nop
