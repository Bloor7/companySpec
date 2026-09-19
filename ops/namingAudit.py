#!/usr/bin/env python3
"""namingAudit — soát việc đặt tên theo PRINCIPLES §7 và docs/NAMING.md.

    python3 ops/namingAudit.py             # báo cáo đầy đủ
    python3 ops/namingAudit.py --check     # im nếu sạch, thoát 1 nếu phạm
    python3 ops/namingAudit.py --uncovered # in tên CHƯA được khai, dạng YAML

CÁCH SOÁT: theo ĐỘ PHỦ, không theo phỏng đoán.

Không có bộ dò "chữ này có phải tiếng Việt không" — thứ đó luôn đoán sai ở rìa
(`han` là tiếng Việt hay viết tắt của handle?). Thay vào đó, mọi định danh
phải nằm ở đúng một trong hai chỗ trong registry/naming.yaml:

    · trong bản đồ đổi tên   → còn phải đổi
    · trong alreadyEnglish   → đã đúng, có người duyệt

Không ở chỗ nào cả = CHƯA AI QUYẾT ĐỊNH, và đó mới là thứ đáng báo. Thêm một
trường mới mà quên khai tên thì bộ soát đỏ ngay: đặt tên thành việc CỐ Ý.

Đây là hàng rào cho luật N1 — luật nào cũng phải có một phép soát chạy được.
"""
import argparse
import glob
import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAMING_PATH = os.path.join(ROOT, "registry", "naming.yaml")
COMPANIES = os.path.join(ROOT, "companies")

CAMEL_CASE = re.compile(r"^[a-z][a-zA-Z0-9]*$")


