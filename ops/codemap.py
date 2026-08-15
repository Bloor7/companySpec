#!/usr/bin/env python3
"""Bản đồ mã nguồn — dựng TỪ MÃ, không từ trí nhớ ai cả.

    python3 ops/codemap.py          # bản đồ cho người đọc
    python3 ops/codemap.py --check  # chỉ soát luật, hỏng thì thoát khác 0

VÌ SAO CÓ FILE NÀY: README từng ghi "11 company · 48 năng lực" trong khi thật
là 15 và 56 — con số chép tay thì lặng lẽ cũ đi, và không ai phát hiện cho tới
lúc có người đếm lại. Mọi con số ở đây đếm lại mỗi lần chạy nên không cũ được.

Phần đáng giá nhất là `--check`: nó biến ba luật kiến trúc từ chỗ "phải nhớ"
thành chỗ "chạy một lệnh là biết". Luật nhớ được thì sẽ có ngày quên; luật
chạy được thì không.
"""
import argparse
import ast
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BO_QUA = (".venv-stt", "__pycache__", "plugin", ".git")


def cac_tep_py() -> dict:
    """Đường dẫn tương đối → tuyệt đối. Bỏ plugin vendor: mã người khác."""
    ra = {}
    for thu_muc, con, tep in os.walk(ROOT):
        con[:] = [c for c in con if c not in BO_QUA]
        for t in tep:
            if t.endswith(".py"):
                p = os.path.join(thu_muc, t)
                ra[os.path.relpath(p, ROOT)] = p
    return ra


def phu_thuoc(tep: dict) -> dict:
    """Ai import module nội bộ nào. Đọc bằng AST — grep sẽ dính cả chuỗi và
    comment, mà chuỗi thì không phải phụ thuộc."""
    noi_bo = {os.path.splitext(os.path.basename(p))[0] for p in tep}
    canh = {}
    for rel, p in tep.items():
        try:
            cay = ast.parse(open(p, encoding="utf-8").read())
        except (SyntaxError, OSError):
            continue
        goi = set()
        for n in ast.walk(cay):
            ten = None
            if isinstance(n, ast.Import):
                for a in n.names:
                    g = a.name.split(".")[0]
                    if g in noi_bo:
                        goi.add(g)
                continue
            if isinstance(n, ast.ImportFrom) and n.module:
                ten = n.module.split(".")[0]
            if ten and ten in noi_bo:
                goi.add(ten)
        canh[rel] = goi
    return canh


def tang_cua(rel: str) -> str:
    if rel.startswith("companies/"):
        return "company"
    if rel.startswith("lib/"):
        return "lib"
    if rel.startswith("ops/"):
        return "ops"
    if rel.startswith("backOffice/"):
        return "backOffice"
    return "khác"


def cong_ty() -> list:
    """(companyId, số năng lực) — đọc từ manifest, đó mới là nguồn sự thật."""
    ra = []
    d = os.path.join(ROOT, "companies")
    for cid in sorted(os.listdir(d)):
        p = os.path.join(d, cid, "companySpec.yaml")
        if not os.path.isfile(p):
            continue
        try:
            spec = yaml.safe_load(open(p, encoding="utf-8")) or {}
        except Exception:
            continue
        ra.append((cid, len(spec.get("capabilities") or [])))
    return ra


def _hop_dong() -> dict:
    """companyId → {tên năng lực: inputSchema}. Manifest là nguồn sự thật."""
    ra = {}
    d = os.path.join(ROOT, "companies")
    for cid in sorted(os.listdir(d)):
        p = os.path.join(d, cid, "companySpec.yaml")
        if not os.path.isfile(p):
            continue
        try:
            spec = yaml.safe_load(open(p, encoding="utf-8")) or {}
        except Exception:
            continue
        ra[cid] = {c["name"]: (c.get("inputSchema") or {})
                   for c in (spec.get("capabilities") or []) if c.get("name")}
    return ra


