#!/usr/bin/env python3
"""profileCompany — hồ sơ về admin, thứ CEO đọc ở mỗi lượt.

Hợp đồng (C1): taskEnvelope trên stdin → companyResult trên stdout.

Nguồn sự thật là PROFILE.md ngay cạnh file này — một file Markdown người đọc
được. Không có bản sao trong sqlite: admin sửa tay trên file thì company đọc
đúng cái đã sửa, không bao giờ có hai phiên bản lệch nhau.

store.sqlite chỉ giữ nhật ký công việc (C3).
"""
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "lib"))
import db  # noqa: E402

STORE = os.path.join(HERE, "..", "store.sqlite")
PROFILE = os.path.join(HERE, "..", "PROFILE.md")
TZ = timezone(timedelta(hours=7))

NHOM = ["xưng hô", "thói quen", "từ vựng riêng", "bối cảnh", "sở thích",
        "trạng thái"]

# Nhóm BẮT BUỘC phải có ngày hết hạn. "Trạng thái" theo định nghĩa là thứ rồi sẽ
# thôi đúng; ghi nó mà không hẹn ngày rụng là tạo ra một câu sai vĩnh viễn trong
# system prompt của mọi lượt sau.
NHOM_PHAI_CO_HAN = {"trạng thái"}

# Trần cứng. Hồ sơ nằm trong system prompt của MỌI lượt, nên nó phình ra là mọi
# tin nhắn đắt lên và những dòng quan trọng bị loãng giữa đám vụn vặt.
# Đếm điều CÒN HIỆU LỰC, không đếm điều đã hết hạn: điều hết hạn không đi vào
# prompt nên nó không tốn gì, chặn nó là chặn nhầm chỗ.
MAX_FACTS = 30

# Hẹn xa quá thì không còn là hạn dùng, chỉ là một cách viết "vĩnh viễn" khác.
MAX_NGAY_HAN = 365

# Điều đã hết hạn vẫn NẰM LẠI trong file — admin còn nhìn thấy và sửa ngày để
# dùng lại. Nhưng để mãi thì file phình, nên quá ngần này ngày kể từ lúc hết hạn
# thì dọn hẳn, và chỉ dọn bên trong company sở hữu file.
GIU_SAU_HET_HAN = 30

HEADER = """# Hồ sơ admin

<!-- Sinh và đọc bởi profileCompany. Sửa tay thoải mái — company đọc lại đúng
     file này, không giữ bản sao ở đâu khác.
     Mỗi dòng dạng:  - (id) nội dung
                     - (id) [đến YYYY-MM-DD] nội dung   ← chỉ đúng tới ngày đó
     Nội dung ở đây được nạp vào system prompt của CEO ở mỗi lượt — trừ những
     dòng đã quá ngày ghi trong ngoặc vuông, chúng nằm lại đây nhưng CEO không
     còn đọc. Muốn dùng lại thì sửa ngày. -->
"""

# Ngày hết hạn nằm NGAY ĐẦU nội dung chứ không ở cuối: CEO đọc thấy "đến ngày
# nào" trước khi đọc câu, nên không có khoảnh khắc nào nó hiểu câu đó là vĩnh
# viễn. Cuối dòng thì với câu dài bị cắt, dấu hạn là thứ mất trước tiên.
DONG = re.compile(
    r"^\s*-\s*\((p\d+)\)\s*(?:\[đến (\d{4}-\d{2}-\d{2})\]\s*)?(.+?)\s*$")
NGAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hom_nay() -> str:
    """Hôm nay theo giờ VN, dạng YYYY-MM-DD.

    So NGÀY với NGÀY, không so chuỗi thời điểm — cùng cái bẫy đã làm bộ lọc
    ngày của Notion không bao giờ khớp.
    """
    return datetime.now(TZ).strftime("%Y-%m-%d")


def ngay_that(s) -> bool:
    """`s` có phải một ngày CÓ THẬT không — 2026-13-45 đúng dạng nhưng không có thật."""
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


def con_hieu_luc(f: dict, ngay: str) -> bool:
    """Còn đúng tính đến `ngay` không. Tính CẢ ngày hết hạn.

    Ngày không có thật thì coi như CÒN hiệu lực — hỏng về phía giữ dữ liệu của
    admin, đừng tự làm biến mất một dòng vì họ gõ nhầm. Nhưng "giữ lại" không
    được phép là "giữ lại trong im lặng": `list_facts` gọi tên riêng những dòng
    đó ra, vì hậu quả của một ngày hỏng là dòng ấy thành vĩnh viễn — đúng thứ
    hạn dùng sinh ra để chặn.
    """
    han = f.get("hetHan")
    if not han or not ngay_that(han):
        return True
    return han >= ngay


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


