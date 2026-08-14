#!/usr/bin/env python3
"""writerCompany — viết bài blog theo giọng văn của từng dự án.

Hợp đồng (C1): taskEnvelope trên stdin → companyResult trên stdout. CEO không
cần biết bên trong nó chạy một phiên LLM riêng.

Khác seoCompany ở một điểm quan trọng: tiến trình con chạy với `--tools ""`,
không cầm một tool nào. Nó không đọc được web, không ghi được file, không chạy
được lệnh. Chữ nó sinh ra chỉ về tới stdout, rồi CODE ở đây mới ghi ra đĩa.

Nghĩa là kể cả khi nội dung bị lái bậy, nó cũng không tự đi đâu được — muốn lên
trang phải qua CEO, qua dispatcher, qua nút duyệt của admin.

Ba việc company này tự lo:
  · Ghi bài ra FILE, trả đường dẫn (D1). Bài dài vài nghìn chữ; nhét vào envelope
    là nghẽn CEO. Quan trọng hơn: bắt CEO chép lại nguyên văn sang lời gọi sau
    là chắc chắn có ngày nó chép sai.
  · Bắt model trả đúng khuôn, hỏng khuôn thì báo failed — không đoán.
  · Khai chi phí thật vào usage.costUsd; nó đốt hạn mức gói Pro.
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
COMPANY = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(COMPANY, "out")
sys.path.insert(0, os.path.join(COMPANY, "..", "..", "lib"))
import repoClient  # noqa: E402   (doc_du_an — danh mục dự án dùng chung)
import db  # noqa: E402

STORE = os.path.join(COMPANY, "store.sqlite")
TZ = timezone(timedelta(hours=7))


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


# ───────────────────────── dựng lời nhắc ─────────────────────────

def dung_prompt(inp: dict) -> tuple[str, dict]:
    """Lời nhắc cho phiên viết bài, ghép từ khuôn của dự án."""
    du_an = repoClient.doc_du_an(inp["duAn"])
    khuon = du_an.get("vietBai") or {}
    if not khuon:
        raise ValueError(
            f"Dự án '{inp['duAn']}' chưa khai khối 'vietBai' trong "
            f"registry/projects.yaml — chưa biết viết theo giọng nào.")

    do_dai = inp.get("doDaiTu") or khuon.get("doDaiTu", 700)
    dan_bai = khuon.get("danBai") or []

    phan = [
        f"Viết một bài blog bằng {khuon.get('ngonNgu', 'tiếng Việt')} "
        f"cho trang {du_an.get('displayName', inp['duAn'])}.",
        f"\nCHỦ ĐỀ: {inp['chuDe']}",
    ]
    if inp.get("tuKhoa"):
        phan.append(f"TỪ KHOÁ SEO cần có mặt tự nhiên: {inp['tuKhoa']}")
    if inp.get("ghiChu"):
        phan.append(f"YÊU CẦU THÊM: {inp['ghiChu']}")

    phan.append(f"\nGIỌNG VĂN:\n{khuon.get('giongVan', '').strip()}")
    if dan_bai:
        phan.append("\nDÀN BÀI — dùng đúng các mục này, mỗi mục một tiêu đề `## `:\n"
                    + "\n".join(f"  - {m}" for m in dan_bai))
    if khuon.get("cauTruc"):
        phan.append(f"\nCẤU TRÚC BẮT BUỘC:\n{khuon['cauTruc'].strip()}")
    phan.append(f"\nĐỘ DÀI: khoảng {do_dai} từ.")

    # Khuôn trả về. Bắt chặt vì code phía dưới tách theo nó — model trả tự do
    # thì không parse được, và đoán mò ở bước này là đẻ ra bài thiếu tiêu đề.
    phan.append(
        "\nĐỊNH DẠNG TRẢ VỀ — bắt buộc đúng khuôn sau, không thêm lời dẫn, "
        "không bọc trong khối mã:\n"
        "TIÊU ĐỀ: <tiêu đề bài, dưới 100 ký tự>\n"
        "TÓM TẮT: <2-3 câu, dưới 400 ký tự, dùng làm excerpt>\n"
        "---\n"
        "<thân bài, markdown: dùng ## cho mục, - cho gạch đầu dòng, "
        "**đậm** để nhấn. KHÔNG lặp lại tiêu đề bài ở đầu thân.>")
    return "\n".join(phan), khuon


def tach_ket_qua(tho: str) -> dict:
    """Tách khuôn model trả về. Thiếu phần nào thì hỏng TO, không vá tạm."""
    tho = tho.strip()
    if tho.startswith("```"):          # model đôi khi bọc trong khối mã
        tho = re.sub(r"^```[a-z]*\n|\n```$", "", tho).strip()

    tieu_de = re.search(r"^TIÊU ĐỀ:\s*(.+)$", tho, re.M)
    tom_tat = re.search(r"^TÓM TẮT:\s*(.+)$", tho, re.M)
    if not tieu_de:
        raise ValueError(
            "Phiên viết bài trả về không đúng khuôn: thiếu dòng 'TIÊU ĐỀ:'. "
            "Không đoán tiêu đề thay model — gọi lại.")

    phan = tho.split("\n---", 1)
    if len(phan) < 2 or not phan[1].strip():
        raise ValueError(
            "Phiên viết bài trả về không đúng khuôn: thiếu dấu '---' ngăn "
            "phần đầu với thân bài, hoặc thân bài rỗng.")

    return {"tieuDe": tieu_de.group(1).strip(),
            "tomTat": tom_tat.group(1).strip() if tom_tat else "",
            "than": phan[1].lstrip("-\n").strip()}


def tao_slug(chu: str) -> str:
    import unicodedata
    chu = chu.replace("đ", "d").replace("Đ", "D")
    chu = unicodedata.normalize("NFD", chu)
    chu = "".join(c for c in chu if unicodedata.category(c) != "Mn")
    chu = re.sub(r"[^a-zA-Z0-9\s-]", "", chu).strip().lower()
    return re.sub(r"[\s-]+", "-", chu)[:80] or "bai-viet"


# ───────────────────────── chạy phiên viết ─────────────────────────

def viet_bai(inp: dict, deadline_sec: int) -> tuple[dict, str, list, float]:
    prompt, _ = dung_prompt(inp)

    cmd = [
        "claude", "-p", prompt,
        # R-NHỐT — không một tool nào. Viết bài không cần đọc web, không cần ghi
        # file, không cần chạy lệnh. Cửa không dùng tới thì đừng mở.
        "--tools", "",
        "--strict-mcp-config",
        "--setting-sources", "project",
        "--max-turns", "3",
        "--output-format", "json",
        "--no-session-persistence",   # mỗi lần gọi là một phiên sạch
    ]
    proc = subprocess.run(cmd, cwd=COMPANY, capture_output=True, text=True,
                          timeout=deadline_sec)
    if proc.returncode != 0:
        raise RuntimeError(
            f"phiên viết bài thoát mã {proc.returncode}: "
            f"{(proc.stdout or proc.stderr).strip()[:250]}")

    kq = json.loads(proc.stdout)
    if kq.get("is_error"):
        raise RuntimeError(f"phiên viết bài hỏng: {str(kq.get('result'))[:250]}")

    bai = tach_ket_qua(str(kq.get("result") or ""))
    slug = tao_slug(bai["tieuDe"])
    so_tu = len(bai["than"].split())

    os.makedirs(OUT, exist_ok=True)
    ten = f"{slug}-{datetime.now(TZ):%Y%m%d-%H%M%S}.md"
    duong_dan = os.path.join(OUT, ten)
    with open(duong_dan, "w", encoding="utf-8") as fh:
        fh.write(bai["than"] + "\n")

    return (
        {"baiVietPath": duong_dan, "tieuDe": bai["tieuDe"], "slug": slug,
         "tomTat": bai["tomTat"], "soTu": so_tu},
        f"Đã viết '{bai['tieuDe']}' ({so_tu} từ) cho {inp['duAn']}. "
        f"Chưa đăng gì — bài nằm ở {ten}",
        [{"path": duong_dan, "kind": "markdown"}],
        float(kq.get("total_cost_usd") or 0.0),
    )


HANDLERS = {"vietBai": viet_bai}


def main() -> int:
    started = time.time()
    env = json.load(sys.stdin)
    task_id, trace_id = env["taskId"], env["traceId"]
    cap, inp = env["capability"], env["input"]
    policy = env.get("policy", {}) or {}
    dry_run = policy.get("dryRun", False)
    deadline = int(policy.get("maxDurationSec") or 300)

    result = {"taskId": task_id, "traceId": trace_id, "status": "failed",
              "output": None, "summary": "", "sideEffects": [], "error": None}
    chi_phi = 0.0

    conn = connect()
    conn.execute(
        "INSERT OR REPLACE INTO taskLog (taskId, traceId, capability, inputHash, "
        "status, startedAt) VALUES (?,?,?,?,?,?)",
        (task_id, trace_id, cap, env.get("_inputHash", ""), "running", now_utc()),
    )
    conn.commit()

    try:
        if cap not in HANDLERS:
            raise ValueError(f"writerCompany không có năng lực '{cap}'")
        if dry_run:  # W2
            result.update(status="ok", summary=f"[dryRun] Sẽ viết bài về "
                                               f"'{inp.get('chuDe')}' cho {inp.get('duAn')}")
        else:
            output, summary, artifacts, chi_phi = HANDLERS[cap](inp, deadline)
            result.update(status="ok", output=output, summary=summary,
                          artifacts=artifacts)

    except repoClient.RepoError as exc:
        result.update(status="failed", error=str(exc),
                      summary=f"Cấu hình dự án hỏng: {exc}")
    except subprocess.TimeoutExpired:
        result.update(status="failed", error="timeout",
                      summary=f"Viết bài quá {deadline}s chưa xong nên bị cắt.")
    except ValueError as exc:
        result.update(status="needsInput", error=str(exc), summary=str(exc))
    except Exception as exc:  # O3
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}",
                      summary=f"writerCompany hỏng khi chạy {cap}.")

    duration = int((time.time() - started) * 1000)
    result["usage"] = {"steps": 1, "durationMs": duration, "costUsd": chi_phi}

    conn.execute(
        "UPDATE taskLog SET status=?, summary=?, finishedAt=?, durationMs=?, costUsd=? "
        "WHERE taskId=?",
        (result["status"], result["summary"], now_utc(), duration, chi_phi, task_id),
    )
    conn.execute(
        "INSERT INTO eventLog (taskId, traceId, eventType, payloadJson, createdAt) "
        "VALUES (?,?,?,?,?)",
        (task_id, trace_id, f"capability.{cap}",
         json.dumps({"status": result["status"], "costUsd": chi_phi},
                    ensure_ascii=False), now_utc()),
    )
    conn.commit()
    conn.close()

    json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
