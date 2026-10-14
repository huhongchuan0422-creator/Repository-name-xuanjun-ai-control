"""Offline Stage5 merchant storefront, QR, routing and split contracts.
No payment provider, signature/key discovery, server, deployment or database.
"""
import hashlib
import hmac
import json
import re
from urllib.parse import urlsplit

ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
CHANNELS = {"mini", "official_h5"}
PAGES = {"storefront", "amount", "pending", "result"}
def valid_id(value):
    return isinstance(value, str) and bool(ID.fullmatch(value))
def scope(value):
    if not isinstance(value, dict) or set(value) != {"tenant_id", "merchant_id", "store_id"}:
        raise ValueError("INVALID_SCOPE")
    if not all(valid_id(x) for x in value.values()): raise ValueError("INVALID_SCOPE")
    return tuple(value[k] for k in ("tenant_id", "merchant_id", "store_id"))
def text_ok(v,n):
    return isinstance(v,str) and 1 <= len(v) <= n and not any(ord(c)<32 for c in v)
def storefront(identity,profile):
    scope(identity)
    if not isinstance(profile,dict) or set(profile)!={"name","description","contact","status"} or profile["status"]!="ACTIVE" or not text_ok(profile["name"],120) or not text_ok(profile["description"],2048) or not text_ok(profile["contact"],120):
        raise ValueError("UNAVAILABLE_STOREFRONT")
    return {"scope":dict(identity),"name":profile["name"],"description":profile["description"],"contact":profile["contact"],"render_escape_required":True}
def opening_hours(identity,store,weekday,minute):
    scope(identity)
    if not isinstance(store,dict) or scope(store.get("scope"))!=scope(identity) or type(weekday) is not int or not 0<=weekday<=6 or type(minute) is not int or not 0<=minute<1440:
        raise ValueError("INVALID_HOURS_INPUT")
    ranges=store.get("hours")
    if not isinstance(ranges,list) or len(ranges)>16: raise ValueError("INVALID_HOURS")
    for item in ranges:
        if not isinstance(item,dict) or set(item)!={"weekday","start","end"} or any(type(item[k]) is not int for k in item) or not 0<=item["weekday"]<=6 or not 0<=item["start"]<item["end"]<=1440:
            raise ValueError("INVALID_HOURS")
    return any(x["weekday"]==weekday and x["start"]<=minute<x["end"] for x in ranges)
def catalog(identity,items,limit=100):
    scope(identity)
    if not isinstance(items,list) or len(items)>1000 or type(limit) is not int or not 1<=limit<=100: raise ValueError("INVALID_CATALOG")
    selected=[]
    for item in items:
        if not isinstance(item,dict) or set(item)!={"scope","id","name","status","sort"} or scope(item["scope"])!=scope(identity) or not valid_id(item["id"]) or not text_ok(item["name"],120) or item["status"] not in ("ACTIVE","HIDDEN") or type(item["sort"]) is not int:
            raise ValueError("INVALID_CATALOG_ITEM")
        if item["status"]=="ACTIVE": selected.append({"id":item["id"],"name":item["name"],"sort":item["sort"]})
    if len({x["id"] for x in selected})!=len(selected): raise ValueError("DUPLICATE_CATALOG_ID")
    return sorted(selected,key=lambda x:(x["sort"],x["id"]))[:limit]
def signed_qr(identity,context,expires,key):
    scope(identity)
    if not valid_id(context) or type(expires) is not int or expires<=0 or not isinstance(key,bytes) or len(key)<32:
        raise ValueError("INVALID_QR_REQUEST")
    payload={"scope":identity,"context":context,"expires":expires,"version":1}
    raw=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()
    return {"payload":payload,"signature":hmac.new(key,raw,hashlib.sha256).hexdigest()}
def verify_qr(token,identity,context,now,key):
    scope(identity)
    if not isinstance(token,dict) or set(token)!={"payload","signature"} or not isinstance(token["payload"],dict) or not isinstance(key,bytes) or len(key)<32 or type(now) is not int:
        return False
    p=token["payload"]
    if set(p)!={"scope","context","expires","version"} or p["scope"]!=identity or p["context"]!=context or p["version"]!=1 or type(p["expires"]) is not int or p["expires"]<=now or not isinstance(token["signature"],str):
        return False
    raw=json.dumps(p,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()
    return hmac.compare_digest(hmac.new(key,raw,hashlib.sha256).hexdigest(),token["signature"])
def payment_amount(amount_minor,currency,reference):
    if type(amount_minor) is not int or not 1<=amount_minor<=100000000 or currency!="CNY" or not valid_id(reference):
        raise ValueError("INVALID_PAYMENT_AMOUNT")
    return {"amount_minor":amount_minor,"currency":currency,"reference":reference,"provider_payment_started":False}
def route(channel,page,identity):
    scope(identity)
    if channel not in CHANNELS or page not in PAGES: raise ValueError("INVALID_CHANNEL_ROUTE")
    return {"channel":channel,"page":page,"scope":dict(identity),"external_payment_navigation":False}
def merchant_authorized(actor,identity,action):
    t,m,s=scope(identity)
    if not isinstance(actor,dict) or actor.get("authenticated") is not True or actor.get("tenant_id")!=t or actor.get("merchant_id")!=m: return False
    if action=="VIEW": return actor.get("role") in ("MERCHANT_ADMIN","STORE_STAFF") and (actor.get("role")=="MERCHANT_ADMIN" or actor.get("store_id")==s)
    if action=="EDIT": return actor.get("role")=="MERCHANT_ADMIN" or (actor.get("role")=="STORE_STAFF" and actor.get("store_id")==s and actor.get("can_edit") is True)
    return False
def platform_authorized(actor,action):
    if not isinstance(actor,dict) or actor.get("authenticated") is not True: return False
    if action=="MERCHANT_APPROVAL": return actor.get("role")=="PLATFORM_REVIEWER"
    if action=="SPLIT_APPROVAL": return actor.get("role")=="FINANCE_APPROVER" and actor.get("second_factor") is True
    return False
def split_amounts(amount_minor,shares,refund_minor=0):
    if type(amount_minor) is not int or amount_minor<0 or type(refund_minor) is not int or not 0<=refund_minor<=amount_minor or not isinstance(shares,dict) or not 1<=len(shares)<=20 or any(not valid_id(k) or type(v) is not int or v<0 for k,v in shares.items()):
        raise ValueError("INVALID_SPLIT")
    available=amount_minor-refund_minor
    if sum(shares.values())!=10000: raise ValueError("INVALID_BASIS_POINTS")
    rows={k:available*v//10000 for k,v in sorted(shares.items())}
    rest=available-sum(rows.values())
    # Largest remainder method; deterministic tie-breaking by beneficiary ID.
    if rest:
        ranks=sorted(shares,key=lambda k:(-(available*shares[k]%10000),k))
        for k in ranks[:rest]: rows[k]+=1
    if sum(rows.values())!=available: raise ValueError("SPLIT_CONSERVATION")
    return {"shares_minor":rows,"refunded_minor":refund_minor,"allocatable_minor":available,"provider_settlement_verified":False}
