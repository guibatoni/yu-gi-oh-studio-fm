"""Regressões da economia PS1: baú, preços, ganho por vitória e segurança."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import struct
import unittest

from fmstudio.core import ModError, Project, _write_csv
from fmstudio.passwords import original_passwords
from fmstudio.ps1_economy import (
    CHEST_VISIBILITY_KEY, DUEL_STARS_KEY, PASSWORD_PRICES_KEY, PRICE_LIMIT,
    REWARD_PC, REWARD_ORIGINAL, REWARD_STORE_PC, REWARD_STORE,
    REWARD_LOAD_PC, REWARD_LOAD,
    apply_password_prices, read_prices, reward_status, patch_win_reward,
    chest_show_all, fixed_win_reward, price_overrides,
    set_chest_show_all, set_password_price, reset_password_price, set_win_reward,
)
from fmstudio.ps1_mod import patch_chest_catalog, inspect_chest_catalog
from fmstudio.tables import PASSWORD_BASE, EXE_DELTA, CARD_COUNT
from test_ps1_mod import seed_chest_catalog


def original_exe():
    """Conserva as três instruções verificadas no SLUS original, sem ROM."""
    exe=bytearray(REWARD_LOAD_PC-EXE_DELTA+16)
    exe[:8]=b'PS-X EXE'
    struct.pack_into('<I',exe,REWARD_PC-EXE_DELTA,REWARD_ORIGINAL)
    struct.pack_into('<I',exe,REWARD_STORE_PC-EXE_DELTA,REWARD_STORE)
    struct.pack_into('<I',exe,REWARD_LOAD_PC-EXE_DELTA,REWARD_LOAD)
    return bytes(exe)


def original_prices():
    wa=bytearray(PASSWORD_BASE + 741*8 + 8)
    for cid,cost in ((1,999999),(16,250),(722,20)):
        struct.pack_into('<II',wa,PASSWORD_BASE+cid*8,cost,0x12345678)
    return bytes(wa)


class PS1EconomyTests(unittest.TestCase):
    def test_reward_patch_only_one_guarded_instruction(self):
        base=original_exe()
        self.assertEqual(reward_status(base)['status'],'original_por_rank')
        for count in (1,5,10,99,255):
            with self.subTest(count=count):
                modified,report=patch_win_reward(base,count)
                at=REWARD_PC-EXE_DELTA
                self.assertEqual(modified[:at],base[:at])
                self.assertEqual(modified[at+4:],base[at+4:])
                self.assertEqual(struct.unpack_from('<I',modified,at)[0],0x24020000|count)
                self.assertEqual(report,{'status':'fixo','estrelas':count})
                self.assertEqual(patch_win_reward(modified,count)[0],modified)
        self.assertEqual(patch_win_reward(base,None)[0],base)

    def test_reward_guard_rejects_incompatible_mod_and_out_of_range(self):
        base=bytearray(original_exe())
        for value in (-1,0,256,1000,True,2.5):
            with self.subTest(value=value), self.assertRaises(ModError):
                patch_win_reward(base,value)
        struct.pack_into('<I',base,REWARD_LOAD_PC-EXE_DELTA,0)
        with self.assertRaisesRegex(ModError,'load'):
            patch_win_reward(base,5)
        self.assertEqual(reward_status(original_exe()),{'status':'original_por_rank','estrelas':None})

    def test_password_cost_only_mutates_selected_u32(self):
        base=original_prices()
        edited,rows=apply_password_prices(base,{1:0,16:50,722:999999})
        self.assertEqual(read_prices(edited,(1,16,722)),{1:0,16:50,722:999999})
        self.assertEqual(len(rows),3)
        for cid in (1,16,722):
            offset=PASSWORD_BASE+cid*8
            self.assertEqual(edited[offset+4:offset+8],base[offset+4:offset+8])
        self.assertEqual(edited[:PASSWORD_BASE+8],base[:PASSWORD_BASE+8])
        self.assertEqual(edited[PASSWORD_BASE+722*8+8:],base[PASSWORD_BASE+722*8+8:])

    def test_expanded_price_reads_shifted_password_table(self):
        base=original_prices()
        data=bytearray(base[:722*2048]+b'\0'*(18*2048)+base[722*2048:])
        struct.pack_into('<II',data,PASSWORD_BASE+723*8+18*2048,100,0x12345678)
        self.assertEqual(read_prices(data,(16,722,723),expanded=True),{16:250,722:20,723:100})
        with self.assertRaises(ModError):
            read_prices(base,(723,),expanded=False)

    def test_chest_visibility_toggle_preserves_retail_bytes(self):
        size=0x80032644 - EXE_DELTA + 16
        base=bytearray(size)
        seed_chest_catalog(base)
        initial=bytes(base)
        self.assertEqual(patch_chest_catalog(initial,show_all=False),initial)
        self.assertEqual(inspect_chest_catalog(initial)['status'],'ausente')
        enabled=patch_chest_catalog(initial,show_all=True)
        self.assertEqual(inspect_chest_catalog(enabled)['status'],'aplicado')
        with self.assertRaisesRegex(ModError,'original'):
            patch_chest_catalog(enabled,show_all=False)

    def test_project_settings_survive_reopen_and_rollback_on_save_failure(self):
        with TemporaryDirectory() as tmp:
            project=Project.create(Path(tmp)/'mod','Teste')
            project.cards={1:{'id':1,'nome':'Card'},723:{'id':723,'nome':'Extra'}}
            self.assertTrue(chest_show_all(project))
            self.assertIsNone(fixed_win_reward(project))
            set_chest_show_all(project,False)
            set_win_reward(project,24)
            set_password_price(project,1,250)
            set_password_price(project,723,45)
            reopened=Project.open(project.folder)
            self.assertFalse(chest_show_all(reopened))
            self.assertEqual(fixed_win_reward(reopened),24)
            self.assertEqual(price_overrides(reopened),{1:250,723:45})
            before=dict(project.metadata)
            with patch.object(project,'save',side_effect=OSError('readonly')):
                with self.assertRaises(OSError):
                    set_win_reward(project,15)
                with self.assertRaises(OSError):
                    set_chest_show_all(project,True)
            self.assertEqual(project.metadata,before)
            reset_password_price(project,723)
            self.assertEqual(price_overrides(project),{1:250})
            set_win_reward(project,None)
            self.assertIsNone(fixed_win_reward(project))

    def test_invalid_card_price_rejected_before_disk_writes(self):
        with TemporaryDirectory() as tmp:
            project=Project.create(Path(tmp)/'mod','Teste')
            project.cards={1:{'id':1}}
            for cid,cost in ((0,4),(741,12),(1,-1),(1,1000000),(1,'12.5'),(1,True),(40,10)):
                with self.subTest(cid=cid,cost=cost), self.assertRaises(ModError):
                    set_password_price(project,cid,cost)
            self.assertFalse(price_overrides(project))

    def test_password_editor_keeps_original_csv_intact(self):
        with TemporaryDirectory() as tmp:
            project=Project.create(Path(tmp)/'mod','Teste')
            project.cards={16:{'id':16,'nome':'Card'}}
            source=project.folder/'base'/'senhas.csv'
            source.parent.mkdir(exist_ok=True)
            _write_csv(source,[{'carta_id':16,'password':'01234567',
                               'password_valido_bcd':1,'custo_starchips':555}])
            stock=source.read_bytes()
            self.assertEqual(original_passwords(project)[16].cost,555)
            set_password_price(project,16,35)
            self.assertEqual(original_passwords(project)[16].cost,35)
            self.assertEqual(stock,source.read_bytes())
            reset_password_price(project,16)
            self.assertEqual(original_passwords(project)[16].cost,555)


if __name__ == '__main__':
    unittest.main()