# ───────────────────── đọc/ghi PROFILE.md ─────────────────────

def read_facts() -> list:
    """Đọc file thành danh sách. Dòng lạ thì bỏ qua, không làm hỏng cả file.

    Admin sửa tay là chuyện được khuyến khích, nên bộ đọc phải rộng lượng: thiếu
    một dấu ngoặc thì mất đúng dòng đó, không phải mất cả hồ sơ.
    """
    if not os.path.isfile(PROFILE):
        return []
    facts, nhom = [], None
    for line in open(PROFILE, encoding="utf-8"):
        if line.startswith("## "):
            nhom = line[3:].strip()
            continue
        m = DONG.match(line)
        if m and nhom:
            facts.append({"factId": m.group(1), "nhom": nhom,
                          "hetHan": m.group(2), "noiDung": m.group(3)})
    return facts


def mot_dong(f: dict) -> str:
    han = f'[đến {f["hetHan"]}] ' if f.get("hetHan") else ""
    return f'- ({f["factId"]}) {han}{f["noiDung"]}\n'


def qua_han_lau(f: dict, ngay: str) -> bool:
    """Hết hạn từ lâu tới mức dọn đi được."""
    if not f.get("hetHan"):
        return False
    try:
        het = datetime.strptime(f["hetHan"], "%Y-%m-%d")
        moc = datetime.strptime(ngay, "%Y-%m-%d")
    except ValueError:
        return False        # ngày admin gõ tay hỏng — giữ nguyên, đừng tự xoá
    return (moc - het).days > GIU_SAU_HET_HAN


def write_facts(facts: list):
    """Viết lại cả file, nhóm theo chủ đề, giữ thứ tự nhóm cố định.

    Đây cũng là chỗ DUY NHẤT dọn điều đã hết hạn quá lâu — dọn ở đây thì nó nằm
    trong company sở hữu file, đi cùng một lời gọi admin đã duyệt, và có dòng
    trong nhật ký. Gateway đọc file này mỗi lượt nhưng KHÔNG được phép dọn: nó
    chỉ có quyền đọc, và một tiến trình đọc mà lại sửa dữ liệu của company là
    thủng ranh giới nặng hơn nhiều so với vài dòng thừa trong file.
    """
    ngay = hom_nay()
    facts = [f for f in facts if not qua_han_lau(f, ngay)]
    out = [HEADER]
    for nhom in NHOM:
        trong_nhom = [f for f in facts if f["nhom"] == nhom]
        if not trong_nhom:
            continue
        out.append(f"\n## {nhom}\n")
        # Điều còn hiệu lực lên trước, điều đã hết hạn xuống cuối nhóm — admin
        # mở file ra là thấy ngay phần đang có tác dụng.
        for f in sorted(trong_nhom, key=lambda x: not con_hieu_luc(x, ngay)):
            out.append(mot_dong(f))
    # Nhóm lạ (admin tự thêm heading khác) vẫn được giữ, không âm thầm xoá.
    la = [f for f in facts if f["nhom"] not in NHOM]
    for nhom in dict.fromkeys(f["nhom"] for f in la):
        out.append(f"\n## {nhom}\n")
        for f in [x for x in la if x["nhom"] == nhom]:
            out.append(mot_dong(f))
    with open(PROFILE, "w", encoding="utf-8") as fh:
        fh.write("".join(out))


def next_id(facts: list) -> str:
    dung = {int(f["factId"][1:]) for f in facts if f["factId"][1:].isdigit()}
    i = 1
    while i in dung:
        i += 1
    return f"p{i}"


# ───────────────────────── năng lực ─────────────────────────

def list_facts(inp):
    ngay = hom_nay()
    facts = read_facts()
    if inp.get("nhom"):
        facts = [f for f in facts if f["nhom"] == inp["nhom"]]

    # Tách hai loại thay vì lọc im lặng. Điều đã hết hạn KHÔNG còn đi vào prompt
    # nên nó không phải "điều đang nhớ" nữa — nhưng nó vẫn nằm trong file, và
    # CEO cần biết là có, nếu không nó sẽ đề nghị nhớ lại đúng câu đó rồi ngạc
    # nhiên khi bị báo trùng. Nói ra số lượng rẻ hơn nhiều so với để nó đoán.
    con = [f for f in facts if con_hieu_luc(f, ngay)]
    het = [f for f in facts if not con_hieu_luc(f, ngay)]
    if not con and not het:
        return {"facts": [], "count": 0}, "Hồ sơ đang trống.", []

    theo_nhom: dict = {}
    for f in con:
        theo_nhom.setdefault(f["nhom"], []).append(f)
    dong = []
    for nhom, items in theo_nhom.items():
        dong.append(nhom + ":")
        for f in items:
            han = f' (đến {f["hetHan"]})' if f.get("hetHan") else ""
            dong.append(f'  ({f["factId"]}) {f["noiDung"]}{han}')
    if het:
        dong.append("đã hết hạn, em không mang theo nữa — sửa ngày thì dùng lại được:")
        dong += [f'  ({f["factId"]}) [hết {f["hetHan"]}] {f["noiDung"]}' for f in het]

    hong = [f for f in con if f.get("hetHan") and not ngay_that(f["hetHan"])]
    if hong:
        dong.append("NGÀY HỎNG — mấy dòng này đang được mang theo VĨNH VIỄN vì em "
                    "không đọc nổi ngày hết hạn. Báo đại ca sửa lại:")
        dong += [f'  ({f["factId"]}) [đến {f["hetHan"]}?] {f["noiDung"]}' for f in hong]

    return ({"facts": con, "count": len(con)},
            f"{len(con)} điều đang nhớ về đại ca"
            + (f" · {len(het)} điều đã hết hạn" if het else "") + ".\n"
            + "\n".join(dong), [])


