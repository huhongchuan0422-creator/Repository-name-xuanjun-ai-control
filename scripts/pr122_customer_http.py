"""Mail-lane seam: byte-identical strict_json fragment of the fixed original
scripts/pr122_customer_http.py at commit 3629c97e41df6a382056cdc68712e8f2f2c21fca
(SHA256 of that full original: 36 lines 1-23 and function 25-34 recorded in
deliveries/email-crm-identity-delta-20261123-2207/SHA256SUMS.txt).
Only pr122_customer_identity.strict() is wired on this branch; the full
Same-origin HTTP adapter still lives in the 3629 lineage and must supersede
this file when the lineages merge. No network listeners are defined here.
"""
import json

def strict_json(raw):
    def pairs(items):
        d={}
        for k,v in items:
            if k in d:raise ValueError('DUPLICATE_KEY')
            d[k]=v
        return d
    def reject(_):raise ValueError('NONFINITE_JSON')
    d=json.loads(raw,object_pairs_hook=pairs,parse_constant=reject)
    if type(d) is not dict:raise ValueError('OBJECT_REQUIRED')
    return d
