#!/usr/bin/env python3
"""Kho phê duyệt và whitelist — phần "hệ tự học" của guardrail (§5).

Hai đồng hồ tách biệt (G11):
  · yêu cầu duyệt  sống 12 giờ  — admin còn ngủ, không được tự từ chối lúc nửa đêm
  · token sau khi bấm nút sống 10 phút, dùng đúng một lần

Whitelist (G7/G8/G9):
  · chỉ áp dụng cho riskTier = write; irreversible không bao giờ whitelist được
  · luôn có hạn dùng, luôn có scope hẹp
  · scope hẹp tới đâu là do CHÍNH COMPANY khai báo trong `whitelistScope`;
    capability không khai thì không whitelist được — mặc định an toàn
"""
import hashlib
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import db  # noqa: E402
BACKOFFICE = os.path.join(ROOT, "backOffice", "store.sqlite")
WHITELIST = os.path.join(ROOT, "registry", "whitelist.jsonl")
GATEWAY_YAML = os.path.join(ROOT, "registry", "gateway.yaml")
GATEWAY_LOCAL = os.path.join(ROOT, "registry", "gateway.local.yaml")


def now_dt():
    return datetime.now(timezone.utc)


def now() -> str:
    return now_dt().strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(ts: str):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def new_id(prefix: str) -> str:
    raw = f"{time.time_ns()}{os.urandom(5).hex()}"
    return f"{prefix}_{hashlib.sha1(raw.encode()).hexdigest()[:16]}"


