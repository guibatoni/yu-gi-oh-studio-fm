/* Resident text adapters. The native scene loader fills this part of the
   campaign arena and flushes the instruction cache before entering the VM. */
.set noreorder
.set noat
.macro check_overlay fallback
    lui $t0, 0x801A
    ori $t0, $t0, 0x9000
    lw $t1, 0($t0)
    lw $t2, 0x2FFC($t0)
    lui $t3, 0x3656
    ori $t3, $t3, 0x4F51     /* QOV6: defer native duel to the retail VM on its next tick. */
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
    /* Enforce the full campaign script window and the F8 0D marker here,
       not only in the overlay. Calling the native handler from an overlay
       fallback would leave a return address inside the reloadable arena. */
    lui $t2, 0x801B
    ori $t2, $t2, 0x1102
    sltu $t3, $t1, $t2
    bne $t3, $zero, .Loriginal
    nop
    lui $t2, 0x801B
    ori $t2, $t2, 0xFB4B
    sltu $t3, $t1, $t2
    beq $t3, $zero, .Loriginal
    nop
    lbu $t3, -2($t1)
    addiu $t2, $zero, 0xF8
    bne $t3, $t2, .Loriginal
    nop
    lbu $t3, -1($t1)
    addiu $t2, $zero, 0x0D
    bne $t3, $t2, .Loriginal
    nop

    lbu $t4, 0($t1)         /* Keep opponent ID across check_overlay. */
    addiu $t1, $t4, -2     /* Simon and non-campaign IDs use native. */
    sltiu $t1, $t1, 37
    beq $t1, $zero, .Loriginal
    nop

    /* The quest is already donated: jump DIRECTLY from this resident
       adapter to the original F8 0D handler. Do not call GAME_DUEL
       from QuestBeforeDuel while its code lives in the scene arena. */
    addiu $t0, $t4, 0x750  /* flag id = QUEST_FLAG_BASE + opponent */
    srl $t1, $t0, 3
    lui $t2, 0x801D
    ori $t2, $t2, 0x0618  /* FLAGS */
    addu $t2, $t2, $t1
    lbu $t2, 0($t2)
    andi $t0, $t0, 7
    addiu $t1, $zero, 0x80
    srlv $t1, $t1, $t0
    and $t2, $t2, $t1
    bne $t2, $zero, .Loriginal
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
    /*
     * QuestAnswer runs from the reloadable scene arena. Call it instead
     * of tail-jumping. After it returns, perform cursor validation and
     * defer the original F8 0D to the next VM tick. Neither the callback
     * nor its adapter may load the next game mode synchronously.
     */
    addiu $sp, $sp, -24
    sw $ra, 20($sp)
    sw $a0, 16($sp)

    /* A stale interrupted handoff can never arm an unrelated F8 12. */
    lui $t0, 0x801D
    lbu $t1, 0x070B($t0)
    addiu $t2, $zero, 0x44
    bne $t1, $t2, .Lanswer_call
    nop
    sb $zero, 0x070B($t0)
.Lanswer_call:
    jal QuestAnswer
    nop

    lw $a0, 16($sp)
    lui $t0, 0x801D
    lbu $t1, 0x070B($t0)
    addiu $t2, $zero, 0x44
    bne $t1, $t2, .Lanswer_return
    nop

    /* Consume marker before validation or scene transition. */
    sb $zero, 0x070B($t0)
    lui $t1, 0x800A
    lbu $t2, -0x4D94($t1)
    andi $t2, $t2, 31
    addiu $t3, $zero, 2
    bne $t2, $t3, .Lanswer_return
    nop

    /* Keep the slot address: the validated original F8 0D opcode must
       be replayed on the NEXT retail VM tick. Native mode changes must not
       occur within the F8 12 choice callback or while quest C is active. */
    lbu $t2, 0x58($a0)
    sll $t2, $t2, 2
    addu $t5, $a0, $t2
    lw $t2, 0($t5)
    srl $t3, $t2, 16
    ori $t4, $zero, 0x801B
    bne $t3, $t4, .Lanswer_return
    nop
    lhu $t3, 0x0708($t0)
    andi $t4, $t2, 0xFFFF
    bne $t3, $t4, .Lanswer_return
    nop
    lbu $t3, 0x070A($t0)
    lbu $t4, 0($t2)
    bne $t3, $t4, .Lanswer_return
    nop

    /* Cursor is on the six retail operands. Rewind by exactly two bytes
       to F8 0D; TEXT_YIELD=1 was set by QuestAnswer. Return through this
       resident adapter, leaving the interpreter to dispatch F8 0D itself
       on the next tick, with the donation flag already committed. */
    addiu $t2, $t2, -2
    sw $t2, 0($t5)
    beq $zero, $zero, .Lanswer_return
    nop
.Lanswer_return:
    lw $ra, 20($sp)
    addiu $sp, $sp, 24
    jr $ra
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
