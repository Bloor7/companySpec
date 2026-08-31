#!/usr/bin/env python3
"""hoiDongCompany — hỏi nhiều model cùng một câu, rồi để một model khác chốt.

Hợp đồng (C1): taskEnvelope trên stdin → companyResult trên stdout. Giống hệt
mọi company khác, dù bên trong nó nói chuyện với ba bốn nhà cung cấp cùng lúc.

VÌ SAO KHÔNG PHẢI MỘT MODEL GIỎI HƠN: một model trả lời một câu hỏi có đánh đổi
thì bao giờ cũng ra một câu trôi chảy và tự tin — kể cả khi nó bỏ sót nguyên
một mặt của vấn đề. Cái nó bỏ sót thì chính nó không thấy, hỏi lại lần nữa cũng
không thấy, vì cùng một model đọc cùng một câu sẽ đi lại cùng một lối. Model
KHÁC NHÀ, luyện trên mớ chữ khác, thì trượt ở chỗ khác. Chỗ hai bên trượt khác
nhau chính là chỗ đáng đọc.

NÊN THÀNH VIÊN PHẢI KHÁC NHÀ, không chỉ khác tên model. Ba model cùng một họ
đồng thuận với nhau không phải là ba bằng chứng, chỉ là một bằng chứng vọng lại
ba lần. Danh sách thành viên nằm ở registry/models.yaml.

GIẤU TÊN KHI ĐƯA CHO CHỦ TOẠ. Chủ toạ đọc "Ý kiến A / B / C" chứ không đọc tên
nhà: biết bản nào của model to nhất thì nó nghiêng theo bản đó, và cuộc họp chỉ
còn là một cách tốn kém để hỏi model to.

CHỮ Ở ĐÂY LÀ DỮ LIỆU, KHÔNG PHẢI SỰ THẬT (P2). Hội đồng không tra web, không
đọc sổ của admin, không nhìn thấy hệ thống này. Nó nghĩ, và nó có thể nghĩ sai
một cách rất thuyết phục.
"""
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
COMPANY = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(COMPANY, "..", "..", "lib"))
import db  # noqa: E402
import llmClient  # noqa: E402

STORE = os.path.join(COMPANY, "store.sqlite")

# Timeout MỘT lời gọi của thành viên. Phải nhỏ hơn HẲN maxDurationSec vì một
# lượt có tới ba chặng nối nhau: vòng 1 → vòng 2 → chủ toạ. Trong mỗi chặng thì
# các thành viên chạy song song, nên chặng dài bằng người chậm nhất.
GIAY_MOI_LOI_GOI = 60

# Ghế chủ toạ được cấp NHIỀU HƠN HẲN, vì ghế đó thường là Claude chạy qua CLI —
# nó phải khởi động cả một tiến trình node rồi mới bắt đầu nghĩ, khác hẳn một
# lời gọi HTTP. Đo thật 2026-08-27: để chung mức 60 giây thì chủ toạ Claude bị
# cắt giữa chừng và cuộc họp rơi xuống ghế dự bị — mất đúng thứ đáng giá nhất
# (khả năng lọc căn cứ của model mạnh nhất) trong khi mọi ý kiến đã lấy về xong
# và đã trả tiền.
GIAY_CHU_TOA = 180

TEN = ("A", "B", "C", "D")

# LUẬT CĂN CỨ — phần quan trọng nhất của cả company này.
#
# Một model trả lời câu hỏi chiến lược sẽ tuôn ra số liệu rất trôi chảy: "kênh
# mới cần 90 ngày để thoát sandbox", "tỉ lệ giữ chân dưới 30% thì YouTube bóp".
# Nghe như tri thức, thật ra là văn mẫu — và ba model cùng tuôn một kiểu thì
# admin lại càng tin. Đó đúng là kiểu hỏng mà hội đồng KHÔNG được phép có: nó
# biến ba lần đoán thành một lần "đồng thuận".
#
# Nên hợp đồng ở đây là: SỰ THẬT chỉ đến từ khối DỮ KIỆN mà CEO cấp (CEO tra
# bằng searchCompany rồi đưa sang). Mọi thứ khác phải tự gắn nhãn [CHƯA KIỂM].
# Model có thể lờ luật này — nên còn một lớp nữa bằng CODE, xem `_so_khong_nguon`.
LUAT_CAN_CU = (
    "LUẬT CĂN CỨ, không được phá:\n"
    "· Bạn KHÔNG tra được web, KHÔNG đọc được sổ sách của người hỏi. Thứ duy "
    "nhất được coi là sự thật là khối DỮ KIỆN bên dưới (nếu có).\n"
    "· Mọi câu có SỐ LIỆU, mốc thời gian, tên sản phẩm, chính sách, hay sự "
    "kiện — mà không nằm trong DỮ KIỆN — phải mở đầu bằng đúng chữ "
    "[CHƯA KIỂM]. Không có ngoại lệ, kể cả khi bạn rất chắc.\n"
    "· TUYỆT ĐỐI không bịa nguồn, không bịa con số, không bịa tên nghiên cứu. "
    "Thà viết \"không biết\" — người hỏi cần biết chỗ nào chắc chỗ nào không "
    "hơn là cần một câu nghe hay.\n"
    "· Nếu để chốt đúng thì phải tra thêm gì, hãy nói RA ĐIỀU CẦN TRA, cụ thể "
    "tới mức người ta gõ vào ô tìm kiếm được.\n"
    "· Suy luận từ nguyên lý chung thì được, và KHÔNG cần nhãn — nhưng phải "
    "nói rõ nó là suy luận, đừng khoác cho nó dáng dấp số liệu."
)

