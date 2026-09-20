#!/usr/bin/env python3
"""cầu — cửa DUY NHẤT từ hộp (distro openclaw) vào hệ.

Hộp ngồi trong một distro riêng, không thấy `/home/tsix`, không thấy
`ops/.env`. Khi nó cần chạm tới ví tiền, Notion, lịch — hay chỉ cần lấy mã về
mà làm — nó gõ cửa ở đây.

ĐỌC KỸ BỐN ĐIỀU SAU TRƯỚC KHI NỚI BẤT CỨ THỨ GÌ:

1. CẦU NÀY HẸP HƠN `dispatch.py`, KHÔNG RỘNG HƠN.
   Nó không phải đường vòng quanh T2 — nó là cái phễu đặt TRƯỚC dispatch. Mọi
   lời gọi vẫn đi qua `dispatch.py`, vẫn sinh phiếu duyệt, vẫn vào nhật ký,
   vẫn bị trần hạn mức chặn. Cầu chỉ làm thêm một việc: CẮT BỚT. Cùng hình
   dạng với `brains/fallback.py`, vốn chỉ có đúng một công cụ và dựng argv bằng tay.

2. DANH SÁCH TRẮNG, KHÔNG PHẢI DANH SÁCH ĐEN.
   Company nào không khai ở `CHO_PHEP` thì hộp không gọi được, chấm hết. Thêm
   một company mới vào hệ KHÔNG tự động mở nó cho hộp. Danh sách đen thì mỗi
   company mới là một lỗ hổng mặc định mà không ai nhớ ra cho tới lúc muộn.

3. KHÔNG CÓ KHOÁ THÌ KHÔNG CHẠY.
   Thiếu `CAU_TOKEN` trong `ops/.env` thì tiến trình CHẾT ngay lúc khởi động,
   không im lặng mở cổng không mật khẩu (O10).

4. GIT ĐI CHUNG CỬA NÀY, không mở `git daemon` riêng.
   git daemon không biết xác thực; mở nó là mở CỬA THỨ HAI trong khi cả thiết
   kế dựng trên đúng một câu — cửa duy nhất. Cắm git vào đây thì nó dùng chung
   khoá, chung nhật ký, chung hàng rào.

Chạy:  python3 gateway/telegram/cau.py            (nghe 127.0.0.1:8787)
Thử:   python3 gateway/telegram/cau.py --tu-kiem  (không mở cổng, chỉ soát cấu hình)
"""
import argparse
import json
import os
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# §36 — ops/ đã tan ra. `session` và `telegram` nay là hàng xóm của file này;
# `db` vẫn ở lib/. Những import đó nằm TRONG hàm (nạp trễ) nên đường dẫn phải
# sẵn sàng từ đây.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))

CONG = int(os.environ.get("CAU_PORT", "8787"))
# 127.0.0.1 là đủ: mọi distro WSL2 chạy chung MỘT máy ảo nên chúng dùng chung
# localhost. Không mở ra ngoài máy — hộp ở ngay bên cạnh, không ở xa.
DIA_CHI = "127.0.0.1"

# Thân yêu cầu gọi company tối đa. Một taskEnvelope hợp lệ chưa bao giờ tới
# 64 KB; lớn hơn thế thì hoặc là lỗi, hoặc là ai đó đang thử trò khác.
THAN_TOI_DA = 64 * 1024

# Kho GƯƠNG — đường đi của MÃ giữa hệ và hộp.
#
# Hộp không có khoá SSH của admin và KHÔNG ĐƯỢC CÓ: khoá ấy mở MỌI kho của tài
# khoản, trong đó có `handoff_panharmon` mà chỉ admin được ghi vào main. Nên
# hộp không clone từ GitHub — nó clone từ cái gương này.
#
# Gương chỉ chứa nội dung git: `ops/.env` chưa bao giờ nằm trong git, sổ sqlite
# thì .gitignore chặn. Ranh giới GHI nằm ở hook `update` của kho gương
# (hop/update-hook.sh): chỉ nhận `refs/heads/y/<mã việc>`, từ chối main.
GUONG = os.path.expanduser("~/hop-guong")
GIT_BACKEND = "/usr/lib/git-core/git-http-backend"
# Thân yêu cầu git lớn hơn thân lời gọi company rất nhiều (một lần push mang
# theo cả object). Vẫn phải có trần: không trần thì một yêu cầu hỏng đủ sức ăn
# hết RAM của máy ảo.
GIT_THAN_TOI_DA = 64 * 1024 * 1024

