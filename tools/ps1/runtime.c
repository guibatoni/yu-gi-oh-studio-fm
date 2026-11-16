/* Studio FM: native rules for the verified NTSC-U Drop x15 executable. */
typedef unsigned char u8;
typedef signed char s8;
typedef unsigned short u16;
typedef signed short s16;
typedef unsigned int u32;

enum {
    OCCUPIED = 0x8000, USED = 0x4000, FACE_DOWN = 0x1000, DEFENSE = 0x800,
    MAGIC = 1, TRAP = 2, INDESTRUCTIBLE = 4, PIERCING = 8, DIRECT = 16, FIRST_TURN = 32,
    FIELD = 5, PLACING = 7, BATTLE = 9,
    CARD_COUNT = 722, DECK_SIZE = 40, RECORD_COUNT = 30,
    AURA = 1, FIELD_TYPE, DECK_TYPE, FIELD_ID, DECK_ID, GRAVE_TYPE
};

typedef struct {
    void *object;
    void *data;
    u32 screen_position;
    s16 id, attack, defense, modifier, terrain;
    u16 flags;
    u32 index;
} Card;
_Static_assert(sizeof(Card) == 28, "field record stride");
_Static_assert(__builtin_offsetof(Card, flags) == 22, "field flags offset");

typedef struct {
    u8 action, scope;
    u16 match, attack, defense;
} Bonus;
typedef struct {
    u8 protection, attacks, copies, bonus_count;
    u16 equip_attack, attack_cost;
    Bonus bonuses[];
} Rules;
typedef struct {
    u8 default_copies, pad;
    u16 offsets[CARD_COUNT + 1];
} Config;
_Static_assert(sizeof(Bonus) == 8 && sizeof(Rules) == 8, "rule pack format");

typedef struct {
    u16 id, equip_attack;
    u8 equip_protection, attacks;
} Instance;

typedef struct {
    Instance field[RECORD_COUNT];
    u16 deck[2][DECK_SIZE];
    u16 graveyard[2][32];
    Instance pending_equip;
    u32 hidden_by_effect;
    s8 battle[2];
    u8 battle_active, lost, deck_ready;
} DuelState;

static DuelState duel;

#define AT(type, addr) (*(volatile type *)(addr))
/* The resident SLUS callbacks share the retail small-data base at 0x8009AF08. */
register u8 *game_gp __asm__("$28");
#define GAME(type, addr) (*(volatile type *)(game_gp + ((addr) - 0x8009AF08)))
#define FN(ret, addr, ...) ((ret (*)(__VA_ARGS__))(addr))
#define ENTRY __attribute__((used, noinline, section(".text.entry")))
#define CARDS ((Card *)0x801A7AD8)
#define CONFIG ((const Config *)0x801CD7A0)
#define STATS ((const u32 *)0x801D4244)
#define OBJECTS ((const u8 *volatile *)0x800E9EF0)
#define SCENE GAME(u16, 0x8009B23A)
#define STEP GAME(u8, 0x8009B174)
#define TURN GAME(u8, 0x8009B1D5)
#define DESTINATION GAME(u8, 0x8009B19C)
#define EFFECT_ID GAME(s16, 0x8009B1D2)
#define EFFECT_FLAGS GAME(u16, 0x8009B220)
#define BATTLE_TRAP GAME(u16, 0x8009B22A)
#define BATTLE_TARGET GAME(s8, 0x8009B1B9)
#define SIDE(side) (0x800E9FF0u + (side) * 32u)

static unsigned type_of(int id)
{
    return (unsigned)(id - 1) < CARD_COUNT ? (STATS[id - 1] >> 26) & 31 : 32;
}

static const Rules *rules(int id)
{
    if ((unsigned)(id - 1) >= CARD_COUNT || !CONFIG->offsets[id]) return 0;
    return (const Rules *)((const u8 *)CONFIG + CONFIG->offsets[id]);
}

