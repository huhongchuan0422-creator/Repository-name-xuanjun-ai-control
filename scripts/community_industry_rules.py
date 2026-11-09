"""Pure official industry binding and review-evidence helpers.

No routes, permissions, storage, OCR or provider requests. Callers MUST validate
current private media with the existing application/media validator first.
Natural-language qualification alternatives are never evaluated as boolean rules.
"""
import hashlib
import json
import re
from pathlib import Path
from scripts.pr122_customer_core import canonical

TABLE = Path(__file__).resolve().parents[1] / 'clients/community-mini/merchant-official-industries.json'
SLOTS = ('industry_permit', 'industry_permit_2', 'industry_permit_3', 'industry_permit_4', 'industry_permit_5')

def _hash(value): return hashlib.sha256(canonical(value)).hexdigest()

def _table():
    table=json.loads(TABLE.read_text())
    rows=table['rows'];keys=[(r['subject'],r['settlement_id'],r['qualification_type']) for r in rows]
    if len(keys)!=len(set(keys)):raise ValueError('AMBIGUOUS_OFFICIAL_INDUSTRY_TABLE')
    return table

def validate_selection(profile, entity, category, current_qualifications):
    """Validate exact selection and minimum presence, NOT qualification adequacy.

    current_qualifications is the output of the original backend current-media
    validator: [{kind, sha256, media_id}]. Never accept these from request JSON.
    Draft saving need not call this; formal review/provider-submit paths should.
    """
    if type(profile) is not dict or entity not in ('ENTERPRISE','SOLE_PROPRIETOR'):
        raise ValueError('EXACT_OFFICIAL_INDUSTRY_REQUIRED')
    info=profile.get('settlement_info')
    if type(info) is not dict:raise ValueError('EXACT_OFFICIAL_INDUSTRY_REQUIRED')
    key=(entity,info.get('settlement_id'),info.get('qualification_type'))
    table=_table();matches=[r for r in table['rows'] if (r['subject'],r['settlement_id'],r['qualification_type'])==key]
    if len(matches)!=1:raise ValueError('EXACT_OFFICIAL_INDUSTRY_REQUIRED')
    row=matches[0]
    if type(current_qualifications) is not list or len(current_qualifications)>5:
        raise ValueError('CURRENT_INDUSTRY_BINDINGS_REQUIRED')
    kinds=set();medias=set();bindings=[]
    for b in current_qualifications:
        if (type(b) is not dict or set(b)!={'kind','sha256','media_id'} or b['kind'] not in SLOTS
                or type(b['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}',b['sha256'])
                or type(b['media_id']) is not str or not b['media_id'] or b['kind'] in kinds or b['media_id'] in medias):
            raise ValueError('CURRENT_INDUSTRY_BINDINGS_REQUIRED')
        kinds.add(b['kind']);medias.add(b['media_id']);bindings.append(dict(b))
    selected=info.get('qualifications',[])
    if type(selected) is not list or selected!=[b['media_id'] for b in bindings]:
        raise PermissionError('CURRENT_SELECTED_INDUSTRY_MEDIA_REQUIRED')
    if category=='FOOD' and not bindings:
        raise ValueError('FOOD_QUALIFICATIONS_REQUIRED_BY_EXISTING_CATEGORY')
    if row['special_qualification_required'] is True and not bindings:
        raise ValueError('OFFICIAL_SPECIAL_QUALIFICATION_MATERIAL_REQUIRED')
    branches=row['special_qualification_branches']
    # Even rows marked "否" can contain conditional requirements (e.g. tobacco).
    complex_conditions=any(b['required_text']!='否' or b['description'].strip()!='无需特殊资质' for b in branches)
    rule=dict(source_url=table['source_url'],source_html_sha256=table['source_html_sha256'],
              source_extraction_sha256=table['source_extraction_sha256'],row=row)
    return dict(entity=entity,settlement_id=key[1],qualification_type=key[2],category=category,
                rule=rule,rule_sha256=_hash(rule),current_qualifications=bindings,
                materials_sha256=_hash(bindings),profile_sha256=_hash(profile),
                minimum_presence_satisfied=True,qualification_adequacy='NOT_AUTOMATICALLY_DETERMINED',
                requires_explicit_review=bool(complex_conditions or category=='FOOD'),
                branches=branches,branch_semantics='SOURCE_CONDITIONAL_TEXT_NOT_ALL_REQUIRED')

def validate_review_evidence(plan, evidence, *, application, application_revision, profile_version,
                             owner_id, authorized_reviewer_id):
    """Validate retained original reviewer evidence, not grant reviewer authority.

    The original protected review path must supply authorized_reviewer_id after
    its own session/role checks. New evidence must be recorded only there.
    Each source branch is explicitly classified, rather than all required or any
    one assumed sufficient. A not-applicable explanation is not auto-approved.
    """
    if not plan['requires_explicit_review']:return False
    fields={'application','application_revision','profile_version','reviewer_id','rule_sha256',
            'materials_sha256','profile_sha256','decision','branch_assessments'}
    if (type(evidence) is not dict or set(evidence)!=fields
            or not authorized_reviewer_id or authorized_reviewer_id==owner_id
            or evidence['reviewer_id']!=authorized_reviewer_id
            or evidence['application']!=application
            or type(evidence['application_revision']) is not int or evidence['application_revision']!=application_revision
            or type(evidence['profile_version']) is not int or evidence['profile_version']!=profile_version
            or any(evidence[k]!=plan[k] for k in ('rule_sha256','materials_sha256','profile_sha256'))
            or evidence['decision']!='CONDITIONS_CONFIRMED'):
        raise PermissionError('CURRENT_INDEPENDENT_INDUSTRY_REVIEW_REQUIRED')
    assessments=evidence['branch_assessments']
    if type(assessments) is not list or len(assessments)!=len(plan['branches']):
        raise PermissionError('COMPLETE_INDUSTRY_BRANCH_REVIEW_REQUIRED')
    seen=set();admitted={b['kind'] for b in plan['current_qualifications']}
    for item in assessments:
        if (type(item) is not dict or set(item)!={'branch_index','applicability','material_kinds','rationale'}
                or type(item['branch_index']) is not int or not 0<=item['branch_index']<len(plan['branches'])
                or item['branch_index'] in seen or item['applicability'] not in ('APPLICABLE_SATISFIED','NOT_APPLICABLE')
                or type(item['material_kinds']) is not list or any(k not in admitted for k in item['material_kinds'])
                or type(item['rationale']) is not str or not item['rationale'].strip()):
            raise PermissionError('EXPLICIT_INDUSTRY_BRANCH_ASSESSMENT_REQUIRED')
        seen.add(item['branch_index'])
    return True
