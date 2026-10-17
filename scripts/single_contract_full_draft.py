"""Assemble a single full-length, unsigned legal draft from approved template.

Offline-only: preserves all 28 legal chapters. Selected requirements and pricing
are embedded into the corresponding chapters, never separate signed annexes.
No real identity signing, payment, procurement or legal release is permitted.
"""
import hashlib
import json
import pathlib

from single_contract_freeze import ContractHold, canonical_bytes
from single_contract_preview import render as render_plain_preview

def build_unsigned_document(candidate, repository_root):
    info=render_plain_preview(candidate)
    if info.get("content_type") != "text/plain; charset=utf-8" or info.get("signable") is not False:
        raise ContractHold("PREVIEW_NOT_SAFE")
    root=pathlib.Path(repository_root).resolve()
    registry=json.loads((root/"docs/legal/registry.json").read_text(encoding="utf-8"))
    if registry.get("production_enabled") is not False:
        raise ContractHold("REGISTRY_NOT_DRAFT_ONLY")
    entry=next((row for row in registry.get("documents",[])
                if row.get("id")=="custom-development"),None)
    if not entry or entry.get("signature_enabled") is not False:
        raise ContractHold("SIGNING_NOT_DISABLED")
    if entry.get("status") != "DRAFT_NOT_FOR_SIGNATURE":
        raise ContractHold("DOCUMENT_NOT_DRAFT")
    src=(root/"docs/legal/templates/custom-development.md").resolve()
    if src != (root/entry["source"]).resolve() or not src.is_file():
        raise ContractHold("TEMPLATE_SOURCE_MISMATCH")
    raw=src.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=entry["source_sha256"]:
        raise ContractHold("TEMPLATE_BYTES_MISMATCH")
    original=raw.decode("utf-8")
    if "二十八、单一合同版本与签署证据" not in original:
        raise ContractHold("INCOMPLETE_LEGAL_BODY")
    scope=candidate["frozen"]["scope"]
    features=candidate["frozen"]["features"]
    resources=candidate["frozen"]["resources"]
    amounts=candidate["frozen"]["payment_cny"]
    # Keep all selected fields in precisely one draft document, below legal
    # clauses where a future trusted generator will substitute full terms.
    # Never insert as Markdown: flatten fields to a single line.
    def field(text):
        if not isinstance(text,str) or not text:
            raise ContractHold("FIELD_MISSING")
        if any(ord(ch)<32 and ch not in ("\n","\t") for ch in text):
            raise ContractHold("INVALID_FIELD")
        return " ".join(text.splitlines()).replace("\t"," ")
    feature_text="；".join("%s：%s，验收：%s" % (
        field(f["feature_id"]),field(f["description"]),field(f["acceptance"]))
        for f in features)
    resource_text="；".join("%s／%s／所有权%s／CNY%s／USD%s" % (
        field(r["item_id"]),field(r["mode"]),field(r["owner"]),
        field(r["display_CNY"]),field(r["display_USD"])) for r in resources)
    if not resource_text:
        resource_text="本项目无额外第三方资源"
    data=[
        ("【按feature_id逐项生成：功能描述、业务角色、页面/接口、可测试成功与异常条件、验收用例、交付物、排除项、依赖及版本】",
         "【未验证完整范围，禁止签约】"+feature_text),
        ("【按冻结quote_version和pricebook_hash生成明细表】",
         "【仍缺完整供应商报价与双币原始凭证，禁止签约】"+resource_text+
         "；首期CNY："+amounts["first_total"]+
         "；尾款CNY："+amounts["development_final_after_acceptance_50pct"]),
    ]
    for old,new in data:
        if original.count(old)!=1:
            raise ContractHold("TEMPLATE_MARKER_CHANGED")
        original=original.replace(old,new,1)
    out=("DRAFT_NOT_FOR_SIGNATURE | COMPLETE_LEGAL_DRAFT_NOT_EXECUTABLE\n"+
         "可信身份/法律适用/完整材料/真实Finance/正式签署缺失，以下文件仅供离线预览。\n"+
         "项目："+field(scope["project_id"])+" 客户："+field(scope["verified_customer_id"])+
         " 合同："+field(scope["contract_id"])+"\n\n"+original)
    return {"text":out,"content_type":"text/plain; charset=utf-8",
            "document_sha256":hashlib.sha256(out.encode("utf-8")).hexdigest(),
            "source_template_sha256":entry["source_sha256"],
            "signable":False,"status":"DRAFT_NOT_FOR_SIGNATURE",
            "contract_sign":"HOLD","payment":"HOLD","procurement":"HOLD"}
