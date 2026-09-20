#!/usr/bin/env python3
"""Đối chiếu core/memory với trí nhớ ĐANG CHẠY của gateway.

VÌ SAO CA NÀY PHẢI CÓ TRƯỚC KHI NỐI DÂY

`gateway/telegram/session.py` đang giữ trí nhớ của admin và đã chạy qua nhiều
tháng. Chuyển người gọi sang `core/memory` mà không chứng minh hai bên trả lời
GIỐNG NHAU thì ta không "gom về một chỗ" — ta tạo NGUỒN SỰ THẬT THỨ HAI cho
thứ riêng tư nhất trong hệ. Dự án này đã trả giá cho đúng chuyện đó một lần,
với "hạn mức ăn uống" ra hai con số mà cả hai đều không lỗi.

Đây là bản sao của lý lẽ trong tests/regression/testPolicyParity.py, áp cho
một thứ đắt hơn: sai ở policy thì admin bị hỏi thừa một câu, sai ở đây thì một
điều admin đã dặn ta nhớ **biến mất mà không có dòng lỗi nào**.

═══ PHÉP ĐO NGÀY 2026-09-20, TRƯỚC KHI VÁ ═══

Ba trên bốn mốc thời gian trong ngày cho ra kết quả KHÁC NHAU:

    moc                              core/memory      gateway
    08:00 VN 20/09                   [21/09]          [20/09, 21/09]   LỆCH
    12:00 VN 20/09                   [21/09]          [20/09, 21/09]   LỆCH
    23:30 VN 20/09                   [21/09]          [20/09, 21/09]   LỆCH
    00:30 VN 21/09                   [21/09]          [21/09]

Hai nguyên nhân, cả hai đều đã có tên trong bảng bẫy của CLAUDE.md:

  1. **So chuỗi ngày nguyên bản.** `recall` so `expiresAt` (10 ký tự,
     "2026-09-20") với `utcNow()` (20 ký tự, "2026-09-20T05:00:00Z"). Chuỗi
     ngắn là tiền tố nên nó LUÔN nhỏ hơn — dòng rụng ngay đầu ngày hết hạn,
     thay vì cuối ngày.
  2. **Lọc theo UTC, còn ngày của admin tính theo giờ VN.** Gateway dùng
     `datetime.now(TZ_VN)`, core dùng UTC. Lệch bảy tiếng.

Và `[đến 2026-10-15]` trong tiếng Việt nghĩa là **đúng HẾT ngày 15/10**, nên
gateway đúng và core sai. Cái sai của core nghiêng về hướng MẤT DỮ LIỆU.
"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "gateway", "telegram"))

import session  # noqa: E402
from core.contracts import MemoryItem, MemoryKind, MemoryTier, newId  # noqa: E402
import core.memory as coreMemory  # noqa: E402


#: Ngày rụng đem ra thử, và một mốc "hôm nay" để so.
HANS = ("2026-09-19", "2026-09-20", "2026-09-21")
HOM_NAY_VN = "2026-09-20"

#: Bốn mốc, mỗi mốc ba cách gọi cùng MỘT khoảnh khắc:
#:   (nhãn, đồng hồ treo tường VN, cùng khoảnh khắc đó theo UTC, ngày VN)
#:
#: Mốc cuối là 00:30 sáng 21/09 giờ VN — theo UTC thì vẫn còn là 20/09. Đúng
#: khoảng 00:00–07:00 mà bảng bẫy CLAUDE.md đã gọi tên một lần với bộ lọc ngày
#: của Notion, và nó quay lại ở đây vì cùng một lý do: ngày của admin không
#: phải ngày của UTC.
MOC = (
    ("08:00 VN 20/09", "2026-09-20T08:00:00", "2026-09-20T01:00:00Z", "2026-09-20"),
    ("12:00 VN 20/09", "2026-09-20T12:00:00", "2026-09-20T05:00:00Z", "2026-09-20"),
    ("23:30 VN 20/09", "2026-09-20T23:30:00", "2026-09-20T16:30:00Z", "2026-09-20"),
    ("00:30 VN 21/09", "2026-09-21T00:30:00", "2026-09-20T17:30:00Z", "2026-09-21"),
)


def _gatewayKeeps(ngayVn: str) -> list:
    """Đúng phép cắt mà `session.profile_block` đang dùng, không phải bản chép.

    Gọi thẳng `session.HAN_DONG` + phép so của nó, để nếu ai sửa gateway thì ca
    này thấy — chép lại một bản thứ hai ở đây là tạo ra đúng thứ ca này đi tìm.
    """
    kept = []
    for han in HANS:
        dong = f"- (p9) [đến {han}] nội dung thử"
        match = session.HAN_DONG.match(dong)
        assert match, "định dạng dòng hồ sơ đã đổi — sửa cả hai bên"
        if match.group(1) < ngayVn:
            continue
        kept.append(han)
    return sorted(kept)


class TestExpiryCutIsTheSameOnBothSides(unittest.TestCase):
    """Hai bên phải rụng CÙNG một lúc, không lệch một ngày."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.conn = coreMemory.openStore(
            os.path.join(self.folder.name, "memory.sqlite"))
        for han in HANS:
            coreMemory.remember(self.conn, MemoryItem(
                tier=MemoryTier.personal, kind=MemoryKind.fact,
                content=f"điều chỉ đúng tới {han}", memoryId=newId("mem"),
                expiresAt=han))

    def tearDown(self):
        self.conn.close()
        self.folder.cleanup()

    def testEveryMomentOfTheDayAgrees(self):
        """Bốn mốc trong ngày, hai bên phải giữ ĐÚNG cùng một tập dòng.

        `now` truyền vào là ĐỒNG HỒ TREO TƯỜNG CỦA ADMIN, không phải UTC — đó
        là hợp đồng của `recall`, và ca dưới đây đo cái giá của việc phá nó.
        """
        for label, nowVn, _nowUtc, ngayVn in MOC:
            with self.subTest(moc=label):
                core = sorted(
                    item.expiresAt for item in coreMemory.recall(
                        self.conn, MemoryTier.personal, now=nowVn))
                self.assertEqual(
                    core, _gatewayKeeps(ngayVn),
                    f"{label}: core/memory và gateway cắt ngày rụng khác nhau "
                    "— chuyển người gọi lúc này sẽ làm hồ sơ admin biến mất "
                    "sớm, và không có dòng lỗi nào")

    def testPassingUtcIsTheHazardAndItIsMeasurable(self):
        """Đưa UTC vào thay vì giờ admin thì lệch — và lệch ĐÚNG MỘT NGÀY.

        Ca này không đòi sửa gì; nó ĐÓNG ĐINH cái giá, để người sau không
        "dọn cho gọn" bằng cách đổi người gọi sang `utcNow()`.

        Bảy tiếng chênh lệch nghĩa là mỗi đêm từ 00:00 tới 07:00 giờ VN, UTC
        vẫn đang ở ngày hôm trước. Trong khoảng đó, một điều admin dặn "đến
        hôm qua" sẽ SỐNG LẠI thêm một đêm — và một điều "đến hôm nay" sẽ chết
        sớm nếu lệch theo chiều kia. Cả hai đều im lặng.
        """
        label, nowVn, nowUtc, ngayVn = MOC[-1]
        theoGioAdmin = sorted(item.expiresAt for item in coreMemory.recall(
            self.conn, MemoryTier.personal, now=nowVn))
        theoUtc = sorted(item.expiresAt for item in coreMemory.recall(
            self.conn, MemoryTier.personal, now=nowUtc))

        self.assertEqual(theoGioAdmin, _gatewayKeeps(ngayVn))
        self.assertNotEqual(
            theoUtc, theoGioAdmin,
            f"{label}: hai múi giờ ra cùng kết quả — hoặc dữ liệu thử đã mất "
            "mốc 00:00–07:00, hoặc phép cắt không còn nhìn vào ngày nữa")
        self.assertEqual(
            theoUtc, _gatewayKeeps("2026-09-20"),
            "đưa UTC vào thì core trả lời cho NGÀY HÔM TRƯỚC")

    def testTheExpiryDayItselfIsStillValid(self):
        """`[đến 15/10]` nghĩa là đúng HẾT ngày 15/10, không phải tới đêm 14.

        Đây là câu hỏi NGỮ NGHĨA, và nó phải được trả lời ở một chỗ chứ không
        phải suy ra từ cách so chuỗi. Sai chiều này thì mỗi điều admin dặn đều
        mất đúng một ngày cuối, mãi mãi, mà không ai thấy.
        """
        core = [item.expiresAt for item in coreMemory.recall(
            self.conn, MemoryTier.personal, now="2026-09-20T05:00:00Z")]
        self.assertIn(
            HOM_NAY_VN, core,
            "dòng hết hạn HÔM NAY đã rụng ngay từ sáng — `đến ngày X` phải "
            "còn đúng hết ngày X")

    def testYesterdayIsGoneOnBothSides(self):
        """Chiều kia: đừng vá quá tay thành ra không bao giờ rụng."""
        core = [item.expiresAt for item in coreMemory.recall(
            self.conn, MemoryTier.personal, now="2026-09-20T05:00:00Z")]
        self.assertNotIn("2026-09-19", core)
        self.assertNotIn("2026-09-19", _gatewayKeeps(HOM_NAY_VN))


