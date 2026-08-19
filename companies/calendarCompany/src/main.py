#!/usr/bin/env python3
"""calendarCompany — lịch trình và nhắc trước giờ.

Hợp đồng (C1): taskEnvelope trên stdin → companyResult trên stdout.

Lịch thật nằm ở Notion. store.sqlite giữ nhật ký công việc và dấu "đã nhắc" —
dấu đó là trạng thái nội bộ, không phải bản sao dữ liệu: mất nó thì cùng lắm
admin bị nhắc lại một lần, không mất sự kiện nào.
"""
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "lib"))
import notionClient as notion  # noqa: E402
import db  # noqa: E402

STORE = os.path.join(HERE, "..", "store.sqlite")
TZ = timezone(timedelta(hours=7))  # Asia/Ho_Chi_Minh


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_local() -> datetime:
    return datetime.now(TZ)


def today() -> str:
    return now_local().strftime("%Y-%m-%d")


def database_id() -> str:
    dbid = os.environ.get("NOTION_CALENDAR_DATABASE_ID", "")
    if not dbid:
        raise notion.NotionError(
            "Thiếu NOTION_CALENDAR_DATABASE_ID. Chạy: python3 ops/setup-notion.py")
    return dbid


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
        -- Dấu "đã nhắc". Khoá gồm cả giờ bắt đầu: admin dời lịch thì coi như sự
        -- kiện mới và được nhắc lại, vì giờ mới mới là thứ cần nhớ.
        CREATE TABLE IF NOT EXISTS daNhac (
          eventId TEXT NOT NULL, batDau TEXT NOT NULL, nhacLuc TEXT NOT NULL,
          PRIMARY KEY (eventId, batDau)
        );
        """
    )
    return conn


# ───────────────────────── thời gian ─────────────────────────

def parse_dt(raw):
    """Notion trả '2026-08-05T09:00:00.000+07:00' hoặc '2026-08-05' (cả ngày)."""
    if not raw:
        return None, False
    txt = raw.replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(txt)
    except ValueError:
        return None, False
    if len(raw) <= 10:          # chỉ có ngày, không có giờ
        return d.replace(tzinfo=TZ), True
    if d.tzinfo is None:
        d = d.replace(tzinfo=TZ)
    return d.astimezone(TZ), False


def gio(d: datetime, ca_ngay: bool) -> str:
    return "cả ngày" if ca_ngay else d.strftime("%H:%M")


def ngay_viet(d: datetime) -> str:
    thu = ["thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ nhật"]
    return f"{thu[d.weekday()]} {d:%d/%m}"


def to_notion(raw: str) -> str:
    """Chuỗi admin/CEO đưa vào → giá trị Notion chấp nhận.

    Có giờ thì phải kèm offset +07:00, nếu không Notion hiểu là UTC và mọi sự
    kiện lệch đi 7 tiếng — sai lặng lẽ, chỉ lộ ra khi lời nhắc đến sai giờ.
    """
    raw = raw.strip()
    if len(raw) <= 10:
        return raw                      # cả ngày
    if len(raw) == 16:                  # YYYY-MM-DDTHH:MM
        raw += ":00"
    return raw + "+07:00"


def row_to_event(page: dict) -> dict:
    props = page.get("properties", {})
    bd_raw = notion.plain(props.get("Bắt đầu"))
    kt_raw = notion.plain(props.get("Kết thúc"))
    bd, ca_ngay = parse_dt(bd_raw)
    kt, _ = parse_dt(kt_raw)
    return {
        "eventId": page["id"],
        "ten": notion.plain(props.get("Tên")) or "(không tên)",
        "batDau": bd_raw,
        "ketThuc": kt_raw,
        "gio": gio(bd, ca_ngay) if bd else "?",
        "caNgay": ca_ngay,
        "loai": notion.plain(props.get("Loại")),
        "diaDiem": notion.plain(props.get("Địa điểm")) or "",
        "ghiChu": notion.plain(props.get("Ghi chú")) or "",
        "url": page.get("url", ""),
        "_bd": bd, "_kt": kt,
    }


def sach(e: dict) -> dict:
    """Bỏ các trường nội bộ trước khi trả ra ngoài (datetime không JSON hoá được)."""
    return {k: v for k, v in e.items() if not k.startswith("_")}


def fetch(token, frm: str, to: str, loai=None, limit=100) -> list:
    conds = [{"property": "Bắt đầu", "date": {"on_or_after": frm}},
             {"property": "Bắt đầu", "date": {"on_or_before": to}}]
    if loai:
        conds.append({"property": "Loại", "select": {"equals": loai}})
    pages = notion.query_database(
        token, database_id(), filter_={"and": conds},
        sorts=[{"property": "Bắt đầu", "direction": "ascending"}], page_size=limit)
    return [row_to_event(p) for p in pages]


def dong_su_kien(e: dict) -> str:
    phan = [f'{e["gio"]}  {e["ten"]}']
    duoi = [x for x in (e["diaDiem"], e["loai"]) if x]
    if duoi:
        phan.append("        " + " · ".join(duoi))
    return "\n".join(phan)


# ───────────────────────── năng lực ─────────────────────────

def today_agenda(token, inp):
    ngay = inp.get("ngay") or today()
    events = fetch(token, ngay, ngay)
    d, _ = parse_dt(ngay)
    if not events:
        return ({"events": [], "count": 0, "ngay": ngay},
                f"{ngay_viet(d)}: không có lịch gì.", [])
    return ({"events": [sach(e) for e in events], "count": len(events), "ngay": ngay},
            f"{ngay_viet(d)} — {len(events)} việc:\n"
            + "\n".join(dong_su_kien(e) for e in events), [])


def list_events(token, inp):
    frm = inp.get("tuNgay") or today()
    to = inp.get("denNgay") or (now_local() + timedelta(days=7)).strftime("%Y-%m-%d")
    events = fetch(token, frm, to, inp.get("loai"), inp.get("gioiHan", 50))
    if not events:
        return ({"events": [], "count": 0}, f"{frm} → {to}: không có sự kiện nào.", [])

    theo_ngay: dict = {}
    for e in events:
        theo_ngay.setdefault(e["_bd"].strftime("%Y-%m-%d") if e["_bd"] else "?", []).append(e)
    dong = []
    for ngay, items in theo_ngay.items():
        d, _ = parse_dt(ngay)
        dong.append(ngay_viet(d) if d else ngay)
        dong += ["  " + dong_su_kien(e).replace("\n", "\n  ") for e in items]
    return ({"events": [sach(e) for e in events], "count": len(events)},
            f"{len(events)} việc từ {frm} đến {to}:\n" + "\n".join(dong), [])


def upcoming_events(token, inp):
    """Sắp tới trong N phút. Cron gọi với danhDau=true để không nhắc lặp.

    Ghi dấu vào store là ghi trạng thái NỘI BỘ, không phải tác động ra ngoài —
    nên năng lực này vẫn là `read` và cron gọi được (S3).
    """
    phut = inp.get("trongPhut", 30)
    bay_gio = now_local()
    han = bay_gio + timedelta(minutes=phut)

    # Quét hai ngày để bắt cả trường hợp mốc rơi qua nửa đêm.
    events = fetch(token, bay_gio.strftime("%Y-%m-%d"), han.strftime("%Y-%m-%d"))
    sap_toi = [e for e in events
               if e["_bd"] and not e["caNgay"] and bay_gio <= e["_bd"] <= han]

    if inp.get("danhDau"):
        conn = connect()
        con_lai = []
        for e in sap_toi:
            da = conn.execute("SELECT 1 FROM daNhac WHERE eventId=? AND batDau=?",
                              (e["eventId"], e["batDau"])).fetchone()
            if da:
                continue
            conn.execute("INSERT INTO daNhac (eventId, batDau, nhacLuc) VALUES (?,?,?)",
                         (e["eventId"], e["batDau"], now_utc()))
            con_lai.append(e)
        conn.commit()
        conn.close()
        sap_toi = con_lai

    out = {"events": [sach(e) for e in sap_toi], "count": len(sap_toi),
           "trongPhut": phut}
    if not sap_toi:
        # Rỗng = không có gì để nói. Scheduler đọc quy ước này để giữ im lặng.
        return out, "", []

    dong = []
    for e in sap_toi:
        con = int((e["_bd"] - bay_gio).total_seconds() // 60)
        dong.append(f'{e["ten"]} — {e["gio"]}, còn {con} phút'
                    + (f' · {e["diaDiem"]}' if e["diaDiem"] else ""))
    return out, "Sắp tới:\n" + "\n".join(dong), []


def add_event(token, inp):
    bd = to_notion(inp["batDau"])
    props = {
        "Tên":     notion.title_prop(inp["ten"]),
        "Bắt đầu": notion.date_prop(bd),
        "Loại":    notion.select_prop(inp["loai"]),
        "Địa điểm": notion.text_prop(inp.get("diaDiem", "")),
        "Ghi chú": notion.text_prop(inp.get("ghiChu", "")),
    }
    if inp.get("ketThuc"):
        props["Kết thúc"] = notion.date_prop(to_notion(inp["ketThuc"]))

    page = notion.create_page(token, database_id(), props)
    d, ca_ngay = parse_dt(bd)
    return (
        {"eventId": page["id"], "ten": inp["ten"], "batDau": bd,
         "ketThuc": inp.get("ketThuc"), "loai": inp["loai"],
         "url": page.get("url", "")},
        f'Đã thêm "{inp["ten"]}" — {ngay_viet(d)} {gio(d, ca_ngay)}'
        + (f' tại {inp["diaDiem"]}' if inp.get("diaDiem") else "")
        + ". Em nhắc trước 30 phút.",
        [{"type": "notion.createPage", "target": page["id"],
          "idempotencyKey": f'{bd}|{inp["ten"]}', "reversible": True}],
    )


def add_events(token, inp):
    """Đổ nhiều sự kiện vào lịch trong một lời gọi.

    VÌ SAO CẦN: bản đầu chỉ có addEvent một-cái-một-lần. Admin nhờ đặt lịch làm
    video 30 ngày, CEO gọi 46 lần, whitelist chạm trần 20/ngày và 39 yêu cầu
    duyệt nằm chờ — admin phải bấm 39 nút. Đo được ngày 2026-08-04. Guardrail mà
    bắt bấm 39 lần thì đến nút thứ ba đã không ai đọc nữa, tức là nó hết tác dụng.

    Bỏ qua sự kiện đã có (cùng tên, cùng giờ bắt đầu): admin nhờ lại lần hai vì
    lần đầu dở dang là chuyện thường, và lúc đó không được đẻ ra bản sao.
    """
    dbid = database_id()
    frm = min(s["batDau"][:10] for s in inp["cacSuKien"])
    to = max(s["batDau"][:10] for s in inp["cacSuKien"])
    da_co = {(e["ten"].strip().lower(), (e["batDau"] or "")[:16])
             for e in fetch(token, frm, to, limit=100)}

    tao, side, bo_qua = [], [], 0
    for sk in inp["cacSuKien"]:
        bd = to_notion(sk["batDau"])
        if (sk["ten"].strip().lower(), bd[:16]) in da_co:
            bo_qua += 1
            continue
        props = {
            "Tên":      notion.title_prop(sk["ten"]),
            "Bắt đầu":  notion.date_prop(bd),
            "Loại":     notion.select_prop(sk["loai"]),
            "Địa điểm": notion.text_prop(sk.get("diaDiem", "")),
            "Ghi chú":  notion.text_prop(sk.get("ghiChu", "")),
        }
        if sk.get("ketThuc"):
            props["Kết thúc"] = notion.date_prop(to_notion(sk["ketThuc"]))
        page = notion.create_page(token, dbid, props)
        d, ca_ngay = parse_dt(bd)
        tao.append({"eventId": page["id"], "ten": sk["ten"], "batDau": bd,
                    "loai": sk["loai"], "gio": gio(d, ca_ngay) if d else "?"})
        side.append({"type": "notion.createPage", "target": page["id"],
                     "idempotencyKey": f'{bd}|{sk["ten"]}', "reversible": True})

    if not tao:
        raise ValueError(
            f"Cả {bo_qua} sự kiện đều đã có trong lịch rồi, em không ghi trùng.")

    d1, _ = parse_dt(min(e["batDau"] for e in tao))
    d2, _ = parse_dt(max(e["batDau"] for e in tao))
    return (
        {"count": len(tao), "boQua": bo_qua, "events": tao,
         "tuNgay": d1.strftime("%Y-%m-%d") if d1 else None,
         "denNgay": d2.strftime("%Y-%m-%d") if d2 else None},
        f"Đã thêm {len(tao)} sự kiện vào lịch, từ {ngay_viet(d1)} đến {ngay_viet(d2)}"
        + (f" (bỏ qua {bo_qua} cái đã có sẵn)" if bo_qua else "")
        + ". Em nhắc trước 30 phút từng cái.",
        side,
    )


def delete_event(token, inp):
    page = notion.get_page(token, inp["eventId"])
    if page.get("archived"):
        raise ValueError("Sự kiện này đã bị xoá trước đó rồi.")
    cur = row_to_event(page)

    # Đối chiếu với thứ admin đã nhìn thấy lúc bấm duyệt (D7).
    if cur["ten"].strip().lower() != inp["ten"].strip().lower():
        raise ValueError(
            f'Không khớp: sự kiện đó tên "{cur["ten"]}", không phải "{inp["ten"]}". '
            "Em không xoá.")

    notion.archive_page(token, inp["eventId"])
    d = cur["_bd"]
    return (
        {"eventId": inp["eventId"], "ten": cur["ten"], "batDau": cur["batDau"],
         "loai": cur["loai"]},
        f'Đã bỏ "{cur["ten"]}"'
        + (f' ({ngay_viet(d)} {cur["gio"]})' if d else "")
        + ". Notion giữ trong thùng rác 30 ngày.",
        [{"type": "notion.archivePage", "target": inp["eventId"],
          "idempotencyKey": f'delete|{inp["eventId"]}', "reversible": True,
          "previousValue": f'{cur["batDau"]}|{cur["ten"]}|{cur["loai"]}'}],
    )


def delete_events(token, inp):
    """Bỏ nhiều sự kiện trong một lời gọi.

    VÌ SAO CẦN: `addEvents` đã chữa được chiều TẠO (31 sự kiện, một nút duyệt),
    nhưng chiều DỌN vẫn một-cái-một-lần. Đo 2026-08-19: admin đổi giờ học từ
    21:00 sang 05:30, còn lại 13 sự kiện cũ, và cách duy nhất để gỡ là 13 yêu
    cầu duyệt. Cùng con bug với vụ 39 nút bấm hồi 04/08, chỉ khác chiều.

    CHẠY HẾT RỒI MỚI BÁO, không dừng ở cái hỏng đầu tiên. Dừng giữa chừng để
    lại một trạng thái nửa vời — vài cái đã xoá, vài cái chưa — mà admin không
    có cách nào biết đã tới đâu. Chạy hết thì trạng thái cuối luôn rõ ràng.

    Nhưng O10: hỏng một phần PHẢI hiện ra. Cái nào trượt thì nằm trong `loi` và
    được nói thẳng trong câu tóm tắt, chứ không để con số "đã xoá 11" che mất
    hai cái còn sót — admin đọc xong tưởng sạch rồi thì lần sau lại ngạc nhiên.
    """
    xoa, side, loi, bo_qua = [], [], [], 0

    for sk in inp["cacSuKien"]:
        eid, ten = sk["eventId"], sk["ten"]
        try:
            page = notion.get_page(token, eid)
            if page.get("archived"):
                bo_qua += 1          # đã xoá từ trước — không phải lỗi
                continue
            cur = row_to_event(page)
            # D7 — đối chiếu với thứ admin đã nhìn thấy lúc bấm duyệt.
            if cur["ten"].strip().lower() != ten.strip().lower():
                loi.append(f'"{ten}": trên lịch tên là "{cur["ten"]}", em không xoá')
                continue
            notion.archive_page(token, eid)
            d = cur["_bd"]
            xoa.append({"eventId": eid, "ten": cur["ten"],
                        "batDau": cur["batDau"], "loai": cur["loai"],
                        "gio": cur["gio"]})
            side.append({
                "type": "notion.archivePage", "target": eid,
                "idempotencyKey": f"delete|{eid}", "reversible": True,
                "previousValue": f'{cur["batDau"]}|{cur["ten"]}|{cur["loai"]}'})
        except Exception as exc:
            # Không nuốt. Một cái hỏng vì mạng chập không được phép làm hỏng cả
            # mẻ, nhưng cũng không được phép biến mất khỏi báo cáo.
            loi.append(f'"{ten}": {type(exc).__name__}: {exc}')

    if not xoa:
        if bo_qua and not loi:
            raise ValueError(
                f"Cả {bo_qua} sự kiện đều đã bị xoá từ trước rồi, không còn gì để bỏ.")
        raise ValueError("Không xoá được cái nào. " + " · ".join(loi))

    d1 = min((e["batDau"] for e in xoa if e["batDau"]), default=None)
    d2 = max((e["batDau"] for e in xoa if e["batDau"]), default=None)
    khoang = ""
    if d1:
        a, _ = parse_dt(d1)
        b, _ = parse_dt(d2)
        khoang = (f", từ {ngay_viet(a)} đến {ngay_viet(b)}"
                  if a and b and d1 != d2 else f" ngày {ngay_viet(a)}" if a else "")

    tom = f"Đã bỏ {len(xoa)} sự kiện khỏi lịch{khoang}."
    if bo_qua:
        tom += f" ({bo_qua} cái đã xoá từ trước.)"
    if loi:
        tom += (f" CÒN {len(loi)} CÁI CHƯA XOÁ ĐƯỢC: " + " · ".join(loi[:5])
                + ("…" if len(loi) > 5 else ""))
    tom += " Notion giữ trong thùng rác 30 ngày."

    return ({"count": len(xoa), "boQua": bo_qua, "loi": loi, "events": xoa},
            tom, side)


HANDLERS = {"todayAgenda": today_agenda, "listEvents": list_events,
            "addEvents": add_events,
            "upcomingEvents": upcoming_events, "addEvent": add_event,
            "deleteEvent": delete_event,
            "deleteEvents": delete_events}


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
    conn.close()

    try:
        handler = HANDLERS.get(cap)
        if handler is None:
            raise ValueError(f"calendarCompany không có năng lực '{cap}'")

        if dry_run:  # W2
            result.update(
                status="ok", output=None,
                summary=f"[dryRun] Sẽ chạy {cap} với {json.dumps(inp, ensure_ascii=False)}")
        else:
            token = notion.token_from_env()
            output, summary, side_effects = handler(token, inp)
            result.update(status="ok", output=output, summary=summary,
                          sideEffects=side_effects)

    except notion.NotionError as exc:
        result.update(status="failed", error=str(exc),
                      summary=f"Notion không phản hồi đúng: {exc}")
    except ValueError as exc:
        result.update(status="needsInput", error=str(exc), summary=str(exc))
    except Exception as exc:  # O3
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}",
                      summary=f"calendarCompany hỏng khi chạy {cap}.")

    duration = int((time.time() - started) * 1000)
    result["usage"] = {"steps": 1, "durationMs": duration, "costUsd": 0.0}

    conn = connect()
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