static unsigned phase(void) { return SCENE & 15; }
static int monster_zone(unsigned slot)
{
    return (slot >= 5 && slot < 10) || (slot >= 20 && slot < 25);
}
static unsigned owner(unsigned slot) { return slot >= 15; }

static int field_slot(const Card *card)
{
    u32 offset = (u32)card - (u32)CARDS;
    return offset < RECORD_COUNT * sizeof(Card) && offset % sizeof(Card) == 0
        ? offset / sizeof(Card) : -1;
}

static int object_slot(const u8 *object) { return object ? object[0x6A] : -1; }

static int face_up(unsigned slot)
{
    unsigned type = type_of(CARDS[slot].id);
    if (type >= 20 && type != 24) return 0;
    if (phase() == BATTLE && duel.battle_active && !BATTLE_TRAP) {
        for (int i = 0; i < 2; i++)
            if (duel.battle[i] == (int)slot && !(duel.lost & (1 << i))) return 1;
    }
    return ((CARDS[slot].flags & OCCUPIED) || (duel.hidden_by_effect & (1u << slot))) &&
           !(CARDS[slot].flags & FACE_DOWN);
}

static unsigned protection(unsigned slot)
{
    const Rules *rule;
    unsigned flags;
    if (!monster_zone(slot) || !face_up(slot)) return 0;
    rule = rules(CARDS[slot].id);
    flags = rule ? rule->protection : 0;
    if (duel.field[slot].id == CARDS[slot].id) flags |= duel.field[slot].equip_protection;
    return flags;
}

static int count_bonus(const Bonus *bonus, unsigned source_side)
{
    int count = 0;
    unsigned by_id = bonus->action == FIELD_ID || bonus->action == DECK_ID;
    for (unsigned side = 0; side < 2; side++) {
        if (bonus->scope < 2 && side != (source_side ^ bonus->scope)) continue;
        if (bonus->action == GRAVE_TYPE) {
            if (bonus->match < 32) count += duel.graveyard[side][bonus->match];
            else for (int i = 0; i < 32; i++) count += duel.graveyard[side][i];
        } else if (bonus->action == DECK_TYPE || bonus->action == DECK_ID) {
            for (int i = 0; i < DECK_SIZE; i++) {
                unsigned id = duel.deck[side][i];
                if (id && (bonus->match == 0xFFFF ||
                           (by_id ? id : type_of(id)) == bonus->match)) count++;
            }
        } else {
            for (unsigned i = side * 15 + 5; i < side * 15 + 10; i++) {
                if (face_up(i) && (bonus->match == 0xFFFF ||
                    (by_id ? (unsigned)CARDS[i].id : type_of(CARDS[i].id)) == bonus->match)) count++;
            }
        }
    }
    return count;
}

static unsigned cap_stat(int value) { return value < 0 ? 0 : value > 9999 ? 9999 : value; }

ENTRY u32 CalculateStats(const Card *card)
{
    int slot = field_slot(card);
    int attack = card->attack + card->modifier + card->terrain;
    int defense = card->defense + card->modifier + card->terrain;
    if (monster_zone(slot) && face_up(slot)) {
        unsigned side = owner(slot);
        unsigned target_type = type_of(card->id);
        if (duel.field[slot].id == card->id) attack += duel.field[slot].equip_attack;
        for (unsigned i = 5; i < 25; i = i == 9 ? 20 : i + 1) {
            if (!face_up(i)) continue;
            const Rules *rule = rules(CARDS[i].id);
            if (!rule) continue;
            for (unsigned j = 0; j < rule->bonus_count; j++) {
                const Bonus *bonus = &rule->bonuses[j];
                int count;
                if (bonus->action == AURA) {
                    if ((bonus->scope < 2 && side != (owner(i) ^ bonus->scope)) ||
                        (bonus->match != 0xFFFF && bonus->match != target_type)) continue;
                    count = 1;
                } else if ((int)i == slot) {
                    count = count_bonus(bonus, side);
                } else continue;
                attack += count * bonus->attack;
                defense += count * bonus->defense;
            }
        }
    }
    return cap_stat(defense) << 16 | cap_stat(attack);
}

