#!/usr/bin/env python3
"""Bộ não của CEO — chọn nó, kiểm nó, và chạy bản dự phòng khi Claude câm.

VÌ SAO CÓ FILE NÀY: trước đây CEO chỉ có MỘT bộ não, `claude -p`. Hết hạn mức
gói Pro, hết phiên đăng nhập, hay đơn giản là mất mạng tới Anthropic — thì cả
hệ câm: không ghi được một khoản chi, không tra được lịch hôm nay, không trả
lời được một câu. Mọi company vẫn chạy tốt (chúng là code cứng), nhưng không ai
gọi được chúng vì người gọi đã chết. Một trợ lý cá nhân mà sống nhờ hạn mức của
một nhà cung cấp thì nó không phải của admin, nó đi mượn.

BA CHẾ ĐỘ (registry/models.yaml → nao.macDinh, admin đổi được lúc chạy):
  claude — như cũ, `claude -p`. Mạnh nhất, tốn hạn mức Pro.
  tu     — claude trước; hết hạn mức / hết phiên thì TỰ chuyển sang não phụ.
  phu    — luôn chạy não phụ, không đụng tới gói Pro.

NÃO PHỤ HẸP HƠN NÃO THẬT, VÀ ĐÓ LÀ CHỦ Ý. Claude CLI cầm tool Bash rồi bị rào
lại bằng deny-list và hook; ở đây model không có shell nào cả — nó chỉ có ĐÚNG
MỘT hàm `goiCompany`, và tham số của hàm đó do code này dựng thành argv, không
qua shell. Không có đường nào để một câu chữ biến thành lệnh máy. T2 giữ
nguyên: vẫn đúng một cổng `ops/dispatch.py`, vẫn đủ kiểm tra schema, riskTier,
phê duyệt, loop guard.

ĐÃ ĐO 2026-08-31 (`python3 ops/evals/run.py --nao phu`), và kết quả đúng như dự
đoán ban đầu — nhưng cụ thể hơn nhiều:

  · Việc MỘT LƯỢT: làm được. 3/4 ca đạt, kể cả chuỗi tiền hai vế (ghi chi rồi
    trừ ví) và mảng object lồng nhau. Ca thứ tư chết vì cả hai model Gemini
    cùng trả 503, tức hỏng vì nhà cung cấp chứ không phải vì model kém.
  · Việc NHIỀU LƯỢT: kém, và kém theo hướng NGUY HIỂM. Ban đầu 1/3 ca đạt.
    Admin hỏi "em ghi chưa đấy" thì nó GHI LẠI LẦN HAI rồi nói "em ghi ngay
    lúc đại ca nhắn rồi ạ" — sổ đôi, ví trừ hai lần, và câu nói khiến không ai
    đi kiểm. Thêm luật vào KHOI_DAN thì ca đó chuyển sang đạt.
  · CÒN LẠI MỘT LỖI CHƯA CHỮA ĐƯỢC BẰNG LỜI DẶN: xoá khoản chi mà quên hoàn
    tiền vào ví. Chạy lại BA lần, cả ba đều quên, dù luật đã nằm trong prompt.
    Nên gateway nhắc admin soát tay mỗi khi não phụ có động vào sổ.

Kết luận dùng được: não phụ đỡ được những quãng Claude câm cho việc thường
ngày, nhưng đừng giao cho nó việc sửa/xoá dây chuyền rồi tin là xong.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "lib"))
import db  # noqa: E402
import llmClient  # noqa: E402

# Ranh giới dữ liệu sống ở core/, không viết lại ở đây (§29, một luật một chỗ).
sys.path.insert(0, ROOT)
from core.brainRouter import (  # noqa: E402
    classificationForPrivacyLevel, filterProviderChain, loadBrainPolicy,
)

DISPATCH = os.path.join(ROOT, "ops", "dispatch.py")
CEO_STORE = os.path.join(ROOT, "ceo", "store.sqlite")
BACKOFFICE = os.path.join(ROOT, "backOffice", "store.sqlite")

CHE_DO = ("claude", "tu", "phu")

# Trần chữ của một kết quả company nhét lại vào đầu model. Danh sách 100 khoản
# chi có thể dài hàng chục nghìn ký tự; model nhỏ nuốt không nổi và cũng không
# cần — nó chỉ cần đủ để tóm tắt lại cho admin.
CAT_KET_QUA = 4000


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cat(s: str, n: int) -> str:
    """Cắt và NÓI RÕ là đã cắt (cùng luật với gateway.cat_gon).

    Cắt im lặng thì model đọc nửa danh sách y như đọc cả danh sách, rồi báo
    admin một con số thiếu mà nghe rất chắc chắn.
    """
    s = s or ""
    if len(s) <= n:
        return s
    return s[:n] + f"\n…[đã cắt, còn {len(s) - n} ký tự nữa]"


# ───────────────────── chế độ đang dùng ─────────────────────
#
# File cấu hình là mặc định; admin đổi lúc chạy thì ghi đè vào sổ CEO. Hai tầng
# chứ không một: đổi tạm bằng tin nhắn không nên sửa file trong git, còn mặc
# định sau khi khởi động lại phải quay về thứ admin đã chốt trong file.

def _cai_dat_store():
    conn = db.connect(CEO_STORE)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS caiDat (
          khoa TEXT PRIMARY KEY, giaTri TEXT NOT NULL, datLuc TEXT NOT NULL)""")
    return conn


