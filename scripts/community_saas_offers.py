"""Offline SaaS offer/price-component extension; no purchases or finance ledger writes.

Multiple offers per reusable module. Explicit CNY and USD line prices require
versioned source evidence; never infer FX, supplier invoices or commission.
"""
import sqlite3
from scripts.community_saas_schema_guard import verify,transactional_install
from scripts.community_saas_modules import MODULES
PAYMENT_MODES = frozenset(("MONTHLY","YEARLY","BUYOUT","FREE","PROMO_ZERO","USAGE","HYBRID","CUSTOM"))
COMPONENT_KINDS = frozenset((
    "MODULE_LICENSE","THIRD_PARTY_SUBSCRIPTION_BASE","THIRD_PARTY_CLOUD_BASE",
    "AGENCY_SERVICE_FEE","DEPLOYMENT_ONCE","IMPLEMENTATION_ONCE",
    "MAINTENANCE_RECURRING","SUPPORT_RECURRING","USAGE_RATE",
    "TAX_AND_PROCESSING","DISCOUNT"))
BILLING_CADENCES=frozenset(("ONCE","MONTHLY","YEARLY","PER_UNIT"))
SCHEMA="""
CREATE TABLE offers(
 offer_id TEXT PRIMARY KEY,module_id TEXT NOT NULL,
 mode TEXT NOT NULL,version INTEGER NOT NULL CHECK(version>0),
 status TEXT NOT NULL CHECK(status IN ('DRAFT','PREVIEW','APPROVED','EFFECTIVE','RETIRED')),
 availability TEXT NOT NULL CHECK(availability IN ('PUBLIC','CUSTOMER_PRIVATE')),
 tenant_scope TEXT, CHECK((availability='PUBLIC' AND tenant_scope IS NULL) OR (availability='CUSTOMER_PRIVATE' AND tenant_scope IS NOT NULL)),
 term_days INTEGER,renewable INTEGER NOT NULL CHECK(renewable IN (0,1)),
 license_scope TEXT NOT NULL,price_basis TEXT NOT NULL,
 CHECK(term_days IS NULL OR term_days>0)
);
CREATE TABLE components(
 offer_id TEXT NOT NULL,component_id TEXT NOT NULL,
 kind TEXT NOT NULL,cadence TEXT NOT NULL,
 cny_minor INTEGER NOT NULL CHECK(cny_minor>=0),
 usd_minor INTEGER NOT NULL CHECK(usd_minor>=0),
 discount INTEGER NOT NULL CHECK(discount IN (0,1)),
 supplier_id TEXT,source_evidence TEXT NOT NULL,
 included INTEGER NOT NULL CHECK(included IN (0,1)),
 PRIMARY KEY(offer_id,component_id),
 FOREIGN KEY(offer_id) REFERENCES offers(offer_id));
"""
def open_offer_store(path=":memory:"):
 db=sqlite3.connect(path)
 try:
  db.execute("PRAGMA foreign_keys=ON")
  row=db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
  expected={"offers","components"}
  if not row and db.execute("PRAGMA user_version").fetchone()[0]==0:
   transactional_install(db,SCHEMA+"\nPRAGMA user_version=1;",lambda:verify(db,SCHEMA,expected))
  else:
   verify(db,SCHEMA,expected)
  return db
 except BaseException:
  db.close()
  raise
def register_offer(db,offer_id,module_id,mode,version,term_days,renewable,license_scope,
                   price_basis,availability="PUBLIC",tenant_scope=None):
 if not isinstance(offer_id,str) or not offer_id or len(offer_id)>90 or module_id not in MODULES or mode not in PAYMENT_MODES:
  raise ValueError("INVALID_OFFER")
 if type(version) is not int or version<1 or type(renewable) is not bool or (term_days is not None and (type(term_days) is not int or term_days<1)):
  raise ValueError("INVALID_TERM")
 if mode in ("MONTHLY","YEARLY") and (term_days is None or not renewable):
  raise ValueError("PERIODIC_TERM_REQUIRED")
 if mode=="BUYOUT" and (renewable or not license_scope):
  raise ValueError("BUYOUT_SCOPE_REQUIRED")
 if mode in ("FREE","PROMO_ZERO") and (not isinstance(license_scope,str) or not license_scope):
  raise ValueError("FREE_LICENSE_SCOPE_REQUIRED")
 if availability not in ("PUBLIC","CUSTOMER_PRIVATE") or not isinstance(price_basis,str) or not price_basis:
  raise ValueError("INVALID_OFFER_METADATA")
 if (availability=="CUSTOMER_PRIVATE" and (type(tenant_scope) is not str or not tenant_scope)) or (availability=="PUBLIC" and tenant_scope is not None):
  raise ValueError("TENANT_SCOPE_REQUIRED")
 with db:
  db.execute("INSERT INTO offers VALUES(?,?,?,?,?,?,?,?,?,?,?)",
    (offer_id,module_id,mode,version,"DRAFT",availability,tenant_scope,term_days,int(renewable),license_scope,price_basis))
