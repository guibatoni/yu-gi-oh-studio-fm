"""Pacote de MOD Eclipse do Farao aplicado num catálogo sintético de 722 cartas.

O catálogo é sintético (os dados reais vêm do disco do usuário e nunca entram
no Git), mas usa os nomes, tipos e ATK aproximados das cartas citadas pelo mod.
"""
import csv
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from fmstudio.core import Project
from fmstudio.mod_data import CONFIG_KEY, normalize_rules
from fmstudio.mod_pack import (Catalog, Report, apply_mod, describe, load_pack, norm, plan_mod,
                               starter_pools)
from fmstudio.ps1_campaign_quests import quest_settings
from fmstudio.ps1_magic_values import magic_values
from fmstudio.ps1_mod import compile_mod
from fmstudio.tables import CARD_COUNT, DECK_SIZE, STARTER_POOLS

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / 'mods' / 'eclipse_do_farao' / 'mod.json'

MONSTERS = {
    'Blue-eyes White Dragon': (0, 3000, 0), 'Mystical Elf': (1, 800, 0), 'Time Wizard': (1, 500, 0),
    'Dark Magician': (1, 2500, 1), 'Baby Dragon': (0, 1200, 4), 'Curse of Dragon': (0, 2000, 1),
    'Celtic Guardian': (3, 1400, 2), 'Kuriboh': (7, 300, 1), 'Red-eyes B. Dragon': (0, 2400, 1),
    'Summoned Skull': (7, 2500, 1), 'Gaia the Fierce Knight': (3, 2300, 2),
    'Gaia the Dragon Champion': (0, 2600, 5), 'Thousand Dragon': (0, 2400, 5), 'Meteor B. Dragon': (0, 3500, 4),
    'B. Skull Dragon': (0, 3200, 1), 'Blue-eyes Ultimate Dragon': (0, 4500, 0), 'Tri-horned Dragon': (0, 2850, 1),
    'Serpent Night Dragon': (0, 2350, 1), 'Twin-headed Thunder Dragon': (15, 2800, 0),
    'Magician of Black Chaos': (1, 2800, 1), 'Dark Elf': (1, 2000, 1), 'Black Luster Soldier': (3, 3000, 2),
    'Kazejin': (1, 2400, 5), 'Sanga of the Thunder': (15, 2600, 0), 'Suijin': (16, 2500, 3),
    'Gate Guardian': (3, 3750, 1), 'Zoa': (7, 2600, 1), 'St. Joan': (8, 2800, 0), 'Labyrinth Tank': (14, 2400, 1),
    'Labyrinth Wall': (18, 0, 2), 'Perfectly Ultimate Great Moth': (9, 3500, 2), 'Great Moth': (9, 2600, 2),
    'Cocoon of Evolution': (9, 0, 2), 'Petit Moth': (9, 300, 2), 'Crimson Sunbird': (6, 2300, 4),
    'Harpie Lady Sisters': (6, 1950, 5), 'Cosmo Queen': (1, 2900, 1), 'Javelin Beetle': (9, 2450, 2),
    'Barrel Dragon': (14, 2600, 1), 'Perfect Machine King': (14, 2700, 2), 'Machine King': (14, 2200, 2),
    'Launcher Spider': (14, 2200, 4), 'Levia-Dragon': (13, 2600, 3), 'Sword Hunter': (3, 2450, 2),
    'Swordstalker': (3, 2000, 1), 'Rabid Horseman': (4, 2000, 2), 'Great Mammoth of Goldfine': (2, 2200, 1),
}
SPELLS = ['Dark Hole', 'Raigeki', 'Mooyan Curry', 'Red Medicine', "Goblin's Secret Remedy", 'Soul of the Pure',
          'Sparks', 'Hinotama', 'Final Flame', 'Ookazi', 'Tremendous Fire', 'Swords of Revealing Light',
          "Harpie's Feather Duster", 'Forest', 'Wasteland', 'Mountain', 'Sogen', 'Umi', 'Yami']
