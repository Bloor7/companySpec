#!/usr/bin/env python3
"""Thợ hỏi "có việc không?" bằng lệnh ĐỌC, không bằng lệnh GHI.

═══════════════════════════════════════════════════════════════════════
HOÁ ĐƠN CỦA CA NÀY — 294 THẺ DUYỆT TRONG MỘT NGÀY
═══════════════════════════════════════════════════════════════════════

Bản cũ của `hop/tho.py:mot_vong` gọi `xuongCompany.nhanViec` ngay dòng đầu
mỗi vòng — tức là hỏi một câu ĐỌC bằng một lời gọi GHI.

Thợ chạy 6 phút/lần ≈ 240 vòng mỗi ngày. Quyền đứng admin cấp có trần 20
lần/ngày. Hết trần sau khoảng hai tiếng, và mỗi vòng còn lại đẻ một thẻ duyệt.

Đo 2026-09-20, lưu lượng THẬT (đã bỏ nhãn bộ đo `reg_ e2e_ demo_`):

    nhanViec gọi 330 lần  →  36 chạy được  ·  294 HỎI DUYỆT

...trong khi xưởng có đúng 3 việc và cả 3 đều ở `choXem`, tức là KHÔNG CÓ GÌ
để nhận. Admin bấm "luôn cho phép" năm lần — sổ whitelist có năm dòng trùng —
và nó vẫn hỏi tiếp, vì trần là 20/ngày chứ không phải vô hạn.

Manifest còn ghi "một lần cho aiLam=hop là thợ nhận việc suốt 90 ngày không
hỏi nữa". Ý định ghi rõ, hiệu lực thì ngược lại — đúng họ với bẫy "chú thích
nói một đằng, giá trị làm một nẻo".

═══ CA NÀY CANH HAI CHIỀU, VÀ CHIỀU THỨ HAI QUAN TRỌNG KHÔNG KÉM ═══

  · chiều IM — xưởng không có việc nhận được thì KHÔNG chạm lệnh ghi nào;
  · chiều TỈNH — có việc thật thì vẫn phải nhận. Vá quá tay thành ra thợ ngủ
    quên thì hỏng theo hướng im lặng, và im lặng là hướng không ai đi tìm.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO_ROOT, "hop"))

import tho  # noqa: E402


class _ThoGia:
    """Thay `goi` bằng bản giả để ĐẾM xem thợ đã gọi những gì.

    Không dựng cầu, không chạm sổ thật, không cần `~/.cau_token` (thợ thật
    chạy trong hộp nên máy này không có khoá đó).
    """

    def __init__(self, cacViec, dsViecHong=False):
        self.cacViec = cacViec
        self.dsViecHong = dsViecHong
        self.daGoi = []

    def __call__(self, company, capability, inputValue, tra=60):
        self.daGoi.append(capability)
        if capability == "dsViec":
            if self.dsViecHong:
                return {"status": "failed", "summary": "sổ hỏng"}
            return {"status": "ok",
                    "output": {"cacViec": self.cacViec,
                               "tong": len(self.cacViec)}}
        if capability == "nhanViec":
            return {"status": "needsApproval", "summary": "cần admin duyệt"}
        return {"status": "ok", "output": {}}


class WorkerTestCase(unittest.TestCase):

    def setUp(self):
        self._goiThat, self._noiThat = tho.goi, tho.noi
        tho.noi = lambda *a, **k: None

    def tearDown(self):
        tho.goi, tho.noi = self._goiThat, self._noiThat

    def _chayMotVong(self, cacViec, dsViecHong=False):
        gia = _ThoGia(cacViec, dsViecHong)
        tho.goi = gia
        tho.mot_vong(True)
        return gia.daGoi


class TestEmptyWorkshopNeverAsksAdmin(WorkerTestCase):
    """Chiều IM — không có việc thì không phiền ai."""

    def testThreeJobsAllWaitingForReview(self):
        """Đúng trạng thái THẬT của xưởng ngày 20/09: 3 việc, đều `choXem`."""
        daGoi = self._chayMotVong([{"trangThai": "choXem"}] * 3)
        self.assertEqual(daGoi, ["dsViec"])
        self.assertNotIn(
            "nhanViec", daGoi,
            "thợ vẫn gọi lệnh GHI khi xưởng không có việc nhận được — "
            "mỗi vòng như thế là một thẻ duyệt gửi cho admin")

    def testCompletelyEmptyWorkshop(self):
        self.assertEqual(self._chayMotVong([]), ["dsViec"])

    def testOnlyFinishedOrAbandonedJobs(self):
        """`daGop`/`bo`/`hong` là việc đã đóng — không có gì để nhận."""
        daGoi = self._chayMotVong([{"trangThai": "daGop"},
                                   {"trangThai": "bo"},
                                   {"trangThai": "hong"}])
        self.assertEqual(daGoi, ["dsViec"])

    def testPollingCapabilityIsReadTier(self):
        """`dsViec` phải là `read` — nếu không thì bản vá này vô nghĩa.

        Cả cách chữa đứng trên đúng một điều: lệnh dùng để HỎI thì đi thẳng,
        không qua cửa duyệt. Đổi `dsViec` thành `write` là bản vá tự vô hiệu.
        """
        import yaml
        spec = yaml.safe_load(open(
            os.path.join(REPO_ROOT, "companies", "xuongCompany",
                         "companySpec.yaml"), encoding="utf-8"))
        caps = {c["name"]: c for c in spec["capabilities"]}
        self.assertEqual(caps["dsViec"]["riskTier"], "read")
        self.assertEqual(caps["nhanViec"]["riskTier"], "write")


class TestRealWorkStillGetsPickedUp(WorkerTestCase):
    """Chiều TỈNH — vá quá tay thì thợ ngủ quên, và im lặng thì không ai tìm."""

    def testANewJob(self):
        self.assertIn("nhanViec", self._chayMotVong([{"trangThai": "moi"}]))

    def testAJobThatDiedMidway(self):
        """`dangLam` mà nhịp tim cũ = đứt gánh. Dở dang phải được làm TRƯỚC."""
        daGoi = self._chayMotVong([{"trangThai": "choXem"},
                                   {"trangThai": "dangLam"}])
        self.assertIn("nhanViec", daGoi)

    def testAPausedJob(self):
        self.assertIn("nhanViec", self._chayMotVong([{"trangThai": "tamDung"}]))

    def testUnreadableLedgerStillTriesToClaim(self):
        """Không đọc được sổ KHÁC xưởng trống.

        Gộp hai câu đó lại là để một lỗi đọc sổ làm thợ ngủ mãi mãi trong im
        lặng — O10, số 0 không được trông giống một kết quả tốt.
        """
        daGoi = self._chayMotVong([], dsViecHong=True)
        self.assertIn("nhanViec", daGoi)


class TestTheStatusListMatchesTheManifest(unittest.TestCase):
    """Danh sách trạng thái nhận được phải là trạng thái CÓ THẬT trong schema.

    Gõ sai một tên (`tamDung` → `tamDưng`) thì thợ im lặng bỏ qua đúng loại
    việc ấy mãi mãi, và không có dòng lỗi nào.
    """

    def testEveryPollableStatusExistsInTheSchema(self):
        import yaml
        spec = yaml.safe_load(open(
            os.path.join(REPO_ROOT, "companies", "xuongCompany",
                         "companySpec.yaml"), encoding="utf-8"))
        caps = {c["name"]: c for c in spec["capabilities"]}
        hopLe = set(caps["dsViec"]["inputSchema"]["properties"]
                    ["trangThai"]["enum"])
        for trangThai in tho.TRANG_THAI_NHAN_DUOC:
            with self.subTest(trangThai=trangThai):
                self.assertIn(
                    trangThai, hopLe,
                    f"`{trangThai}` không có trong enum của xuongCompany — "
                    "thợ sẽ lặng lẽ không bao giờ khớp loại việc này")


if __name__ == "__main__":
    unittest.main(verbosity=2)
