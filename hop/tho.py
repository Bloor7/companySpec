#!/usr/bin/env python3
"""thợ — vòng làm việc của HỘP. Chạy TRONG distro openclaw, không chạy ở hệ.

Một vòng: nhận việc → làm trên bản sao → tự kiểm → đẩy nhánh → đóng việc.
Mọi lời gọi vào hệ đều qua cây cầu có khoá (`gateway/telegram/cau.py`); thợ không có
`ops/.env`, không có khoá SSH, và không đẩy được vào main — hook của kho gương
chặn bằng mã.

BỐN ĐIỀU ĐƯỢC VIẾT VÌ MỘT BÀI HỌC ĐÃ TRẢ GIÁ:

1. `is_successful()` CHỨ KHÔNG PHẢI `is_done()`. Não tự nói "xong" với nội
   dung là một câu kế hoạch thì đó là CHƯA XONG. Ở đây, "xong" chỉ được công
   nhận khi có THỨ ĐO ĐƯỢC: `git diff` khác rỗng VÀ `codemap --check` thoát 0.
   Không đủ hai thứ đó thì việc về `hong`, không về `choXem`.

2. GHI BƯỚC TRƯỚC KHI LÀM, không phải sau. Mất điện giữa chừng thì cái đã ghi
   là thứ duy nhất còn lại. Ghi sau thì đúng cảnh hỏng nhất lại là cảnh không
   có gì được ghi.

3. HẾT HẠN MỨC THÌ DỪNG HẲN, có hẹn giờ. Gói Pro là túi chung với CEO: thợ cày
   tiếp lúc trần đã chạm là lấy mất phần của admin lúc 11 giờ đêm. Nhận diện
   bằng `lib/quotaSignal.py` của chính repo — mẫu thật, không phải mẫu tự nghĩ.

4. CẮT LOG TỪ ĐUÔI. Traceback để loại lỗi ở DÒNG CUỐI; cắt từ đầu thì đúng
   dòng nói hỏng vì cái gì sẽ mất.

Chạy:
  python3 tho.py --mot-vong           # làm đúng một việc rồi thoát
  python3 tho.py --mot-vong --khong-goi-nao   # chạy khô: không gọi model nào
  python3 tho.py --xem                # xem xưởng đang có gì, không làm gì
"""
import argparse
import json
import os
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

NHA = os.path.expanduser("~")
BAN_SAO = os.path.join(NHA, "work", "companySpec")
# Dự án RIÊNG — mỗi việc một thư mục, git riêng, KHÔNG dính gì tới companySpec.
#
# VÌ SAO TÁCH HẲN: lời nhắc của loại `repo` nói "cậu đang ở bản sao repo
# companySpec, đọc CLAUDE.md trước" — đưa một việc kiểu "làm cho anh một web
# todolist" vào đó thì mã đẻ ra nằm lẫn trong repo của hệ, và `codemap --check`
# (thứ dùng để chấm "xong") thì chẳng nói được gì về một web app cả.
#
# Thư mục này nhìn từ Windows: \\wsl.localhost\openclaw\home\hop\work\duan\...
# — admin mở Explorer là thấy, không cần đẩy đi đâu.
DU_AN = os.path.join(NHA, "work", "duan")
CAU = "http://127.0.0.1:8787/goi"
KHOA_TEP = os.path.join(NHA, ".cau_token")

# Ngân sách một lượt não. Dài hơn timeout của cầu là vô nghĩa, nên giữ dưới đó
# — và cầu lại phải lớn hơn hẳn ngân sách company, đúng chiều đã ghi trong
# CLAUDE.md ("ở tầng GỌI thì timeout phải LỚN HƠN HẲN ngân sách tầng dưới").
NAO_GIAY = 900


def gio() -> str:
    return datetime.now().strftime("%H:%M:%S")


def noi(*phan) -> None:
    print(f"[thợ {gio()}]", *phan, flush=True)


# ───────────────────────── nói chuyện với hệ qua cầu ─────────────────────────

