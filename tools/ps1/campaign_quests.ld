OUTPUT_ARCH(mips)
ENTRY(QuestBeforeDuel)
/* Drop x15 keeps resident code at 0x801AAC40..0x801AAEE0 and uses
   0x801AAC00..0x801AAC3F as a register save area (drop draw, result rewards
   and the card-name text command jump there). The quest scene load covers
   0x801A9000..0x801AC000, so the overlay must leave that range to the mod:
   code and the fixed table header go below it, zero-initialised state above. */
DROP15_SCRATCH = 0x801AAC00;
DROP15_END = 0x801AAEE0;
SECTIONS
{
    /* 16-byte header precedes the code on disc. */
    . = 0x801A9010;
    .quest : {
        *(.text .text.*)
        *(.rodata .rodata.*)
        *(.data .data.* .sdata .sdata.*)
        . = ALIGN(4);
        QuestConfiguration = .;
    }
    /* Table header: magic, 39 offsets, 95 glyphs, 722 rarities (900 bytes). */
    ASSERT(QuestConfiguration + 900 <= DROP15_SCRATCH, "Quest table header overlaps Drop x15 code")
    .quest_bss DROP15_END (NOLOAD) : {
        *(.bss .bss.* .sbss .sbss.* COMMON)
        . = ALIGN(4);
        QuestBssEnd = .;
    }
    ASSERT(QuestBssEnd <= 0x801ABFFC, "Quest state exceeds the scene arena")
    .quest_before : { *(.quest_before) }
    .quest_answer : { *(.quest_answer) }
    .quest_shop : { *(.quest_shop) }
    /DISCARD/ : { *(.comment .note.* .MIPS.abiflags .reginfo .pdr .mdebug.* .eh_frame* .got) }
}
