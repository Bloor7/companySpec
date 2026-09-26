#!/usr/bin/env python3
"""Secret broker lùi về manifest — không được RỘNG HƠN phiếu lúc sổ khoẻ.

Đo từ nhận xét review 26/09. `_capPhieuSecret` (gateway/cli/dispatch.py) nói
đúng ở docstring: sổ phiếu (`coreSecrets.openStore()`) hỏng thì KHÔNG được
làm chết lời gọi (O8) — nó lùi về đúng danh sách `declared` đọc từ manifest
trên đĩa. Nhưng "lùi về đúng `declared`" chỉ AN TOÀN chừng nào `declared`
không rộng hơn thứ broker THẬT SỰ cấp lúc sổ khoẻ. Nếu một lần sửa sau này
làm nhánh lùi tự thêm một tên không nằm trong tập broker healthy từng cấp
(ví dụ: gộp nhầm biến môi trường, hoặc đọc từ một danh sách khác `declared`),
company sẽ nhận một secret mà broker CHƯA TỪNG chuẩn thuận — đúng cửa mà P4
dựng ra để chặn.

Ca này không tin "lùi về = declared, healthy cũng = declared" là mãi đúng.
Nó ĐO cả hai nhánh bằng cùng một lời gọi thật (`dispatch._capPhieuSecret`),
trên cùng một manifest thật, rồi so — không suy diễn từ đọc mã.
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO_ROOT, "gateway", "cli"))
sys.path.insert(0, os.path.join(REPO_ROOT, "core", "policy"))

from harness import loadManifests  # noqa: E402
import dispatch  # noqa: E402
import core.secrets as coreSecrets  # noqa: E402

# Bản GỐC, chụp lại TRƯỚC khi ca thử patch bất cứ gì — patch xong mà gọi lại
# `coreSecrets.openStore` bên trong chính patch đó thì đệ quy vào chính mock.
_OPEN_STORE_THAT = coreSecrets.openStore


def _manifestWithSecrets() -> tuple:
    """Một company thật có khai `secrets`, để ca không đo trên dữ liệu bịa."""
    for companyId, spec in sorted(loadManifests(includeInternal=True).items()):
        declared = tuple(spec.get("secrets") or ())
        if declared:
            return companyId, declared
    raise AssertionError(
        "không company nào khai `secrets` trong companySpec.yaml — "
        "ca này mất mẫu thật để đo")


class TestSecretFallbackNeverWiderThanHealthyBroker(unittest.TestCase):

    def setUp(self):
        self.companyId, self.declared = _manifestWithSecrets()
        # Sổ phiếu riêng cho ca thử — KHÔNG đụng core/secretLease.sqlite thật.
        self.tmpStorePath = os.path.join(
            tempfile.mkdtemp(prefix="travisSecFallback"), "lease.sqlite")

    def _namesGrantedWithHealthyStore(self, traceId: str) -> set:
        """Sổ khoẻ, trỏ vào một file tạm — kết quả là điều `_capPhieuSecret`
        cấp khi mọi thứ chạy đúng thiết kế."""
        def _openTemp(*_args, **_kwargs):
            return _OPEN_STORE_THAT(self.tmpStorePath)

        with mock.patch.object(coreSecrets, "openStore", side_effect=_openTemp):
            leases = dispatch._capPhieuSecret(
                self.companyId, "capThu", self.declared, "subjectThu", traceId)
        return {lease.secretName for lease in leases}

    def _namesGrantedWithBrokenStore(self, traceId: str) -> set:
        """Sổ hỏng — nhánh lùi về (đường đi mà ca này canh)."""
        with mock.patch.object(
                coreSecrets, "openStore",
                side_effect=RuntimeError("sổ hỏng giả lập — do ca thử")):
            leases = dispatch._capPhieuSecret(
                self.companyId, "capThu", self.declared, "subjectThu", traceId)
        return {lease.secretName for lease in leases}

    def testFallbackIsNotWiderThanHealthyGrant(self):
        healthy = self._namesGrantedWithHealthyStore("trc_secfallback_healthy")
        fallback = self._namesGrantedWithBrokenStore("trc_secfallback_broken")

        self.assertTrue(
            fallback <= healthy,
            f"lùi về cấp {sorted(fallback - healthy)} — thứ sổ KHOẺ chưa từng "
            f"cấp cho cùng manifest `{self.companyId}`. Nhánh lùi (O8) chỉ "
            "được phép quay về đúng cách hệ chạy trước khi có broker, không "
            "được rộng hơn nó.")

    def testFallbackNeverGrantsANameOutsideTheDeclaredManifest(self):
        """Cùng bất biến, nhìn từ phía manifest thay vì phía sổ khoẻ.

        Thử phá (làm tay, không sửa `dispatch.py` để khỏi để lại một nhánh
        code chết trong repo): sửa tạm nhánh `except` của `_capPhieuSecret`
        thành trả thêm một `SecretLease` mang tên KHÔNG nằm trong `declared`
        — chạy lại ca này thì `fallbackNames` chứa cái tên lạ, phép
        `assertLessEqual` dưới đây đỏ ngay. Đã xác nhận bằng cách đọc lại
        nhánh lùi: nó dựng lease từ đúng vòng `for name in declared`, nên
        thêm một cái tên khác `declared` là ĐỔI code, không phải đổi input —
        chính là loại thay đổi ca này dựng ra để bắt.
        """
        fallback = self._namesGrantedWithBrokenStore("trc_secfallback_manifest")
        self.assertLessEqual(
            fallback, set(self.declared),
            f"lùi về cấp {sorted(fallback - set(self.declared))} — tên này "
            f"không hề có trong `secrets:` của companySpec.yaml `{self.companyId}`")


if __name__ == "__main__":
    unittest.main(verbosity=2)
