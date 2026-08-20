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

Trang KHÔNG gọi mạng ngoài: giọng đọc lấy từ speechSynthesis có sẵn trong
trình duyệt. Chữ Hán cần font CJK nên có nạp Google Fonts, và đó là host duy
nhất trang này chạm tới.
"""
import argparse
import html
import json
import os
import sys
from datetime import datetime, timedelta

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NGUON = os.path.join(ROOT, "registry", "giaotrinh-ngoaingu.yaml")
KHUNG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "giaotrinh.tpl.html")


def main() -> int:
    ap = argparse.ArgumentParser(description="Dựng trang giáo trình từ YAML")
    ap.add_argument("--ra", help="ghi ra file; bỏ trống thì in ra stdout")
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
    so_bai = len(gt.get("bai") or [])
    so_cau = sum(len(b.get("tu") or []) for b in gt.get("bai") or [])
    trang = trang.replace("__SO_BAI__", str(so_bai)).replace("__SO_CAU__", str(so_cau))
    # Trang KHÔNG còn nói gì về lịch: bài nào là bài hôm nay do tiến độ admin
    # tích quyết định, và trang tĩnh thì không biết tiến độ đó. Nói bừa một
    # ngày bắt đầu ở đây là để trang mâu thuẫn với tin nhắn 5h30.

    if args.ra:
        with open(args.ra, "w", encoding="utf-8") as fh:
            fh.write(trang)
        print(f"{so_bai} bài · {so_cau} câu → {args.ra}")
    else:
        sys.stdout.write(trang)
    return 0


if __name__ == "__main__":
    sys.exit(main())
