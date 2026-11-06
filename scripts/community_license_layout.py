"""First-party license layout mapper. No inference, persistence or authority.

Geometry hypotheses rotate coordinates, never images or model inference. They
are layout heuristics, not document-orientation/authenticity guarantees. Every
returned field requires explicit human review, irrespective of OCR confidence.
"""
import math
from bisect import bisect_left
import re

VERSION = 'community.license-layout.v2-no-scope-candidate'
LABELS = {
    'company_name': ('个体工商户名称', '企业名称', '名称'),
    'credit_code': ('统一社会信用代码', '社会信用代码'),
    'legal_representative': ('法定代表人', '经营者', '负责人'),
    'registered_address': ('经营场所', '住所', '地址'),
}
# Excluded from OCR targets by user request; keep its label as a barrier so
# neighbouring fields cannot borrow paragraph text. No historical data changes.
STOP_LABELS = ('经营范围', '注册资本', '成立日期', '营业期限', '登记机关', '发照日期', '组成形式', '类型')
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


def _parts(text, aliases=None, pattern=None):
    aliases = ALIASES if aliases is None else aliases
    pattern = PATTERN if pattern is None else pattern
    matches = list(pattern.finditer(text))
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
        out.append((aliases[label], tail))
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
            'source_lines': sorted({i for n in nodes for i in n.get('source_indices', [n['source_index']])}),
            'source_boxes': [dict(source_index=i, box=b) for n in nodes
                for i,b in n.get('source_boxes', [(n['source_index'], n['box'])]) if b is not None],
            'requires_review': True}


# Printed boxes/check marks can be detected together with a label fragment.
# Remove these only when recognizing a complete known label; never clean values.
LABEL_DECORATIONS = '☐☑☒□■▢✓✔√：:'


def _label_fragment(text):
    return re.sub(r'\s+', '', text).strip(LABEL_DECORATIONS)


def _label_nodes(rows, turn, aliases, pattern):
    nodes = [dict(n, b=_bounds(n['box'], turn) if n['box'] is not None else None,
                  parts=_parts(n['text'], aliases, pattern)) for n in rows]
    for node in nodes:
        fragment = _label_fragment(node['text'])
        if not node['parts'] and fragment in aliases:
            node['parts'] = [(aliases[fragment], '')]
    # Join exact printed label fragments using geometry, not OCR array order.
    # This does not repair misspelled labels or invent missing characters.
    used = set()
    combined = []
    for label in sorted(aliases, key=len, reverse=True):
        for first in nodes:
            text = _label_fragment(first['text'])
            if first['source_index'] in used or first['parts'] or first['b'] is None or not text or not label.startswith(text) or text == label:
                continue
            chain = [first]
            while text != label:
                last = chain[-1]
                choices = [n for n in nodes if n['source_index'] not in used
                    and n not in chain and not n['parts'] and n['b'] is not None
                    and -min(_h(first),_h(n))*.15 <= n['b'][0]-last['b'][2] <= 3*max(_h(first),_h(n))
                    and abs(_cy(n)-_cy(first)) <= min(_h(first),_h(n))*.45
                    and _label_fragment(n['text']) and label.startswith(text+_label_fragment(n['text']))]
                if not choices:
                    break
                nxt = min(choices, key=lambda n:n['b'][0])
                chain.append(nxt); text += _label_fragment(nxt['text'])
            if text == label:
                used.update(n['source_index'] for n in chain)
                bounds = (min(n['b'][0] for n in chain), min(n['b'][1] for n in chain),
                          max(n['b'][2] for n in chain), max(n['b'][3] for n in chain))
                combined.append(dict(first, text=label, b=bounds, parts=[(aliases[label], '')],
                    confidence=min(n['confidence'] for n in chain),
                    source_indices=[n['source_index'] for n in chain],
                    source_boxes=[(n['source_index'],n['box']) for n in chain]))
    return [n for n in nodes if n['source_index'] not in used] + combined


