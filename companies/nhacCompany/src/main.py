#!/usr/bin/env python3
"""nhacCompany — giữ những lời hẹn NHẮC. Tới giờ, scheduler đọc rồi nhắn.

Hợp đồng (C1): taskEnvelope trên stdin → companyResult trên stdout.

CÔNG TY NÀY KHÔNG GỬI TIN. Nó chỉ giữ sổ. Gửi tin là việc của `ops/telegram.py`
— T1, đường ra duy nhất — và scheduler là thứ đọc sổ này rồi gọi đường đó. Tách
ra vì một lý do đo được: nếu company tự gửi tin thì mỗi company sau này lại có
một đường ra riêng, và cái ngày admin muốn tắt tiếng thì phải đi tìm từng chỗ.

VÌ SAO KHÔNG CÓ CỘT "ĐÃ GỬI": cron chỉ được ĐỌC (S3), nên scheduler không ghi
được vào sổ này. Trí nhớ "đã nhắc rồi" nằm ở sổ của chính scheduler. Đây đúng
cách ngoaiNguCompany đã giải bài toán ấy hồi 24/08 — không phải giải pháp đẹp
nhất, nhưng là giải pháp KHÔNG cần nới quyền cho cron.

Hệ quả phải biết: lời nhắc đã kêu vẫn nằm lại trong sổ này. `datNhac` dọn giúp
những dòng quá hạn lâu mỗi lần admin đặt cái mới — dọn ở đường GHI, vì đó là
đường duy nhất được phép ghi.
"""
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
COMPANY = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(COMPANY, "..", "..", "lib"))
import db  # noqa: E402

STORE = os.path.join(COMPANY, "store.sqlite")
TZ_VN = timezone(timedelta(hours=7))

