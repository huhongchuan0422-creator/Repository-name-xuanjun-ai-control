"""Bounded CP10 CLI roundtrip in one disposable PID namespace."""
import argparse,json,subprocess,sys
p=argparse.ArgumentParser();p.add_argument('--request',required=True);p.add_argument('--role',required=True);args=p.parse_args()
first=None
for action in ('execute','inspect','recover'):
    result=subprocess.run([sys.executable,'-B','-S','-m','production.p2_install.b4_sandbox',action,
        '--request',args.request,'--role',args.role],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=25)
    sys.stderr.buffer.write(result.stderr)
    sys.stdout.buffer.write(result.stdout);sys.stdout.flush()
    if result.returncode:sys.exit(result.returncode)
    row=json.loads(result.stdout)
    if row['status']!='CP10_FINITE_COMMITTED':raise ValueError('CP10_NOT_COMMITTED')
    if first is None:first=row
    elif first!=row:raise ValueError('CP10_RESTART_RECEIPT_CHANGED')
