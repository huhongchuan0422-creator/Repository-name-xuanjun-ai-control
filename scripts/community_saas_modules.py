"""Stage5 SaaS feature modules: independent catalog, price versions and entitlements.

Framework is free; modules are independently selectable. This is an OFFLINE
product/contract model, not payment collection or provider authorization.
All money values are quoted configuration; no transaction is settled here.
"""
import sqlite3
import re
from scripts.community_merchant_contract import valid_id

MODULES = {
 "storefront_catalog": {"title":"商家商品展示", "entrypoint":"storefront",
   "dependencies":(), "capabilities":("catalog.read","storefront.read")},
 "merchant_operations": {"title":"商家经营后台", "entrypoint":"merchant",
   "dependencies":("storefront_catalog",), "capabilities":("catalog.manage","orders.read")},
 "advertising": {"title":"双广告位与投放管理", "entrypoint":"advertising",
   "dependencies":("storefront_catalog",), "capabilities":("ads.read","ads.manage","ads.review")},
 "refund_preview": {"title":"退款预览账本", "entrypoint":"refund_preview",
   "dependencies":("merchant_operations",), "capabilities":("refund.preview.read","refund.preview.record")},
 "split_preview": {"title":"分账预览", "entrypoint":"split_preview",
   "dependencies":("refund_preview",), "capabilities":("split.preview",)},
 "reconciliation_preview": {"title":"对账预览", "entrypoint":"reconciliation",
   "dependencies":("refund_preview",), "capabilities":("reconciliation.preview",)},
 "signed_qr": {"title":"签名扫码入口", "entrypoint":"signed_qr",
   "dependencies":("storefront_catalog",), "capabilities":("qr.demo",)}
}
CAPABILITIES = {cap:code for code,item in MODULES.items() for cap in item["capabilities"]}
SCHEMA = """
CREATE TABLE module_prices (
 module_id TEXT NOT NULL, version INTEGER NOT NULL CHECK(version>0),
 cny_minor INTEGER NOT NULL CHECK(cny_minor>=0),
 usd_minor INTEGER NOT NULL CHECK(usd_minor>=0),
 period_days INTEGER NOT NULL CHECK(period_days>0),
 active INTEGER NOT NULL CHECK(active IN (0,1)),
 PRIMARY KEY(module_id,version));
CREATE TABLE module_entitlements (
 tenant_id TEXT NOT NULL,module_id TEXT NOT NULL,valid_from INTEGER NOT NULL,
 valid_until INTEGER NOT NULL,price_version INTEGER NOT NULL,
 source TEXT NOT NULL CHECK(source IN ('OFFLINE_GRANT','PAID_ORDER_CONFIRMED','CUSTOM_DELIVERY')),
 PRIMARY KEY(tenant_id,module_id),CHECK(valid_from<valid_until));
CREATE TABLE module_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 tenant_id TEXT NOT NULL,module_id TEXT NOT NULL,action TEXT NOT NULL,
 old_until INTEGER,new_until INTEGER,occurred_at INTEGER NOT NULL);
CREATE TRIGGER module_events_immutable_update BEFORE UPDATE ON module_events
BEGIN SELECT RAISE(ABORT,'MODULE_EVENT_APPEND_ONLY'); END;
CREATE TRIGGER module_events_immutable_delete BEFORE DELETE ON module_events
BEGIN SELECT RAISE(ABORT,'MODULE_EVENT_APPEND_ONLY'); END;
"""
def _id(v):
 if not valid_id(v):raise ValueError("INVALID_TENANT_OR_MODULE_ID")
 return v
def connect(path=":memory:"):
 db=sqlite3.connect(path)
 try:
  db.execute("PRAGMA foreign_keys=ON")
  actual=db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
  if actual:
   expected={"module_prices","module_entitlements","module_events"}
   # Compatible with the additive multi-Offer extension; legacy DBs stay valid.
   offer_tables={"saas_offer_versions","saas_offer_lines","saas_quotes"}
   actual_names={row[0] for row in actual}
   allowed=(actual_names==expected or actual_names==expected|offer_tables)
   if not allowed or db.execute("PRAGMA user_version").fetchone()[0]!=1:
    raise ValueError("UNRECOGNIZED_MODULE_DATABASE")
  else:
   if db.execute("PRAGMA user_version").fetchone()[0]!=0:
    raise ValueError("UNRECOGNIZED_MODULE_DATABASE")
   db.executescript("BEGIN IMMEDIATE;"+SCHEMA+"PRAGMA user_version=1;COMMIT;")
  return db
 except BaseException:
  db.close()
  raise