def _soat_mot_loi_goi(cid: str, cap: str, khoa: set, hd: dict, o_dau: str) -> list:
    """Đối chiếu MỘT lời gọi với hợp đồng. Trả danh sách chỗ phạm."""
    if cid not in hd:
        return [f"C2.1 · {o_dau}: không có company '{cid}'"]
    if cap not in hd[cid]:
        co = ", ".join(sorted(hd[cid])) or "(không có năng lực nào)"
        return [f"C2.2 · {o_dau}: '{cid}' không có năng lực '{cap}'. Có: {co}"]
    isc = hd[cid][cap]
    props = set((isc.get("properties") or {}).keys())
    pham = []
    if isc.get("additionalProperties") is False:
        la = khoa - props
        if la:
            pham.append(f"C2.3 · {o_dau}: {cid}.{cap} không khai trường "
                        f"{', '.join(sorted(la))} — có: {', '.join(sorted(props)) or '(không trường nào)'}")
    thieu = set(isc.get("required") or []) - khoa
    if thieu:
        pham.append(f"C2.3 · {o_dau}: {cid}.{cap} thiếu trường bắt buộc "
                    f"{', '.join(sorted(thieu))}")
    return pham


def soat_ten_truong(tep: dict) -> list:
    """Tên trường ở nơi GỌI phải khớp `inputSchema` trong manifest.

    VÌ SAO CÓ LUẬT NÀY: đây là con bug tốn công nhất của dự án. Báo cáo tiền
    cuối ngày gọi sổ thu/chi bằng `from` trong khi hợp đồng khai `tuNgay`;
    dispatcher trả `rejected`, code nuốt lỗi bằng `or {}`, và hệ in
    "thu 0đ · chi 0đ" mỗi tối SUỐT NHIỀU TUẦN mà không ai nghi — vì số 0 trông
    y hệt "hôm nay không tiêu gì". Hỏi lại CEO thì số đúng, nên càng khó ngờ.

    Chỉ soát được lời gọi VIẾT CỨNG (tên company, tên năng lực và dict đều là
    hằng). Lời gọi dựng động thì bỏ qua — soát nửa vời còn tệ hơn không soát,
    vì nó tạo cảm giác đã kiểm rồi. CEO gọi động nên không nằm trong tầm này;
    bù lại CEO được đưa sẵn danh mục kèm tên trường mỗi lượt (gateway).
    """
    hd = _hop_dong()
    pham = []

    # (1) Lời gọi trong Python: hàm nào có dạng f("<x>Company", "<cap>", {...})
    for rel, p in sorted(tep.items()):
        try:
            cay = ast.parse(open(p, encoding="utf-8").read())
        except (SyntaxError, OSError):
            continue
        for n in ast.walk(cay):
            if not isinstance(n, ast.Call) or len(n.args) < 3:
                continue
            a0, a1, a2 = n.args[0], n.args[1], n.args[2]
            if not (isinstance(a0, ast.Constant) and isinstance(a0.value, str)
                    and a0.value.endswith("Company")
                    and isinstance(a1, ast.Constant) and isinstance(a1.value, str)
                    and isinstance(a2, ast.Dict)):
                continue
            # Dict có khoá động (**kwargs hoặc khoá không phải hằng) thì không
            # kết luận được — bỏ qua thay vì báo bừa.
            if any(k is None or not isinstance(k, ast.Constant) for k in a2.keys):
                continue
            khoa = {k.value for k in a2.keys}
            pham += _soat_mot_loi_goi(a0.value, a1.value, khoa, hd,
                                      f"{rel}:{n.lineno}")

    # (2) Lịch định kỳ: registry/schedules.yaml khai input tĩnh. Cron chạy lúc
    # admin ngủ, sai ở đây thì không ai thấy cho tới khi đọc báo cáo.
    lich = os.path.join(ROOT, "registry", "schedules.yaml")
    if os.path.isfile(lich):
        try:
            ds = (yaml.safe_load(open(lich, encoding="utf-8")) or {}).get("schedules") or []
        except Exception:
            ds = []
        for s in ds:
            if not s.get("companyId") or not s.get("capability"):
                continue
            pham += _soat_mot_loi_goi(
                s["companyId"], s["capability"], set((s.get("input") or {}).keys()),
                hd, f"schedules.yaml:{s.get('scheduleId', '?')}")
    return pham


