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
#define SIMON_UNLOCK_FLAG 0x6e1
#define EGYPT_TWO_FLAG 0x47
#define HIDING_FLAG 0x5a
#define TRUNK ((volatile u8 *)0x801d0250)
#define DECK ((volatile u16 *)0x801d0200)
#define STATS ((volatile u32 *)0x801d4244)
#define LEVELS ((volatile u8 *)(*(const u32 *)0x801a9004))
#define FLAGS ((volatile u8 *)0x801d0618)
#define MODE (*(volatile u8 *)0x8009b26c)
#define SCENE (*(volatile u8 *)0x8009b27a)
#define MAP_LOCATION (*(volatile u8 *)0x8009b363)
#define SCRIPT_CURSOR (*(const u8 *volatile *)0x8009b290)
#define SCRIPT_COMMAND (*(volatile u16 *)0x8009b27c)
#define STORY_TEXT_BOX ((u8 *)0x800eb0f8)
#define TEXT_YIELD (*(volatile u32 *)0x8009b350)
#define TEXT_CHOICE_LAYOUT (*(volatile u32 *)0x8009b340)
#define PAD1_PRESSED (*(volatile u16 *)0x8009b398)
#define PAD_CONFIRM 0xc0
#define GAME_DUEL ((void (*)(u8 *))0x80038530)
#define GAME_MAP ((void (*)(void))0x8002eb48)
#define GAME_SHOW_DIALOG ((void (*)(void))0x8002e5ac)
#define TEXT_BUILD_STEP ((void (*)(u8 *))0x800393b0)
#define TEXT_CLOSE_CHOICE ((void (*)(u8 *))0x80038b08)
#define TEXT_REFRESH_FRAME ((void (*)(u8 *))0x800391e4)
#define PENDING_TAG 0x4d

enum { EXACT_CARD, TYPE, ATTRIBUTE, GUARDIAN, RARITY };
enum { REVIEW, DONATE, RETREAT };

