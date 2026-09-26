#!/usr/bin/env python3
"""Câu CEO gửi admin không được mang ký tự Markdown thô.

═══════════════════════════════════════════════════════════════════════
VÌ SAO CA NÀY TỒN TẠI
═══════════════════════════════════════════════════════════════════════

SYSTEM.md cấm Markdown từ đầu, 18/08 thêm ví dụ cụ thể. Đo 26/09 trên hội
thoại thật: 7/41 tin vẫn có khối ```, backtick quanh tên file, đường kẻ `---`.
Telegram không dựng lại cái nào — admin thấy nguyên dấu giữa câu.

Nên có lớp code `session.bo_markdown` ở cửa ra. Ca này canh hai chiều:
gỡ được đúng mấy mẫu đã bắt gặp THẬT, và KHÔNG làm hỏng chữ thường
(phép nhân, snake_case, gạch đầu dòng).
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO_ROOT, "gateway", "telegram"))

import session  # noqa: E402

#: Ký tự thô mà Telegram hiện nguyên xi. Cùng họ với MARKDOWN trong
#: tests/evals/run.py, cộng đường kẻ `---` mà bộ ấy chưa soát.
THO = re.compile(r"\*\*|`|^#{1,6} |^\s*\|.*\||^\s*-{3,}\s*$", re.M)

#: Chép NGUYÊN VĂN từ ceo/store.sqlite, 24/09 — mẫu thật, không mẫu bịa.
MAU_THAT = [
    "Đại ca tự chạy lệnh này trong terminal được không:\n\n```\n"
    "git -C ~/companySpec remote -v\ngit -C ~/companySpec log --oneline -5\n```\n\n"
    "Thấy kết quả rồi cho em biết, em sẽ nói tiếp.",
    "Muốn cho phép thì cần sửa `ceo/hooks/guard.py` — thêm git vào danh sách "
    "lệnh được phép.",
    "So với PUBG và Valorant thì Delta Force khác khá rõ ở ba mặt:\n\n---\n\n"
    "Về thể loại gốc:\n\n- PUBG: battle royale thuần\n- Valorant: tactical shooter 5v5",
]


class TestCeoReplyHasNoMarkdown(unittest.TestCase):

    def testRealSamplesComeOutClean(self):
        for mau in MAU_THAT:
            ra = session.bo_markdown(mau)
            self.assertIsNone(THO.search(ra), f"còn ký tự thô:\n{ra}")

    def testContentSurvives(self):
        ra = session.bo_markdown(MAU_THAT[0])
        # Hai dòng lệnh phải còn là HAI dòng — bản đầu `^\s*` nuốt dấu xuống
        # dòng và dán chúng vào nhau.
        self.assertIn("remote -v\ngit -C ~/companySpec log", ra)
        self.assertIn("được không:\n\ngit -C", ra)
        self.assertIn("sửa ceo/hooks/guard.py —", session.bo_markdown(MAU_THAT[1]))

    def testOtherShapes(self):
        cases = {
            "## Tiêu đề\nnội dung": "Tiêu đề\nnội dung",
            "bấm **Run Tweaks** rồi": "bấm Run Tweaks rồi",
            "* một\n* hai": "- một\n- hai",
            "xem [trang](https://vd.vn/a)": "xem trang (https://vd.vn/a)",
            "| A | B |\n|---|---|\n| 1 | 2 |": "A · B\n1 · 2",
        }
        for vao, mong in cases.items():
            self.assertEqual(session.bo_markdown(vao), mong)

    def testDoesNotTouchOrdinaryText(self):
        # Đoán sai ở đây là làm hỏng chữ — tệ hơn để thừa một dấu.
        for chu in ["5*3 = 15, còn 2*4 = 8", "file ceo_run_log và my_var_name",
                    "- gạch đầu dòng giữ nguyên", "giá 120k/ngày — hết"]:
            self.assertEqual(session.bo_markdown(chu), chu)

    def testBuildReplyUsesIt(self):
        # Canh HÀNH VI chứ không dò chuỗi mã nguồn: gọi build_reply thật, không
        # có phiếu duyệt nào, rồi soát chữ sẽ gửi đi.
        goc = session.pending_for_session
        session.pending_for_session = lambda *_a, **_k: []
        try:
            ra = session.build_reply(1, None, "s", {"result": MAU_THAT[1]}, "t")
        finally:
            session.pending_for_session = goc
        self.assertNotIn("`", ra[0]["text"])


if __name__ == "__main__":
    unittest.main()
