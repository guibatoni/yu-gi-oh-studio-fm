OUTPUT_ARCH(mips)
ENTRY(QuestAfterWin)
SECTIONS
{
    /* 16-byte header precedes the code on disc. */
    . = 0x801DC010;
    .quest : {
        *(.text .text.*)
        *(.rodata .rodata.*)
        *(.data .data.* .sdata .sdata.*)
        *(.bss .bss.* .sbss .sbss.* COMMON)
        . = ALIGN(4);
        QuestConfiguration = .;
    }
    .quest_win : { *(.quest_win) }
    .quest_answer : { *(.quest_answer) }
    /DISCARD/ : { *(.comment .note.* .MIPS.abiflags .reginfo .pdr .mdebug.* .eh_frame* .got) }
}