# Lời nhắc đã quá hạn lâu hơn ngần này thì dọn. Giữ lại vài ngày để admin còn
# hỏi được "hôm kia em nhắc anh cái gì".
DON_SAU_NGAY = 7


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
        -- `khiNaoUtc` là mốc so sánh của máy; `khiNao` giữ nguyên chữ admin nói
        -- để lúc kể lại không phải đổi múi giờ ngược. Hai cột cho một khái
        -- niệm là chấp nhận được ở đây vì một cột dành cho máy, một cho người.
        CREATE TABLE IF NOT EXISTS nhac (
          nhacId TEXT PRIMARY KEY, noiDung TEXT NOT NULL,
          khiNao TEXT NOT NULL, khiNaoUtc TEXT NOT NULL, createdAt TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS nhac_gio ON nhac (khiNaoUtc);
        """
    )
    return conn


def _doc_gio(chuoi: str) -> datetime:
    """Đọc giờ admin nói (giờ VN) thành mốc UTC.

    Nhận `2026-09-01T03:00` hoặc `2026-09-01T03:00:00`. KHÔNG nhận chuỗi có
    múi giờ: CEO hay gắn `Z` vào rồi cái hẹn 3h sáng thành 10h sáng — đúng họ
    với con bug lọc ngày theo UTC hồi 25/08. Ở đây bắt lỗi ngay, đừng đoán hộ.
    """
    s = (chuoi or "").strip()
    if s.endswith("Z") or "+" in s:
        raise ValueError(
            "khiNao phải là giờ Việt Nam, KHÔNG có Z hay +07:00 ở cuối. "
            "Ví dụ: 2026-09-01T03:00")
    for dinh_dang in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(s, dinh_dang).replace(tzinfo=TZ_VN)
        except ValueError:
            continue
    raise ValueError(f"khiNao không đọc được: {s!r}. Dạng đúng: 2026-09-01T03:00")


def _con_bao_lau(moc: datetime) -> str:
    giay = (moc - datetime.now(timezone.utc)).total_seconds()
    if giay < 0:
        return "đã qua"
    if giay < 3600:
        return f"{int(giay // 60)} phút nữa"
    if giay < 86400:
        return f"{giay / 3600:.1f} giờ nữa"
    return f"{giay / 86400:.1f} ngày nữa"


def dat_nhac(inp: dict) -> tuple:
    moc = _doc_gio(inp["khiNao"])
    if moc <= datetime.now(timezone.utc):
        raise ValueError(
            f"{inp['khiNao']} đã qua rồi. Hỏi admin ý là ngày nào, đừng tự "
            "đẩy sang hôm sau — đoán sai một ngày thì chuông kêu sai một ngày.")

    conn = connect()
    # Dọn ở đường GHI, vì đó là đường duy nhất được phép ghi (S3).
    cutoff = (datetime.now(timezone.utc) - timedelta(days=DON_SAU_NGAY)
              ).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute("DELETE FROM nhac WHERE khiNaoUtc < ?", (cutoff,))

    nhac_id = "nhac_" + os.urandom(6).hex()
    utc = moc.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "INSERT INTO nhac (nhacId, noiDung, khiNao, khiNaoUtc, createdAt) "
        "VALUES (?,?,?,?,?)",
        (nhac_id, inp["noiDung"], inp["khiNao"], utc, now_utc()))
    conn.commit()
    conn.close()
    con = _con_bao_lau(moc)
    return ({"nhacId": nhac_id, "khiNao": inp["khiNao"], "conBaoLau": con},
            f"Đã đặt nhắc lúc {inp['khiNao']} ({con}): {inp['noiDung'][:80]}",
            [{"type": "reminder.set", "target": nhac_id,
              "idempotencyKey": f"nhac|{inp['khiNao']}|{inp['noiDung'][:40]}",
              "reversible": True}])


def ds_nhac(inp: dict) -> tuple:
    """Mặc định chỉ kể lời nhắc CÒN TREO — đó là thứ admin hỏi khi hỏi.

    `gomDenHan` mở thêm cửa sổ một giờ về quá khứ, và scheduler dùng đúng cửa
    đó: cái vừa rơi qua mốc mới là cái cần kêu. Bản đầu không có tham số này và
    hậu quả rất im lặng — lời nhắc tới giờ thì lập tức biến mất khỏi danh sách,
    nên scheduler không bao giờ thấy nó, và cái chuông không bao giờ kêu. Đo
    được 31/08 bằng một lần chạy thật đầu-đến-cuối.
    """
    conn = connect()
    moc = now_utc()
    if inp.get("gomDenHan"):
        moc = (datetime.now(timezone.utc) - timedelta(hours=1)
               ).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = list(conn.execute(
        "SELECT nhacId, noiDung, khiNao, khiNaoUtc FROM nhac "
        "WHERE khiNaoUtc >= ? ORDER BY khiNaoUtc LIMIT ?",
        (moc, int(inp.get("gioiHan") or 20))))
    conn.close()
    ds = [{"nhacId": r["nhacId"], "noiDung": r["noiDung"], "khiNao": r["khiNao"],
           "conBaoLau": _con_bao_lau(
               datetime.strptime(r["khiNaoUtc"], "%Y-%m-%dT%H:%M:%SZ")
               .replace(tzinfo=timezone.utc))} for r in rows]
    if not ds:
        return {"cacNhac": [], "tong": 0}, "Không có lời nhắc nào đang treo.", []
    dong = "\n".join(f"{d['khiNao']} ({d['conBaoLau']}) — {d['noiDung'][:60]}"
                     for d in ds)
    return ({"cacNhac": ds, "tong": len(ds)},
            f"{len(ds)} lời nhắc đang treo:\n{dong}", [])


def huy_nhac(inp: dict) -> tuple:
    conn = connect()
    row = conn.execute("SELECT noiDung FROM nhac WHERE nhacId=?",
                       (inp["nhacId"],)).fetchone()
    if row is None:
        conn.close()
        # D6 — không tìm thấy thì BÁO, đừng lặng lẽ coi như đã xong.
        raise ValueError(f"Không có lời nhắc nào mang mã {inp['nhacId']}. "
                         "Chạy dsNhac để lấy mã đúng.")
    conn.execute("DELETE FROM nhac WHERE nhacId=?", (inp["nhacId"],))
    conn.commit()
    conn.close()
    return ({"daHuy": True, "noiDung": row["noiDung"]},
            f"Đã bỏ lời nhắc: {row['noiDung'][:80]}",
            [{"type": "reminder.cancel", "target": inp["nhacId"],
              "idempotencyKey": f"huy|{inp['nhacId']}", "reversible": False}])


HANDLERS = {"datNhac": dat_nhac, "dsNhac": ds_nhac, "huyNhac": huy_nhac}


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
            raise ValueError(f"nhacCompany không có năng lực '{cap}'")
        if dry_run:  # W2
            result.update(status="ok", output=None,
                          summary=f"[dryRun] {cap}: "
                                  + json.dumps(inp, ensure_ascii=False)[:150])
        else:
            output, summary, side_effects = handler(inp)
            result.update(status="ok", output=output, summary=summary,
                          sideEffects=side_effects)
    except ValueError as exc:
        result.update(status="needsInput", error=str(exc), summary=str(exc))
    except Exception as exc:  # O3
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}",
                      summary=f"nhacCompany hỏng khi chạy {cap}: {exc}")

    duration = int((time.time() - started) * 1000)
    result["usage"] = {"steps": 1, "durationMs": duration, "costUsd": 0.0}
    conn = connect()
    conn.execute(
        "UPDATE taskLog SET status=?, summary=?, finishedAt=?, durationMs=? "
        "WHERE taskId=?",
        (result["status"], result["summary"][:400], now_utc(), duration, task_id))
    conn.execute(
        "INSERT INTO eventLog (taskId, traceId, eventType, payloadJson, createdAt) "
        "VALUES (?,?,?,?,?)",
        (task_id, trace_id, f"{cap}.{result['status']}",
         json.dumps({"status": result["status"]}, ensure_ascii=False), now_utc()))
    conn.commit()
    conn.close()

    json.dump(result, sys.stdout, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
