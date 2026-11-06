"""Pinned original model, real four-direction pixels, one reusable engine.

Four sequential model calls per business job; no crop re-inference, downloads,
allocator changes, persistence or automatic writeback. Only detached text and
boxes survive each call. Coordinate mapping is not orientation inference.
"""
import copy
import hashlib
from pathlib import Path
from scripts.community_license_layout import (
    normalize_layout, extract_license_fields, _label_nodes, ALIASES, PATTERN,
)
from scripts.community_identity_layout import extract_identity_fields, FRONT, BACK
import re

UPSTREAM_FILES = {
    'api.py':'0aa40ec64550b64c33bec4902d83155bcd19ab97cae7ea2b28874b28c222621c',
    'secure_store.py':'c0191b6766fc884fc4e5f32e9b6492daa5bf0d90527ab77ed2feb5bd03a05696',
    'ocr_core.py':'bbc99d7e5bc606fc0f069b5a26babc4b87a5f7b4e0726cd71acab231933bc308',
}
# Explicit reviewed compatibility delta: only id_back type/confirmation keys.
# Deployment manifest requires this successor; legacy runtime remains usable
# for same-model offline comparison. Core/store/model pins are unchanged.
COMPATIBLE_API_SHA256 = '32cf647f56f9f1fbed9d0c7d15bb50a0f60a9cd5124bd5ff835129196766636e'
EXPECTED_FIELDS = {
    'business_license': ('company_name', 'credit_code', 'legal_representative', 'registered_address'),
    'id_front': ('id_name', 'id_number', 'registered_address'),
    'id_back': ('issuing_authority', 'valid_from', 'valid_to'),
}


def _orientation_evidence(rows, result, document_type):
    """Transparent lexicographic evidence; no truth values or confidence cutoff.

    More mapped fields, then more label/value geometric associations, then more
    horizontal printed labels. Confidence is reported, never used to resolve a
    semantic orientation tie. Tied directions retain every distinct candidate.
    """
    fields = [f for key,f in result['fields'].items()
              if key in EXPECTED_FIELDS[document_type] and f.get('value')]
    aliases = ALIASES if document_type == 'business_license' else FRONT if document_type == 'id_front' else BACK
    pattern = PATTERN if document_type == 'business_license' else re.compile('|'.join(
        '\\s*'.join(map(re.escape, label)) for label in sorted(aliases, key=len, reverse=True)))
    labels = _label_nodes(rows, 0, aliases, pattern)
    horizontal = [n for n in labels if any(key is not None for key,unused in n['parts']) and n['b'] is not None
                  and n['b'][2]-n['b'][0] >= n['b'][3]-n['b'][1]]
    associations = sum(len(f.get('source_lines', [])) > 1 for f in fields)
    evidence = {'mapped_fields':len(fields), 'geometric_associations':associations,
                'horizontal_labels':len(horizontal), 'layout_score':result.get('layout_score',0),
                'mean_field_confidence':round(sum(f['confidence'] for f in fields)/len(fields),6) if fields else 0.0}
    return (len(fields), associations, len(horizontal)), evidence


def _original_box(box, ccw_turns, width, height):
    """Inverse of numpy.rot90 pixel-center coordinates, without clipping."""
    if box is None:
        return None
    mapped = []
    for x,y in box:
        if ccw_turns == 1: x,y = width-1-y,x
        elif ccw_turns == 2: x,y = width-1-x,height-1-y
        elif ccw_turns == 3: x,y = y,height-1-x
        mapped.append([float(x),float(y)])
    return mapped


def _map_sources(result, turn, width, height):
    def mapped(item):
        for source in item.get('source_boxes', []):
            source['box'] = _original_box(source['box'],turn,width,height)
        if 'value_boxes' in item:
            item['value_boxes'] = [_original_box(b,turn,width,height) for b in item['value_boxes']]
        item['source_coordinate_space'] = 'input_image_pixels'
        item['correction_counterclockwise_degrees'] = turn*90
    # Fields and candidate lists can share nested references. Detach before
    # transforming each record, avoiding an accidental double rotation.
    for key, field in list(result['fields'].items()):
        field = copy.deepcopy(field)
        field['candidates'] = [copy.deepcopy(c) for c in field.get('candidates', [])]
        mapped(field)
        for candidate in field['candidates']:
            mapped(candidate)
        result['fields'][key] = field
    if 'unresolved_validity_candidates' in result:
        for candidate in result['unresolved_validity_candidates']:
            mapped(candidate)
    return result


