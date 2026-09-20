#!/usr/bin/env python3
"""Bản đồ mã nguồn — dựng TỪ MÃ, không từ trí nhớ ai cả.

    python3 ops/codemap.py          # bản đồ cho người đọc
    python3 ops/codemap.py --check  # chỉ soát luật, hỏng thì thoát khác 0

VÌ SAO CÓ FILE NÀY: README từng ghi "11 company · 48 năng lực" trong khi thật
là 15 và 56 — con số chép tay thì lặng lẽ cũ đi, và không ai phát hiện cho tới
lúc có người đếm lại. Mọi con số ở đây đếm lại mỗi lần chạy nên không cũ được.

Phần đáng giá nhất là `--check`: nó biến ba luật kiến trúc từ chỗ "phải nhớ"
thành chỗ "chạy một lệnh là biết". Luật nhớ được thì sẽ có ngày quên; luật
chạy được thì không.
"""
import argparse
import ast
import glob
import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Thư mục KHÔNG phải mã của dự án. Bỏ qua trước khi đọc, vì hai lẽ:
#
#   · Báo bừa: mã thư viện người khác không tuân luật kiến trúc của dự án này,
#     và cũng không cần tuân.
#   · Tệ hơn — LÀM HỎNG CẢ BỘ SOÁT. Tập "module nội bộ" được suy ra từ tên file
#     .py có trong cây thư mục; site-packages chứa hàng loạt file trùng tên
#     thư viện chuẩn, nên `json`/`os` bỗng bị coi là module nội bộ và luật P3
#     bắt nhầm cả company viết đúng. Đo được 2026-08-17 khi dựng .venv cho
#     browserCompany: 810KB báo lỗi giả, trong đó có seoCompany hoàn toàn sạch.
BO_QUA = (".venv", ".venv-stt", "venv", "node_modules", "site-packages",
          "__pycache__", "plugin", ".git")


def cac_tep_py() -> dict:
    """Đường dẫn tương đối → tuyệt đối. Bỏ plugin vendor: mã người khác."""
    ra = {}
    for thu_muc, con, tep in os.walk(ROOT):
        con[:] = [c for c in con if c not in BO_QUA]
        for t in tep:
            if t.endswith(".py"):
                p = os.path.join(thu_muc, t)
                ra[os.path.relpath(p, ROOT)] = p
    return ra


#: Thư mục gốc được coi là GÓI. Cần vì `from core.policy import decide` không
#: có module nào tên `core.py` để nhận ra.
GOI_NOI_BO = {"core", "ops", "lib", "companies", "backOffice", "hop",
              "employees", "tests", "gateway", "brains"}

#: Module trong core/ mà company ĐƯỢC PHÉP import. Danh sách này phải ở lại
#: rất ngắn — mỗi cái thêm vào là một sợi dây nối company với Core, và cả điểm
#: của P3 là company không có sợi dây nào ngoài dispatcher.
NGOAI_LE_CORE_CHO_COMPANY = {"brainRunner"}


