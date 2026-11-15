"""Persistência de projeto FM. Não altera a imagem original e não implementa efeitos no PS1."""
from __future__ import annotations
import csv
import hashlib
import json
import os
import re
import shutil
import struct
from datetime import datetime, timezone
from pathlib import Path

from .tables import (CARD_COUNT, EXE_DELTA, LEVEL_ADDR, STATS_ADDR, decode_all,
                     sha256, TYPE_NAMES, ATTR_NAMES, STAR_NAMES)
from .disc import DiscReader, DiscError

SCHEMA_VERSION = 1
DEFAULT_NAME_COLOR = '#F1CF6E'  # Cor da prévia do Studio; não altera a ROM.
FIELDS = ('nome', 'descricao', 'cor_nome', 'ataque', 'defesa', 'tipo_id', 'atributo_id', 'nivel', 'guardian_1_id', 'guardian_2_id')
NUMERIC = ('ataque', 'defesa', 'tipo_id', 'atributo_id', 'nivel', 'guardian_1_id', 'guardian_2_id')
EVENTS = {
    'invocar': 'Ao invocar', 'atacar': 'Ao atacar', 'defender': 'Ao defender',
    'destruir': 'Ao destruir outro monstro', 'destruido': 'Ao ser destruído',
    'inicio_turno': 'Início do turno', 'fim_turno': 'Fim do turno',
}
ACTIONS = {'aumentar_atk':'Aumentar ATK', 'reduzir_atk':'Reduzir ATK',
           'aumentar_def':'Aumentar DEF', 'reduzir_def':'Reduzir DEF',
           'dano_lp':'Causar dano aos LP', 'cura_lp':'Recuperar LP'}
TARGETS = {'proprio':'Próprio monstro / jogador', 'inimigo':'Monstro / jogador adversário'}

class ModError(ValueError):
    pass


def _timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _read_csv(path: Path):
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f, delimiter=';'))


