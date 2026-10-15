"""Offline SaaS commercial offer catalog. No payments, purchasing or finance ledger.

Offer and quote documents are immutable by version. Quotes are previews, not orders.
This adapter accepts prices explicitly; only a separate authorized Finance service
may provide a trusted FX quote or recognize revenue.
"""
import json
import sqlite3
from scripts.community_merchant_contract import valid_id
from scripts.community_saas_modules import MODULES, SCHEMA as MODULE_SCHEMA
from scripts.community_saas_schema_guard import verify,transactional_install

KINDS = frozenset(("MONTHLY", "YEARLY", "BUYOUT", "FREE", "PROMOTION", "METERED", "CUSTOM"))
COMPONENTS = frozenset(("MODULE_FEE", "SUPPLIER_COST", "AGENCY_FEE", "DEPLOYMENT", "MAINTENANCE", "TAX", "PAYMENT_FX", "OTHER"))
CYCLES = frozenset(("ONCE", "MONTH", "YEAR", "USAGE"))
SCHEMA = """
CREATE TABLE IF NOT EXISTS saas_offer_versions (
 offer_id TEXT NOT NULL, version INTEGER NOT NULL CHECK(version>0),
 module_id TEXT NOT NULL, kind TEXT NOT NULL, tenant_scope TEXT,
 term_days INTEGER, active INTEGER NOT NULL CHECK(active IN (0,1)),
 supplier_payment TEXT NOT NULL CHECK(supplier_payment IN ('PLATFORM','CUSTOMER','NONE')),
 PRIMARY KEY(offer_id,version));
CREATE TABLE IF NOT EXISTS saas_offer_lines (
 offer_id TEXT NOT NULL, version INTEGER NOT NULL,
 line_no INTEGER NOT NULL CHECK(line_no>0), type TEXT NOT NULL,
 label TEXT NOT NULL, cycle TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity>0),
 cny_minor INTEGER, usd_minor INTEGER, cost_cny_minor INTEGER, cost_usd_minor INTEGER,
 PRIMARY KEY(offer_id,version,line_no),
 FOREIGN KEY(offer_id,version) REFERENCES saas_offer_versions(offer_id,version));
CREATE TABLE IF NOT EXISTS saas_quotes (
 quote_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
 offer_id TEXT NOT NULL, offer_version INTEGER NOT NULL,
 created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
 fx_source TEXT, fx_at INTEGER, snapshot TEXT NOT NULL,
 FOREIGN KEY(offer_id,offer_version) REFERENCES saas_offer_versions(offer_id,version),
 CHECK(expires_at>created_at));
CREATE TRIGGER IF NOT EXISTS saas_quote_no_update BEFORE UPDATE ON saas_quotes
 BEGIN SELECT RAISE(ABORT,'IMMUTABLE_QUOTE'); END;
CREATE TRIGGER IF NOT EXISTS saas_quote_no_delete BEFORE DELETE ON saas_quotes
 BEGIN SELECT RAISE(ABORT,'IMMUTABLE_QUOTE'); END;
CREATE TRIGGER IF NOT EXISTS saas_offer_no_update BEFORE UPDATE ON saas_offer_versions
 BEGIN SELECT RAISE(ABORT,'IMMUTABLE_OFFER'); END;
CREATE TRIGGER IF NOT EXISTS saas_offer_no_delete BEFORE DELETE ON saas_offer_versions
 BEGIN SELECT RAISE(ABORT,'IMMUTABLE_OFFER'); END;
CREATE TRIGGER IF NOT EXISTS saas_line_no_update BEFORE UPDATE ON saas_offer_lines
 BEGIN SELECT RAISE(ABORT,'IMMUTABLE_OFFER_LINE'); END;
CREATE TRIGGER IF NOT EXISTS saas_line_no_delete BEFORE DELETE ON saas_offer_lines
 BEGIN SELECT RAISE(ABORT,'IMMUTABLE_OFFER_LINE'); END;
CREATE TRIGGER saas_offer_versions_no_replace BEFORE INSERT ON saas_offer_versions
WHEN EXISTS(SELECT 1 FROM saas_offer_versions WHERE offer_id=NEW.offer_id AND version=NEW.version)
BEGIN SELECT RAISE(ABORT,'IMMUTABLE_CONFLICT'); END;
CREATE TRIGGER saas_offer_lines_no_replace BEFORE INSERT ON saas_offer_lines
WHEN EXISTS(SELECT 1 FROM saas_offer_lines WHERE offer_id=NEW.offer_id AND version=NEW.version AND line_no=NEW.line_no)
BEGIN SELECT RAISE(ABORT,'IMMUTABLE_CONFLICT'); END;
CREATE TRIGGER saas_quotes_no_replace BEFORE INSERT ON saas_quotes
WHEN EXISTS(SELECT 1 FROM saas_quotes WHERE quote_id=NEW.quote_id)
BEGIN SELECT RAISE(ABORT,'IMMUTABLE_CONFLICT'); END;
"""
def install(db):
    """Add offer extension to an existing trusted module database transactionally.

    Does not create a second wallet, ledger or FX service.
    """
    if not isinstance(db, sqlite3.Connection):
        raise TypeError("SQLITE_CONNECTION_REQUIRED")
    db.execute("PRAGMA foreign_keys=ON")
    base={"module_prices","module_entitlements","module_events"}
    ext={"saas_offer_versions","saas_offer_lines","saas_quotes"}
    names={row[0] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    if names==base:
        verify(db,MODULE_SCHEMA,base)
        transactional_install(db,SCHEMA,
            lambda:verify(db,MODULE_SCHEMA,base|ext,extra_schema=SCHEMA))
    elif names==base|ext:
        verify(db,MODULE_SCHEMA,base|ext,extra_schema=SCHEMA)
    else:
        raise ValueError("UNRECOGNIZED_OFFER_INSTALL_SCHEMA")

def _identifier(value):
    if type(value) is not str or not valid_id(value):
        raise ValueError("INVALID_IDENTIFIER")
    return value

def _money(value):
    if value is not None and (type(value) is not int or value < 0):
        raise ValueError("INVALID_MONEY")
    return value

def _line(line):
    if type(line) is not dict:
        raise ValueError("INVALID_LINE")
    typ, cycle = line.get("type"), line.get("cycle")
    if typ not in COMPONENTS or cycle not in CYCLES:
        raise ValueError("INVALID_LINE_CLASS")
    label=line.get("label")
    qty=line.get("quantity",1)
    if type(label) is not str or not label.strip() or len(label)>160 or type(qty) is not int or qty<1:
        raise ValueError("INVALID_LINE")
    cny=_money(line.get("cny_minor")); usd=_money(line.get("usd_minor"))
    cost_cny=_money(line.get("cost_cny_minor"));cost_usd=_money(line.get("cost_usd_minor"))
    # The absence of supplier price is UNKNOWN rather than free.
    if (cny is None or usd is None) and typ != "SUPPLIER_COST":
        raise ValueError("UNKNOWN_CUSTOMER_PRICE")
    return (typ,label,cycle,qty,cny,usd,cost_cny,cost_usd)

def create_offer(db, offer_id, version, module_id, kind, lines,
                 term_days=None, tenant_scope=None, supplier_payment="NONE"):
    _identifier(offer_id)
    if module_id not in MODULES or type(version) is not int or version<1 or kind not in KINDS:
        raise ValueError("INVALID_OFFER")
    if type(lines) not in (tuple,list) or not lines:
        raise ValueError("EMPTY_OFFER_LINES")
    if term_days is not None and (type(term_days) is not int or term_days<1):
        raise ValueError("INVALID_TERM")
    if kind in ("MONTHLY","YEARLY") and term_days is None:
        raise ValueError("TERM_REQUIRED")
    if kind in ("BUYOUT","FREE") and term_days is not None:
        raise ValueError("INVALID_PERPETUAL_TERM")
    if tenant_scope is not None:_identifier(tenant_scope)
    if supplier_payment not in ("NONE","PLATFORM","CUSTOMER"):
        raise ValueError("INVALID_SUPPLIER_PAYMENT")
    parsed=[_line(line) for line in lines]
    if kind=="FREE" and any(p[4]!=0 or p[5]!=0 for p in parsed):
        raise ValueError("FREE_MUST_BE_ZERO")
    if supplier_payment=="CUSTOMER" and any(p[0]=="SUPPLIER_COST" and (p[4] not in (0,None) or p[5] not in (0,None)) for p in parsed):
        raise ValueError("SUPPLIER_DOUBLE_CHARGE")
    with db:
        db.execute("INSERT INTO saas_offer_versions VALUES(?,?,?,?,?,?,?,?)",
                   (offer_id,version,module_id,kind,tenant_scope,term_days,1,supplier_payment))
        db.executemany("INSERT INTO saas_offer_lines VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       [(offer_id,version,i,*row) for i,row in enumerate(parsed,1)])
    return (offer_id,version)

def get_offer(db,offer_id,version):
    _identifier(offer_id)
    if type(version) is not int or version<1:raise ValueError("INVALID_VERSION")
    row=db.execute("SELECT module_id,kind,tenant_scope,term_days,active,supplier_payment "
                   "FROM saas_offer_versions WHERE offer_id=? AND version=?",(offer_id,version)).fetchone()
    if row is None:raise ValueError("UNKNOWN_OFFER")
    lines=db.execute("SELECT line_no,type,label,cycle,quantity,cny_minor,usd_minor,cost_cny_minor,cost_usd_minor "
                     "FROM saas_offer_lines WHERE offer_id=? AND version=? ORDER BY line_no",(offer_id,version)).fetchall()
    return {"offer_id":offer_id,"version":version,"module_id":row[0],"kind":row[1],
            "tenant_scope":row[2],"term_days":row[3],"active":bool(row[4]),
            "supplier_payment":row[5],
            "lines":[dict(zip(("line_no","type","label","cycle","quantity","cny_minor","usd_minor","cost_cny_minor","cost_usd_minor"),v)) for v in lines]}

def list_offers(db,module_id,tenant_id=None):
    if module_id not in MODULES:raise ValueError("UNKNOWN_MODULE")
    if tenant_id is not None:_identifier(tenant_id)
    rows=db.execute("SELECT offer_id,version FROM saas_offer_versions WHERE module_id=? "
                    "AND (tenant_scope IS NULL OR tenant_scope=?) ORDER BY offer_id,version",
                    (module_id,tenant_id)).fetchall()
    return [get_offer(db,*row) for row in rows]

def quote(db,quote_id,tenant_id,offer_id,version,created_at,expires_at,
          fx_source=None,fx_at=None):
    _identifier(quote_id);_identifier(tenant_id)
    if any(type(v) is not int for v in (created_at,expires_at)) or created_at<0 or expires_at<=created_at:
        raise ValueError("INVALID_QUOTE_TIME")
    if (fx_source is None)!=(fx_at is None) or (fx_at is not None and (type(fx_at) is not int or fx_at<0)):
        raise ValueError("INVALID_FX_EVIDENCE")
    offer=get_offer(db,offer_id,version)
    if not offer["active"] or offer["tenant_scope"] not in (None,tenant_id):
        raise ValueError("OFFER_NOT_AVAILABLE")
    # Prices are configured in both currencies. No implicit exchange rate is invented.
    totals={}
    for currency in ("cny","usd"):
        vals=[(line[currency+"_minor"],line["quantity"]) for line in offer["lines"]]
        totals[currency+"_minor"]=None if any(v is None for v,q in vals) else sum(v*q for v,q in vals)
    # Never present a sum of one-time, monthly and usage fees as an amount due.
    # Keep legacy all-line totals for compatibility, but mark them NON_PAYABLE.
    breakdown={}
    for cycle in sorted(CYCLES):
        selected=[line for line in offer["lines"] if line["cycle"]==cycle]
        if not selected:
            continue
        breakdown[cycle]={}
        for currency in ("cny","usd"):
            values=[line[currency+"_minor"] for line in selected]
            breakdown[cycle][currency+"_minor"]=(
                None if any(value is None for value in values)
                else sum(line[currency+"_minor"]*line["quantity"] for line in selected))
    mixed_cycles=len(breakdown)>1
    snapshot={**offer,"tenant_id":tenant_id,"created_at":created_at,"expires_at":expires_at,
              "fx_source":fx_source,"fx_at":fx_at,"totals":totals,
              "totals_by_cycle":breakdown,"mixed_billing_cycles":mixed_cycles,
              "totals_are_payable":False,
              "payment_authorized":False,"procurement_authorized":False,
              "revenue_recognized":False}
    with db:
        db.execute("INSERT INTO saas_quotes VALUES(?,?,?,?,?,?,?, ?,?)",
                   (quote_id,tenant_id,offer_id,version,created_at,expires_at,fx_source,fx_at,
                    json.dumps(snapshot,ensure_ascii=False,sort_keys=True,separators=(",",":"))))
    return snapshot

def read_quote(db,quote_id,tenant_id):
    _identifier(quote_id);_identifier(tenant_id)
    row=db.execute("SELECT snapshot FROM saas_quotes WHERE quote_id=? AND tenant_id=?",
                   (quote_id,tenant_id)).fetchone()
    if row is None:raise ValueError("QUOTE_NOT_FOUND")
    return json.loads(row[0])