class TestOneLawTwoBodies(unittest.TestCase):
    """`isStillValid` (Python) và `_NOT_EXPIRED` (SQL) phải trả lời GIỐNG NHAU.

    Chúng là hai thân của cùng một luật, nên chúng CÓ THỂ lệch — và lệch thì
    không có dòng lỗi nào, chỉ có một dòng hồ sơ có mặt ở chỗ này và vắng ở
    chỗ kia. Đây là lần thứ ba dự án này gặp hình dạng ấy (`Verification.
    isVerified` vs `concludeTask`, rồi `canWhitelist` viết ở ba nơi), nên lần
    này nó được canh bằng một ma trận chứ không bằng lời hứa.
    """

    CASES = (
        (None, "2026-09-20T12:00:00"),
        ("", "2026-09-20T12:00:00"),
        ("2026-09-19", "2026-09-20T00:00:01"),
        ("2026-09-20", "2026-09-20T00:00:01"),
        ("2026-09-20", "2026-09-20T23:59:59"),
        ("2026-09-21", "2026-09-20T23:59:59"),
        ("2026-09-20T23:59:59Z", "2026-09-20T12:00:00"),
        ("2026-09-20T06:00:00Z", "2026-09-20T12:00:00"),
        ("2027-01-01", "2026-09-20T12:00:00"),
    )

    def testSqlAndPythonAnswerTheSameQuestion(self):
        with tempfile.TemporaryDirectory() as folder:
            conn = coreMemory.openStore(os.path.join(folder, "m.sqlite"))
            try:
                for expiresAt, now in self.CASES:
                    with self.subTest(expiresAt=expiresAt, now=now):
                        conn.execute("DELETE FROM memoryItem")
                        memoryId = newId("mem")
                        conn.execute(
                            "INSERT INTO memoryItem (memoryId, tier, kind, "
                            "content, source, scopeId, createdAt, expiresAt) "
                            "VALUES (?,?,?,?,'','','2026-01-01T00:00:00Z',?)",
                            (memoryId, MemoryTier.personal.value,
                             MemoryKind.fact.value, "điều thử", expiresAt))
                        conn.commit()

                        bySql = bool(coreMemory.recall(
                            conn, MemoryTier.personal, now=now))
                        byPython = coreMemory.isStillValid(expiresAt, now)
                        self.assertEqual(
                            bySql, byPython,
                            f"SQL nói {bySql}, Python nói {byPython} cho "
                            f"expiresAt={expiresAt!r} lúc {now!r}")
            finally:
                conn.close()


