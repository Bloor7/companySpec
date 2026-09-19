#!/usr/bin/env python3
"""Chạy CẢ HAI bộ: regression (từng mảnh) và integration (cả dây chuyền).

    python3 tests/run.py              # tất cả
    python3 tests/run.py --fast       # bỏ ca gọi tiến trình con
    python3 tests/run.py --only naming

VÌ SAO HAI BỘ, KHÔNG PHẢI MỘT:

  regression/   kiểm TỪNG MẢNH, phần lớn bằng hàm thuần. Nhanh, chỉ rõ chỗ hỏng.
  integration/  kiểm CHỖ NỐI, qua đúng dispatcher thật và sổ thật.

Một hệ có 185 ca đơn vị xanh vẫn hỏng được ở chỗ nối — và chỗ nối là chỗ
không ai nhìn, vì mỗi bên đều tin bên kia lo rồi.

Không tốn tiền, không cần mạng, không đụng dữ liệu thật: integration đi qua
`travisSelfTestCompany` (`internal: true`).
"""
import argparse
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SUITES = ("regression", "integration")
SLOW_MODULES = {"testDryRunAllCapabilities"}


def main() -> int:
    parser = argparse.ArgumentParser(description="bộ kiểm của Travis")
    parser.add_argument("--fast", action="store_true",
                        help="bỏ những ca phải gọi nhiều tiến trình con")
    parser.add_argument("--only", help="chỉ chạy module có tên chứa chuỗi này")
    parser.add_argument("--suite", choices=SUITES,
                        help="chỉ chạy một bộ")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    chosen = []

    for suiteName in SUITES:
        if args.suite and suiteName != args.suite:
            continue
        directory = os.path.join(HERE, suiteName)
        if not os.path.isdir(directory):
            continue
        # Mỗi bộ có `harness` riêng, nên đường dẫn phải đặt lại trước khi nạp.
        sys.path.insert(0, directory)
        for name in sorted(os.listdir(directory)):
            if not (name.startswith("test") and name.endswith(".py")):
                continue
            moduleName = name[:-3]
            if args.fast and moduleName in SLOW_MODULES:
                continue
            if args.only and args.only.lower() not in moduleName.lower():
                continue
            chosen.append(f"{suiteName}/{moduleName}")
            suite.addTests(loader.loadTestsFromName(moduleName))

    if not chosen:
        print("không có module nào khớp", file=sys.stderr)
        return 2

    print(f"chạy {len(chosen)} module: {', '.join(chosen)}\n")
    result = unittest.TextTestRunner(verbosity=1 if args.quiet else 2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