struct Criterion {
    u8 kind, quantity;
    u16 target, source_card;
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

/* Four retail-unused flag bytes 0x780..0x79f. The memory card's native
   tertiary seal covers this checkpoint. The descriptor remains in the SLUS. */
struct PendingQuest {
    u16 offset;
    u8 opponent, tag;
};
#define PENDING ((volatile struct PendingQuest *)0x801d0708)

static struct {
    u8 *channel;
    const u8 *resume;
    const volatile u8 *options;
    const volatile u8 *accept;
    const volatile u8 *retreat;
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

static int flag_is_set(unsigned id)
{
    return (FLAGS[id >> 3] & (0x80 >> (id & 7))) != 0;
}

static void set_flag(unsigned id)
{
    FLAGS[id >> 3] |= 0x80 >> (id & 7);
}

static int campaign_challenge(const u8 *entry)
{
    /* F8 0D consumes this six-byte descriptor in the stock dialogue bank. */
    return (unsigned)entry >= 0x801b1102 && (unsigned)entry <= 0x801bfb4a
        && entry[-2] == 0xf8 && entry[-1] == 0x0d && *entry >= 2 && *entry <= 38;
}

static void clear_pending(unsigned opponent)
{
    if (PENDING->tag == PENDING_TAG && PENDING->opponent == opponent)
        PENDING->tag = 0;
}

static const struct Quest *quest_for(u8 opponent)
{
    return (const struct Quest *)((const u8 *)&QuestConfiguration
                                  + QuestConfiguration.offsets[opponent]);
}

/* Keep the caller's register pressure low enough to leave the retail $gp intact. */
static __attribute__((noinline)) int eligible(unsigned card, const struct Criterion *criterion)
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

/* The stream can start at any alignment. The ePSXe dynarec can corrupt
   the emitted commands if the compiler combines byte writes into SWL/SWR. */
static volatile u8 *text(volatile u8 *out, const char *line, unsigned limit)
{
    while (limit-- && *line)
        *out++ = glyph(*(const u8 *)line++);
    return out;
}

static volatile u8 *number(volatile u8 *out, unsigned n)
{
    if (n >= 100)
        *out++ = glyph('0' + n / 100);
    if (n >= 10)
        *out++ = glyph('0' + n / 10 % 10);
    *out++ = glyph('0' + n % 10);
    return out;
}

static volatile u8 *choice_command(volatile u8 *out, unsigned action)
{
    *out++ = 0xf8;
    *out++ = 0x1a;  /* Close the native choice before changing pages. */
    *out++ = 0xf8;
    *out++ = 0x12;
    *out++ = action;
    *out++ = 0xff;
    return out;
}

static void set_target(volatile u8 *field, const volatile u8 *target)
{
    unsigned address = (unsigned)target;
    field[0] = address;
    field[1] = address >> 8;
}

static void start_quest_page(u8 *channel)
{
    /* The story can leave custom dimensions or a pending choice layout.
       The native VM lays out all choices in one frame and cannot accept
       a button to advance a page while that layout is in progress. */
    u16 *width = (u16 *)(channel + 0x3e), *height = (u16 *)(channel + 0x42);
    if (*width != 288 || *height != 48) {
        *width = 288;
        *height = 48;
        TEXT_REFRESH_FRAME(channel);
    }
    channel[0x5a] = 8;
    channel[0x5b] = 12;
    channel[0x61] = 0;
    /* Clear the previous input lock and fast/build/choice/done flags. */
    *(u16 *)(channel + 0x34) &= ~0x3c04;
    TEXT_CHOICE_LAYOUT = 0;
    TEXT_CLOSE_CHOICE(channel);
    channel[0x52] = 1;
    *cursor(channel) = active.dialog;
}

static void show_quest(void)
{
    const struct Quest *quest = active.quest;
    unsigned missing = QuestCountMissing(quest), req;
    volatile u8 *out = active.dialog, *targets;
    out = text(out, "Antes do duelo", 24);
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
    *out++ = 0xf8;
    *out++ = 0x12;
    active.options = out;
    *out++ = 0xfb;
    *out++ = 2;
    out = text(out, missing ? "Rever requisitos" : "Doar e duelar", 24);
    *out++ = 0xfe;
    out = text(out, "Ir ao Card Shop", 24);
    *out++ = 0xfe;
    *out++ = 0xfb;
    *out++ = 0x80;
    targets = out;
    out += 4;
    set_target(targets, out);
    active.accept = out + 4;
    out = choice_command(out, missing ? REVIEW : DONATE);
    set_target(targets + 2, out);
    active.retreat = out + 4;
    choice_command(out, RETREAT);
    start_quest_page(active.channel);
}

void QuestBeforeDuel(u8 *channel)
{
    const u8 *entry = *cursor(channel);
    unsigned id;
    if ((MODE & 31) != 2 || !campaign_challenge(entry)) {
        GAME_DUEL(channel);
        return;
    }
    id = *entry;
    /* Provide a renewable source even on the opening path that skips Simon.
       Only the Free Duel list is unlocked. The campaign win flag is untouched. */
    set_flag(SIMON_UNLOCK_FLAG);
    if (flag_is_set(QUEST_FLAG_BASE + id)) {
        clear_pending(id);
        GAME_DUEL(channel);
        return;
    }
    active.quest = quest_for(id);
    active.channel = channel;
    active.resume = entry;
    active.opponent = id;
    show_quest();
}

static void leave_for_shop(void)
{
    unsigned id = active.opponent;
    active.channel = 0;
    TEXT_YIELD = 1;
    if (id >= 9 && id <= 17) {
        SCENE = 189 + (id - 9);  /* Tournament shops lead to the current round. */
        MODE = 2;
        return;
    }
    PENDING->tag = 0;
    PENDING->offset = (unsigned)active.resume;
    PENDING->opponent = id;
    PENDING->tag = PENDING_TAG;
    if (!flag_is_set(EGYPT_TWO_FLAG))
        MAP_LOCATION = 13;
    else
        MAP_LOCATION = (id >= 31 || flag_is_set(HIDING_FLAG)) ? 15 : 12;
    MODE = 5;
}

void QuestAnswer(u8 *channel)
{
    const u8 *operation;
    if (active.channel != channel || (MODE & 31) != 2)
        return;
    operation = *cursor(channel);
    if (operation == active.options) {
        /* The VM can enter the menu in the same frame as the page advance.
           Consume that confirm so selecting an option takes a second press. */
        PAD1_PRESSED &= ~PAD_CONFIRM;
        TEXT_YIELD = 1;
        return;
    }
    if (operation == active.retreat) {
        leave_for_shop();
        return;
    }
    if (operation != active.accept)
        return;
    if (*operation != DONATE || QuestCountMissing(active.quest)) {
        show_quest();
        return;
    }
    take_claimed_cards();
    set_flag(QUEST_FLAG_BASE + active.opponent);
    *cursor(channel) = active.resume;
    clear_pending(active.opponent);
    active.channel = 0;
    GAME_DUEL(channel);
}

void QuestResumeShop(void)
{
    static const u8 dialog_operand[] = {2, 0};
    const u8 *map_operand = SCRIPT_CURSOR;
    const u8 *entry = (const u8 *)(0x801b0000 | PENDING->offset);
    if ((MODE & 31) != 2 || PENDING->tag != PENDING_TAG
            || !campaign_challenge(entry) || *entry != PENDING->opponent) {
        PENDING->tag = 0;
        GAME_MAP();
        return;
    }
    /* Start a native story box inside the shop scene, then give it the saved
       encounter. Its win/loss scene, terrain and BGM still come from F8 0D. */
    SCRIPT_CURSOR = dialog_operand;
    SCRIPT_COMMAND = 2;
    GAME_SHOW_DIALOG();
    /* The first build step sets the story text pointer and then yields. */
    TEXT_BUILD_STEP(STORY_TEXT_BOX);
    SCRIPT_CURSOR = map_operand - 1;
    *cursor(STORY_TEXT_BOX) = entry;
    QuestBeforeDuel(STORY_TEXT_BOX);
}
