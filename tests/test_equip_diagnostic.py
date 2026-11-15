"""Testes de diagnóstico de equipamentos em BIN/CUE sintético."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from fmstudio.ps1_equip import (patch_equipment_targets,
                               diagnose_equipment_project, describe_equip_diagnostic)
from test_ps1_content import write_disc
from test_ps1_equip import sample_wa


class DiagnoseEquipTests(unittest.TestCase):
    def test_original_false_generated_true(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=root/'Drop-x15.bin'
            modified=root/'FM_STUDIO_TESTE_Drop-x15.bin'
            exe=b'PS-X EXE'+bytes(2048)
            wa=sample_wa()
            patched,_=patch_equipment_targets(wa,{'650':[1]})
            write_disc(source,exe,wa)
            write_disc(modified,exe,patched)
            project=SimpleNamespace(metadata={
                'base_source':str(source),'ps1_equip_additions':{'650':[1]}})
            report=diagnose_equipment_project(project,modified)
            self.assertTrue(report['sete_tabelas_iguais'])
            self.assertEqual(report['comparacoes'][0]['resultado'],'ADICIONADO_A_TABELA')
            self.assertEqual(report['codigo_equip_igual_a_origem'],True)
            self.assertIn('adicionado à tabela',describe_equip_diagnostic(report))

    def test_selected_original_reports_not_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=root/'Drop-x15.bin'
            write_disc(source,b'PS-X EXE'+bytes(2048),sample_wa())
            project=SimpleNamespace(metadata={
                'base_source':str(source),'ps1_equip_additions':{'650':[1]}})
            report=diagnose_equipment_project(project,source)
            self.assertEqual(report['comparacoes'][0]['resultado'],'NAO_GRAVADO')
            self.assertIn('NÃO GRAVADO',describe_equip_diagnostic(report))

    def test_no_plan_gives_actionable_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            from fmstudio.core import ModError
            with self.assertRaisesRegex(ModError,'Nenhuma permissão'):
                diagnose_equipment_project(SimpleNamespace(metadata={}),Path(tmp)/'disc.bin')


if __name__=='__main__':
    unittest.main()
