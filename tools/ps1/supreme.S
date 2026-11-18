/* Drop x15 Guardian Star extension. The project's ID 16 is packed as 11. */
.set noreorder
.set noat
.section .runtime.supreme, "ax"

.equ SUPREME, 11
.equ SUPREME_BONUS, 700
.equ SUPREME_ICON, 0x49
.equ STOCK_ICON_CODE, 0x17 + SUPREME
.equ ICON_PAGE, 0xA
.equ ICON_U, 160
.equ ICON_V, 192
.equ CLUT_X, 672
.equ CLUT_Y, 255

.globl SupremeMatchup
SupremeMatchup:
    addiu $v1, $zero, SUPREME
    beq $a0, $v1, .Lsupreme_left
    nop
    beq $a1, $v1, .Lsupreme_right
    nop
    /* Replay the start of the original two-cycle comparison. */
    addiu $a0, $a0, -7
    bltz $a0, .Lfirst_cycle
    addiu $v1, $zero, 6
    j 0x8002CB8C
    nop
.Lfirst_cycle:
    j 0x8002CBA0
    nop
.Lsupreme_left:
    addiu $v0, $a1, -1
    sltiu $v0, $v0, 10
    beq $v0, $zero, .Lneutral
    nop
    jr $ra
    addiu $v0, $zero, SUPREME_BONUS
.Lsupreme_right:
    addiu $v0, $a0, -1
    sltiu $v0, $v0, 10
    beq $v0, $zero, .Lneutral
    nop
    jr $ra
    addiu $v0, $zero, -SUPREME_BONUS
.Lneutral:
    jr $ra
    move $v0, $zero

/* The original code for star 11 overlaps a controller button. Translate it
   only when a card's star icon is about to be appended. Names still use 8322. */
.globl SupremeTextIcon
SupremeTextIcon:
    andi $v0, $a2, 0xff
    bne $v0, $zero, .Lno_text_icon
    addiu $t0, $zero, STOCK_ICON_CODE
    bne $a1, $t0, .Lappend
    nop
    addiu $a1, $zero, SUPREME_ICON
.Lappend:
    j 0x80037FF4
    nop
.Lno_text_icon:
    j 0x80037FFC
    nop

.globl SupremeFieldIcon
SupremeFieldIcon:
    lbu $a1, 0x43c($gp)
    addiu $sp, $sp, -24
    addiu $t0, $zero, STOCK_ICON_CODE
    bne $a1, $t0, .Lfield_icon
    nop
    addiu $a1, $zero, SUPREME_ICON
.Lfield_icon:
    j 0x80038078
    nop

.globl SupremeSprite
SupremeSprite:
    lbu $t0, -6($s2)
    lw $s1, 0x34($sp)
    addiu $t1, $zero, SUPREME_ICON
    beq $t0, $t1, .Ldraw_supreme
    nop
    /* v1 is the sprite for the stock renderer; s1 for the God renderer. */
    lw $v1, 0x34($sp)
    j 0x8003608C
    addiu $v0, $zero, 0xB
.Ldraw_supreme:
    sw $t0, 0($s6)
    lui $a0, ((ICON_V << 8) | ICON_U)
    ori $a0, $a0, ICON_PAGE
    sw $a0, 0xC($s1)
    lui $a2, CLUT_Y
    ori $a2, $a2, CLUT_X
    sw $a2, 0x10($s1)
    lw $v0, 0x100($sp)
    lui $a0, 0x0800
    lw $v0, 4($v0)
    lui $a2, 0x0010
    ori $a2, $a2, 0x0010
    or $v0, $v0, $a0
    sw $a2, 8($s1)
    j 0x800362A8
    sw $v0, 0($s1)

/* The battle particle effect accepts phases 0–9 for the original stars.
   Initialize its normal particles once, then set the new tile for drawing. */
.globl SupremeGather
SupremeGather:
    addiu $t0, $zero, 14
    bne $a0, $t0, .Lretail_gather
    addiu $t0, $zero, SUPREME - 1
    bne $a1, $t0, .Lretail_gather
    nop
    addiu $sp, $sp, -24
    sw $a2, 16($sp)
    sw $ra, 20($sp)
    jal 0x801462B0
    move $a1, $zero
    lw $a2, 16($sp)
    lui $v0, ICON_V
    ori $v0, $v0, ICON_U
    sw $v0, 0x8C4($a2)
    lui $v0, ((CLUT_Y << 6) | (CLUT_X >> 4))
    ori $v0, $v0, ICON_PAGE | 0x20
    sw $v0, 0x8C8($a2)
    lw $ra, 20($sp)
    addiu $sp, $sp, 24
    jr $ra
    nop
.Lretail_gather:
    j 0x801462B0
    nop

/* The native animation has already selected the winner's display object.
   Look up its selected star to stop the counter at 700 or the original 500. */
.globl SupremeDisplayBonus
SupremeDisplayBonus:
    lb $t1, 0x2B1($gp)
    lui $t0, 0x800F
    sll $t1, $t1, 2
    addu $t0, $t0, $t1
    lw $t0, -0x6110($t0)
    addiu $t2, $zero, 500
    beq $t0, $zero, .Ldisplay_limit
    nop
    lbu $t1, 0x6A($t0)
    lui $t0, 0x801A
    sll $t3, $t1, 3
    subu $t3, $t3, $t1
    sll $t3, $t3, 2
    addu $t0, $t0, $t3
    lh $t1, 0x7AE4($t0)
    lhu $t3, 0x7AEE($t0)
    sll $t1, $t1, 2
    andi $t3, $t3, 0x200
    lui $t0, 0x801D
    addu $t0, $t0, $t1
    lw $t1, 0x4240($t0)
    nop
    beq $t3, $zero, .Lstar_read
    srl $t0, $t1, 22
    srl $t0, $t1, 18
.Lstar_read:
    andi $t0, $t0, 15
    addiu $t1, $zero, SUPREME
    bne $t0, $t1, .Ldisplay_limit
    nop
    addiu $t2, $zero, SUPREME_BONUS
.Ldisplay_limit:
    lhu $t0, 0x2C8($gp)
    nop
    addiu $t0, $t0, 16
    sltu $t1, $t0, $t2
    bne $t1, $zero, .Ldisplay_store
    nop
    andi $v0, $v1, 0xBF
    sb $v0, 0x26C($gp)
    move $t0, $t2
.Ldisplay_store:
    sh $t0, 0x2C8($gp)
    j 0x8001FF90
    lui $v0, 0x800F
