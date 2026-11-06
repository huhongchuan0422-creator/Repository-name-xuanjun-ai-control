"""Offline license-address lookup. No I/O other than reading the bundled directory.

Use resolve_license_region for draft feedback. Call validate only at final submission.
The address is never rewritten, retained in results, transmitted, or truncated.
"""
import json
import re
from pathlib import Path

LICENSE_ADDRESS_PATH = 'subject_info.business_license_info.license_address'
BIZ_ADDRESS_CODE_PATH = 'business_info.sales_info.biz_store_info.biz_address_code'
_AREAS = json.loads(Path(__file__).with_name('community_license_region_areas.json').read_text(encoding='utf-8'))
DIRECTORY = {key: _AREAS[key] for key in ('source_url', 'observed_at_utc', 'xlsx_sha256')}
DIRECTORY.update(row_count=len(_AREAS['rows']), effective_version=None)
# ECMAScript whitespace set, deliberately not Python's broader Unicode \\s.
_FORMAT = re.compile('[\\t\\n\\v\\f\\r \\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000\\ufeff,，、]')
_PREFIX = re.compile(r'^(?:营业执照注册地址|注册地址|经营场所|住所|地址)[:：]')
_COUNTRY = re.compile(r'^(?:中华人民共和国|中国)')
_ROOT = {}
_BY_CODE = {}
_PROVINCES, _CITIES, _DISTRICTS = {}, {}, {}
_DISTRICTS_BY_CITY = {}


def _normalize(value):
    return _FORMAT.sub('', value).replace('（', '(').replace('）', ')')


def _add_path(names, row):
    node = _ROOT
    for char in _normalize(''.join(names)):
        node = node.setdefault(char, {})
    rows = node.setdefault(None, [])
    if row not in rows:
        rows.append(row)


for _source in _AREAS['rows']:
    _row = tuple(_source)
    if not re.fullmatch('[0-9]{6}', _row[0]) or _row[0] in _BY_CODE:
        raise ValueError('INVALID_OFFICIAL_REGION_DIRECTORY')
    _BY_CODE[_row[0]] = _row
    _PROVINCES[_row[1]] = None
    _CITIES[_row[2]] = None
    _DISTRICTS[_row[3]] = None
    _DISTRICTS_BY_CITY.setdefault((_row[1], _row[2]), []).append(_row[3])
    _add_path(_row[1:], _row)
    if _row[1] == _row[2]:
        _add_path([_row[1], _row[3]], _row)
    if _row[2] == _row[3]:
        _add_path([_row[1], _row[2]], _row)
    if _row[2] != _row[3]:
        _add_path(_row[2:], _row)


def _match_at(text, start):
    node, match = _ROOT, None
    for at in range(start, len(text)):
        node = node.get(text[at])
        if node is None:
            break
        if node.get(None):
            match = (node[None], at + 1)
    return match


def _failure(reason, message):
    return dict(ok=False, reason=reason, code=None, row=None, correctionStep=0, message=message)


def _incomplete():
    return _failure('INCOMPLETE_ADDRESS', '营业执照地址信息不足以唯一确定地区，请返回第一步核对原地址；保持执照真实内容，暂不填写猜测编码。')


def _mismatch():
    return _failure('DIRECTORY_MISMATCH', '营业执照地址与现有地区目录未匹配。请核对第一步原地址；地址正确时需核对或更新地区目录，不要改成旧地名。')


def resolve_license_region(address):
    """Return a JS-compatible result dictionary; never guess a missing code."""
    if not isinstance(address, str):
        return _failure('INVALID_ADDRESS', '请返回第一步填写或核对营业执照地址。')
    text = _normalize(address)
    if not text:
        return _incomplete()
    text = _COUNTRY.sub('', _PREFIX.sub('', text, count=1), count=1)
    if not text:
        return _incomplete()
    match = _match_at(text, 0)
    if not match:
        province = next((name for name in _PROVINCES if text.startswith(name)), None)
        if not province:
            if any(text.startswith(name) for names in (_CITIES, _DISTRICTS) for name in names):
                return _incomplete()
            return _failure('UNRECOGNIZED_ADDRESS', '未能识别营业执照地址的完整行政区信息，请返回第一步核对原地址；地址正确时需核对地区目录，不要填写猜测值。')
        rest = text[len(province):]
        if not rest:
            return _incomplete()
        rows = [row for row in _BY_CODE.values() if row[1] == province]
        city = next((row[2] for row in rows if rest.startswith(row[2])), None)
        if city and rest == city:
            return _incomplete()
        if not city and province != rows[0][2] and any(rest.startswith(row[3]) for row in rows):
            return _incomplete()
        return _mismatch()
    matched_rows, end = match
    if len(matched_rows) != 1:
        return _failure('AMBIGUOUS_ADDRESS', '营业执照地址对应多个地区，请返回第一步核对，暂不填写地区编码。')
    row = matched_rows[0]
    tail = text[end:]
    alternative = re.sub(r'^(?:或者|或|/|;|；|\||至|及|与)+', '', tail)
    district_names = _DISTRICTS if alternative != tail else _DISTRICTS_BY_CITY[(row[1], row[2])]
    if any(name != row[3] and alternative.startswith(name) for name in district_names):
        return _failure('AMBIGUOUS_ADDRESS', '营业执照地址中出现不同地区，请返回第一步核对，暂不填写地区编码。')
    for at in range(end, len(text)):
        if text[at] not in _ROOT:
            continue
        other = _match_at(text, at)
        if other and any(item[0] != row[0] for item in other[0]):
            return _failure('AMBIGUOUS_ADDRESS', '营业执照地址中出现不同地区，请返回第一步核对，暂不填写地区编码。')
    names = [name for index, name in enumerate(row[1:]) if not index or name != row[index]]
    return dict(ok=True, reason='EXACT_DIRECTORY_MATCH', code=row[0], row=list(row), label=' / '.join(names), correctionStep=None, message='已依据第一步营业执照地址匹配地区。')


def region_for_exact_code(code):
    row = _BY_CODE.get(code) if isinstance(code, str) else None
    return list(row) if row else None


class RegionValidationError(ValueError):
    """Stable submission error. result carries the structured reason, without address."""
    def __init__(self, result):
        self.result = dict(result)
        self.reason = result['reason']
        self.correctionStep = result['correctionStep']
        super().__init__(result['message'])


def validate(address, code):
    """Return exact result or raise RegionValidationError; not a draft-save gate.

    Code must be an unchanged six-character code from the bundled dictionary,
    and must agree with the exact address result. No coercion or whitespace trim.
    """
    if region_for_exact_code(code) is None:
        raise RegionValidationError(_failure('INVALID_REGION_CODE', '地区编码为空或不在现有地区目录中，请依据第一步营业执照地址重新匹配。'))
    result = resolve_license_region(address)
    if not result['ok']:
        raise RegionValidationError(result)
    if code != result['code']:
        raise RegionValidationError(_failure('REGION_CODE_MISMATCH', '地区编码与第一步营业执照地址不一致，请重新匹配后提交。'))
    return result
