#!/usr/bin/env python3
"""Hợp đồng manifest — soát tĩnh, không chạy gì, không tốn gì.

Bộ này canh đúng những loại hỏng đã xảy ra thật và KHÔNG cái nào gây crash:
manifest đúng cú pháp nhưng sai nghĩa, hàng rào khai mà không ai đỡ, giá trị
rỗng mang nghĩa ngược với trực giác.

Xem bảng bẫy trong CLAUDE.md — mỗi ca dưới đây chỉ về một dòng ở đó.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import (  # noqa: E402
    REPO_ROOT, capabilitiesOf, loadManifests, readCompanySource,
)

MANIFESTS = loadManifests()

# Từ khoá schema mà ops/dispatch.py:validate() THẬT SỰ đỡ.
#
# Khai một từ khoá ngoài danh sách này là dựng hàng rào giả: người đọc manifest
# sau này sẽ tin nó, mà bộ soát thì chưa từng đọc tới. Đã xảy ra với `pattern`.
SUPPORTED_SCHEMA_KEYWORDS = {
    "type", "enum", "minLength", "maxLength", "pattern", "minimum", "maximum",
    "required", "properties", "additionalProperties", "minItems", "maxItems",
    "items", "description", "anyOf", "oneOf",
}


class TestManifestShape(unittest.TestCase):
    """Mỗi manifest phải khai đủ thứ dispatcher cần đọc."""

    def testEveryManifestHasCoreKeys(self):
        for companyId, spec in MANIFESTS.items():
            with self.subTest(company=companyId):
                for key in ("companyId", "displayName", "entrypoint", "capabilities"):
                    self.assertIn(key, spec, f"{companyId}: thiếu `{key}`")
                self.assertEqual(
                    spec["companyId"], os.path.basename(spec["_dir"]),
                    f"{companyId}: companyId phải trùng tên thư mục")

    def testEntrypointExists(self):
        for companyId, spec in MANIFESTS.items():
            with self.subTest(company=companyId):
                entry = os.path.join(spec["_dir"], spec["entrypoint"])
                self.assertTrue(os.path.isfile(entry),
                                f"{companyId}: entrypoint không tồn tại: {entry}")

    def testEveryCapabilityHasContract(self):
        for companyId, spec in MANIFESTS.items():
            for name, cap in capabilitiesOf(spec).items():
                with self.subTest(company=companyId, capability=name):
                    for key in ("description", "riskTier", "maxDurationSec",
                                "inputSchema", "outputSchema"):
                        self.assertIn(key, cap, f"{companyId}.{name}: thiếu `{key}`")
                    self.assertIn(cap["riskTier"], ("read", "write", "irreversible"),
                                  f"{companyId}.{name}: riskTier lạ")

    def testSchemasCloseTheDoor(self):
        """`additionalProperties: false` — trường không khai là trường bị chặn.

        Thiếu dòng này thì schema hoá ra chỉ là gợi ý, và CEO gửi trường thừa
        vẫn lọt.
        """
        for companyId, spec in MANIFESTS.items():
            for name, cap in capabilitiesOf(spec).items():
                for kind in ("inputSchema", "outputSchema"):
                    schema = cap.get(kind) or {}
                    if schema.get("type") != "object":
                        continue
                    with self.subTest(company=companyId, capability=name, schema=kind):
                        self.assertIs(
                            schema.get("additionalProperties"), False,
                            f"{companyId}.{name}.{kind}: thiếu "
                            "`additionalProperties: false`")


class TestNoFakeFences(unittest.TestCase):
    """Hàng rào giả hại hơn không có hàng rào."""

    def testOnlySupportedSchemaKeywords(self):
        """Khai từ khoá mà validate() không đọc = luật không ai canh.

        Bài học: `pattern:` viết trong companySpec.yaml nhìn như một hàng rào,
        nhưng bộ soát chưa từng đọc từ khoá đó, nên "31/10/2026" đi lọt.
        """
        def walk(schema, where):
            if not isinstance(schema, dict):
                return
            for key in schema:
                if key in SUPPORTED_SCHEMA_KEYWORDS:
                    continue
                self.fail(f"{where}: từ khoá schema `{key}` không được "
                          "ops/dispatch.py:validate() đỡ. Hoặc bỏ nó đi, hoặc "
                          "mở validate() ra đọc nó — cùng một lần sửa.")
            for key, sub in (schema.get("properties") or {}).items():
                walk(sub, f"{where}.{key}")
            if isinstance(schema.get("items"), dict):
                walk(schema["items"], f"{where}[]")
            for keyword in ("anyOf", "oneOf"):
                for i, branch in enumerate(schema.get(keyword) or []):
                    walk(branch, f"{where}.{keyword}[{i}]")

        for companyId, spec in MANIFESTS.items():
            for name, cap in capabilitiesOf(spec).items():
                for kind in ("inputSchema", "outputSchema"):
                    with self.subTest(company=companyId, capability=name, schema=kind):
                        walk(cap.get(kind) or {}, f"{companyId}.{name}.{kind}")

    def testNoMalformedYamlKeys(self):
        """Thiếu MỘT dấu cách sau dấu hai chấm sinh ra một khoá rác.

        `lanTruocDung:{ type: string }` tạo khoá tên `lanTruocDung:{ type`.
        Manifest vẫn hợp lệ, codemap vẫn sạch, và nó chỉ vỡ lúc chạy thật —
        SAU KHI đã có tác động ra ngoài.
        """
        suspicious = re.compile(r"[:{}\[\]]|\s")
        for companyId, spec in MANIFESTS.items():
            for name, cap in capabilitiesOf(spec).items():
                for kind in ("inputSchema", "outputSchema"):
                    props = (cap.get(kind) or {}).get("properties") or {}
                    for fieldName in props:
                        with self.subTest(company=companyId, capability=name,
                                          field=fieldName):
                            self.assertFalse(
                                suspicious.search(fieldName),
                                f"{companyId}.{name}.{kind}: tên trường "
                                f"`{fieldName}` có ký tự lạ — gần như chắc chắn "
                                "là thiếu dấu cách sau dấu hai chấm trong YAML")

    def testWhitelistScopeIsNeverEmptyList(self):
        """`whitelistScope: []` là ĐÓNG, không phải mở.

        gateway.canWhitelist đọc `bool(cap.get("whitelistScope"))` — danh sách
        rỗng là falsy, nên nút "Luôn cho phép" KHÔNG BAO GIỜ hiện, và admin
        bấm "cho phép 1 lần" mãi mãi mà không ai báo lỗi gì.

        Muốn đóng thì BỎ HẲN khoá đi, để ý định đọc được từ mặt chữ.
        """
        for companyId, spec in MANIFESTS.items():
            for name, cap in capabilitiesOf(spec).items():
                if "whitelistScope" not in cap:
                    continue
                with self.subTest(company=companyId, capability=name):
                    self.assertTrue(
                        cap["whitelistScope"],
                        f"{companyId}.{name}: `whitelistScope: []` nghĩa là ĐÓNG. "
                        "Nếu đó là ý định thì bỏ hẳn khoá này đi; nếu không thì "
                        "kể tên các trường làm phạm vi.")

    def testWhitelistScopeFieldsExist(self):
        """Phạm vi whitelist phải trỏ vào trường CÓ THẬT trong inputSchema."""
        for companyId, spec in MANIFESTS.items():
            for name, cap in capabilitiesOf(spec).items():
                scope = cap.get("whitelistScope") or []
                props = (cap.get("inputSchema") or {}).get("properties") or {}
                for fieldName in scope:
                    with self.subTest(company=companyId, capability=name,
                                      field=fieldName):
                        self.assertIn(
                            fieldName, props,
                            f"{companyId}.{name}: whitelistScope trỏ vào "
                            f"`{fieldName}` mà inputSchema không khai trường đó")


class TestCapabilityReachesCode(unittest.TestCase):
    """Năng lực khai trong manifest phải có đường chạy thật trong code."""

    def testEveryCapabilityAppearsInSource(self):
        """Bất kể company dùng HANDLERS, PROMPTS hay so chuỗi trực tiếp.

        Ba company hôm nay dùng ba kiểu khác nhau, nên ca này soát bằng thứ
        chung nhất: tên năng lực phải xuất hiện như một chuỗi trong mã nguồn.
        Khai một năng lực mà quên viết nhánh cho nó thì dispatcher nhận việc
        rồi company mới ngã — tức là admin đã bấm duyệt cho một thứ không chạy.
        """
        for companyId, spec in MANIFESTS.items():
            source = readCompanySource(spec)
            for name in capabilitiesOf(spec):
                with self.subTest(company=companyId, capability=name):
                    self.assertIn(
                        f'"{name}"', source,
                        f"{companyId}: manifest khai năng lực `{name}` nhưng "
                        f"{spec['entrypoint']} không nhắc tới nó ở đâu cả")


class TestPaidApiDeclared(unittest.TestCase):
    """L8 — tiêu tiền thật thì phải khai, để có nút duyệt và có trần."""

    PAID_KEY_HINT = re.compile(r"\b(GEMINI|OPENAI|ANTHROPIC|DATAFORSEO|SERPER)_",
                               re.IGNORECASE)

    def testCompanyHoldingPaidKeyDeclaresPaidApi(self):
        for companyId, spec in MANIFESTS.items():
            secretNames = " ".join(spec.get("secrets") or [])
            if not self.PAID_KEY_HINT.search(secretNames):
                continue
            declared = any(cap.get("paidApi")
                           for cap in capabilitiesOf(spec).values())
            with self.subTest(company=companyId):
                self.assertTrue(
                    declared,
                    f"{companyId} cầm khoá API tính tiền ({secretNames}) nhưng "
                    "không năng lực nào khai `paidApi` — nghĩa là nó tiêu tiền "
                    "của admin trong im lặng: không nút duyệt, không trần, "
                    "không dòng nào trong sổ.")

    def testPaidApiHasProviderAndPrice(self):
        for companyId, spec in MANIFESTS.items():
            for name, cap in capabilitiesOf(spec).items():
                paid = cap.get("paidApi")
                if not paid:
                    continue
                with self.subTest(company=companyId, capability=name):
                    self.assertTrue(paid.get("nhaCungCap"),
                                    f"{companyId}.{name}: paidApi thiếu nhà cung cấp")
                    self.assertIsNotNone(paid.get("giaUocVnd"),
                                         f"{companyId}.{name}: paidApi thiếu giá ước")


class TestIsolationDeclared(unittest.TestCase):
    """C2.4 — company chỉ nhận secret nó đã khai."""

    def testSecretsAreNamesNotValues(self):
        """Khai TÊN biến môi trường, không bao giờ khai giá trị."""
        looksLikeValue = re.compile(r"[=:/]|^[a-z]{2,}-|\s")
        for companyId, spec in MANIFESTS.items():
            for secretName in (spec.get("secrets") or []):
                with self.subTest(company=companyId, secret=secretName):
                    self.assertFalse(
                        looksLikeValue.search(secretName),
                        f"{companyId}: `{secretName}` trông như một GIÁ TRỊ chứ "
                        "không phải tên biến môi trường. Secret không bao giờ "
                        "nằm trong repo.")
                    self.assertEqual(
                        secretName, secretName.upper(),
                        f"{companyId}: tên biến môi trường phải UPPER_SNAKE")

    def testCompanyCannotCallCompany(self):
        """P3 — không có cạnh ẩn giữa các company."""
        for companyId, spec in MANIFESTS.items():
            with self.subTest(company=companyId):
                self.assertFalse(
                    spec.get("canCall"),
                    f"{companyId}: khai `canCall` — P3 cấm company gọi company. "
                    "Việc ghép nhiều bước là của Core, không phải của company.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