def config() -> dict:
    """gateway.yaml là bản gốc; gateway.local.yaml và biến môi trường đè lên (F6)."""
    with open(GATEWAY_YAML, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    if os.path.isfile(GATEWAY_LOCAL):
        with open(GATEWAY_LOCAL, encoding="utf-8") as fh:
            local = yaml.safe_load(fh) or {}
        for key, val in local.items():
            if isinstance(val, dict) and isinstance(cfg.get(key), dict):
                cfg[key].update(val)
            else:
                cfg[key] = val
    env_chat = os.environ.get("COMPANYSPEC_ADMIN_CHAT_ID")
    if env_chat:
        cfg["adminChatId"] = int(env_chat)
    return cfg


def store():
    conn = db.connect(BACKOFFICE)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS approvalRequest (
          approvalId       TEXT PRIMARY KEY,
          traceId          TEXT NOT NULL,
          sessionId        TEXT,
          companyId        TEXT NOT NULL,
          capability       TEXT NOT NULL,
          inputJson        TEXT NOT NULL,
          payloadHash      TEXT NOT NULL,
          riskTier         TEXT NOT NULL,
          consequence      TEXT NOT NULL,
          status           TEXT NOT NULL,
          decidedAt        TEXT,
          tokenExpiresAt   TEXT,
          requestExpiresAt TEXT NOT NULL,
          createdAt        TEXT NOT NULL
        );
        """
    )
    return conn


# ───────────────────────── yêu cầu duyệt ─────────────────────────

def create_request(trace_id, session_id, company_id, capability, inp,
                   payload_hash, risk_tier, consequence) -> str:
    """Tạo yêu cầu duyệt. Đã có phiếu y hệt đang treo thì DÙNG LẠI phiếu đó.

    VÌ SAO: trước đây hàm này luôn INSERT dòng mới. CEO gọi lại cùng một việc —
    vì tưởng lần trước hỏng, vì đang thử lại, vì bất cứ lý do gì — là admin nhận
    thêm một nút duyệt nữa cho CÙNG một khoản tiền. Bấm cả hai thì ghi hai lần.

    Đo được 2026-08-06: hai phiếu cùng xin ghi 228.000đ "công việc", cách nhau
    2 phút 24 giây, từ cùng một phiên. Admin nhìn vào không có cách nào biết đó
    là một khoản hay hai khoản.

    payloadHash đã băm sẵn company+capability+input nên trùng hash là trùng việc.
    Chỉ gộp phiếu còn `pending` và chưa hết hạn: phiếu đã dùng, đã từ chối hay đã
    quá hạn thì lần xin sau là một lần xin thật, phải hỏi lại.
    """
    cfg = config()
    conn = store()
    cu = conn.execute(
        "SELECT approvalId FROM approvalRequest WHERE companyId=? AND capability=? "
        "AND payloadHash=? AND status='pending' AND requestExpiresAt > ? "
        "ORDER BY rowid DESC LIMIT 1",
        (company_id, capability, payload_hash, now()),
    ).fetchone()
    if cu:
        # Gộp phiếu, nhưng phải KÉO NÓ SANG lượt đang hỏi.
        #
        # Gateway chỉ gắn nút cho phiếu `sessionId` khớp phiên hiện tại VÀ
        # `createdAt` nằm trong lượt này (pending_for_session). Trả về phiếu cũ
        # mà không đổi hai trường đó thì admin nhận được câu "xin duyệt" KHÔNG
        # CÓ NÚT NÀO — kẹt hẳn, phải tự gõ /duyet mới bấm được.
        # Đo được 2026-08-08 07:14: CEO xin duyệt đăng bài, tin nhắn về trơ mỗi
        # mã phiếu.
        #
        # Vẫn đúng một dòng trong sổ nên tính chất quan trọng nhất — không bao
        # giờ ghi trùng tiền — được giữ nguyên. Hạn cũng đẩy lại từ bây giờ:
        # admin đang được hỏi lúc này, không phải lúc lần đầu.
        expires = now_dt() + timedelta(hours=cfg["approval"]["requestTtlHours"])
        conn.execute(
            "UPDATE approvalRequest SET sessionId=?, traceId=?, createdAt=?, "
            "requestExpiresAt=? WHERE approvalId=?",
            (session_id, trace_id, now(),
             expires.strftime("%Y-%m-%dT%H:%M:%SZ"), cu["approvalId"]),
        )
        conn.commit()
        conn.close()
        return cu["approvalId"]

    approval_id = new_id("apr")
    expires = now_dt() + timedelta(hours=cfg["approval"]["requestTtlHours"])
    conn.execute(
        "INSERT INTO approvalRequest (approvalId, traceId, sessionId, companyId, "
        "capability, inputJson, payloadHash, riskTier, consequence, status, "
        "requestExpiresAt, createdAt) VALUES (?,?,?,?,?,?,?,?,?,'pending',?,?)",
        (approval_id, trace_id, session_id, company_id, capability,
         json.dumps(inp, ensure_ascii=False), payload_hash, risk_tier,
         consequence, expires.strftime("%Y-%m-%dT%H:%M:%SZ"), now()),
    )
    conn.commit()
    conn.close()
    return approval_id


def quet_het_han() -> int:
    """Đánh dấu `expired` cho mọi phiếu `pending` đã quá hạn. Trả về số phiếu.

    VÌ SAO: trạng thái `pending` không tự hết. Phiếu quá hạn vẫn nằm đó, và
    /duyet lôi ra mời admin bấm — `max(0, …)` biến số giờ âm thành "còn 0 giờ",
    trông như một việc gấp chứ không phải một việc đã chết.

    Đo được 2026-08-08 07:22: admin gõ /duyet, nhận HAI thẻ cho cùng một bài,
    một thẻ "còn 11 giờ" và một thẻ "còn 0 giờ" — thẻ sau là phiếu từ hôm trước
    đã quá hạn 11 tiếng. Bấm nhầm thẻ đó thì chỉ nhận về lỗi.
    """
    conn = store()
    cur = conn.execute(
        "UPDATE approvalRequest SET status='expired' "
        "WHERE status='pending' AND requestExpiresAt <= ?", (now(),))
    conn.commit()
    n = cur.rowcount
    conn.close()
    return n


def get(approval_id):
    conn = store()
    row = conn.execute(
        "SELECT * FROM approvalRequest WHERE approvalId=?", (approval_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def decide(approval_id: str, decision: str):
    """decision: once | always | deny. Trả (ok, thông điệp, bản ghi)."""
    cfg = config()
    row = get(approval_id)
    if row is None:
        return False, "Yêu cầu này không tồn tại.", None
    if row["status"] != "pending":
        return False, f"Yêu cầu này đã ở trạng thái '{row['status']}', không bấm lại được.", row
    if parse(row["requestExpiresAt"]) < now_dt():
        _set(approval_id, status="expired")
        return False, "Yêu cầu đã quá hạn 12 giờ. Hãy nhắn lại từ đầu.", row

    if decision == "deny":
        _set(approval_id, status="denied", decidedAt=now())
        return True, "Đã từ chối.", row

    # G9 — irreversible không bao giờ whitelist được, kể cả khi bấm "luôn cho phép"
    if decision == "always" and row["riskTier"] != "write":
        return False, "Việc không hoàn tác được thì không có 'luôn cho phép' (G2).", row

    token_exp = now_dt() + timedelta(minutes=cfg["approval"]["tokenTtlMinutes"])
    _set(approval_id, status="approved", decidedAt=now(),
         tokenExpiresAt=token_exp.strftime("%Y-%m-%dT%H:%M:%SZ"))
    return True, "Đã duyệt.", get(approval_id)


def _set(approval_id, **fields):
    conn = store()
    cols = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE approvalRequest SET {cols} WHERE approvalId=?",
                 (*fields.values(), approval_id))
    conn.commit()
    conn.close()


def consume(approval_id: str, payload_hash: str):
    """Dispatcher gọi hàm này. Token dùng một lần và phải khớp đúng nội dung (G4)."""
    row = get(approval_id)
    if row is None:
        return False, "approvalId không tồn tại"
    if row["status"] == "used":
        return False, "token đã dùng rồi — mỗi lần duyệt chỉ chạy được một lần"
    if row["status"] != "approved":
        return False, f"yêu cầu đang ở trạng thái '{row['status']}', chưa được duyệt"
    if parse(row["tokenExpiresAt"]) < now_dt():
        _set(approval_id, status="expired")
        return False, "token đã quá hạn 10 phút — xin duyệt lại"
    if row["payloadHash"] != payload_hash:
        # G4 — xin duyệt việc vô hại rồi đổi nội dung thành việc khác
        return False, ("nội dung đã bị đổi sau khi admin duyệt — token vô hiệu")
    _set(approval_id, status="used")
    return True, f"đã duyệt qua {approval_id}"


# ───────────────────────── whitelist ─────────────────────────

def _rules():
    """Đọc file append-only. Dòng {"revoke": ruleId} thu hồi một luật."""
    if not os.path.isfile(WHITELIST):
        return []
    rules, revoked = {}, set()
    with open(WHITELIST, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            rec = json.loads(line)
            if "revoke" in rec:
                revoked.add(rec["revoke"])
            else:
                rules[rec["ruleId"]] = rec
    return [r for rid, r in rules.items() if rid not in revoked]


def active_rules():
    return [r for r in _rules() if parse(r["expiresAt"]) > now_dt()]


def scope_of(inp: dict, scope_fields):
    return {k: inp.get(k) for k in sorted(scope_fields)}


def whitelist_match(company_id, capability, inp, cap_spec):
    """G8 — khớp khi và chỉ khi mọi trường trong scope giống hệt."""
    fields = cap_spec.get("whitelistScope")
    if not fields:
        return None  # capability không khai thì không whitelist được
    want = scope_of(inp, fields)
    # G8 — phạm vi rỗng thì KHÔNG khớp gì cả. Nếu lời gọi không nêu trường dùng
    # làm phạm vi, `want` có giá trị None, và một rule cũ cũng None sẽ khớp với
    # MỌI lời gọi thiếu trường đó — quyền hẹp biến thành quyền rộng mà không ai
    # bấm nút nào. Thà hỏi lại admin còn hơn tự nới.
    if any(v is None for v in want.values()):
        return None
    for rule in active_rules():
        if rule["companyId"] == company_id and rule["capability"] == capability \
                and rule["scope"] == want:
            return rule
    return None


def whitelist_add(company_id, capability, inp, cap_spec, approval_id):
    cfg = config()["whitelist"]
    fields = cap_spec.get("whitelistScope")
    if not fields:
        return None, (f"'{capability}' không khai báo whitelistScope nên không thể "
                      "'luôn cho phép'. Mỗi lần vẫn phải duyệt.")
    scope = scope_of(inp, fields)
    thieu = [k for k, v in scope.items() if v is None]
    if thieu:
        # Không cấp một quyền mà chính ta không mô tả nổi phạm vi. Xảy ra khi
        # whitelistScope trỏ vào trường không bắt buộc và lời gọi bỏ trống nó.
        return None, (f"lời gọi này không nêu {', '.join(thieu)}, nên 'luôn cho phép' "
                      "sẽ rộng hơn đại ca định — nó khớp cả những lần sau cũng bỏ trống. "
                      "Em chỉ duyệt lần này thôi.")
    rule = {
        "ruleId": new_id("wl"),
        "companyId": company_id,
        "capability": capability,
        "scope": scope,
        "maxPerDay": cfg["defaultMaxPerDay"],
        # G7 — quyền không bao giờ vĩnh viễn
        "expiresAt": (now_dt() + timedelta(days=cfg["defaultDays"]))
                     .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "createdFromApprovalId": approval_id,
        "createdAt": now(),
    }
    os.makedirs(os.path.dirname(WHITELIST), exist_ok=True)
    with open(WHITELIST, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rule, ensure_ascii=False) + "\n")
    return rule, None


def whitelist_revoke(rule_id: str):
    with open(WHITELIST, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"revoke": rule_id, "revokedAt": now()}) + "\n")


def used_today(company_id, capability) -> int:
    conn = store()
    today = now_dt().strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT COUNT(*) c FROM taskLog WHERE companyId=? AND capability=? "
        "AND status='ok' AND startedAt LIKE ?",
        (company_id, capability, f"{today}%"),
    ).fetchone()
    conn.close()
    return row["c"]
