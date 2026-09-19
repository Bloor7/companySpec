#!/usr/bin/env python3
"""Chạy cả bộ regression.

    python3 tests/regression/run.py              # tất cả
    python3 tests/regression/run.py --fast       # bỏ ca chạy khô (nhanh ~0,1s)
    python3 tests/regression/run.py --only naming

Không tốn tiền, không cần mạng, không đụng Notion. Ca chạy khô có gọi tiến
trình con nên mất khoảng 20 giây; phần còn lại gần như tức thì.
"""
import argparse
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SLOW_MODULES = {"testDryRunAllCapabilities"}


def main() -> int:
    parser = argparse.ArgumentParser(description="bộ regression của Travis")
    parser.add_argument("--fast", action="store_true",
                        help="bỏ những ca phải gọi tiến trình con")
    parser.add_argument("--only", help="chỉ chạy module có tên chứa chuỗi này")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    sys.path.insert(0, HERE)
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    moduleNames = sorted(
        name[:-3] for name in os.listdir(HERE)
        if name.startswith("test") and name.endswith(".py")
    )
    chosen = []
    for moduleName in moduleNames:
        if args.fast and moduleName in SLOW_MODULES:
            continue
        if args.only and args.only.lower() not in moduleName.lower():
            continue
        chosen.append(moduleName)
        suite.addTests(loader.loadTestsFromName(moduleName))

    if not chosen:
        print("không có module nào khớp", file=sys.stderr)
        return 2

    print(f"chạy: {', '.join(chosen)}\n")
    result = unittest.TextTestRunner(verbosity=1 if args.quiet else 2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
