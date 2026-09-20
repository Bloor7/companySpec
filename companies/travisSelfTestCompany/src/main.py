#!/usr/bin/env python3
"""travisSelfTestCompany — company GIẢ để đo chính hệ thống.

Hợp đồng C1 y hệt mọi company khác: taskEnvelope trên stdin → companyResult
trên stdout. Khác duy nhất: phần nghiệp vụ rỗng.

KHÔNG gọi mạng. KHÔNG giữ secret. Tác động duy nhất là một dòng trong sổ
sqlite của chính nó — hoàn tác được, và không chạm gì của admin.
"""
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(HERE, "..", "store.sqlite")


def nowUtc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(STORE)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS taskLog (
          taskId TEXT PRIMARY KEY, traceId TEXT NOT NULL, capability TEXT NOT NULL,
          inputHash TEXT NOT NULL, status TEXT NOT NULL, startedAt TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS selfTestEntry (
          entryId TEXT PRIMARY KEY, label TEXT NOT NULL, value TEXT NOT NULL,
          createdAt TEXT NOT NULL
        );
        """
    )
    conn.commit()
    return conn


def echoRead(inputValue: dict):
    return ({"message": inputValue["message"], "echoedAt": nowUtc()},
            f"đã vọng lại: {inputValue['message'][:60]}",
            [])


def recordWrite(inputValue: dict):
    entryId = f"ste_{int(time.time() * 1000)}"
    conn = connect()
    conn.execute(
        "INSERT INTO selfTestEntry (entryId, label, value, createdAt) "
        "VALUES (?,?,?,?)",
        (entryId, inputValue["label"], inputValue["value"], nowUtc()))
    conn.commit()
    conn.close()
    return (
        {"entryId": entryId, "label": inputValue["label"],
         "value": inputValue["value"]},
        f"đã ghi {inputValue['label']}",
        # Khai tác động — đây là thứ `verifyCompanyCall` soi để biết thế giới
        # đã đổi. Năng lực GHI mà không khai là một khoảng tối.
        [{"type": "selfTest.entry", "target": entryId, "reversible": True}],
    )


def failOnPurpose(inputValue: dict):
    """Hỏng theo kiểu được chọn — để kiểm rằng hệ XỬ LÝ ĐƯỢC hỏng."""
    mode = inputValue["mode"]

    if mode == "timeout":
        # Ngủ lâu hơn `maxDurationSec` (5s). Executor phải cắt và trả
        # `budgetExceeded` BÁO ĐƯỢC, không phải văng TimeoutExpired (O8).
        time.sleep(30)
        return {"mode": mode}, "không bao giờ tới đây", []

    if mode == "badOutput":
        # Trả về thứ KHÔNG khớp outputSchema. Dispatcher phải bắt ở C2.3 ra.
        return {"khongCoTruongNay": True}, "output sai schema có chủ ý", []

    if mode == "crash":
        # Chết thật, và để LOẠI LỖI ở dòng cuối stderr — đúng hình dạng của
        # traceback Python. Nếu log bị cắt từ đầu thì dòng này mất.
        sys.stderr.write("x" * 3000 + "\n")
        raise RuntimeError("SelfTestCrash: đây là dòng cuối nói hỏng vì cái gì")

    if mode == "needsInput":
        raise ValueError("thiếu dữ kiện có chủ ý — để kiểm nhánh needsInput")

    raise ValueError(f"mode lạ: {mode}")


HANDLERS = {"echoRead": echoRead, "recordWrite": recordWrite,
            # Cùng một việc, khác đúng một thứ: manifest khai `autonomyOptIn`
            # cho nó. Tách ra thành hai tên để `recordWrite` giữ nguyên vai
            # chốt canh cửa duyệt trong tests/integration/testEndToEnd.py.
            "recordWriteAuto": recordWrite,
            "failOnPurpose": failOnPurpose}


def main() -> int:
    started = time.time()
    env = json.load(sys.stdin)
    taskId, traceId = env["taskId"], env["traceId"]
    capability, inputValue = env["capability"], env["input"]
    dryRun = env.get("policy", {}).get("dryRun", False)

    result = {"taskId": taskId, "traceId": traceId, "status": "failed",
              "output": None, "summary": "", "sideEffects": [], "error": None}

    conn = connect()
    conn.execute(
        "INSERT OR REPLACE INTO taskLog (taskId, traceId, capability, "
        "inputHash, status, startedAt) VALUES (?,?,?,?,?,?)",
        (taskId, traceId, capability, env.get("_inputHash", ""), "running",
         nowUtc()))
    conn.commit()

    try:
        handler = HANDLERS.get(capability)
        if handler is None:
            raise ValueError(
                f"travisSelfTestCompany không có năng lực '{capability}'")

        if dryRun:  # W2 — chặn TRƯỚC khi chạm gì, như mọi company khác
            result.update(
                status="ok", output=None,
                summary=f"[dryRun] Sẽ chạy {capability} với "
                        f"{json.dumps(inputValue, ensure_ascii=False)}")
        else:
            output, summary, sideEffects = handler(inputValue)
            result.update(status="ok", output=output, summary=summary,
                          sideEffects=sideEffects)

    except ValueError as exc:
        result.update(status="needsInput", error=str(exc), summary=str(exc))
    except Exception as exc:  # O3 — hỏng thì hỏng to, nhưng vẫn báo được
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}",
                      summary=f"travisSelfTestCompany hỏng khi chạy {capability}.")
        conn.execute("UPDATE taskLog SET status=? WHERE taskId=?",
                     ("failed", taskId))
        conn.commit()
        conn.close()
        # Chết thật để executor thấy mã thoát khác 0 và đọc stderr.
        print(json.dumps(result, ensure_ascii=False))
        raise

    conn.execute("UPDATE taskLog SET status=? WHERE taskId=?",
                 (result["status"], taskId))
    conn.commit()
    conn.close()

    result["usage"] = {"steps": 1,
                       "durationMs": int((time.time() - started) * 1000),
                       "costUsd": 0.0}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