# ───────────────────────── danh sách trắng ─────────────────────────
#
# Khai đúng tên trong `companySpec.yaml` — `codemap --check` soát tên company
# và tên năng lực viết cứng trong `ops/*.py`, nên gõ sai ở đây bị bắt ngay chứ
# không đợi tới lúc hộp gọi trượt.
#
# VÌ SAO NGẮN THẾ NÀY: hộp mới sinh ra hôm nay. Mở đúng thứ nó cần cho việc
# đầu tiên — nhận việc, ghi bước, tra API — rồi mở thêm khi có nhu cầu THẬT.
# Mở rộng thì lúc nào cũng làm được; thu hẹp lại sau khi đã quen tay thì không.
CHO_PHEP = {
    "xuongCompany": {"themViec", "dsViec", "nhanViec", "ghiBuoc", "tamDung",
                     "xongViec", "donDep", "nhatKy"},
    "apiCompany": {"timApi", "xemApi", "kiemApi", "capNhatDanhMuc"},
}


def nap_env() -> dict:
    """Đọc ops/.env. KHÔNG đưa cả môi trường cho tiến trình con."""
    duong = os.path.join(ROOT, "ops", ".env")
    ra = {}
    if not os.path.exists(duong):
        return ra
    with open(duong, encoding="utf-8") as f:
        for dong in f:
            dong = dong.strip()
            if not dong or dong.startswith("#") or "=" not in dong:
                continue
            k, v = dong.split("=", 1)
            ra[k.strip()] = v.strip().strip('"').strip("'")
    return ra


def lay_khoa() -> str:
    khoa = nap_env().get("CAU_TOKEN", "").strip()
    if len(khoa) < 24:
        raise SystemExit(
            "ops/.env thiếu CAU_TOKEN (hoặc ngắn hơn 24 ký tự). Cầu KHÔNG mở "
            "cổng không khoá. Sinh một cái:\n"
            "  python3 -c \"import secrets; print('CAU_TOKEN=' + "
            "secrets.token_urlsafe(32))\" >> ops/.env")
    return khoa


def ghi(*phan) -> None:
    """Nhật ký ra stderr — systemd gom hộ, không đẻ thêm một cái sổ nữa."""
    print(f"[cau {time.strftime('%H:%M:%S')}]", *phan, file=sys.stderr,
          flush=True)


def goi_dispatch(company: str, capability: str, inp: dict, tra: int) -> dict:
    """Dựng argv BẰNG TAY, không qua shell. Cùng lẽ với brains/fallback.py."""
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "gateway", "cli", "dispatch.py"), "call",
         "--company", company, "--capability", capability,
         "--input", json.dumps(inp, ensure_ascii=False),
         "--issued-by", "ceo"],
        capture_output=True, text=True, cwd=ROOT, timeout=tra)
    if not proc.stdout.strip():
        # O10 — dispatcher câm thì nói là câm, đừng trả {} cho giống thành công.
        raise RuntimeError(
            f"dispatch.py không trả gì (mã thoát {proc.returncode}). "
            f"stderr: {proc.stderr[-800:]}")
    return json.loads(proc.stdout)


# Lần cuối gửi thẻ duyệt cho mỗi (company, năng lực) — chống nhắc lặp. Xem
# khối "HAI LỚP CHẶN LẶP" trong moi_duyet().
_da_nhac: dict = {}
# Một tiếng. Đủ để admin đang ngủ không bị dựng dậy 12 lần; đủ ngắn để nếu
# admin bỏ lỡ thẻ đầu thì chiều về vẫn thấy một cái nhắc lại.
NHAC_CACH_GIAY = 3600


