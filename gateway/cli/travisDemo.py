#!/usr/bin/env python3
"""travisDemo — chạy MỘT lượt xuyên suốt và in ra từng chặng.

    python3 gateway/cli/travisDemo.py

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

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "core", "policy"))

import approvals  # noqa: E402

COMPANY = "travisSelfTestCompany"
RUN = uuid.uuid4().hex[:6]

#: Nhãn trace của bản trình diễn — LẤY TỪ danh sách chung, không gõ lại.
#: Cùng luật với `tests/drills/run.py`: bộ đo nào phát minh một nhãn mà quên
#: đăng ký thì mọi thứ nó đẻ ra bị đếm như việc THẬT.
sys.path.insert(0, ROOT)
from core.audit import TEST_TRACE_PREFIXES  # noqa: E402

DEMO_PREFIX = "demo_"
assert DEMO_PREFIX in TEST_TRACE_PREFIXES, (
    f"`{DEMO_PREFIX}` chưa có trong core.audit.TEST_TRACE_PREFIXES")


def call(capability: str, payload: dict, *extra, label: str = "") -> dict:
    argv = [sys.executable, os.path.join(ROOT, "gateway", "cli", "dispatch.py"), "call",
            "--company", COMPANY, "--capability", capability,
            "--input", json.dumps(payload, ensure_ascii=False),
            "--trace", f"{DEMO_PREFIX}{RUN}_{label or capability}",
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
    subprocess.run([sys.executable, os.path.join(ROOT, "gateway", "cli", "travis.py"),
                    "why", done["taskId"]], cwd=ROOT)

    print("\n  Mọi thứ trên đi qua ĐÚNG dispatcher thật, ĐÚNG sổ thật, ĐÚNG")
    print("  cổng duyệt thật — không có cờ nào chỉ dành cho bản trình diễn.")

    return 0


def don_dep() -> int:
    """Xoá phiếu duyệt của CHÍNH LƯỢT CHẠY NÀY. Trả về số dòng đã xoá.

    ═══ VÌ SAO PHẢI DỌN, DÙ ĐÂY CHỈ LÀ BẢN TRÌNH DIỄN ═══

    Demo cố ý đi qua cổng duyệt THẬT — đó là cả điểm của nó. Nhưng phiếu duyệt
    không nằm yên trong sổ: nó hiện thành MỘT CÁI THẺ trên Telegram của admin,
    có nút bấm.

    Đo 21/09: 15 phiếu `demo_` còn nằm lại trong sổ, và một trong số đó admin
    đã bấm **"luôn cho phép"** — đẻ ra một quyền đứng THẬT
    (`wl_7f5e254bdf53c200`) cho `travisSelfTestCompany.recordWrite`. Một bản
    trình diễn vừa cấp cho mình một quyền thường trực.

    Lần này vô hại: company ấy `internal: true` nên CEO không gọi được (C5).
    Nhưng cái vô hại là do MAY, không do thiết kế — và lần sau bản trình diễn
    có thể chạy qua một company thật.

    Cùng họ với "ca thử tự chạy thật việc GHI", và với "bộ đo làm hỏng chính
    phép đo": `tests/regression` và `tests/drills` đều tự dọn, chỉ file này
    quên.

    ⚠ Chỉ xoá đúng nhãn + token CỦA LƯỢT NÀY. Xoá mọi dòng `demo_` là xoá cả
    dấu vết của những lượt trước mà ai đó có thể đang đọc.
    """
    return approvals.xoa_phieu_theo_trace(f"{DEMO_PREFIX}{RUN}_%")


if __name__ == "__main__":
    # `finally` chứ không phải dòng cuối của `main()`: `main` có một nhánh
    # thoát SỚM ("đã có whitelist khớp") — và đó đúng là lượt chạy đáng dọn
    # nhất, vì nó xảy ra ngay sau khi một quyền đứng vừa được cấp. Một cú
    # Ctrl-C hay một `json.loads` vỡ giữa chừng cũng để phiếu nằm lại.
    #
    # Dọn dẹp chỉ nằm trên nhánh ĐẸP thì nó không phải dọn dẹp.
    try:
        _ma = main()
    finally:
        _daDon = don_dep()
        if _daDon:
            print(f"\n  Đã dọn {_daDon} phiếu duyệt do bản trình diễn này "
                  "đẻ ra.")
    sys.exit(_ma)