class TestMalformedExpiryIsStoppedAtTheDoor(unittest.TestCase):
    """Ghi vào được mà không đọc ra được là hình dạng hỏng tệ nhất ở đây.

    `expiresAt = ""` từng lọt: bộ đọc SQL coi chuỗi rỗng là ĐÃ RỤNG, bộ đọc
    Python coi là KHÔNG HẠN. Nên mẩu nhớ ghi thành công, `remember` trả về
    bình thường, không lỗi gì — rồi `recall` không bao giờ thấy nó nữa.

    Chính ma trận SQL↔Python ở trên bắt được; không ai đọc ra bằng mắt.
    """

    def _reject(self, expiresAt):
        with tempfile.TemporaryDirectory() as folder:
            conn = coreMemory.openStore(os.path.join(folder, "m.sqlite"))
            try:
                with self.assertRaises(coreMemory.MemoryValidationError):
                    coreMemory.remember(conn, MemoryItem(
                        tier=MemoryTier.personal, kind=MemoryKind.fact,
                        content="điều thử", memoryId=newId("mem"),
                        expiresAt=expiresAt))
            finally:
                conn.close()

    def testEmptyStringIsRefused(self):
        self._reject("")

    def testGarbageDateIsRefused(self):
        for bad in ("31/10/2026", "hôm nào đó", "2026-13-45x", "2026-9-5"):
            with self.subTest(expiresAt=bad):
                self._reject(bad)

    def testNoneMeansNoExpiryAndIsFine(self):
        """Chiều kia: đừng vá quá tay thành ra không cất được điều vĩnh viễn."""
        with tempfile.TemporaryDirectory() as folder:
            conn = coreMemory.openStore(os.path.join(folder, "m.sqlite"))
            try:
                coreMemory.remember(conn, MemoryItem(
                    tier=MemoryTier.personal, kind=MemoryKind.fact,
                    content="điều luôn đúng", memoryId=newId("mem")))
                self.assertEqual(
                    len(coreMemory.recall(conn, MemoryTier.personal,
                                          now="2099-01-01T00:00:00")), 1)
            finally:
                conn.close()