def moi_duyet(kq: dict, company: str, capability: str) -> None:
    """Việc GHI của hộp cần admin bấm duyệt — nên phải CÓ AI ĐÓ gửi phiếu.

    ĐÂY LÀ CHỖ SUÝT HỎNG CÂM. Khi CEO gọi dispatch, gateway gom phiếu chờ rồi
    gắn nút vào câu trả lời trong Telegram. Hộp thì không đi qua gateway — nên
    nếu cầu không gửi phiếu, dispatch vẫn sinh `needsApproval` tử tế, hộp vẫn
    nhận kết quả tử tế, và admin KHÔNG BAO GIỜ thấy cái nút. Việc treo vĩnh
    viễn mà mọi bộ phận đều báo "chạy ok" — đúng hình dạng con bug tốn công
    nhất dự án này.

    Đi qua `gateway/telegram/telegram.py`, đường ra duy nhất (T1). Gắn nhãn "HỘP" ở đầu vì
    admin cần biết phiếu này sinh ra từ máy đang tự làm việc, không phải từ câu
    vừa nhắn — hai thứ đó đáng được cân nhắc khác nhau.
    """
    xin = kq.get("approvalRequest") or {}
    ma = xin.get("approvalId")
    if not ma:
        return

    # HAI LỚP CHẶN LẶP, VÌ MỘT LỚP KHÔNG ĐỦ.
    #
    # Lớp 1 (trạng thái): đã có phiếu cùng loại đang chờ thì im.
    # Lớp 2 (thời gian): phiếu cũ HẾT HẠN rồi thì lớp 1 hở ra, và thợ chạy mỗi
    #   5 phút sẽ sinh thẻ mới sau mỗi lần hết hạn — cả đêm. Đo được 18/09
    #   đúng cảnh đó: lớp 1 không bắt vì phiếu 21:55 đã không còn `pending`
    #   lúc 21:56. Nên chặn thêm theo đồng hồ.
    #
    # Nhớ trong RAM, không ghi sổ: cầu chạy liên tục, và nếu nó khởi động lại
    # thì một thẻ thừa là cái giá rẻ hơn hẳn một cái sổ nữa phải dọn.
    gio = time.time()
    khoa_nhac = f"{company}.{capability}"
    truoc = _da_nhac.get(khoa_nhac, 0)
    if gio - truoc < NHAC_CACH_GIAY:
        ghi(f"IM — vừa gửi thẻ {khoa_nhac} {int((gio - truoc) / 60)} phút trước, "
            f"chờ đủ {NHAC_CACH_GIAY // 60} phút mới nhắc lại ({ma})")
        return

    # ĐÃ CÓ PHIẾU CÙNG LOẠI ĐANG CHỜ THÌ IM.
    #
    # Thợ trong hộp chạy theo timer 5 phút. Phiếu chưa bấm thì lần chạy sau lại
    # sinh phiếu nữa — 12 thẻ một giờ, 100 thẻ một đêm, tất cả cùng một nội
    # dung. Đó đúng là dòng "lỗi hạ tầng lặp lại nhắn mỗi lần" trong CLAUDE.md:
    # cron 15 phút × sự cố 6 tiếng = 21 tin giống hệt lúc nửa đêm, và cái giá
    # thật không phải là phiền — là admin học được cách bỏ qua thông báo.
    #
    # Nên: lần đầu nhắn, lặp thì im. Phiếu cũ vẫn nằm đó chờ bấm; bấm một cái
    # là cả loạt sau chạy tiếp.
    try:
        sys.path.insert(0, os.path.join(ROOT, "lib"))
        import db
        conn = db.connect(os.path.join(ROOT, "backOffice", "store.sqlite"))
        cu = conn.execute(
            "SELECT COUNT(*) FROM approvalRequest WHERE companyId=? AND "
            "capability=? AND status='pending' AND approvalId<>?",
            (company, capability, ma)).fetchone()[0]
        conn.close()
        if cu:
            ghi(f"IM — đã có {cu} phiếu {company}.{capability} đang chờ bấm, "
                f"không gửi thêm ({ma})")
            return
    except Exception as exc:
        # Soát không được thì cứ gửi: thà một thẻ thừa còn hơn một việc treo
        # câm. Nhưng phải nói ra là đã không soát được.
        ghi(f"không soát được phiếu trùng ({type(exc).__name__}: {exc}) — vẫn gửi")

    chat = os.environ.get("COMPANYSPEC_ADMIN_CHAT_ID", "").strip()
    if not chat:
        ghi("KHÔNG gửi được phiếu duyệt: thiếu COMPANYSPEC_ADMIN_CHAT_ID")
        return
    try:
        import session
        import telegram
        nut = session.approval_keyboard(
            ma, session.can_whitelist(company, capability,
                                      xin.get("riskTier", "write")))
        telegram.send_message(
            chat,
            telegram.esc(f"HỘP xin duyệt · {company}.{capability}\n"
                         + (xin.get("consequence") or "")[:600]),
            session.markup_json(nut))
        _da_nhac[khoa_nhac] = gio
        ghi(f"đã gửi phiếu duyệt {ma} cho admin")
    except Exception as exc:
        # O10 — gửi phiếu hỏng thì NÓI RA. Nuốt ở đây là quay lại đúng cảnh
        # treo câm mà hàm này sinh ra để tránh.
        ghi(f"GỬI PHIẾU HỎNG ({ma}): {type(exc).__name__}: {exc}")