def soat_han(nhom: str, het_han, ngay: str):
    """Soát ngày hết hạn. Trả về chuỗi ngày đã chuẩn hoá, hoặc None nếu không hạn.

    Bốn cách sai, và cách nào cũng phải nói ra thành câu CEO sửa được — chứ
    không phải im lặng ghi bừa rồi để admin đọc một câu sai suốt ba tháng.
    """
    if het_han in (None, ""):
        if nhom in NHOM_PHAI_CO_HAN:
            raise ValueError(
                f'Nhóm "{nhom}" bắt buộc có `hetHan` (YYYY-MM-DD). Trạng thái nào '
                "rồi cũng thôi đúng — không hẹn ngày rụng thì nó thành một câu sai "
                "nằm mãi trong đầu em. Không đoán được ngày thì hỏi đại ca.")
        return None

    if not NGAY.match(het_han):
        raise ValueError(f'`hetHan` phải dạng YYYY-MM-DD, không phải "{het_han}".')
    if het_han < ngay:
        raise ValueError(
            f"`hetHan` {het_han} đã qua rồi (hôm nay {ngay}). Ghi vào là ghi một "
            "điều chết ngay lúc sinh.")
    try:
        xa = (datetime.strptime(het_han, "%Y-%m-%d")
              - datetime.strptime(ngay, "%Y-%m-%d")).days
    except ValueError:
        raise ValueError(f'`hetHan` "{het_han}" không phải một ngày có thật.')
    if xa > MAX_NGAY_HAN:
        raise ValueError(
            f"`hetHan` {het_han} xa quá {MAX_NGAY_HAN} ngày. Xa tới mức đó thì nó "
            "không còn là hạn dùng, chỉ là chữ 'vĩnh viễn' viết cách khác — nếu "
            "điều này thật sự luôn đúng thì bỏ `hetHan` và chọn nhóm khác.")
    return het_han