DAN_THANH_VIEN = (
    "Bạn là một thành viên hội đồng cố vấn cho một người. Bạn đang được hỏi "
    "cùng một câu với vài model khác, và sẽ có người đọc cả mấy bản trả lời "
    "rồi so.\n"
    "· Trả lời NGẮN: nhiều nhất 8 câu, văn xuôi thuần TIẾNG VIỆT. KHÔNG dùng "
    "Markdown — không dấu sao, không backtick, không tiêu đề, không bảng.\n"
    "· Nói thẳng bạn CHỌN gì và VÌ SAO. Đừng liệt kê hết mọi khả năng rồi để "
    "người đọc tự quyết — đó là cách né việc.\n"
    "· Nói ra điều bạn KHÔNG CHẮC và cái giá phải trả nếu bạn sai. Phần này "
    "quan trọng hơn phần bạn chắc.\n\n" + LUAT_CAN_CU
)

DAN_CHU_TOA = (
    "Bạn là chủ toạ. Bạn KHÔNG đưa ý kiến riêng — bạn đọc các ý kiến rồi rút "
    "ra kết luận từ chúng.\n"
    "· Điều quan trọng nhất là tìm cho ra chỗ các ý kiến NÓI KHÁC NHAU, kể cả "
    "khi khác nhau ngấm ngầm. Đừng làm mượt cho hoà cả làng.\n"
    "· Việc thứ hai: LỌC RÁC. Khẳng định nào không có trong DỮ KIỆN thì không "
    "được nâng lên thành căn cứ, dù mấy ý kiến cùng nói. Nhiều model cùng nói "
    "một con số KHÔNG làm con số đó thành thật — chúng học từ cùng một mớ chữ "
    "nên sai giống nhau là chuyện thường.\n"
    "· Kết luận phải là một khuyến nghị CỤ THỂ, không phải bản tóm tắt, và "
    "phải đứng vững kể cả khi bỏ hết những khẳng định chưa kiểm.\n"
    "· Viết TIẾNG VIỆT, văn xuôi thuần, không Markdown.\n\n" + LUAT_CAN_CU
)


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect() -> sqlite3.Connection:
    conn = db.connect(STORE)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS taskLog (
          taskId TEXT PRIMARY KEY, traceId TEXT NOT NULL, capability TEXT NOT NULL,
          inputHash TEXT NOT NULL, status TEXT NOT NULL, summary TEXT,
          startedAt TEXT NOT NULL, finishedAt TEXT, durationMs INTEGER, costUsd REAL
        );
        CREATE TABLE IF NOT EXISTS eventLog (
          eventId INTEGER PRIMARY KEY AUTOINCREMENT, taskId TEXT, traceId TEXT NOT NULL,
          eventType TEXT NOT NULL, payloadJson TEXT, createdAt TEXT NOT NULL
        );
        -- Giữ lại từng phiên họp: ai nói gì, chốt ra sao. Đây là thứ để sau này
        -- trả lời được câu "hội đồng có hơn một model không" bằng dữ liệu chứ
        -- không bằng cảm giác.
        CREATE TABLE IF NOT EXISTS phienHop (
          id INTEGER PRIMARY KEY AUTOINCREMENT, taskId TEXT, cauHoi TEXT,
          soVong INTEGER, thanhVienJson TEXT, ketLuan TEXT, tienVnd REAL,
          createdAt TEXT NOT NULL
        );
        """
    )
    return conn


def _loc_thanh_vien(cfg: dict, so: int) -> list:
    """Bỏ thành viên không dùng được, và nói RÕ vì sao bỏ.

    Ba lý do bỏ: chưa có khoá, models.yaml không khai nhà đó, hoặc nhà tính
    tiền mà admin chưa cho phép. Không nuốt im lặng: "hội đồng ba người" mà
    thật ra chỉ một người trả lời là đúng kiểu kết quả rỗng đội lốt thành công
    (O10) — CEO sẽ nói với admin rằng "ba model đều đồng ý".
    """
    hd = cfg.get("hoiDong") or {}
    cho_tra_tien = bool(hd.get("chapNhanTraTien"))
    nhan, bo = [], []
    for tv in (hd.get("thanhVien") or []):
        nha_cfg = (cfg.get("nha") or {}).get(tv.get("nha")) or {}
        ten = f'{tv.get("nha")}/{tv.get("model")}'
        if not nha_cfg:
            bo.append(f"{ten}: models.yaml không khai nhà này")
        elif llmClient.thieu_khoa(nha_cfg):
            bo.append(f"{ten}: chưa có {nha_cfg['khoaEnv']}")
        elif not nha_cfg.get("mienPhi") and not cho_tra_tien:
            bo.append(f"{ten}: nhà tính tiền, hoiDong.chapNhanTraTien đang tắt")
        else:
            nhan.append(tv)
        if len(nhan) >= so:
            break
    return nhan, bo


def _cau_hoi_day_du(inp: dict) -> str:
    """Câu hỏi + bối cảnh + DỮ KIỆN. Ba khối tách bạch, cố ý.

    `boiCanh` là ràng buộc của người hỏi (thời gian, sức người) — đúng vì họ
    nói thế. `duKien` là sự thật đã TRA ĐƯỢC, do CEO lấy từ searchCompany hoặc
    từ sổ của admin rồi đưa sang. Trộn hai thứ vào một khối thì model không
    phân biệt được đâu là điều đã kiểm, mà đó chính là ranh giới cả company
    này dựng lên để giữ.
    """
    cau = inp["cauHoi"]
    if inp.get("boiCanh"):
        cau += "\n\nBối cảnh người hỏi đưa thêm:\n" + inp["boiCanh"]
    du = [str(d).strip() for d in (inp.get("duKien") or []) if str(d).strip()]
    if du:
        cau += ("\n\nDỮ KIỆN đã tra được — CHỈ những dòng này mới được coi là "
                "sự thật:\n" + "\n".join(f"- {d}" for d in du))
    else:
        # Nói RA sự vắng mặt. Không nói thì model mặc định coi trí nhớ của nó
        # là dữ kiện — đúng thứ ta đang chặn.
        cau += ("\n\nKHÔNG có dữ kiện nào được cấp cho cuộc họp này. Nghĩa là "
                "bạn không có gì đã kiểm chứng trong tay: hãy nói rõ điều đó, "
                "và gắn nhãn [CHƯA KIỂM] cho mọi khẳng định về đời thực.")
    return cau


# Số đáng soi: từ hai chữ số trở lên, hoặc có phần trăm / dấu phân cách / đuôi
# tiền. "3 bước" thì bỏ qua — nó là cách nói, không phải một khẳng định về đời
# thực. "90 ngày", "30%", "1.500 view" thì soi.
SO_DANG_SOI = re.compile(r"\d[\d.,]*\s*%|\d[\d.,]{1,}|\b\d{2,}\b")


def _so_khong_nguon(ket_luan: str, nguon: str) -> list:
    """Số nào trong kết luận mà KHÔNG có trong dữ kiện đầu vào.

    Lớp hàng rào thứ hai, và là lớp DUY NHẤT không phụ thuộc vào việc model có
    chịu nghe lời hay không. Luật [CHƯA KIỂM] ở trên nằm trong prompt, mà prompt
    thì model phá lúc nào cũng được và không ai biết — y như bài học "hàng rào
    giả hại hơn không có hàng rào".

    Cố ý THÔ: nó chỉ so chuỗi số, không hiểu ngữ nghĩa. Nên nó sẽ bắt nhầm vài
    con số vô hại, và bắt sót những câu bịa không có số. Nhưng thứ nó bắt đúng
    lại là thứ nguy nhất — con số cụ thể là cái admin nhớ và đem đi quyết định.
    Thà thừa một dòng "cần kiểm" còn hơn để một con số bịa đi thẳng vào đầu.
    """
    co = set()
    for m in SO_DANG_SOI.finditer(nguon or ""):
        co.add(m.group().replace(" ", ""))
    thieu = []
    for m in SO_DANG_SOI.finditer(ket_luan or ""):
        s = m.group().replace(" ", "")
        if s not in co and s not in thieu:
            thieu.append(s)
    return thieu[:8]


def _chu_cua(kq: dict) -> str:
    return (kq.get("chu") or "").strip()


def _vong_hai(cfg, thanh_vien, y_kien, cau, timeout, vai=None) -> list:
    """Mỗi thành viên đọc ý kiến của NGƯỜI KHÁC rồi được sửa lại ý mình.

    Đây mới là chỗ "thảo luận" khác với "ba câu trả lời rời nhau". Vòng 1 chỉ
    cho ba bản độc lập; vòng 2 mới thấy ai chịu đổi ý và ai giữ nguyên — mà một
    ý kiến được giữ nguyên SAU KHI đọc phản bác thì đáng tin hơn hẳn cùng ý
    kiến đó lúc chưa ai phản bác.
    """
    viec, tin = [], []
    for i, tv in enumerate(thanh_vien):
        cua_nguoi_khac = "\n\n".join(
            f"Ý kiến {TEN[j]}:\n{y}" for j, y in enumerate(y_kien) if j != i and y)
        if not cua_nguoi_khac:
            continue
        viec.append(tv)
        tin.append([
            # Giữ NGUYÊN góc nhìn của ghế sang vòng hai. Bỏ nó đi thì vòng
            # phản biện kéo mọi người về giọng trung dung — đúng cái mà việc
            # chia vai vừa mới chữa xong ở vòng một.
            {"role": "system",
             "content": _dan_thanh_vien((vai or [None] * len(thanh_vien))[i])},
            {"role": "user", "content": cau},
            {"role": "assistant", "content": y_kien[i]},
            {"role": "user", "content":
             "Đây là ý kiến của các thành viên khác cho cùng câu hỏi:\n\n"
             + cua_nguoi_khac
             + "\n\nLàm hai việc, theo đúng thứ tự:\n"
               "1. SOI CĂN CỨ trước. Chỉ ra từng khẳng định của họ mà không có "
               "trong DỮ KIỆN — con số, mốc thời gian, chính sách nền tảng, "
               "\"nghiên cứu cho thấy\". Gọi thẳng: \"Ý kiến B nói X, cái đó "
               "không có trong dữ kiện\". Đây là việc quan trọng nhất của bạn "
               "ở vòng này; đừng bỏ qua vì nể.\n"
               "2. Rồi viết lại ý mình, nhiều nhất 8 câu. Họ chỉ ra chỗ bạn "
               "sai hoặc bỏ sót thì SỬA và nói rõ đã đổi ý chỗ nào; vẫn giữ "
               "nguyên thì nói vì sao lập luận của họ chưa làm bạn đổi ý.\n"
               "Đừng nhắc lại ý họ cho dài."}])
    if not viec:
        return y_kien
    # SONG SONG, mỗi người một bộ messages riêng. Bản đầu gọi tuần tự và đó là
    # một cái bẫy ngân sách: 4 thành viên × 60 giây = 240 giây cho riêng vòng
    # này, trong khi cả năng lực chỉ có ngần ấy. Nó sẽ không hỏng lúc thử với
    # 2 người, mà hỏng đúng hôm admin mời đủ 4 người vào họp.
    ket = llmClient.song_song(
        [{"nha": tv["nha"], "model": tv["model"], "messages": m}
         for tv, m in zip(viec, tin)], cfg=cfg, timeout=timeout)
    moi = list(y_kien)
    for tv, k in zip(viec, ket):
        _cong(k)
        # Vòng 2 hỏng thì GIỮ NGUYÊN ý kiến vòng 1 của người đó. Mất một lần
        # phản biện, không mất cả tiếng nói.
        if k.get("ok") and _chu_cua(k):
            moi[thanh_vien.index(tv)] = _chu_cua(k)
    return moi


# Sổ chi chạy suốt một lượt. HAI Ô, không phải một: `vnd` là tiền trừ thẻ,
# `usd` là hạn mức gói Pro mà chủ toạ Claude tiêu. Gộp chung thì đến lúc đối
# chiếu hoá đơn không tách ra được — mà đối chiếu hoá đơn chính là lý do sổ
# chiTieuNgoai tồn tại.
_SO = {"vnd": 0.0, "usd": 0.0}


def _cong(kq: dict) -> None:
    _SO["vnd"] += kq.get("tienVnd") or 0
    _SO["usd"] += kq.get("costUsd") or 0


def _doc_ket_luan(chu: str) -> tuple:
    """Đọc JSON chủ toạ trả về. Đọc không được thì DÙNG NGUYÊN CHỮ, đừng vứt.

    Model nhỏ trả JSON hỏng là chuyện thường. Ném lỗi ở đây là vứt cả cuộc họp
    vừa chạy xong chỉ vì cái vỏ sai — trong khi ruột (câu kết luận) vẫn dùng
    được. Mất phần tách đồng thuận/bất đồng thì nói thẳng là mất, chứ đừng bịa
    ra hai danh sách rỗng trông như "không ai bất đồng".
    """
    d = llmClient.boc_json(chu)     # phần bóc rào ```json nằm chung ở lib
    if d and d.get("ketLuan"):
        return (str(d["ketLuan"]),
                [str(x) for x in (d.get("dongThuan") or [])][:6],
                [str(x) for x in (d.get("batDong") or [])][:6],
                [str(x) for x in (d.get("chuaKiemChung") or [])][:8])
    return (chu.strip(), [], [], [])


SETTINGS = os.path.join(COMPANY, "settings.json")
VAI_FILE = os.path.join(COMPANY, "vai.yaml")


def _nap_vai() -> dict:
    """Đọc vai.yaml. Hỏng thì NÉM — đừng lặng lẽ họp mà không có vai.

    O10: một cuộc họp thiếu vai trông y hệt một cuộc họp có vai, chỉ khác là
    bốn model lại trả lời na ná nhau — mà đó chính là thứ vai sinh ra để chữa.
    Không ai phát hiện được bằng mắt, nên phải hỏng TO ngay tại đây.
    """
    import yaml
    with open(VAI_FILE, encoding="utf-8") as fh:
        d = yaml.safe_load(fh) or {}
    if not d.get("vai"):
        raise EnvironmentError(f"{VAI_FILE} không khai vai nào.")
    return d


def _gan_vai(so_ghe: int, inp: dict) -> list:
    """Gán góc nhìn cho từng ghế. Trả list cùng thứ tự với thành viên.

    Lời gọi nói rõ `vai` thì theo; không nói thì lấy `macDinh`. Tên vai lạ thì
    ném ValueError → dispatcher trả `needsInput`, CEO sửa rồi gọi lại. Lặng lẽ
    bỏ qua tên sai nghĩa là ghế đó thành ghế trắng và cuộc họp yếu đi một góc
    mà không ai biết.
    """
    d = _nap_vai()
    ten = list(inp.get("vai") or d.get("macDinh") or [])
    la = [t for t in ten if t not in d["vai"]]
    if la:
        raise ValueError(
            f"không có vai {', '.join(la)}. Đang có: {', '.join(d['vai'])}.")
    ra = []
    for i in range(so_ghe):
        # Ít vai hơn ghế thì xoay vòng: thà hai người cùng một góc còn hơn một
        # người không có góc nào.
        v = d["vai"][ten[i % len(ten)]] if ten else None
        ra.append(v)
    return ra


def _dan_thanh_vien(vai: dict) -> str:
    """Lời dặn cho MỘT thành viên, có kèm góc nhìn của ghế đó."""
    if not vai:
        return DAN_THANH_VIEN
    return (DAN_THANH_VIEN + "\n\n## Ghế của bạn: " + str(vai.get("ten") or "")
            + "\n\nHội đồng cố ý xếp mỗi ghế một góc nhìn khác nhau, để không "
              "ai bỏ sót cùng một chỗ. Đây là góc của bạn — bám lấy nó, đừng "
              "trả lời cân đối cho đủ mọi mặt; mặt khác đã có người lo.\n\n"
            + str(vai.get("khung") or "")
            # RANH GIỚI phải nói ra. Model được luyện để trả lời cho cân đối,
            # nên không cấm thì nó tự nói nốt phần của ghế khác — và bốn ghế
            # lại thành bốn bản na ná, tức là mất sạch lý do chia vai.
            + (f"\nRANH GIỚI của ghế này: {vai['ranhGioi']} Lấn sang phần của "
               "ghế khác là làm hỏng cuộc họp, không phải làm kỹ hơn."
               if vai.get("ranhGioi") else ""))

YEU_CAU_CHOT = (
    "Trả về ĐÚNG một khối JSON, không viết gì ngoài nó:\n"
    '{"ketLuan": "khuyến nghị cụ thể, 3-6 câu", '
    '"dongThuan": ["điểm mọi ý kiến cùng nói"], '
    '"batDong": ["chỗ các ý kiến khác nhau, ghi rõ bên nào nói gì"], '
    '"chuaKiemChung": ["khẳng định được nêu ra mà KHÔNG có trong DỮ KIỆN — '
    'ghi lại nguyên văn khẳng định đó, và nói cần tra gì để kiểm"]}\n'
    "`chuaKiemChung` là phần bắt buộc nghĩ kỹ: để trống chỉ khi thật sự mọi "
    "khẳng định đều tra được trong DỮ KIỆN. Một cuộc họp không có dữ kiện nào "
    "mà `chuaKiemChung` rỗng thì chắc chắn bạn đã bỏ sót.")


def _chot(cfg: dict, cau: str, ban: str, so_y: int, timeout: int) -> tuple:
    """Chủ toạ đọc các ý kiến GIẤU TÊN rồi chốt. Ghế này có người dự bị.

    Ghế chính là Claude (gói Pro). Nó là bộ não mạnh nhất trong nhà, nhưng cũng
    là thứ hay câm nhất — hết hạn mức là hết. Không có ghế dự bị thì đúng vào
    lúc Pro cạn, cả cuộc họp vừa chạy xong bị vứt chỉ vì thiếu người chốt, dù
    bốn ý kiến đã nằm sẵn trong tay.

    Trả về (kết_luận, đồng_thuận, bất_đồng, ai_chốt). `ai_chốt` phải đi ra tới
    tận CEO: một kết luận do model 8B chốt và một kết luận do Claude chốt không
    đáng tin ngang nhau, và admin có quyền biết mình đang đọc loại nào.
    """
    hd = cfg.get("hoiDong") or {}
    ghe = [g for g in (hd.get("chuToa"), hd.get("chuToaDuPhong")) if g]
    tin = [{"role": "system", "content": DAN_CHU_TOA},
           {"role": "user", "content":
            f"Câu hỏi:\n{cau}\n\n{so_y} ý kiến thu được:\n\n{ban}\n\n"
            + YEU_CAU_CHOT}]
    loi = []
    for i, g in enumerate(ghe):
        try:
            kq = llmClient.goi(nha=g["nha"], model=g["model"], cfg=cfg,
                               messages=tin, timeout=timeout, max_tokens=1200,
                               settings=SETTINGS)
            _cong(kq)
            k, d, b, cks = _doc_ket_luan(_chu_cua(kq))
            ai = f'{g["nha"]}/{g["model"]}'
            if i:      # phải nói ra là ghế chính đã hỏng, đừng lặng lẽ thay người
                k += f"\n\n(Chủ toạ chính không chốt được — {loi[0][:120]})"
            return k, d, b, cks, ai
        except llmClient.LLMError as exc:
            loi.append(str(exc))
    # Không ai chốt được thì ĐƯA THẲNG các ý kiến cho CEO, đừng vứt cuộc họp.
    # Kết quả xấu nhưng thật: admin vẫn đọc được bốn góc nhìn, chỉ là chưa ai
    # gom lại. Vứt đi mới là mất trắng thứ đã chạy xong.
    return ("Chưa ai chốt được (" + " · ".join(loi)[:200] + "). Các ý kiến thu "
            "được:\n\n" + ban, [], [],
            ["Không ai chốt được nên KHÔNG ai lọc căn cứ — coi mọi khẳng định "
             "trong các ý kiến dưới đây là chưa kiểm."], "")


def hoi_y(inp: dict, deadline_sec: int) -> tuple:
    _SO["vnd"], _SO["usd"] = 0.0, 0.0
    cfg = llmClient.nap()
    so = int(inp.get("soThanhVien") or 3)
    so_vong = int(inp.get("soVong") or 1)
    thanh_vien, bo = _loc_thanh_vien(cfg, so)

    if len(thanh_vien) < 2:
        raise EnvironmentError(
            "Không đủ hai thành viên để họp. " + (" · ".join(bo) or "chưa khai "
            "thành viên nào trong registry/models.yaml") + ". Lấy khoá miễn phí "
            "ở console.groq.com hoặc cloud.cerebras.ai rồi thêm vào ops/.env.")

    cau = _cau_hoi_day_du(inp)
    # Chia ngân sách theo ĐỒNG HỒ THẬT, không chia đều từ đầu: vòng 1 có thể
    # xong trong 3 giây và lúc đó phần thừa phải chảy về cho chủ toạ, chứ không
    # bốc hơi. Đây cũng là cách duy nhất giữ đúng luật "timeout phải nhỏ hơn
    # HẲN ngân sách" khi số thành viên và số vòng đều đổi được.
    het_luc = time.monotonic() + deadline_sec

    def con_lai() -> int:
        return int(het_luc - time.monotonic())

    timeout = max(20, min(GIAY_MOI_LOI_GOI, con_lai() // (1 + so_vong)))

    # ── vòng 1: hỏi song song, mỗi ghế một GÓC NHÌN riêng ──
    vai = _gan_vai(len(thanh_vien), inp)
    ket = llmClient.song_song(
        [{"nha": t["nha"], "model": t["model"],
          "messages": [{"role": "system", "content": _dan_thanh_vien(v)},
                       {"role": "user", "content": cau}]}
         for t, v in zip(thanh_vien, vai)],
        cfg=cfg, timeout=timeout, messages=[])
    y_kien, ai_noi = [], []
    for t, v, k in zip(thanh_vien, vai, ket):
        _cong(k)
        y_kien.append(_chu_cua(k) if k.get("ok") else "")
        ai_noi.append({"nha": t["nha"], "model": t["model"],
                       "vai": (v or {}).get("ten", ""),
                       "traLoi": bool(k.get("ok") and _chu_cua(k)),
                       "loi": "" if k.get("ok") else str(k.get("loi") or "")[:200]})

    co_mat = [i for i, y in enumerate(y_kien) if y]
    if len(co_mat) < 2:
        raise RuntimeError(
            "Chỉ có " + str(len(co_mat)) + "/" + str(len(thanh_vien))
            + " thành viên trả lời được nên không thành cuộc họp: "
            + " · ".join(a["loi"] for a in ai_noi if a["loi"])[:400])

    # ── vòng 2: đọc của nhau rồi sửa ý mình ──
    if so_vong >= 2:
        y_kien = _vong_hai(cfg, thanh_vien, y_kien, cau, timeout, vai)

    # ── chủ toạ chốt, đọc bản GIẤU TÊN ──
    #
    # Giấu NHÀ nhưng KHÔNG giấu ghế: chủ toạ cần biết mấy ý kiến trái nhau là
    # do được xếp góc khác nhau, chứ không phải do ai đó lạc đề. Không nói thì
    # nó sẽ coi phần "soi mặt trái" là bi quan thái quá rồi làm nhẹ đi — tức là
    # xoá đúng phần đắt nhất của cuộc họp.
    ban = "\n\n".join(
        f"Ý kiến {TEN[i]}"
        + (f" (ghế: {ai_noi[i]['vai']})" if ai_noi[i].get("vai") else "")
        + f":\n{y}" for i, y in enumerate(y_kien) if y)
    # Chủ toạ ăn TOÀN BỘ thời gian còn lại (chừa 10 giây để trả kết quả), tối
    # đa GIAY_CHU_TOA. Nó là chặng cuối nên không phải nhường ai nữa.
    ket_luan, dong_thuan, bat_dong, chua_kiem, ai_chot = _chot(
        cfg, cau, ban, len(co_mat), max(45, min(GIAY_CHU_TOA, con_lai() - 10)))

    # LỚP HÀNG RÀO BẰNG CODE. Chủ toạ có thể quên, có thể lười, có thể tự thấy
    # mình chắc chắn — mấy chuyện đó không ai canh được từ trong prompt. Con số
    # thì canh được: số nào trong kết luận mà không có trong dữ kiện đầu vào
    # thì nêu tên nó ra.
    la = _so_khong_nguon(ket_luan, cau)
    if la:
        chua_kiem.append("Số chưa có nguồn trong dữ kiện: " + ", ".join(la)
                         + " — đừng dùng mấy con số này để quyết.")
    if not (inp.get("duKien") or []):
        chua_kiem.append("Cuộc họp chạy KHÔNG có dữ kiện nào được cấp: kết "
                         "luận chỉ là suy luận, chưa dựa trên thông tin đã tra.")

    thieu = f" ({len(thanh_vien) - len(co_mat)} thành viên vắng)" if len(co_mat) < len(thanh_vien) else ""
    tom = (ket_luan[:900] + thieu
           + (f"\n\nChốt bởi: {ai_chot}." if ai_chot else "")
           + ("\n\nBất đồng: " + " | ".join(bat_dong)[:500] if bat_dong else
              "\n\n(Không tách được phần bất đồng — đọc kỹ kết luận.)")
           # CHƯA KIỂM phải vào tận `summary`, vì đó là thứ CEO đọc kỹ nhất và
           # là thứ admin sẽ nghe. Nằm im trong `output` thì rất dễ bị bỏ qua
           # đúng lúc nó cần được nói ra.
           + ("\n\nCHƯA KIỂM CHỨNG: " + " | ".join(chua_kiem)[:600]
              if chua_kiem else ""))
    return (
        {"ketLuan": ket_luan[:6000], "dongThuan": dong_thuan,
         "batDong": bat_dong, "thanhVien": ai_noi, "soVong": so_vong,
         "chuToa": ai_chot, "chuaKiemChung": chua_kiem[:10]},
        tom,
        [],                                   # chỉ nghĩ, không đổi gì (read)
        # `paidVnd` là tiền TRỪ THẺ; hạn mức Pro mà chủ toạ Claude tiêu đi
        # đường `costUsd` riêng, vào cột costUsd của taskLog như mọi company
        # chạy phiên Claude khác.
        {"paidVnd": round(_SO["vnd"], 2), "costUsd": round(_SO["usd"], 6),
         "paidProvider": ", ".join(sorted({t["nha"] for t in thanh_vien}))},
    )


HANDLERS = {"hoiY": hoi_y}


def main() -> int:
    started = time.time()
    env = json.load(sys.stdin)
    task_id, trace_id = env["taskId"], env["traceId"]
    cap, inp = env["capability"], env["input"]
    dry_run = env.get("policy", {}).get("dryRun", False)

    result = {"taskId": task_id, "traceId": trace_id, "status": "failed",
              "output": None, "summary": "", "sideEffects": [], "error": None}
    tien_khai = {}

    conn = connect()
    conn.execute(
        "INSERT OR REPLACE INTO taskLog (taskId, traceId, capability, inputHash, "
        "status, startedAt) VALUES (?,?,?,?,?,?)",
        (task_id, trace_id, cap, env.get("_inputHash", ""), "running", now_utc()),
    )
    conn.commit()

    try:
        handler = HANDLERS.get(cap)
        if handler is None:
            raise ValueError(f"hoiDongCompany không có năng lực '{cap}'")

        if dry_run:  # W2
            result.update(status="ok", output=None,
                          summary="[dryRun] Sẽ họp hội đồng về: "
                                  + str(inp.get("cauHoi"))[:150])
        else:
            # Chừa 15 giây trước deadline để còn kịp trả kết quả về. Hết giờ mà
            # chưa kịp trả thì dispatcher chỉ thấy một tiến trình chết — mất
            # luôn cuộc họp vừa chạy xong.
            dl = datetime.strptime(env["budget"]["deadlineAt"], "%Y-%m-%dT%H:%M:%SZ")
            con = (dl.replace(tzinfo=timezone.utc)
                   - datetime.now(timezone.utc)).total_seconds()
            output, summary, side_effects, tien = handler(inp, max(40, int(con) - 15))
            result.update(status="ok", output=output, summary=summary,
                          sideEffects=side_effects)
            tien_khai.update(tien)
            conn.execute(
                "INSERT INTO phienHop (taskId, cauHoi, soVong, thanhVienJson, "
                "ketLuan, tienVnd, createdAt) VALUES (?,?,?,?,?,?,?)",
                (task_id, str(inp.get("cauHoi"))[:1000], output["soVong"],
                 json.dumps(output["thanhVien"], ensure_ascii=False),
                 output["ketLuan"][:4000], tien.get("paidVnd") or 0, now_utc()))

    except ValueError as exc:
        result.update(status="needsInput", error=str(exc), summary=str(exc))
    except (EnvironmentError, RuntimeError, llmClient.LLMError) as exc:
        result.update(status="failed", error=str(exc), summary=str(exc))
    except Exception as exc:  # O3
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}",
                      summary=f"hoiDongCompany hỏng khi chạy {cap}: {exc}")

    duration = int((time.time() - started) * 1000)
    # HAI cột chi, cố ý tách: `costUsd` là hạn mức gói Pro (chủ toạ Claude tiêu,
    # 0 khi ghế đó do model miễn phí ngồi), `paidVnd` là tiền trừ thẻ mà
    # dispatcher chép sang sổ chiTieuNgoai. Gộp lại là mất đường đối chiếu.
    result["usage"] = {"steps": 1, "durationMs": duration, "costUsd": 0.0,
                       **{k: v for k, v in tien_khai.items() if v is not None}}
    conn.execute(
        "UPDATE taskLog SET status=?, summary=?, finishedAt=?, durationMs=? "
        "WHERE taskId=?",
        (result["status"], result["summary"][:400], now_utc(), duration, task_id),
    )
    conn.execute(
        "INSERT INTO eventLog (taskId, traceId, eventType, payloadJson, createdAt) "
        "VALUES (?,?,?,?,?)",
        (task_id, trace_id, f"{cap}.{result['status']}",
         json.dumps({"status": result["status"]}, ensure_ascii=False), now_utc()),
    )
    conn.commit()
    conn.close()

    json.dump(result, sys.stdout, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
