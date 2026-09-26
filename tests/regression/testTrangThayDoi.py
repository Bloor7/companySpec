#!/usr/bin/env python3
"""Trang xem thay đổi (gateway/telegram/trang.py) — hiện đúng, và không chạy chữ lạ.

Nội dung thay đổi do MÁY PHỤ viết ra, tức là dữ liệu từ ngoài (P2). Trang ấy
mở trên điện thoại admin; một dòng `<script>` trong mã máy phụ viết mà lọt
qua không thoát thì nó CHẠY trong trình duyệt của admin. Ca này canh điều đó,
cộng hai điều admin cần thấy: dòng thêm/bỏ được tô, và tóm tắt bằng lời.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO_ROOT, "gateway", "telegram"))

import trang  # noqa: E402

DIFF = """diff --git a/web/a.html b/web/a.html
index 111..222 100644
--- a/web/a.html
+++ b/web/a.html
@@ -1,2 +1,2 @@
-<p>cũ</p>
+<script>alert('x')</script>
 giữ nguyên
"""
O = {"viecId": "y_thu", "tieuDe": "Thử <b>đậm</b>", "moTa": "", "trangThai": "choXem",
     "nhanh": "y/y_thu", "tepDoi": [{"ten": "web/a.html", "them": 1, "bot": 1}],
     "diff": DIFF, "daCat": False}


class TestTrangThayDoi(unittest.TestCase):

    def setUp(self):
        self.p = trang.dung_trang(O)

    def testUntrustedContentIsEscaped(self):
        self.assertNotIn("<script>", self.p)
        self.assertNotIn("<b>đậm</b>", self.p)
        self.assertIn("&lt;script&gt;", self.p)

    def testAddedAndRemovedLinesAreMarked(self):
        self.assertIn('class="d them">+&lt;script&gt;', self.p)
        self.assertIn('class="d bot">-&lt;p&gt;cũ&lt;/p&gt;', self.p)

    def testPlainSummaryAndStatusInWords(self):
        self.assertIn("Đã thay đổi 1 tệp", self.p)
        self.assertIn("chờ đại ca đồng ý", self.p)       # không phải "choXem"
        self.assertNotIn("choXem", self.p)

    def testTruncationIsSaidOutLoud(self):
        self.assertIn("quá dài", trang.dung_trang(dict(O, daCat=True)))


if __name__ == "__main__":
    unittest.main()