def bao_xong(kq: dict, company: str, capability: str) -> None:
    """Hộp đóng xong một việc → NHẮN CHO ADMIN. Không có bước này thì cả cái
    dây chuyền chạy đúng mà vô nghĩa.

    ĐO ĐƯỢC 18/09, và đây là bài học đắt nhất của cả ngày hôm ấy: hộp dựng
    xong một web todolist hoàn chỉnh — index.html, style.css, app.js, README
    có hướng dẫn chạy, đã commit — rồi đặt việc về `choXem` và im lặng. Cùng
    tối đó admin hỏi CEO "cái web làm sao xem", và CEO đáp "em không viết file
    HTML được". Sản phẩm nằm cách đó một thư mục.

    Không ai hỏng cả: hộp làm đúng, sổ ghi đúng, `choXem` đúng nghĩa "chờ xem".
    Chỉ là KHÔNG AI CHỦ ĐỘNG NÓI RA. Việc xong mà người cần biết không biết thì
    tính là chưa xong.
    """
    if company != "xuongCompany" or capability != "xongViec":
        return
    if kq.get("status") != "ok":
        return
    o = kq.get("output") or {}
    if o.get("trangThai") not in ("choXem", "hong"):
        return          # daGop/bo là admin tự quyết, không cần báo lại
    chat = os.environ.get("COMPANYSPEC_ADMIN_CHAT_ID", "").strip()
    if not chat:
        ghi("việc xong nhưng KHÔNG báo được: thiếu COMPANYSPEC_ADMIN_CHAT_ID")
        return
    try:
        import telegram
        dau = ("Hộp làm xong một việc, chờ đại ca xem"
               if o["trangThai"] == "choXem" else "Hộp làm KHÔNG xong một việc")
        telegram.send_message(
            chat, telegram.esc(f"{dau}\n\n{(kq.get('summary') or '')[:900]}"))
        ghi(f"đã báo admin: việc {o.get('viecId')} → {o['trangThai']}")
    except Exception as exc:
        ghi(f"BÁO XONG HỎNG: {type(exc).__name__}: {exc}")