def _write_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=';', extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def _write_json_atomic(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(tmp, path)


def _bounded_int(value, name, low, high, step=1):
    try:
        v = int(str(value).strip())
    except (ValueError, TypeError) as exc:
        raise ModError(f'{name}: informe número inteiro') from exc
    if not (low <= v <= high) or v % step:
        raise ModError(f'{name}: esperado {low} a {high}' + (f' em múltiplos de {step}' if step != 1 else ''))
    return v


def check_card_edit(row: dict):
    cleaned = {}
    for key in FIELDS:
        if key not in row:
            continue
        val = row[key]
        if key == 'cor_nome':
            color = str(val).strip().upper()
            if not re.fullmatch(r'#[0-9A-F]{6}', color):
                raise ModError('cor_nome: escolha uma cor RGB válida (#RRGGBB)')
            cleaned[key] = color
        elif key in ('nome', 'descricao'):
            if len(str(val)) > (100 if key == 'nome' else 2000):
                raise ModError(f'{key}: texto muito longo')
            cleaned[key] = str(val)
        elif key in ('ataque', 'defesa'):
            cleaned[key] = _bounded_int(val, key, 0, 5110, 10)
        elif key == 'tipo_id':
            cleaned[key] = _bounded_int(val, key, 0, 31)
        elif key == 'atributo_id':
            cleaned[key] = _bounded_int(val, key, 0, 15)
        elif key == 'nivel':
            cleaned[key] = _bounded_int(val, key, 0, 15)
        else:
            cleaned[key] = _bounded_int(val, key, 0, 15)
    return cleaned


def check_effect(entry: dict):
    event, action, target = entry.get('evento'), entry.get('acao'), entry.get('alvo')
    if event not in EVENTS or action not in ACTIONS or target not in TARGETS:
        raise ModError('Efeito: evento, ação ou alvo não suportado nesta versão')
    amount = _bounded_int(entry.get('valor'), 'valor do efeito', 0, 9999)
    if amount == 0:
        raise ModError('Valor do efeito precisa ser maior que zero')
    if action in ('dano_lp','cura_lp') and target not in TARGETS:
        raise ModError('Alvo de LP inválido')
    return {'evento':event, 'acao':action, 'alvo':target, 'valor':amount,
            'observacao':str(entry.get('observacao',''))[:500]}


class Project:
    def __init__(self, folder: Path, metadata: dict, edits=None, effects=None, arts=None):
        self.folder = Path(folder)
        self.metadata = metadata
        self.edits: dict[str,dict] = edits or {}
        self.effects: dict[str,list] = effects or {}
        self.arts: dict[str,str] = arts or {}
        self.cards: dict[int,dict] = {}
        self.fusions: list[dict] = []
        self.imported_notes: list[str] = []
        self._load_base()

    @classmethod
    def create(cls, folder: Path, name: str):
        if not name.strip():
            raise ModError('Nome do projeto obrigatório')
        folder = Path(folder)
        if (folder / 'projeto.json').exists():
            raise ModError('Já existe um projeto nesta pasta; use Abrir projeto')
        folder.mkdir(parents=True, exist_ok=True)
        obj = cls(folder, {'schema':SCHEMA_VERSION, 'nome':name.strip()[:100], 'created':_timestamp(),
                          'updated':_timestamp(), 'target':'PS1 SLUS-01411',
                          'fusion_policy':'readonly_stock', 'base_sha256':{}, 'base_source':''})
        obj.save()
        return obj

    @classmethod
    def open(cls, folder: Path):
        folder = Path(folder)
        path = folder / 'projeto.json'
        if not path.is_file():
            raise ModError(f'Não há projeto.json em {folder}')
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('schema') != SCHEMA_VERSION:
            raise ModError('Versão do projeto incompatível')
        return cls(folder, data, data.get('edicoes',{}), data.get('efeitos',{}), data.get('artes',{}))

    def save(self):
        self.metadata['updated'] = _timestamp()
        data = dict(self.metadata)
        data['edicoes'] = self.edits
        data['efeitos'] = self.effects
        data['artes'] = self.arts
        current = self.folder / 'projeto.json'
        # Backup rotativo: recupera uma edição acidental sem copiar a ISO.
        if current.is_file():
            backups = self.folder / 'backups'
            backups.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
            shutil.copy2(current, backups / f'projeto_{stamp}.json')
            for old in sorted(backups.glob('projeto_*.json'))[:-15]:
                old.unlink()
        _write_json_atomic(current, data)

    def _load_base(self):
        file = self.folder / 'base' / 'cartas.csv'
        if file.is_file():
            self.cards = {}
            for row in _read_csv(file):
                cid = _bounded_int(row.get('id'), 'ID da carta', 1, CARD_COUNT)
                if cid in self.cards:
                    raise ModError(f'Carta repetida: {cid}')
                self.cards[cid] = row
        fusions = self.folder / 'base' / 'fusoes.csv'
        self.fusions = _read_csv(fusions) if fusions.exists() else []
        meta = self.folder / 'base' / 'resumo.json'
        self.imported_notes = json.loads(meta.read_text(encoding='utf-8')).get('warnings',[]) if meta.exists() else []

    def import_tables(self, source: Path):
        source = Path(source)
        if not (source / 'cartas.csv').is_file() or not (source / 'fusoes.csv').is_file():
            raise ModError('Selecione a pasta com cartas.csv E fusoes.csv (ex.: analysis\\tabelas)')
        rows = _read_csv(source / 'cartas.csv')
        ids = [int(row['id']) for row in rows]
        if len(ids) != CARD_COUNT or len(set(ids)) != CARD_COUNT or set(ids) != set(range(1, CARD_COUNT+1)):
            raise ModError('A base deve conter exatamente 722 IDs de cartas únicos (1–722)')
        if self.cards and (self.edits or self.effects):
            raise ModError('Projeto já editado: crie outro projeto para trocar a base')
        base = self.folder / 'base'
        base.mkdir(parents=True, exist_ok=True)
        stale_exe = base / 'source_SLUS_014.11'
        if stale_exe.is_file():
            stale_exe.unlink()
        for name in ('cartas.csv','fusoes.csv','equipamentos.csv','rituais.csv','decks_drops.csv','resumo_duelistas.csv','senhas.csv','resumo.json'):
            f = source / name
            if f.is_file() and f.resolve() != (base / name).resolve():
                shutil.copy2(f, base / name)
        self._load_base()
        self.metadata['base_source'] = str(source.resolve())
        self.metadata['base_sha256'] = {'cartas':sha256(base/'cartas.csv'),
                                        'fusoes':sha256(base/'fusoes.csv') if (base/'fusoes.csv').exists() else None}
        # Auto-detecta o executável ao lado das tabelas, sem sobrescrever nada.
        for candidate in (source.parent/'extracted'/'SLUS_014.11', source.parent.parent/'extracted'/'SLUS_014.11'):
            if candidate.is_file():
                self.attach_executable(candidate)
                break
        self.save()

    def import_disc(self, path: Path):
        if self.cards and (self.edits or self.effects):
            raise ModError('Não substitua uma base editada. Crie um novo projeto')
        with DiscReader(path) as reader:
            names = {x.path.upper():x for x in reader.files() if not x.is_dir}
            if not {'SLUS_014.11','DATA/WA_MRG.MRG'}.issubset(names):
                raise ModError('Este disco não contém SLUS_014.11 e DATA/WA_MRG.MRG')
            slus = b''.join(reader.read_entry(names['SLUS_014.11']))
            wa = b''.join(reader.read_entry(names['DATA/WA_MRG.MRG']))
        results, notes = decode_all(slus, wa)
        if len(results['cartas']) != CARD_COUNT:
            raise ModError('Extração não retornou 722 cartas')
        base = self.folder/'base'
        base.mkdir(exist_ok=True)
        for key, rows in results.items():
            _write_csv(base/(key+'.csv'), rows)
        _write_json_atomic(base/'resumo.json', {'source':str(path), 'warnings':notes,
                'source_sha256':{'SLUS_014.11':hashlib.sha256(slus).hexdigest(),
                                 'DATA/WA_MRG.MRG':hashlib.sha256(wa).hexdigest()}})
        (base/'source_SLUS_014.11').write_bytes(slus)
        self._load_base()
        self.metadata['base_source'] = str(Path(path).resolve())
        self.metadata['base_sha256'] = {'cartas':sha256(base/'cartas.csv'),
                                        'fusoes':sha256(base/'fusoes.csv'),
                                        'slus':hashlib.sha256(slus).hexdigest()}
        self.save()

    def extract_complete(self, source: Path, progress=None):
        """Extrai textos e imagens da própria imagem do jogo ou da pasta extraída.

        Usa somente arquivos locais; garante que SLUS/tabelas pertencem à
        mesma base. As receitas de fusão ficam somente leitura.
        """
        from .deep_extract import (extract_texts, export_visuals, write_semicolon_csv,
                                   prepare_full_catalog, build_full_report, ExtractionError)
        source=Path(source)
        if progress:progress('Lendo os arquivos do jogo (somente leitura)...')
        raw_files=[]
        if source.is_dir():
            exe_candidates=[source/'SLUS_014.11',source/'extracted'/'SLUS_014.11',source/'analysis'/'extracted'/'SLUS_014.11']
            wa_candidates=[source/'DATA'/'WA_MRG.MRG',source/'WA_MRG.MRG',
                           source/'extracted'/'DATA'/'WA_MRG.MRG',source/'analysis'/'extracted'/'DATA'/'WA_MRG.MRG']
            exe_path=next((p for p in exe_candidates if p.is_file()),None)
            wa_path=next((p for p in wa_candidates if p.is_file()),None)
            if not exe_path or not wa_path:
                raise ModError('Pasta incorreta: selecione a pasta com SLUS_014.11 e DATA/WA_MRG.MRG (ou a pasta analysis que contém extracted).')
            slus=exe_path.read_bytes(); wa=wa_path.read_bytes()
            raw_files=[{'arquivo':'SLUS_014.11','tamanho':len(slus),'sha256':hashlib.sha256(slus).hexdigest()},
                       {'arquivo':'DATA/WA_MRG.MRG','tamanho':len(wa),'sha256':hashlib.sha256(wa).hexdigest()}]
        else:
            with DiscReader(source) as disc:
                entries={i.path.upper():i for i in disc.files() if not i.is_dir}
                if not {'SLUS_014.11','DATA/WA_MRG.MRG'}.issubset(entries):
                    raise ModError('Imagem não possui SLUS_014.11 e DATA/WA_MRG.MRG')
                slus=b''.join(disc.read_entry(entries['SLUS_014.11']))
                wa=b''.join(disc.read_entry(entries['DATA/WA_MRG.MRG']))
                raw_files=[{'arquivo':e.path,'tamanho':e.size,'extent_lba':e.extent}
                           for e in entries.values()]
        if not slus.startswith(b'PS-X EXE'):
            raise ModError('A base extraída não possui cabeçalho PS-X EXE válido')
        if self.cards:
            from .tables import decode_cards
            checked,_=decode_cards(slus)
            if len(checked)!=len(self.cards):
                raise ModError('O SLUS selecionado possui quantidade de cartas diferente do projeto')
            for item in checked:
                existing=self.cards[item['id']]
                if (str(existing.get('valor_hex','')).upper()!=item['valor_hex'] or
                    int(existing.get('nivel',-1))!=item['nivel'] or
                    int(existing.get('atributo_id',-1))!=item['atributo_id']):
                    raise ModError(f'O arquivo SLUS é de outra base! Divergência na carta #{item["id"]:03d}. Não extraí para evitar misturar MODs.')
            source_exe=self.folder/'base'/'source_SLUS_014.11'
            if source_exe.exists() and hashlib.sha256(source_exe.read_bytes()).digest()!=hashlib.sha256(slus).digest():
                raise ModError('O executável informado não corresponde ao SLUS vinculado anteriormente. Crie outro projeto para essa versão.')
        else:
            # Se o projeto não tem cartas, importa os dados básicos primeiro.
            tables,notes=decode_all(slus,wa)
            base=self.folder/'base'
            base.mkdir(parents=True,exist_ok=True)
            for k,rows in tables.items():_write_csv(base/(k+'.csv'),rows)
            _write_json_atomic(base/'resumo.json',{'warnings':notes,
                'source_sha256':{'SLUS_014.11':hashlib.sha256(slus).hexdigest(),
                                 'DATA/WA_MRG.MRG':hashlib.sha256(wa).hexdigest()}})
            (base/'source_SLUS_014.11').write_bytes(slus)
            self._load_base()
            self.metadata['base_source']=str(source.resolve())
            self.metadata['base_sha256']={'cartas':sha256(base/'cartas.csv'),'fusoes':sha256(base/'fusoes.csv'),
                                          'slus':hashlib.sha256(slus).hexdigest()}
        # Mesmo para projetos importados por CSV, se um SHA do WA foi registrado, respeite-o.
        info=self.folder/'base'/'resumo.json'
        if info.is_file():
            summary=json.loads(info.read_text(encoding='utf-8'))
            expected=(summary.get('source_sha256') or {}).get('DATA/WA_MRG.MRG')
            if expected and expected.lower()!=hashlib.sha256(wa).hexdigest():
                raise ModError('WA_MRG.MRG diferente do arquivo usado para extrair as tabelas. Imagem não misturada.')
        if progress:progress('Decodificando nomes, descrições, diálogos e demais textos...')
        results,warnings=extract_texts(slus)
        base=self.folder/'base'
        staging=base/'_extracao_em_andamento'
        import shutil
        if staging.exists(): shutil.rmtree(staging)
        staging.mkdir(parents=True)
        try:
            for k,v in results.items():write_semicolon_csv(staging/(k+'.csv'),v)
            if progress:progress('Extraindo artes, miniaturas e retratos do disco...')
            visualstats,manifest,visualwarn=export_visuals(wa,staging/'visuais',include_strips=True,progress=progress)
            warnings+=visualwarn
            (staging/'manifesto_imagens.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
            # Indexações de dados: relações com nomes ficam separadas para não
            # sobrescrever as tabelas brutas nem modificar as receitas originais.
            if progress:progress('Cruzando fusões, equipamentos, rituais e pools...')
            txt={int(r['id']):r for r in results['nomes_descricoes']}
            def label(cid):
                try:return txt[int(cid)].get('nome','')
                except (KeyError,ValueError,TypeError):return ''
            named_tables={}
            for kind,columns in [('fusoes',('material_1','material_2','resultado')),
                                 ('equipamentos',('equipamento_id','monstro_id')),
                                 ('rituais',('ritual_id','tributo_1','tributo_2','tributo_3','resultado')),
                                 ('decks_drops',('carta_id',)),('senhas',('carta_id',))]:
                src=base/(kind+'.csv')
                if not src.exists():continue
                transformed=[]
                for original in _read_csv(src):
                    row=dict(original)
                    for field in columns:row[field+'_nome']=label(row.get(field))
                    if kind=='decks_drops':
                        row['probabilidade_teorica_pct']=''
                        try:
                            if int(row['peso'])>=0:row['probabilidade_teorica_pct']=round(100*int(row['peso'])/2048,6)
                        except (ValueError,KeyError):pass
                    transformed.append(row)
                named_tables[kind]=len(transformed)
                write_semicolon_csv(staging/(kind+'_nomeado.csv'),transformed)
            metrics=results['metricas_texto'][0]
            stats=build_full_report(base,results,metrics,visualstats,warnings,
                                    {'local':str(source.resolve()),'arquivos':raw_files,
                                     'sha256_slus':hashlib.sha256(slus).hexdigest(),
                                     'sha256_wa_mrg':hashlib.sha256(wa).hexdigest()})
            stats['indexacoes_nomeadas']=named_tables
            stats['artefatos_csv']=[x.name for x in sorted(staging.glob('*.csv'))]
            (staging/'relatorio_completo.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
            target=base/'extracao_completa'
            if target.exists():
                backup=base/'extracao_completa_anterior'
                if backup.exists():shutil.rmtree(backup)
                target.replace(backup)
            staging.replace(target)
            # Só enriquecer nomes após criar todas as saídas da extração.
            enrichment=prepare_full_catalog(base,results['nomes_descricoes'])
            stats['enriquecimento_cartas']=enrichment
            (target/'relatorio_completo.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
            self._load_base()
            self.metadata['base_sha256']['cartas']=sha256(base/'cartas.csv')
            self.metadata['deep_extraction']={'completed':_timestamp(),'results_path':str(target),
                'names':metrics['nomes_cartas'],'descriptions':metrics['descricoes_cartas'],
                'arts':visualstats['artes'],'thumbnails':visualstats['miniaturas'],
                'portraits':visualstats['retratos'],'warnings':len(warnings)}
            self.save()
            if progress:progress('Extração concluída. Verifique o relatório detalhado.')
            return stats
        except Exception:
            if staging.exists():shutil.rmtree(staging)
            raise

    def attach_executable(self, path: Path):
        path = Path(path)
        raw = path.read_bytes()
        if not raw.startswith(b'PS-X EXE') or len(raw) < (LEVEL_ADDR-EXE_DELTA + CARD_COUNT+1):
            raise ModError('Executável não é um PS-X EXE válido para SLUS-01411')
        # Conferir o hash do relatório, se existir, antes de comparar cada carta.
        summary = self.folder/'base'/'resumo.json'
        if summary.exists():
            info = json.loads(summary.read_text(encoding='utf-8'))
            expected = info.get('source_sha256', {}).get('SLUS_014.11')
            if expected and hashlib.sha256(raw).hexdigest() != expected:
                raise ModError('Este SLUS não corresponde ao hash usado na extração das tabelas')
        # Conferir as estatísticas e níveis de TODAS as cartas.
        for cid, card in self.cards.items():
            pos = STATS_ADDR - EXE_DELTA + (cid-1)*4
            value = struct.unpack_from('<I', raw, pos)[0]
            if f'{value:08X}' != card['valor_hex'].upper():
                raise ModError(f'SLUS diferente das tabelas na carta #{cid:03}')
            lv_attr = raw[LEVEL_ADDR - EXE_DELTA + cid]
            if lv_attr != ((int(card['atributo_id']) << 4) | int(card['nivel'])):
                raise ModError(f'SLUS diferente das tabelas (nível/atributo) na carta #{cid:03}')
        dest = self.folder/'base'/'source_SLUS_014.11'
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.resolve() != path.resolve():
            shutil.copy2(path, dest)
        self.metadata['base_sha256']['slus'] = hashlib.sha256(raw).hexdigest()
        self.save()

    def get(self, cid: int):
        if cid not in self.cards:
            raise ModError(f'Carta #{cid} não encontrada')
        base = dict(self.cards[cid])
        base.setdefault('nome', '')
        base.setdefault('descricao', '')
        base.setdefault('cor_nome', DEFAULT_NAME_COLOR)
        base.update(self.edits.get(str(cid),{}))
        return base

    def set_card(self, cid: int, fields: dict):
        if cid not in self.cards:
            raise ModError('ID inexistente')
        clean = check_card_edit(fields)
        baseline = dict(self.cards[cid])
        baseline.setdefault('cor_nome', DEFAULT_NAME_COLOR)
        diff = {}
        for k, v in clean.items():
            if k in NUMERIC:
                if v != int(baseline[k]):
                    diff[k] = v
            elif v != baseline.get(k, ''):
                diff[k] = v
        if diff:
            self.edits[str(cid)] = diff
        else:
            self.edits.pop(str(cid), None)
        self.save()

    def apply_many(self, card_changes: dict[int, dict], effect_changes: dict[int, list] | None = None):
        """Valida tudo antes e salva uma única vez (com apenas um backup).

        Nenhuma edição é gravada em arquivos do PS1. Se salvar falhar, restaura
        o estado anterior em memória, sem perder a possibilidade de retentar.
        """
        staged_edits = {k: dict(v) for k, v in self.edits.items()}
        staged_effects = {k: [dict(v) for v in arr] for k, arr in self.effects.items()}
        for cid, values in card_changes.items():
            if cid not in self.cards:
                raise ModError(f'Carta #{cid} não carregada')
            cleaned = check_card_edit(values)
            base = dict(self.cards[cid])
            base.setdefault('cor_nome', DEFAULT_NAME_COLOR)
            diff = {k: v for k, v in cleaned.items()
                    if (int(base[k]) != v if k in NUMERIC else base.get(k, '') != v)}
            if diff:
                staged_edits[str(cid)] = diff
            else:
                staged_edits.pop(str(cid), None)
        for cid, effects in (effect_changes or {}).items():
            if cid not in self.cards:
                raise ModError(f'Carta #{cid} não carregada para efeitos')
            validated = [check_effect(e) for e in effects]
            if validated:
                staged_effects[str(cid)] = validated
            else:
                staged_effects.pop(str(cid), None)
        old_edits, old_effects = self.edits, self.effects
        self.edits, self.effects = staged_edits, staged_effects
        try:
            self.save()
        except Exception:
            self.edits, self.effects = old_edits, old_effects
            raise

    def attach_art(self, cid: int, path: Path):
        if cid not in self.cards:
            raise ModError('Carta não carregada')
        path = Path(path)
        if path.suffix.lower() != '.png' or not path.is_file():
            raise ModError('Selecione uma imagem PNG válida')
        with path.open('rb') as inp:
            if inp.read(8) != b'\x89PNG\r\n\x1a\n':
                raise ModError('Assinatura PNG inválida')
        folder = self.folder / 'assets' / 'cartas'
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / f'{cid:03d}.png'
        if path.resolve() != dest.resolve():
            shutil.copy2(path,dest)
        self.arts[str(cid)] = str(dest.relative_to(self.folder)).replace('\\','/')
        self.save()

    def add_effect(self, cid: int, entry: dict):
        if cid not in self.cards:
            raise ModError('Carta não carregada')
        effect = check_effect(entry)
        self.effects.setdefault(str(cid),[]).append(effect)
        self.save()

    def remove_effect(self, cid: int, idx: int):
        self.effects[str(cid)].pop(idx)
        if not self.effects[str(cid)]:
            del self.effects[str(cid)]
        self.save()

    def simulate(self, cid: int, event: str, card_override=None, effects_override=None):
        if event not in EVENTS:
            raise ModError('Evento desconhecido')
        stats = card_override if card_override is not None else self.get(cid)
        state = {'ataque':int(stats['ataque']), 'defesa':int(stats['defesa']),
                 'ataque_adversario':1800, 'defesa_adversario':1500,
                 'lp_jogador':8000,'lp_adversario':8000}
        applied = []
        for eff in (effects_override if effects_override is not None else self.effects.get(str(cid), [])):
            if eff['evento'] != event:
                continue
            value = int(eff['valor'])
            action, enemy = eff['acao'], eff['alvo']=='inimigo'
            if action.endswith('_atk'):
                key = 'ataque_adversario' if enemy else 'ataque'
                delta = value if action=='aumentar_atk' else -value
                state[key] = max(0, state[key] + delta)
            elif action.endswith('_def'):
                key = 'defesa_adversario' if enemy else 'defesa'
                delta = value if action=='aumentar_def' else -value
                state[key] = max(0, state[key] + delta)
            elif action in ('dano_lp','cura_lp'):
                key = 'lp_adversario' if enemy else 'lp_jogador'
                state[key] = max(0,min(99999,state[key] + (value if action=='cura_lp' else -value)))
            applied.append(eff)
        return state, applied

    def validate(self):
        issues = []
        for cid, edits in self.edits.items():
            try:
                if int(cid) not in self.cards:
                    raise ModError('ID fora da base')
                check_card_edit(edits)
            except ModError as exc:
                issues.append(f'Carta {cid}: {exc}')
        for cid, arr in self.effects.items():
            for i, item in enumerate(arr,1):
                try:
                    check_effect(item)
                except ModError as exc:
                    issues.append(f'Efeito {cid}/{i}: {exc}')
        orig_fusions = self.folder/'base'/'fusoes.csv'
        if self.cards and not orig_fusions.exists():
            issues.append('Faltam as fusões da base. Importação incompleta!')
        if orig_fusions.exists() and self.metadata.get('base_sha256',{}).get('fusoes') != sha256(orig_fusions):
            issues.append('Arquivo de fusões originais alterado externamente!')
        orig_cards = self.folder/'base'/'cartas.csv'
        if orig_cards.exists() and self.metadata.get('base_sha256',{}).get('cartas') != sha256(orig_cards):
            issues.append('Arquivo-base de cartas alterado externamente!')
        return issues

    def export(self):
        issues = self.validate()
        if issues:
            raise ModError('Exportação bloqueada:\n'+'\n'.join(issues[:12]))
        output = self.folder/'exportacao'
        output.mkdir(parents=True,exist_ok=True)
        changes = []
        for cid in sorted(self.cards):
            if str(cid) in self.edits:
                changes.append({'id':cid, **self.edits[str(cid)]})
        _write_json_atomic(output/'alteracoes_cartas.json', changes)
        _write_json_atomic(output/'efeitos_planejados.json',
                           {'status':'SIMULACAO_APENAS_SEM_PATCH_PS1', 'efeitos_por_carta':self.effects})
        _write_json_atomic(output/'artes_referencia.json',
                           {'status':'REFERENCIA_VISUAL_APENAS_SEM_PATCH_PS1', 'artes':self.arts})
        manifest = {'projeto':self.metadata['nome'], 'gerado':_timestamp(),
                    'fusoes':'ORIGINAIS_PRESERVADAS', 'cartas_editadas':len(changes),
                    'efeitos_planejados':sum(map(len,self.effects.values())),
                    'alerta':'Efeitos e textos NÃO foram implementados no motor PS1 nesta versão',
                    'patch_jogavel':False, 'arquivos': ['alteracoes_cartas.json','efeitos_planejados.json','artes_referencia.json']}
        source = self.folder/'base'/'source_SLUS_014.11'
        if source.exists() and any(any(k in NUMERIC for k in row) for row in changes):
            data = bytearray(source.read_bytes())
            if hashlib.sha256(data).hexdigest() != self.metadata.get('base_sha256',{}).get('slus'):
                raise ModError('Executável original diverge do hash salvo; exportação bloqueada')
            byte_diffs = []
            for row in changes:
                cid = row['id']
                base = self.cards[cid]
                off = STATS_ADDR - EXE_DELTA + (cid - 1) * 4
                before = struct.unpack_from('<I', data, off)[0]
                if f'{before:08X}' != base['valor_hex'].upper():
                    raise ModError(f'Proteção: bytes originais inesperados na carta #{cid}')
                current = self.get(cid)
                raw = (before & 0x80000000) | \
                      ((int(current['tipo_id']) & 31) << 26) | \
                      ((int(current['guardian_1_id']) & 15) << 22) | \
                      ((int(current['guardian_2_id']) & 15) << 18) | \
                      (((int(current['defesa']) // 10) & 511) << 9) | \
                      ((int(current['ataque']) // 10) & 511)
                if raw != before:
                    struct.pack_into('<I', data, off, raw)
                    byte_diffs.append({'carta_id':cid, 'offset':f'0x{off:X}',
                                       'antes':struct.pack('<I',before).hex(),
                                       'depois':struct.pack('<I',raw).hex()})
                level_off = LEVEL_ADDR - EXE_DELTA + cid
                old = data[level_off]
                new = (int(current['atributo_id'])<<4) | int(current['nivel'])
                if old != new:
                    data[level_off] = new
                    byte_diffs.append({'carta_id':cid, 'offset':f'0x{level_off:X}',
                                       'antes':f'{old:02x}', 'depois':f'{new:02x}'})
            build = output/'build_local'
            build.mkdir(exist_ok=True)
            (build/'SLUS_014.11').write_bytes(data)
            _write_json_atomic(output/'mudancas_binarias.json',byte_diffs)
            manifest['arquivos'].extend(['build_local/SLUS_014.11','mudancas_binarias.json'])
            manifest['slus_modificado_sha256'] = hashlib.sha256(data).hexdigest()
            manifest['observacao_executavel'] = ('Executável auxiliar modificado localmente; NÃO é imagem BIN/CUE '
                'jogável e não deve ser distribuído. Ainda faltam empacotamento do disco e testes in-game.')
        _write_json_atomic(output/'manifesto.json',manifest)
        return output, manifest
