#!/usr/bin/env python3
"""Đồ nghề dùng chung cho bộ regression.

VÌ SAO CÓ FILE NÀY: mọi refactor lớn trước đây đều nghiệm thu bằng cảm giác.
Bộ này đóng băng hành vi HIỆN TẠI để lát nữa đổi tên, dựng core/, tách policy…
thì biết ngay mình có làm gãy gì không.

Quy ước đặt tên: tiếng Anh camelCase kể cả cho biến Python — xem docs/NAMING.md
luật L2. Lý do: JSON/YAML và code dùng CHUNG một tên thì không còn điểm dịch
nào để tên trôi.

Không phụ thuộc pytest — máy admin không có, và thêm một phụ thuộc chỉ để chạy
test là thêm một thứ có thể hỏng.
"""
import glob
import json
import os
import subprocess
import sys

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COMPANIES_DIR = os.path.join(REPO_ROOT, "companies")

# Mọi lời gọi của bộ test mang tiền tố này trong traceId.
#
# Bài học "bộ đo tự đứng ngoài phép đo" (CLAUDE.md): bộ ca thử cũ gọi thẳng
# `claude -p` nên chi phí không vào sổ. Ở đây làm ngược lại — test đi qua ĐÚNG
# cổng thật, ghi vào ĐÚNG sổ thật, và tách ra bằng nhãn chứ không bằng cách
# trốn khỏi sổ. Muốn dọn thì: DELETE FROM taskLog WHERE traceId LIKE 'reg_%'.
TRACE_PREFIX = "reg_"


def loadManifests() -> dict:
    """Đọc mọi companySpec.yaml. Trả về {companyId: spec}."""
    manifests = {}
    for path in sorted(glob.glob(os.path.join(COMPANIES_DIR, "*", "companySpec.yaml"))):
        with open(path, encoding="utf-8") as fh:
            spec = yaml.safe_load(fh)
        spec["_path"] = path
        spec["_dir"] = os.path.dirname(path)
        manifests[spec["companyId"]] = spec
    return manifests


def capabilitiesOf(spec: dict) -> dict:
    """{capabilityName: capabilitySpec} cho một company."""
    return {c["name"]: c for c in (spec.get("capabilities") or [])}


def sampleForSchema(schema: dict, fieldName: str = ""):
    """Sinh MỘT giá trị hợp lệ tối thiểu cho schema.

    Chỉ đỡ đúng tập con từ khoá mà ops/dispatch.py:validate() hiểu. Thêm từ
    khoá mới vào validate() thì phải thêm ở đây cùng một lần sửa — bài học
    "mở rộng một định dạng mà quên kéo hàng rào theo".
    """
    if "enum" in schema:
        return schema["enum"][0]

    declaredType = schema.get("type")
    if isinstance(declaredType, list):
        # Kiểu liên hợp: lấy cái đầu tiên KHÔNG phải null, để giá trị còn mang
        # thông tin. `["string", "null"]` mà trả None thì không kiểm được gì.
        declaredType = next((t for t in declaredType if t != "null"), declaredType[0])

    if declaredType == "object":
        value = {}
        properties = schema.get("properties") or {}
        for key in schema.get("required", []):
            value[key] = sampleForSchema(properties.get(key, {}), key)
        # `anyOf`/`oneOf` cũng ra ràng buộc bắt buộc — thoả NHÁNH ĐẦU là đủ.
        #
        # Thêm cùng ngày với `anyOf` trong ops/dispatch.py:validate(). Quên chỗ
        # này thì chính bộ đo lại dính đúng cái bẫy "mở rộng một định dạng mà
        # quên kéo hàng rào theo": validate() hiểu anyOf, bộ sinh mẫu thì không,
        # nên ca thử đỏ vì lý do sai.
        for keyword in ("anyOf", "oneOf"):
            branches = schema.get(keyword)
            if not branches:
                continue
            for key in (branches[0].get("required") or []):
                value.setdefault(key, sampleForSchema(properties.get(key, {}), key))
            break
        return value

    if declaredType == "array":
        minItems = schema.get("minItems", 0)
        if minItems <= 0:
            return []
        itemSchema = schema.get("items", {})
        return [sampleForSchema(itemSchema, fieldName) for _ in range(minItems)]

    if declaredType == "integer":
        return int(schema.get("minimum", 1) or 1)

    if declaredType == "number":
        return float(schema.get("minimum", 1) or 1)

    if declaredType == "boolean":
        return False

    if declaredType == "null":
        return None

    # string, hoặc không khai type
    return _sampleString(schema, fieldName)


