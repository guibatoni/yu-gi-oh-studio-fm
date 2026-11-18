/* Drop x15 campaign gates. The text VM owns the active dialogue. */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;

#define CARD_COUNT 722
#define DECK_SIZE 40
#define CRITERIA 4
#define MASKS (1 << CRITERIA)
#define LABEL_WIDTH 22
#define QUEST_FLAG_BASE 0x750
#define TRUNK ((volatile u8 *)0x801d0250)
#define DECK ((volatile u16 *)0x801d0200)
#define STATS ((volatile u32 *)0x801d4244)
#define LEVELS ((volatile u8 *)(*(const u32 *)0x801dc004))
#define FLAGS ((volatile u8 *)0x801d0618)
#define MODE (*(volatile u8 *)0x8009b26c)
#define OPPONENT (*(volatile u8 *)0x8009b361)
#define OUTCOME (*(volatile u8 *)0x8009b362)
#define TEXT_YIELD (*(volatile u8 *)0x8009b350)
#define GAME_UNLOCK ((void (*)(u8 *))0x80038ab0)

enum { EXACT_CARD, TYPE, ATTRIBUTE, GUARDIAN, RARITY };
enum { REVIEW, DONATE, DONATE_WITH_RESERVE };

struct Criterion {
    u8 kind, quantity;
    u16 target, reserve;
    char label[LABEL_WIDTH];
};

struct Quest {
    u8 count, pad;
    struct Criterion criteria[];
};

struct QuestTable {
    u32 magic;
    u16 offsets[39];
    u8 glyphs[95];
    u8 rarities[CARD_COUNT];
};

_Static_assert(sizeof(struct Criterion) == 6 + LABEL_WIDTH, "quest record format");
extern const struct QuestTable QuestConfiguration;

static struct {
    u8 *channel;
    const u8 *resume;
    const u8 *accept;
    const u8 *review;
    const struct Quest *quest;
    u8 opponent;
    u8 dialog[256];
} active;

static struct {
    u8 spare[CARD_COUNT];
    u8 masks[CARD_COUNT];
    u16 unused[MASKS];
    u16 claims[MASKS][CRITERIA];
    u16 progress[CRITERIA];
} inventory;

static const u8 **cursor(u8 *channel)
{
    return &((const u8 **)channel)[channel[0x58]];
}

static const struct Quest *quest_for(u8 opponent)
{
    return (const struct Quest *)((const u8 *)&QuestConfiguration
                                  + QuestConfiguration.offsets[opponent]);
}

static int eligible(unsigned card, const struct Criterion *criterion)
{
    u32 value;
    unsigned target = criterion->target;
    if (card < 1 || card > CARD_COUNT)
        return 0;
    value = STATS[card - 1];
    switch (criterion->kind) {
    case EXACT_CARD: return card == target;
    case TYPE: return (value >> 26 & 31) == target;
    case ATTRIBUTE: return LEVELS[card] >> 4 == target;
    case GUARDIAN:
        if (target == 16)
            target = 11; /* Studio's Supreme occupies native slot 11. */
        return (value >> 22 & 15) == target || (value >> 18 & 15) == target;
    case RARITY: return QuestConfiguration.rarities[card - 1] == target;
    default: return 0;
    }
}

/* One augmenting path assigns a real copy. Requirements with overlapping
   categories can trade claims without double-counting or losing progress. */
static int claim(unsigned requirement, unsigned visited)
{
    unsigned mask, other, bit = 1u << requirement;
    if (visited & bit)
        return 0;
    visited |= bit;
    for (mask = 1; mask < MASKS; ++mask) {
        if ((mask & bit) && inventory.unused[mask]) {
            --inventory.unused[mask];
            ++inventory.claims[mask][requirement];
            return 1;
        }
    }
    for (mask = 1; mask < MASKS; ++mask) {
        if (!(mask & bit))
            continue;
        for (other = 0; other < CRITERIA; ++other) {
            if (inventory.claims[mask][other] && claim(other, visited)) {
                --inventory.claims[mask][other];
                ++inventory.claims[mask][requirement];
                return 1;
            }
        }
    }
    return 0;
}

unsigned QuestCountMissing(const struct Quest *quest)
{
    unsigned card, slot, mask, req, missing = 0;
    for (mask = 0; mask < MASKS; ++mask) {
        inventory.unused[mask] = 0;
        for (req = 0; req < CRITERIA; ++req)
            inventory.claims[mask][req] = 0;
    }
    for (card = 0; card < CARD_COUNT; ++card)
        inventory.spare[card] = TRUNK[card];
    for (slot = 0; slot < DECK_SIZE; ++slot) {
        card = DECK[slot];
        if (card >= 1 && card <= CARD_COUNT && inventory.spare[card - 1])
            --inventory.spare[card - 1];
    }
    for (card = 0; card < CARD_COUNT; ++card) {
        mask = 0;
        if (inventory.spare[card]) {
            for (req = 0; req < quest->count; ++req)
                if (eligible(card + 1, &quest->criteria[req]))
                    mask |= 1u << req;
            if (mask && inventory.unused[mask] < 255 * CRITERIA)
                inventory.unused[mask] += inventory.spare[card];
        }
        inventory.masks[card] = mask;
    }
    for (req = 0; req < quest->count; ++req) {
        unsigned quantity = quest->criteria[req].quantity, assigned = 0;
        while (assigned < quantity && claim(req, 0))
            ++assigned;
        inventory.progress[req] = assigned;
        missing += quantity - assigned;
    }
    return missing;
}