def phu_thuoc(tep: dict) -> dict:
    """Ai import module nội bộ nào. Đọc bằng AST — grep sẽ dính cả chuỗi và
    comment, mà chuỗi thì không phải phụ thuộc.

    ⚠ SỬA 2026-09-19 — BỘ QUÉT NÀY TỪNG MÙ VỚI IMPORT DẠNG GÓI.

    Bản cũ chỉ so tên module PHẲNG (`import db`). Với `from ops import session`
    thì `n.module` là "ops", mà không có file nào tên `ops.py`, nên nó không
    khớp gì cả và cạnh phụ thuộc BIẾN MẤT. `from core.policy import decide`
    cũng vậy.

    Trước đây cả repo dùng import phẳng nên chưa ai gặp. Nhưng hệ quả là luật
    C4.2 (`core/` không được phụ thuộc ra ngoài) treo trên một bộ quét mù —
    một hàng rào trông như đang canh mà chưa từng nhìn thấy gì. Đúng họ
    "hàng rào giả", phát hiện bằng cách THỬ PHÁ chứ không bằng đọc mã.

    Nay soát cả ba đường: tên gói gốc, mọi đoạn của tên có chấm, và tên được
    lôi ra trong `from X import Y`.
    """
    noi_bo = {os.path.splitext(os.path.basename(p))[0] for p in tep}
    canh = {}
    for rel, p in tep.items():
        try:
            cay = ast.parse(open(p, encoding="utf-8").read())
        except (SyntaxError, OSError):
            continue
        goi = set()

        def nhan(ten: str):
            if ten and (ten in noi_bo or ten in GOI_NOI_BO):
                goi.add(ten)

        for n in ast.walk(cay):
            if isinstance(n, ast.Import):
                for a in n.names:
                    for phan in a.name.split("."):
                        nhan(phan)
                continue
            if isinstance(n, ast.ImportFrom):
                for phan in (n.module or "").split("."):
                    nhan(phan)
                # `from ops import session` — thứ bị lôi ra cũng là phụ thuộc.
                for a in n.names:
                    nhan(a.name)
        canh[rel] = goi
    return canh


def tang_cua(rel: str) -> str:
    if rel.startswith("companies/"):
        return "company"
    if rel.startswith("lib/"):
        return "lib"
    if rel.startswith("core/"):
        return "core"
    if rel.startswith("brains/"):
        return "brains"
    if rel.startswith("gateway/"):
        return "gateway"
    if rel.startswith("ops/"):
        return "ops"
    if rel.startswith("backOffice/"):
        return "backOffice"
    return "khác"


def cong_ty() -> list:
    """(companyId, số năng lực) — đọc từ manifest, đó mới là nguồn sự thật."""
    ra = []
    d = os.path.join(ROOT, "companies")
    for cid in sorted(os.listdir(d)):
        p = os.path.join(d, cid, "companySpec.yaml")
        if not os.path.isfile(p):
            continue
        try:
            spec = yaml.safe_load(open(p, encoding="utf-8")) or {}
        except Exception:
            continue
        ra.append((cid, len(spec.get("capabilities") or [])))
    return ra


def _hop_dong() -> dict:
    """companyId → {tên năng lực: inputSchema}. Manifest là nguồn sự thật."""
    ra = {}
    d = os.path.join(ROOT, "companies")
    for cid in sorted(os.listdir(d)):
        p = os.path.join(d, cid, "companySpec.yaml")
        if not os.path.isfile(p):
            continue
        try:
            spec = yaml.safe_load(open(p, encoding="utf-8")) or {}
        except Exception:
            continue
        ra[cid] = {c["name"]: (c.get("inputSchema") or {})
                   for c in (spec.get("capabilities") or []) if c.get("name")}
    return ra


def _soat_mot_loi_goi(cid: str, cap: str, khoa: set, hd: dict, o_dau: str,
                      soat_thieu: bool = True) -> list:
    """Đối chiếu MỘT lời gọi với hợp đồng. Trả danh sách chỗ phạm.

    `soat_thieu=False` cho nơi chỉ khai MỘT PHẦN input — ca thử nêu vài trường
    cần kiểm chứ không dựng lời gọi đầy đủ. Ở đó "thiếu trường bắt buộc" không
    phải lỗi, còn "trường không khai trong manifest" thì vẫn là lỗi.
    """
    if cid not in hd:
        return [f"C2.1 · {o_dau}: không có company '{cid}'"]
    if cap not in hd[cid]:
        co = ", ".join(sorted(hd[cid])) or "(không có năng lực nào)"
        return [f"C2.2 · {o_dau}: '{cid}' không có năng lực '{cap}'. Có: {co}"]
    isc = hd[cid][cap]
    props = set((isc.get("properties") or {}).keys())
    pham = []
    if isc.get("additionalProperties") is False:
        la = khoa - props
        if la:
            pham.append(f"C2.3 · {o_dau}: {cid}.{cap} không khai trường "
                        f"{', '.join(sorted(la))} — có: {', '.join(sorted(props)) or '(không trường nào)'}")
    thieu = (set(isc.get("required") or []) - khoa) if soat_thieu else set()
    if thieu:
        pham.append(f"C2.3 · {o_dau}: {cid}.{cap} thiếu trường bắt buộc "
                    f"{', '.join(sorted(thieu))}")
    return pham