TRAPS = ['Fake Trap', 'Widespread Ruin', 'Acid Trap Hole', 'Invisible Wire', 'Bear Trap']
EQUIPS = ['Dragon Treasure', 'Book of Secret Arts', 'Violet Crystal', 'Legendary Sword', 'Mystical Moon',
          'Beast Fangs', 'Follow Wind', 'Dark Energy', 'Silver Bow and Arrow', 'Laser Cannon Armor',
          'Raise Body Heat', 'Horn of the Unicorn', 'Steel Shell', 'Machine Conversion Factory', 'Electro-whip',
          'Power of Kaishin', 'Salamandra', 'Vile Germs', 'Axe of Despair', 'Megamorph',
          'Sword of Dark Destruction', "Elf's Light"]
REMOVAL = {653: 'Crush Card', 656: 'Warrior Elimination', 660: 'Eternal Rest', 661: 'Stain Storm',
           662: 'Eradicating Aerosol', 663: 'Breath of Light', 664: 'Eternal Drought'}
ATTR_BY_TYPE = {0: 1, 1: 1, 2: 1, 3: 2, 4: 2, 5: 2, 6: 5, 7: 1, 8: 0, 9: 2, 10: 2, 11: 3, 12: 3, 13: 3,
                14: 1, 15: 0, 16: 3, 17: 4, 18: 2, 19: 2}


def synthetic_rows():
    named = ([(name, *stats) for name, stats in MONSTERS.items()]
             + [(name, 20, 0, 0) for name in SPELLS] + [(name, 21, 0, 0) for name in TRAPS]
             + [(name, 23, 0, 0) for name in EQUIPS])
    for kind in range(20):
        for step in range(25):
            atk = 200 + step * 110
            named.append((f'Filler {kind:02d}-{step:02d}', kind, atk, ATTR_BY_TYPE[kind]))
    rows, queue = {}, iter(named)
    for cid in range(1, CARD_COUNT + 1):
        if cid in REMOVAL:
            entry = (REMOVAL[cid], 20, 0, 0)
        else:
            entry = next(queue, (f'Spare {cid}', 20, 0, 0))
        name, kind, atk, attr = entry
        rows[cid] = dict(id=cid, nome=name, descricao='', ataque=atk, defesa=atk // 2, tipo_id=kind,
                         atributo_id=attr, nivel=4, guardian_1_id=1, guardian_2_id=2)
    return list(rows.values())