def _choose_orientation(runs, document_type, width, height):
    best = max(run['rank'] for run in runs)
    winners = [run for run in runs if run['rank'] == best]
    # Zero evidence does not establish an orientation, including empty pages.
    ambiguous = len(winners) != 1 or best[0] == 0
    result = copy.deepcopy(winners[0]['result'])
    if ambiguous:
        keys = set().union(*(run['result']['fields'].keys() for run in winners))
        for key in keys:
            variants = []
            for run in winners:
                field = run['result']['fields'].get(key, {})
                variants.extend(copy.deepcopy(field.get('candidates', [])))
            unique_values = {c['value'] for c in variants}
            base = copy.deepcopy(next((run['result']['fields'][key] for run in winners if key in run['result']['fields']), {}))
            base['candidates'] = variants
            base.update(source_lines=[], source_boxes=[], value_boxes=[], correction_counterclockwise_degrees=None)
            base['warnings'] = list(dict.fromkeys(base.get('warnings', []) + ['ORIENTATION_AMBIGUOUS']))
            if len(unique_values) != 1:
                base.update(value='', confidence=0.0, source_lines=[], source_boxes=[], value_boxes=[])
                base['warnings'].append('CONFLICTING_CANDIDATES' if unique_values else 'LAYOUT_VALUE_MISSING')
            result['fields'][key] = base
    degrees = None if ambiguous else winners[0]['turn']*90
    result['orientation'] = {
        'correction_counterclockwise_degrees':degrees,
        'clockwise_rotation_to_upright_degrees':None if degrees is None else (-degrees)%360,
        'ambiguous':ambiguous,
        'candidate_corrections_counterclockwise_degrees':[run['turn']*90 for run in winners],
        'method':'four_actual_pixel_rotations_original_model',
        'selection_rule':['mapped_fields','geometric_associations','horizontal_labels'],
        'inference_calls':len(runs),
        'engine_instances':1,
        'directions':[dict(correction_counterclockwise_degrees=run['turn']*90, **run['evidence']) for run in runs],
    }
    result['correction_counterclockwise_degrees'] = degrees
    result['input_dimensions'] = {'width':width,'height':height}
    result['source_coordinate_space'] = 'input_image_pixels'
    result['extraction_after_pixel_rotation'] = True
    # Do not return an excluded target even if a legacy result reaches this merge.
    # Persisted historical jobs are deliberately untouched.
    result['fields'].pop('business_scope', None)
    result['requires_human_confirmation'] = True
    result['authenticity_verified'] = False
    for field in result['fields'].values():
        field['requires_review'] = True
    return result


def run_license_layout_ocr(image, document_type, max_bytes=8*1024*1024, max_pixels=20_000_000):
    from services.ocr_engine import ocr_core
    root = Path(ocr_core.__file__).resolve().parent
    for name, digest in UPSTREAM_FILES.items():
        accepted = {digest, COMPATIBLE_API_SHA256} if name == 'api.py' else {digest}
        if hashlib.sha256((root/name).read_bytes()).hexdigest() not in accepted:
            raise PermissionError('LICENSE_OCR_UPSTREAM_PIN_MISMATCH')
    if document_type not in EXPECTED_FIELDS:
        raise ValueError('UNSUPPORTED_DOCUMENT_TYPE')
    if not isinstance(image, bytes) or not image or len(image)>max_bytes:
        raise ValueError('INVALID_IMAGE_SIZE')
    if not (image.startswith(b'\xff\xd8\xff') or image.startswith(b'\x89PNG\r\n\x1a\n')):
        raise ValueError('UNSUPPORTED_IMAGE_MAGIC')
    models = ocr_core._verified_model_paths()
    import cv2
    import numpy as np
    from rapidocr import RapidOCR
    decoded = cv2.imdecode(np.frombuffer(image,dtype=np.uint8),cv2.IMREAD_COLOR)
    if decoded is None or len(decoded.shape)!=3:
        raise ValueError('IMAGE_DECODE_FAILED')
    height,width=decoded.shape[:2]
    if width<1 or height<1 or width*height>max_pixels:
        raise ValueError('IMAGE_PIXEL_LIMIT')
    engine = RapidOCR(params={'Det.model_path':models['det'],'Cls.model_path':models['cls'],'Rec.model_path':models['rec']})
    runs = []
    try:
        for turn in range(4):
            rotated = np.ascontiguousarray(np.rot90(decoded,turn)) if turn else decoded
            raw = engine(rotated)
            rows = normalize_layout(raw)
            del raw, rotated  # Only detached Python text/scalars/quads remain.
            result = extract_license_fields(rows, (0,)) if document_type == 'business_license' else extract_identity_fields(rows, document_type, (0,))
            rank,evidence = _orientation_evidence(rows,result,document_type)
            result = _map_sources(result,turn,width,height)
            runs.append({'turn':turn,'rank':rank,'evidence':evidence,'result':result})
            del rows, result
    finally:
        # Native libraries can retain allocator arenas until process exit.
        # Deleting references is not a claim of immediate OS memory release.
        del engine, decoded
    return _choose_orientation(runs,document_type,width,height)