def soat_ten_truong(tep: dict) -> list:
    """Tên trường ở nơi GỌI phải khớp `inputSchema` trong manifest.

    VÌ SAO CÓ LUẬT NÀY: đây là con bug tốn công nhất của dự án. Báo cáo tiền
    cuối ngày gọi sổ thu/chi bằng `from` trong khi hợp đồng khai `tuNgay`;
    dispatcher trả `rejected`, code nuốt lỗi bằng `or {}`, và hệ in
    "thu 0đ · chi 0đ" mỗi tối SUỐT NHIỀU TUẦN mà không ai nghi — vì số 0 trông
    y hệt "hôm nay không tiêu gì". Hỏi lại CEO thì số đúng, nên càng khó ngờ.

    Chỉ soát được lời gọi VIẾT CỨNG (tên company, tên năng lực và dict đều là
    hằng). Lời gọi dựng động thì bỏ qua — soát nửa vời còn tệ hơn không soát,
    vì nó tạo cảm giác đã kiểm rồi. CEO gọi động nên không nằm trong tầm này;
    bù lại CEO được đưa sẵn danh mục kèm tên trường mỗi lượt (gateway).
    """
    hd = _hop_dong()
    pham = []

    # (1) Lời gọi trong Python: hàm nào có dạng f("<x>Company", "<cap>", {...})
    for rel, p in sorted(tep.items()):
        try:
            nguon = open(p, encoding="utf-8").read()
            cay = ast.parse(nguon)
        except (SyntaxError, OSError):
            continue
        dong_nguon = nguon.splitlines()
        for n in ast.walk(cay):
            if not isinstance(n, ast.Call) or len(n.args) < 3:
                continue

            # CỬA THOÁT CÓ TÊN, cùng kiểu với `# sql-an-toan:`.
            #
            # Bộ diễn tập CỐ Ý gọi một năng lực không tồn tại để chứng minh nó
            # bị chặn (bài `deny`). Không có cửa thoát thì hoặc phải bỏ cả
            # `tests/` khỏi tầm soát — và mất luôn phần soát thật — hoặc phải
            # giấu cái tên đi, mà giấu thì người đọc sau không hiểu vì sao.
            #
            # Đánh dấu thì ý định đọc được TỪ MẶT CHỮ, và cửa thoát hẹp đúng
            # một dòng thay vì cả một thư mục.
            quanh = dong_nguon[max(0, n.lineno - 3):n.lineno]
            if any("ten-sai-co-y" in d for d in quanh):
                continue
            a0, a1, a2 = n.args[0], n.args[1], n.args[2]
            if not (isinstance(a0, ast.Constant) and isinstance(a0.value, str)
                    and a0.value.endswith("Company")
                    and isinstance(a1, ast.Constant) and isinstance(a1.value, str)
                    and isinstance(a2, ast.Dict)):
                continue
            # Dict có khoá động (**kwargs hoặc khoá không phải hằng) thì không
            # kết luận được — bỏ qua thay vì báo bừa.
            if any(k is None or not isinstance(k, ast.Constant) for k in a2.keys):
                continue
            khoa = {k.value for k in a2.keys}
            pham += _soat_mot_loi_goi(a0.value, a1.value, khoa, hd,
                                      f"{rel}:{n.lineno}")

    # (2) Lịch định kỳ: registry/schedules.yaml khai input tĩnh. Cron chạy lúc
    # admin ngủ, sai ở đây thì không ai thấy cho tới khi đọc báo cáo.
    lich = os.path.join(ROOT, "registry", "schedules.yaml")
    if os.path.isfile(lich):
        try:
            ds = (yaml.safe_load(open(lich, encoding="utf-8")) or {}).get("schedules") or []
        except Exception:
            ds = []
        for s in ds:
            if not s.get("companyId") or not s.get("capability"):
                continue
            pham += _soat_mot_loi_goi(
                s["companyId"], s["capability"], set((s.get("input") or {}).keys()),
                hd, f"schedules.yaml:{s.get('scheduleId', '?')}")

    # (3) Ca thử: tests/evals/cases.yaml khai tên company, tên năng lực và tên
    # trường mong đợi — cùng loại chữ viết cứng, nên cùng một kiểu mục ruỗng.
    # Đổi tên một trường trong manifest mà quên sửa ca thử thì ca đó lặng lẽ
    # TRƯỢT MÃI, và tệ hơn: bộ kiểm mất uy tín nên người ta bắt đầu bỏ qua nó.
    # ⚠ `tests/evals/`, không phải `ops/evals/` — §36 dời thư mục ca thử mà
    # quên dòng này. Nó có `if os.path.isfile(...)` bao ngoài nên KHÔNG lỗi:
    # bộ soát chỉ lặng lẽ bỏ qua toàn bộ ca thử, tức là một hàng rào tự tắt mà
    # vẫn in ra "SOÁT LUẬT: sạch". Cùng họ với "hàng rào giả".
    ca_thu = os.path.join(ROOT, "tests", "evals", "cases.yaml")
    if os.path.isfile(ca_thu):
        try:
            ds = (yaml.safe_load(open(ca_thu, encoding="utf-8")) or {}).get("cases") or []
        except Exception:
            ds = []
        for ca in ds:
            o_dau = f"cases.yaml:{ca.get('id', '?')}"
            # Ca nhiều lượt (thêm 18/08) để `phaiGoi` BÊN TRONG từng lượt. Bản
            # soát cũ chỉ đọc tầng gốc nên ca nhiều lượt lọt ra ngoài vùng phủ
            # mà không ai hay — và lọt ngay lần đầu dùng: ca
            # `thieu-gio-thi-hoi-roi-moi-dat` viết `tenSuKien` trong khi
            # manifest khai `ten`, đúng con bug mà hàng rào này sinh ra để bắt.
            # Mở rộng một định dạng thì phải kéo hàng rào theo, nếu không thì
            # định dạng mới lặng lẽ thành vùng không ai kiểm.
            mong_ca = list(ca.get("phaiGoi") or [])
            cam_ca = list(ca.get("khongDuocGoi") or [])
            for lu in ca.get("luot") or []:
                mong_ca += list(lu.get("phaiGoi") or [])
                cam_ca += list(lu.get("khongDuocGoi") or [])
            for mong in mong_ca:
                cid, _, cap = (mong.get("goi") or "").partition(".")
                if cid and cap:
                    pham += _soat_mot_loi_goi(
                        cid, cap, set((mong.get("truong") or {}).keys()), hd,
                        o_dau, soat_thieu=False)
            for cam in cam_ca:
                cid, _, cap = cam.partition(".")
                if cid and cap:
                    pham += _soat_mot_loi_goi(cid, cap, set(), hd, o_dau,
                                              soat_thieu=False)
    return pham