class Cua(BaseHTTPRequestHandler):
    server_version = "cau/0.1"
    khoa = ""

    def log_message(self, *_a):      # tắt log mặc định, đã có ghi() riêng
        pass

    def _tra(self, ma: int, than: dict) -> None:
        cuc = json.dumps(than, ensure_ascii=False).encode("utf-8")
        self.send_response(ma)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuc)))
        self.end_headers()
        self.wfile.write(cuc)

    def _co_khoa(self) -> bool:
        return self.headers.get("Authorization", "") == f"Bearer {self.khoa}"

    def _git(self, phuong: str) -> None:
        """Phục vụ kho gương bằng `git http-backend` (CGI).

        Không có gì thông minh ở đây: dựng đúng bộ biến môi trường CGI mà git
        đòi, đưa thân yêu cầu vào stdin, rồi chuyển nguyên phần đầu và thân nó
        trả ra. Ranh giới ai được ghi nhánh nào KHÔNG nằm ở đây — nó nằm trong
        hook `update` của kho gương, tức là còn nguyên kể cả khi có ngày ai đó
        gọi git-http-backend bằng một đường khác.
        """
        if not self._co_khoa():
            ghi("TỪ CHỐI git — sai khoá")
            return self._tra(401, {"loi": "sai khoá"})
        if not os.path.isdir(GUONG):
            return self._tra(503, {"loi": f"chưa có kho gương ở {GUONG}"})

        duong, _, truy_van = self.path[len("/git"):].partition("?")
        dai = int(self.headers.get("Content-Length") or 0)
        if dai > GIT_THAN_TOI_DA:
            return self._tra(413, {"loi": "thân git quá lớn"})
        than = self.rfile.read(dai) if dai > 0 else b""

        moi_truong = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "GIT_PROJECT_ROOT": GUONG,
            "GIT_HTTP_EXPORT_ALL": "1",
            "PATH_INFO": duong,
            "REQUEST_METHOD": phuong,
            "QUERY_STRING": truy_van,
            "CONTENT_TYPE": self.headers.get("Content-Type", ""),
            "CONTENT_LENGTH": str(dai),
            # git ghi tên này vào reflog — sau này nhìn reflog còn biết ai đẩy
            # cái gì.
            "REMOTE_USER": "hop",
            "REMOTE_ADDR": self.client_address[0],
            "GIT_HTTP_MAX_REQUEST_BUFFER": str(GIT_THAN_TOI_DA),
        }
        try:
            proc = subprocess.run([GIT_BACKEND], input=than, env=moi_truong,
                                  capture_output=True, timeout=300)
        except FileNotFoundError:
            return self._tra(500, {"loi": f"không có {GIT_BACKEND} trên máy"})
        except subprocess.TimeoutExpired:
            ghi(f"QUÁ GIỜ git {duong}")
            return self._tra(504, {"loi": "git quá 300 giây"})

        dau, _, than_ra = proc.stdout.partition(b"\r\n\r\n")
        ma, tieu_de = 200, []
        for dong in dau.decode("utf-8", "replace").split("\r\n"):
            if not dong:
                continue
            ten, _, gia = dong.partition(":")
            if ten.strip().lower() == "status":
                ma = int(gia.strip().split()[0])
            else:
                tieu_de.append((ten.strip(), gia.strip()))
        if proc.stderr.strip():
            # Hook `update` từ chối thì lời giải thích đi ra ĐƯỜNG NÀY. Nuốt nó
            # là biến một câu nói rõ vì sao thành một lần push hỏng câm.
            ghi(f"git stderr: {proc.stderr.decode('utf-8', 'replace')[-500:]}")
        self.send_response(ma)
        for ten, gia in tieu_de:
            self.send_header(ten, gia)
        self.send_header("Content-Length", str(len(than_ra)))
        self.end_headers()
        self.wfile.write(than_ra)

    def do_GET(self):
        if self.path.startswith("/git/"):
            return self._git("GET")
        if self.path == "/song":
            return self._tra(200, {"song": True,
                                   "choPhep": sorted(CHO_PHEP),
                                   "guong": os.path.isdir(GUONG)})
        self._tra(404, {"loi": "chỉ có POST /goi, GET /song, và /git/…"})

    def do_POST(self):
        if self.path.startswith("/git/"):
            return self._git("POST")
        if self.path != "/goi":
            return self._tra(404, {"loi": "chỉ có POST /goi"})

        if not self._co_khoa():
            ghi("TỪ CHỐI — sai khoá")
            return self._tra(401, {"loi": "sai khoá"})

        dai = int(self.headers.get("Content-Length") or 0)
        if dai <= 0 or dai > THAN_TOI_DA:
            return self._tra(413, {"loi": f"thân phải từ 1 tới {THAN_TOI_DA} byte"})
        try:
            yc = json.loads(self.rfile.read(dai).decode("utf-8"))
        except Exception as exc:
            return self._tra(400, {"loi": f"JSON hỏng: {exc}"})

        company = yc.get("company") or ""
        capability = yc.get("capability") or ""
        inp = yc.get("input")
        if not isinstance(inp, dict):
            return self._tra(400, {"loi": "'input' phải là object"})

        nang = CHO_PHEP.get(company)
        if nang is None or capability not in nang:
            # Nói RÕ cái gì mở, để người viết hộp không phải đoán mò.
            ghi(f"TỪ CHỐI — {company}.{capability} không nằm trong danh sách trắng")
            return self._tra(403, {
                "loi": f"{company}.{capability} không mở cho hộp",
                "choPhep": {k: sorted(v) for k, v in CHO_PHEP.items()},
                "cachMo": "khai thêm vào CHO_PHEP trong gateway/telegram/cau.py, có chủ ý"})

        tra = min(int(yc.get("traGiay") or 60), 300)
        ghi(f"gọi {company}.{capability}")
        try:
            kq = goi_dispatch(company, capability, inp, tra)
        except subprocess.TimeoutExpired:
            # O8 — cửa vào không được phép sập. Quá giờ thì trả một kết quả BÁO
            # ĐƯỢC, đừng để hộp nhận về một cục traceback.
            ghi(f"QUÁ GIỜ {company}.{capability} sau {tra}s")
            return self._tra(200, {
                "status": "failed",
                "error": f"dispatch quá {tra} giây",
                "summary": f"{company}.{capability} chạy quá {tra} giây nên bị "
                           "cắt. Việc có thể ĐÃ chạy một phần — kiểm tra trước "
                           "khi gọi lại, đừng gọi lại mù."})
        except Exception as exc:
            ghi(f"HỎNG {company}.{capability}: {exc}")
            return self._tra(200, {"status": "failed",
                                   "error": f"{type(exc).__name__}: {exc}",
                                   "summary": f"cầu hỏng khi gọi {company}."
                                              f"{capability}: {exc}"})
        ghi(f"→ {kq.get('status')} {company}.{capability}")
        if kq.get("status") == "needsApproval":
            moi_duyet(kq, company, capability)
        else:
            bao_xong(kq, company, capability)
        self._tra(200, kq)


