"""Private, unconfirmed OCR drafts. Never part of a provider applyment profile."""
from copy import deepcopy

FIELDS = {
    'business_license': {'company_name', 'credit_code', 'legal_representative', 'registered_address'},
    'id_front': {'id_name', 'id_number', 'registered_address'},
    'id_back': {'valid_from', 'valid_to'},
    'bank_card': {'account_number', 'account_bank'},
}
MATERIAL = {'id_front': 'identity_front', 'id_back': 'identity_back'}


def merge_drafts(previous, updates, materials):
    """An omitted update never clears pending confirmation. No client confirmed flag."""
    result = deepcopy(previous or {})
    if updates is None:
        return result
    if type(updates) is not dict or set(updates) - set(FIELDS):
        raise ValueError('INVALID_PRIVATE_OCR_DRAFT')
    for kind, draft in updates.items():
        if type(draft) is not dict or set(draft) != {'object_id', 'sha256', 'fields'}:
            raise ValueError('INVALID_PRIVATE_OCR_DRAFT')
        material = materials.get(MATERIAL.get(kind, kind))
        if not material or any(draft[k] != material.get(k) for k in ('object_id', 'sha256')):
            raise ValueError('PRIVATE_OCR_DRAFT_MATERIAL_CHANGED')
        fields = draft['fields']
        if (type(fields) is not dict or not fields or set(fields) - FIELDS[kind]
                or any(type(v) is not str or len(v) > 512 for v in fields.values())):
            raise ValueError('INVALID_PRIVATE_OCR_DRAFT_FIELDS')
        old = result.get(kind, {})
        same_source = all(old.get(k) == draft[k] for k in ('object_id', 'sha256'))
        merged_fields = dict(old.get('fields', {}) if same_source else {}, **fields)
        result[kind] = dict(object_id=draft['object_id'], sha256=draft['sha256'],
                            fields=merged_fields, revision=old.get('revision', 0) + 1,
                            needs_confirmation=True)
    return result


def current_drafts(drafts, materials):
    return {kind: draft for kind, draft in (drafts or {}).items()
            if draft.get('needs_confirmation') and
            (material := materials.get(MATERIAL.get(kind, kind))) and
            all(draft.get(k) == material.get(k) for k in ('object_id', 'sha256'))}


def current_pending(drafts, materials):
    return {kind: draft for kind, draft in current_drafts(drafts, materials).items()
            if any(type(value) is str and value.strip() for value in draft['fields'].values())}


def resolve_confirmed(drafts, kind, material, confirmed_fields):
    """Call ONLY inside the original verified confirmation + dual-version CAS.

    A human correction supersedes the old suggestion for each confirmed key.
    Comparing values would leave a corrected old draft permanently pending.
    Ordinary saves cannot call this; other keys and materials stay untouched.
    """
    result = deepcopy(drafts or {})
    pending = result.get(kind)
    if not pending or not all(pending.get(k) == material.get(k) for k in ('object_id', 'sha256')):
        return result
    remaining = {key: value for key, value in pending['fields'].items()
                 if key not in confirmed_fields}
    if remaining:
        result[kind]['fields'] = remaining
    else:
        del result[kind]
    return result
