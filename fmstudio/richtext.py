"""Anotações de cores e ícones usadas pelo editor e pelo exportador PS1."""
from __future__ import annotations
import re
from .expanded import resolve_references
# Códigos F8 documentados do jogo. Native icons 0x00..0x28.
NATIVE_ICONS = {'Dragon':0x00, 'Spellcaster':0x01, 'Zombie':0x02,
    'Warrior':0x03, 'Beast-Warrior':0x04, 'Beast':0x05, 'Winged Beast':0x06,
    'Fiend':0x07, 'Fairy':0x08, 'Insect':0x09, 'Dinosaur':0x0A,
    'Reptile':0x0B, 'Fish':0x0C, 'Sea Serpent':0x0D, 'Machine':0x0E,
    'Thunder':0x0F, 'Aqua':0x10, 'Pyro':0x11, 'Rock':0x12, 'Plant':0x13,
    'Magic':0x14, 'Trap':0x15, 'Ritual':0x16, 'Equip':0x17,
    'Mars':0x18,'Jupiter':0x19,'Saturn':0x1A,'Uranus':0x1B,
    'Pluto':0x1C,'Neptune':0x1D,'Mercury':0x1E,'Sun':0x1F,
    'Moon':0x20,'Venus':0x21,'Cross':0x22,'Triangle':0x23,
    'Square':0x24,'Circle':0x25,'Star':0x26}
TEXT_COLORS = {'branco':(0,'#EFEFEF'),'amarelo':(1,'#F1D34D'),
    'azul':(2,'#77B8FF'),'verde':(3,'#81E1A0'), 'cinza':(4,'#B4B6BE'),
    'laranja':(5,'#F9AA52'), 'vermelho':(6,'#FE737A')}
CUSTOM_ICONS={'perfurar':'Perfurante','ataque_2x':'2x ataque',
    'ataque_3x':'3x ataque','nao_bloqueavel':'Não bloqueável',
    'infinito':'Sem limite no deck','anti_trap':'Imune a trap',
    'anti_magia':'Imune a mágicas','indestrutivel':'Indestrutível',
    'god':'God', 'ataque_primeiro_turno':'Ataca no primeiro turno',
    'vinculo_vida':'Vínculo com Vida (coração e espada)',
    'restaurar_lp':'Restaurar LP (coração)'}
TOKEN = re.compile(r'(\{f8 0[AB] [0-9A-Fa-f]{2}\}|\{icon:[a-z0-9_]+\}|\{color:[a-z]+\}|\{/color\}|\{card:[0-9]+\})')

def tokens(value: str, cards=None):
    """[(text, color, icon_name)] para prévia; ícones nativos não são embutidos em fontes locais."""
    color=TEXT_COLORS['branco'][1]; out=[]
    for chunk in TOKEN.split(value):
        if not chunk: continue
        if chunk.startswith('{color:'):
            color=TEXT_COLORS.get(chunk[7:-1],TEXT_COLORS['branco'])[1]
        elif chunk=='{/color}': color=TEXT_COLORS['branco'][1]
        elif chunk.startswith('{f8 0A '):
            n=int(chunk[-3:-1],16)
            color=next((x[1] for x in TEXT_COLORS.values() if x[0]==n),color)
        elif chunk.startswith('{f8 0B '):
            code=int(chunk[-3:-1],16)
            name=next((k for k,v in NATIVE_ICONS.items() if v==code),f'ícone 0x{code:02X}')
            out.append(('',color,'nativo:'+name))
        elif chunk.startswith('{icon:'):
            name=chunk[6:-1]
            out.append(('',color,name if name in CUSTOM_ICONS else 'desconhecido:'+name))
        elif chunk.startswith('{card:'):
            out.append((resolve_references(chunk,cards or {}),color,None))
        else:
            out.append((chunk,color,None))
    return out

def native_text_only(text: str) -> tuple[str,list[str]]:
    """Converte cores conhecidas para F8; avisa sobre tokens ainda não suportados pelo PS1."""
    warnings=[]
    def conv(m):
        ch=m.group(0)
        if ch.startswith('{color:'):
            name=ch[7:-1]
            if name not in TEXT_COLORS: warnings.append('cor desconhecida '+name);return ch
            return f'{{f8 0A {TEXT_COLORS[name][0]:02X}}}'
        if ch=='{/color}': return '{f8 0A 00}'
        if ch.startswith('{icon:'):
            name=ch[6:-1]
            if name in CUSTOM_ICONS: warnings.append('ícone personalizado requer patch de fontes do PS1: '+name)
            else: warnings.append('ícone desconhecido '+name)
        if ch.startswith('{card:'): warnings.append('referência a carta exige substituição antes de compilar texto')
        return ch
    return TOKEN.sub(conv,text),warnings
