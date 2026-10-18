"""Public projection boundary: technical names/counts/hashes only, never authority."""
def validate_observation(d, expected, nonce):
    import re
    def need(ok):
        if not ok: raise ValueError('DATA_INVENTORY_CONTRACT')
    def fields(x, keys):need(type(x) is dict and set(x)==set(keys.split()))
    def integer(x, maximum=2**64):need(type(x) is int and 0<=x<maximum)
    def digest(x):need(type(x) is str and re.fullmatch('[0-9a-f]{64}',x))
    def filename(x):need(type(x) is str and re.fullmatch('[A-Za-z0-9_./-]{1,240}',x) and '..' not in x.split('/'))
    fields(d,'hostname nonce observed_at scope source schedulers business_source_imports database_opened service_actions business_requests canonical_data_assigned authoritative_writer enforced_fence limitations')
    need(d['hostname']==expected and d['nonce']==nonce)
    need(d['scope']=='PR99_SOURCE_AND_SCHEDULER_INVENTORY_NOT_AUTHORITY')
    need(type(d['observed_at']) is str and re.fullmatch('[0-9T:.Z-]{19,40}',d['observed_at']))
    for name in ('business_source_imports','service_actions','business_requests'):
        need(type(d[name]) is int and d[name]==0)
    need(d['database_opened'] is False and d['canonical_data_assigned'] is False)
    need(d['authoritative_writer']==d['enforced_fence']=='UNKNOWN')
    need(d['limitations']==['STATIC_CANDIDATES_NOT_PROVEN_WRITERS','DYNAMIC_PATHS_AND_IDLE_WRITERS_NOT_RESOLVED',
         'EXCLUDED_LINKS_AND_OTHER_NAMESPACES_NOT_COVERED','NO_DRAIN_OR_FENCE_PERFORMED'])
    s=d['source'];fields(s,'files bytes manifest_sha256 candidate_files_total omitted_candidate_files candidates parse_errors excluded_links')
    integer(s['files'],2049);integer(s['bytes'],67108865);digest(s['manifest_sha256'])
    for key in ('candidate_files_total','omitted_candidate_files','excluded_links'):integer(s[key],4097)
    need(s['candidate_files_total']<=s['files'] and s['omitted_candidate_files']==max(0,s['candidate_files_total']-128))
    need(type(s['candidates']) is list and len(s['candidates'])==min(128,s['candidate_files_total']))
    seen=set()
    for row in s['candidates']:
        fields(row,'path sha256 calls environment_keys environment_keys_total')
        filename(row['path']);need(row['path'].endswith('.py') and row['path'] not in seen);seen.add(row['path'])
        digest(row['sha256']);fields(row['calls'],'DB_FACTORY FILE_WRITE MUTATION_CALL')
        for count in row['calls'].values():integer(count,100001)
        need(sum(row['calls'].values())>0)
        integer(row['environment_keys_total'],100001)
        need(type(row['environment_keys']) is list and len(row['environment_keys'])==min(12,row['environment_keys_total']))
        need(row['environment_keys']==sorted(set(row['environment_keys'])))
        for key in row['environment_keys']:need(type(key) is str and re.fullmatch('[A-Z][A-Z0-9_]{1,100}',key))
    need(type(s['parse_errors']) is list and len(s['parse_errors'])<=32)
    for path in s['parse_errors']:filename(path)
    r=d['schedulers'];fields(r,'regular_fragments_read excluded_symlinks candidates')
    integer(r['regular_fragments_read'],2050);integer(r['excluded_symlinks'],100001)
    need(type(r['candidates']) is list and len(r['candidates'])<=129)
    seen=set()
    for row in r['candidates']:
        fields(row,'root_slot name sha256 bytes matching_lines')
        integer(row['root_slot'],5);filename(row['name']);need('/' not in row['name'])
        need((row['root_slot'],row['name']) not in seen);seen.add((row['root_slot'],row['name']))
        digest(row['sha256']);integer(row['bytes'],131073);integer(row['matching_lines'],131073)
    return d
