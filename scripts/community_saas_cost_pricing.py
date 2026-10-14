"""Offline per-offer cost evidence and margin advisory; no billing execution.
Keep cost status UNKNOWN as NULL, never automatically convert to zero.
A cadence-specific quote is not an accounting income statement.
"""
import sqlite3
from scripts.community_saas_offers import open_offer_store

SCHEMA = """
CREATE TABLE component_costs(
 offer_id TEXT NOT NULL, component_id TEXT NOT NULL,
 cost_cny_minor INTEGER,cost_usd_minor INTEGER,
 status TEXT NOT NULL CHECK(status IN ('UNKNOWN','EVIDENCED_ESTIMATE','VERIFIED_ACTUAL')),
 evidence_ref TEXT, cadence TEXT NOT NULL,
 PRIMARY KEY(offer_id,component_id),
 CHECK((status='UNKNOWN' AND cost_cny_minor IS NULL AND cost_usd_minor IS NULL AND evidence_ref IS NULL)
 OR (status!='UNKNOWN' AND cost_cny_minor>=0 AND cost_usd_minor>=0 AND evidence_ref IS NOT NULL)));
"""
def open_cost_store(path=":memory:"):
 db=sqlite3.connect(path)
 try:
  tables={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
  if not tables:
   if db.execute("PRAGMA user_version").fetchone()[0]!=0:raise ValueError("INVALID_COST_SCHEMA")
   db.executescript("BEGIN IMMEDIATE;"+SCHEMA+"PRAGMA user_version=1;COMMIT;")
  elif tables!={"component_costs"} or db.execute("PRAGMA user_version").fetchone()[0]!=1:
   raise ValueError("INVALID_COST_SCHEMA")
  return db
 except BaseException:
  db.close();raise
def save_cost(db,offer_id,component_id,status,cny=None,usd=None,evidence_ref=None,cadence="ONCE"):
 if status not in ("UNKNOWN","EVIDENCED_ESTIMATE","VERIFIED_ACTUAL"):
  raise ValueError("INVALID_COST_STATUS")
 if cadence not in ("ONCE","MONTHLY","YEARLY","PER_UNIT"):
  raise ValueError("INVALID_COST_CADENCE")
 if status=="UNKNOWN":
  if any(v is not None for v in (cny,usd,evidence_ref)):
   raise ValueError("UNKNOWN_COST_MUST_REMAIN_NULL")
 else:
  if any(type(v) is not int or v<0 for v in (cny,usd)) or not isinstance(evidence_ref,str) or not evidence_ref:
   raise ValueError("COST_EVIDENCE_REQUIRED")
 with db:
  db.execute("INSERT INTO component_costs VALUES(?,?,?,?,?,?,?) "
   "ON CONFLICT(offer_id,component_id) DO UPDATE SET "
   "cost_cny_minor=excluded.cost_cny_minor,cost_usd_minor=excluded.cost_usd_minor,"
   "status=excluded.status,evidence_ref=excluded.evidence_ref,cadence=excluded.cadence",
   (offer_id,component_id,cny,usd,status,evidence_ref,cadence))
def preview(offer_db,cost_db,offer_id):
 result=offer_db.execute("SELECT status FROM offers WHERE offer_id=?",(offer_id,)).fetchone()
 if result is None:raise ValueError("UNKNOWN_OFFER")
 rows=offer_db.execute("SELECT component_id,kind,cadence,cny_minor,usd_minor,included "
                       "FROM components WHERE offer_id=? ORDER BY component_id",(offer_id,)).fetchall()
 groups={}
 lines=[]
 incomplete=not bool(rows)
 estimate=False
 for cid,kind,cadence,cny,usd,included in rows:
  record=cost_db.execute("SELECT cost_cny_minor,cost_usd_minor,status,evidence_ref,cadence "
    "FROM component_costs WHERE offer_id=? AND component_id=?",(offer_id,cid)).fetchone()
  cc,cu,state,evidence,cost_cadence=record if record else (None,None,"UNKNOWN",None,cadence)
  if state=="UNKNOWN" or cc is None or cu is None or cost_cadence!=cadence:incomplete=True
  if state=="EVIDENCED_ESTIMATE":estimate=True
  sale_cny=0 if included else -cny if kind=="DISCOUNT" else cny
  sale_usd=0 if included else -usd if kind=="DISCOUNT" else usd
  group=groups.setdefault(cadence,{"sale_cny_minor":0,"sale_usd_minor":0,"cost_cny_minor":0,"cost_usd_minor":0})
  group["sale_cny_minor"]+=sale_cny
  group["sale_usd_minor"]+=sale_usd
  if cc is not None:group["cost_cny_minor"]+=cc
  if cu is not None:group["cost_usd_minor"]+=cu
  lines.append({"component_id":cid,"kind":kind,"cadence":cadence,
   "sale_cny_minor":sale_cny,"sale_usd_minor":sale_usd,
   "cost_cny_minor":cc,"cost_usd_minor":cu,"cost_status":state,
   "cost_evidence_ref":evidence,"cost_cadence":cost_cadence})
 for row in groups.values():
  row["gross_margin_cny_minor"]=None if incomplete else row["sale_cny_minor"]-row["cost_cny_minor"]
  row["gross_margin_usd_minor"]=None if incomplete else row["sale_usd_minor"]-row["cost_usd_minor"]
  if incomplete:
   row["cost_cny_minor"]=None
   row["cost_usd_minor"]=None
 return {"offer_id":offer_id,"publishable_cost_evidence":not incomplete,
  "contains_estimates":estimate,"cost_unknown":incomplete,
  "by_cadence":groups,"lines":lines,"commissions_payable":False}
def assert_publishable_cost(offer_db,cost_db,offer_id):
 view=preview(offer_db,cost_db,offer_id)
 if not view["publishable_cost_evidence"]:
  raise ValueError("COST_INCOMPLETE_QUOTE_BLOCKED")
 return view