def loadNaming() -> dict:
    with open(NAMING_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def loadManifests() -> dict:
    manifests = {}
    for path in sorted(glob.glob(os.path.join(COMPANIES, "*", "companySpec.yaml"))):
        with open(path, encoding="utf-8") as fh:
            spec = yaml.safe_load(fh)
        manifests[spec["companyId"]] = spec
    return manifests


def collectIdentifiers(manifests: dict) -> tuple:
    """Trả về (capabilityNames, fieldNames) — mỗi cái là {(companyId, name)}."""
    capabilityNames, fieldNames = set(), set()
    for companyId, spec in manifests.items():
        for cap in (spec.get("capabilities") or []):
            capabilityNames.add((companyId, cap["name"]))
            for kind in ("inputSchema", "outputSchema"):
                for fieldName in _walkProperties(cap.get(kind) or {}):
                    fieldNames.add((companyId, fieldName))
    return capabilityNames, fieldNames


def _walkProperties(schema: dict):
    """Mọi tên trường trong một schema, kể cả lồng trong items/anyOf."""
    if not isinstance(schema, dict):
        return
    for fieldName, sub in (schema.get("properties") or {}).items():
        yield fieldName
        yield from _walkProperties(sub)
    if isinstance(schema.get("items"), dict):
        yield from _walkProperties(schema["items"])
    for keyword in ("anyOf", "oneOf"):
        for branch in (schema.get(keyword) or []):
            yield from _walkProperties(branch)


def resolveField(naming: dict, companyId: str, fieldName: str):
    """Tên mới cho một trường, hoặc None nếu chưa khai.

    perCompany thắng global — vì `vi` ở walletCompany là `wallet` còn ở
    ngoaiNguCompany là mã ngôn ngữ `vi`.
    """
    fields = naming.get("fields") or {}
    perCompany = (fields.get("perCompany") or {}).get(companyId) or {}
    if fieldName in perCompany:
        return perCompany[fieldName]
    return (fields.get("global") or {}).get(fieldName)


def resolveCapability(naming: dict, companyId: str, name: str):
    return ((naming.get("capabilities") or {}).get(companyId) or {}).get(name)


def audit(naming: dict, manifests: dict) -> dict:
    capabilityNames, fieldNames = collectIdentifiers(manifests)
    alreadyEnglish = set(naming.get("alreadyEnglish") or [])

    report = {
        "toRenameCapabilities": [],
        "toRenameFields": [],
        "uncoveredCapabilities": [],
        "uncoveredFields": [],
        "notCamelCase": [],
        "danglingEntries": [],
        "totalCapabilities": len(capabilityNames),
        "totalFields": len(fieldNames),
    }

    # Mục bản đồ trỏ vào thứ KHÔNG TỒN TẠI là một no-op im lặng: người đọc
    # naming.yaml tưởng tên đó đã được xử lý, còn máy thì chưa từng chạm tới.
    # Cùng họ với "hàng rào giả" — nên phải kêu.
    realCapabilities = {}
    realFields = {}
    for companyId, name in capabilityNames:
        realCapabilities.setdefault(companyId, set()).add(name)
    for companyId, fieldName in fieldNames:
        realFields.setdefault(companyId, set()).add(fieldName)

    for companyId, mapping in (naming.get("capabilities") or {}).items():
        for oldName in mapping:
            if oldName in realCapabilities.get(companyId, set()):
                continue
            owner = sorted(c for c, names in realCapabilities.items()
                           if oldName in names)
            report["danglingEntries"].append(
                f"capabilities.{companyId}.{oldName} — thực tế nằm ở "
                + (", ".join(owner) if owner else "KHÔNG COMPANY NÀO"))

    for companyId, mapping in ((naming.get("fields") or {})
                               .get("perCompany") or {}).items():
        for oldName in mapping:
            if oldName not in realFields.get(companyId, set()):
                report["danglingEntries"].append(
                    f"fields.perCompany.{companyId}.{oldName} — company này "
                    "không khai trường đó")

    for companyId, name in sorted(capabilityNames):
        if not CAMEL_CASE.match(name):
            report["notCamelCase"].append(f"{companyId}.{name}")
        newName = resolveCapability(naming, companyId, name)
        if newName:
            report["toRenameCapabilities"].append((companyId, name, newName))
        elif name not in alreadyEnglish:
            report["uncoveredCapabilities"].append((companyId, name))

    for companyId, fieldName in sorted(fieldNames):
        if not CAMEL_CASE.match(fieldName):
            report["notCamelCase"].append(f"{companyId}:{fieldName}")
        newName = resolveField(naming, companyId, fieldName)
        if newName and newName != fieldName:
            report["toRenameFields"].append((companyId, fieldName, newName))
        elif not newName and fieldName not in alreadyEnglish:
            report["uncoveredFields"].append((companyId, fieldName))

    return report


def printReport(report: dict) -> None:
    print(f"namingAudit — {report['totalCapabilities']} năng lực · "
          f"{report['totalFields']} cặp (company, trường)\n")

    if report["danglingEntries"]:
        print(f"MỤC BẢN ĐỒ TRỎ VÀO HƯ KHÔNG ({len(report['danglingEntries'])}) — "
              "khai rồi mà không tác dụng gì:")
        for item in report["danglingEntries"]:
            print(f"  {item}")
        print()

    if report["notCamelCase"]:
        print("KHÔNG PHẢI camelCase (§7):")
        for item in report["notCamelCase"]:
            print(f"  {item}")
        print()

    if report["toRenameCapabilities"]:
        print(f"TỪ ĐIỂN — năng lực tiếng Việt và tên tiếng Anh tương ứng "
              f"({len(report['toRenameCapabilities'])}). Tra khi viết code mới; "
              "KHÔNG phải việc phải làm:")
        for companyId, old, new in report["toRenameCapabilities"]:
            print(f"  {companyId:22} {old:22} → {new}")
        print()

    if report["toRenameFields"]:
        print(f"TỪ ĐIỂN — trường ({len(report['toRenameFields'])}):")
        shown = {}
        for companyId, old, new in report["toRenameFields"]:
            shown.setdefault((old, new), []).append(companyId)
        for (old, new), companies in sorted(shown.items()):
            where = companies[0] if len(companies) == 1 else f"{len(companies)} company"
            print(f"  {old:22} → {new:24} ({where})")
        print()

    uncovered = report["uncoveredCapabilities"] + report["uncoveredFields"]
    if uncovered:
        print(f"CHƯA AI QUYẾT ĐỊNH ({len(uncovered)}) — phải khai trong "
              "registry/naming.yaml:")
        for companyId, name in uncovered:
            print(f"  {companyId:22} {name}")
        print()


def printUncoveredAsYaml(report: dict) -> None:
    """In dạng dán thẳng được vào naming.yaml — đỡ gõ tay, đỡ gõ sai."""
    names = sorted({name for _c, name in report["uncoveredFields"]}
                   | {name for _c, name in report["uncoveredCapabilities"]})
    print("alreadyEnglish:")
    for name in names:
        print(f"  - {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="soát đặt tên theo §7")
    parser.add_argument("--check", action="store_true",
                        help="im nếu sạch, thoát 1 nếu còn chỗ phạm")
    parser.add_argument("--uncovered", action="store_true",
                        help="in tên chưa khai, dạng YAML dán được")
    args = parser.parse_args()

    naming = loadNaming()
    manifests = loadManifests()
    report = audit(naming, manifests)

    if args.uncovered:
        printUncoveredAsYaml(report)
        return 0

    # CHỈ coi là "phạm luật" những thứ SAI THẬT, không phải những tên tiếng Việt
    # đang chạy tốt.
    #
    # Đổi tên hàng loạt code đang chạy là việc tốn công và rủi ro cao mà không
    # mua lại được gì tương xứng — admin chốt 2026-09-19. Bản đồ ở
    # registry/naming.yaml giữ vai trò TỪ ĐIỂN: nơi tra "khái niệm này gọi là
    # gì" khi viết code MỚI, để không đẻ thêm tên thứ ba cho cùng một thứ.
    #
    # Hai thứ dưới đây vẫn là lỗi thật:
    #   · danglingEntries — mục từ điển trỏ vào thứ không tồn tại, tức là từ
    #     điển đang nói dối người tra nó.
    #   · notCamelCase    — phạm §7 về hình thức, sửa rẻ.
    problems = len(report["notCamelCase"]) + len(report["danglingEntries"])

    if args.check:
        if problems:
            printReport(report)
            print(f"namingAudit: {problems} chỗ chưa đạt §7", file=sys.stderr)
            return 1
        print(f"{report['totalCapabilities']} năng lực · "
              f"{report['totalFields']} cặp (company, trường) · 0 chỗ phạm luật")
        return 0

    printReport(report)
    if not problems:
        print("sạch — mọi định danh đã đúng §7 và đã có người duyệt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
