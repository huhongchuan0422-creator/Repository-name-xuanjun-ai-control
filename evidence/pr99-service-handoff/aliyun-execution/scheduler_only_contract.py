def validate_observation(d,expected,nonce):
    def need(ok):
        if not ok:raise ValueError('SCHEDULER_CONTRACT')
    def fields(x,keys):need(type(x)is dict and set(x)==set(keys.split()))
    fields(d,'hostname nonce observed_at scope schedulers source_inventory business_source_imports database_opened service_actions business_requests canonical_data_assigned authoritative_writer enforced_fence limitations')
    need(d['hostname']==expected and d['nonce']==nonce)
    need(d['scope']=='PR99_SCHEDULER_DEFINITIONS_ONLY_NOT_AUTHORITY')
    need(type(d['observed_at'])is str and re.fullmatch('[0-9T:.Z-]{19,40}',d['observed_at']))
    need(d['source_inventory']=='PREVIOUS_FAILED_RESULT_NOT_RETURNED_NOT_REPLAYED')
    for k in ('business_source_imports','service_actions','business_requests'):need(type(d[k])is int and d[k]==0)
    need(d['database_opened']is False and d['canonical_data_assigned']is False)
    need(d['authoritative_writer']==d['enforced_fence']=='UNKNOWN')
    need(d['limitations']==['IMMEDIATE_REGULAR_FRAGMENTS_ONLY_NOT_EFFECTIVE_UNIT_CONFIGURATION',
                           'EXCLUDED_LINKS_DROPINS_OTHER_NAMESPACES_NOT_COVERED','NO_DRAIN_OR_FENCE_PERFORMED'])
    s=d['schedulers'];fields(s,'regular_fragments_read excluded_symlinks candidates')
    for k in ('regular_fragments_read','excluded_symlinks'):need(type(s[k])is int and 0<=s[k]<100001)
    need(type(s['candidates'])is list and len(s['candidates'])<=129)
    seen=set()
    for row in s['candidates']:
        fields(row,'root_slot name sha256 bytes matching_lines')
        need(type(row['root_slot'])is int and 0<=row['root_slot']<5)
        need(type(row['name'])is str and re.fullmatch(r'[A-Za-z0-9_.:@\\-]{1,240}',row['name']))
        need(row['name']not in ('.','..') and (row['root_slot'],row['name'])not in seen)
        seen.add((row['root_slot'],row['name']))
        need(type(row['sha256'])is str and re.fullmatch('[0-9a-f]{64}',row['sha256']))
        for k in ('bytes','matching_lines'):need(type(row[k])is int and 0<=row[k]<=131072)
    return d