def remember_fact(inp):
    ngay = hom_nay()
    facts = read_facts()
    het_han = soat_han(inp["nhom"], inp.get("hetHan"), ngay)

    noi_dung = " ".join(inp["noiDung"].split())
    trung = next((f for f in facts if f["noiDung"].lower() == noi_dung.lower()), None)

    # Trùng với một điều ĐÃ HẾT HẠN thì gia hạn, đừng báo lỗi. Không có nhánh
    # này thì trạng thái cũ trở thành ngõ cụt: câu vẫn nằm trong file nên bị
    # chặn vì trùng, mà lại không vào prompt nên CEO không thấy — nó sẽ thử đi
    # thử lại đúng câu đó và lần nào cũng bị từ chối, không hiểu vì sao.
    if trung and not con_hieu_luc(trung, ngay):
        cu = trung["hetHan"]
        if het_han is None:
            raise ValueError(
                f'({trung["factId"]}) "{noi_dung}" đã có trong hồ sơ, hết hạn {cu}. '
                "Muốn dùng lại thì gọi lại kèm `hetHan` mới.")
        trung["hetHan"], trung["nhom"] = het_han, inp["nhom"]
        write_facts(facts)
        con = [f for f in facts if con_hieu_luc(f, ngay)]
        return (
            {"factId": trung["factId"], "nhom": inp["nhom"], "noiDung": noi_dung,
             "hetHan": het_han, "tong": len(con)},
            f'Điều này em từng nhớ và đã hết hạn {cu} — nay gia hạn tới {het_han}: '
            f'({trung["factId"]}) {noi_dung}.',
            [{"type": "profile.remember", "target": trung["factId"],
              "idempotencyKey": f"remember|{noi_dung}|{het_han}",
              "reversible": True, "previousValue": f"hetHan|{cu}"}],
        )

    if trung:
        han = f' (đến {trung["hetHan"]})' if trung.get("hetHan") else ""
        raise ValueError(
            f'Đã nhớ rồi: ({trung["factId"]}) {trung["noiDung"]}{han}. Em không ghi trùng.')

    # Đếm điều CÒN HIỆU LỰC. Điều đã hết hạn không đi vào prompt nên nó không
    # tốn gì của lượt nào — chặn theo nó là chặn nhầm thứ trần này sinh ra để chặn.
    dang_co = [f for f in facts if con_hieu_luc(f, ngay)]
    if len(dang_co) >= MAX_FACTS:
        raise ValueError(
            f"Hồ sơ đã có {len(dang_co)} điều đang hiệu lực — trần là {MAX_FACTS}. "
            "Quên bớt một điều cũ trước đã; nhớ quá nhiều thì đắt mỗi lượt và "
            "những điều quan trọng bị loãng.")

    fid = next_id(facts)
    facts.append({"factId": fid, "nhom": inp["nhom"], "noiDung": noi_dung,
                  "hetHan": het_han})
    write_facts(facts)
    tong = len(dang_co) + 1

    mang_theo = (f"Từ giờ tới hết {het_han} em mang theo điều này trong mọi cuộc "
                 f"trò chuyện, qua ngày đó thì tự quên."
                 if het_han else
                 "Từ giờ em mang theo điều này trong mọi cuộc trò chuyện.")
    return (
        {"factId": fid, "nhom": inp["nhom"], "noiDung": noi_dung,
         "hetHan": het_han, "tong": tong},
        f'Đã nhớ ({fid}) {noi_dung} — nhóm "{inp["nhom"]}". {mang_theo} '
        f"Hồ sơ: {tong}/{MAX_FACTS} điều.",
        # D3 — không chạm mạng, nhưng chạm một file quyết định cách CEO hiểu admin
        # ở mọi lượt sau. Việc nào thay đổi hành vi lâu dài thì phải khai.
        [{"type": "profile.remember", "target": fid,
          "idempotencyKey": f"remember|{noi_dung}",
          "reversible": True, "previousValue": None}],
    )


def forget_fact(inp):
    facts = read_facts()
    cur = next((f for f in facts if f["factId"] == inp["factId"]), None)
    if cur is None:
        raise ValueError(f'Không có điều nào mang mã {inp["factId"]}.')

    # Đối chiếu với thứ admin đã nhìn thấy lúc bấm duyệt (D7).
    if cur["noiDung"].strip().lower() != " ".join(inp["noiDung"].split()).lower():
        raise ValueError(
            f'Không khớp: ({cur["factId"]}) đang là "{cur["noiDung"]}", '
            f'không phải "{inp["noiDung"]}". Em không xoá.')

    facts = [f for f in facts if f["factId"] != inp["factId"]]
    write_facts(facts)
    tong = len([f for f in facts if con_hieu_luc(f, hom_nay())])
    return (
        {"factId": cur["factId"], "nhom": cur["nhom"], "noiDung": cur["noiDung"],
         "tong": tong},
        f'Đã quên ({cur["factId"]}) {cur["noiDung"]}. Còn {tong} điều.',
        # D5 — chép lại nội dung cũ, nếu không thì "quên" là không thể hoàn tác.
        # Chép CẢ ngày hết hạn: khôi phục một trạng thái mà mất ngày rụng của nó
        # là khôi phục thành một câu vĩnh viễn, tức là không khôi phục đúng.
        [{"type": "profile.forget", "target": cur["factId"],
          "idempotencyKey": f'forget|{cur["factId"]}',
          "reversible": True,
          "previousValue": f'{cur["nhom"]}|{cur.get("hetHan") or ""}|{cur["noiDung"]}'}],
    )


HANDLERS = {"listFacts": list_facts, "rememberFact": remember_fact,
            "forgetFact": forget_fact}


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
            raise ValueError(f"profileCompany không có năng lực '{cap}'")

        if dry_run:  # W2
            result.update(
                status="ok", output=None,
                summary=f"[dryRun] Sẽ chạy {cap} với {json.dumps(inp, ensure_ascii=False)}")
        else:
            output, summary, side_effects = handler(inp)
            result.update(status="ok", output=output, summary=summary,
                          sideEffects=side_effects)

    except ValueError as exc:
        result.update(status="needsInput", error=str(exc), summary=str(exc))
    except Exception as exc:  # O3
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}",
                      summary=f"profileCompany hỏng khi chạy {cap}.")

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
         json.dumps({"status": result["status"], "input": inp}, ensure_ascii=False),
         now_utc()),
    )
    conn.commit()
    conn.close()

    json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
