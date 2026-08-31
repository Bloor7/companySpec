#!/usr/bin/env python3
"""dispatcher — điểm nghẽn cố ý (T2). Mọi lời gọi company đi qua đúng chỗ này.

Đây là code cứng. Nó nói KHÔNG, và CEO không đi vòng qua được (P1, P2).
Thứ tự kiểm tra — hỏng ở bước nào thì dừng ở bước đó:

  1. C2.1  company phải có companySpec.yaml
  2. C2.2  năng lực phải được khai báo
  3. C2.3  input phải khớp inputSchema
  4. L3    còn hạn deadline
  5. L4    loopGuard — không lặp lại cùng một lời gọi
  6. G3    riskTier đọc từ manifest trên đĩa, KHÔNG đọc từ envelope
  7. G4    write/irreversible phải có approvalToken khớp payloadHash
  8. ...   chạy company
  9. C2.3  output phải khớp outputSchema
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import approvals  # noqa: E402  (cùng thư mục ops/)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPANIES = os.path.join(ROOT, "companies")
sys.path.insert(0, os.path.join(ROOT, "lib"))
import db  # noqa: E402
BACKOFFICE = os.path.join(ROOT, "backOffice", "store.sqlite")

LOOP_GUARD_MAX = 2  # L4 — cùng dấu vân tay quá số này trong một trace là chặn


# ────────────────────────── tiện ích ──────────────────────────

def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(prefix: str) -> str:
    raw = f"{time.time_ns()}{os.urandom(5).hex()}"
    return f"{prefix}_{hashlib.sha1(raw.encode()).hexdigest()[:20]}"


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def so_tien_that(conn=None):
    """Mở sổ TIỀN THẬT. Tách bảng riêng, không trộn vào taskLog.

    taskLog ghi `costUsd` — đó là hạn mức gói Pro, thứ dùng hết thì thôi. Tiền
    ở đây trừ vào thẻ của admin. Trộn hai loại vào một cột thì đến lúc đối
    chiếu hoá đơn không tách ra được, mà đối chiếu hoá đơn chính là lý do tồn
    tại của cái sổ này (admin bị Google AI Studio trừ 144.000đ, 2026-08).
    """
    c = conn or db.connect(BACKOFFICE)
    c.execute(
        """CREATE TABLE IF NOT EXISTS chiTieuNgoai (
          chiId INTEGER PRIMARY KEY AUTOINCREMENT, taskId TEXT, traceId TEXT,
          companyId TEXT NOT NULL, capability TEXT NOT NULL,
          nhaCungCap TEXT, soTienVnd REAL NOT NULL, ghiChu TEXT,
          createdAt TEXT NOT NULL)"""
    )
    return c


def chi_tieu_ngoai_thang() -> float:
    """Tổng tiền thật đã tiêu trong THÁNG DƯƠNG hiện tại.

    Theo tháng vì hoá đơn của nhà cung cấp cũng theo tháng — admin đối chiếu
    được. Cửa sổ trượt 30 ngày thì đẹp về kỹ thuật nhưng không khớp với thứ
    admin nhìn thấy khi mở bảng thanh toán ra.
    """
    dau_thang = datetime.now(timezone.utc).strftime("%Y-%m-01T00:00:00Z")
    conn = so_tien_that()
    tong = conn.execute(
        "SELECT COALESCE(SUM(soTienVnd), 0) FROM chiTieuNgoai WHERE createdAt >= ?",
        (dau_thang,)).fetchone()[0]
    conn.close()
    return float(tong or 0)


def payload_hash(company_id: str, capability: str, inp: dict) -> str:
    """G4 — token gắn với ĐÚNG lời gọi đã hiện cho admin xem.
    Đổi một ký tự trong input là hash sai, token vô hiệu."""
    return hashlib.sha256(
        f"{company_id}|{capability}|{canonical(inp)}".encode()
    ).hexdigest()[:16]


# ────────────────── validator tối giản (không cần thư viện ngoài) ──────────────────

def validate(value, schema, path="input"):
    """Trả về danh sách lỗi. Đủ dùng cho tập con schema mà dự án này khai báo."""
    errs = []
    t = schema.get("type")
    types = [t] if isinstance(t, str) else (t or [])

    def is_a(kind):
        return {
            "object": lambda v: isinstance(v, dict),
            "array": lambda v: isinstance(v, list),
            "string": lambda v: isinstance(v, str),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool),
            "null": lambda v: v is None,
        }[kind](value)

    if types and not any(is_a(k) for k in types):
        return [f"{path}: cần kiểu {'/'.join(types)}, nhận được {type(value).__name__}"]

    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: phải là một trong {schema['enum']}")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errs.append(f"{path}: ngắn hơn {schema['minLength']} ký tự")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errs.append(f"{path}: dài hơn {schema['maxLength']} ký tự")
        # `pattern` — thêm 2026-08-21 cùng lúc với `hetHan` của profileCompany,
        # người dùng đầu tiên của từ khoá này. Trước đó bộ soát lặng lẽ bỏ qua
        # `pattern`, nghĩa là một luật khai trong manifest trông như đang được
        # canh mà thật ra không: `hetHan: "31/10/2026"` đi lọt qua cổng. Một
        # hàng rào giả thì hại hơn không có hàng rào, vì người đọc manifest sau
        # này sẽ tin nó. Regex hỏng thì BÁO chứ không nuốt (O10) — im lặng ở đây
        # lại đúng là cái sai vừa sửa.
        if "pattern" in schema:
            try:
                if not re.search(schema["pattern"], value):
                    errs.append(f"{path}: không đúng dạng {schema['pattern']}")
            except re.error as e:
                errs.append(f"{path}: `pattern` trong manifest hỏng ({e})")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append(f"{path}: nhỏ hơn {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errs.append(f"{path}: lớn hơn {schema['maximum']}")

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errs.append(f"{path}.{key}: thiếu trường bắt buộc")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    errs.append(f"{path}.{key}: trường không được khai báo")
        for key, sub in props.items():
            if key in value:
                errs.extend(validate(value[key], sub, f"{path}.{key}"))

    if isinstance(value, list):
        # Trần số phần tử. Không kiểm ở đây thì `maxItems` trong companySpec chỉ
        # là lời chú thích: company khai 20 bước, CEO gửi 200, và admin nhận một
        # nút duyệt cho thứ không ai đọc hết nổi.
        if "minItems" in schema and len(value) < schema["minItems"]:
            errs.append(f"{path}: cần ít nhất {schema['minItems']} phần tử, "
                        f"nhận được {len(value)}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errs.append(f"{path}: tối đa {schema['maxItems']} phần tử, "
                        f"nhận được {len(value)}")
        if "items" in schema:
            for i, item in enumerate(value):
                errs.extend(validate(item, schema["items"], f"{path}[{i}]"))

    return errs


# ────────────────────────── backOffice ──────────────────────────

def backoffice():
    conn = db.connect(BACKOFFICE)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS taskLog (
          taskId TEXT PRIMARY KEY, traceId TEXT NOT NULL, companyId TEXT NOT NULL,
          capability TEXT NOT NULL, riskTier TEXT NOT NULL, fingerprint TEXT NOT NULL,
          status TEXT NOT NULL, summary TEXT, startedAt TEXT NOT NULL,
          finishedAt TEXT, durationMs INTEGER, costUsd REAL
        );
        CREATE TABLE IF NOT EXISTS sideEffectLog (
          id INTEGER PRIMARY KEY AUTOINCREMENT, taskId TEXT NOT NULL, traceId TEXT NOT NULL,
          type TEXT NOT NULL, target TEXT, reversible INTEGER, createdAt TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ceoRunLog (
          runId INTEGER PRIMARY KEY AUTOINCREMENT, traceId TEXT NOT NULL,
          sessionId TEXT, numTurns INTEGER, durationMs INTEGER,
          cacheCreationTokens INTEGER, cacheReadTokens INTEGER,
          costUsd REAL, isError INTEGER, createdAt TEXT NOT NULL
        );
        """
    )
    return conn