def soat(tep: dict, canh: dict) -> list:
    """Ba luật kiến trúc, soát được bằng code. Trả danh sách chỗ phạm.

    Chỉ soát thứ ĐỌC ĐƯỢC TỪ MÃ. Những luật cần hiểu ý (riskTier khai đúng
    chưa, mô tả năng lực có thật không) thì không nhét vào đây — soát nửa vời
    còn tệ hơn không soát, vì nó tạo cảm giác đã kiểm rồi.
    """
    lib = {os.path.splitext(os.path.basename(p))[0]
           for r, p in tep.items() if tang_cua(r) == "lib"}
    pham = []
    for rel, goi in canh.items():
        tang = tang_cua(rel)
        if tang == "company":
            # P3 — company không gọi company. Dispatcher là đường duy nhất.
            la = goi - lib
            if la:
                pham.append(f"P3 · {rel} import ngoài lib/: {', '.join(sorted(la))}")
        elif tang == "lib":
            # C4.1 — thư viện chung không được biết nghiệp vụ. Nó phụ thuộc
            # ngược lên ops/ hay company là vòng tròn, và là dấu hiệu nghiệp vụ
            # đã rò vào chỗ đáng lẽ chỉ có kỹ thuật.
            nguoc = goi - lib
            if nguoc:
                pham.append(f"C4.1 · {rel} phụ thuộc ngược: {', '.join(sorted(nguoc))}")
    # Không ai được import thẳng vào ruột một company.
    for rel, p in tep.items():
        if tang_cua(rel) == "company":
            continue
        try:
            noi = open(p, encoding="utf-8").read()
        except OSError:
            continue
        if "companies/" in noi and "import" in noi:
            for dong in noi.splitlines():
                if dong.strip().startswith(("import ", "from ")) and "companies" in dong:
                    pham.append(f"C2 · {rel} import thẳng vào company: {dong.strip()[:60]}")
    pham += soat_ten_truong(tep)
    return pham


def main() -> int:
    ap = argparse.ArgumentParser(description="Bản đồ mã nguồn companySpec")
    ap.add_argument("--check", action="store_true",
                    help="chỉ soát luật; phạm luật thì thoát mã 1")
    args = ap.parse_args()

    tep = cac_tep_py()
    canh = phu_thuoc(tep)
    pham = soat(tep, canh)

    if args.check:
        for d in pham:
            print("PHẠM LUẬT:", d)
        print(f"{len(tep)} file .py · {len(pham)} chỗ phạm luật")
        return 1 if pham else 0

    cty = cong_ty()
    print(f"companySpec — {len(cty)} company · {sum(n for _, n in cty)} năng lực "
          f"· {len(tep)} file .py")
    print()
    print("TẦNG (mũi tên = được phép phụ thuộc):")
    print("  ops/       →  lib/, backOffice/     điều phối: gateway, dispatcher, scheduler")
    print("  companies/ →  lib/ MÀ THÔI          nghiệp vụ, mỗi company một hộp kín")
    print("  backOffice/→  lib/, ops/approvals   theo dõi và báo cáo, không phải company")
    print("  lib/       →  (không gì cả)         kỹ thuật thuần, không biết nghiệp vụ")
    print()
    print("PHỤ THUỘC THẬT:")
    for rel in sorted(canh):
        if canh[rel]:
            print(f"  {rel:44} → {', '.join(sorted(canh[rel]))}")
    print()
    dem = {}
    for goi in canh.values():
        for m in goi:
            dem[m] = dem.get(m, 0) + 1
    print("BỊ PHỤ THUỘC NHIỀU NHẤT (sửa ở đây là chạm nhiều nơi):")
    for m, n in sorted(dem.items(), key=lambda kv: -kv[1])[:6]:
        print(f"  {m:16} {n} nơi dùng")
    print()
    print("COMPANY:")
    for cid, n in cty:
        print(f"  {cid:20} {n:>2} năng lực")
    print()
    print(f"SOÁT LUẬT: {len(pham)} chỗ phạm" if pham else "SOÁT LUẬT: sạch")
    for d in pham:
        print("  ", d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
