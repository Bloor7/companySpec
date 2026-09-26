#!/usr/bin/env python3
"""Dựng trang HTML cho admin XEM TRỰC TIẾP những chỗ một việc đã thay đổi.

26/09 admin hỏi "show anh xem" và nhận về một lệnh terminal. Admin: "anh muốn
xem trực tiếp… nếu trong tele không thể xem được thì anh tính làm dashboard".
Xem được — Telegram gửi được tệp, bấm vào là mở trên điện thoại.

Trang tự chứa: không tải font, không script, không gì từ ngoài. Mở được khi
không có mạng, và không rò việc admin đang xem cái gì ra đâu cả.

Chữ trên trang theo docs/NOI_DE_HIEU.md: nói bằng lời trước, mã sau.
"""
import html

_CSS = """
:root{--nen:#fafaf9;--chu:#1c1917;--mo:#78716c;--vien:#e7e5e4;--the:#fff;
--them:#dcfce7;--them-chu:#14532d;--bot:#fee2e2;--bot-chu:#7f1d1d;--moc:#eef2ff}
@media (prefers-color-scheme:dark){:root{--nen:#1c1917;--chu:#f5f5f4;--mo:#a8a29e;
--vien:#44403c;--the:#292524;--them:#14532d;--them-chu:#dcfce7;--bot:#7f1d1d;
--bot-chu:#fee2e2;--moc:#312e81}}
*{box-sizing:border-box}body{margin:0;background:var(--nen);color:var(--chu);
font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:960px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:4px 0 8px}p{margin:6px 0}.mo{color:var(--mo);font-size:14px}
.the{background:var(--the);border:1px solid var(--vien);border-radius:10px;
padding:12px 14px;margin:12px 0}
ul{padding-left:20px;margin:6px 0}li{overflow-wrap:anywhere}.so-them{color:#16a34a}.so-bot{color:#dc2626}
.chu-giai span{display:inline-block;padding:0 6px;border-radius:4px;margin-right:6px}
details{margin:12px 0;border:1px solid var(--vien);border-radius:10px;
background:var(--the);overflow:hidden}
summary{padding:10px 14px;cursor:pointer;font-weight:600;word-break:break-all}
pre{margin:0;overflow-x:auto;font:13px/1.45 ui-monospace,Menlo,Consolas,monospace}
.d{display:block;padding:0 12px;white-space:pre}
.d.them{background:var(--them);color:var(--them-chu)}
.d.bot{background:var(--bot);color:var(--bot-chu)}
.d.moc{background:var(--moc);color:var(--mo)}
"""

_TRANG_THAI = {"choXem": "chờ đại ca đồng ý", "daGop": "đã đưa vào hệ",
               "hong": "máy phụ làm không xong", "bo": "đã bỏ",
               "dangLam": "máy phụ đang làm", "moi": "chưa bắt đầu",
               "tamDung": "đang tạm dừng"}


def _cat_theo_tep(diff: str) -> list:
    """Chia diff thành từng tệp: [(tên, [dòng…])]."""
    tep, hien = [], None
    for dong in diff.splitlines():
        if dong.startswith("diff --git "):
            ten = dong.split(" b/", 1)[-1]
            hien = (ten, [])
            tep.append(hien)
        elif hien is not None:
            hien[1].append(dong)
    return tep


def _dong(d: str) -> str:
    # Dòng đầu mỗi tệp (index, ---, +++) là chi tiết kỹ thuật — bỏ, tên tệp đã
    # nằm trên tiêu đề khối.
    if d.startswith(("index ", "--- ", "+++ ", "new file mode", "deleted file mode",
                     "similarity index", "rename from", "rename to", "old mode",
                     "new mode")):
        return ""
    lop = ("them" if d.startswith("+") else "bot" if d.startswith("-")
           else "moc" if d.startswith("@@") else "")
    return f'<span class="d {lop}">{html.escape(d) or " "}</span>'


def dung_trang(o: dict) -> str:
    """Kết quả `xuongCompany.xemThayDoi` → một trang HTML hoàn chỉnh."""
    e = html.escape
    tep = o.get("tepDoi") or []
    them = sum(t.get("them", 0) for t in tep)
    bot = sum(t.get("bot", 0) for t in tep)
    ds = "".join(
        f'<li>{e(t["ten"])} — <span class="so-them">+{t["them"]}</span> '
        f'<span class="so-bot">−{t["bot"]}</span></li>' for t in tep)
    khoi = "".join(
        f'<details{" open" if len(tep) <= 3 else ""}><summary>{e(ten)}</summary>'
        f'<pre>{"".join(_dong(d) for d in dong)}</pre></details>'
        for ten, dong in _cat_theo_tep(o.get("diff") or ""))
    cat = ('<p class="the">⚠ Phần thay đổi quá dài nên trang này chỉ hiện một '
           'phần. Nhắn Claude Code nếu cần xem hết.</p>' if o.get("daCat") else "")
    mo_ta = (f'<p><b>Việc được giao:</b> {e(o["moTa"])}</p>'
             if o.get("moTa") else "")
    trang_thai = _TRANG_THAI.get(o.get("trangThai", ""), o.get("trangThai", ""))
    return f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Thay đổi · {e(o.get("viecId", ""))}</title><style>{_CSS}</style></head>
<body><main>
<p class="mo">Việc của máy phụ · mã {e(o.get("viecId", ""))} · {e(trang_thai)}</p>
<h1>{e(o.get("tieuDe", ""))}</h1>
<div class="the">{mo_ta}
<p><b>Đã thay đổi {len(tep)} tệp</b> — thêm {them} dòng, bỏ {bot} dòng:</p>
<ul>{ds}</ul>
<p class="mo chu-giai"><span class="d them">+ dòng thêm</span>
<span class="d bot">− dòng bỏ</span></p></div>
{cat}{khoi}
<p class="mo">Đây mới là bản nháp nếu trạng thái là "chờ đại ca đồng ý" — chưa
vào hệ đang chạy. Muốn dùng: nhắn Claude Code "duyệt việc {e(o.get("viecId", ""))}".</p>
</main></body></html>"""
