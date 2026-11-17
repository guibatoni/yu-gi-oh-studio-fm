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
    .runtime_mod 0x801CF500 : {
        __runtime_mod_start = .;
        KEEP(*(.runtime.mod))
        . = ALIGN(4);
        __runtime_mod_end = .;
    }
    ASSERT(__runtime_mod_end <= 0x801CF9B0, "PS1 decks and name colors conflict with the password code")
    .runtime_password 0x801CF9B0 : {
        __password_start = .;
        KEEP(*(.runtime.password))
        . = ALIGN(4);
        __password_end = .;
    }
    ASSERT(__password_end <= 0x801CFB00, "PS1 passwords conflict with the extended effects code")
    .runtime_ext 0x801CFB00 : {
        __runtime_ext_start = .;
        KEEP(*(.runtime.extension))
        . = ALIGN(4);
        __runtime_ext_end = .;
    }
    ASSERT(__runtime_ext_end <= 0x801CFF00, "PS1 extension conflicts with the LP bank")
    .runtime_markers 0x801CEB00 : {
        __markers_start = .;
        KEEP(*(.runtime.markers .runtime.markers.data))
        . = ALIGN(4);
        __markers_end = .;
    }
    ASSERT(__markers_end <= 0x801CF180, "PS1 entry markers conflict with the rank HUD")
    .runtime_rank_hud 0x801CF180 : {
        __rank_hud_start = .;
        KEEP(*(.runtime.rank_hud .runtime.rank_hud.data))
        . = ALIGN(4);
        __rank_hud_end = .;
    }
    ASSERT(__rank_hud_end <= 0x801CF500, "PS1 rank HUD conflicts with decks and name colors")
    /DISCARD/ : { *(.MIPS.abiflags .reginfo .pdr .comment .note.* .gnu.attributes .mdebug.*) }
}