def _sampleString(schema: dict, fieldName: str) -> str:
    """Chuỗi hợp lệ: đủ dài, không quá dài, và khớp `pattern` nếu có.

    Ưu tiên đoán theo TÊN TRƯỜNG trước, vì phần lớn ràng buộc thật của dự án
    này là ngày tháng: minLength 10 nghĩa là "YYYY-MM-DD".
    """
    minLength = schema.get("minLength", 0)
    maxLength = schema.get("maxLength", 10_000)
    pattern = schema.get("pattern")

    candidates = []
    lowerName = fieldName.lower()
    if "date" in lowerName or "ngay" in lowerName or "han" in lowerName:
        candidates.append("2026-01-01")
    if "url" in lowerName or "link" in lowerName:
        candidates.append("https://example.invalid/regression")
    if "time" in lowerName or "gio" in lowerName or lowerName.endswith("at"):
        candidates.append("2026-01-01T00:00:00Z")
    # Id dài: nhiều manifest đòi minLength 32 (id của Notion)
    candidates.append("a" * max(minLength, 1))
    candidates.append("regressionSample")
    candidates.append("2026-01-01")
    candidates.append("2026-01-01T00:00:00Z")

    for candidate in candidates:
        if len(candidate) < minLength or len(candidate) > maxLength:
            continue
        if pattern:
            import re
            try:
                if not re.search(pattern, candidate):
                    continue
            except re.error:
                # Regex trong manifest hỏng — không phải việc của hàm này, đã có
                # ca riêng bắt. Ở đây cứ trả về để ca đó nói lời của nó.
                pass
        return candidate

    # Không ứng viên nào vừa: đệm cho đủ dài rồi cắt cho đủ ngắn.
    padded = ("a" * minLength) if minLength else "regressionSample"
    return padded[:maxLength] if maxLength else padded


def sampleInputFor(capability: dict) -> dict:
    """Input hợp lệ tối thiểu cho một năng lực (chỉ các trường bắt buộc)."""
    return sampleForSchema(capability.get("inputSchema") or {"type": "object"})


def callDispatch(companyId: str, capabilityName: str, payload: dict,
                 dryRun: bool = True, extraArgs=None, traceSuffix: str = "") -> dict:
    """Gọi ops/dispatch.py như CEO gọi, rồi trả về result đã parse.

    Mặc định `--dry-run`: đã kiểm tra cả 22 company đều chặn dryRun TRƯỚC khi
    chạm handler và trước cả khi lấy token — nên đường này không đụng Notion,
    không đụng mạng, không sinh phiếu duyệt.
    """
    traceId = f"{TRACE_PREFIX}{companyId}_{capabilityName}{traceSuffix}"
    argv = [
        sys.executable, os.path.join(REPO_ROOT, "ops", "dispatch.py"), "call",
        "--company", companyId,
        "--capability", capabilityName,
        "--input", json.dumps(payload, ensure_ascii=False),
        "--trace", traceId,
    ]
    if dryRun:
        argv.append("--dry-run")
    argv.extend(extraArgs or [])

    proc = subprocess.run(argv, capture_output=True, text=True, cwd=REPO_ROOT,
                          timeout=120)
    if not proc.stdout.strip():
        raise AssertionError(
            f"dispatch không in gì cho {companyId}.{capabilityName}. "
            # Cắt từ ĐUÔI: traceback Python để loại lỗi ở dòng cuối.
            f"stderr(đuôi)={proc.stderr[-2000:]!r}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"dispatch in ra thứ không phải JSON cho {companyId}.{capabilityName}: "
            f"{exc}\nstdout={proc.stdout[:800]!r}") from exc


def readCompanySource(spec: dict) -> str:
    """Mã nguồn entrypoint của một company, dạng chữ."""
    entry = os.path.join(spec["_dir"], spec["entrypoint"])
    with open(entry, encoding="utf-8") as fh:
        return fh.read()
