#!/usr/bin/env python3
"""seoCompany — bọc plugin claude-seo thành một company có hợp đồng.

Hợp đồng (C1): taskEnvelope trên stdin → companyResult trên stdout. Giống hệt
ba company kia, dù bên trong nó chạy cả một phiên Claude Code riêng.

Đó chính là điểm của C1: CEO không biết và không cần biết sự khác nhau. Với nó,
gọi seoCompany hay gọi expenseCompany là cùng một việc.

Ba thứ company này phải tự lo, vì nó là company duy nhất dùng LLM:
  · Nhốt tiến trình con: chỉ cho đúng tool cần, deny rules riêng, không MCP.
  · Ghi báo cáo ra FILE, trả đường dẫn (D1). Báo cáo SEO dài hàng nghìn chữ,
    nhét vào envelope là làm nghẽn cả CEO lẫn Telegram.
  · Khai chi phí thật vào usage.costUsd — nó đốt hạn mức gói Pro, khác hẳn
    các company chỉ gọi REST.
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "lib"))
COMPANY = os.path.abspath(os.path.join(HERE, ".."))
PLUGIN = os.path.join(COMPANY, "plugin")
SETTINGS = os.path.join(COMPANY, "settings.json")
OUT = os.path.join(COMPANY, "out")
sys.path.insert(0, os.path.join(COMPANY, "..", "..", "lib"))
import db  # noqa: E402

STORE = os.path.join(COMPANY, "store.sqlite")
TZ = timezone(timedelta(hours=7))

# Tool mà tiến trình SEO được cầm. CEO không có cái nào trong số này ngoài Bash.
TOOLS = "Bash,Read,Write,Glob,Grep,WebFetch,WebSearch,Task,Skill,TodoWrite"

PROMPTS = {
    "auditPage": '/seo page {url}',
    "auditSite": '/seo audit {url}',
}


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


def safe_name(url: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", url).strip("-")[:60] or "site"


def run_skill(cap: str, inp: dict, deadline_sec: int) -> dict:
    """Chạy một phiên Claude Code riêng, nhốt kín, chỉ có plugin SEO."""
    prompt = PROMPTS[cap].format(url=inp["url"])
    if inp.get("focus"):
        prompt += f"\n\nTập trung vào: {inp['focus']}"
    if inp.get("maxPages"):
        prompt += f"\n\nGiới hạn {inp['maxPages']} trang."
    prompt += ("\n\nViết báo cáo bằng TIẾNG VIỆT. Kết thúc bằng một dòng duy nhất "
               "dạng: TÓM TẮT: <một câu dưới 200 ký tự>")

    cmd = [
        "claude", "-p", prompt,
        "--plugin-dir", PLUGIN,
        "--settings", SETTINGS,
        "--tools", TOOLS,
        "--strict-mcp-config",      # B6 — không nạp connector nào
        "--setting-sources", "project",
        "--max-turns", "60",        # audit thật cần nhiều vòng; vẫn có trần
        "--output-format", "json",
        "--no-session-persistence", # mỗi lần gọi là một phiên sạch
    ]
    proc = subprocess.run(cmd, cwd=COMPANY, capture_output=True, text=True,
                          timeout=deadline_sec)
    if proc.returncode != 0:
        raise RuntimeError(
            f"phiên SEO thoát mã {proc.returncode}: {proc.stderr.strip()[:300]}")
    data = json.loads(proc.stdout)

    # O3 — hỏng thì hỏng TO.
    # Lần đầu chạy, tool bị chặn quyền nên skill không đọc được web, nhưng vẫn
    # viết ra một "báo cáo" nói rằng nó không đọc được — và company trả về ok.
    # Báo cáo vô dụng đội lốt thành công là kiểu hỏng tệ nhất: admin tin là xong.
    # CLI trả sẵn permission_denials; có phần tử nào là kết quả không đáng tin.
    denials = data.get("permission_denials") or []
    if denials:
        tools = ", ".join(sorted({d.get("tool_name", "?") for d in denials}))
        raise RuntimeError(
            f"phiên SEO bị chặn quyền dùng: {tools}. Kết quả không đáng tin — "
            "bổ sung vào permissions.allow của companies/seoCompany/settings.json")
    return data


def audit(cap, inp, deadline_sec):
    data = run_skill(cap, inp, deadline_sec)
    report = (data.get("result") or "").strip()
    if not report:
        raise RuntimeError("phiên SEO không trả về nội dung nào")

    os.makedirs(OUT, exist_ok=True)
    stamp = datetime.now(TZ).strftime("%Y%m%d-%H%M")
    path = os.path.join(OUT, f"{cap}-{safe_name(inp['url'])}-{stamp}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# {cap} · {inp['url']}\n\n_{now_utc()}_\n\n{report}\n")

    # Skill được dặn kết thúc bằng "TÓM TẮT: …" — lấy đúng dòng đó cho CEO đọc.
    m = re.search(r"^\s*TÓM TẮT:\s*(.+)$", report, re.M | re.I)
    summary = (m.group(1) if m else report.splitlines()[-1])[:300]

    # Đếm thô số điểm cần sửa, để CEO có con số nói với admin.
    findings = len(re.findall(r"^\s*[-*]\s+", report, re.M))

    rel = os.path.relpath(path, os.path.dirname(os.path.dirname(COMPANY)))
    return (
        {"url": inp["url"], "reportPath": rel, "findings": findings},
        f"{summary} (báo cáo: {os.path.basename(path)})",
        [],                                   # chỉ đọc web, không đổi gì (read)
        data.get("total_cost_usd", 0.0),
    )


def main() -> int:
    started = time.time()
    env = json.load(sys.stdin)
    task_id, trace_id = env["taskId"], env["traceId"]
    cap, inp = env["capability"], env["input"]
    dry_run = env.get("policy", {}).get("dryRun", False)

    result = {"taskId": task_id, "traceId": trace_id, "status": "failed",
              "output": None, "summary": "", "sideEffects": [], "error": None}
    cost = 0.0

    conn = connect()
    conn.execute(
        "INSERT OR REPLACE INTO taskLog (taskId, traceId, capability, inputHash, "
        "status, startedAt) VALUES (?,?,?,?,?,?)",
        (task_id, trace_id, cap, env.get("_inputHash", ""), "running", now_utc()),
    )
    conn.commit()

    try:
        if cap not in PROMPTS:
            raise ValueError(f"seoCompany không có năng lực '{cap}'")
        if not inp["url"].startswith(("http://", "https://")):
            raise ValueError("url phải bắt đầu bằng http:// hoặc https://")

        if dry_run:  # W2
            result.update(status="ok", output=None,
                          summary=f"[dryRun] Sẽ chạy {PROMPTS[cap].format(url=inp['url'])}")
        else:
            # Chừa 30 giây trước deadline để còn kịp ghi file và trả kết quả.
            # Hết giờ mà không kịp trả thì dispatcher chỉ thấy tiến trình chết —
            # mất luôn báo cáo đã tốn công làm.
            dl = datetime.strptime(env["budget"]["deadlineAt"], "%Y-%m-%dT%H:%M:%SZ")
            remain = (dl.replace(tzinfo=timezone.utc)
                      - datetime.now(timezone.utc)).total_seconds()
            budget = max(60, int(remain) - 30)
            output, summary, side_effects, cost = audit(cap, inp, budget)
            result.update(status="ok", output=output, summary=summary,
                          sideEffects=side_effects)

    except subprocess.TimeoutExpired:
        result.update(status="budgetExceeded",
                      summary="Phiên SEO chạy quá lâu, đã cắt. Thử auditPage thay vì auditSite.",
                      error="timeout")
    except ValueError as exc:
        result.update(status="needsInput", error=str(exc), summary=str(exc))
    except Exception as exc:  # O3
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}",
                      summary=f"seoCompany hỏng khi chạy {cap}: {str(exc)[:150]}")

    duration = int((time.time() - started) * 1000)
    result["usage"] = {"steps": 1, "durationMs": duration, "costUsd": cost}

    conn.execute(
        "UPDATE taskLog SET status=?, summary=?, finishedAt=?, durationMs=?, costUsd=? "
        "WHERE taskId=?",
        (result["status"], result["summary"], now_utc(), duration, cost, task_id),
    )
    conn.execute(
        "INSERT INTO eventLog (taskId, traceId, eventType, payloadJson, createdAt) "
        "VALUES (?,?,?,?,?)",
        (task_id, trace_id, f"capability.{cap}",
         json.dumps({"status": result["status"], "costUsd": cost}, ensure_ascii=False),
         now_utc()),
    )
    conn.commit()
    conn.close()

    json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
