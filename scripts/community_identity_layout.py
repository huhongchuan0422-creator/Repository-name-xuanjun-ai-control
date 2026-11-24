"""Geometry-only suggestions for both identity-card sides.

No OCR model, network, writeback, authentication or authenticity inference.
OCR array order is never a substitute for label/value geometry.
"""
import datetime
import re
from scripts.community_license_layout import _candidate, _extract_fields

VERSION = 'community.identity-layout.v1-candidate'
FRONT = {
    '姓名': 'id_name',
    '公民身份号码': 'id_number', '公民身份证号码': 'id_number',
    '身份证号码': 'id_number', '身份号码': 'id_number',
    '住址': 'registered_address', '住所': 'registered_address', '地址': 'registered_address',
    '性别': None, '民族': None, '出生': None, '出生日期': None,
}
BACK = {
    '签发机关': 'issuing_authority', '签发机构': 'issuing_authority',
    '有效期限': 'validity_period', '有效期': 'validity_period',
    '中华人民共和国': None, '居民身份证': None,
}
ID_NUMBER = re.compile(r'(?<![0-9])[1-9][0-9]{16}[0-9Xx](?![0-9])')
DATE = re.compile(r'(?<!\d)(\d{4})\s*[.\-/年]\s*(\d{1,2})\s*[.\-/月]\s*(\d{1,2})\s*日?(?!\d)')


def _identity_candidate(key, nodes, value=None):
    item = _candidate(key, nodes, value)
    if item and key == 'id_number':
        match = ID_NUMBER.search(re.sub(r'\s+', '', item['value']))
        if match is None:
            return None
        item['value'] = match.group().upper()
    return item


def _date_candidates(field):
    output = {'valid_from': [], 'valid_to': []}
    for candidate in field.get('candidates', []):
        value = candidate['value']
        matches = list(DATE.finditer(value))
        dates = []
        for match in matches:
            try:
                dates.append(datetime.date(*(int(v) for v in match.groups())).isoformat())
            except ValueError:
                dates.append(None)
        if len(dates) == 2 and all(dates):
            values = {'valid_from': dates[0], 'valid_to': dates[1]}
        elif len(dates) == 1 and dates[0] and '长期' in value[matches[0].end():]:
            values = {'valid_from': dates[0], 'valid_to': '长期'}
        else:
            # A lone date without a range/long-term endpoint cannot identify
            # whether it is the start or end. Keep the raw candidate for review.
            continue
        for key, val in values.items():
            output[key].append(dict(candidate, value=val))
    return output


def extract_identity_fields(rows, document_type='id_front', coordinate_turns=None):
    if document_type not in ('id_front', 'id_back'):
        raise ValueError('UNSUPPORTED_DOCUMENT_TYPE')
    aliases = FRONT if document_type == 'id_front' else BACK
    pattern = re.compile('|'.join('\\s*'.join(map(re.escape, label))
        for label in sorted(aliases, key=len, reverse=True)))
    # Identity-card printing often joins a short label and value with no space.
    # Insert a parsing separator only; do not change any recognized value.
    prepared = []
    for row in rows:
        text = row['text']; match = pattern.match(text)
        if match and match.end() < len(text) and text[match.end()] not in ' ：:\t':
            text = text[:match.end()] + '：' + text[match.end():]
        prepared.append(dict(row, text=text))
    result = _extract_fields(prepared, document_type, aliases, pattern,
        _identity_candidate, ('registered_address',), coordinate_turns, VERSION)
    if document_type == 'id_back':
        raw = result['fields'].pop('validity_period', {})
        dates = _date_candidates(raw)
        for key, candidates in dates.items():
            by_value = {item['value']: item for item in candidates}
            unique = list(by_value.values())
            item = unique[0] if len(unique) == 1 else None
            result['fields'][key] = {
                'value': item['value'] if item else '',
                'confidence': item['confidence'] if item else 0.0,
                'requires_review': True, 'source': 'ocr', 'candidates': unique,
                'warnings': [] if item else ['CONFLICTING_CANDIDATES' if unique else 'DATE_RANGE_UNRESOLVED'],
                'source_lines': item['source_lines'] if item else [],
                'source_boxes': item['source_boxes'] if item else [],
                'value_boxes': item.get('value_boxes', []) if item else [],
                'mapping_version': VERSION,
            }
        if raw and not all(result['fields'][k]['value'] for k in dates):
            result['unresolved_validity_candidates'] = raw.get('candidates', [])
    return result
