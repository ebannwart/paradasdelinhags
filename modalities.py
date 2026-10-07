"""One mutually exclusive modality for every launch, shared by all screens."""
import re
import unicodedata

MODALITIES = ['ME', 'MM', 'Preventiva', 'OP', 'ST', 'PP', 'EX']
LABELS = {'ME': 'Manutenção elétrica', 'MM': 'Manutenção mecânica',
          'Preventiva': 'Manutenção preventiva + reparo geral', 'OP': 'Operação',
          'ST': 'Setup', 'PP': 'Programação sem preventivas', 'EX': 'Externa / demais paradas'}


def plain(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', str(value or ''))
                           if not unicodedata.combining(c)).lower().split())


def effective_type(original, auto_type, override):
    if override is not None: return override
    if auto_type in ('Manutenção Preventiva', 'Reparo Geral'): return auto_type
    text = plain(original)
    if re.search(r'\breparo geral\b|\breforma geral\b|\brg\b', text): return 'Reparo Geral'
    if re.search(r'\bpreventiva\b|\bmp\b', text): return 'Manutenção Preventiva'
    return auto_type


def modality(original, responsible, auto_type, override):
    if effective_type(original, auto_type, override) in ('Manutenção Preventiva', 'Reparo Geral'):
        return 'Preventiva'
    text = plain(original)
    code = text.split('-')[0].strip()
    if 'eletri' in text: return 'ME'
    if 'mecan' in text: return 'MM'
    if code in ('me','el') or responsible == 'Elétrica': return 'ME'
    if code == 'mm' or responsible == 'Mecânica': return 'MM'
    if 'opera' in text or code == 'op' or responsible == 'Operação': return 'OP'
    if 'setup' in text or 'set up' in text or code in ('st','su') or responsible == 'Setup': return 'ST'
    if 'programa' in text or code in ('pp','pr','pm') or responsible == 'Programação': return 'PP'
    return 'EX'


MODALITY_SQL = 'stop_modality(r.responsible_original,r.responsible,r.auto_type,r.type_override)'
TYPE_SQL = 'effective_type(r.responsible_original,r.auto_type,r.type_override)'
