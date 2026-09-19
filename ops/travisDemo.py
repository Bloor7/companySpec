#!/usr/bin/env python3
"""travisDemo — chạy MỘT lượt xuyên suốt và in ra từng chặng.

    python3 ops/travisDemo.py

Không phải test (test nằm ở `tests/`). Đây là thứ để NHÌN: một lời gọi thật đi
qua Employee → Policy → Execution → Verification → Audit, và mỗi chặng in ra
nó đã quyết gì.

AN TOÀN: mọi thứ đi qua `travisSelfTestCompany` (`internal: true`) — không gọi
mạng, không giữ secret, tác động duy nhất là một dòng trong sổ sqlite của
chính nó. CEO không nhìn thấy company này và không gọi được nó (C5).
"""
import json
import os
import subprocess
import sys
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "ops"))

import approvals  # noqa: E402

COMPANY = "travisSelfTestCompany"
RUN = uuid.uuid4().hex[:6]


def call(capability: str, payload: dict, *extra, label: str = "") -> dict:
    argv = [sys.executable, os.path.join(ROOT, "ops", "dispatch.py"), "call",
            "--company", COMPANY, "--capability", capability,
            "--input", json.dumps(payload, ensure_ascii=False),
            "--trace", f"demo_{RUN}_{label or capability}",
            "--allow-internal", *extra]
    proc = subprocess.run(argv, capture_output=True, text=True, cwd=ROOT,
                          timeout=120)
    return json.loads(proc.stdout)


def heading(text: str) -> None:
    # `flush` vì chặng cuối gọi một tiến trình con in thẳng ra stdout — không
    # flush thì phần in của tiến trình con chen lên trước, và bản trình diễn
    # đọc ngược thứ tự.
    print(f"\n{'═' * 72}\n  {text}\n{'═' * 72}", flush=True)


def main() -> int:
    payload = {"label": "alpha", "value": "một lượt xuyên suốt"}

    heading("1 · VIỆC GHI → hệ DỪNG LẠI HỎI (G5: nói hậu quả, không nói tên hàm)")
    asked = call("recordWrite", payload, label="ask")
    print(f"  status            : {asked['status']}")
    request = asked.get("approvalRequest") or {}
    print(f"  hậu quả admin đọc : {request.get('consequence', '')[:110]}")
    print(f"  nút luôn-cho-phép : {request.get('canWhitelist')}")
    approvalId = request.get("approvalId")
    if not approvalId:
        print("  (đã có whitelist khớp — bỏ qua phần chữ ký)")
        return 0

    heading("2 · CHỮ KÝ KHOÁ VÀO NỘI DUNG (G4) — đổi nội dung là chữ ký hết giá trị")
    approvals.decide(approvalId, "approved")
    sneaky = call("recordWrite", {"label": "gamma", "value": "nội dung KHÁC"},
                  "--approval-id", approvalId, label="abuse")
    print(f"  dùng chữ ký cho nội dung khác → {sneaky['status']}"
          f"  ({sneaky.get('summary', '')[:60]})")

    heading("3 · ĐÚNG NỘI DUNG → CHẠY, và sinh BẰNG CHỨNG (V-1)")
    done = call("recordWrite", payload, "--approval-id", approvalId,
                label="run")
    print(f"  status            : {done['status']}")
    print(f"  tác động ra ngoài : {done.get('sideEffects')}")
    verification = done.get("verification") or {}
    print(f"  bằng chứng        : {verification.get('status')}")
    for check in verification.get("checks", []):
        print(f"      {check['name']:20} {check['status']:12} {check['detail'][:46]}")

    heading("4 · RANH GIỚI EMPLOYEE — hai chiều, không phải chỉ cấm")
    print("  Company này là `database`. Ai có `database.*` thì làm được, ai"
          " không thì không.\n")
    for employeeId in ("sage", "sentinel", "forge", "atlas"):
        readAttempt = call("echoRead", {"message": "thử đọc"},
                           "--employee", employeeId, label=f"r{employeeId}")
        writeAttempt = call("recordWrite", {"label": "beta", "value": "thử ghi"},
                            "--employee", employeeId, label=f"w{employeeId}")

        def verdict(result):
            if result["status"] == "denied":
                return "CHẶN"
            return "được" if result["status"] in ("ok", "needsApproval") else result["status"]

        print(f"  {employeeId:9} đọc → {verdict(readAttempt):6}"
              f"   ghi → {verdict(writeAttempt)}")
    print("\n  `sage` KHÔNG đọc nổi sổ của admin, và đó là CỐ Ý: nó là employee")
    print("  tiếp xúc chữ từ trang lạ, nên kể cả khi bị dụ, nó không có gì để")
    print("  mang đi. Chặn ở tầng QUYỀN thì không phụ thuộc model có nghe lời.")

    heading("5 · HỎNG KIỂU GÌ CŨNG PHẢI BÁO ĐƯỢC (O8: cửa vào không được sập)")
    for mode in ("timeout", "badOutput", "crash", "needsInput"):
        broken = call("failOnPurpose", {"mode": mode}, label=f"fail{mode}")
        summary = (broken.get("summary") or "").strip()
        # In ĐUÔI chứ không in đầu: traceback Python để LOẠI LỖI ở dòng cuối.
        # Company này cố tình xả 3000 ký tự rác ra stderr trước khi chết — in
        # đầu chuỗi thì thấy toàn rác, và đó chính là con bug `stderr[:400]`.
        tail = summary[-60:] if len(summary) > 60 else summary
        print(f"  {mode:11} → {broken['status']:15} …{tail}")

    heading("6 · TRA LẠI: VÌ SAO LỜI GỌI ĐÓ ĐƯỢC PHÉP (§30)")
    subprocess.run([sys.executable, os.path.join(ROOT, "ops", "travis.py"),
                    "why", done["taskId"]], cwd=ROOT)

    print("\n  Mọi thứ trên đi qua ĐÚNG dispatcher thật, ĐÚNG sổ thật, ĐÚNG")
    print("  cổng duyệt thật — không có cờ nào chỉ dành cho bản trình diễn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
