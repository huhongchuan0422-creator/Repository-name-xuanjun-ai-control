"""Printed bank-card suggestions only; no account/bank ownership verification.

Consumes normalize_layout rows. Never infers holder, branch or missing digits.
Length, checksum and confidence are review hints, not acceptance gates.
"""
import re
from scripts.community_license_layout import _candidate, _extract_fields

VERSION = 'community.bank-card-layout.v1-candidate'
ALIASES = {'银行卡号': 'account_number', '卡号': 'account_number', '账号': 'account_number',
           '账户号码': 'account_number', '银行名称': 'account_bank', '发卡银行': 'account_bank',
           '有效期': None, '有效期限': None, '服务热线': None, '客服电话': None,
           '电话': None, '姓名': None, '持卡人': None, '开户支行': None, '支行': None}
RESERVED_LABELS = ('安全码', '验证码', '卡验证码', '密码', '个人识别码',
                   'CVV', 'CVC', 'CVV2', 'CVC2', 'CID', 'PIN',
                   'VALID THRU', 'VALID UNTIL', 'EXPIRY', 'EXP',
                   '有效期', '有效期限', '服务热线', '客服电话', '电话')
for _label in RESERVED_LABELS:
    for _variant in (_label, _label.lower(), _label.title()):
        ALIASES[re.sub(r'\s+', '', _variant)] = None
PATTERN = re.compile('|'.join('\\s*'.join(map(re.escape, label)) for label in sorted(ALIASES, key=len, reverse=True)))
# These are textual suggestions, not a registry or a BIN-to-issuer lookup.
PRINTED_BANK = re.compile(r'[\u4e00-\u9fffA-Za-z·（）()]+(?:银行|信用合作社|信用社)(?:股份有限公司|有限公司)?')
NUMBER = re.compile(r'[0-9０-９*＊xX×●•][0-9０-９*＊xX×●•\s\-－]*')


def _bank_candidate(key, nodes, value=None):
    item = _candidate(key, nodes, value)
    if not item:
        return None
    printed = item['value']
    if key == 'account_number':
        if not NUMBER.fullmatch(printed) or not any(c.isdecimal() for c in printed):
            return None
        value = re.sub(r'[\s\-－]', '', printed).translate(str.maketrans('０１２３４５６７８９', '0123456789'))
        item.update(value=value, printed_value=printed)
        warnings = ['ACCOUNT_VALIDITY_NOT_VERIFIED']
        if not value.isascii() or not value.isdigit():
            warnings.append('MASKED_OR_INCOMPLETE_NUMBER')
        else:
            if not 12 <= len(value) <= 19:
                warnings.append('UNUSUAL_NUMBER_LENGTH')
            digits = [int(c) for c in value[::-1]]
            total = sum((d*2-9 if d*2>9 else d*2) if i % 2 else d for i,d in enumerate(digits))
            if total % 10:
                warnings.append('LUHN_CHECK_MISMATCH')
        item['warnings'] = warnings
    else:
        # Require a whole printed name, never convert a logo/BIN to an issuer.
        if not PRINTED_BANK.fullmatch(printed):
            return None
        item['warnings'] = ['PRINTED_BANK_NAME_NOT_VERIFIED']
    item['value_boxes'] = [n['box'] for n in nodes if n['box'] is not None]
    return item


def extract_bank_card_fields(rows, coordinate_turns=None):
    """Compatible with four pixel rotations: caller passes coordinate_turns=(0,).

    Standalone numeric rows remain ambiguous candidates, including short/masked
    ones. No row-order concatenation: split unrelated OCR rows cannot manufacture
    an account. Unknown names/fragments stay in unresolved_rows for manual entry.
    """
    prepared = []
    for row in rows:
        text = row['text']; match = PATTERN.match(text)
        if match and match.end() < len(text) and text[match.end()] not in ' ：:\t':
            text = text[:match.end()] + '：' + text[match.end():]
        prepared.append(dict(row, text=text))
    turns = (0,1,2,3) if coordinate_turns is None else tuple(coordinate_turns)
    if not turns or any(type(t) is not int or t not in range(4) for t in turns):
        raise ValueError('BANK_CARD_COORDINATE_TURNS_INVALID')
    # Resolve printed excluded labels using the SAME geometry mapper. This
    # reserves their separate value boxes, without filtering numbers by length.
    reserved_names = {re.sub(r'\s+', '', v) for label in RESERVED_LABELS
                      for v in (label, label.lower(), label.title())}
    reserved_aliases = {label: ('_excluded' if label in reserved_names else key)
                        for label, key in ALIASES.items()}
    reserved = _extract_fields(prepared, 'bank_card', reserved_aliases, PATTERN,
                               _candidate, (), turns, VERSION)
    excluded = {i for c in reserved['fields'].get('_excluded', {}).get('candidates', [])
                for i in c['source_lines']}
    excluded.update(row['source_index'] for row in prepared
                    if (m := PATTERN.match(row['text'])) and
                    re.sub(r'\s+', '', m.group()) in reserved_names)
    safe_rows = [row for row in prepared if row['source_index'] not in excluded]
    result = _extract_fields(safe_rows, 'bank_card', ALIASES, PATTERN,
                             _bank_candidate, (), turns, VERSION)
    used = set()
    for key in ('account_number', 'account_bank'):
        field = result['fields'].setdefault(key, {'candidates': [], 'requires_review': True,
            'source': 'ocr', 'mapping_version': VERSION})
        by_value = {c['value']: c for c in field['candidates']}
        for row in safe_rows:
            if PATTERN.match(row['text']):
                continue
            item = _bank_candidate(key, [row])
            if item:
                if key == 'account_number':
                    item['warnings'].append('UNLABELLED_NUMBER_REQUIRES_REVIEW')
                if row['box'] is None:
                    item['warnings'].append('LAYOUT_GEOMETRY_UNAVAILABLE')
                old = by_value.get(item['value'])
                if old is None or item['confidence'] > old['confidence']:
                    by_value[item['value']] = item
        candidates = sorted(by_value.values(), key=lambda c:c['value'])
        only = candidates[0] if len(candidates) == 1 else None
        warnings = [] if only else ['CONFLICTING_CANDIDATES' if candidates else 'LAYOUT_VALUE_MISSING']
        for item in candidates:
            used.update(item['source_lines'])
            warnings.extend(w for w in item.get('warnings', []) if w not in warnings)
        field.update(candidates=candidates, value=only['value'] if only else '',
                     confidence=only['confidence'] if only else 0.0, warnings=warnings,
                     source_lines=only['source_lines'] if only else [],
                     source_boxes=only['source_boxes'] if only else [],
                     value_boxes=only.get('value_boxes', []) if only else [])
    result['unresolved_rows'] = [dict(row) for row in rows if row['source_index'] not in used and row['source_index'] not in excluded]
    result['account_validity_verified'] = False
    result['bank_identity_verified'] = False
    return result
