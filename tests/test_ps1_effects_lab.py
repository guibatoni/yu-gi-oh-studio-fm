"""Deck numérico por carta no simulador e scanner/patch MIPS experimental PS1."""
import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fmstudio.abilities import quick_settings, replace_quick_effects
from fmstudio.core import check_effect, ModError
from fmstudio.duel_engine import DuelLab
from fmstudio.ps1_effects_lab import (
    SITES, scan_effect_sites, deck_global_patch_probe, patch_deck_global_limit,
    analyze_project_effects, save_project_effect_analysis,
)
from fmstudio.disc_build import build_test_disc
from fmstudio.disc import DiscReader
from fmstudio.tables import EXE_DELTA
from test_ps1_content import write_disc


DECK_SITE=SITES['construcao_deck'][1]-EXE_DELTA


def stock_like_exe(*, candidates=1, hook=False):
    size=max(DECK_SITE+SITES['construcao_deck'][2]+32, 0x90000)
    data=bytearray(b'PS-X EXE'+bytes(size-8))
    # Prologue MIPS addiu sp,sp,-32; comparação slti t0,t1,3;
    # branch beq t0,$zero, label; outros candidatos só em testes negativos.
    struct.pack_into('<I',data,DECK_SITE,0x27BDFFE0)
    if hook:
        struct.pack_into('<I',data,DECK_SITE,0x08000001)  # jump hook: deve recusar
    for index in range(candidates):
        pos=DECK_SITE+0x40+index*0x20
        struct.pack_into('<I',data,pos,0x29280003) # slti t0,t1,3
        struct.pack_into('<I',data,pos+4,0x11000006) # beq t0,$zero,+6
    return bytes(data)


class MipsEffectProbeTests(unittest.TestCase):
    def test_fingerprints_known_functions(self):
        exe=stock_like_exe()
        report=scan_effect_sites(exe)
        self.assertEqual(report['construcao_deck']['status'],
                         'regiao_encontrada_sem_hook_validado')
        self.assertEqual(report['construcao_deck']['endereco_ram'],
                         '0x800336F0')
        self.assertEqual(report['construcao_deck']['sha256_regiao'],
                         hashlib.sha256(exe[DECK_SITE:DECK_SITE+0x1F4]).hexdigest())

    def test_single_comparison_changes_only_immediate(self):
        original=stock_like_exe()
        result,changes=patch_deck_global_limit(original,40)
        self.assertEqual(len(changes),1)
        self.assertEqual(changes[0]['limite_global_por_id'],40)
        self.assertEqual(struct.unpack_from('<I',result,DECK_SITE+0x40)[0],0x29280028)
        self.assertEqual(len(original),len(result))
        diffs=[i for i,(a,b) in enumerate(zip(original,result)) if a!=b]
        self.assertEqual(diffs,[DECK_SITE+0x40])
        self.assertEqual(patch_deck_global_limit(original,3),(original,[]))

    def test_rejects_ambiguous_hooked_or_missing_function(self):
        for exe in (stock_like_exe(candidates=0),
                    stock_like_exe(candidates=2),
                    stock_like_exe(hook=True)):
            probe=deck_global_patch_probe(exe,8)
            self.assertEqual(probe['status'],'incompativel')
            with self.assertRaises(ModError):
                patch_deck_global_limit(exe,8)
        with self.assertRaises(ModError):
            patch_deck_global_limit(stock_like_exe(),41)

    def test_report_does_not_claim_effects_implemented(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            (folder/'base').mkdir()
            (folder/'base'/'source_SLUS_014.11').write_bytes(stock_like_exe())
            project=SimpleNamespace(
                folder=folder,
                metadata={'ps1_deck_global_limit':40},
                effects={'16':[
                    {'evento':'continuo','acao':'bonus_cemiterio_tipo',
                     'alvo':'proprio','valor':100,'tipo_id':0},
                    {'evento':'continuo','acao':'monstro_indestrutivel',
                     'alvo':'proprio','valor':0},
                ]})
            result=analyze_project_effects(project)
            self.assertEqual(result['perfil_limite_global_deck']['status'],
                             'candidato_unico_experimental')
            self.assertFalse(result['habilidades_ineditas_gravadas_no_PS1'])
            self.assertEqual(len(result['grupos_programados_no_studio']['atributos_dinamicos']),1)
            self.assertEqual(len(result['grupos_programados_no_studio']['protecao']),1)
            out=save_project_effect_analysis(project)
            self.assertTrue(out.is_file())
            self.assertIn('Duel_CalcCardStats',out.read_text(encoding='utf-8'))

    def test_bin_cue_global_deck_limit_keeps_source_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            source=folder/'Drop-X15.bin'
            exe=stock_like_exe()
            # Disc builder only needs a valid synthetic PS1 CD with SLUS and WA.
            write_disc(source,exe,bytes(2048))
            first=hashlib.sha256(source.read_bytes()).hexdigest()
            project=SimpleNamespace(folder=folder,arts={},metadata={
                'base_sha256':{'slus':hashlib.sha256(exe).hexdigest()},
                'ps1_deck_global_limit':15})
            project.export=lambda:(folder/'exportacao',{})
            result=build_test_disc(project,source)
            self.assertEqual(result['limite_global_copias_ps1_aplicado'][0]
                             ['limite_global_por_id'],15)
            with DiscReader(result['bin']) as reader:
                entry=next(x for x in reader.files() if x.path=='SLUS_014.11')
                modified=b''.join(reader.read_entry(entry))
            self.assertEqual(struct.unpack_from('<I',modified,DECK_SITE+0x40)[0],0x2928000F)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),first)


class CustomDeckCopiesTests(unittest.TestCase):
    def test_quick_preset_1_2_5_40_and_unlimited(self):
        for limit in (1,2,5,40):
            effects=replace_quick_effects([],
                          {'ataques':1,'custo_lp':0,'limite_copias':limit})
            self.assertEqual(quick_settings(effects)['limite_copias'],limit)
            cards={1:{'tipo_id':0}}
            lab=DuelLab(cards,{'1':effects})
            lab.set_deck('jogador',[1]*limit)
            if limit<40:
                with self.assertRaises(ModError):
                    lab.set_deck('jogador',[1]*(limit+1))
            self.assertEqual(len(lab.decks['jogador']),limit)
        unlimited=replace_quick_effects([],
                   {'ataques':1,'limite_copias':2,'sem_limite_deck':True})
        self.assertEqual(len([x for x in unlimited if x['acao']=='limite_copias_deck']),0)
        lab=DuelLab({1:{'tipo_id':0}}, {'1':unlimited})
        lab.set_deck('jogador',[1]*40)
        self.assertEqual(len(lab.decks['jogador']),40)

    def test_legacy_limit_three_and_manual_validation(self):
        self.assertEqual(replace_quick_effects([],
                          {'ataques':1,'limite_copias':3}),[])
        with self.assertRaises(ModError):
            replace_quick_effects([],
                  {'ataques':1,'limite_copias':41})
        for amount in (0,41,-1):
            with self.assertRaises(ModError):
                check_effect({'evento':'regra_deck','acao':'limite_copias_deck',
                              'alvo':'proprio','valor':amount})
        valid=check_effect({'evento':'regra_deck','acao':'limite_copias_deck',
                            'alvo':'proprio','valor':2})
        self.assertEqual(valid['valor'],2)


if __name__=='__main__':
    unittest.main()
