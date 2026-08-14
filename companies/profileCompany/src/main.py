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

NHOM = ["xưng hô", "thói quen", "từ vựng riêng", "bối cảnh", "sở thích"]

# Trần cứng. Hồ sơ nằm trong system prompt của MỌI lượt, nên nó phình ra là mọi
# tin nhắn đắt lên và những dòng quan trọng bị loãng giữa đám vụn vặt.
MAX_FACTS = 30

HEADER = """# Hồ sơ admin

<!-- Sinh và đọc bởi profileCompany. Sửa tay thoải mái — company đọc lại đúng
     file này, không giữ bản sao ở đâu khác.
     Mỗi dòng dạng:  - (id) nội dung
     Nội dung ở đây được nạp vào system prompt của CEO ở mỗi lượt. -->
"""

DONG = re.compile(r"^\s*-\s*\((p\d+)\)\s*(.+?)\s*$")


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
            facts.append({"factId": m.group(1), "nhom": nhom, "noiDung": m.group(2)})
    return facts


def write_facts(facts: list):
    """Viết lại cả file, nhóm theo chủ đề, giữ thứ tự nhóm cố định."""
    out = [HEADER]
    for nhom in NHOM:
        trong_nhom = [f for f in facts if f["nhom"] == nhom]
        if not trong_nhom:
            continue
        out.append(f"\n## {nhom}\n")
        for f in trong_nhom:
            out.append(f'- ({f["factId"]}) {f["noiDung"]}\n')
    # Nhóm lạ (admin tự thêm heading khác) vẫn được giữ, không âm thầm xoá.
    la = [f for f in facts if f["nhom"] not in NHOM]
    for nhom in dict.fromkeys(f["nhom"] for f in la):
        out.append(f"\n## {nhom}\n")
        for f in [x for x in la if x["nhom"] == nhom]:
            out.append(f'- ({f["factId"]}) {f["noiDung"]}\n')
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
    facts = read_facts()
    if inp.get("nhom"):
        facts = [f for f in facts if f["nhom"] == inp["nhom"]]
    if not facts:
        return {"facts": [], "count": 0}, "Hồ sơ đang trống.", []

    theo_nhom: dict = {}
    for f in facts:
        theo_nhom.setdefault(f["nhom"], []).append(f)
    dong = []
    for nhom, items in theo_nhom.items():
        dong.append(nhom + ":")
        dong += [f'  ({f["factId"]}) {f["noiDung"]}' for f in items]
    return ({"facts": facts, "count": len(facts)},
            f"{len(facts)} điều đang nhớ về đại ca.\n" + "\n".join(dong), [])


def remember_fact(inp):
    facts = read_facts()
    if len(facts) >= MAX_FACTS:
        raise ValueError(
            f"Hồ sơ đã có {len(facts)} điều — trần là {MAX_FACTS}. "
            "Quên bớt một điều cũ trước đã; nhớ quá nhiều thì đắt mỗi lượt và "
            "những điều quan trọng bị loãng.")

    noi_dung = " ".join(inp["noiDung"].split())
    trung = next((f for f in facts if f["noiDung"].lower() == noi_dung.lower()), None)
    if trung:
        raise ValueError(
            f'Đã nhớ rồi: ({trung["factId"]}) {trung["noiDung"]}. Em không ghi trùng.')

    fid = next_id(facts)
    facts.append({"factId": fid, "nhom": inp["nhom"], "noiDung": noi_dung})
    write_facts(facts)

    return (
        {"factId": fid, "nhom": inp["nhom"], "noiDung": noi_dung, "tong": len(facts)},
        f'Đã nhớ ({fid}) {noi_dung} — nhóm "{inp["nhom"]}". '
        f"Từ giờ em mang theo điều này trong mọi cuộc trò chuyện. "
        f"Hồ sơ: {len(facts)}/{MAX_FACTS} điều.",
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
    return (
        {"factId": cur["factId"], "nhom": cur["nhom"], "noiDung": cur["noiDung"],
         "tong": len(facts)},
        f'Đã quên ({cur["factId"]}) {cur["noiDung"]}. Còn {len(facts)} điều.',
        # D5 — chép lại nội dung cũ, nếu không thì "quên" là không thể hoàn tác.
        [{"type": "profile.forget", "target": cur["factId"],
          "idempotencyKey": f'forget|{cur["factId"]}',
          "reversible": True,
          "previousValue": f'{cur["nhom"]}|{cur["noiDung"]}'}],
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
