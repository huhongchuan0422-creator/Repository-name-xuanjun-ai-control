"""Persist/restore finite native component state, not phase SKIP or re-execution.

Only explicit data fields from the original concrete composition are included.
Restoration follows authenticated native journal/CAS and independent host effect
readback. It never changes plans, policies, handlers, guards or executable code.
"""
import copy
import json
from receipt_provider import need, canonical

FIELDS={
 'gate':('authorization','current_targets','current_generation','current_additive_targets'),
 'verifier':('cached','checked_under_lock'),
 'controls':('next_index','open_phase'),
 'diagnostics':('sequence',),
 'authority':('predecessor_record_sha',),
 'core':('current','started','staged_release_parent'),
 'runtime':('phase','cleanup_scope','attempted','cleanup_attempted'),
 'legacy':('cleaning','restored','remasked','restoration'),
 'acceptance':('phase','done','results'),
}
SETS=frozenset(('started','attempted','cleanup_attempted','done'))

def objects(driver):
    result={'gate':driver.gate,'verifier':driver.gate.verifier,'controls':driver.controls,'diagnostics':driver.diagnostics}
    authority=getattr(driver.journal_io,'authority',None)
    if authority is not None:result['authority']=authority
    containment=driver.containment
    for name in ('core','runtime','legacy'):
        value=getattr(containment,name,None)
        if value is not None:result[name]=value
    runtime=result.get('runtime')
    acceptance=getattr(getattr(runtime,'access_check',None),'__self__',None)
    if acceptance is not None:result['acceptance']=acceptance
    return result

def capture(driver, completed):
    result={'schema':1,'completed':list(completed),'objects':{}}
    for name,obj in objects(driver).items():
        values={}
        for field in FIELDS[name]:
            if hasattr(obj,field):
                value=getattr(obj,field)
                values[field]=sorted(value) if field in SETS else copy.deepcopy(value)
        result['objects'][name]={'type':type(obj).__module__+'.'+type(obj).__name__,'values':values}
    if 'next_index' in result['objects']['controls']['values']:
        need(result['objects']['controls']['values']=={'next_index':len(completed),'open_phase':None},
             'NATIVE_CURSOR_NOT_AT_CHECKPOINT')
    need(len(canonical(result))<=196608,'NATIVE_COMPONENT_BOUND')
    return json.loads(canonical(result).decode('utf-8'))

def restore(driver, state, completed):
    need(type(state) is dict and set(state)=={'schema','completed','objects'} and
         type(state['schema']) is int and state['schema']==1 and state['completed']==list(completed),
         'NATIVE_COMPONENT_BINDING')
    live=objects(driver)
    need(type(state['objects']) is dict and set(state['objects'])==set(live),'NATIVE_COMPOSITION_CHANGED')
    # Validate all fields before any in-memory mutation.
    for name,obj in live.items():
        row=state['objects'][name]
        need(type(row) is dict and set(row)=={'type','values'} and
             row['type']==type(obj).__module__+'.'+type(obj).__name__ and
             type(row['values']) is dict and set(row['values'])<=set(FIELDS[name]), 'NATIVE_COMPONENT_SCHEMA')
        required={field for field in FIELDS[name] if hasattr(obj,field)}
        need(required<=set(row['values']),'NATIVE_COMPONENT_MISSING')
        for field in SETS&set(row['values']):
            value=row['values'][field]
            need(type(value) is list and all(type(x) is str for x in value) and
                 value==sorted(set(value)), 'NATIVE_COMPONENT_SET')
    cursor=state['objects']['controls']['values']
    if 'next_index' in cursor:
        need(type(cursor['next_index']) is int and cursor['next_index']==len(completed) and
             cursor.get('open_phase') is None, 'NATIVE_CURSOR_BINDING')
    # Original immutable proposal/review fields are never restored from data.
    authorization=state['objects']['gate']['values']['authorization']
    need(type(authorization) is dict and authorization.get('review_id')==driver.gate.review_id and
         authorization.get('binding')==driver.gate.expected,'NATIVE_REVIEW_BINDING')
    cached=state['objects']['verifier']['values']['cached']
    need(type(cached) is dict and cached.get('review_id')==driver.gate.verifier.review_id and
         cached.get('body_sha256')==driver.gate.verifier.body_sha and
         cached.get('approval')==driver.gate.verifier.wanted and
         state['objects']['verifier']['values'].get('checked_under_lock') is True, 'NATIVE_CACHED_PROVENANCE')
    for name,obj in live.items():
        for field,value in state['objects'][name]['values'].items():
            setattr(obj,field,set(value) if field in SETS else copy.deepcopy(value))