class TestGatewayUsesTheCoreLaw(unittest.TestCase):
    """Gateway phải HỎI core, không giữ bản sao của luật.

    Nếu ai đó chép phép so ngược trở lại `profile_block` thì hai bên lại lệch,
    và lần sau không có ai đi đo lại.
    """

    def testProfileBlockCallsIsStillValid(self):
        calls = []
        original = coreMemory.isStillValid

        def spy(expiresAt, now):
            calls.append((expiresAt, now))
            return original(expiresAt, now)

        session.coreMemory.isStillValid = spy
        try:
            block = session.profile_block()
        finally:
            session.coreMemory.isStillValid = original

        if not block:
            self.skipTest("chưa có PROFILE.md")
        self.assertTrue(
            calls,
            "`profile_block` không gọi `core.memory.isStillValid` — gateway "
            "đang giữ một bản thứ hai của luật ngày rụng")

    def testItAsksWithAdminWallClockNotUtc(self):
        """Mốc đưa vào phải là giờ VN. Đưa UTC là trả lời cho ngày khác.

        So bằng NGÀY chứ không so từng giây: ca chạy ở giờ nào cũng phải đúng,
        và hai múi giờ chỉ khác nhau ở phần ngày trong khoảng 00:00–07:00.
        """
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        calls = []
        original = coreMemory.isStillValid

        def spy(expiresAt, now):
            calls.append(now)
            return original(expiresAt, now)

        session.coreMemory.isStillValid = spy
        try:
            session.profile_block()
        finally:
            session.coreMemory.isStillValid = original

        if not calls:
            self.skipTest("PROFILE.md chưa có dòng nào mang hạn dùng")
        ngayVn = _dt.now(_tz(_td(hours=7))).strftime("%Y-%m-%d")
        for now in calls:
            self.assertEqual(
                now[:10], ngayVn,
                f"gateway đưa vào ngày {now[:10]} trong khi hôm nay ở VN là "
                f"{ngayVn} — đang lọc theo múi giờ khác")


class TestRecallIsDeterministic(unittest.TestCase):
    """`now` truyền vào phải QUYẾT ĐỊNH kết quả, không phải trang trí.

    Một hàm nhận `now` rồi vẫn tự đọc đồng hồ là hàm không kiểm được — và nó
    trông y hệt hàm kiểm được, nên không ai đi tìm.
    """

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.conn = coreMemory.openStore(
            os.path.join(self.folder.name, "memory.sqlite"))

    def tearDown(self):
        self.conn.close()
        self.folder.cleanup()

    def testExpiringSoonHonoursTheGivenNow(self):
        """`expiringSoon(now=...)` phải trả lời theo mốc ĐƯỢC ĐƯA, không theo
        đồng hồ máy.

        Bản đầu nhận `now` cho phần cận dưới nhưng dựng `horizon` bằng
        `datetime.now(timezone.utc)` — tức là nửa phép so đọc đồng hồ thật.
        Chạy ca này vào một ngày khác thì kết quả khác, và không ai biết vì
        sao.
        """
        coreMemory.remember(self.conn, MemoryItem(
            tier=MemoryTier.personal, kind=MemoryKind.fact,
            content="sắp rụng", memoryId=newId("mem"),
            expiresAt="2027-03-05"))

        soon = coreMemory.expiringSoon(
            self.conn, withinDays=7, now="2027-03-01T00:00:00Z")
        self.assertEqual(
            [item.expiresAt for item in soon], ["2027-03-05"],
            "`expiringSoon` không nghe mốc thời gian được đưa vào — nó đang "
            "tự đọc đồng hồ máy")

        farAway = coreMemory.expiringSoon(
            self.conn, withinDays=7, now="2026-01-01T00:00:00Z")
        self.assertEqual(farAway, [])