def goi(company: str, capability: str, inp: dict, tra: int = 90) -> dict:
    khoa = open(KHOA_TEP).read().strip()
    yc = urllib.request.Request(
        CAU,
        data=json.dumps({"company": company, "capability": capability,
                         "input": inp, "traGiay": tra}).encode(),
        headers={"Authorization": f"Bearer {khoa}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(yc, timeout=tra + 15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        than = exc.read().decode("utf-8", "replace")
        # O10 — cầu từ chối thì nói rõ nó từ chối cái gì, đừng biến thành một
        # dict rỗng trông như "không có việc".
        raise RuntimeError(f"cầu trả HTTP {exc.code}: {than[:300]}")
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"không gọi được cầu ({exc}). Hệ có đang chạy không? "
            "Bên kia kiểm bằng: systemctl --user is-active companyspec-cau")


def ghi_buoc(viec_id: str, ten: str, trang_thai: str, ket_qua: str = "",
             ma_thoat=None, ke_tiep: str = "") -> None:
    inp = {"viecId": viec_id, "ten": ten[:200], "trangThai": trang_thai}
    if ket_qua:
        inp["ketQua"] = ket_qua[:2000]
    if ma_thoat is not None:
        inp["maThoat"] = int(ma_thoat)
    if ke_tiep:
        inp["buocKeTiep"] = ke_tiep[:500]
    kq = goi("xuongCompany", "ghiBuoc", inp)
    if kq.get("status") != "ok":
        # Không ghi được bước thì trí nhớ thủng đúng chỗ cần nhất. Kêu to.
        noi(f"⚠ KHÔNG ghi được bước ({kq.get('status')}): "
            f"{str(kq.get('summary'))[:200]}")


# ───────────────────────── chạy lệnh trong bản sao ─────────────────────────

def chay(lenh: list, tra: int = 300, cwd: str = BAN_SAO) -> tuple:
    """Chạy một lệnh, trả (mã thoát, đầu ra cắt TỪ ĐUÔI)."""
    try:
        p = subprocess.run(lenh, cwd=cwd, capture_output=True, text=True,
                           timeout=tra)
    except subprocess.TimeoutExpired:
        return 124, f"quá {tra} giây: {' '.join(lenh[:4])}"
    except FileNotFoundError as exc:
        return 127, f"không có lệnh: {exc}"
    ra = (p.stdout + p.stderr).strip()
    return p.returncode, ra[-2000:]


def thu_muc_du_an(viec_id: str, tieu_de: str) -> str:
    """Thư mục của một dự án riêng: ~/work/duan/<mã việc>-<tên rút gọn>.

    BỎ DẤU TIẾNG VIỆT trong tên thư mục. Linux và UNC của Windows đều mở được
    đường dẫn có dấu, nhưng nó sẽ đi qua rất nhiều chỗ khác trong đời một dự
    án — dòng lệnh, npm, git remote, một cái script ai đó viết vội — và mỗi
    chỗ là một cơ hội hỏng vì lý do không liên quan gì tới việc đang làm.
    Mã việc đứng đầu nên vẫn tra ngược ra được, tên chỉ để người đọc dễ nhận.
    """
    khong_dau = unicodedata.normalize("NFKD", tieu_de.lower())
    khong_dau = "".join(c for c in khong_dau if not unicodedata.combining(c))
    khong_dau = khong_dau.replace("đ", "d")
    goc = "".join(c if c.isascii() and c.isalnum() else "-" for c in khong_dau)
    goc = "-".join(x for x in goc.split("-") if x)[:40].strip("-")
    d = os.path.join(DU_AN, f"{viec_id}-{goc}" if goc else viec_id)
    os.makedirs(d, exist_ok=True)
    if not os.path.isdir(os.path.join(d, ".git")):
        chay(["git", "init", "-q"], cwd=d)
        chay(["git", "config", "user.name", "hop"], cwd=d)
        chay(["git", "config", "user.email", "hop@openclaw.local"], cwd=d)
    return d


def chuan_bi_nhanh(viec_id: str) -> tuple:
    nhanh = f"y/{viec_id}"
    ma, ra = chay(["git", "fetch", "origin", "main"])
    if ma != 0:
        return None, f"git fetch hỏng: {ra}"
    # Nhánh cũ còn trên gương thì làm tiếp trên nó, đừng vứt công cũ đi.
    ma_co, _ = chay(["git", "ls-remote", "--exit-code", "--heads", "origin",
                     nhanh])
    if ma_co == 0:
        chay(["git", "fetch", "origin", f"{nhanh}:{nhanh}"])
        ma, ra = chay(["git", "checkout", nhanh])
    else:
        ma, ra = chay(["git", "checkout", "-B", nhanh, "origin/main"])
    if ma != 0:
        return None, f"git checkout hỏng: {ra}"
    return nhanh, ""


# ───────────────────────── bộ não ─────────────────────────

def het_han_muc(chu: str) -> bool:
    """Dùng CHÍNH bộ nhận diện của repo, không tự nghĩ mẫu.

    CLAUDE.md: "Mẫu nhận diện viết từ phỏng đoán, không từ mẫu thật" — mẫu tự
    nghĩ đã từng không khớp câu Anthropic thật sự gửi, suốt nhiều tháng, và chỉ
    lọt lưới nhờ mã 429 đi kèm.
    """
    try:
        sys.path.insert(0, os.path.join(BAN_SAO, "lib"))
        import quotaSignal
        for ten in ("la_quota", "nhan_dien", "detect", "match"):
            ham = getattr(quotaSignal, ten, None)
            if callable(ham):
                return bool(ham(chu))
    except Exception:
        pass
    thap = chu.lower()
    return ("session limit" in thap or "usage limit" in thap
            or "429" in thap)


def chua_dang_nhap(chu: str) -> bool:
    """Claude trong hộp chưa `/login` — KHÁC hẳn hết hạn mức, và phải khác.

    Hết hạn mức thì vài tiếng nữa tự hết; chưa đăng nhập thì có đợi tới sang
    năm cũng vẫn thế, phải có người đi bấm. Gộp hai thứ vào một nhánh là để
    thợ quay vòng vô ích mỗi năm phút suốt đêm mà không ai biết vì sao.

    Đo 18/09: `claude` cài xong trong hộp nhưng chưa có phiên nào.
    """
    thap = chu.lower()
    return any(m in thap for m in (
        "invalid api key", "please run /login", "run `claude /login`",
        "failed to authenticate", "not logged in", "no credentials",
        "authentication_error"))


def goi_nao(viec: dict, cho_lam: str, kho: bool) -> tuple:
    """Gọi Claude Code. Trả (ok, chữ, lý do dừng hoặc "").

    `cho_lam` là nhánh git (việc `repo`) hay đường dẫn thư mục (việc `duAn`) —
    và lời nhắc đổi theo, vì hai loại việc có bối cảnh không giống nhau chút
    nào. Gửi nhầm lời nhắc là cách chắc chắn nhất để nhận về mã lạc chỗ.
    """
    chung = (f"Việc: {viec['tieuDe']}\n\n{viec.get('moTa') or ''}\n\n"
             f"Lần trước dừng vì: {viec.get('lanTruocDung') or 'chưa từng dừng'}\n"
             f"BƯỚC KẾ TIẾP đã ghi: {viec.get('buocKeTiep') or '(chưa có)'}\n")

    if viec.get("loai") == "duAn":
        thu_muc = cho_lam
        loi_nhac = (
            chung
            + f"\nBối cảnh: đây là một DỰ ÁN RIÊNG. Thư mục làm việc là "
            f"{thu_muc}, git riêng, trống hoặc đang dở. KHÔNG liên quan gì tới "
            "repo companySpec — đừng đi tìm CLAUDE.md hay ops/ ở đây, chúng "
            "không tồn tại và cũng không nên tồn tại.\n"
            "Làm cho chạy được thật: có tệp chạy được, có README ngắn nói cách "
            "chạy. Thứ gì cần cài thì ghi vào README, đừng cài linh tinh ra "
            "ngoài thư mục này.\n"
            "ĐỪNG commit — thợ lo phần đó.")
        cwd = thu_muc
    else:
        loi_nhac = (
            chung
            + f"\nBối cảnh: cậu đang ở bản sao repo companySpec, nhánh "
            f"{cho_lam}. Đọc CLAUDE.md trước khi sửa bất cứ thứ gì — nhất là "
            "bảng 'Đã sửa rồi — đừng làm lại'.\n"
            "Xong thì phải chạy được `python3 ops/codemap.py --check` sạch. "
            "ĐỪNG commit, đừng push — thợ lo phần đó.")
        cwd = BAN_SAO

    if kho:
        noi(f"chạy khô — KHÔNG gọi model nào (sẽ làm ở {cwd})")
        return True, "[chạy khô] không gọi não", ""

    ma, ra = chay(["claude", "-p", loi_nhac, "--output-format", "json",
                   "--permission-mode", "acceptEdits"], tra=NAO_GIAY, cwd=cwd)
    if het_han_muc(ra):
        return False, ra, "hetHanMuc"
    if chua_dang_nhap(ra):
        return False, ra, "chuaDangNhap"
    # Mã thoát 0 KHÔNG có nghĩa là chạy được — soi cả `is_error` trong JSON.
    # Phiên OAuth hết hạn từng trả is_error kèm mã thoát 0, và nhánh mã-0 đi
    # thẳng qua mọi cửa dự phòng.
    try:
        d = json.loads(ra[ra.index("{"):])
        if d.get("is_error"):
            return False, str(d.get("result") or ra)[-2000:], ""
    except Exception:
        pass
    return ma == 0, ra, ""


# ───────────────────────── một vòng ─────────────────────────

#: Trạng thái mà `nhanViec` THẬT SỰ nhận được: việc tạm dừng tới giờ thử lại,
#: việc đứt gánh, và việc mới. `choXem`/`daGop`/`bo`/`hong` thì không.
#:
#: Danh sách này phải khớp với thứ tự nhận khai trong `nhanViec.description`.
#: Lệch thì hỏng về phía CHẶT (bỏ qua một việc đáng làm), nên ca `--xem` in ra
#: số đếm để soi được bằng mắt.
TRANG_THAI_NHAN_DUOC = ("moi", "dangLam", "tamDung")


def co_viec_de_nhan() -> tuple:
    """Hỏi "có việc không?" bằng một lời gọi ĐỌC. Trả (biết_chắc, có_việc).

    ═══════════════════════════════════════════════════════════════════
    VÌ SAO KHÔNG HỎI THẲNG `nhanViec`
    ═══════════════════════════════════════════════════════════════════

    `nhanViec` là `write`, và bản cũ gọi nó NGAY dòng đầu mỗi vòng — tức là
    hỏi một câu ĐỌC bằng một lời gọi GHI. Thợ chạy 6 phút/lần ≈ 240 vòng mỗi
    ngày, trong khi quyền đứng admin cấp có trần 20 lần/ngày. Hết trần sau
    khoảng hai tiếng, và 220 vòng còn lại MỖI VÒNG đẻ một thẻ duyệt.

    Đo 20/09, lưu lượng THẬT (đã bỏ nhãn bộ đo): `nhanViec` gọi 330 lần, chỉ
    36 lần chạy được, **294 lần hỏi duyệt** — trong khi xưởng có đúng 3 việc
    và cả 3 đều ở `choXem`, tức là KHÔNG CÓ GÌ để nhận. Admin bấm "luôn cho
    phép" năm lần, sổ whitelist có năm dòng trùng nhau, và nó vẫn hỏi tiếp.

    Chú thích trong manifest còn ghi "một lần cho aiLam=hop là thợ nhận việc
    suốt 90 ngày không hỏi nữa" — ý định ghi rõ, hiệu lực thì ngược lại. Đúng
    họ với bẫy "chú thích nói một đằng, giá trị làm một nẻo".

    `dsViec` là `read` nên đi thẳng, không bao giờ hỏi ai, không tốn gì. Xưởng
    trống thì thợ IM LẶNG — đó mới là hành vi admin mong đợi.

    ═══ TRẢ VỀ HAI GIÁ TRỊ, CÓ CHỦ Ý ═══

    `biết_chắc=False` nghĩa là KHÔNG ĐỌC ĐƯỢC sổ, không phải "xưởng trống".
    Gộp hai câu đó lại là để một lỗi đọc sổ làm thợ ngủ mãi mãi trong im lặng
    (O10 — số 0 không được trông giống một kết quả tốt).
    """
    kq = goi("xuongCompany", "dsViec", {})
    if kq.get("status") != "ok":
        return False, False
    cac_viec = (kq.get("output") or {}).get("cacViec") or []
    return True, any(v.get("trangThai") in TRANG_THAI_NHAN_DUOC
                     for v in cac_viec)


def mot_vong(kho: bool) -> int:
    # CỬA ĐỌC ĐỨNG TRƯỚC CỬA GHI. Xem `co_viec_de_nhan` để biết vì sao.
    biet_chac, co_viec = co_viec_de_nhan()
    if biet_chac and not co_viec:
        noi("xưởng trống — không nhận việc, không phiền đại ca.")
        return 0
    if not biet_chac:
        # Không đọc được sổ thì VẪN thử nhận: thà tốn một lời gọi ghi còn hơn
        # ngủ quên vì một lỗi đọc. Nhưng phải NÓI RA là đã không đọc được.
        noi("không đọc được danh sách việc — vẫn thử nhận một lần.")

    kq = goi("xuongCompany", "nhanViec", {"aiLam": "hop"})
    if kq.get("status") == "needsApproval":
        # THOÁT 0, không phải mã lỗi. Đang chờ người bấm không phải là hỏng —
        # trả mã khác 0 thì systemd ghi "Failed" mỗi 5 phút và cái log ấy dạy
        # người đọc bỏ qua chính nó. Cầu đã lo phần không gửi thẻ trùng.
        noi("việc nhận cần đại ca bấm duyệt — thẻ đã sang Telegram (chỉ gửi "
            "một lần). Bấm 'luôn cho phép' thì các vòng sau khỏi hỏi nữa.")
        return 0
    if kq.get("status") != "ok":
        noi(f"không nhận được việc: {kq.get('status')} · "
            f"{str(kq.get('summary'))[:200]}")
        return 1
    o = kq.get("output") or {}
    if not o.get("coViec"):
        noi(kq.get("summary") or "xưởng trống")
        return 0

    viec_id, tieu_de = o["viecId"], o["tieuDe"]
    noi(f"nhận {viec_id}: {tieu_de}")
    if o.get("lanTruocDung"):
        noi(f"  lần trước dừng vì: {o['lanTruocDung']}")
    noi(f"  bước kế tiếp: {o.get('buocKeTiep')}")

    la_du_an = o.get("loai") == "duAn"

    # GHI TRƯỚC KHI LÀM. Mất điện ở bất cứ dòng nào dưới đây thì đây là thứ
    # còn lại.
    ten_buoc = "dựng thư mục dự án" if la_du_an else "dựng nhánh làm việc"
    ghi_buoc(viec_id, ten_buoc, "dangLam",
             ke_tiep=("Dựng ~/work/duan/<mã việc> rồi gọi não" if la_du_an
                      else "Dựng nhánh y/<mã việc> từ origin/main rồi gọi não"))
    if la_du_an:
        cho_lam, loi = thu_muc_du_an(viec_id, tieu_de), ""
        nhanh = ""
    else:
        nhanh, loi = chuan_bi_nhanh(viec_id)
        cho_lam = nhanh
    if not cho_lam:
        ghi_buoc(viec_id, ten_buoc, "hong", loi, 1)
        goi("xuongCompany", "tamDung",
            {"viecId": viec_id, "lyDo": "loi", "ghiChu": loi[:900],
             "buocKeTiep": "Sửa chỗ git hỏng rồi nhận lại việc"})
        return 1
    ghi_buoc(viec_id, ten_buoc, "xong", cho_lam, 0,
             ke_tiep="Gọi não làm phần việc chính")

    ghi_buoc(viec_id, "gọi não làm việc", "dangLam",
             ke_tiep="Não đang chạy; nếu đứt ở đây thì kiểm git status trước "
                     "khi gọi lại, tránh làm hai lần")
    ok, chu, ly_do = goi_nao(dict(o, lanTruocDung=o.get("lanTruocDung")),
                             cho_lam, kho)
    if ly_do:
        # Hai loại dừng, hai cái hẹn khác nhau — cố ý không gộp:
        #   hetHanMuc     → vài tiếng nữa tự hết, hẹn lại 4 tiếng.
        #   chuaDangNhap  → đợi bao lâu cũng không tự khỏi, phải có người bấm.
        #                   Hẹn xa (12 tiếng) để thợ khỏi quay vòng vô ích suốt
        #                   đêm, và câu ghi chú phải nói RÕ ai cần làm gì.
        gio_cho = 4 if ly_do == "hetHanMuc" else 12
        tiep = (datetime.now(timezone.utc) + timedelta(hours=gio_cho)
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
        ghi_chu = chu[-900:]
        if ly_do == "chuaDangNhap":
            ghi_chu = ("Claude trong hộp CHƯA ĐĂNG NHẬP. Đại ca chạy một lần:\n"
                       "  wsl -d openclaw -u hop -- claude /login\n\n" + chu[-600:])
        ghi_buoc(viec_id, "gọi não làm việc", "hong", chu[-800:], 1)
        goi("xuongCompany", "tamDung",
            {"viecId": viec_id,
             "lyDo": "hetHanMuc" if ly_do == "hetHanMuc" else "loi",
             "ghiChu": ghi_chu, "tiepLuc": tiep,
             "buocKeTiep": "Gọi lại não cho phần việc chính"})
        noi(f"DỪNG ({ly_do}) — hẹn lại {tiep}")
        return 3
    ghi_buoc(viec_id, "gọi não làm việc", "xong" if ok else "hong",
             chu[-800:], 0 if ok else 1,
             ke_tiep=("Soát có tệp thật rồi đóng việc" if la_du_an
                      else "Chạy codemap --check rồi đẩy nhánh"))

    # ── Tự kiểm. "Xong" phải ĐO ĐƯỢC, không phải do não tự nhận ──
    #
    # Hai loại việc đo bằng hai thước khác nhau, và phải khác: `codemap --check`
    # nói được điều gì đó về repo companySpec, nhưng không nói gì về một web
    # app. Dùng nhầm thước thì hoặc chặn oan, hoặc gật bừa.
    cwd = cho_lam if la_du_an else BAN_SAO
    ma_st, tinh_trang = chay(["git", "status", "--porcelain"], cwd=cwd)
    co_doi = bool(tinh_trang.strip())
    ghi_buoc(viec_id, "soát có thay đổi thật không",
             "xong" if co_doi else "hong",
             tinh_trang[:500] or "KHÔNG có tệp nào được tạo hay sửa",
             0 if co_doi else 1)

    if la_du_an:
        # Không có luật kiến trúc nào để soát một dự án lạ. Thước đo ở đây là
        # thứ đếm được: có bao nhiêu tệp, và có README nói cách chạy không.
        so_tep = len([d for d in tinh_trang.splitlines() if d.strip()])
        co_readme = any(os.path.exists(os.path.join(cwd, t))
                        for t in ("README.md", "readme.md", "README"))
        ma_luat = 0 if co_readme else 1
        ra_luat = (f"{so_tep} tệp được tạo/sửa · README: "
                   f"{'có' if co_readme else 'KHÔNG CÓ'}")
        ghi_buoc(viec_id, "soát dự án có chạy được không",
                 "xong" if co_readme else "hong", ra_luat, ma_luat,
                 ke_tiep="Ghi commit rồi đóng việc")
    else:
        ma_luat, ra_luat = chay(["python3", "ops/codemap.py", "--check"],
                                tra=180, cwd=cwd)
        ghi_buoc(viec_id, "codemap --check", "xong" if ma_luat == 0 else "hong",
                 ra_luat[-600:], ma_luat, ke_tiep="Đẩy nhánh rồi đóng việc")

    if not (co_doi and ma_luat == 0 and ok):
        vi = []
        if not ok:
            vi.append("não báo hỏng")
        if not co_doi:
            vi.append("không tạo/sửa tệp nào (rất có thể chỉ trả về một câu kế hoạch)")
        if ma_luat != 0:
            vi.append("thiếu README nói cách chạy" if la_du_an
                      else f"codemap --check thoát {ma_luat}")
        goi("xuongCompany", "xongViec",
            {"viecId": viec_id, "trangThai": "hong", "nhanh": nhanh,
             "ketQua": "CHƯA XONG — " + " · ".join(vi) + f"\n{ra_luat[-500:]}"})
        noi("việc về HỎNG: " + " · ".join(vi))
        return 1

    chay(["git", "add", "-A"], cwd=cwd)
    chay(["git", "commit", "-m",
          f"{tieu_de[:60]}\n\nViệc {viec_id} của xưởng, do hộp làm."], cwd=cwd)

    if la_du_an:
        # KHÔNG đẩy đi đâu cả: gương chỉ nhận nhánh y/* của companySpec, và
        # một dự án riêng không có việc gì nằm trong lịch sử của repo hệ.
        # Admin mở thẳng thư mục từ Windows Explorer.
        duong_win = ("\\\\wsl.localhost\\openclaw"
                     + cho_lam.replace("/", "\\"))
        goi("xuongCompany", "xongViec",
            {"viecId": viec_id, "trangThai": "choXem",
             "ketQua": f"Dự án nằm trong hộp: {cho_lam}\n"
                       f"Mở từ Windows: {duong_win}\n{ra_luat}\n"
                       f"{tinh_trang.strip()[-400:]}"})
        noi(f"XONG {viec_id} → {cho_lam} (mở Windows: {duong_win})")
        return 0

    ma_p, ra_p = chay(["git", "push", "-u", "origin", nhanh], tra=180, cwd=cwd)
    ghi_buoc(viec_id, "đẩy nhánh lên gương", "xong" if ma_p == 0 else "hong",
             ra_p[-400:], ma_p)
    if ma_p != 0:
        goi("xuongCompany", "tamDung",
            {"viecId": viec_id, "lyDo": "loi", "ghiChu": ra_p[-900:],
             "buocKeTiep": "Đẩy lại nhánh lên gương"})
        return 1

    goi("xuongCompany", "xongViec",
        {"viecId": viec_id, "trangThai": "choXem", "nhanh": nhanh,
         "ketQua": f"{tinh_trang.strip()[-600:]}\ncodemap --check: sạch. "
                   f"Nhánh {nhanh} đã đẩy lên gương, chờ đại ca xem rồi gộp."})
    noi(f"XONG {viec_id} → nhánh {nhanh}, chờ đại ca xem")
    return 0


def xem() -> int:
    kq = goi("xuongCompany", "dsViec", {})
    print(kq.get("summary") or json.dumps(kq, ensure_ascii=False)[:500])
    return 0 if kq.get("status") == "ok" else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="thợ — vòng làm việc của hộp")
    ap.add_argument("--mot-vong", action="store_true", help="làm một việc rồi thoát")
    ap.add_argument("--xem", action="store_true", help="xem xưởng, không làm gì")
    ap.add_argument("--khong-goi-nao", action="store_true",
                    help="chạy khô: đi hết vòng nhưng KHÔNG gọi model nào")
    args = ap.parse_args()
    if args.xem:
        return xem()
    if args.mot_vong:
        return mot_vong(args.khong_goi_nao)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
