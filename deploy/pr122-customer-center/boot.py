"""Hash-check installed reviewed source before importing service code."""
import hashlib,json,sys
from pathlib import Path
root=Path(__file__).resolve().parent
m=json.loads((root/'CUSTOMER_MANIFEST.json').read_bytes())
for row in m['files']:
 p=root/row['path']
 if p.is_symlink() or not p.is_file() or p.stat().st_size!=row['size'] or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise SystemExit('HOLD: SOURCE_DRIFT')
sys.path.insert(0,str(root))
from scripts.pr122_customer_ops import main
main()