ENTRY void ResetCards(void)
{
    /* The resident reset runs at new duel setup. The 3D battle resume keeps it. */
    for (unsigned i = 0; i < RECORD_COUNT; i++) {
        CARDS[i].object = CARDS[i].data = 0;
        CARDS[i].flags = 0;
    }
    volatile u8 *memory = (volatile u8 *)&duel;
    for (unsigned i = 0; i < sizeof(duel); i++) memory[i] = 0;
}

ENTRY void Startup(void)
{
    FN(void, 0x80018608, void)();
    if (phase() != 1 && !duel.deck_ready) {
        const s16 *record = (const s16 *)0x801A7E20;
        for (int side = 0; side < 2; side++)
            for (int i = 0; i < DECK_SIZE; i++, record += 3)
                duel.deck[side][i] = *record;
        duel.deck_ready = 1;
    }
}

ENTRY void DrawPhase(void)
{
    if (!(SCENE & 0x8000))
        for (int i = 0; i < RECORD_COUNT; i++) duel.field[i].attacks = 0;
    FN(void, 0x8001898C, void)();
}

static void cemetery(unsigned side, int id)
{
    unsigned type = type_of(id);
    if (type < 32 && duel.graveyard[side][type] != 0xFFFF) duel.graveyard[side][type]++;
}

static void end_instance(unsigned slot)
{
    cemetery(owner(slot), CARDS[slot].id);
    duel.field[slot] = (Instance){0};
}

ENTRY void RemoveCard(Card *card)
{
    int slot = field_slot(card);
    if (slot >= 0 && (card->flags & OCCUPIED) && phase() != PLACING) end_instance(slot);
    FN(void, 0x80024914, Card *)(card);
    card->flags = 0;
}

ENTRY unsigned AttackTrap(const u8 *attacker)
{
    unsigned flags = protection(object_slot(attacker));
    if (flags & (TRAP | INDESTRUCTIBLE)) return 0;
    return FN(unsigned, 0x8001F0D0, const u8 *)(attacker);
}

static void finish_battle(void)
{
    int slot = duel.battle[0];
    if (monster_zone(slot) && (CARDS[slot].flags & OCCUPIED)) {
        const Rules *rule = rules(CARDS[slot].id);
        if (rule && rule->attacks > duel.field[slot].attacks) {
            CARDS[slot].flags &= ~USED;
            FN(void, 0x80018080, void *)(CARDS[slot].object);
        }
    }
    duel.battle_active = 0;
}

static void lose_lp(unsigned side, unsigned amount)
{
    u16 lp = AT(u16, SIDE(side) + 0x14);
    AT(u16, SIDE(side) + 0x14) = lp > amount ? lp - amount : 0;
}

ENTRY void Battle(void)
{
    unsigned before = STEP & 15;
    if (!(SCENE & 0x8000)) {
        int slot = object_slot(OBJECTS[0]);
        duel.battle_active = 1;
        duel.battle[0] = slot;
        duel.battle[1] = object_slot(OBJECTS[1]);
        duel.lost = 0;
        if (monster_zone(slot)) {
            Instance *card = &duel.field[slot];
            if (card->id != CARDS[slot].id) *card = (Instance){.id = CARDS[slot].id};
            if (card->attacks < 255) card->attacks++;
            const Rules *rule = rules(card->id);
            if (rule && rule->attack_cost) lose_lp(TURN, rule->attack_cost);
        }
    }
    FN(void, 0x8001F55C, void)();
    if (!duel.battle_active) return;
    if (phase() == FIELD) {
        finish_battle();
        return;
    }
    if (before == 3 && (STEP & 15) == 4 && !BATTLE_TRAP &&
        duel.battle[1] >= 0 && (GAME(u16, 0x8009B17A) & DEFENSE) &&
        GAME(s8, 0x8009B1B1) < 0 && (protection(duel.battle[0]) & PIERCING)) {
        int edge = FN(int, 0x8001EFD4, const u8 *, const u8 *)(OBJECTS[0], OBJECTS[1]);
        if (edge > 0) {
            lose_lp(TURN ^ 1, edge);
            GAME(s16, 0x8009B1A6) = edge;
        }
    }
    if (before != 10 && (STEP & 15) == 10) {
        unsigned target = BATTLE_TARGET;
        if (target < 2 && (!BATTLE_TRAP || target == 0)) {
            int slot = duel.battle[target];
            if (monster_zone(slot) && !(duel.lost & (1 << target))) {
                if (protection(slot) & INDESTRUCTIBLE) STEP = 6;
                else {
                    duel.lost |= 1 << target;
                    end_instance(slot);
                }
            }
        }
    }
    /* 3D battles pass the two removal slots forward to the resume phase. */
    if (before == 5 && GAME(u8, 0x8009B369) == 1) {
        for (unsigned i = 0; i < 2; i++) {
            int slot = GAME(s8, 0x8009B208 + i);
            if (protection(slot) & INDESTRUCTIBLE) GAME(s8, 0x8009B208 + i) = -1;
        }
    }
}