def tu_kiem() -> int:
    """Soát cấu hình mà KHÔNG mở cổng. Rẻ, chạy được mọi lúc."""
    import yaml
    loi = []
    try:
        lay_khoa()
        print("khoá: có, đủ dài")
    except SystemExit as exc:
        loi.append(str(exc).splitlines()[0])
        print("khoá: THIẾU")
    print(f"gương: {GUONG} — {'có' if os.path.isdir(GUONG) else 'CHƯA CÓ'}")
    if not os.path.isdir(GUONG):
        loi.append(f"chưa có kho gương ở {GUONG}")
    for cid, caps in CHO_PHEP.items():
        duong = os.path.join(ROOT, "companies", cid, "companySpec.yaml")
        if not os.path.exists(duong):
            loi.append(f"{cid}: không có companySpec.yaml")
            continue
        spec = yaml.safe_load(open(duong, encoding="utf-8"))
        that = {c["name"] for c in spec["capabilities"]}
        thua = caps - that
        if thua:
            loi.append(f"{cid}: khai năng lực không tồn tại — {sorted(thua)}")
        print(f"{cid}: {len(caps)} năng lực mở / {len(that)} năng lực có")
    if loi:
        print("\nHỎNG:")
        for x in loi:
            print("  ·", x)
        return 1
    print("\nCấu hình cầu: sạch.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="cầu — cửa duy nhất từ hộp vào hệ")
    ap.add_argument("--tu-kiem", action="store_true",
                    help="soát cấu hình rồi thoát, không mở cổng")
    ap.add_argument("--cong", type=int, default=CONG)
    args = ap.parse_args()
    if args.tu_kiem:
        return tu_kiem()

    Cua.khoa = lay_khoa()
    may = ThreadingHTTPServer((DIA_CHI, args.cong), Cua)
    ghi(f"nghe {DIA_CHI}:{args.cong} · mở {sum(len(v) for v in CHO_PHEP.values())}"
        f" năng lực của {len(CHO_PHEP)} company · gương "
        f"{'có' if os.path.isdir(GUONG) else 'CHƯA CÓ'}")
    try:
        may.serve_forever()
    except KeyboardInterrupt:
        ghi("dừng")
    return 0


if __name__ == "__main__":
    sys.exit(main())
