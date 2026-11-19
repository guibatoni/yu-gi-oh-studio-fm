OUTPUT_ARCH(mips)
ENTRY(QuestBeforeDuel)
SECTIONS
{
    /* 16-byte header precedes the code on disc. */
    . = 0x801A9010;
    .quest : {
        *(.text .text.*)
        *(.rodata .rodata.*)
        *(.data .data.* .sdata .sdata.*)
        *(.bss .bss.* .sbss .sbss.* COMMON)
        . = ALIGN(4);
        QuestConfiguration = .;
    }
    .quest_before : { *(.quest_before) }
    .quest_answer : { *(.quest_answer) }
    .quest_shop : { *(.quest_shop) }
    /DISCARD/ : { *(.comment .note.* .MIPS.abiflags .reginfo .pdr .mdebug.* .eh_frame* .got) }
}