ENTRY void Resume(void)
{
    FN(void, 0x8001825C, void)();
    if (duel.battle_active && phase() == FIELD) finish_battle();
}

static unsigned effect_protection(void) { return type_of(EFFECT_ID) == 21 ? TRAP : MAGIC; }

ENTRY void SpellUsed(int id, int stage)
{
    cemetery(TURN, id);
    FN(void, 0x80026BA4, int, int)(id, stage);
}

extern void CollectOriginal(void **output, int selector);

ENTRY void CollectTargets(void **output, int selector)
{
    CollectOriginal(output, selector);
    if (!(EFFECT_FLAGS & 0x8000)) return;
    unsigned guard = effect_protection() | INDESTRUCTIBLE;
    unsigned count = 0;
    for (unsigned i = 0; i < 20 && output[i]; i++) {
        if (!(protection(object_slot(output[i])) & guard)) output[count++] = output[i];
    }
    output[count] = 0;
}

static void set_occupied(u32 mask, unsigned bit)
{
    for (unsigned i = 0; mask; i++, mask >>= 1)
        if (mask & 1) CARDS[i].flags = (CARDS[i].flags & ~OCCUPIED) | bit;
}

static void filter_spell(void (*handler)(void), unsigned destroys)
{
    unsigned guard = effect_protection() | destroys;
    u32 hidden = 0;
    for (unsigned i = 5; i < 25; i = i == 9 ? 20 : i + 1)
        if ((CARDS[i].flags & OCCUPIED) && (protection(i) & guard)) hidden |= 1u << i;
    duel.hidden_by_effect = hidden;
    set_occupied(hidden, 0);
    handler();
    set_occupied(hidden, OCCUPIED);
    duel.hidden_by_effect = 0;
}

#define FILTER(name, address, destruction) \
    ENTRY void name(void) { filter_spell(FN(void, address, void), destruction); }
FILTER(BoardDestruction, 0x800257A0, INDESTRUCTIBLE)
FILTER(MonsterRemoval, 0x8002538C, INDESTRUCTIBLE)
FILTER(StopDefense, 0x800255FC, 0)
FILTER(Raigeki, 0x8002596C, INDESTRUCTIBLE)
FILTER(Reveal, 0x80025BEC, 0)
FILTER(StatPenalty, 0x80025D30, 0)
FILTER(Swords, 0x80025F3C, 0)

