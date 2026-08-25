#!/usr/bin/env python3
"""ngoaiNguCompany — sổ câu ngoại ngữ admin tự thêm trong lúc chat với CEO.

Hợp đồng (C1): taskEnvelope trên stdin → companyResult trên stdout.

Nguồn sự thật là CAU-CUA-TOI.yaml ngay cạnh thư mục này — file người đọc được,
sửa tay được. Không có bản sao trong sqlite: admin sửa một chữ phiên âm trên
file thì company đọc đúng cái đã sửa, không bao giờ có hai bản lệch nhau (cùng
lý lẽ với PROFILE.md của profileCompany).

store.sqlite chỉ giữ nhật ký công việc (C3).

VIỆC CEO PHẢI LÀM TRƯỚC KHI GỌI: dịch sang Anh/Trung, bính âm, và phiên âm chữ
Việt. Company này không biết một chữ ngoại ngữ nào — nó chỉ giữ đúng cái nhận
được và từ chối thứ trông không giống cái nó chờ.
"""
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "lib"))
import db  # noqa: E402

STORE = os.path.join(HERE, "..", "store.sqlite")
SO = os.path.join(HERE, "..", "CAU-CUA-TOI.yaml")
TZ = timezone(timedelta(hours=7))

DANG_HOC, THUOC = "đang học", "thuộc"

# Trần cứng cho số câu ĐANG HỌC. Không phải để giữ file nhỏ — file vài trăm
# dòng thì nhẹ tênh — mà vì tin học mỗi sáng chỉ chở được vài câu, nên sổ càng
# dày thì một câu càng lâu mới quay lại. Xem chú thích ở NGUONG_LOANG.
MAX_DANG_HOC = 200

# Trên ngưỡng này thì company tự nói ra chuyện vòng ôn đang giãn: 4 câu/ngày,
# 40 câu đang học nghĩa là mỗi câu mười ngày mới gặp lại một lần — thưa hơn thế
# thì không còn là học, chỉ là lướt qua. Nói ra ở summary chứ KHÔNG chặn: chặn
# thì admin mất câu vừa nghĩ ra, mà đó mới là thứ quý.
NGUONG_LOANG = 40

DAU_CAU = re.compile(r"[^\w\s]", re.UNICODE)