def sweep_orphans(conn):
    """Đánh dấu những lời gọi kẹt ở 'running' quá lâu.

    Tiến trình company bị giết giữa chừng (restart gateway, máy sập, Ctrl+C) thì
    không ai quay lại sửa dòng taskLog — nó nằm 'running' vĩnh viễn và backOffice
    đếm sai. Không có ai canh thì phải tự dọn: quá 20 phút là chắc chắn đã chết,
    vì maxDurationSec dài nhất trong hệ là 900 giây.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=20)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    n = conn.execute(
        "UPDATE taskLog SET status='failed', "
        "summary='Tiến trình chết giữa chừng, không có kết quả', finishedAt=? "
        "WHERE status='running' AND startedAt < ?", (now(), cutoff)).rowcount
    conn.commit()   # no-op ở chế độ tự commit, giữ cho ý đồ rõ ràng
    return n


def loop_guard_count(conn, trace_id: str, fingerprint: str) -> int:
    """L4 — đếm số lần cùng một dấu vân tay THẬT SỰ CHẠY trong trace này.

    Không tính lần bị từ chối và lần chỉ hỏi duyệt: hỏi duyệt rồi được duyệt là
    một luồng hợp lệ, không phải CEO đang lặp lại chính mình.
    """
    return conn.execute(
        "SELECT COUNT(*) c FROM taskLog WHERE traceId=? AND fingerprint=? "
        "AND status NOT IN ('rejected','needsApproval')",
        (trace_id, fingerprint),
    ).fetchone()["c"]


def log_outcome(conn, task_id, trace_id, company_id, capability, risk,
                fingerprint, result):
    """O5/O6 — mọi lời gọi đều để lại dấu, kể cả lần bị chặn.
    Không có việc gì trong hệ thống không thuộc về một trace nào (T4)."""
    conn.execute(
        "INSERT OR REPLACE INTO taskLog (taskId, traceId, companyId, capability, "
        "riskTier, fingerprint, status, summary, startedAt, finishedAt, durationMs, "
        "costUsd) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (task_id, trace_id, company_id, capability, risk, fingerprint,
         result["status"], result.get("summary", ""), now(), now(),
         result.get("usage", {}).get("durationMs", 0),
         result.get("usage", {}).get("costUsd", 0.0)),
    )
    conn.commit()


# ────────────────────────── lõi ──────────────────────────

def cac_company() -> list[str]:
    """companyId đang tồn tại, trừ đồ nội bộ (C5)."""
    ten = []
    for cid in sorted(os.listdir(COMPANIES)):
        path = os.path.join(COMPANIES, cid, "companySpec.yaml")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                if not (yaml.safe_load(fh) or {}).get("internal"):
                    ten.append(cid)
        except Exception:
            continue
    return ten


def load_spec(company_id: str) -> dict:
    path = os.path.join(COMPANIES, company_id, "companySpec.yaml")
    if not os.path.isfile(path):
        # Kèm luôn danh sách company có thật — cùng lý do C2.2 kèm danh sách
        # năng lực: rẻ hơn nhiều so với để CEO đoán sai rồi gọi lại.
        #
        # Đo được 2026-08-06: CEO không biết panharmonCompany tồn tại nên đoán
        # lần lượt wordpressCompany, contentCompany, dreamCompany, blogCompany.
        # Mỗi lần chỉ nhận lại "không tồn tại" — không một gợi ý nào — nên nó cứ
        # đoán tiếp. Bốn lượt cháy sạch, rồi chạm trần --max-turns và chết giữa
        # chừng, để lại việc dở dang.
        raise FileNotFoundError(
            f"C2.1 — '{company_id}' không có companySpec.yaml → không tồn tại với "
            f"hệ thống. Đang có: {', '.join(cac_company())}. "
            f"Chạy `python3 ops/dispatch.py list` để xem từng company làm được gì."
        )
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def reject(task_id, trace_id, reason, status="rejected"):
    return {
        "taskId": task_id, "traceId": trace_id, "status": status,
        "output": None, "summary": reason, "sideEffects": [], "error": reason,
        "usage": {"steps": 0, "durationMs": 0, "costUsd": 0.0},
    }


def cmd_call(args) -> dict:
    started = time.time()
    trace_id = (args.trace or os.environ.get("COMPANYSPEC_TRACE_ID")
                or new_id("trc"))
    task_id = new_id("tsk")
    conn = backoffice()
    sweep_orphans(conn)
    risk, fingerprint = "unknown", ""

    def bail(reason, status="rejected", extra=None):
        """Từ chối, nhưng vẫn để lại dấu vết (O5). Lần bị chặn cũng là dữ liệu."""
        res = reject(task_id, trace_id, reason, status)
        if extra:
            res.update(extra)
        log_outcome(conn, task_id, trace_id, args.company, args.capability,
                    risk, fingerprint, res)
        conn.close()
        return res

    try:
        inp = json.loads(args.input)
        if not isinstance(inp, dict):
            raise ValueError("input phải là một object JSON")
    except Exception as exc:
        return bail(f"input không phải JSON hợp lệ: {exc}")

    # 1. C2.1
    try:
        spec = load_spec(args.company)
    except FileNotFoundError as exc:
        return bail(str(exc))

    # C5 — company nội bộ thì CEO không được gọi, kể cả khi đoán ra tên.
    if spec.get("internal") and not args.allow_internal:
        return bail(
            f"C5 — '{args.company}' là company nội bộ, chỉ dùng để kiểm thử. "
            "Hãy chọn company khác trong danh mục."
        )

    # 2. C2.2
    caps = {c["name"]: c for c in spec.get("capabilities", [])}
    cap = caps.get(args.capability)
    if cap is None:
        return bail(
            f"C2.2 — '{args.company}' không khai báo năng lực '{args.capability}'. "
            f"Có: {', '.join(sorted(caps)) or '(không có)'}"
        )

    # 6. G3 — riskTier LẤY TỪ MANIFEST, không lấy từ envelope
    risk = cap["riskTier"]

    # S3 — cron KHÔNG được ghi, không có ngoại lệ, không whitelist nào nâng được.
    # Kiểm ở đây chứ không tin registry/schedules.yaml: lịch là dữ liệu, dispatcher
    # là luật. Khai nhầm một lịch thành write thì bị chặn ở đây, không phải chạy
    # rồi mới biết.
    # NGOẠI LỆ DUY NHẤT, mở 2026-08-31: lời gọi mang theo PHIẾU HẸN mà admin đã
    # ký sẵn. Đó không phải "cho cron quyền ghi" — cron vẫn không có quyền gì;
    # nó chỉ mở một chữ ký của admin đúng vào giờ đã hẹn. Phiếu khoá vào đúng
    # một nội dung bằng payloadHash (G4), dùng ĐÚNG MỘT LẦN, và `consume()` từ
    # chối nếu chưa tới giờ hoặc đã quá cửa sổ. Sai thì sai đúng một lần, không
    # thành vòng lặp lúc 3h sáng.
    #
    # Whitelist thì VẪN không nâng được S3: nó là quyền đứng, không gắn với một
    # nội dung nào, nên nó mở ra một cánh cửa rộng chứ không phải một khe.
    hen_ok = False
    if args.issued_by == "scheduledTrigger" and args.approval_id:
        phieu = approvals.get(args.approval_id)
        hen_ok = bool(phieu and phieu["henLuc"])
    if args.issued_by == "scheduledTrigger" and risk != "read" and not hen_ok:
        return bail(
            f"S3 — việc định kỳ chỉ được phép ĐỌC. '{args.capability}' là "
            f"'{risk}'. Cron quan sát và chuẩn bị; muốn hành động thì chờ admin, "
            "hoặc dùng phiếu hẹn admin đã ký trước.")

    # KHÔNG CÒN CẦU DAO HẠN MỨC Ở ĐÂY — gỡ ngày 2026-08-16, admin quyết.
    #
    # Bản cũ cộng chi phí token rồi so với một ngưỡng đoán, chạm thì khoá việc
    # GHI. Sai hai tầng:
    #   · Con số không bám thực tế. `claude -p --output-format json` không trả
    #     về hạn mức còn lại, CLI cũng không có lệnh `usage` — nên "3,95/5" là
    #     hệ tự bịa từ bảng giá, không liên quan trần thật của gói Pro.
    #   · Nó chặn NGƯỢC. Chỉ chặn `write` — ghi chi tiêu, ví, việc vặt — vốn
    #     tốn $0 LLM vì company là code cứng. Thứ thật sự đốt hạn mức lại đều
    #     là `read`: nghienCuu $3,50 · auditSite $2,00. Không cái nào bị chặn.
    #
    # Thay bằng: đợi Anthropic tự nói hết hạn mức rồi BÁO admin
    # (lib/quotaSignal.py). Lúc đó CEO tự dừng vì không gọi được model nữa,
    # nên không cần ai khoá hộ; còn sổ sách vẫn ghi được bình thường vì company
    # không dùng LLM. Chi phí vẫn được đo và báo cáo, chỉ không dùng để chặn.
    # L8 — TIỀN THẬT ra ngoài. Đây mới là chỗ cầu dao có ý nghĩa: khác hạn mức
    # Pro (dùng hết thì thôi, tháng sau lại có), đây là tiền trừ vào thẻ, đo
    # được từng lời gọi và có hoá đơn đối chiếu.
    paid = cap.get("paidApi")
    if paid and not args.dry_run:
        cfg = approvals.config().get("chiTieuNgoai", {})
        tran = float(cfg.get("tranThangVnd", 0) or 0)
        da_tieu = chi_tieu_ngoai_thang()
        gia = float(paid.get("giaUocVnd", 0) or 0)
        if tran and da_tieu + gia > tran:
            return bail(
                f"L8 — tháng này đã tiêu {da_tieu:,.0f}đ tiền thật cho API ngoài, "
                f"lời gọi này ước {gia:,.0f}đ nữa là vượt trần {tran:,.0f}đ. "
                "Muốn tiêu thêm thì sửa `chiTieuNgoai.tranThangVnd` trong "
                "registry/gateway.yaml.",
                status="budgetExceeded")

    fingerprint = payload_hash(args.company, args.capability, inp)

    # 3. C2.3 vào
    errs = validate(inp, cap.get("inputSchema", {}))
    if errs:
        return bail("C2.3 — input sai schema: " + "; ".join(errs))

    # 4. L3 — hạn chót lấy từ MANIFEST, không lấy từ một con số mặc định.
    # Company biết việc của nó cần bao lâu; auditPage cần 600s còn addExpense
    # cần 20s. Ép chung một trần là hoặc cắt oan, hoặc treo vô ích.
    ttl = args.ttl or cap.get("maxDurationSec", 120)
    deadline = datetime.now(timezone.utc) + timedelta(seconds=ttl)

    # 5. L4
    seen = loop_guard_count(conn, trace_id, fingerprint)
    if seen >= LOOP_GUARD_MAX:
        return bail(
            f"L4 — lời gọi này đã chạy {seen} lần trong trace {trace_id}. "
            "Anh đang lặp lại chính mình; hãy đổi cách làm hoặc báo cáo admin."
        )

    # 7. G7 → G4 — whitelist trước, chưa khớp thì mới hỏi admin
    # `paid` cũng phải qua cửa này dù riskTier là `read`: đọc thì không đổi gì
    # của admin, nhưng vẫn TRỪ TIỀN. Rủi ro ở đây không nằm ở dữ liệu mà ở ví.
    if (risk in ("write", "irreversible") or paid) and not args.dry_run:
        granted, why = False, ""

        # G9 — irreversible không bao giờ đi đường whitelist.
        # `paid` cũng vậy, admin chốt 2026-08-16: mọi lời gọi tốn tiền thật đều
        # phải hỏi, mỗi lần. "Luôn cho phép tiêu tiền" là câu không ai muốn nói.
        if risk == "write" and not paid:
            rule = approvals.whitelist_match(args.company, args.capability, inp, cap)
            if rule:
                used = approvals.used_today(args.company, args.capability)
                if used < rule["maxPerDay"]:
                    granted, why = True, f"whitelist {rule['ruleId']} ({used + 1}/{rule['maxPerDay']} hôm nay)"
                else:
                    why = (f"whitelist {rule['ruleId']} đã hết hạn mức ngày "
                           f"({used}/{rule['maxPerDay']}) — phải hỏi lại admin")

        if not granted and args.approval_id:
            ok, msg = approvals.consume(args.approval_id, fingerprint)
            granted, why = ok, msg

        # HẸN GIỜ: không bao giờ chạy ngay, kể cả khi whitelist đã cho phép.
        # Whitelist trả lời câu "được làm không"; hẹn giờ trả lời câu "làm lúc
        # nào". Cho whitelist nuốt luôn cái hẹn thì việc chạy ngay lập tức —
        # đúng thứ admin vừa bảo là đừng làm.
        if args.hen_luc:
            granted, why = False, f"hẹn tới {args.hen_luc}"

        if not granted:
            # G5 — nói hậu quả. Với việc tốn tiền thật thì GIÁ chính là hậu quả
            # admin cần thấy trước khi bấm, đặt lên đầu câu chứ không giấu ở
            # cuối: đó là thứ phân biệt "đồng ý làm" với "đồng ý trả tiền".
            tien = ""
            if paid:
                gia = float(paid.get("giaUocVnd", 0) or 0)
                da = chi_tieu_ngoai_thang()
                tien = (f"TỐN TIỀN THẬT ~{gia:,.0f}đ "
                        f"({paid.get('nhaCungCap', 'API ngoài')}) · "
                        f"tháng này đã tiêu {da:,.0f}đ. ")
            consequence = (f"{tien}{spec['displayName']} · {cap['description']} "
                           f"Nội dung: {canonical(inp)[:160]}")
            session_id = args.session or os.environ.get("COMPANYSPEC_SESSION_ID")
            if args.hen_luc:
                consequence = (f"[HẸN {args.hen_luc}] " + consequence
                               + " — admin ký bây giờ, hệ chạy đúng giờ đã hẹn.")
            approval_id = approvals.create_request(
                trace_id, session_id, args.company, args.capability, inp,
                fingerprint, risk, consequence, hen_luc=args.hen_luc,
            )
            return bail(
                f"Cần admin duyệt trước khi thực hiện ({risk})."
                + (f" [{why}]" if why else ""),
                status="needsApproval",
                extra={
                    "error": None,
                    "approvalRequest": {
                        # KHÔNG trả payloadHash cho CEO. Biết hash từng là biết
                        # cách tự duyệt, hồi còn cờ --approve. Cờ đã bỏ, nhưng
                        # nguyên tắc giữ: đừng đưa model thứ nó không cần.
                        "approvalId": approval_id,
                        # G5 — nói hậu quả, không nói tên hàm
                        "consequence": consequence,
                        "riskTier": risk,
                        # nút "luôn cho phép" chỉ hiện khi company cho phép (G8)
                        # Không có nút "luôn cho phép" cho việc tốn tiền thật.
                        "canWhitelist": (risk == "write" and not paid
                                         and bool(cap.get("whitelistScope"))),
                    },
                },
            )

    envelope = {
        "taskId": task_id,
        "traceId": trace_id,
        "parentTaskId": None,
        "companyId": args.company,
        "capability": args.capability,
        "input": inp,
        "context": {"adminIntent": args.intent or ""},
        "budget": {
            "depth": 1, "maxDepth": 2, "stepsUsed": 0, "maxSteps": 20,
            "deadlineAt": deadline.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "costUsedUsd": 0.0, "maxCostUsd": 1.0,
        },
        "policy": {
            "riskTier": risk,
            "approvalToken": args.approval_id,
            "dryRun": bool(args.dry_run),
        },
        "issuedBy": args.issued_by,
        "issuedAt": now(),
    }

    conn.execute(
        "INSERT INTO taskLog (taskId, traceId, companyId, capability, riskTier, "
        "fingerprint, status, startedAt) VALUES (?,?,?,?,?,?,?,?)",
        (task_id, trace_id, args.company, args.capability, risk,
         fingerprint, "running", now()),
    )
    conn.commit()

    # 8. chạy company
    #
    # `runtime` là NHÃN (code | skill | agent | workflow | connector) dùng để
    # báo cáo và soi chính sách RP1/RP2/RP3 — không phải nhánh rẽ ở đây.
    # Mọi company, kể cả loại chạy cả một phiên LLM bên trong, đều tuân đúng
    # một hợp đồng: envelope vào stdin, result ra stdout (C1).
    entry = os.path.join(COMPANIES, args.company, spec["entrypoint"])

    # C2.4 — company CHỈ nhận đúng những secret nó đã khai trong manifest.
    # Nếu truyền cả os.environ thì notesCompany cũng đọc được NOTION_TOKEN, và
    # "mỗi company một phạm vi" chỉ còn là lời nói. Danh sách lấy từ file trên
    # đĩa, không lấy từ envelope — model không nới được (G3).
    child_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", ""),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "PYTHONIOENCODING": "utf-8",
    }
    for name in spec.get("secrets") or []:
        if name in os.environ:
            child_env[name] = os.environ[name]
    # Cấu hình không phải secret nhưng thuộc về company (id database…)
    for name in spec.get("env") or []:
        if name in os.environ:
            child_env[name] = os.environ[name]

    try:
        proc = subprocess.run(
            [sys.executable, entry],
            input=json.dumps(envelope, ensure_ascii=False),
            capture_output=True, text=True, env=child_env,
            timeout=cap.get("maxDurationSec", 30),
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip()[:400] or "tiến trình thoát khác 0")
        result = json.loads(proc.stdout)
    except subprocess.TimeoutExpired:
        result = reject(task_id, trace_id,
                        f"Quá {cap.get('maxDurationSec', 30)}s — cắt.", "budgetExceeded")
    except Exception as exc:
        result = reject(task_id, trace_id,
                        f"Company hỏng: {type(exc).__name__}: {exc}", "failed")

    # 9. C2.3 ra
    if result.get("status") == "ok":
        errs = validate(result.get("output") or {}, cap.get("outputSchema", {}), "output")
        if errs and not args.dry_run:
            # Việc ĐÃ chạy xong rồi mới tới lượt kiểm output, nên nếu company khai
            # sideEffects thì thế giới bên ngoài ĐÃ đổi — chỉ có kết quả là không
            # đọc được. Nói rõ chỗ đó, nếu không CEO sẽ báo "chưa làm gì" và admin
            # thử lại, thành ra làm hai lần. Đã xảy ra thật ngày 2026-08-04: bảng
            # kế hoạch được tạo trên Notion trong khi CEO báo "chưa được tạo".
            se = result.get("sideEffects") or []
            canh = ""
            if se:
                canh = (f" ĐÃ CÓ {len(se)} tác động ra ngoài rồi ("
                        + ", ".join(sorted({x.get('type', '?') for x in se}))
                        + ") — việc coi như đã làm, chỉ là kết quả trả về sai định "
                          "dạng. ĐỪNG làm lại; kiểm tra thực tế trước.")
            hong = reject(task_id, trace_id,
                          "C2.3 — output sai schema: " + "; ".join(errs) + canh,
                          "failed")
            # Giữ nguyên sideEffects để backOffice vẫn ghi được dấu vết (O5/D3).
            hong["sideEffects"] = se
            result = hong

    duration = int((time.time() - started) * 1000)
    result.setdefault("usage", {})["durationMs"] = duration

    conn.execute(
        "UPDATE taskLog SET status=?, summary=?, finishedAt=?, durationMs=?, costUsd=? "
        "WHERE taskId=?",
        (result["status"], result.get("summary", ""), now(), duration,
         result.get("usage", {}).get("costUsd", 0.0), task_id),
    )
    # L8 — TIỀN THẬT đã tiêu, ghi vào sổ riêng.
    #
    # Lấy con số company BÁO VỀ, không lấy `giaUocVnd` trong manifest: manifest
    # là ước lượng để hiện lên nút duyệt, còn đây là số thật sau khi gọi. Hai
    # con số lệch nhau là chuyện thường (ảnh nặng hơn dự tính, retry, đổi giá),
    # và chỉ số thật mới đối chiếu được với hoá đơn.
    #
    # Company khai `paidApi` mà chạy xong KHÔNG báo tiền thì ghi theo giá ước —
    # thà ghi thừa còn hơn để một khoản chi biến mất khỏi sổ (O10). Nói rõ
    # trong `ghiChu` rằng đó là số ước, để lúc đối chiếu biết đường trừ.
    if paid and result.get("status") == "ok":
        u = result.get("usage") or {}
        thuc = u.get("paidVnd")
        conn2 = so_tien_that()
        conn2.execute(
            "INSERT INTO chiTieuNgoai (taskId, traceId, companyId, capability, "
            "nhaCungCap, soTienVnd, ghiChu, createdAt) VALUES (?,?,?,?,?,?,?,?)",
            (task_id, trace_id, args.company, args.capability,
             u.get("paidProvider") or paid.get("nhaCungCap"),
             float(thuc if thuc is not None else paid.get("giaUocVnd", 0) or 0),
             "số thật company báo về" if thuc is not None else "ƯỚC theo manifest",
             now()))
        conn2.commit()
        conn2.close()

    for se in result.get("sideEffects", []):
        conn.execute(
            "INSERT INTO sideEffectLog (taskId, traceId, type, target, reversible, createdAt) "
            "VALUES (?,?,?,?,?,?)",
            (task_id, trace_id, se["type"], se.get("target"),
             int(se.get("reversible", False)), now()),
        )
    conn.commit()
    conn.close()
    return result


def mo_ta_truong(v: dict):
    """Mô tả một trường đầu vào, đủ để CEO gõ đúng ngay lần đầu.

    MẢNG CÁC OBJECT phải nói rõ bên trong có gì. Trước đây chỗ này chỉ in
    "array", và CEO không có cách nào biết phần tử là chuỗi hay là object —
    nên nó đoán. Đo được 2026-08-16 bằng ca thử: cả `createPlan` lẫn `addTodos`
    đều bị gửi mảng chuỗi trước, bị dispatcher chặn, rồi mới gọi lại cho đúng.
    Một việc tốn 4 lời gọi thay vì 2. Lỗi im lặng về mặt kết quả (cuối cùng vẫn
    đúng) nhưng tốn tiền và tốn thời gian chờ của admin mỗi lần.
    """
    if "enum" in v:
        return {"enum": v["enum"]}
    if v.get("type") == "array":
        items = v.get("items") or {}
        if items.get("type") == "object":
            truong = {k: mo_ta_truong(s)
                      for k, s in (items.get("properties") or {}).items()}
            return {"array of object": truong,
                    "required": items.get("required", [])}
        return "array"
    return v.get("type", "?")


def cmd_list(_args) -> dict:
    """Danh mục năng lực — thứ duy nhất CEO cần biết về company (C1)."""
    out = []
    for cid in sorted(os.listdir(COMPANIES)) if os.path.isdir(COMPANIES) else []:
        path = os.path.join(COMPANIES, cid, "companySpec.yaml")
        if not os.path.isfile(path):
            continue
        spec = load_spec(cid)
        if spec.get("internal"):
            continue  # C5 — không cho CEO thấy đồ nội bộ
        out.append({
            "companyId": spec["companyId"],
            "displayName": spec["displayName"],
            "capabilities": [
                {"name": c["name"], "riskTier": c["riskTier"],
                 "description": c["description"],
                 # Kèm luôn giá trị hợp lệ: rẻ hơn để CEO đoán sai rồi bị chặn
                 # rồi gọi lại — mỗi vòng thừa là một lượt đi-về với model.
                 "input": {
                     k: mo_ta_truong(v)
                     for k, v in (c.get("inputSchema", {}).get("properties") or {}).items()
                 },
                 "required": c.get("inputSchema", {}).get("required", [])}
                for c in spec.get("capabilities", [])
            ],
        })
    return {"companies": out}


def main() -> int:
    ap = argparse.ArgumentParser(description="dispatcher — cổng duy nhất tới company")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("call", help="gọi một năng lực của một company")
    p.add_argument("--company", required=True)
    p.add_argument("--capability", required=True)
    p.add_argument("--input", required=True, help="JSON object")
    p.add_argument("--trace", help="traceId; bỏ trống thì sinh mới")
    p.add_argument("--intent", help="tóm tắt ý admin, để company hiểu bối cảnh")
    p.add_argument("--approval-id", help="approvalId admin đã bấm duyệt trên Telegram")
    p.add_argument("--hen-luc", help="ISO UTC, ví dụ 2026-09-01T20:40:00Z. Có cờ "
                                     "này thì KHÔNG chạy ngay: sinh một phiếu "
                                     "HẸN để admin ký trước, tới giờ scheduler "
                                     "mới mở khoá và chạy")
    p.add_argument("--session", help="sessionId của CEO, để gắn yêu cầu duyệt về đúng phiên")
    p.add_argument("--dry-run", action="store_true", help="in việc định làm, không làm (W2)")
    p.add_argument("--allow-internal", action="store_true",
                   help="cho gọi company nội bộ — chỉ dùng từ terminal, CEO không có cờ này")
    p.add_argument("--ttl", type=int, default=None,
                   help="ghi đè hạn chót (giây); bỏ trống thì lấy maxDurationSec của năng lực")
    p.add_argument("--issued-by", default="ceo", choices=["ceo", "scheduledTrigger"])
    p.set_defaults(fn=cmd_call)

    sub.add_parser("list", help="danh mục company và năng lực").set_defaults(fn=cmd_list)

    args = ap.parse_args()

    # O5 — mọi lời gọi phải để lại dấu, kể cả khi hỏng theo cách không lường trước.
    # Trước đây một ngoại lệ ngoài dự kiến làm tiến trình văng traceback rồi thoát:
    # CEO chỉ thấy stdout rỗng, admin thấy một câu lỗi vô nghĩa, và trong log
    # KHÔNG CÓ GÌ. Không tra được thì không sửa được.
    try:
        result = args.fn(args)
    except Exception as exc:
        result = {
            "taskId": new_id("tsk"),
            "traceId": os.environ.get("COMPANYSPEC_TRACE_ID") or new_id("trc"),
            "status": "failed", "output": None, "sideEffects": [],
            "summary": f"Dispatcher hỏng ngoài dự kiến: {type(exc).__name__}",
            "error": f"{type(exc).__name__}: {exc}",
            "usage": {"steps": 0, "durationMs": 0, "costUsd": 0.0},
        }
        try:
            conn = backoffice()
            log_outcome(conn, result["taskId"], result["traceId"],
                        getattr(args, "company", "?"), getattr(args, "capability", "?"),
                        "unknown", "", result)
            conn.close()
        except Exception:
            pass  # ghi log hỏng nữa thì cũng phải trả kết quả cho CEO đọc được
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
