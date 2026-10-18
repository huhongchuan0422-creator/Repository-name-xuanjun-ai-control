"""Align exact start proof reads with original held proof capacity; no gate removal."""
from pathlib import Path
def repair(s):
    start=s.index(" require(p['source_writer_fence_receipt_sha256']==sha(read(RELEASE/")
    end=s.index(' # Owner removed the review/permit wait;',start)
    s=s[:start]+" load_final_receipts(p,now)\n"+s[end:]
    function='''
    def load_final_receipts(p,now):
     # Read each exact proof once; match the source HeldProof capacities.
     # Large complete manifests are allowed; truncation and drift remain HOLD.
     fence=read(RELEASE/'source-writer-fence.receipt.json',16384)
     checkpoint=read(RELEASE/'final-checkpoint.receipt.json',2097152)
     assignment=read(RELEASE/'canonical-writer-assignment.json',16384)
     return validate_final_receipts(p,fence,checkpoint,assignment,now)
    
    '''
    import textwrap
    function=textwrap.dedent(function).rstrip()+'\n\n'
    s=s[:s.index('def admit():')]+function+s[s.index('def admit():'):]
    return s

if __name__=='__main__':
    p=Path(__file__).with_name('owner_production_start.py')
    p.write_text(repair(p.read_text()))
