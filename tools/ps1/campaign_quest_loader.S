/* Resident adapters. The overlay owns the staging area only while a
   pre-duel donation is being displayed in the native story dialogue. */
.set noreorder
.set noat
.section .quest_before,"ax",@progbits
.globl QuestDuelLoader
QuestDuelLoader:
    beq $a0, $zero, .Lload_runtime  /* Shop relay, not a text command. */
    lui $t0, 0x800A
    lbu $t1, -0x4d94($t0)   /* game mode */
    addiu $t2, $zero, 2
    andi $t1, $t1, 31
    bne $t1, $t2, .Loriginal
    lbu $t1, 0x58($a0)      /* text stream depth */
    nop
    sll $t1, $t1, 2
    addu $t1, $t1, $a0
    lw $t1, 0($t1)
    ori $t2, $zero, 0x801b
    srl $t3, $t1, 16
    bne $t3, $t2, .Loriginal
    nop
    lbu $t1, 0($t1)
    nop
    addiu $t1, $t1, -2      /* Simon and non-campaign IDs go straight to native. */
    sltiu $t1, $t1, 37
    beq $t1, $zero, .Loriginal
    nop
.Lload_runtime:
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
    lui $t3, 0x3256
    ori $t3, $t3, 0x4F51     /* QOV2 */
    bne $t1, $t3, .Lrestore_original
    nop
    bne $t2, $t3, .Lrestore_original
    addiu $t0, $zero, 0xA0
    jalr $t0                 /* BIOS FlushCache for newly loaded code */
    addiu $t1, $zero, 0x44
    lw $a0, 32($sp)
    lw $ra, 36($sp)
    addiu $sp, $sp, 40
    beq $a0, $zero, .Lresume_shop
    nop
    j QuestBeforeDuel
    nop
.Lresume_shop:
    j QuestResumeShop
    nop
.Lrestore_original:
    lw $a0, 32($sp)
    lw $ra, 36($sp)
    addiu $sp, $sp, 40
    beq $a0, $zero, .Loriginal_map
    nop
.Loriginal:
    j 0x80038530
    nop
.Loriginal_map:
    j 0x8002EB48
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
    lui $t1, 0x3256
    ori $t1, $t1, 0x4F51
    bne $t0, $t1, .Lordinary
    nop
    j QuestAnswer
    nop
.Lordinary:
    jr $ra
    nop

.section .quest_shop,"ax",@progbits
.globl QuestShopLoader
QuestShopLoader:
    lui $t0, 0x801D
    lbu $t1, 0x070B($t0)           /* PendingQuest.tag in sealed save state. */
    addiu $t2, $zero, 0x4D
    bne $t1, $t2, .Lnative_map
    lui $t0, 0x800A
    lw $t1, -0x4D70($t0)          /* Script cursor after fetching opcode 08. */
    lui $t0, 0x801A
    ori $t2, $t0, 0x82CD          /* Hiding Card Shop. */
    beq $t1, $t2, .Lresume
    ori $t2, $t0, 0x8B1D          /* Hiding Card Shop loaded from a save. */
    beq $t1, $t2, .Lresume
    ori $t2, $t0, 0x8295          /* First Egypt Card Shop. */
    bne $t1, $t2, .Lnative_map
    nop
.Lresume:
.globl QuestShopRelay
QuestShopRelay:
    j 0x80000000                   /* QuestDuelLoader, relocated at export. */
    addu $a0, $zero, $zero
.Lnative_map:
    j 0x8002EB48
    nop