def che_do(cfg: dict = None) -> tuple:
    """Trả (chế_độ, nguồn). Nguồn để còn nói cho admin biết vì sao đang thế."""
    try:
        conn = _cai_dat_store()
        row = conn.execute("SELECT giaTri FROM caiDat WHERE khoa='nao'").fetchone()
        conn.close()
        if row and row[0] in CHE_DO:
            return row[0], "admin đặt"
    except Exception as exc:      # O10 — sổ hỏng thì nói ra, đừng im
        print(f"[nao] không đọc được caiDat: {type(exc).__name__}: {exc}",
              file=sys.stderr)
    try:
        cfg = cfg or llmClient.nap()
        mac = (cfg.get("nao") or {}).get("macDinh")
        if mac in CHE_DO:
            return mac, "models.yaml"
    except llmClient.LLMError as exc:
        print(f"[nao] không đọc được models.yaml: {exc}", file=sys.stderr)
    # Không đọc được gì thì về đúng hành vi CŨ. Mặc định an toàn là "y như
    # trước khi có file này", không phải "thử cái mới".
    return "claude", "mặc định cứng"


def dat_che_do(gia_tri: str) -> str:
    if gia_tri not in CHE_DO:
        raise ValueError(f"chế độ phải là một trong {', '.join(CHE_DO)}")
    conn = _cai_dat_store()
    conn.execute("INSERT OR REPLACE INTO caiDat (khoa, giaTri, datLuc) "
                 "VALUES ('nao', ?, ?)", (gia_tri, now()))
    conn.commit()
    conn.close()
    return gia_tri


# ───────────────────── phần thêm vào prompt ─────────────────────
#
# ceo/SYSTEM.md dạy CEO gọi company bằng câu lệnh shell. Não phụ KHÔNG CÓ shell,
# nên phần đó phải được đè lại — nếu không model sẽ viết ra một câu lệnh bash
# rồi ngồi đợi kết quả không bao giờ tới.

KHOI_DAN = """

## ĐỌC KỸ — bạn đang chạy trên bộ não DỰ PHÒNG

Phần "Cách gọi company" ở trên nói về câu lệnh shell. Ở đây KHÔNG CÓ shell.
Bạn có đúng một công cụ tên goiCompany, ba tham số:
  company    tên company, ví dụ expenseCompany
  capability tên năng lực, ví dụ addExpense
  input      object đúng theo tên trường trong Danh mục company bên dưới
  approvalId chỉ điền khi admin vừa bấm duyệt và hệ đưa mã cho bạn

Mọi luật khác giữ nguyên: vẫn đúng một cổng, vẫn cần admin duyệt cho việc ghi,
vẫn không được bịa. Không viết câu lệnh bash, không nói "để em chạy lệnh".

Bạn yếu hơn bộ não chính, nên giữ ba điều này cho chặt:
· Làm ÍT lời gọi thôi. Xong việc admin nhờ thì dừng và trả lời.
· Không chắc tên trường thì đọc lại Danh mục công ty, đừng đoán.
· Việc dài nhiều bước mà thấy rối thì nói thẳng là nên đợi bộ não chính, đừng
  làm nửa vời rồi báo đã xong.

## HAI LỖI BẠN ĐÃ MẮC THẬT — đọc kỹ, đây không phải lời dặn chung chung

Đo ngày 2026-08-31 trên bộ ca thử, chạy đúng bộ não này:

1. ĐỪNG GHI LẠI THỨ ĐÃ GHI. Admin nhắn "50k ck ăn sáng", bạn ghi đúng. Lượt
   sau admin hỏi "em ghi chưa đấy" — và bạn GHI LẠI LẦN NỮA, rồi nói với admin
   "em đã ghi ngay sau khi đại ca nhắn rồi ạ". Sổ chi của admin có hai khoản,
   ví bị trừ hai lần, và câu bạn nói khiến không ai đi kiểm.
   Câu hỏi "em ghi chưa", "xong chưa", "làm chưa" là CÂU HỎI, không phải lệnh
   làm lại. Nhìn lại các lượt trước trong cuộc trò chuyện: đã gọi rồi thì trả
   lời là đã gọi rồi, kèm những gì đã ghi. Không gọi lại.

2. VIỆC VỀ TIỀN CÓ HAI VẾ, ĐỪNG BỎ VẾ SAU. Bạn xoá một khoản chi mà quên hoàn
   tiền lại vào ví. Ghi chi thì trừ ví; xoá khoản chi thì CỘNG LẠI vào ví; ghi
   thu thì cộng ví. Làm vế đầu rồi dừng là để lại sổ sai mà không dòng lỗi nào
   báo lên.
   Và làm THEO THỨ TỰ, đợi kết quả: lệnh đầu trả về rejected hay needsApproval
   thì DỪNG, đừng chạy vế sau — chỉnh ví trước khi biết sổ có đổi không là tạo
   ra một cái sai không có dấu vết.
"""