# Tên secret cho biết company đang cầm chìa khoá một dịch vụ TÍNH TIỀN THẬT.
# Danh sách này sẽ cũ đi — thêm nhà cung cấp mới vào đây khi gặp.
API_TRA_TIEN = re.compile(
    r"GEMINI|GOOGLE_AI|VERTEX|OPENAI|ANTHROPIC_API_KEY|REPLICATE|ELEVENLABS|"
    r"RUNWAY|STABILITY|MIDJOURNEY|DEEPGRAM|ASSEMBLYAI|FAL_|TOGETHER_|GROQ|"
    r"HEYGEN|SYNTHESIA|LEONARDO|CLOUDINARY|TWILIO|SENDGRID|STRIPE",
    re.I)


def soat_api_tra_tien() -> list:
    """Company cầm chìa khoá dịch vụ tính tiền thì phải khai `paidApi`.

    VÌ SAO CÓ LUẬT NÀY: admin bị Google AI Studio trừ 144.000đ mà không thu
    được sản phẩm ưng ý (2026-08). Khoản đó tiêu ngoài hệ, nhưng nó cho thấy
    đúng lỗ hổng sắp mở ra: company đầu tiên dùng Gemini/Veo mà quên khai thì
    sẽ tiêu tiền thật của admin trong im lặng — không nút duyệt, không trần,
    không dòng nào trong sổ.

    Khai `paidApi` là thứ bật cả ba: dispatcher ép hỏi duyệt mỗi lần (không
    whitelist), chặn khi quá trần tháng, và ghi vào sổ `chiTieuNgoai` để đối
    chiếu hoá đơn. Quên khai thì cả ba đều không chạy, và không có gì kêu lên.

    Chỉ soát ở mức company: có ít nhất một năng lực khai `paidApi` thì coi như
    người viết đã ý thức được. Đòi từng năng lực phải khai sẽ báo bừa với những
    năng lực chỉ đọc lại cache.
    """
    pham = []
    for path in sorted(glob.glob(os.path.join(ROOT, "companies", "*", "companySpec.yaml"))):
        try:
            spec = yaml.safe_load(open(path, encoding="utf-8")) or {}
        except Exception:
            continue
        cid = spec.get("companyId") or os.path.basename(os.path.dirname(path))
        chia_khoa = [s for s in (spec.get("secrets") or []) + (spec.get("env") or [])
                     if API_TRA_TIEN.search(str(s))]
        caps = spec.get("capabilities") or []
        co_khai = [c for c in caps if c.get("paidApi")]

        if chia_khoa and not co_khai:
            pham.append(
                f"L8 · {cid}: cầm khoá dịch vụ tính tiền ({', '.join(chia_khoa)}) "
                "nhưng không năng lực nào khai `paidApi` — sẽ tiêu tiền thật mà "
                "không hỏi duyệt, không trần, không vào sổ.")

        # Khai rồi thì phải khai ĐỦ: thiếu giá thì nút duyệt không nói được
        # admin sắp trả bao nhiêu, mà giá chính là thứ họ cần biết để bấm.
        for c in co_khai:
            p = c["paidApi"]
            if not isinstance(p, dict) or not p.get("nhaCungCap"):
                pham.append(f"L8 · {cid}.{c['name']}: `paidApi` thiếu `nhaCungCap`.")
            if not isinstance(p, dict) or not p.get("giaUocVnd"):
                pham.append(f"L8 · {cid}.{c['name']}: `paidApi` thiếu `giaUocVnd` — "
                            "nút duyệt sẽ không nói được admin sắp trả bao nhiêu.")
    return pham