def catalog():
 return [{"id":key,"title":item["title"],"entrypoint":item["entrypoint"],
          "dependencies":list(item["dependencies"]),"capabilities":list(item["capabilities"])}
          for key,item in sorted(MODULES.items())]
def set_price(db,module_id,version,cny_minor,usd_minor,period_days,active=True):
 if module_id not in MODULES or any(type(v) is not int for v in (version,cny_minor,usd_minor,period_days)) or version<1 or min(cny_minor,usd_minor)<0 or period_days<1 or type(active) is not bool:
  raise ValueError("INVALID_MODULE_PRICE")
 with db:
  db.execute("INSERT INTO module_prices VALUES(?,?,?,?,?,?)",
   (module_id,version,cny_minor,usd_minor,period_days,int(active)))
def offers(db):
 result=[]
 for module in catalog():
  row=db.execute("SELECT version,cny_minor,usd_minor,period_days FROM module_prices "
    "WHERE module_id=? AND active=1 ORDER BY version DESC LIMIT 1",(module["id"],)).fetchone()
  result.append({**module,"offer":None if row is None else
   {"version":row[0],"cny_minor":row[1],"usd_minor":row[2],"period_days":row[3]}})
 return result
def entitled(db,tenant_id,module_id,at):
 _id(tenant_id)
 if module_id not in MODULES or type(at) is not int or at<0:
  raise ValueError("INVALID_ENTITLEMENT_LOOKUP")
 row=db.execute("SELECT valid_from,valid_until FROM module_entitlements WHERE tenant_id=? AND module_id=?",
   (tenant_id,module_id)).fetchone()
 return row is not None and row[0]<=at<row[1]
def capability_allowed(db,tenant_id,capability,at):
 if capability not in CAPABILITIES:raise ValueError("UNKNOWN_CAPABILITY")
 module_id=CAPABILITIES[capability]
 seen=set()
 def check(code):
  if code in seen:raise ValueError("CYCLIC_MODULE_DEPENDENCY")
  seen.add(code)
  try:
   return entitled(db,tenant_id,code,at) and all(check(dep) for dep in MODULES[code]["dependencies"])
  finally:seen.remove(code)
 return check(module_id)
def grant(db,tenant_id,module_id,valid_from,valid_until,version,source="OFFLINE_GRANT"):
 _id(tenant_id)
 if module_id not in MODULES or source not in ("OFFLINE_GRANT","PAID_ORDER_CONFIRMED","CUSTOM_DELIVERY") or any(type(x) is not int for x in (valid_from,valid_until,version)) or valid_from<0 or valid_until<=valid_from:
  raise ValueError("INVALID_MODULE_GRANT")
 with db:
  if db.execute("SELECT 1 FROM module_prices WHERE module_id=? AND version=?",
      (module_id,version)).fetchone() is None:raise ValueError("UNKNOWN_PRICE_VERSION")
  before=db.execute("SELECT valid_until FROM module_entitlements WHERE tenant_id=? AND module_id=?",
      (tenant_id,module_id)).fetchone()
  if before and valid_until<=before[0]:raise ValueError("GRANT_MUST_EXTEND")
  db.execute("INSERT INTO module_entitlements VALUES(?,?,?,?,?,?) "
    "ON CONFLICT(tenant_id,module_id) DO UPDATE SET valid_from=excluded.valid_from, "
    "valid_until=excluded.valid_until,price_version=excluded.price_version,source=excluded.source",
    (tenant_id,module_id,valid_from,valid_until,version,source))
  db.execute("INSERT INTO module_events(tenant_id,module_id,action,old_until,new_until,occurred_at) "
    "VALUES(?,?,?,?,?,?)",(tenant_id,module_id,"GRANT" if before is None else "RENEW",
      None if before is None else before[0],valid_until,valid_from))
 return {"tenant_id":tenant_id,"module_id":module_id,"valid_until":valid_until,"module_enabled":True}
