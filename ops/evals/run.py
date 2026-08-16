#!/usr/bin/env python3
"""Chạy bộ ca thử cho CEO và chấm — lưới an toàn cho mọi thay đổi ở SYSTEM.md.

    python3 ops/evals/run.py                 # chạy hết
    python3 ops/evals/run.py --only chi-ck   # chạy một ca (chạy hết thì tốn tiền)
    python3 ops/evals/run.py --liet-ke       # xem có ca nào, không tốn gì

NÓ ĐO CÁI GÌ: CEO nhận một câu của admin thì bắn ra những lời gọi nào. Không đo
văn phong, không đo câu trả lời — hai thứ đó người đọc là biết. Thứ không nhìn
bằng mắt được là chuỗi lời gọi phía sau, và đó đúng là chỗ mọi bug đắt tiền của
dự án này đã nấp: ghi sổ mà quên trừ ví, trừ ví hai lần, gọi bằng tên trường
không có trong manifest.

NÓ KHÔNG ĐO ĐƯỢC CÁI GÌ — nói trước để đừng ai tin quá:
  · Không đo được câu chữ CEO nói với admin. Ca "đạt" vẫn có thể kèm một câu
    trả lời khó hiểu.
  · Không đo được company chạy đúng hay sai. Ở đây company không hề chạy.
  · Không đo được hành vi nhiều lượt (admin nhắn tiếp, bấm duyệt rồi làm tiếp).
    Mỗi ca là MỘT lượt, phiên mới tinh.
  · Model không tất định. Một ca trượt một lần chưa phải bằng chứng; chạy lại
    ca đó vài lần trước khi đi sửa prompt.

TỐN TIỀN THẬT. Mỗi ca là một phiên CEO đầy đủ, ăn vào đúng hạn mức mà cầu dao
L7 đang đếm (`backOffice/src/backoffice.py usage`). Chạy cả bộ trước khi ngủ
thì sáng ra báo cáo có thể bị khoá ghi. Số đo in ở cuối mỗi lần chạy.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import uuid

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SANDBOX = os.path.join(HERE, "shim")
CASES = os.path.join(HERE, "cases.yaml")

sys.path.insert(0, os.path.join(ROOT, "ops"))
import gateway  # noqa: E402  — dùng ĐÚNG hàm dựng prompt của bản chạy thật

# Secret phải biến mất khỏi phiên ca thử. Lớp chặn số 2 (xem docstring của
# shim): kể cả có ai chạy được company thật thì nó cũng không đăng nhập nổi.
SECRETS = ["NOTION_TOKEN", "TELEGRAM_BOT_TOKEN", "SUPABASE_KEY",
           "SUPABASE_SERVICE_KEY", "GITHUB_TOKEN", "ANTHROPIC_API_KEY"]


def system_prompt(co_profile: bool) -> str:
    """Prompt y hệt bản chạy thật.

    Dựng lại bằng tay thì ca thử sẽ đo một CEO khác với CEO admin đang dùng —
    vô dụng theo cách khó phát hiện nhất. Nên gọi thẳng hàm của gateway.
    """
    with open(gateway.SYSTEM_PROMPT, encoding="utf-8") as fh:
        s = fh.read()
    return s + gateway.danh_muc_block() + (gateway.profile_block() if co_profile else "")


def chay_mot_ca(ca: dict, co_profile: bool) -> dict:
    log = tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8")
    log.close()

    env = {k: v for k, v in os.environ.items() if k not in SECRETS}
    env.update({
        "COMPANYSPEC_EVAL_ROOT": ROOT,
        "COMPANYSPEC_EVAL_LOG": log.name,
        "COMPANYSPEC_EVAL_STUB": json.dumps(ca.get("traVe") or {}, ensure_ascii=False),
    })

    cmd = [
        "claude", "-p",
        "--system-prompt", system_prompt(co_profile),
        "--settings", gateway.SETTINGS,   # deny list + hook guard y như thật
        "--output-format", "json",
        "--tools", "Bash",
        "--strict-mcp-config",
        "--setting-sources", "project",
        "--max-turns", "12",
        "--session-id", str(uuid.uuid4()),
    ]
    # cwd là sandbox: `python3 ops/dispatch.py` ở đây trỏ vào bản giả. Đây là
    # toàn bộ mẹo của bộ ca thử — không cờ mới, không sửa cổng thật.
    proc = subprocess.run(cmd, cwd=SANDBOX, capture_output=True, text=True,
                          input=ca["cauAdmin"], timeout=600, env=env)

    calls = []
    with open(log.name, encoding="utf-8") as fh:
        for dong in fh:
            if dong.strip():
                calls.append(json.loads(dong))
    os.unlink(log.name)

    try:
        data = json.loads(proc.stdout)
    except Exception:
        # O10 — phiên hỏng thì nói ra, đừng coi như "không gọi gì cả" rồi chấm
        # cho qua những ca mà đáp án đúng là im lặng.
        return {"calls": calls, "loiPhien": (proc.stderr or proc.stdout)[:300],
                "traLoi": "", "chiPhi": 0.0}
    return {
        "calls": calls,
        "loiPhien": data.get("result", "")[:300] if data.get("is_error") else None,
        "traLoi": (data.get("result") or "")[:400],
        "chiPhi": float(data.get("total_cost_usd") or 0.0),
    }


def cham(ca: dict, calls: list) -> list:
    """Trả về danh sách lỗi. Rỗng = đạt."""
    loi = []
    da_goi = [f"{c['company']}.{c['capability']}" for c in calls]

    for mong in ca.get("phaiGoi") or []:
        ten = mong["goi"]
        khop = [c for c in calls if f"{c['company']}.{c['capability']}" == ten]
        if not khop:
            loi.append(f"thiếu lời gọi {ten}")
            continue
        for truong, cho_doi in (mong.get("truong") or {}).items():
            thay = [c["input"].get(truong) for c in khop]
            if all(v is None for v in thay):
                loi.append(f"{ten}: thiếu trường '{truong}'")
            elif isinstance(cho_doi, str) and cho_doi.startswith("~"):
                # "~abc" = chuỗi phải CHỨA abc. Dùng cho nội dung tự do: câu chữ
                # do model đặt thì không so bằng nhau được, nhưng vẫn phải giữ
                # đúng những mẩu admin đã gõ.
                can = cho_doi[1:]
                if not any(isinstance(v, str) and can in v for v in thay):
                    loi.append(f"{ten}.{truong}: phải chứa {can!r}, nhận {thay!r}")
            elif cho_doi != "*" and cho_doi not in thay:
                loi.append(f"{ten}.{truong}: cần {cho_doi!r}, nhận {thay!r}")

    for cam in ca.get("khongDuocGoi") or []:
        if cam in da_goi:
            loi.append(f"KHÔNG được gọi {cam} nhưng đã gọi")

    tran = ca.get("toiDaLoiGoi")
    if tran is not None and len(calls) > tran:
        loi.append(f"gọi {len(calls)} lần, quá trần {tran}")

    # Lời gọi bị cổng từ chối là hỏng thật, kể cả khi phần trên đã đạt: ngoài
    # đời nó thành một vòng đi-về vô ích, và đúng dạng bug "sai tên trường".
    for c in calls:
        if c.get("status") == "rejected":
            loi.append(f"{c['company']}.{c['capability']} bị từ chối: "
                       f"{c.get('loi') or c.get('vi')}")
    return loi


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="chỉ chạy ca có id này; nhiều ca thì ngăn bằng dấu phẩy")
    ap.add_argument("--liet-ke", action="store_true", help="xem danh sách ca, không chạy")
    ap.add_argument("--khong-profile", action="store_true",
                    help="chạy không nạp PROFILE.md (mặc định có, cho giống thật)")
    args = ap.parse_args()

    with open(CASES, encoding="utf-8") as fh:
        cases = yaml.safe_load(fh)["cases"]
    if args.only:
        muon = [x.strip() for x in args.only.split(",") if x.strip()]
        cases = [c for c in cases if c["id"] in muon]
        # Gõ sai một id thì nói ra. Lặng lẽ chạy 3 ca khi người ta gọi 4 ca là
        # kiểu hỏng đúng bằng cách tệ nhất: báo cáo "tất cả đều đạt".
        thieu = set(muon) - {c["id"] for c in cases}
        if thieu:
            print(f"không có ca nào tên: {', '.join(sorted(thieu))}")
            return 1

    if args.liet_ke:
        for c in cases:
            print(f"  {c['id']:32} {c['cauAdmin']}")
        print(f"\n{len(cases)} ca.")
        return 0

    dat, tong_chi = 0, 0.0
    for i, ca in enumerate(cases, 1):
        print(f"\n[{i}/{len(cases)}] {ca['id']}  ·  admin: {ca['cauAdmin']!r}",
              flush=True)
        kq = chay_mot_ca(ca, co_profile=not args.khong_profile)
        tong_chi += kq["chiPhi"]

        for c in kq["calls"]:
            print(f"      → {c['company']}.{c['capability']} "
                  f"{json.dumps(c['input'], ensure_ascii=False)}")
        if not kq["calls"]:
            print("      → (không gọi company nào)")

        if kq["loiPhien"]:
            print(f"   HỎNG PHIÊN: {kq['loiPhien']}")
            continue

        loi = cham(ca, kq["calls"])
        if loi:
            print("   TRƯỢT")
            for l in loi:
                print(f"      · {l}")
            print(f"      CEO đáp: {kq['traLoi'][:160]!r}")
        else:
            dat += 1
            print(f"   ĐẠT  (${kq['chiPhi']:.4f})")

    print(f"\n{dat}/{len(cases)} ca đạt · tốn ${tong_chi:.4f}")
    print("Đối chiếu hạn mức: python3 backOffice/src/backoffice.py usage")
    return 0 if dat == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