def soat_sql(tep: dict) -> list:
    """Câu SQL không được ghép từ chuỗi động.

    VÌ SAO SOÁT: dữ liệu vào hệ này là chữ admin gõ trên Telegram — có dấu nháy,
    dấu chấm phẩy, dấu gạch, đủ cả. Ghép thẳng vào câu SQL thì một ghi chú
    chứa dấu nháy đủ làm hỏng truy vấn, và trong trường hợp xấu hơn là hỏng
    bảng. Đo 2026-08-16: 136 lời gọi `execute` trong hệ, chỉ 2 chỗ dùng
    f-string và cả hai đều là tên cột/hằng nội bộ — tức là hôm nay hệ SẠCH.
    Luật này giữ cho câu đó còn đúng vào lần thêm mã tiếp theo.

    Cho qua khi phần nội suy là HẰNG viết hoa (BUSY_TIMEOUT_MS…) vì hằng không
    đến từ người dùng. Trường hợp buộc phải ghép động — tên cột, sqlite không
    cho đặt tham số ở vị trí đó — thì đánh dấu `# sql-an-toan: <lý do>` ngay
    trên dòng, và phải chặn bằng danh sách trắng ở nơi gọi.
    """
    pham = []
    for rel, p in sorted(tep.items()):
        try:
            nguon = open(p, encoding="utf-8").read()
            cay = ast.parse(nguon)
        except (SyntaxError, OSError):
            continue
        dong_nguon = nguon.splitlines()
        for n in ast.walk(cay):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr in ("execute", "executemany", "executescript")
                    and n.args and isinstance(n.args[0], ast.JoinedStr)):
                continue
            # Nhìn lên vài dòng: chú thích giải thích lý do thường dài hơn một
            # dòng, và bắt người ta viết cụt lại chỉ để lọt qua bộ soát là sai
            # hướng — cái cần là lý do đọc hiểu được.
            quanh = dong_nguon[max(0, n.lineno - 4):n.lineno]
            if any("sql-an-toan" in d for d in quanh):
                continue
            dong_ = [x for x in n.args[0].values
                     if isinstance(x, ast.FormattedValue)]
            xau = [x for x in dong_
                   if not (isinstance(x.value, ast.Name) and x.value.id.isupper())]
            if xau:
                pham.append(
                    f"SQL · {rel}:{n.lineno}: câu SQL ghép bằng f-string. Giá trị "
                    "phải đi qua tham số '?'; buộc phải ghép tên cột thì ghi "
                    "'# sql-an-toan: <lý do>' ngay trên dòng.")
    return pham