class TestSecretsNeverReachEitherMemory(unittest.TestCase):
    """P4 — chặn ở CỬA VÀO, và phải chặn ở cả hai đường vào."""

    def testCoreRefusesASecret(self):
        with tempfile.TemporaryDirectory() as folder:
            conn = coreMemory.openStore(os.path.join(folder, "m.sqlite"))
            try:
                with self.assertRaises(coreMemory.SecretInMemoryError):
                    coreMemory.remember(conn, MemoryItem(
                        tier=MemoryTier.personal, kind=MemoryKind.fact,
                        content="khoá notion là ntn_" + "a" * 30,
                        memoryId=newId("mem")))
            finally:
                conn.close()

    def testTheRealProfileHoldsNoSecret(self):
        """Soi HỒ SƠ THẬT bằng chính bộ dò của core.

        Hồ sơ do model đề xuất rồi admin bấm duyệt, nên một khoá hoàn toàn có
        thể lọt vào — và nó sẽ đi theo MỌI prompt về sau, sang mọi nhà cung
        cấp, không gọi về được.
        """
        block = session.profile_block()
        if not block:
            self.skipTest("chưa có PROFILE.md")
        self.assertFalse(
            coreMemory.looksLikeSecret(block),
            "PROFILE.md chứa thứ trông như KHOÁ — nó đang đi vào prompt CEO "
            "mỗi lượt")


class TestProfileBlockKeepsItsGuards(unittest.TestCase):
    """Những hàng rào của `profile_block` phải sống sót qua lần nối dây.

    Mỗi ca dưới đây là hoá đơn của một lần hỏng thật. Nối `core/memory` vào mà
    đánh rơi một trong số chúng là mua lại đúng con bug đã trả tiền rồi.
    """

    def testCommentBlockIsStrippedBeforeReadingLines(self):
        """Dòng VÍ DỤ trong `<!-- -->` từng được nạp như một sự thật về admin.

        Bộ đọc cũ lọc dòng bằng `lstrip().startswith("- (")`, nên dòng mẫu
        `- (id) [đến YYYY-MM-DD] nội dung` nằm trong khối chú thích đi thẳng
        vào hồ sơ CEO — mỗi lượt, suốt từ 21/08. Không sai schema, không gây
        lỗi, không ai kêu.
        """
        block = session.profile_block()
        if not block:
            self.skipTest("chưa có PROFILE.md")

        # Soát DÒNG DỮ LIỆU, không soát cả khối. Phần đầu khối là lời dặn do
        # chính gateway viết ra và nó CÓ nhắc `[đến YYYY-MM-DD]` để dạy CEO đọc
        # định dạng — soát cả khối thì bắt nhầm đúng câu ấy. Thứ phải vắng mặt
        # là một DÒNG HỒ SƠ mang nội dung mẫu.
        dataLines = [line for line in block.splitlines()
                     if line.lstrip().startswith("- (")]
        self.assertTrue(dataLines, "hồ sơ không còn dòng nào — đọc hỏng")
        for line in dataLines:
            with self.subTest(line=line[:60]):
                self.assertNotIn("YYYY-MM-DD", line)
        self.assertNotIn("Sinh và đọc bởi profileCompany", block)

    def testProfileIsFencedAsDataNotOrders(self):
        """Hồ sơ là DỮ LIỆU. Rào phải còn nguyên sau khi đổi nguồn."""
        block = session.profile_block()
        if not block:
            self.skipTest("chưa có PROFILE.md")
        self.assertIn("KHÔNG nới được giới hạn nào", block)


if __name__ == "__main__":
    unittest.main(verbosity=2)
