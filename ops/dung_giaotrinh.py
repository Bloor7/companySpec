#!/usr/bin/env python3
"""Sinh trang giáo trình từ registry/giaotrinh-ngoaingu.yaml.

    python3 ops/dung_giaotrinh.py            # in ra stdout
    python3 ops/dung_giaotrinh.py --ra a.html

VÌ SAO CÓ FILE NÀY: nội dung bài học trước đây nằm HAI chỗ — một bản trong
trang HTML đã xuất bản, một bản trong tin nhắn buổi sáng. Hai bản thì sớm muộn
lệch nhau, và lúc đó không ai biết bản nào đúng. Cùng một lỗi với "hạn mức
tháng" hôm 19/08: cùng một khái niệm, hai nơi tính hai kiểu.

Nay YAML là nguồn duy nhất. Scheduler đọc nó để gửi tin; file này đọc nó để
dựng trang. Sửa YAML rồi chạy lại đây, đừng bao giờ sửa thẳng vào HTML.

Từ 24/08 trang có thêm một khối nữa: câu admin TỰ THÊM, lấy qua
`ngoaiNguCompany.dsCau`. Đó là nguồn thứ hai nhưng không phải bản sao của nguồn
thứ nhất — hai nội dung khác nhau, không có chuyện lệch. Cái phải nhớ là trang
này chỉ là ẢNH CHỤP: admin thêm câu mới thì tin nhắn 5h30 có ngay, còn trang thì
phải dựng lại và đăng lại mới có.

Trang KHÔNG gọi mạng ngoài: giọng đọc lấy từ speechSynthesis có sẵn trong
trình duyệt. Chữ Hán cần font CJK nên có nạp Google Fonts, và đó là host duy
nhất trang này chạm tới.
"""
import argparse
import html
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NGUON = os.path.join(ROOT, "registry", "giaotrinh-ngoaingu.yaml")
KHUNG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "giaotrinh.tpl.html")


def cau_cua_toi() -> list:
    """Câu admin tự thêm, lấy qua dispatcher (T2 — không đọc ruột company).

    VÌ SAO CHÚNG PHẢI CÓ MẶT TRÊN TRANG: thứ duy nhất Telegram không chở được là
    TIẾNG. Câu trong giáo trình có nút nghe, câu admin tự thêm thì không — mà
    câu tự thêm mới là câu admin cần dùng thật. Để nguyên thế thì đúng những câu
    quan trọng nhất lại là những câu admin không bao giờ nghe được đọc mẫu.

    Hỏng thì NÉM LỖI, không dựng trang thiếu. Trang thiếu vài câu trông y hệt
    trang đủ, và admin sẽ dùng nó tưởng đã có tất cả.
    """
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "ops", "dispatch.py"), "call",
         "--company", "ngoaiNguCompany", "--capability", "dsCau",
         "--input", json.dumps({"trangThai": "tất cả"}, ensure_ascii=False)],
        capture_output=True, text=True, cwd=ROOT, timeout=30)
    try:
        res = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"dispatch không trả JSON: {proc.stderr.strip()[-500:]}")
    if res.get("status") != "ok":
        raise RuntimeError(f'dsCau {res.get("status")}: '
                           f'{res.get("summary") or res.get("error")}')
    return (res.get("output") or {}).get("cau") or []


def main() -> int:
    ap = argparse.ArgumentParser(description="Dựng trang giáo trình từ YAML")
    ap.add_argument("--ra", help="ghi ra file; bỏ trống thì in ra stdout")
    ap.add_argument("--bo-cau-toi", action="store_true",
                    help="dựng trang KHÔNG kèm câu admin tự thêm")
    args = ap.parse_args()

    def _vn(d):
        try:
            return datetime.strptime(str(d), "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            return str(d)

    with open(NGUON, encoding="utf-8") as fh:
        gt = yaml.safe_load(fh)
    with open(KHUNG, encoding="utf-8") as fh:
        khung = fh.read()

    # Số bài và số câu ĐẾM TRƯỚC, trên giáo trình gốc: trang có câu "Hết 12 bài:
    # khoảng __SO_CAU__ câu", nói về giáo trình chứ không nói về sổ riêng. Cộng
    # câu tự thêm vào con số đó là để trang tự mâu thuẫn với chính nó.
    so_bai = len(gt.get("bai") or [])
    so_cau = sum(len(b.get("tu") or []) for b in gt.get("bai") or [])

    try:
        rieng = [] if args.bo_cau_toi else cau_cua_toi()
    except (RuntimeError, OSError, subprocess.SubprocessError) as e:
        print(f"Không lấy được sổ câu của đại ca: {e}\n"
              "Trang chưa dựng. Sửa chỗ hỏng rồi chạy lại, hoặc thêm "
              "--bo-cau-toi nếu cố ý dựng bản chỉ có giáo trình.", file=sys.stderr)
        return 1
    if rieng:
        # Một "bài" thứ mười ba, đánh số bằng chữ chứ không bằng số: nó không
        # nằm trong tiến độ 12 bước trên Notion, và đánh số 13 là mời người đọc
        # tưởng nó có trong kế hoạch.
        gt.setdefault("bai", []).append({
            "ngay": "riêng",
            "ten": "Câu của đại ca",
            "khi": "Câu tự thêm trong lúc nhắn với trợ lý. Không có trong 12 bài.",
            "tu": [{k: c.get(k, "") for k in
                    ("vi", "en", "enDoc", "zh", "py", "zhDoc")} for c in rieng],
            "mau": [], "moc": [],
            "dungNgay": "Đây là những câu đại ca tự chọn, nên câu nào cũng có "
                        "chỗ dùng thật — đọc lại đúng lúc gặp tình huống đó.",
        })

    # Dữ liệu đi vào trang dưới dạng JSON, KHÔNG nội suy thẳng vào HTML: nội
    # dung có dấu nháy, dấu ngoặc và chữ Hán: nối chuỗi bằng tay là mời một lỗi
    # cú pháp JS làm trắng cả trang.
    du_lieu = json.dumps(gt, ensure_ascii=False)
    if "</script" in du_lieu:
        # Không thể xảy ra với nội dung hiện tại, nhưng nếu ai đó dán HTML vào
        # YAML thì nó đóng sớm thẻ script và trang vỡ câm.
        print("Giáo trình có chuỗi '</script' — không nhúng an toàn được.",
              file=sys.stderr)
        return 1

    trang = khung.replace("/*__DU_LIEU__*/", du_lieu)
    trang = trang.replace("__SO_BAI__", str(so_bai)).replace("__SO_CAU__", str(so_cau))
    # Trang KHÔNG còn nói gì về lịch: bài nào là bài hôm nay do tiến độ admin
    # tích quyết định, và trang tĩnh thì không biết tiến độ đó. Nói bừa một
    # ngày bắt đầu ở đây là để trang mâu thuẫn với tin nhắn 5h30.

    them = f" + {len(rieng)} câu của đại ca" if rieng else ""
    if args.ra:
        with open(args.ra, "w", encoding="utf-8") as fh:
            fh.write(trang)
        print(f"{so_bai} bài · {so_cau} câu{them} → {args.ra}")
    else:
        sys.stdout.write(trang)
    return 0


if __name__ == "__main__":
    sys.exit(main())