def make_project(folder: Path) -> Project:
    project = Project.create(folder, 'Teste Eclipse')
    base = folder / 'base'
    base.mkdir(parents=True, exist_ok=True)
    rows = synthetic_rows()
    with (base / 'cartas.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter=';')
        writer.writeheader()
        writer.writerows(rows)
    return Project.open(folder)


class TestEclipseModPack(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = make_project(Path(self.tmp.name) / 'projeto')
        self.pack = load_pack(PACK)

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_name_resolves_on_a_full_catalog(self):
        plan = plan_mod(self.project, self.pack)
        self.assertEqual(plan.report.missing, {})
        self.assertEqual(plan.report.warnings, [])

    def test_opponent_decks_respect_types_size_and_pool_rules(self):
        plan = plan_mod(self.project, self.pack)
        catalog = Catalog(self.project, Report())
        for row in self.pack['oponentes']:
            deck = plan.decks[row['id']]
            self.assertEqual(sum(deck.values()), DECK_SIZE, row['nome'])
            self.assertGreaterEqual(len(deck), 14, row['nome'])
            self.assertLessEqual(max(deck.values()), 3)
            allowed = {['Dragon', 'Spellcaster', 'Zombie', 'Warrior', 'Beast-Warrior', 'Beast', 'Winged Beast',
                        'Fiend', 'Fairy', 'Insect', 'Dinosaur', 'Reptile', 'Fish', 'Sea Serpent', 'Machine',
                        'Thunder', 'Aqua', 'Pyro', 'Rock', 'Plant'].index(name) for name in row['tipos']}
            monsters = [cid for cid in deck if catalog.is_monster(cid)]
            self.assertTrue(monsters)
            self.assertTrue(all(catalog.cards[cid]['tipo'] in allowed for cid in monsters), row['nome'])
            self.assertGreaterEqual(sum(deck[c] for c in monsters), 20, row['nome'])

    def test_effects_only_on_high_power_monsters(self):
        plan = plan_mod(self.project, self.pack)
        catalog = Catalog(self.project, Report())
        fusion_results = set(plan.fusions.values())
        for cid in plan.effects:
            card = catalog.cards[cid]
            minimum = 1801 if cid in fusion_results else 1901
            self.assertGreaterEqual(card['atk'], minimum, card['nome'])
            self.assertTrue(catalog.is_monster(cid))
        time_wizard = catalog.by_name[norm('Time Wizard')]
        self.assertNotIn(time_wizard, plan.effects)

    def test_starters_have_removal_and_exact_native_pools(self):
        plan = plan_mod(self.project, self.pack, starter=3)
        catalog = Catalog(self.project, Report())
        removal = {catalog.by_name[norm('Dark Hole')], catalog.by_name[norm('Raigeki')]}
        self.assertEqual(len(plan.starters), 6)
        for name, deck in plan.starters.items():
            self.assertEqual(sum(deck.values()), DECK_SIZE, name)
            self.assertTrue(removal & set(deck), name)
            pools, exact = starter_pools(deck)
            self.assertTrue(exact, name)
            self.assertLessEqual(len(pools), STARTER_POOLS)
            self.assertEqual(sum(row['compras'] for row in pools), DECK_SIZE)
        self.assertEqual(plan.starter_ps1, 'Laminas de Sogen')

    def test_apply_writes_valid_project_and_fits_native_area(self):
        plan, mod_plan, native = apply_mod(self.project, self.pack, starter='Mares Profundas')
        reopened = Project.open(self.project.folder)
        rules = reopened.metadata[CONFIG_KEY]
        normalize_rules(rules, {cid: reopened.get(cid) for cid in reopened.cards})
        self.assertEqual(rules['ia_ps1'], 'dificil')
        self.assertEqual(len(rules['duelistas']), 39)
        self.assertEqual(len(rules['receitas']['fusoes']), 16)
        settings = quest_settings(reopened)
        self.assertTrue(settings['ativado'])
        self.assertEqual(len(settings['requisitos']), 37)
        self.assertTrue(all(len(rows) <= 3 for rows in settings['requisitos'].values()))
        self.assertEqual(len(magic_values(reopened)['destruicao']), 7)
        replay = compile_mod(reopened, profile=True, wa_verified=True)
        self.assertEqual(len(replay.fusions), 16)
        self.assertEqual(sorted(op for op, kind in replay.groups if kind == 'deck'), list(range(1, 40)))
        self.assertTrue(all(kind in ('deck', 'pow', 'tec', 'bcd') for _, kind in replay.groups))
        self.assertEqual(replay.starters and len(replay.starters), len(plan.starter_pools))
        unexpected = [row for row in replay.pending if 'Perfis adicionais' not in row]
        self.assertEqual(unexpected, [])
        self.assertLessEqual(native.data_end + 256, native.bank_end)
        self.assertGreater(len(plan.effects), 60)
        text = describe(plan, reopened, self.pack, mod_plan)
        self.assertIn('Nitemare', text)
        self.assertTrue(any(p.name.startswith('projeto_antes_') for p in (self.project.folder / 'backups').iterdir()))

    def test_drops_prepare_next_opponent(self):
        plan = plan_mod(self.project, self.pack)
        catalog = Catalog(self.project, Report())
        drought = catalog.by_name[norm('Eternal Drought')]
        hunter = catalog.by_name[norm('Sword Hunter')]
        # Heishin (#8) entrega Eternal Drought; Isis (#16) antecede Kaiba e libera o caçador de dragões.
        self.assertIn(drought, plan.drops[8]['tec'])
        self.assertIn(hunter, plan.drops[16]['pow'])
        tally = Counter(len(plan.drops[op]['tec']) for op in plan.drops)
        self.assertNotIn(0, tally)


if __name__ == '__main__':
    unittest.main()