ENTRY void FieldActions(void)
{
    unsigned side = TURN;
    const s8 *cursor = (const s8 *)(0x800E9F48u + side * 0x70u);
    volatile s8 *swords = (volatile s8 *)(SIDE(side) + 0x19);
    unsigned flags = (cursor[0x10] == 2 && (unsigned)cursor[0xF] < 5)
        ? protection(5 + side * 15 + cursor[0xF]) : 0;
    u16 lock = flags & FIRST_TURN ? GAME(u16, 0x8009B16C) & 0x1000 : 0;
    s8 turns = flags & MAGIC ? *swords : 0;
    u32 hidden = 0;
    unsigned step = STEP & 15;
    if ((flags & DIRECT) && (step == 5 || step == 6)) {
        unsigned i = side ? 5 : 20;
        for (unsigned end = i + 5; i < end; i++)
            if (CARDS[i].flags & OCCUPIED) hidden |= 1u << i;
        set_occupied(hidden, 0);
    }
    if (turns) *swords = 0;
    if (lock) GAME(u16, 0x8009B16C) &= ~lock;
    FN(void, 0x8001D670, void)();
    if (lock && phase() != 10) GAME(u16, 0x8009B16C) |= lock;
    if (turns) *swords = turns;
    set_occupied(hidden, OCCUPIED);
}

static int placed_id(const u8 *object)
{
    unsigned slot = object_slot(object);
    return slot < RECORD_COUNT ? CARDS[slot].id : 0;
}

ENTRY void Placement(void)
{
    unsigned sub = STEP;
    int discarded = 0;
    if (!(SCENE & 0x8000)) {
        duel.pending_equip = (Instance){0};
    } else if (sub == 6) {
        cemetery(TURN, placed_id(OBJECTS[0]));
        cemetery(TURN, placed_id(OBJECTS[1]));
    } else if ((sub & 15) == 7 && (sub & 0x80)) {
        discarded = placed_id(OBJECTS[0]);
    } else if ((sub & 15) == 4 && GAME(u8, 0x8009B210) == 2) {
        int id = GAME(s16, 0x8009B206);
        int result = GAME(u16, 0x8009B150);
        int source = object_slot(OBJECTS[0]);
        if (result & 0x8000) duel.pending_equip = (Instance){0};
        else if (source >= 0 && source < RECORD_COUNT && type_of(id) == 23) {
            const Rules *rule = rules(id);
            if (rule) {
                unsigned total = duel.pending_equip.equip_attack + rule->equip_attack;
                duel.pending_equip.equip_attack = total > 9999 ? 9999 : total;
                duel.pending_equip.equip_protection |= rule->protection;
            }
            cemetery(TURN, id);
        }
    }
    FN(void, 0x80019D18, void)();
    if (discarded && STEP == 3) cemetery(TURN, discarded);
}

ENTRY void ConfirmPlacement(void)
{
    int slot = DESTINATION;
    unsigned sub = STEP;
    int current = object_slot(OBJECTS[0]);
    int did_equip = sub == 5 || (sub & 15) == 6;
    s16 pending = 0;
    if (sub == 5 && ((protection(slot) | duel.pending_equip.equip_protection) & TRAP)) {
        pending = GAME(s16, 0x8009B154);
        GAME(s16, 0x8009B154) = 0;
    }
    FN(void, 0x8001B170, void)();
    if (pending) GAME(s16, 0x8009B154) = pending;
    if (monster_zone(slot) && (CARDS[slot].flags & OCCUPIED)) {
        Instance *state = &duel.field[slot];
        if ((current != slot || state->id != CARDS[slot].id) &&
            (STEP & 0xCF) == 0xC4 && (sub & 0xCF) != 0xC4) {
            *state = (Instance){.id = CARDS[slot].id};
        }
        if (did_equip && phase() == FIELD && state->id == CARDS[slot].id) {
            if (sub == 5) {
                int total = state->equip_attack + duel.pending_equip.equip_attack;
                state->equip_attack = total > 9999 ? 9999 : total;
                state->equip_protection |= duel.pending_equip.equip_protection;
            }
            duel.pending_equip = (Instance){0};
        }
    }
}

ENTRY unsigned DeckAllowsCopies(int id, unsigned copies)
{
    const Rules *rule = rules(id);
    unsigned limit = rule && rule->copies ? rule->copies :
                     (unsigned)(id - 17) < 5 ? 1 : CONFIG->default_copies;
    return copies < limit;
}
