OUTPUT_ARCH(mips)
ENTRY(CalculateStats)
SECTIONS {
    . = 0x800FE740;
    __runtime_start = .;
    .runtime : {
        KEEP(*(.text.entry))
        *(.text .text.*)
        *(.rodata .rodata.*)
        *(.data .data.*)
        . = ALIGN(4);
    }
    __runtime_end = .;
    ASSERT(__runtime_end <= 0x80100000, "PS1 resident extension exceeds reserved memory")
    .bss 0x801CD5A0 (NOLOAD) : {
        *(.bss .bss.* COMMON)
        . = ALIGN(4);
    }
    ASSERT(. <= 0x801CD7A0, "PS1 duel state exceeds reserved memory")
    /DISCARD/ : { *(.MIPS.abiflags .reginfo .pdr .comment .note.* .gnu.attributes .mdebug.*) }
}
