/* Resident text adapters. The native scene loader fills this part of the
   campaign arena and flushes the instruction cache before entering the VM. */
.set noreorder
.set noat
.macro check_overlay fallback
    lui $t0, 0x801A
    ori $t0, $t0, 0x9000
    lw $t1, 0($t0)
    lw $t2, 0x2FFC($t0)
    lui $t3, 0x3356
    ori $t3, $t3, 0x4F51     /* QOV3 */
    bne $t1, $t3, \fallback
    nop
    bne $t2, $t3, \fallback
    nop
.endm

.section .quest_before,"ax",@progbits
.globl QuestDuelLoader
QuestDuelLoader:
    lui $t0, 0x800A
    lbu $t1, -0x4D94($t0)   /* game mode */
    addiu $t2, $zero, 2
    andi $t1, $t1, 31
    bne $t1, $t2, .Loriginal
    lbu $t1, 0x58($a0)      /* text stream depth */
    nop
    sll $t1, $t1, 2
    addu $t1, $t1, $a0
    lw $t1, 0($t1)
    ori $t2, $zero, 0x801B
    srl $t3, $t1, 16
    bne $t3, $t2, .Loriginal
    nop
    lbu $t1, 0($t1)
    nop
    addiu $t1, $t1, -2      /* Simon and non-campaign IDs go straight to native. */
    sltiu $t1, $t1, 37
    beq $t1, $zero, .Loriginal
    nop
    check_overlay .Loriginal
    j QuestBeforeDuel
    nop
.Loriginal:
    j 0x80038530
    nop

.section .quest_answer,"ax",@progbits
.globl QuestAnswerLoader
QuestAnswerLoader:
    lbu $t0, 0x58($a0)
    lui $t1, 0x801A
    sll $t0, $t0, 2
    addu $t0, $t0, $a0
    lw $t0, 0($t0)
    ori $t2, $t1, 0x9000
    sltu $t3, $t0, $t2
    bne $t3, $zero, .Lordinary
    ori $t2, $t1, 0xC000
    sltu $t3, $t0, $t2
    beq $t3, $zero, .Lordinary
    nop
    check_overlay .Lordinary
    j QuestAnswer
    nop
.Lordinary:
    j 0x80038888
    nop

.section .quest_shop,"ax",@progbits
.globl QuestShopLoader
QuestShopLoader:
    lui $t0, 0x801D
    lbu $t1, 0x070B($t0)     /* PendingQuest.tag in sealed save state. */
    addiu $t2, $zero, 0x4D
    bne $t1, $t2, .Lnative_map
    lui $t0, 0x800A
    lw $t1, -0x4D70($t0)    /* Script cursor after fetching opcode 08. */
    lui $t0, 0x801A
    ori $t2, $t0, 0x82CD    /* Hiding Card Shop. */
    beq $t1, $t2, .Lresume
    ori $t2, $t0, 0x8B1D    /* Hiding Card Shop loaded from a save. */
    beq $t1, $t2, .Lresume
    ori $t2, $t0, 0x8295    /* First Egypt Card Shop. */
    bne $t1, $t2, .Lnative_map
    nop
.Lresume:
    check_overlay .Lnative_map
    j QuestResumeShop
    nop
.Lnative_map:
    j 0x8002EB48
    nop
