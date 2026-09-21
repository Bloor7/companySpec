#!/usr/bin/env python3
"""Đường dẫn viết cứng trong mã phải trỏ vào file CÓ THẬT.

═══════════════════════════════════════════════════════════════════════
VÌ SAO CA NÀY TỒN TẠI — BỐN CHỖ HỎNG CÙNG MỘT NGÀY
═══════════════════════════════════════════════════════════════════════

§36 đổi tên module `gateway.py` → `session.py` (bắt buộc: có một GÓI tên
`gateway/` rồi, để trùng thì `import gateway` trả về một gói RỖNG). Lần đổi
tên ấy quét `gateway` → `session` hơi rộng tay, và trúng bốn chỗ:

  1. `poller.GATEWAY` → `gateway/telegram/gateway.py` — file CHƯA TỪNG tồn
     tại. Hậu quả: MỌI tin nhắn của admin ra "Hệ gặp lỗi khi xử lý".
  2. `session.py` tự gọi lại chính nó qua `gateway.py` để làm mới "Bức tranh
     hiện tại". `Popen` bắn-đi-rồi-quên, stdout/stderr nuốt vào DEVNULL, nên
     nó hỏng TUYỆT ĐỐI IM LẶNG — admin chỉ thấy số liệu cũ dần.
  3. `codemap.py` tìm ca thử ở `ops/evals/` sau khi chúng dời sang
     `tests/evals/`. Có `if os.path.isfile()` bao ngoài nên bộ soát chỉ lặng
     lẽ bỏ qua toàn bộ ca thử — một hàng rào TỰ TẮT mà vẫn in "SOÁT LUẬT: sạch".
  4. `gateway.local.yaml` → `session.local.yaml`: file đè của `gateway.yaml`
     bị đổi tên rời khỏi file nó đè.

Không ca thử nào bắt được cả bốn, vì không ca nào CHẠY THỬ đường đó. Và cái
số 1 — nặng nhất — nằm im suốt vì admin chưa nhắn lần nào sau khi đổi tên:
journal có ĐÚNG 0 dòng `gateway lỗi`.

Bài học: **đổi tên một file thì phải grep hết mọi nơi gọi tên cũ** — và một
`grep` thủ công thì có ngày quên. Đây là bản tự động của phép grep ấy.
"""
import ast
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))

#: Thư mục KHÔNG soát. `lab/` được phép hỏng (P6); `main/` là vùng tin được
#: nhưng đang trống; phần còn lại là thư viện bên ngoài hoặc rác biên dịch.
BO_QUA_THU_MUC = {".venv", "__pycache__", "lab", "main", "hop", "workspaces",
                  ".git", "node_modules"}

#: Đuôi file KHÔNG đòi phải có sẵn: sổ sqlite do chính chương trình tạo ra ở
#: lần chạy đầu. Đòi nó tồn tại là đòi sai — repo là ĐẶC TẢ, không phải môi
#: trường chạy (F4).
BO_QUA_DUOI = (".sqlite", ".sqlite-journal", ".sqlite-wal", ".log")

#: File tuỳ chọn, CÓ TÊN, kèm lý do. Danh sách này cố ý ngắn và cố ý phải
#: khai tay: một cửa thoát rộng thì ca thử này thành vô dụng.
TUY_CHON = {
    # Bản đè cấu hình của admin. Không có cũng chạy — nhưng TÊN vẫn phải đúng,
    # vì sai tên thì nó im lặng không bao giờ được đọc (đúng lỗi số 4 ở trên).
    "registry/gateway.local.yaml": "bản đè tuỳ chọn của registry/gateway.yaml",
    # Sổ ghi những lần đọc ảnh hỏng. Mở bằng `"a"` kèm `os.makedirs`, tức là
    # nó chỉ ra đời khi có lỗi ĐẦU TIÊN — chưa có nghĩa là chưa hỏng lần nào.
    "backOffice/media-loi.jsonl": "sổ lỗi, tự sinh lúc có lỗi đầu tiên",
}


def _duongDanVietCung(tree):
    """Mọi `os.path.join(ROOT, "a", "b")` mà MỌI đoạn đều là chuỗi viết cứng.

    Chỉ nhận gốc là `ROOT`/`REPO_ROOT` — tức là đường dẫn tính từ gốc repo.
    Bỏ qua gốc `HERE` và mọi biến khác: chúng tương đối với file đang xét, nên
    ghép với gốc repo sẽ ra kết quả sai và ca thử sẽ kêu oan.
    """
    ra = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "join"):
            continue
        if not node.args:
            continue
        goc = node.args[0]
        if not (isinstance(goc, ast.Name) and goc.id in ("ROOT", "REPO_ROOT")):
            continue
        doan = []
        for arg in node.args[1:]:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                doan.append(arg.value)
            else:
                doan = None       # có biến ở giữa → không kết luận được
                break
        if doan:
            ra.append((node.lineno, doan))
    return ra