TOOLS = [{
    "type": "function",
    "function": {
        "name": "goiCompany",
        "description": ("Gọi một năng lực của company. Đây là cách DUY NHẤT để "
                        "làm bất cứ việc gì có tác động ra ngoài: ghi chi tiêu, "
                        "đặt lịch, tra sổ, ghi nhớ hồ sơ."),
        "parameters": {
            "type": "object",
            "required": ["company", "capability", "input"],
            "properties": {
                "company": {"type": "string"},
                "capability": {"type": "string"},
                "input": {"type": "object"},
                "approvalId": {"type": "string"},
            },
        },
    },
}]


def _doc_goi_trong_chu(chu: str):
    """Model không gọi tool mà VIẾT RA một khối JSON thì vẫn hiểu.

    Model nhỏ hay làm đúng việc này: nó biết phải gọi gì, chỉ là không dùng
    đúng kênh tool_calls. Bỏ qua thì admin nhận về một cục JSON thay vì câu trả
    lời, và việc thì không chạy — hỏng theo kiểu vô lý nhất. Đọc thêm một định
    dạng rẻ hơn nhiều so với đổi model.

    Chỉ nhận khối có ĐỦ ba khoá company/capability/input. Thiếu thì coi như
    model đang nói chuyện bình thường, đừng đoán.
    """
    if not chu or "capability" not in chu:
        return None
    d = llmClient.boc_json(chu)     # phần bóc rào ```json nằm chung ở lib
    if d is None:
        return None
    # Có nơi model bọc thêm một tầng {"goiCompany": {...}} hoặc {"tool": {...}}
    for khoa in ("goiCompany", "tool", "goi"):
        if isinstance(d.get(khoa), dict):
            d = d[khoa]
            break
    if all(k in d for k in ("company", "capability")) and isinstance(
            d.get("input"), dict):
        return {"id": "chu_0", "ten": "goiCompany", "thamSo": d}
    return None


# ───────────────────── gọi company ─────────────────────

