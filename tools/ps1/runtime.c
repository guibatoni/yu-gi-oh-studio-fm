/* Studio FM: native rules for the verified NTSC-U Drop x15 executable. */
typedef unsigned char u8;
typedef signed char s8;
typedef unsigned short u16;
typedef signed short s16;
typedef unsigned int u32;

enum {
    OCCUPIED = 0x8000, USED = 0x4000, FACE_DOWN = 0x1000, DEFENSE = 0x800,
    MAGIC = 1, TRAP = 2, INDESTRUCTIBLE = 4, PIERCING = 8, DIRECT = 16, FIRST_TURN = 32,
    FIELD = 5, PLACING = 7, CONFIRMING = 8, BATTLE = 9,
    CARD_COUNT = 722, DECK_SIZE = 40, RECORD_COUNT = 30, DUELIST_COUNT = 40,
    AURA = 1, FIELD_TYPE, DECK_TYPE, FIELD_ID, DECK_ID, GRAVE_TYPE, SUMMON_DAMAGE, SUMMON_HEAL,
    ENTRY_GROW, ENTRY_SHRINK,
    ATTRIBUTE_MASK = 0x7C, MATCH_EITHER = 0x80
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
    u16 match;
    union {
        struct { u16 attack, defense; };
        u16 grave_count[2];
    };
} Bonus;
typedef struct {
    u8 protection, attacks, copies, bonus_count;
    u16 equip_attack, attack_cost;
    Bonus bonuses[];
} Rules;
typedef struct {
    u8 default_copies, entry_markers;
    u16 offsets[CARD_COUNT + 1];
    u16 password_prefix;
    u8 deck_drops[DUELIST_COUNT / 8];
    u8 reserved;
    u16 fixed_decks, name_colors;
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
static u8 prior_name_color[4], name_depth[4];

#define AT(type, addr) (*(volatile type *)(addr))
/* The resident SLUS callbacks share the retail small-data base at 0x8009AF08. */
register u8 *game_gp __asm__("$28");
#define GAME(type, addr) (*(volatile type *)(game_gp + ((addr) - 0x8009AF08)))
#define FN(ret, addr, ...) ((ret (*)(__VA_ARGS__))(addr))
#define ENTRY __attribute__((used, noinline, section(".text.entry")))
#define EXTENSION __attribute__((noinline, section(".runtime.extension")))
#define MOD_RULE __attribute__((used, noinline, section(".runtime.mod")))
#define MARKER_RULE __attribute__((used, noinline, section(".runtime.markers")))
#define GRAVE_FILTER_CODE __attribute__((noinline, section(".runtime.grave_filters")))
#define CARDS ((Card *)0x801A7AD8)
#define CONFIG ((const Config *)0x801CD7A0)
/* Offset zero of the card directory is unused by card IDs. */
#define GRAVE_FILTERS ((Bonus *)((u8 *)CONFIG + CONFIG->offsets[0]))
#define STATS ((const u32 *)0x801D4244)
#define LEVELS ((const u8 *)0x801D5332)
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

typedef struct { int attack, defense; } Marker;
static struct {
    Marker slots[10];
    u32 fusion_slots;
    u16 pending_slot, pending_id;
} markers __attribute__((section(".runtime.markers.data")));

static inline __attribute__((always_inline)) unsigned type_in_catalog(unsigned id)
{
    return (STATS[id - 1] >> 26) & 31;
}

static unsigned type_of(int id)
{
    return (unsigned)(id - 1) < CARD_COUNT ? type_in_catalog(id) : 32;
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

static EXTENSION int object_slot(const u8 *object) { return object ? object[0x6A] : -1; }

static int field_monster(unsigned slot, int include_face_down)
{
    unsigned type = type_of(CARDS[slot].id);
    if (type >= 20 && type != 24) return 0;
    if (phase() == BATTLE && duel.battle_active && !BATTLE_TRAP) {
        for (int i = 0; i < 2; i++)
            if (duel.battle[i] == (int)slot && !(duel.lost & (1 << i))) return 1;
    }
    return ((CARDS[slot].flags & OCCUPIED) || (duel.hidden_by_effect & (1u << slot))) &&
           (include_face_down || !(CARDS[slot].flags & FACE_DOWN));
}

static unsigned protection(unsigned slot)
{
    const Rules *rule;
    unsigned flags;
    if (!monster_zone(slot) || !field_monster(slot, 1)) return 0;
    rule = rules(CARDS[slot].id);
    flags = rule ? rule->protection : 0;
    /* A single hidden permission: first-turn attack, never an immunity. */
    if (CARDS[slot].flags & FACE_DOWN) return flags & FIRST_TURN;
    if (duel.field[slot].id == CARDS[slot].id) flags |= duel.field[slot].equip_protection;
    return flags;
}

static EXTENSION int matches_bonus(const Bonus *bonus, unsigned id, int by_id)
{
    if (id < 1 || id > CARD_COUNT) return 0;
    unsigned kind = by_id ? id : type_in_catalog(id);
    int type_matches = (bonus->match == 0xFFFF) | (kind == bonus->match);
    unsigned attribute = (bonus->scope & ATTRIBUTE_MASK) >> 2;
    if (!attribute) return type_matches;
    int attribute_matches = attribute == (LEVELS[id] >> 4) + 1u;
    return bonus->scope & MATCH_EITHER ? type_matches | attribute_matches
                                      : type_matches & attribute_matches;
}

/* One counter per side and distinct configured predicate. ID zero clears
 * them at the start of each duel. The ROM copy of every counter is zero. */
static GRAVE_FILTER_CODE void update_grave_filters(unsigned side, int id)
{
    for (Bonus *filter = GRAVE_FILTERS; filter->scope; filter++) {
        if (!id) {
            filter->grave_count[0] = 0;
            filter->grave_count[1] = 0;
        } else if (matches_bonus(filter, id, 0) && filter->grave_count[side] != 0xFFFF) {
            filter->grave_count[side]++;
        }
    }
}

static EXTENSION int count_bonus(const Bonus *bonus, unsigned source_side)
{
    int count = 0;
    unsigned scope = bonus->scope & 3;
    unsigned by_id = bonus->action == FIELD_ID || bonus->action == DECK_ID;
    for (unsigned side = 0; side < 2; side++) {
        if (scope < 2 && side != (source_side ^ scope)) continue;
        if (bonus->action == GRAVE_TYPE) {
            if (bonus->scope & ATTRIBUTE_MASK) count += GRAVE_FILTERS[bonus->match].grave_count[side];
            else if (bonus->match < 32) count += duel.graveyard[side][bonus->match];
            else for (int i = 0; i < 32; i++) count += duel.graveyard[side][i];
        } else if (bonus->action == DECK_TYPE || bonus->action == DECK_ID) {
            for (int i = 0; i < DECK_SIZE; i++)
                count += matches_bonus(bonus, duel.deck[side][i], by_id);
        } else {
            for (unsigned i = side * 15 + 5; i < side * 15 + 10; i++) {
                if (field_monster(i, 1)) count += matches_bonus(bonus, CARDS[i].id, by_id);
            }
        }
    }
    return count;
}

static unsigned cap_stat(int value) { return value < 0 ? 0 : value > 9999 ? 9999 : value; }

static MARKER_RULE Marker *slot_marker(unsigned slot)
{
    return &markers.slots[slot < 20 ? slot - 5 : slot - 15];
}

ENTRY u32 CalculateStats(const Card *card)
{
    int slot = field_slot(card);
    int attack = card->attack + card->modifier + card->terrain;
    int defense = card->defense + card->modifier + card->terrain;
    if (monster_zone(slot) && field_monster(slot, 1)) {
        unsigned side = owner(slot);
        if (duel.field[slot].id == card->id) attack += duel.field[slot].equip_attack;
        if (CONFIG->entry_markers) {
            const Marker *marker = slot_marker(slot);
            attack += marker->attack;
            defense += marker->defense;
        }
        for (unsigned i = 5; i < 25; i = i == 9 ? 20 : i + 1) {
            if (!field_monster(i, 1)) continue;
            const Rules *rule = rules(CARDS[i].id);
            if (!rule) continue;
            for (unsigned j = 0; j < rule->bonus_count; j++) {
                const Bonus *bonus = &rule->bonuses[j];
                int count;
                if (bonus->action >= SUMMON_DAMAGE) continue;
                if (bonus->action == AURA) {
                    unsigned scope = bonus->scope & 3;
                    if ((scope < 2 && side != (owner(i) ^ scope)) ||
                        !matches_bonus(bonus, card->id, 0)) continue;
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
    if (CONFIG->offsets[0]) update_grave_filters(0, 0);
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
    if (type >= 32) return;
    if (duel.graveyard[side][type] != 0xFFFF) duel.graveyard[side][type]++;
    if (CONFIG->offsets[0]) update_grave_filters(side, id);
}

static EXTENSION void end_instance(unsigned slot)
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

static EXTENSION void summon_damage(unsigned slot)
{
    const Rules *rule = rules(CARDS[slot].id);
    if (!rule) return;
    for (unsigned i = 0; i < rule->bonus_count; i++) {
        const Bonus *effect = &rule->bonuses[i];
        if (effect->action == SUMMON_DAMAGE)
            lose_lp(owner(slot) ^ effect->scope, effect->attack);
        else if (effect->action == SUMMON_HEAL) {
            unsigned side = owner(slot) ^ effect->scope;
            u16 current = AT(u16, SIDE(side) + 0x14);
            u32 total = (u32)current + effect->attack;
            AT(u16, SIDE(side) + 0x14) = total > 65535u ? 65535u : total;
        }
    }
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
    unsigned step = STEP & 15;
    /* Step 3 checks the selected attacker. The native end-turn step clears the lock. */
    u16 lock = step == 3 && (flags & FIRST_TURN) ? GAME(u16, 0x8009B16C) & 0x1000 : 0;
    s8 turns = flags & MAGIC ? *swords : 0;
    u32 hidden = 0;
    if ((flags & DIRECT) && (step == 5 || step == 6)) {
        unsigned i = side ? 5 : 20;
        for (unsigned end = i + 5; i < end; i++)
            if (CARDS[i].flags & OCCUPIED) hidden |= 1u << i;
        set_occupied(hidden, 0);
    }
    if (turns) *swords = 0;
    if (lock) GAME(u16, 0x8009B16C) &= ~lock;
    FN(void, 0x8001D670, void)();
    if (lock) GAME(u16, 0x8009B16C) |= lock;
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
            if (!did_equip) summon_damage(slot);
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

void MARKER_RULE ResetCardsWithMarkers(void)
{
    volatile u8 *memory = (volatile u8 *)&markers;
    for (unsigned i = 0; i < sizeof(markers); i++) memory[i] = 0;
    ResetCards();
}

void MARKER_RULE ConsumeFusionMaterial(Card *card)
{
    int slot = field_slot(card);
    if (monster_zone(slot)) {
        *slot_marker(slot) = (Marker){0};
        markers.fusion_slots |= 1u << slot;
        duel.field[slot] = (Instance){0};
    }
    RemoveCard(card);
}

/* Only the two placement call sites use this wrapper. The animation may
 * still have live pointers to the new object, so resolve at the field phase. */
void MARKER_RULE CreateMarkedPlacement(unsigned raw_slot, int deck_index)
{
    unsigned slot = raw_slot & 0x80 ? (raw_slot & 0x7F) + 15 : raw_slot;
    u32 fused = markers.fusion_slots;
    int reused = phase() == CONFIRMING && object_slot(OBJECTS[0]) == (int)slot &&
        monster_zone(slot) && !(fused & (1u << slot));
    FN(void, 0x80024D34, unsigned, int)(raw_slot, deck_index);
    if (!monster_zone(slot) || !field_monster(slot, 1) || reused) return;
    *slot_marker(slot) = (Marker){0};
    markers.pending_slot = slot;
    markers.pending_id = CARDS[slot].id;
}

static MARKER_RULE int entry_delta(const Rules *rule, unsigned action, unsigned side,
                                   int id, Marker *marker)
{
    int applied = 0;
    if (!rule) return 0;
    for (unsigned i = 0; i < rule->bonus_count; i++) {
        const Bonus *bonus = &rule->bonuses[i];
        unsigned scope = bonus->scope & 3;
        if (bonus->action != action || (scope != 2 && scope != side) ||
            !matches_bonus(bonus, id, 0)) continue;
        int sign = action == ENTRY_GROW ? 1 : -1;
        marker->attack += sign * bonus->attack;
        marker->defense += sign * bonus->defense;
        applied = 1;
    }
    return applied;
}

static MARKER_RULE void apply_entry(void)
{
    unsigned source = markers.pending_slot;
    int id = markers.pending_id;
    markers.pending_slot = 0;
    if (CARDS[source].id != id || !field_monster(source, 1)) return;
    const Rules *reduction = rules(id);
    u32 weakened = 0;
    for (unsigned slot = 5; slot < 25; slot = slot == 9 ? 20 : slot + 1) {
        if (!field_monster(slot, 1)) continue;
        int subject = CARDS[slot].id;
        unsigned side = owner(source) ^ owner(slot);
        Marker *marker = slot_marker(slot);
        entry_delta(rules(subject), ENTRY_GROW, side, id, marker);
        if (entry_delta(reduction, ENTRY_SHRINK, side, subject, marker))
            weakened |= 1u << slot;
    }
    /* Resolve all markers before testing for destruction. Recheck the
     * remaining targets when a destroyed card was providing an aura. */
    while (weakened) {
        u32 doomed = 0;
        for (unsigned slot = 5; slot < 25; slot = slot == 9 ? 20 : slot + 1)
            if ((weakened & (1u << slot)) && !CalculateStats(&CARDS[slot]) &&
                !(protection(slot) & INDESTRUCTIBLE)) doomed |= 1u << slot;
        if (!doomed) break;
        for (unsigned slot = 5; slot < 25; slot = slot == 9 ? 20 : slot + 1)
            if (doomed & (1u << slot)) RemoveCard(&CARDS[slot]);
        weakened &= ~doomed;
    }
}

void MARKER_RULE FieldActionsWithMarkers(void)
{
    markers.fusion_slots = 0;
    if (markers.pending_slot && !EFFECT_FLAGS) apply_entry();
    FieldActions();
}

ENTRY unsigned DeckAllowsCopies(int id, unsigned copies)
{
    const Rules *rule = rules(id);
    /* Zero in the rule record inherits the default; 0xFF bans this ID. */
    if (rule && rule->copies == 0xFF) return 0;
    unsigned limit = rule && rule->copies ? rule->copies :
                     (unsigned)(id - 17) < 5 ? 1 : CONFIG->default_copies;
    return copies < limit;
}


extern int RetailCardDrop(int rank);

ENTRY int SelectDeckDrop(int rank)
{
    unsigned opponent = GAME(u8, 0x8009B361);
    if (duel.deck_ready && opponent < DUELIST_COUNT &&
        (CONFIG->deck_drops[opponent / 8] & (1u << (opponent % 8)))) {
        u16 eligible[DECK_SIZE];
        unsigned count = 0;
        for (unsigned i = 0; i < DECK_SIZE; i++) {
            unsigned id = duel.deck[1][i];
            if (id >= 1 && id <= CARD_COUNT) eligible[count++] = id;
        }
        if (count) return eligible[FN(unsigned, 0x800358FC, unsigned)(count)];
    }
    return RetailCardDrop(rank);
}

typedef struct {
    u32 price, password;
} PasswordRecord;

__attribute__((used, noinline, section(".runtime.password")))
void UpdatePasswordShop(void)
{
    const volatile u8 *digits = (const volatile u8 *)0x8016D410;
    u32 packed = 0;
    for (unsigned i = 0; i < 8; i++) packed = (packed << 4) | digits[i];
    unsigned id = 100 * digits[5] + 10 * digits[6] + digits[7];
    unsigned stage = AT(u16, 0x8016D424) & 31;
    if ((packed >> 12) != CONFIG->password_prefix || (unsigned)(id - 1) >= CARD_COUNT ||
        (stage && AT(u16, 0x8016D4DC) != id)) {
        FN(void, 0x8016A37C, void)();
        return;
    }
    /* Route the alias through the stock preview, purchase and chest code. */
    volatile PasswordRecord *entry = (volatile PasswordRecord *)0x801A8000 + id;
    u32 price = entry->price;
    u32 password = entry->password;
    entry->price = 1;
    entry->password = packed;
    FN(void, 0x8016A37C, void)();
    entry->price = price;
    entry->password = password;
}


MOD_RULE void DealConfiguredDecks(const u16 *player, const u16 *rival)
{
    unsigned opponent = GAME(u8, 0x8009B361);
    if (opponent < DUELIST_COUNT && CONFIG->fixed_decks) {
        const u16 *offsets = (const u16 *)((const u8 *)CONFIG + CONFIG->fixed_decks);
        if (offsets[opponent]) rival = (const u16 *)((const u8 *)CONFIG + offsets[opponent]);
    }
    FN(void, 0x800245A0, const u16 *, const u16 *)(player, rival);
    if (opponent < DUELIST_COUNT) {
        const u16 *shuffled = (const u16 *)0x80177FE8;
        for (unsigned i = 0; i < DECK_SIZE; i++) {
            duel.deck[0][i] = shuffled[i];
            duel.deck[1][i] = shuffled[DECK_SIZE + i];
        }
        duel.deck_ready = 1;
    }
}

enum { TIER_COUNT = 9, TIER_TAG = 0x80, FONT_X = 0x280, FONT_Y = 232, SMALL_FONT_X = 0x290 };

typedef struct {
    u32 rgb[TIER_COUNT + 1];
    u8 by_id[CARD_COUNT + 1];
} NameColors;

static inline const NameColors *name_colors(void)
{
    return (const NameColors *)((const u8 *)CONFIG + CONFIG->name_colors);
}

static inline unsigned name_tag(unsigned color)
{
    return color - TIER_TAG - 1 < TIER_COUNT;
}

MOD_RULE void InsertTierName(u8 *box)
{
    unsigned channel = box[0x57], depth = box[0x58];
    const u8 *text = ((const u8 **)box)[depth];
    unsigned command = *text;
    unsigned id = GAME(u16, 0x8009B338);

    if (channel < 4 && name_tag(box[0x54]))
        box[0x54] = prior_name_color[channel];
    FN(void, 0x80037DA4, u8 *)(box);
    if (channel < 4 && (command & 0x30) == 0x20 &&
        (unsigned)(id - 1) < CARD_COUNT && box[0x58] != depth) {
        unsigned tier = name_colors()->by_id[id];
        if (tier) {
            prior_name_color[channel] = box[0x54];
            name_depth[channel] = box[0x58];
            box[0x54] = TIER_TAG + tier;
        }
    }
}

MOD_RULE void EndTierName(u8 *box)
{
    unsigned channel = box[0x57];
    if (channel < 4 && name_tag(box[0x54]) && name_depth[channel] == box[0x58])
        box[0x54] = prior_name_color[channel];
    FN(void, 0x80038E7C, u8 *)(box);
}

typedef struct {
    u32 attribute;
    s16 x, y, width, height, tpage;
    u8 u, v;
    s16 cx, cy;
    u32 rgb;
} FontSprite;
_Static_assert(__builtin_offsetof(FontSprite, rgb) == 20, "sprite RGB offset");

MOD_RULE void SortTierGlyph(FontSprite *sprite, void *ordering_table, u16 priority)
{
    unsigned color = 0;
    if ((u32)sprite == 0x1F8000C0)
        color = (unsigned)(sprite->cy - FONT_Y);
    else if ((u32)sprite == 0x1F800140)
        color = (unsigned)(sprite->cx - SMALL_FONT_X) >> 4;
    if (!name_tag(color)) {
        FN(void, 0x800849F0, FontSprite *, void *, u16)(sprite, ordering_table, priority);
        return;
    }
    u32 rgb = sprite->rgb, attribute = sprite->attribute;
    s16 cx = sprite->cx, cy = sprite->cy;
    if ((u32)sprite == 0x1F800140)
        sprite->cx = SMALL_FONT_X;
    else
        sprite->cy = FONT_Y;
    sprite->attribute = attribute & ~0x40u;
    sprite->rgb = name_colors()->rgb[color - TIER_TAG];
    FN(void, 0x800849F0, FontSprite *, void *, u16)(sprite, ordering_table, priority);
    sprite->cx = cx;
    sprite->cy = cy;
    sprite->rgb = rgb;
    sprite->attribute = attribute;
}

MOD_RULE void SortTierPolygon(u8 *polygon, void *ordering_table, u16 priority)
{
    /* The animated text path uses the same large-font CLUT coordinates. */
    u16 *clut = (u16 *)(polygon + 14);
    unsigned original = *clut;
    if ((u32)polygon == 0x1F800000 && (original & 63) == FONT_X / 16 &&
        name_tag((original >> 6) - FONT_Y))
        *clut = (FONT_Y << 6) | (FONT_X / 16);
    FN(void, 0x80084320, u8 *, void *, u16)(polygon, ordering_table, priority);
    *clut = original;
}