def soat(tep: dict, canh: dict) -> list:
    """Ba luật kiến trúc, soát được bằng code. Trả danh sách chỗ phạm.

    Chỉ soát thứ ĐỌC ĐƯỢC TỪ MÃ. Những luật cần hiểu ý (riskTier khai đúng
    chưa, mô tả năng lực có thật không) thì không nhét vào đây — soát nửa vời
    còn tệ hơn không soát, vì nó tạo cảm giác đã kiểm rồi.
    """
    lib = {os.path.splitext(os.path.basename(p))[0]
           for r, p in tep.items() if tang_cua(r) == "lib"}
    pham = []
    for rel, goi in canh.items():
        tang = tang_cua(rel)
        if tang == "company":
            # P3 — company không gọi company. Dispatcher là đường duy nhất.
            #
            # NGOẠI LỆ CÓ TÊN, không phải lỗ hổng: §36 chuyển `lib/skillRun.py`
            # sang `core/execution/brainRunner.py`, và hai company cần chạy một
            # phiên LLM nhốt kín thì phải với tới nó. Ngoại lệ hẹp tới mức một
            # module — company vẫn KHÔNG chạm được core/policy, core/audit hay
            # bất cứ thứ gì khác trong core/.
            #
            # Ghi tên ở đây thay vì nới luật, để lần sau ai thêm một ngoại lệ
            # nữa thì phải sửa ĐÚNG dòng này và nhìn thấy dòng chú thích này.
            la = goi - lib - NGOAI_LE_CORE_CHO_COMPANY
            if la:
                pham.append(f"P3 · {rel} import ngoài lib/: {', '.join(sorted(la))}")
        elif tang == "lib":
            # C4.1 — thư viện chung không được biết nghiệp vụ. Nó phụ thuộc
            # ngược lên ops/ hay company là vòng tròn, và là dấu hiệu nghiệp vụ
            # đã rò vào chỗ đáng lẽ chỉ có kỹ thuật.
            nguoc = goi - lib
            if nguoc:
                pham.append(f"C4.1 · {rel} phụ thuộc ngược: {', '.join(sorted(nguoc))}")
        elif tang == "core":
            # C4.2 — core/ là LUẬT, không phải người vận chuyển.
            #
            # Nó chỉ được phụ thuộc vào chính nó và lib/. Import `ops.gateway`
            # hay một company vào đây là phá đúng thứ việc tách tầng vừa mua
            # được: quyết định quyền hạn hết tất định, và muốn kiểm một luật
            # lại phải dựng cả một lượt chạy thật.
            #
            # Chiều NGƯỢC LẠI thì được: ops/ gọi vào core/ là đúng hình.
            # Gồm cả tên GÓI `core` — `from core.events import …` là core gọi
            # core, hợp lệ. Bản đầu chỉ lấy basename file, mà basename của
            # `core/events/__init__.py` là `__init__`, nên `core` không có
            # trong tập và mọi import nội bộ dạng gói đều bị báo nhầm.
            trong_core = {os.path.splitext(os.path.basename(p))[0]
                          for r, p in tep.items() if tang_cua(r) == "core"}
            trong_core.add("core")
            la = goi - lib - trong_core
            if la:
                pham.append(f"C4.2 · {rel} phụ thuộc ra ngoài core/+lib/: "
                            f"{', '.join(sorted(la))}")
    # Không ai được import thẳng vào ruột một company.
    for rel, p in tep.items():
        if tang_cua(rel) == "company":
            continue
        try:
            noi = open(p, encoding="utf-8").read()
        except OSError:
            continue
        if "companies/" in noi and "import" in noi:
            for dong in noi.splitlines():
                if dong.strip().startswith(("import ", "from ")) and "companies" in dong:
                    pham.append(f"C2 · {rel} import thẳng vào company: {dong.strip()[:60]}")
    pham += soat_ten_truong(tep)
    pham += soat_sql(tep)
    pham += soat_api_tra_tien()
    return pham


