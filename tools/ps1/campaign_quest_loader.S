/* Resident dialogue adapters. The event overlay owns the CD staging area
   from the verified victory command until the native dialogue resumes. */
.set noreorder
.set noat
.section .quest_win,"ax",@progbits
.globl QuestWinLoader
QuestWinLoader:
    lui $t0, 0x800A
    lbu $t1, -0x4d94($t0)   /* game mode */
    lbu $t2, -0x4c9e($t0)   /* duel outcome */
    andi $t1, $t1, 31
    bne $t2, $zero, .Loriginal
    addiu $t2, $zero, 2
    bne $t1, $t2, .Loriginal
    lbu $t1, 0x58($a0)      /* text stream depth */
    nop
    sll $t1, $t1, 2
    addu $t1, $t1, $a0
    lw $t1, 0($t1)
    ori $t2, $zero, 0x801b
    srl $t1, $t1, 16
    bne $t1, $t2, .Loriginal
    nop
    addiu $sp, $sp, -40
    sw $ra, 36($sp)
    jal 0x800137E4           /* File_WaitForTransfers */
    sw $a0, 32($sp)

    lui $t0, 0x801E
    addiu $t1, $t0, -0x4000
    sw $zero, 0($t1)
    sw $zero, -4($t0)
    sw $zero, 16($sp)
    sw $zero, 20($sp)
    sw $t1, 24($sp)
    addu $a0, $zero, $zero   /* WA_MRG file index */
    addu $a1, $zero, $zero
.globl QuestSectorImmediate
QuestSectorImmediate:
    ori $a2, $zero, 0        /* WA retail sector written by the Studio */
    jal 0x80014E1C           /* File_RequestAsyncTransfer */
    addiu $a3, $zero, 8
    beq $v0, $zero, .Lrestore_original
    nop
    jal 0x800137E4
    nop

    lui $t0, 0x801E
    lw $t1, -0x4000($t0)
    lw $t2, -4($t0)
    lui $t3, 0x3156
    ori $t3, $t3, 0x4F51     /* QOV1 */
    bne $t1, $t3, .Lrestore_original
    nop
    bne $t2, $t3, .Lrestore_original
    addiu $t0, $zero, 0xA0
    jalr $t0                 /* BIOS FlushCache for newly loaded code */
    addiu $t1, $zero, 0x44
    lw $a0, 32($sp)
    lw $ra, 36($sp)
    j QuestAfterWin
    addiu $sp, $sp, 40
.Lrestore_original:
    lw $a0, 32($sp)
    lw $ra, 36($sp)
    addiu $sp, $sp, 40
.Loriginal:
    j 0x80038AB0
    nop

.section .quest_answer,"ax",@progbits
.globl QuestAnswerLoader
QuestAnswerLoader:
    lbu $t0, 0x58($a0)
    lui $t1, 0x801E
    sll $t0, $t0, 2
    addu $t0, $t0, $a0
    lw $t0, 0($t0)
    addiu $t2, $t1, -0x4000
    sltu $t3, $t0, $t2
    bne $t3, $zero, .Lordinary
    sltu $t3, $t0, $t1
    beq $t3, $zero, .Lordinary
    lw $t0, 0($t2)
    lui $t1, 0x3156
    ori $t1, $t1, 0x4F51
    bne $t0, $t1, .Lordinary
    nop
    j QuestAnswer
    nop
.Lordinary:
    jr $ra
    nop
