/* Live rank in the verified SLUS-014.11 duel HUD (R3000A). */
typedef unsigned char u8;
typedef signed char s8;
typedef unsigned short u16;
typedef signed short s16;
typedef unsigned int u32;

#define HUD __attribute__((used, section(".runtime.rank_hud")))

typedef struct {
    s16 limit, points;
} RankBand;

/* The prefix of the native GsSPRITE consumed by GsSortFastSprite. */
typedef struct {
    u32 attribute;
    s16 x, y, width, height, tpage;
    u8 u, v;
    s16 cx, cy;
    u32 rgb;
} RankSprite;

_Static_assert(__builtin_offsetof(RankSprite, rgb) == 20, "GsSPRITE RGB offset");

#define PLAYER ((const volatile u8 *)0x800E9FF0)
#define RULES ((const volatile RankBand (*)[5])0x801798A8)
#define OPPONENT (*(const volatile s8 *)0x8009B361)
#define ORDERING_TABLES ((void *const volatile *)0x800E9D90)
#define DRAW_DIGITS ((void (*)(const u8 *, RankSprite *, int, int))0x80016D2C)
#define SORT_SPRITE ((void (*)(RankSprite *, void *, u16))0x800849F0)
#define SCORE_CHANGE ((int (*)(int, int))0x80021558)

static const u8 counter_offsets[10] __attribute__((section(".runtime.rank_hud.data"))) =
    {1, 2, 3, 4, 5, 6, 0x18, 0x14, 8, 9};

/* Indices in the 8x8 Latin font of the original duel texture. */
enum { C = 0xA2, D = 0xA3, E = 0xA4, O = 0xAE, P = 0xAF, S = 0xB2,
       T = 0xB3, W = 0xB6, DASH = 0xBE, ZERO = 0xE0 };

/* Replaces the last call of Duel_DrawLifePointsAndDeckCounts. Its arguments
 * and delay slot are the original two-digit deck count of the player. */
HUD void DrawLiveRank(const u8 *panel, RankSprite *sprite, int remaining, int count)
{
    DRAW_DIGITS(panel, sprite, remaining, count);
    if (OPPONENT < 0) return;

    int score = 50 + ((s8)PLAYER[0] ? (s8)PLAYER[0] : 2);
    for (unsigned rule = 0; rule < 10; rule++) {
        /* The retail lookup scans until a strictly greater threshold.
         * Validate the loaded row's sentinel and keep each read inside it. */
        if (RULES[rule][4].limit != 32767) return;
        int value = PLAYER[counter_offsets[rule]];
        if (rule == 6) value = (s8)value;
        if (rule == 7) value = *(const volatile s16 *)(PLAYER + 0x14);
        score += SCORE_CHANGE(rule, value == 32767 ? 32766 : value);
    }
    if (score < 0) score = 0;
    if (score > 99) score = 99;

    int tens = score / 10;
    int tec = tens < 5;
    int grade = tec ? 4 - tens : tens - 5;
    u8 text[8];
    text[0] = grade == 4 ? S : D - grade;
    text[1] = DASH;
    text[2] = tec ? T : P;
    text[3] = tec ? E : O;
    text[4] = tec ? C : W;
    text[5] = 0;
    text[6] = ZERO + tens;
    text[7] = ZERO + score % 10;

    /* The last number is already queued. Reuse its 8x8 scratch sprite. */
    sprite->attribute = 0x08000000;
    sprite->x = *(const s16 *)(panel + 0x30) - 35;
    sprite->y = *(const s16 *)(panel + 0x32) + 23;
    sprite->tpage = 0x0B;
    sprite->cx = 0x290;
    sprite->cy = 0xFA;
    sprite->rgb = 0x808080;
    void *table = ORDERING_TABLES[panel[0x17]];
    u16 depth = *(const u16 *)(panel + 0x14);
    for (unsigned i = 0; i < sizeof(text); i++, sprite->x += 8) {
        unsigned glyph = text[i];
        if (!glyph) continue;
        sprite->u = 0x80 + (glyph & 15) * 8;
        sprite->v = (glyph >> 4) * 8;
        SORT_SPRITE(sprite, table, depth);
    }
}