def _moiFilePython():
    for folder, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in BO_QUA_THU_MUC]
        for name in files:
            if name.endswith(".py"):
                yield os.path.join(folder, name)


class TestHardcodedPathsExist(unittest.TestCase):

    def testEveryLiteralPathFromRepoRootExists(self):
        """Quét cả repo. Đây là phép `grep` mà con người sẽ có ngày quên làm."""
        thieu, daSoat = [], 0
        for path in _moiFilePython():
            try:
                tree = ast.parse(open(path, encoding="utf-8").read())
            except (SyntaxError, UnicodeDecodeError):
                continue    # file không phải Python hợp lệ thì không phải việc của ca này
            for lineno, doan in _duongDanVietCung(tree):
                dich = os.path.join(REPO_ROOT, *doan)
                tuongDoi = "/".join(doan)
                if "*" in tuongDoi or dich.endswith(BO_QUA_DUOI):
                    continue
                if tuongDoi in TUY_CHON:
                    continue
                # Chỉ soát thứ TRÔNG NHƯ MỘT FILE. Thư mục thì nhiều chỗ tạo
                # ra lúc chạy, đòi có sẵn là đòi sai.
                if "." not in os.path.basename(tuongDoi):
                    continue
                daSoat += 1
                if not os.path.exists(dich):
                    thieu.append(
                        f"{os.path.relpath(path, REPO_ROOT)}:{lineno} → "
                        f"{tuongDoi} (KHÔNG TỒN TẠI)")

        self.assertGreater(daSoat, 10,
                           "bộ quét không tìm thấy đường dẫn nào — nó đang hỏng")
        self.assertEqual(
            thieu, [],
            "Có đường dẫn viết cứng trỏ vào file không tồn tại:\n  "
            + "\n  ".join(thieu)
            + "\n\nĐổi tên file thì phải sửa MỌI nơi gọi tên cũ.")

    def testOptionalFilesAreNamedNotJustSkipped(self):
        """Cửa thoát phải CÓ TÊN và có lý do, không phải một mẫu chung chung.

        `skipped` khác `inconclusive`: khai rõ thì đọc được trong file, còn bỏ
        qua bằng một mẫu rộng thì sáu tuần sau không ai biết còn gì đang lọt.
        """
        for ten, lyDo in TUY_CHON.items():
            with self.subTest(file=ten):
                self.assertTrue(lyDo.strip(),
                                f"{ten} nằm trong danh sách tuỳ chọn mà không nói vì sao")