HEADER = """# Câu ngoại ngữ do đại ca tự thêm — sổ riêng của ngoaiNguCompany.
#
# Sinh và đọc bởi companies/ngoaiNguCompany. Sửa tay thoải mái: company đọc lại
# đúng file này, không giữ bản sao ở đâu khác. Giữ nguyên tên trường thì thôi.
#
# Khác registry/giaotrinh-ngoaingu.yaml ở NGUỒN: giáo trình là 12 bài soạn sẵn,
# file này là câu đời sống đưa tới. Hai bên không ai ghi đè ai.
#
# trangThai: "đang học" (còn được gửi mỗi sáng) | "thuộc" (nằm lại để tra).
"""


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


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
        """
    )
    return conn


# ───────────────────────── sổ trên đĩa ─────────────────────────

def doc_so() -> dict:
    """Đọc sổ. Thiếu file là bình thường (chưa thêm câu nào); hỏng thì KHÔNG.

    O10 — file có mà đọc không ra thì phải kêu lên. Trả sổ rỗng ở đây nghĩa là
    lần `themCau` kế tiếp ghi đè một file admin đã gõ tay vào, và không dòng lỗi
    nào nói rằng vừa mất cái gì.
    """
    if not os.path.exists(SO):
        return {"soDaCap": 0, "cau": []}
    with open(SO, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if data is None:
        return {"soDaCap": 0, "cau": []}
    if not isinstance(data, dict) or not isinstance(data.get("cau") or [], list):
        raise ValueError(
            "CAU-CUA-TOI.yaml không đúng hình (phải là object có khoá `cau`). "
            "Em không dám ghi đè lên nó.")
    data.setdefault("cau", [])
    data.setdefault("soDaCap", 0)
    return data


def ghi_so(data: dict) -> None:
    """Ghi nguyên tử: viết file tạm rồi đổi tên đè lên.

    Ghi thẳng thì một lần hết đĩa hoặc một lần tiến trình chết giữa chừng để
    lại file cụt — và sổ cụt trông y hệt sổ thật, chỉ thiếu mấy câu cuối.
    """
    tmp = SO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(HEADER + "\n")
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False,
                       default_flow_style=False, width=1000)
    os.replace(tmp, SO)


def gon(s: str) -> str:
    """Chuẩn hoá để SO SÁNH — bỏ dấu câu, gộp khoảng trắng, thường hoá."""
    s = unicodedata.normalize("NFC", (s or "")).strip().lower()
    return " ".join(DAU_CAU.sub(" ", s).split())


def dang_hoc(data: dict) -> list:
    return [c for c in data["cau"] if c.get("trangThai", DANG_HOC) == DANG_HOC]


def tim(data: dict, cau_id: str) -> dict:
    for c in data["cau"]:
        if c.get("id") == cau_id:
            return c
    # D6 — không thấy thì BÁO, đừng lặng lẽ tạo mới hay bỏ qua.
    raise ValueError(f"Không có câu nào mang id '{cau_id}' trong sổ. "
                     "Gọi dsCau để lấy id đúng đã.")


# ───────────────────────── năng lực ─────────────────────────

def them_cau(inp):
    data = doc_so()

    # Trùng thì DỪNG, không ghi bản thứ hai. Admin gặp lại một tình huống rồi
    # nhắc lại cùng câu là chuyện thường; hai dòng giống nhau trong sổ chỉ làm
    # tin buổi sáng lặp và đẩy câu khác ra ngoài vòng ôn.
    moi_vi, moi_en = gon(inp["vi"]), gon(inp["en"])
    for c in data["cau"]:
        if gon(c.get("vi")) == moi_vi or gon(c.get("en")) == moi_en:
            tt = c.get("trangThai", DANG_HOC)
            raise ValueError(
                f'Câu này đã có trong sổ rồi ({c["id"]}: "{c["vi"]}" — {tt}). '
                + ("Muốn ôn lại thì bảo em, em chuyển về đang học."
                   if tt == THUOC else "Em không ghi thêm bản thứ hai."))

    con = len(dang_hoc(data))
    if con >= MAX_DANG_HOC:
        raise ValueError(
            f"Sổ đang có {con} câu chưa thuộc — chạm trần {MAX_DANG_HOC}. "
            "Đánh dấu thuộc bớt vài câu rồi thêm tiếp.")

    data["soDaCap"] = int(data.get("soDaCap") or 0) + 1
    cau = {
        "id": f'c{data["soDaCap"]}',
        "vi": inp["vi"].strip(),
        "en": inp["en"].strip(),
        "enDoc": inp["enDoc"].strip(),
        "zh": inp["zh"].strip(),
        "py": inp["py"].strip(),
        "zhDoc": inp["zhDoc"].strip(),
        "nhom": inp["nhom"],
        "trangThai": DANG_HOC,
        "themLuc": today(),
    }
    if inp.get("khi"):
        cau["khi"] = inp["khi"].strip()
    data["cau"].append(cau)
    ghi_so(data)

    con += 1
    them = ""
    if con >= NGUONG_LOANG:
        them = (f" Sổ đang có {con} câu chưa thuộc, mỗi sáng gửi được 4 — "
                "một câu phải chờ hơn mười ngày mới quay lại. Đánh dấu thuộc "
                "bớt thì vòng ôn dày lên.")
    return (
        {"cauId": cau["id"], "vi": cau["vi"], "nhom": cau["nhom"], "tong": con},
        f'Đã thêm vào sổ ({cau["id"]}, nhóm {cau["nhom"]}): {cau["vi"]} · '
        f'{cau["en"]} · {cau["zh"]}. Sáng mai nó có trong bài học.' + them,
        [{"type": "ngoaiNgu.themCau", "target": cau["id"],
          "idempotencyKey": f'them|{moi_vi}',
          "reversible": True}],
    )


def ds_cau(inp):
    data = doc_so()
    muon = inp.get("trangThai") or DANG_HOC
    cau = data["cau"] if muon == "tất cả" else \
        [c for c in data["cau"] if c.get("trangThai", DANG_HOC) == muon]
    if inp.get("nhom"):
        cau = [c for c in cau if c.get("nhom") == inp["nhom"]]

    tong = len(cau)
    cau = cau[:inp.get("gioiHan", 200)]
    ra = [{"cauId": c.get("id", ""), "vi": c.get("vi", ""), "en": c.get("en", ""),
           "enDoc": c.get("enDoc", ""), "zh": c.get("zh", ""), "py": c.get("py", ""),
           "zhDoc": c.get("zhDoc", ""), "nhom": c.get("nhom", "khác"),
           "khi": c.get("khi", ""), "trangThai": c.get("trangThai", DANG_HOC),
           "themLuc": c.get("themLuc", "")}
          for c in cau]

    nhom: dict = {}
    for c in ra:
        nhom[c["nhom"]] = nhom.get(c["nhom"], 0) + 1
    trai = ", ".join(f"{k} {v}" for k, v in sorted(nhom.items(), key=lambda kv: -kv[1]))
    return (
        {"cau": ra, "count": len(ra)},
        (f"{len(ra)} câu ({muon})" + (f" · {trai}" if trai else "")
         + (f" — sổ có {tong}, đã cắt bớt" if tong > len(ra) else "")),
        [],
    )


def danh_dau_thuoc(inp):
    data = doc_so()
    c = tim(data, inp["cauId"])
    # D7 — đối chiếu trước khi đổi. Lệch một chi tiết là dừng.
    if gon(c.get("vi")) != gon(inp["vi"]):
        raise ValueError(f'Không khớp: {inp["cauId"]} là "{c.get("vi")}", '
                         f'không phải "{inp["vi"]}". Em không đánh dấu.')
    if c.get("trangThai") == THUOC:
        raise ValueError(f'Câu "{c["vi"]}" đã đánh dấu thuộc từ '
                         f'{c.get("thuocLuc", "trước đó")} rồi.')
    c["trangThai"] = THUOC
    c["thuocLuc"] = today()
    ghi_so(data)
    con = len(dang_hoc(data))
    return (
        {"cauId": c["id"], "vi": c["vi"], "conLai": con},
        f'Đã đánh dấu thuộc: "{c["vi"]}". Nó thôi xuất hiện trong tin học, '
        f"vẫn nằm trong sổ. Còn {con} câu đang học.",
        [{"type": "ngoaiNgu.danhDauThuoc", "target": c["id"],
          "idempotencyKey": f'thuoc|{c["id"]}',
          "reversible": True, "previousValue": DANG_HOC}],
    )


def xoa_cau(inp):
    data = doc_so()
    c = tim(data, inp["cauId"])
    if gon(c.get("vi")) != gon(inp["vi"]):
        raise ValueError(f'Không khớp: {inp["cauId"]} là "{c.get("vi")}", '
                         f'không phải "{inp["vi"]}". Em không xoá.')
    # D5 — chép lại nguyên câu vừa mất. File không có thùng rác, nên dòng này
    # trong sổ backOffice là bản sao duy nhất còn lại.
    truoc = json.dumps(c, ensure_ascii=False)
    data["cau"] = [x for x in data["cau"] if x.get("id") != c["id"]]
    ghi_so(data)
    con = len(dang_hoc(data))
    return (
        {"cauId": c["id"], "vi": c["vi"], "conLai": con},
        f'Đã xoá khỏi sổ: "{c["vi"]}" ({c["id"]}). Còn {con} câu đang học.',
        [{"type": "ngoaiNgu.xoaCau", "target": c["id"],
          "idempotencyKey": f'xoa|{c["id"]}',
          "reversible": False, "previousValue": truoc}],
    )


HANDLERS = {"themCau": them_cau, "dsCau": ds_cau,
            "danhDauThuoc": danh_dau_thuoc, "xoaCau": xoa_cau}


def main() -> int:
    started = time.time()
    env = json.load(sys.stdin)
    task_id, trace_id = env["taskId"], env["traceId"]
    cap, inp = env["capability"], env["input"]
    dry_run = env.get("policy", {}).get("dryRun", False)

    result = {"taskId": task_id, "traceId": trace_id, "status": "failed",
              "output": None, "summary": "", "sideEffects": [], "error": None}

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
            raise ValueError(f"ngoaiNguCompany không có năng lực '{cap}'")

        if dry_run:  # W2
            preview = json.dumps(inp, ensure_ascii=False)[:200]
            result.update(status="ok", output=None,
                          summary=f"[dryRun] Sẽ chạy {cap} với {preview}")
        else:
            output, summary, side_effects = handler(inp)
            result.update(status="ok", output=output, summary=summary,
                          sideEffects=side_effects)

    except ValueError as exc:
        result.update(status="needsInput", error=str(exc), summary=str(exc))
    except yaml.YAMLError as exc:
        result.update(status="failed", error=f"YAMLError: {exc}",
                      summary="CAU-CUA-TOI.yaml đang hỏng cú pháp — em không "
                              "đọc nổi sổ câu, nên chưa làm gì cả.")
    except Exception as exc:  # O3
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}",
                      summary=f"ngoaiNguCompany hỏng khi chạy {cap}.")

    duration = int((time.time() - started) * 1000)
    result["usage"] = {"steps": 1, "durationMs": duration, "costUsd": 0.0}

    conn.execute(
        "UPDATE taskLog SET status=?, summary=?, finishedAt=?, durationMs=?, costUsd=? "
        "WHERE taskId=?",
        (result["status"], result["summary"], now_utc(), duration, 0.0, task_id),
    )
    conn.execute(
        "INSERT INTO eventLog (taskId, traceId, eventType, payloadJson, createdAt) "
        "VALUES (?,?,?,?,?)",
        (task_id, trace_id, f"capability.{cap}",
         json.dumps({"status": result["status"]}, ensure_ascii=False), now_utc()),
    )
    conn.commit()
    conn.close()

    json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
