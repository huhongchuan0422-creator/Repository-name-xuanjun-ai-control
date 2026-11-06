"""First-party license layout mapper. No inference, persistence or authority.

Geometry hypotheses rotate coordinates, never images or model inference. They
are layout heuristics, not document-orientation/authenticity guarantees. Every
returned field requires explicit human review, irrespective of OCR confidence.
"""
import math
from bisect import bisect_left
import re

VERSION = 'community.license-layout.v1-candidate'
LABELS = {
    'company_name': ('个体工商户名称', '企业名称', '名称'),
    'credit_code': ('统一社会信用代码', '社会信用代码'),
    'legal_representative': ('法定代表人', '经营者', '负责人'),
    'registered_address': ('经营场所', '住所', '地址'),
    'business_scope': ('经营范围',),
}
STOP_LABELS = ('注册资本', '成立日期', '营业期限', '登记机关', '发照日期', '组成形式', '类型')
ALIASES = {label: key for key, labels in LABELS.items() for label in labels}
ALIASES.update({label: None for label in STOP_LABELS})
# Spaces between printed label characters are common. Do not strip spaces in values.
PATTERN = re.compile('|'.join('\\s*'.join(map(re.escape, label)) for label in sorted(ALIASES, key=len, reverse=True)))
CREDIT = re.compile(r'(?<![0-9A-Z])[0-9A-HJ-NP-RTUWXY]{2}[0-9]{6}[0-9A-HJ-NP-RTUWXY]{10}(?![0-9A-Z])')


def normalize_layout(raw):
    """Keep aligned text/score/quadrilateral and original index; never zip-truncate."""
    get = raw.get if isinstance(raw, dict) else lambda k, d=None: getattr(raw, k, d)
    texts, scores, boxes = get('txts'), get('scores'), get('boxes')
    if texts is None and scores is None:
        return []
    if texts is None or scores is None or len(texts) != len(scores):
        raise ValueError('LICENSE_OCR_RESULT_ALIGNMENT_INVALID')
    if boxes is not None and len(boxes) != len(texts):
        raise ValueError('LICENSE_OCR_RESULT_ALIGNMENT_INVALID')
    rows = []
    for i, (text, score) in enumerate(zip(texts, scores)):
        score = float(score)
        if not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError('LICENSE_OCR_SCORE_INVALID')
        box = None if boxes is None else boxes[i]
        if box is not None:
            try:
                if len(box) != 4 or any(len(p) != 2 for p in box):
                    raise ValueError('unusable geometry')
                box = [[float(x), float(y)] for x, y in box]
                if not all(math.isfinite(v) for p in box for v in p):
                    raise ValueError('unusable geometry')
                area = abs(sum(box[j][0]*box[(j+1)%4][1]-box[(j+1)%4][0]*box[j][1] for j in range(4)))
                if area == 0:
                    raise ValueError('unusable geometry')
            except (TypeError, ValueError, OverflowError):
                # One unusable quad must not fail other text in the document.
                # Keep its aligned text/score; never guess a neighbour for it.
                box = None
        rows.append({'text': str(text).strip(), 'confidence': score, 'box': box, 'source_index': i})
    return rows


def _parts(text):
    matches = list(PATTERN.finditer(text))
    # A keyword inside a value is not itself a field label. An initial label is
    # needed. Later labels must be delimited, not embedded in a company name.
    if not matches or text[:matches[0].start()].strip(' ：:'):
        return []
    # Require an explicit end boundary: a company value beginning with a field
    # keyword is not a label merely because of its spelling.
    def end_boundary(m):
        return m.end() == len(text) or text[m.end()] in ' \t:：'
    if not end_boundary(matches[0]):
        return []
    matches = [matches[0]] + [m for m in matches[1:] if end_boundary(m) and
        ((m.start() and text[m.start()-1] in ' \t;；,，') or text[m.end():].lstrip().startswith((':','：')))]
    out = []
    for i, m in enumerate(matches):
        label = re.sub(r'\s+', '', m.group())
        tail = text[m.end():matches[i+1].start() if i+1 < len(matches) else len(text)].lstrip(' ：:').rstrip()
        if i+1 < len(matches):
            tail = tail.rstrip(' ;；,，')
        out.append((ALIASES[label], tail))
    return out


def _bounds(box, turn):
    pts = []
    for x, y in box:
        for unused in range(turn):
            x, y = -y, x
        pts.append((x, y))
    xs, ys = zip(*pts)
    return (min(xs), min(ys), max(xs), max(ys))


def _h(node): return max(node['b'][3]-node['b'][1], 1.0)
def _cy(node): return (node['b'][1]+node['b'][3])/2

def _join_texts(values):
    out = ''
    for text in values:
        text = text.strip()
        if out and text and out[-1].isascii() and out[-1].isalnum() and text[0].isascii() and text[0].isalnum():
            out += ' '
        out += text
    return out


def _candidate(key, nodes, value=None):
    value = _join_texts(n['text'] for n in nodes) if value is None else value
    value = value.strip().lstrip('：:')
    if not value:
        return None
    if key == 'credit_code':
        match = CREDIT.search(value.upper().replace(' ', ''))
        if not match:
            return None
        value = match.group()
    return {'value': value, 'confidence': round(min(n['confidence'] for n in nodes), 4),
            'source_lines': sorted({n['source_index'] for n in nodes}), 'requires_review': True}