def main() -> int:
    ap = argparse.ArgumentParser(description="Bản đồ mã nguồn companySpec")
    ap.add_argument("--check", action="store_true",
                    help="chỉ soát luật; phạm luật thì thoát mã 1")
    args = ap.parse_args()

    tep = cac_tep_py()
    canh = phu_thuoc(tep)
    pham = soat(tep, canh)

    if args.check:
        for d in pham:
            print("PHẠM LUẬT:", d)
        print(f"{len(tep)} file .py · {len(pham)} chỗ phạm luật")
        return 1 if pham else 0

    cty = cong_ty()
    print(f"companySpec — {len(cty)} company · {sum(n for _, n in cty)} năng lực "
          f"· {len(tep)} file .py")
    print()
    print("TẦNG (mũi tên = được phép phụ thuộc):")
    print("  ops/       →  lib/, backOffice/     điều phối: gateway, dispatcher, scheduler")
    print("  companies/ →  lib/ MÀ THÔI          nghiệp vụ, mỗi company một hộp kín")
    print("  backOffice/→  lib/, ops/approvals   theo dõi và báo cáo, không phải company")
    print("  lib/       →  (không gì cả)         kỹ thuật thuần, không biết nghiệp vụ")
    print()
    print("PHỤ THUỘC THẬT:")
    for rel in sorted(canh):
        if canh[rel]:
            print(f"  {rel:44} → {', '.join(sorted(canh[rel]))}")
    print()
    dem = {}
    for goi in canh.values():
        for m in goi:
            dem[m] = dem.get(m, 0) + 1
    print("BỊ PHỤ THUỘC NHIỀU NHẤT (sửa ở đây là chạm nhiều nơi):")
    for m, n in sorted(dem.items(), key=lambda kv: -kv[1])[:6]:
        print(f"  {m:16} {n} nơi dùng")
    print()
    print("COMPANY:")
    for cid, n in cty:
        print(f"  {cid:20} {n:>2} năng lực")
    print()
    print(f"SOÁT LUẬT: {len(pham)} chỗ phạm" if pham else "SOÁT LUẬT: sạch")
    for d in pham:
        print("  ", d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