def _hypothesis(rows, turn, aliases=None, pattern=None, candidate_fn=None,
                multiline=('registered_address',)):
    aliases = ALIASES if aliases is None else aliases
    pattern = PATTERN if pattern is None else pattern
    candidate_fn = _candidate if candidate_fn is None else candidate_fn
    nodes = _label_nodes(rows, turn, aliases, pattern)
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
                item = candidate_fn(key, [label], inline) if inline else None
                if item: candidates[key].append(item)
                continue
            left, top, right, bottom = label['b']
            height = _h(label)
            # Document line coordinates must be approximately horizontal. This
            # is a hypothesis-ranking signal, not an upload/acceptance limit.
            if right-left < height*.8:
                item = candidate_fn(key, [label], inline) if inline else None
                if item: candidates[key].append(item)
                continue
            blockers = [n for b,n in barrier_nodes.items() if b != label['b']]
            same = [n for n in values_by_x if n['b'][0] >= right-height*.15
                    and abs(_cy(n)-_cy(label)) <= max(height, _h(n))*.65]
            if key == 'credit_code':
                same = [n for n in same if candidate_fn(key, [n])]
            if same:
                seed = min(same, key=lambda n:(abs(_cy(n)-_cy(label)), n['b'][0]))
                same = [n for n in same if abs(_cy(n)-_cy(seed)) <= min(_h(n),_h(seed))*.45]
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
                if key == 'credit_code':
                    below = [n for n in below if candidate_fn(key, [n])]
                below.sort(key=lambda n:(_cy(n),n['b'][0]))
                if below:
                    n = below[0]
                    if not any(bottom <= z['b'][1] <= n['b'][1] and abs(z['b'][0]-left)<height for z in blockers):
                        selected = [n]
            if not selected:
                continue
            first = selected[0]
            # Multiline text remains within the field's column. Other labels
            # form barriers, including labels whose values are not extracted.
            if key in multiline:
                anchor = first['b'][2] if inline else first['b'][0]
                boundary = min([z['b'][0] for z in blockers if z['b'][0] > anchor
                                and abs(_cy(z)-_cy(label)) <= height] or [float('inf')])
                last = max(n['b'][3] for n in selected)
                last_cy = max(_cy(n) for n in selected)
                selected_indices = {n['source_index'] for n in selected}
                stop_y = min([_cy(z) for z in blockers if _cy(label) < _cy(z)
                              and left-height*.5 <= z['b'][0] < min(boundary, anchor+height)] or [float('inf')])
                for n in sorted(values_by_y, key=lambda n:(_cy(n),n['b'][0])):
                    if n['source_index'] in selected_indices or _cy(n) <= last_cy+height*.3:
                        continue
                    if n['b'][1]-last > height*1.8:
                        break
                    if not (left-height*.5 <= n['b'][0] <= anchor+height and n['b'][2]<boundary):
                        continue
                    if stop_y <= _cy(n)+height*.6:
                        break
                    selected.append(n); selected_indices.add(n['source_index']); last=n['b'][3]; last_cy=_cy(n); extended = True
            item = candidate_fn(key, [label]+selected, _join_texts(n['text'] for n in selected))
            if item:
                item['value_source_lines'] = sorted({i for n in selected for i in n.get('source_indices', [n['source_index']])})
                item['value_boxes'] = [n['box'] for n in selected if n['box'] is not None]
                candidates[key].append(item)
                gap = max(0,first['b'][0]-right)/height + abs(_cy(first)-_cy(label))/height
                if not inline or extended:
                    quality += 10 + 1/(1+gap)
    return candidates, quality


def _extract_fields(rows, document_type, aliases, pattern, candidate_fn, multiline, coordinate_turns, version):
    turns = list(range(4) if coordinate_turns is None else coordinate_turns)
    hypotheses = [_hypothesis(rows, turn, aliases, pattern, candidate_fn, multiline) for turn in turns]
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
        if any(n['box'] is None and any(k == key for k, unused in _parts(n['text'], aliases, pattern)) for n in rows):
            warnings.append('LAYOUT_GEOMETRY_UNAVAILABLE')
        fields[key] = {'value': items[0]['value'] if len(items)==1 else '',
                       'confidence': items[0]['confidence'] if len(items)==1 else 0.0,
                       'requires_review': True, 'source':'ocr', 'candidates':items,
                       'warnings': warnings, 'mapping_version':version,
                       'source_lines': items[0]['source_lines'] if len(items)==1 else [],
                       'source_boxes': items[0]['source_boxes'] if len(items)==1 else [],
                       'value_boxes': items[0].get('value_boxes',[]) if len(items)==1 else []}
    return {'document_type':document_type,'fields':fields,'requires_human_confirmation':True,
            'authenticity_verified':False,'layout_coordinate_turns':[turns[i] for i in winners],'mapping_version':version,
            'layout_score':best}


def extract_license_fields(rows, coordinate_turns=None):
    """Coordinate hypotheses are layout mapping only, not image orientation.

    The inference wrapper passes (0,) after real pixel rotation. Legacy raw
    replay may evaluate all coordinate hypotheses without claiming orientation.
    """
    return _extract_fields(rows, 'business_license', ALIASES, PATTERN, _candidate,
        ('registered_address',), coordinate_turns, VERSION)