def goi_company(tham: dict, *, trace_id: str, session_id: str, timeout: int,
                dispatch_py: str = "", cwd: str = "",
                env_them: dict = None) -> str:
    """Chạy đúng một lời gọi qua dispatcher. Trả về chữ để nhét lại vào model.

    KHÔNG QUA SHELL. argv dựng bằng tay từ các trường đã tách, nên dù model có
    nhét dấu nháy, dấu chấm phẩy hay `$(...)` vào tên company thì nó cũng chỉ
    là một chuỗi tham số — dispatcher sẽ trả "không có company đó" và hết
    chuyện. Đây là chỗ não phụ CHẶT HƠN Claude CLI, vốn phải rào Bash bằng
    deny-list.
    """
    cid = str(tham.get("company") or "")
    cap = str(tham.get("capability") or "")
    inp = tham.get("input")
    if not cid or not cap or not isinstance(inp, dict):
        return json.dumps({"status": "rejected", "error":
                           "thiếu company/capability/input, hoặc input không "
                           "phải object"}, ensure_ascii=False)

    # `dispatch_py`/`cwd` là THAM SỐ, cố ý không phải biến môi trường: chỉ bộ
    # ca thử truyền chúng (để trỏ vào dispatcher giả), và tham số thì model
    # không có đường nào chạm tới. Một biến môi trường đổi được cổng ra thì
    # sớm muộn thành lỗ hổng — T2 phải do code giữ, không do môi trường giữ.
    argv = [sys.executable, dispatch_py or DISPATCH, "call", "--company", cid,
            "--capability", cap, "--input",
            json.dumps(inp, ensure_ascii=False)]
    if tham.get("approvalId"):
        argv += ["--approval-id", str(tham["approvalId"])]

    env = {**os.environ,
           "COMPANYSPEC_SESSION_ID": session_id,
           "COMPANYSPEC_TRACE_ID": trace_id,
           **(env_them or {})}
    try:
        proc = subprocess.run(argv, cwd=cwd or ROOT, capture_output=True,
                              text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        # O8 — không để lỗi này làm sập vòng lặp. Model cần đọc được câu này để
        # còn báo lại admin cho tử tế.
        return json.dumps({"status": "failed", "error":
                           f"dispatcher không trả lời trong {timeout}s"},
                          ensure_ascii=False)
    ra = (proc.stdout or "").strip()
    if not ra:
        # Cắt từ ĐUÔI: traceback Python để loại lỗi ở dòng cuối.
        return json.dumps({"status": "failed", "error":
                           f"dispatcher thoát mã {proc.returncode}: "
                           + (proc.stderr or "")[-600:]}, ensure_ascii=False)
    return _cat(ra, CAT_KET_QUA)


# ───────────────────── vòng lặp não phụ ─────────────────────

def _ghi_tien_that(vnd: float, mo_ta: str, trace_id: str) -> None:
    """Não phụ tiêu tiền thật thì ghi vào ĐÚNG cái sổ dispatcher đang ghi.

    Bài học "bộ đo tự đứng ngoài phép đo": thứ nào tiêu hạn mức thì phải ghi sổ,
    kể cả công cụ của chính hệ. Ghi chung bảng chiTieuNgoai, tách bằng
    companyId — hai bảng thì sớm muộn có người cộng một bảng rồi tưởng đã cộng hết.
    """
    if vnd <= 0:
        return
    try:
        conn = db.connect(BACKOFFICE)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS chiTieuNgoai (
              chiId INTEGER PRIMARY KEY AUTOINCREMENT, taskId TEXT, traceId TEXT,
              companyId TEXT NOT NULL, capability TEXT NOT NULL,
              nhaCungCap TEXT, soTienVnd REAL NOT NULL, ghiChu TEXT,
              createdAt TEXT NOT NULL)""")
        conn.execute(
            "INSERT INTO chiTieuNgoai (taskId, traceId, companyId, capability, "
            "nhaCungCap, soTienVnd, ghiChu, createdAt) VALUES (?,?,?,?,?,?,?,?)",
            (None, trace_id, "(naoPhu)", "suyNghi", mo_ta, float(vnd),
             "não phụ của CEO, tính từ token", now()))
        conn.commit()
        conn.close()
    except Exception as exc:
        print(f"[nao] không ghi được chiTieuNgoai: {type(exc).__name__}: {exc}",
              file=sys.stderr)


def _da_tieu_thang() -> float:
    """Tiền THẬT đã tiêu cho API ngoài trong tháng dương này.

    Đọc CÙNG một cái sổ dispatcher đang ghi (`chiTieuNgoai`), không dựng sổ
    riêng. Hai sổ thì sớm muộn có người cộng một sổ rồi tưởng đã cộng hết —
    và cái trần sẽ nới ra gấp đôi mà không ai để ý.
    """
    dau = datetime.now(timezone.utc).strftime("%Y-%m-01T00:00:00Z")
    try:
        conn = db.connect(BACKOFFICE)
        tong = conn.execute(
            "SELECT COALESCE(SUM(soTienVnd), 0) FROM chiTieuNgoai "
            "WHERE createdAt >= ?", (dau,)).fetchone()[0]
        conn.close()
        return float(tong or 0)
    except Exception as exc:
        # Không đọc được sổ thì coi như ĐÃ TIÊU HẾT TRẦN, không phải coi như 0.
        # O10 ngược chiều: chỗ này mà nuốt lỗi thành 0 thì một sổ hỏng sẽ mở
        # toang cầu dao đúng lúc không ai nhìn.
        print(f"[nao] không đọc được sổ chiTieuNgoai: {exc}", file=sys.stderr)
        return float("inf")


def _tran_thang() -> float:
    """Trần tiền thật mỗi tháng, lấy từ registry/gateway.yaml (một nguồn duy nhất)."""
    try:
        import yaml
        with open(os.path.join(ROOT, "registry", "gateway.yaml"),
                  encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
        return float((cfg.get("chiTieuNgoai") or {}).get("tranThangVnd") or 0)
    except Exception as exc:
        print(f"[nao] không đọc được trần tháng: {exc}", file=sys.stderr)
        return 0.0


def _con_tra_tien_duoc() -> tuple:
    """(được phép tiêu tiếp?, câu giải thích). Kiểm TRƯỚC khi gọi, không phải sau.

    Dispatcher đã có đúng phép kiểm này cho company (L8), nhưng não phụ không đi
    qua dispatcher — nó LÀ người gọi dispatcher. Không có bản kiểm riêng ở đây
    thì bộ não là thứ duy nhất trong hệ tiêu tiền thật mà không cái trần nào
    chạm tới được.
    """
    tran = _tran_thang()
    if not tran:
        return True, ""
    da = _da_tieu_thang()
    if da >= tran:
        return False, (f"tháng này đã tiêu {da:,.0f}đ tiền thật cho API ngoài, "
                       f"chạm trần {tran:,.0f}đ. Muốn tiêu thêm thì sửa "
                       "chiTieuNgoai.tranThangVnd trong registry/gateway.yaml.")
    return True, ""


def chay(message: str, *, system_prompt: str, lich_su: list = None,
         trace_id: str = "", session_id: str = "", cfg: dict = None,
         timeout: int = 300, dispatch_py: str = "", cwd: str = "",
         env_them: dict = None) -> dict:
    """Chạy một lượt CEO trên não phụ. Trả về ĐÚNG hình dáng mà run_ceo trả.

    Cùng hình dáng là điều kiện để gateway không phải biết nó đang chạy bộ não
    nào — `result` / `is_error` / `usage` / `total_cost_usd` / `num_turns`.
    Thêm vài trường riêng (`nao`, `moTaNao`, `tienVnd`) để báo cáo và ghi sổ.

    `total_cost_usd` LUÔN là 0: đó là cột đo hạn mức gói Claude, mà đường này
    không đụng tới gói đó. Tiền thật (nếu có) nằm ở `tienVnd` và đã vào sổ
    chiTieuNgoai. Nhét tiền của nhà khác vào cột costUsd là làm hỏng đúng con
    số mà backOffice đang dùng để đối chiếu.
    """
    bat_dau = time.monotonic()
    han_chot = bat_dau + timeout
    cfg = cfg or llmClient.nap()
    nao_cfg = cfg.get("nao") or {}
    chuoi = nao_cfg.get("chuoi") or []
    luot_toi_da = int(nao_cfg.get("soLuotToiDa") or 8)
    chi_mien_phi = not nao_cfg.get("chapNhanTraTien")

    # L8 — chạm trần tháng thì HẠ chuỗi xuống còn nhà miễn phí, đừng tiêu lố.
    # Không dừng hẳn: còn nhà miễn phí nào trong chuỗi thì vẫn nên chạy, vì
    # lúc này Claude cũng đang câm và admin đang không có ai để nói chuyện.
    canh_tran = ""
    if not chi_mien_phi:
        duoc, ly_do = _con_tra_tien_duoc()
        if not duoc:
            chi_mien_phi = True
            canh_tran = ly_do

    # ─── RANH GIỚI DỮ LIỆU (§29) ───
    #
    # "Local-first" KHÔNG có nghĩa dữ liệu không rời máy: gọi API của nhà nào
    # là context đi sang máy nhà đó. Đo 27/08 — một lượt đi ra 37.282 byte, có
    # cả hồ sơ đời tư và số dư từng ví.
    #
    # `nao.riengTu` quyết định prompt bị cắt tới đâu, và mức cắt quyết định
    # nhà nào được nhận. Luật nằm ở registry/brainPolicy.yaml, không ở đây —
    # nới nó phải là sửa một file đọc được, không phải sửa một nhánh `if`.
    muc_rieng_tu = (nao_cfg.get("riengTu") or "canTrong")
    phan_loai = classificationForPrivacyLevel(muc_rieng_tu)
    # `nhaThuThem` CHỈ dùng cho ca thử với nhà giả — xem docstring của
    # filterProviderChain. models.yaml thật không khai khoá này.
    chuoi, bi_chan = filterProviderChain(
        chuoi, phan_loai, loadBrainPolicy(),
        extraAllowed=tuple(nao_cfg.get("nhaThuThem") or ()))
    if bi_chan:
        # KHÔNG im lặng. Chặn mà không nói thì admin thấy "bộ não dự phòng
        # không chạy" và đi tìm lỗi ở chỗ không có lỗi.
        print(f"[nao] ranh giới dữ liệu `{phan_loai.value}` "
              f"(riengTu={muc_rieng_tu}) chặn: {', '.join(bi_chan)}",
              file=sys.stderr)
    if not chuoi:
        return {"result":
                f"Không gọi được bộ não dự phòng nào: mức riêng tư "
                f"`{muc_rieng_tu}` xếp prompt vào loại `{phan_loai.value}`, và "
                f"ranh giới dữ liệu chặn mọi nhà trong chuỗi "
                f"({', '.join(bi_chan) or 'chuỗi rỗng'}).\n\n"
                "Đây KHÔNG phải lỗi — đó là luật đang giữ đúng thứ nó phải "
                "giữ. Muốn đổi thì sửa `dataBoundary` trong "
                "registry/brainPolicy.yaml, hoặc đặt `nao.riengTu: canTrong` "
                "để prompt được cắt bớt trước khi gửi đi.",
                "is_error": True, "tienVnd": 0.0, "soLuot": 0}

    tin = [{"role": "system", "content": system_prompt + KHOI_DAN}]
    for m in lich_su or []:
        tin.append({"role": "user" if m.get("vaiTro") == "admin" else "assistant",
                    "content": m.get("noiDung") or ""})
    tin.append({"role": "user", "content": message})

    tien, tokens_vao, tokens_ra, luot = 0.0, 0, 0, 0
    so_loi_goi = 0          # lượt này có động vào sổ không — xem cuối hàm
    so_loi_goi = 0
    mo_ta_nao, tra_loi, da_thu = "", "", []

    while luot < luot_toi_da:
        con_lai = int(han_chot - time.monotonic())
        if con_lai < 15:
            return _het_gio(tra_loi, tien, luot, bat_dau, mo_ta_nao,
                            tokens_vao, tokens_ra)
        try:
            kq = llmClient.goi_chuoi(
                chuoi, cfg=cfg, chi_mien_phi=chi_mien_phi, messages=tin,
                tools=TOOLS, timeout=min(90, con_lai), max_tokens=1200)
        except llmClient.LLMError as exc:
            return {"result":
                    "Bộ não chính không dùng được, mà bộ não dự phòng cũng "
                    f"không gọi được model nào: {exc}."
                    + (f" (Và {canh_tran})" if canh_tran else "")
                    + " Đại ca kiểm khoá trong ops/.env hoặc chạy "
                      "python3 ops/nao.py kiem.",
                    "is_error": True, "usage": {}, "total_cost_usd": 0.0,
                    "num_turns": luot, "duration_ms": _ms(bat_dau),
                    "nao": "phu", "moTaNao": mo_ta_nao, "tienVnd": tien}

        luot += 1
        tien += kq.get("tienVnd") or 0
        tokens_vao += (kq.get("usage") or {}).get("prompt_tokens") or 0
        tokens_ra += (kq.get("usage") or {}).get("completion_tokens") or 0
        mo_ta_nao = f'{kq["nha"]}/{kq["model"]}'
        da_thu += kq.get("daThu") or []
        tra_loi = kq.get("chu") or tra_loi

        goi = kq.get("goiTool") or []
        if not goi:
            trong_chu = _doc_goi_trong_chu(kq.get("chu") or "")
            if trong_chu:
                goi = [trong_chu]
        if not goi:
            break                      # model đã trả lời xong

        # Lượt của model: GỬI LẠI NGUYÊN VĂN bản nhà cung cấp trả về, đừng dựng
        # lại. Nhà nào cũng có quyền gắn thêm trường riêng vào lượt đó và đòi
        # nhận lại đúng nó — đo thật 27/08: Gemini 3.x gắn `thought_signature`
        # vào tool_calls, thiếu là HTTP 400 ở lượt SAU, tức là não phụ gọi được
        # company rồi chết ngay khi đọc kết quả. Chỉ dựng tay khi không có bản
        # gốc (đường CLI, vốn chỉ chạy một lượt).
        tin.append(kq.get("tinGoc") or {
            "role": "assistant", "content": kq.get("chu") or "",
            "tool_calls": [{"id": g["id"], "type": "function",
                            "function": {"name": g["ten"],
                                         "arguments": json.dumps(
                                             g["thamSo"], ensure_ascii=False)}}
                           for g in goi]})
        for g in goi:
            if g["ten"] != "goiCompany":
                ket = json.dumps({"status": "rejected", "error":
                                  f"không có công cụ tên {g['ten']}. Chỉ có "
                                  "goiCompany."}, ensure_ascii=False)
            else:
                con_lai = int(han_chot - time.monotonic())
                ket = goi_company(g["thamSo"], trace_id=trace_id,
                                  session_id=session_id,
                                  timeout=max(20, min(900, con_lai - 10)),
                                  dispatch_py=dispatch_py, cwd=cwd,
                                  env_them=env_them)
            so_loi_goi += 1
            so_loi_goi += 1
            tin.append({"role": "tool", "tool_call_id": g["id"],
                        "name": g["ten"], "content": ket})
        tra_loi = ""      # đã gọi tool thì câu chữ lượt trước không phải câu trả lời

    _ghi_tien_that(tien, mo_ta_nao, trace_id)

    het_luot = luot >= luot_toi_da and not tra_loi
    if het_luot:
        # L3 — chạm trần vòng suy nghĩ. Nói rõ việc CÓ THỂ ĐÃ LÀM MỘT PHẦN,
        # cùng câu chữ với nhánh max-turns của Claude CLI: admin phải đi kiểm
        # chứ không nhắn lại từ đầu.
        tra_loi = (f"Em chạy hết {luot} lượt trên bộ não dự phòng mà chưa "
                   "xong. Việc có thể đã làm được một phần — đại ca kiểm lại "
                   "rồi nhắn tiếp phần còn thiếu.")

    if canh_tran:
        # Nói ngay trong câu trả lời, đừng để admin phát hiện qua báo cáo cuối
        # tháng: lúc này họ đang mất Claude, và mất luôn Gemini là chuyện họ
        # cần biết để còn quyết định nâng trần hay chờ.
        tra_loi = (tra_loi or "") + f"\n\n(Lưu ý: {canh_tran} Nên lượt này em "
        tra_loi += "chạy bằng model miễn phí, yếu hơn.)"

    return {"result": tra_loi or "Bộ não dự phòng không trả về nội dung nào.",
            "is_error": het_luot or not tra_loi,
            "usage": {"input_tokens": tokens_vao, "output_tokens": tokens_ra},
            "total_cost_usd": 0.0, "num_turns": luot,
            "duration_ms": _ms(bat_dau), "nao": "phu", "moTaNao": mo_ta_nao,
            "tienVnd": round(tien, 2), "daThu": da_thu,
            # Lượt này có ĐỘNG VÀO SỔ hay không. Gateway dùng nó để nhắc admin
            # soát lại — xem `_chay_phu`.
            "soLoiGoi": so_loi_goi}


def _ms(bat_dau: float) -> int:
    return int((time.monotonic() - bat_dau) * 1000)


def _het_gio(tra_loi, tien, luot, bat_dau, mo_ta_nao, tv, tr) -> dict:
    return {"result": (tra_loi or "") + ("\n\n" if tra_loi else "")
            + "Hết giờ giữa chừng nên em dừng ở đây. Việc có thể mới xong một "
              "phần, đại ca kiểm lại trước khi nhắn tiếp.",
            "is_error": True,
            "usage": {"input_tokens": tv, "output_tokens": tr},
            "total_cost_usd": 0.0, "num_turns": luot, "duration_ms": _ms(bat_dau),
            "nao": "phu", "moTaNao": mo_ta_nao, "tienVnd": round(tien, 2)}


# ───────────────────── lệnh dòng lệnh ─────────────────────

def _nap_env() -> None:
    """Dùng lại đúng hàm đọc .env của gateway — một chỗ đọc, không hai.

    Nạp muộn (trong hàm) để không tạo vòng import: gateway import file này ở
    tầng module, nên chiều ngược lại phải nằm trong hàm.
    """
    sys.path.insert(0, HERE)
    import gateway
    gateway.nap_env()


def cmd_kiem(args) -> int:
    """Hỏi thật từng nhà một câu ngắn. Đây là nguồn sự thật DUY NHẤT về việc
    tên model trong models.yaml còn sống hay đã bị rút.

    Không có lệnh này thì một tên model chết sẽ hỏng NGẦM: chuỗi tự nhảy sang
    nhà sau, hệ vẫn chạy, và admin không bao giờ biết mình đang dùng model hạng
    hai. Rẻ: mỗi lời gọi vài chục token.
    """
    _nap_env()
    cfg = llmClient.nap()
    print(f"Chế độ hiện tại: {che_do(cfg)[0]} ({che_do(cfg)[1]})\n")
    hoi = [{"role": "user", "content": "Trả lời đúng một từ: ok"}]
    for ten, nha_cfg in (cfg.get("nha") or {}).items():
        gan = "miễn phí" if nha_cfg.get("mienPhi") else "TÍNH TIỀN"
        # Nhà chạy bằng CLI (Claude gói Pro) KHÔNG hỏi thử theo mặc định: đo
        # thật 27/08, một lời gọi bốn token vẫn ghi 11.790 token cache và
        # $0,071 — phần lớn là prompt nền của chính CLI. Một lệnh "kiểm cho
        # yên tâm" mà đắt hơn cả việc thật thì admin sẽ thôi chạy nó.
        if llmClient.la_cli(nha_cfg):
            if not args.ca_claude:
                print(f"  {ten:12} CLI gói Pro — bỏ qua (thêm --ca-claude để "
                      f"hỏi thật, tốn hạn mức)")
                continue
            gan = "gói Pro"
        if llmClient.thieu_khoa(nha_cfg):
            print(f"  {ten:12} {gan:9} — chưa có {nha_cfg['khoaEnv']} trong ops/.env")
            continue
        for model in nha_cfg.get("model") or []:
            try:
                kq = llmClient.goi(nha=ten, model=model, messages=hoi, cfg=cfg,
                                   timeout=args.timeout, max_tokens=8)
                print(f"  {ten:12} {gan:9} — {model}: SỐNG "
                      f"({kq['giay']}s, {kq['tienVnd']}đ)")
            except llmClient.LLMError as exc:
                print(f"  {ten:12} {gan:9} — {model}: HỎNG · {exc}")
    return 0


def cmd_trang_thai(args) -> int:
    # Phải nạp .env, nếu không lệnh này báo "thiếu khoá" cho những nhà ĐANG CÓ
    # khoá — một câu trả lời sai theo hướng doạ, và admin sẽ đi tìm một lỗi
    # không tồn tại.
    _nap_env()
    cfg = llmClient.nap()
    cd, nguon = che_do(cfg)
    nao_cfg = cfg.get("nao") or {}
    print(f"Chế độ: {cd}  ({nguon})")
    print("  claude = chỉ dùng claude -p · tu = claude trước, hỏng thì chuyển "
          "· phu = chỉ dùng não phụ")
    muc = nao_cfg.get("riengTu") or "canTrong"
    print(f"Riêng tư khi chạy não phụ: {muc}")
    print("  dayDu = gửi cả hồ sơ và bức tranh · canTrong = không gửi hai thứ "
          "đó · toiThieu = chỉ danh mục")
    print("  Xem tận mắt: python3 ops/nao.py xem-goi \"câu muốn thử\"")
    print(f"\nChuỗi não phụ (trần {nao_cfg.get('soLuotToiDa')} lượt, "
          f"{'CHO PHÉP trả tiền' if nao_cfg.get('chapNhanTraTien') else 'chỉ nhà miễn phí'}):")
    for b in nao_cfg.get("chuoi") or []:
        nha_cfg = (cfg.get("nha") or {}).get(b.get("nha")) or {}
        vi = ("thiếu " + str(nha_cfg.get("khoaEnv"))
              if llmClient.thieu_khoa(nha_cfg) else "có khoá")
        print(f"  · {b.get('nha')}/{b.get('model')} — {vi}")
    hd = cfg.get("hoiDong") or {}
    print("\nHội đồng — thành viên bàn, chủ toạ chốt:")
    san = 0
    for tv in hd.get("thanhVien") or []:
        nha_cfg = (cfg.get("nha") or {}).get(tv.get("nha")) or {}
        if not nha_cfg:
            vi = "models.yaml chưa khai nhà này"
        elif llmClient.thieu_khoa(nha_cfg):
            vi = "THIẾU " + str(nha_cfg.get("khoaEnv"))
        elif not nha_cfg.get("mienPhi") and not hd.get("chapNhanTraTien"):
            vi = "nhà tính tiền, đang bị loại"
        else:
            vi = "sẵn sàng"
            san += 1
        print(f"  · {tv.get('nha')}/{tv.get('model')} — {vi}")
    for nhan, ghe in (("chủ toạ", hd.get("chuToa")),
                      ("dự bị ", hd.get("chuToaDuPhong"))):
        if ghe:
            print(f"  {nhan}: {ghe.get('nha')}/{ghe.get('model')}")
    if san < 2:
        print("  ⚠ Chưa đủ hai thành viên có khoá — hội đồng sẽ báo failed.")
    return 0


def cmd_xem_goi(args) -> int:
    """In ĐÚNG thứ sẽ được gửi ra nhà ngoài, mà KHÔNG gửi đi đâu cả.

    Câu hỏi "gửi API bên ngoài thì có rò rỉ gì không" chỉ trả lời tử tế được
    bằng cách mở gói tin ra xem. Trả lời bằng lời hứa — "chỉ gửi câu hỏi thôi"
    — là loại câu nghe rất yên tâm và không kiểm được, đúng thứ dự án này cấm.

    Chạy 0đ, không chạm mạng: nó dựng prompt y hệt đường thật rồi dừng lại.
    """
    _nap_env()
    sys.path.insert(0, HERE)
    import gateway

    muc = gateway._muc_rieng_tu()
    conn = gateway.ceo_store()
    brief = gateway.brief_block(conn)
    sach, _ = gateway.so_tay_block(args.cau, False)
    conn.close()
    loi = open(gateway.SYSTEM_PROMPT, encoding="utf-8").read()
    danh_muc = gateway.danh_muc_block()
    ho_so = gateway.profile_block()

    khoi = [("lõi SYSTEM.md", loi, True),
            ("danh mục company", danh_muc, True),
            ("hồ sơ admin (đời tư)", ho_so, muc == "dayDu"),
            ("bức tranh hiện tại (ví, kế hoạch, lịch)", brief, muc == "dayDu"),
            ("sổ tay theo việc", sach, muc != "toiThieu"),
            ("câu đại ca đang hỏi", args.cau, True)]

    print(f"Chế độ riêng tư: {muc} — {gateway.RIENG_TU[muc]}\n")
    print(f"{'KHỐI':42} {'KÝ TỰ':>8}  GỬI ĐI?")
    tong = 0
    for ten, noi, gui in khoi:
        if gui:
            tong += len(noi or "")
        print(f"{ten:42} {len(noi or ''):>8}  {'CÓ' if gui else 'không'}")
    print(f"{'TỔNG THẬT SỰ RA KHỎI MÁY':42} {tong:>8}")
    if muc != "toiThieu":
        print("\n(Cộng thêm vài tin nhắn gần đây của phiên đang mở, và mọi kết "
              "quả company trả về trong lượt — chúng đi ngược vào prompt để "
              "model đọc.)")
    if args.day_du:
        for ten, noi, gui in khoi:
            if gui and noi:
                print(f"\n{'=' * 20} {ten} {'=' * 20}\n{noi}")
    else:
        print("\nThêm --day-du để in nguyên văn từng khối.")
    return 0


def cmd_dat(args) -> int:
    print("Đã đặt chế độ não:", dat_che_do(args.che_do))
    return 0


def cmd_hoi(args) -> int:
    """Hỏi thẳng chuỗi não phụ một câu, KHÔNG có công cụ nào. Để soi chất lượng
    model, không phải để làm việc thật — làm việc thật thì phải qua CEO."""
    _nap_env()
    cfg = llmClient.nap()
    kq = llmClient.goi_chuoi(
        cfg.get("nao", {}).get("chuoi") or [], cfg=cfg,
        chi_mien_phi=not cfg.get("nao", {}).get("chapNhanTraTien"),
        messages=[{"role": "user", "content": args.cau}], timeout=args.timeout)
    print(f"[{kq['nha']}/{kq['model']} · {kq['giay']}s · {kq['tienVnd']}đ]\n")
    print(kq["chu"])
    for t in kq.get("daThu") or []:
        print(f"\n(đã thử trước đó: {t['nha']}/{t['model']} — {t['loi']})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="bộ não của CEO")
    sub = ap.add_subparsers(dest="lenh", required=True)

    p = sub.add_parser("kiem", help="hỏi thật từng nhà xem model còn sống không")
    p.add_argument("--timeout", type=int, default=30)
    p.add_argument("--ca-claude", action="store_true",
                   help="hỏi thử cả Claude — tốn hạn mức gói Pro")
    p.set_defaults(func=cmd_kiem)

    p = sub.add_parser("trang-thai", help="đang chạy bộ não nào, chuỗi ra sao")
    p.set_defaults(func=cmd_trang_thai)

    p = sub.add_parser("dat", help="đổi chế độ: claude | tu | phu")
    p.add_argument("che_do", choices=CHE_DO)
    p.set_defaults(func=cmd_dat)

    p = sub.add_parser("xem-goi", help="in thứ SẼ gửi ra nhà ngoài, không gửi")
    p.add_argument("cau")
    p.add_argument("--day-du", action="store_true", help="in nguyên văn")
    p.set_defaults(func=cmd_xem_goi)

    p = sub.add_parser("hoi", help="hỏi thử chuỗi não phụ một câu")
    p.add_argument("cau")
    p.add_argument("--timeout", type=int, default=60)
    p.set_defaults(func=cmd_hoi)

    args = ap.parse_args()
    try:
        return args.func(args)
    except llmClient.LLMError as exc:
        print(f"Hỏng: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
