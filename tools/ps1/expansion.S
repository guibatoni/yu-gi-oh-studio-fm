/* Native 723..740 adapters. All continuations are signature-checked in Python.
   No original ID, ownership byte, model package or card record is replaced. */
.set noreorder
.set noat
.section .runtime.expansion,"ax",@progbits
.align 2

/* v0 -> retail behavior/model ID; preserves argument registers and ra. */
.globl MapNewCard
MapNewCard:
    addiu $t8, $v0, -723
    sltiu $t9, $t8, 18
    beq $t9, $zero, .Lmapped
    sll $t8, $t8, 1
    lui $t9, 0x801D
    addu $t9, $t9, $t8
    lhu $t8, 0x53A0($t9)
    nop
    beq $t8, $zero, .Lmapped
    nop
    addu $v0, $t8, $zero
.Lmapped:
    jr $ra
    nop

.globl ExpandedTransfer
ExpandedTransfer:
    bltz $a3, .Ltransfer
    andi $t8, $a1, 0xFF
    bne $t8, $zero, .Ltransfer
    lw $t9, 20($sp)
    lui $t8, 0x8002
    ori $t8, $t8, 0x45EC
    beq $t8, $t9, .Ltransfer
    sltiu $t8, $a3, 722
    bne $t8, $zero, .Ltransfer
    lui $t8, 0x8002
    ori $t8, $t8, 0x89BC
    bne $t8, $t9, .Lshift
    sltiu $t8, $a3, 5776
    bne $t8, $zero, .Lshift
    lui $t8, 0x801D
    lw $t8, 0x53C4($t8) /* appended art base minus virtual sector 5776 */
    nop
    beq $zero, $zero, .Ltransfer
    addu $a3, $a3, $t8
.Lshift:
    addiu $a3, $a3, 18
.Ltransfer:
    addiu $sp, $sp, -40
    sw $s2, 24($sp)
    j 0x800139A0
    nop

.globl ExpandedModel
ExpandedModel:
    andi $t8, $a0, 0x7F
    sltiu $t8, $t8, 2
    beq $t8, $zero, .Lmodel
    addu $t7, $ra, $zero
    jal MapNewCard
    addiu $v0, $a1, 1
    addu $ra, $t7, $zero
    addiu $a1, $v0, -1
.Lmodel:
    addiu $sp, $sp, -72
    sw $s6, 56($sp)
    j 0x8005650C
    nop

.globl ExpandedEffect
ExpandedEffect:
    addiu $sp, $sp, -24
    sw $ra, 20($sp)
    sw $a0, 16($sp)
    jal MapNewCard
    addu $v0, $a0, $zero
    jal OriginalEffect
    addu $a0, $v0, $zero
    lw $t8, 16($sp)
    lui $t9, 0x801D
    sll $v0, $t8, 2
    addu $t9, $t9, $v0
    lw $v0, 0x4240($t9)
    addiu $t9, $zero, 22
    srl $v0, $v0, 26
    andi $v0, $v0, 31
    bne $v0, $t9, .Leffect
    nop
    sh $t8, 0x2CA($gp) /* rituals must look up their own recipe */
.Leffect:
    lw $ra, 20($sp)
    nop
    jr $ra
    addiu $sp, $sp, 24

.globl OriginalEffect
OriginalEffect:
    addiu $v0, $a0, -301
    sltiu $v0, $v0, 50
    j 0x80026BAC
    nop

/* Per-load continuations do not change the actual card's field ID. */
.globl AttackTrapId
AttackTrapId:
    addu $t7, $ra, $zero
    lhu $v0, 12($a2)
    jal MapNewCard
    nop
    addu $ra, $t7, $zero
    j 0x8001F178
    addu $a1, $v0, $zero

.globl SpellTrapId
SpellTrapId:
    addu $t7, $ra, $zero
    lh $v0, 12($v1)
    jal MapNewCard
    nop
    addu $ra, $t7, $zero
    j 0x8002508C
    nop

.globl FakeTrapId
FakeTrapId:
    addu $t7, $ra, $zero
    lh $v0, 12($a2)
    jal MapNewCard
    nop
    addu $ra, $t7, $zero
    j 0x8001F338
    addu $v1, $v0, $zero

/* Only card-seen call sites use this adapter. Password and campaign flag
   calls keep their original entry. The library itself remains retail-sized. */
.globl ExpandedSeen
ExpandedSeen:
    addiu $v0, $a0, -0x121
    sltiu $v0, $v0, 722
    bne $v0, $zero, .Lseen
    nop
    jr $ra
    nop
.Lseen:
    j 0x8002CCE4
    nop

/* Resolve built-in equip animations and Megamorph's 1000-point branch.
   The four displaced loads otherwise compare only the original IDs. */
.globl EquipBonusId
EquipBonusId:
    addu $t7, $ra, $zero
    lh $v0, 0x2FE($gp)
    jal MapNewCard
    nop
    addu $ra, $t7, $zero
    addu $v1, $v0, $zero
    j 0x8001A81C
    addiu $v0, $zero, 657

.globl EquipAnimationId
EquipAnimationId:
    addu $t7, $ra, $zero
    lhu $v0, 0x2FE($gp)
    jal MapNewCard
    nop
    addu $ra, $t7, $zero
    j 0x8001ABA0
    addu $a0, $v0, $zero

.globl EquipSwordId
EquipSwordId:
    addu $t7, $ra, $zero
    addu $t6, $v0, $zero
    lh $v0, 0x2FE($gp)
    jal MapNewCard
    nop
    addu $ra, $t7, $zero
    addu $v1, $v0, $zero
    j 0x8001ABE0
    addu $v0, $t6, $zero

.globl EquipSecondAnimationId
EquipSecondAnimationId:
    addu $t7, $ra, $zero
    lh $v0, 0x2FE($gp)
    jal MapNewCard
    nop
    addu $ra, $t7, $zero
    addu $v1, $v0, $zero
    j 0x8001ABFC
    addiu $v0, $zero, 657