def add_component(db,offer_id,component_id,kind,cadence,cny_minor,usd_minor,
                  source_evidence,supplier_id=None,included=False):
 if kind not in COMPONENT_KINDS or cadence not in BILLING_CADENCES or not isinstance(component_id,str) or not component_id:
  raise ValueError("INVALID_COMPONENT")
 if type(cny_minor) is not int or type(usd_minor) is not int or min(cny_minor,usd_minor)<0 or type(included) is not bool:
  raise ValueError("INVALID_PRICE")
 if not isinstance(source_evidence,str) or not source_evidence or source_evidence=="UNKNOWN":
  raise ValueError("COST_EVIDENCE_REQUIRED")
 if supplier_id is not None and (not isinstance(supplier_id,str) or not supplier_id):
  raise ValueError("INVALID_SUPPLIER")
 if kind.startswith("THIRD_PARTY") and not supplier_id:raise ValueError("SUPPLIER_REQUIRED")
 with db:
  row=db.execute("SELECT status FROM offers WHERE offer_id=?",(offer_id,)).fetchone()
  if row is None or row[0]!="DRAFT":raise ValueError("OFFER_COMPONENTS_FROZEN")
  db.execute("INSERT INTO components VALUES(?,?,?,?,?,?,?,?,?,?)",
   (offer_id,component_id,kind,cadence,cny_minor,usd_minor,int(kind=="DISCOUNT"),
    supplier_id,source_evidence,int(included)))
def quote_offers(db,module_id,procurement_mode="XUANJUN_MANAGED",tenant_id=None):
 if module_id not in MODULES or procurement_mode not in ("XUANJUN_MANAGED","CUSTOMER_MANAGED","HYBRID") or (tenant_id is not None and (type(tenant_id) is not str or not tenant_id)):
  raise ValueError("INVALID_QUOTE_CONTEXT")
 result=[]
 rows=db.execute("SELECT offer_id,mode,version,term_days,renewable,license_scope,price_basis FROM offers "
                 "WHERE module_id=? AND status='EFFECTIVE' AND (availability='PUBLIC' OR tenant_scope=?) ORDER BY offer_id",(module_id,tenant_id)).fetchall()
 for oid,mode,version,term,renewable,scope,basis in rows:
  components=[]
  total_cny=total_usd=0
  by_cadence={}
  for cid,kind,cadence,cny,usd,discount,supplier,evidence,included in db.execute(
      "SELECT component_id,kind,cadence,cny_minor,usd_minor,discount,supplier_id,source_evidence,included "
      "FROM components WHERE offer_id=? ORDER BY component_id",(oid,)):
   if procurement_mode=="CUSTOMER_MANAGED" and kind.startswith("THIRD_PARTY") and not included:
    raise ValueError("BYOK_SUPPLIER_PRINCIPAL_MUST_NOT_BE_CHARGED")
   adjustment=-1 if discount else 1
   charge_cny=0 if included else cny*adjustment
   charge_usd=0 if included else usd*adjustment
   total_cny+=charge_cny;total_usd+=charge_usd
   period=by_cadence.setdefault(cadence,{"cny_minor":0,"usd_minor":0})
   period["cny_minor"]+=charge_cny
   period["usd_minor"]+=charge_usd
   components.append({"component_id":cid,"kind":kind,"cadence":cadence,"cny_minor":charge_cny,
      "usd_minor":charge_usd,"supplier_id":supplier,"evidence":evidence,"included":bool(included)})
  # Discounts must not make any billing cadence negative, even if another
  # cadence is positive. An arithmetic sum across cadences is never payable.
  if total_cny<0 or total_usd<0 or any(
      amount["cny_minor"]<0 or amount["usd_minor"]<0
      for amount in by_cadence.values()):
   raise ValueError("NEGATIVE_QUOTE_TOTAL")
  if mode in ("FREE","PROMO_ZERO") and (total_cny!=0 or total_usd!=0):
   raise ValueError("FREE_OFFER_HAS_PAYABLE_COMPONENTS")
  result.append({"offer_id":oid,"mode":mode,"version":version,"term_days":term,
   "renewable":bool(renewable),"license_scope":scope,"price_basis":basis,
   "components":components,"total_cny_minor":total_cny,"total_usd_minor":total_usd,
   "totals_by_cadence":by_cadence,"mixed_billing_cadences":len(by_cadence)>1,
   "totals_are_payable":False,
   "settlement_currency":None,"fx_rate_assumed":False,"procurement_executed":False})
 return result
def change_offer_status(db,offer_id,new_status,cost_db=None):
 if new_status not in ("PREVIEW","APPROVED","EFFECTIVE","RETIRED"):raise ValueError("INVALID_STATUS")
 allowed={"DRAFT":"PREVIEW","PREVIEW":"APPROVED","APPROVED":"EFFECTIVE","EFFECTIVE":"RETIRED"}
 with db:
  row=db.execute("SELECT status FROM offers WHERE offer_id=?",(offer_id,)).fetchone()
  if row is None or allowed.get(row[0])!=new_status:raise ValueError("INVALID_OFFER_TRANSITION")
  if new_status=="EFFECTIVE":
   if cost_db is None:raise ValueError("COST_EVIDENCE_GATE_REQUIRED")
   from scripts.community_saas_cost_pricing import assert_publishable_cost
   assert_publishable_cost(db,cost_db,offer_id)
  db.execute("UPDATE offers SET status=? WHERE offer_id=?",(new_status,offer_id))
