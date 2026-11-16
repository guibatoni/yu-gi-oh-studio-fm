/* Entry hooks and continuations for the Drop x15 executable. */
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


/* a0/a1 hold the unchanged material IDs for the retail fallback.
   Each record is 10 bits per ID, with the result in bits 20-29. */
.globl CheckEditedFusion
CheckEditedFusion:
    addiu $t0, $a0, -1
    sltiu $t0, $t0, 722
    beq $t0, $zero, .Lretail_fusion
    addiu $t0, $a1, -1
    sltiu $t0, $t0, 722
    beq $t0, $zero, .Lretail_fusion
    sltu $t0, $a1, $a0
    addu $t1, $a0, $zero
    beq $t0, $zero, .Lpack_fusion
    addu $t2, $a1, $zero
    addu $t1, $a1, $zero
    addu $t2, $a0, $zero
.Lpack_fusion:
    sll $t2, $t2, 10
    or $t1, $t1, $t2
    lui $t0, 0x801C
    ori $t0, $t0, 0xD7A0
    lhu $t2, 1460($t0)  /* FUSION_CONFIG in ps1_runtime.py */
    lui $t3, 0x000F
    ori $t3, $t3, 0xFFFF
    addu $t0, $t0, $t2
.Lnext_fusion:
    lw $v0, 0($t0)
    addiu $t0, $t0, 4
    beq $v0, $zero, .Lretail_fusion
    and $t2, $v0, $t3
    bne $t2, $t1, .Lnext_fusion
    nop
    jr $ra
    srl $v0, $v0, 20
.Lretail_fusion:
    j 0x80019A60
    nop

.section .runtime.mod,"ax",@progbits
.align 2
.globl RetailCardDrop
RetailCardDrop:
    # The installer copies the two original non-branch entry instructions.
    nop
    nop
    j 0x80021818
    nop
