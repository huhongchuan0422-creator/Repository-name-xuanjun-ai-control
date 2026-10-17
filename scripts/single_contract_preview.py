"""Render an unsigned, complete single-document custom-development preview.

Offline-only presentation from an already frozen candidate. This module does not
validate signer identity, grant signature, submit payments or activate procurement.
No untrusted HTML injection: output is plain UTF-8 Markdown text.
"""
from __future__ import unicode_literals

import hashlib
from decimal import Decimal
from single_contract_freeze import ContractHold, canonical_bytes

_REQUIRED_HOLDS = ("contract_sign", "payment", "procurement", "development_start")


def render(candidate):
    if not isinstance(candidate, dict) or candidate.get("status") != "UNSIGNED_CANDIDATE_ONLY":
        raise ContractHold("UNSIGNED_CANDIDATE_REQUIRED")
    if any(candidate.get(k) != "HOLD" for k in _REQUIRED_HOLDS):
        raise ContractHold("GATE_TAMPERED")
    frozen = candidate.get("frozen")
    if not isinstance(frozen, dict):
        raise ContractHold("INVALID_FROZEN")
    digest = hashlib.sha256(canonical_bytes(frozen)).hexdigest()
    if candidate.get("contract_document_hash") != digest:
        raise ContractHold("FROZEN_HASH_MISMATCH")
    scope = frozen["scope"]
    payment = frozen["payment_cny"]
    features = frozen["features"]
    resources = frozen["resources"]
    if not features:
        raise ContractHold("FEATURES_REQUIRED")

    def plain(value):
        if not isinstance(value, str) or not value or any(ord(c) < 32 and c not in "\n\t" for c in value):
            raise ContractHold("INVALID_TEXT")
        # Escape Markdown delimiters so customer-selected text cannot forge sections.
        return value.replace("\\", "\\\\").replace("|", "\\|").replace("#", "\\#").replace("<", "&lt;").replace(">", "&gt;")

    out = [
        "# 软件与AI定制开发电子合同（唯一文件，未签署预览）",
        "",
        "**DRAFT_NOT_FOR_SIGNATURE｜本预览不可签署，不构成付款订单或采购许可。**",
        "",
        "## 一、合同身份与受控版本",
        "项目ID：" + plain(scope["project_id"]),
        "客户ID：" + plain(scope["verified_customer_id"]),
        "合同ID：" + plain(scope["contract_id"]),
        "需求版本：" + plain(scope["requirements_version"]),
        "报价版本：" + plain(scope["quote_version"]),
        "验收版本：" + plain(scope["acceptance_version"]),
        "合同数据摘要SHA256：" + digest,
        "",
        "## 二、功能范围与验收明细",
    ]
    for index, feature in enumerate(features, 1):
        out.append("%d. 功能 %s：%s；验收标准：%s" % (
            index, plain(feature["feature_id"]), plain(feature["description"]),
            plain(feature["acceptance"])))
    out += ["", "## 三、资源选择与双币展示"]
    if not resources:
        out.append("客户本次未选择额外第三方资源。")
    for index, resource in enumerate(resources, 1):
        out.append("%d. %s；方式：%s；权属：%s；人民币展示：%s；美元展示：%s" % (
            index, plain(resource["item_id"]), plain(resource["mode"]),
            plain(resource["owner"]), plain(resource["display_CNY"]),
            plain(resource["display_USD"])))
    out += [
        "", "## 四、约定付款节点（CNY）",
        "首期开发费50%：" + plain(payment["development_first_50pct"]),
        "首期代购第三方本金全额：" + plain(payment["third_party_first_full"]),
        "首期服务费、部署费及税费：" + plain(payment["agreed_services_and_tax_first"]),
        "首次合计：" + plain(payment["first_total"]),
        "最终验收合格后开发费尾款50%：" + plain(payment["development_final_after_acceptance_50pct"]),
        "",
        "## 五、授权、隐私及合同成立条件",
        "第三方费用按选择方式分别核算，自购资源不重复收本金。授权、材料、认证、密钥种类和完整功能须在唯一最终合同中列明，秘密值仅通过安全渠道提交。",
        "真正签署必须另经法定主体核验、逐项披露、有效授权、单份完整法律文本冻结、双方主动签署和送达存证。",
        "当前仅为离线报价与需求预览，真实合同条款、退款、IP、维护、适用法律及客户具体准备清单仍需从已审核的完整模板和可信项目来源合并，禁止将本预览用于客户签约。",
        "",
        "**CONTRACT_SIGN=HOLD；PAYMENT=HOLD；PROCUREMENT=HOLD。**",
    ]
    text = "\n".join(out) + "\n"
    return {"text": text, "preview_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "contract_snapshot_sha256": digest, "signable": False,
            "status": "DRAFT_NOT_FOR_SIGNATURE"}