static void take_claimed_cards(void)
{
    unsigned mask, req, card, pending, count;
    for (mask = 1; mask < MASKS; ++mask) {
        pending = 0;
        for (req = 0; req < CRITERIA; ++req)
            pending += inventory.claims[mask][req];
        for (card = 0; pending && card < CARD_COUNT; ++card) {
            if (mask != inventory.masks[card])
                continue;
            count = inventory.spare[card];
            if (count > pending)
                count = pending;
            TRUNK[card] -= count;
            pending -= count;
        }
    }
}

static u8 glyph(unsigned c)
{
    return QuestConfiguration.glyphs[c >= 32 && c <= 126 ? c - 32 : '?' - 32];
}

static u8 *text(u8 *out, const char *line, unsigned limit)
{
    while (limit-- && *line)
        *out++ = glyph(*(const u8 *)line++);
    return out;
}

static u8 *number(u8 *out, unsigned n)
{
    if (n >= 100)
        *out++ = glyph('0' + n / 100);
    if (n >= 10)
        *out++ = glyph('0' + n / 10 % 10);
    *out++ = glyph('0' + n % 10);
    return out;
}

static u8 *choice_command(u8 *out, unsigned action)
{
    *out++ = 0xf8;
    *out++ = 0x1a;  /* Close the native choice before changing pages. */
    *out++ = 0xf8;
    *out++ = 0x12;
    *out++ = action;
    *out++ = 0xff;
    return out;
}

static void set_target(u8 *field, const u8 *target)
{
    unsigned address = (unsigned)target;
    field[0] = address;
    field[1] = address >> 8;
}

static void show_quest(void)
{
    const struct Quest *quest = active.quest;
    unsigned missing = QuestCountMissing(quest), req;
    u8 *out = active.dialog, *targets;
    out = text(out, "Doacao - sobras do bau", 30);
    *out++ = 0xfe;
    for (req = 0; req < quest->count; ++req) {
        const struct Criterion *criterion = &quest->criteria[req];
        out = text(out, criterion->label, LABEL_WIDTH);
        *out++ = glyph(' ');
        out = number(out, inventory.progress[req]);
        *out++ = glyph('/');
        out = number(out, criterion->quantity);
        *out++ = req + 1 == quest->count || req == 1 ? 0xfa : 0xfe;
    }
    *out++ = 0xfb;
    *out++ = 2;
    out = text(out, missing ? "Entregar com reserva" : "Confirmar doacao", 24);
    *out++ = 0xfe;
    out = text(out, "Rever requisitos", 24);
    *out++ = 0xfe;
    *out++ = 0xfb;
    *out++ = 0x80;
    targets = out;
    out += 4;
    set_target(targets, out);
    active.accept = out + 4;
    out = choice_command(out, missing ? DONATE_WITH_RESERVE : DONATE);
    set_target(targets + 2, out);
    active.review = out + 4;
    choice_command(out, REVIEW);
    *cursor(active.channel) = active.dialog;
    active.channel[0x51] = 2;  /* Clear the previous page in the normal VM. */
    TEXT_YIELD = 1;
}

void QuestAfterWin(u8 *channel)
{
    const u8 *entry = *cursor(channel);
    unsigned id = *entry, flag = QUEST_FLAG_BASE + id;
    if ((MODE & 31) != 2 || OUTCOME != 0 || id < 1 || id > 38 || id != OPPONENT
            || ((unsigned)entry >> 16) != 0x801b
            || (FLAGS[flag >> 3] & (0x80 >> (flag & 7)))) {
        GAME_UNLOCK(channel);
        return;
    }
    active.quest = quest_for(id);
    active.channel = channel;
    active.resume = entry;
    active.opponent = id;
    show_quest();
}

void QuestAnswer(u8 *channel)
{
    const u8 *operation;
    unsigned flag, req;
    if (active.channel != channel)
        return;
    operation = *cursor(channel);
    if (operation == active.review) {
        show_quest();
        return;
    }
    if (operation != active.accept || (MODE & 31) != 2 || OPPONENT != active.opponent)
        return;
    if (QuestCountMissing(active.quest) && *operation != DONATE_WITH_RESERVE) {
        show_quest();
        return;
    }
    /* Reserve cards go directly to the offering and never enter the chest. */
    for (req = 0; req < active.quest->count; ++req) {
        const struct Criterion *criterion = &active.quest->criteria[req];
        if (inventory.progress[req] < criterion->quantity &&
                !eligible(criterion->reserve, criterion)) {
            show_quest();
            return;
        }
    }
    take_claimed_cards();
    flag = QUEST_FLAG_BASE + active.opponent;
    FLAGS[flag >> 3] |= 0x80 >> (flag & 7);
    *cursor(channel) = active.resume;
    active.channel = 0;
    GAME_UNLOCK(channel);
}