def _hypothesis(rows, turn):
    nodes = [dict(n, b=_bounds(n['box'], turn) if n['box'] is not None else None,
                  parts=_parts(n['text'])) for n in rows]
    labels = [n for n in nodes if n['parts']]
    unplaced_labels = any(n['b'] is None and any(not value for key,value in n['parts']) for n in labels)
    values = [n for n in nodes if not n['parts'] and n['text'] and n['b'] is not None]
    # Barrier queries depend only on geometry, not duplicate text labels.
    # Preserve every source node/candidate while sharing equivalent barriers.
    barrier_nodes = {n['b']: n for n in labels if n['b'] is not None}
    values_by_y = sorted(values, key=lambda n:(n['b'][1],n['b'][0]))
    values_by_x = sorted(values, key=lambda n:n['b'][0])
    candidates = {}
    quality = 0.0
    for label in labels:
        for key, inline in label['parts']:
            if key is None:
                continue
            candidates.setdefault(key, [])
            if label['b'] is None or (inline and (len(label['parts']) > 1 or unplaced_labels)):
                item = _candidate(key, [label], inline) if inline else None
                if item: candidates[key].append(item)
                continue
            left, top, right, bottom = label['b']
            height = _h(label)
            # Document line coordinates must be approximately horizontal. This
            # is a hypothesis-ranking signal, not an upload/acceptance limit.
            if right-left < height*.8:
                item = _candidate(key, [label], inline) if inline else None
                if item: candidates[key].append(item)
                continue
            blockers = [n for b,n in barrier_nodes.items() if b != label['b']]
            same = [n for n in values_by_x if n['b'][0] >= right-height*.15
                    and abs(_cy(n)-_cy(label)) <= max(height, _h(n))*.65]
            barrier_xs = sorted(z['b'][0] for z in blockers if
                abs(_cy(z)-_cy(label)) <= max(height,_h(z))*.65)
            selected = [dict(label,text=inline)] if inline else []
            extended = False
            for n in same:
                start = right if not selected else selected[-1]['b'][2]
                barrier_index = bisect_left(barrier_xs, start-height*.1)
                if barrier_index < len(barrier_xs) and barrier_xs[barrier_index] < n['b'][0]:
                    break
                if selected and n['b'][0]-start > 2.5*max(height,_h(n)):
                    break
                selected.append(n); extended = True
            # A value directly below its own label is supported only when close
            # and aligned; array order is never used as evidence.
            if not selected:
                below = [n for n in values if 0 <= n['b'][1]-bottom <= height*1.6
                         and abs(n['b'][0]-left) <= height*.8]
                below.sort(key=lambda n:(n['b'][1],n['b'][0]))
                if below:
                    n = below[0]
                    if not any(bottom <= z['b'][1] <= n['b'][1] and abs(z['b'][0]-left)<height for z in blockers):
                        selected = [n]
            if not selected:
                continue
            first = selected[0]
            # Multiline text remains within the field's column. Other labels
            # form barriers, including labels whose values are not extracted.
            if key in ('business_scope', 'registered_address'):
                anchor = first['b'][2] if inline else first['b'][0]
                boundary = min([z['b'][0] for z in blockers if z['b'][0] > anchor
                                and abs(_cy(z)-_cy(label)) <= height] or [float('inf')])
                last = max(n['b'][3] for n in selected)
                selected_indices = {n['source_index'] for n in selected}
                stop_y = min([_cy(z) for z in blockers if _cy(label) < _cy(z)
                              and left-height*.5 <= z['b'][0] < boundary] or [float('inf')])
                for n in values_by_y:
                    if n['source_index'] in selected_indices or n['b'][1] < last-height*.2:
                        continue
                    if n['b'][1]-last > height*1.8:
                        break
                    if not (left-height*.5 <= n['b'][0] <= anchor+height and n['b'][2]<boundary):
                        continue
                    if stop_y <= _cy(n)+height*.6:
                        break
                    selected.append(n); selected_indices.add(n['source_index']); last=n['b'][3]; extended = True
            item = _candidate(key, [label]+selected, _join_texts(n['text'] for n in selected))
            if item:
                candidates[key].append(item)
                gap = max(0,first['b'][0]-right)/height + abs(_cy(first)-_cy(label))/height
                if not inline or extended:
                    quality += 10 + 1/(1+gap)
    return candidates, quality


def extract_license_fields(rows):
    """Map suggestions only; conflicts have no arbitrary primary value."""
    hypotheses = [_hypothesis(rows, turn) for turn in range(4)]
    best = max(score for fields, score in hypotheses)
    winners = [i for i, (fields, score) in enumerate(hypotheses) if abs(score-best)<1e-8]
    merged = {}
    for index in winners:
        for key, items in hypotheses[index][0].items():
            by_value = merged.setdefault(key, {})
            for item in items:
                old = by_value.get(item['value'])
                if old is None or old['confidence'] < item['confidence']:
                    by_value[item['value']] = item
    fields = {}
    for key, by_value in merged.items():
        items = sorted(by_value.values(), key=lambda c:c['value'])
        warning = 'LAYOUT_VALUE_MISSING' if not items else 'CONFLICTING_CANDIDATES' if len(items)>1 else None
        warnings = [warning] if warning else []
        if any(n['box'] is None and any(k == key for k, unused in _parts(n['text'])) for n in rows):
            warnings.append('LAYOUT_GEOMETRY_UNAVAILABLE')
        fields[key] = {'value': items[0]['value'] if len(items)==1 else '',
                       'confidence': items[0]['confidence'] if len(items)==1 else 0.0,
                       'requires_review': True, 'source':'ocr', 'candidates':items,
                       'warnings': warnings, 'mapping_version':VERSION}
    return {'document_type':'business_license','fields':fields,'requires_human_confirmation':True,
            'authenticity_verified':False,'layout_coordinate_turns':winners,'mapping_version':VERSION}