class TestNoMeasuringToolLeavesApprovalCards(unittest.TestCase):
    """Phiếu duyệt không nằm yên trong sổ — nó là MỘT CÁI THẺ CÓ NÚT BẤM.

    ═══════════════════════════════════════════════════════════════════
    HOÁ ĐƠN: MỘT BẢN TRÌNH DIỄN TỰ CẤP CHO MÌNH MỘT QUYỀN THƯỜNG TRỰC
    ═══════════════════════════════════════════════════════════════════

    `travisDemo.py` cố ý đi qua cổng duyệt THẬT — đó là cả điểm của nó. Nhưng
    nó không dọn, nên đo 21/09: **15 phiếu `demo_` còn nằm trong sổ**, và một
    trong số đó admin đã bấm "luôn cho phép" trên Telegram → đẻ ra một quyền
    đứng THẬT cho `travisSelfTestCompany.recordWrite`.

    Lần này vô hại vì company ấy `internal: true` nên CEO không gọi được (C5).
    Nhưng cái vô hại là do MAY, không do thiết kế.

    `tests/regression` và `tests/drills` đều tự dọn; chỉ `travisDemo` quên.
    Ca này hỏi câu chung cho cả ba: **bộ đo có để lại thẻ bấm nào không.**
    """

    def _soTest(self):
        """Mở sổ bằng cửa đã có (`coreAudit.openStore`) — có `row_factory`.

        Đọc theo index (`r[0]`, `r[1]`…) thì thêm một cột vào `SELECT` là
        phải đếm lại ở mọi dòng dùng, và sai thì im lặng: `traceId` với
        `companyId` đều là chuỗi, `startswith` vẫn chạy ngon.
        """
        import core.audit as coreAudit
        if not os.path.exists(coreAudit.DEFAULT_STORE):
            self.skipTest("chưa có sổ backOffice")
        return coreAudit.openStore(), coreAudit.TEST_TRACE_PREFIXES

    def testApprovalLedgerHasNoLingeringTestCards(self):
        conn, prefixes = self._soTest()
        try:
            # Lọc ngay trong SQL, đúng khuôn `core/audit` đang dùng.
            # sql-an-toan: chỉ ghép `laTest` dựng từ hằng viết cứng
            laTest = " OR ".join(f"traceId LIKE '{p}%'" for p in prefixes)
            sot = [dict(r) for r in conn.execute(
                "SELECT traceId, companyId, capability, status "
                f"FROM approvalRequest WHERE {laTest}")]
        finally:
            conn.close()

        self.assertEqual(
            sot, [],
            f"{len(sot)} phiếu duyệt của BỘ ĐO còn trong sổ thật. Mỗi phiếu "
            "là một thẻ có nút trên Telegram của admin.\n  "
            + "\n  ".join(f"{r['traceId']} → {r['companyId']}.{r['capability']}"
                          f" [{r['status']}]" for r in sot[:8])
            + "\n\nMọi bộ đo phải tự dọn phiếu của LƯỢT CHẠY MÌNH "
              "(xem `travisDemo.don_dep`, `drills.don_dep`).")

    def testNoStandingGrantEverCameFromAMeasuringTool(self):
        """Dọn cái THẺ mà để lại cái QUYỀN là vá nhầm tầng.

        Sự cố 21/09 kể là "demo tự cấp cho mình một quyền thường trực", nhưng
        bản vá đầu chỉ xoá `approvalRequest`. Quyền đứng do sự cố đẻ ra vẫn
        sống — và còn bị commit vào repo.

        Cửa thật chỉ có MỘT (`approvals.whitelist_add`) và nay nó từ chối mọi
        phiếu mang nhãn bộ đo. Ca này canh KẾT QUẢ của luật ấy trên sổ thật:
        không quyền đứng nào được sinh từ một phiếu của bộ đo.
        """
        import json
        conn, prefixes = self._soTest()
        try:
            traceCua = {r["approvalId"]: r["traceId"] for r in conn.execute(
                "SELECT approvalId, traceId FROM approvalRequest")}
        finally:
            conn.close()

        duongDan = os.path.join(REPO_ROOT, "registry", "whitelist.jsonl")
        if not os.path.exists(duongDan):
            self.skipTest("chưa có sổ quyền đứng")
        with open(duongDan, encoding="utf-8") as fh:
            dong = [json.loads(l) for l in fh if l.strip()]

        daThuHoi = {d["revoke"] for d in dong if "revoke" in d}
        ban = []
        for d in dong:
            if not d.get("ruleId") or d["ruleId"] in daThuHoi:
                continue
            trace = traceCua.get(d.get("createdFromApprovalId") or "")
            if trace and trace.startswith(tuple(prefixes)):
                ban.append(f"{d['ruleId']} → {d['companyId']}.{d['capability']}"
                           f" (từ trace `{trace}`)")

        self.assertEqual(
            ban, [],
            "Có quyền ĐỨNG sinh ra từ phiếu của BỘ ĐO — một bản trình diễn "
            "tự cấp cho mình quyền thường trực:\n  " + "\n  ".join(ban)
            + "\n\nThu hồi bằng `approvals.whitelist_revoke(<ruleId>)`.")


class TestTheGatewaySpawnTargetActuallyRuns(unittest.TestCase):
    """Cái file mà poller ĐẺ RA cho mỗi tin nhắn phải chạy được.

    Ca trên bắt được "file không tồn tại". Ca này đi xa hơn một bước và hỏi
    câu quan trọng hơn: **chạy nó có ra JSON không?** Vì một đường dẫn đúng mà
    file bên trong hỏng thì admin vẫn nhận "Hệ gặp lỗi khi xử lý", và triệu
    chứng giống hệt.
    """

    def testPollerPointsAtAFileThatExists(self):
        sys.path.insert(0, os.path.join(REPO_ROOT, "gateway", "telegram"))
        import poller
        self.assertTrue(
            os.path.isfile(poller.GATEWAY),
            f"poller.GATEWAY trỏ vào {poller.GATEWAY} — file không tồn tại. "
            "Mọi tin nhắn của admin sẽ ra 'Hệ gặp lỗi khi xử lý'.")
        self.assertTrue(
            poller.GATEWAY.endswith("session.py"),
            "Module cửa vào tên `session.py` — KHÔNG được đặt là `gateway.py`: "
            "trùng tên với gói `gateway/` thì `import gateway` trả về gói rỗng.")

    def testRunningItReturnsJson(self):
        """Chạy thật với một update RỖNG — không gửi gì, không đổi gì."""
        import json
        import subprocess
        sys.path.insert(0, os.path.join(REPO_ROOT, "gateway", "telegram"))
        import poller

        proc = subprocess.run(
            [sys.executable, poller.GATEWAY, "handle"],
            input="{}", capture_output=True, text=True,
            cwd=REPO_ROOT, timeout=120)

        self.assertEqual(
            proc.returncode, 0,
            f"cửa vào thoát mã {proc.returncode}. stderr (đuôi):\n"
            + proc.stderr.strip()[-800:])
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            self.fail("cửa vào không trả về JSON — poller sẽ coi là lỗi.\n"
                      f"stdout: {proc.stdout[:300]}")
        self.assertIn("actions", payload)


if __name__ == "__main__":
    unittest.main(verbosity=2)
