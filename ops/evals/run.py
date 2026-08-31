#!/usr/bin/env python3
"""Chạy bộ ca thử cho CEO và chấm — lưới an toàn cho mọi thay đổi ở SYSTEM.md.

    python3 ops/evals/run.py                 # chạy hết
    python3 ops/evals/run.py --only chi-ck   # chạy một ca (chạy hết thì tốn tiền)
    python3 ops/evals/run.py --liet-ke       # xem có ca nào, không tốn gì

NÓ ĐO CÁI GÌ: CEO nhận một câu của admin thì bắn ra những lời gọi nào. Không đo
văn phong, không đo câu trả lời — hai thứ đó người đọc là biết. Thứ không nhìn
bằng mắt được là chuỗi lời gọi phía sau, và đó đúng là chỗ mọi bug đắt tiền của
dự án này đã nấp: ghi sổ mà quên trừ ví, trừ ví hai lần, gọi bằng tên trường
không có trong manifest.

ĐO THÊM ĐƯỢC TỪ 2026-08-18:
  · **Nhiều lượt.** Ca có khoá `luot:` sẽ chạy nối tiếp trong CÙNG một phiên
    (`--resume`), mỗi lượt chấm riêng. Đây là chỗ những bug đắt nhất còn lại
    đang nấp: bấm duyệt xong làm tiếp, admin trả lời câu hỏi rồi mới đủ dữ
    kiện, hoặc CEO làm lại việc đã làm ở lượt trước.
  · **Câu chữ.** `phaiNoi` / `khongDuocNoi` soát nội dung CEO nói với admin, và
    luật "không Markdown" được soát TỰ ĐỘNG cho mọi ca — SYSTEM.md cấm Markdown
    vì Telegram hiện nó ra thành ký tự thô, nhưng cho tới nay chưa ai đo.
  · **Sổ tay.** Prompt được dựng đúng như bản chạy thật, gồm cả sổ tay mà router
    của gateway chọn (`chon_so_tay`). Không có phần này thì ca thử đo một CEO
    KHÁC với CEO admin đang dùng — vô dụng theo cách khó phát hiện nhất.

NÓ VẪN KHÔNG ĐO ĐƯỢC CÁI GÌ — nói trước để đừng ai tin quá:
  · Không đo được company chạy đúng hay sai. Ở đây company không hề chạy.
  · Không đo được chất lượng SUY NGHĨ, chỉ đo được vài luật câu chữ tra được.
  · Model không tất định. Một ca trượt một lần chưa phải bằng chứng; chạy lại
    ca đó vài lần trước khi đi sửa prompt.

TỐN TIỀN THẬT. Mỗi ca là một phiên CEO đầy đủ, ăn vào cùng gói Pro với việc
thật. Số đo in ở cuối mỗi lần chạy, VÀ ghi vào `ceoRunLog` dưới traceId bắt đầu
bằng `evl_` để `backoffice usage` tách riêng ra được.

VÌ SAO PHẢI GHI SỔ — bản trước KHÔNG ghi, và câu docstring ở đây từng khẳng
định ngược lại rằng chi phí "ăn vào đúng cầu dao L7 đang đếm". Đo 2026-08-18:
sổ ghi $0,95 trong khi ca thử tiêu $2,64. Admin đọc `usage` sau một đêm chạy
eval sẽ thấy con số thấp hơn thực tế gần ba lần — đúng loại lỗi O10, số liệu
sai theo hướng trấn an. Nay ghi đủ, nhưng gắn nhãn để "chi cho việc thật" và
"chi cho việc tự kiểm" không bị trộn thành một con số vô nghĩa.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SANDBOX = os.path.join(HERE, "shim")
CASES = os.path.join(HERE, "cases.yaml")

sys.path.insert(0, os.path.join(ROOT, "ops"))
import gateway  # noqa: E402  — dùng ĐÚNG hàm dựng prompt của bản chạy thật
import nao  # noqa: E402  — để đo được cả bộ não dự phòng, không chỉ Claude

# Secret phải biến mất khỏi phiên ca thử. Lớp chặn số 2 (xem docstring của
# shim): kể cả có ai chạy được company thật thì nó cũng không đăng nhập nổi.
SECRETS = ["NOTION_TOKEN", "TELEGRAM_BOT_TOKEN", "SUPABASE_KEY",
           "SUPABASE_SERVICE_KEY", "GITHUB_TOKEN", "ANTHROPIC_API_KEY",
           # Khoá model: tiến trình con (dispatcher giả) không cần, và không
           # được cầm. Nhưng tiến trình CHA thì cần khi đo bộ não dự phòng —
           # nó gọi nhà cung cấp ngay trong process này, xem `nap_khoa_nao`.
           "GEMINI_API_KEY", "GROQ_API_KEY", "CEREBRAS_API_KEY",
           "OPENROUTER_API_KEY", "MISTRAL_API_KEY", "XAI_API_KEY",
           "OPENAI_API_KEY"]


def system_prompt(co_profile: bool) -> str:
    """Prompt y hệt bản chạy thật.

    Dựng lại bằng tay thì ca thử sẽ đo một CEO khác với CEO admin đang dùng —
    vô dụng theo cách khó phát hiện nhất. Nên gọi thẳng hàm của gateway.
    """
    with open(gateway.SYSTEM_PROMPT, encoding="utf-8") as fh:
        s = fh.read()
    return s + gateway.danh_muc_block() + (gateway.profile_block() if co_profile else "")


def cac_luot(ca: dict) -> list:
    """Ca một lượt và ca nhiều lượt về chung một dạng.

    Ca cũ viết `cauAdmin:` phẳng; ca mới viết `luot:` là danh sách. Quy về một
    dạng ngay tại đây để phần chạy và phần chấm chỉ phải biết MỘT hình.
    """
    if ca.get("luot"):
        return ca["luot"]
    return [{k: ca[k] for k in
             ("cauAdmin", "phaiGoi", "khongDuocGoi", "toiDaLoiGoi",
              "phaiNoi", "khongDuocNoi", "traVe") if k in ca}]


def ghi_so(sid: str, data: dict) -> None:
    """Ghi một lượt ca thử vào `ceoRunLog`, gắn nhãn `evl_`.

    Dùng ĐÚNG bảng của việc thật chứ không dựng bảng riêng: hai bảng thì sớm
    muộn ai đó cộng một bảng rồi tưởng đã cộng hết. Phân biệt bằng tiền tố
    traceId, và `spent_since()` tách ra khi báo cáo.
    """
    try:
        conn = gateway.db.connect(
            os.path.join(ROOT, "backOffice", "store.sqlite"))
        u = data.get("usage") or {}
        conn.execute(
            "INSERT INTO ceoRunLog (traceId, sessionId, numTurns, durationMs, "
            "cacheCreationTokens, cacheReadTokens, costUsd, isError, createdAt, loi) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("evl_" + sid.replace("-", "")[:20], sid,
             data.get("num_turns", 0), data.get("duration_ms", 0),
             u.get("cache_creation_input_tokens", 0),
             u.get("cache_read_input_tokens", 0),
             float(data.get("total_cost_usd") or 0.0),
             int(bool(data.get("is_error"))), gateway.now(),
             str(data.get("result") or "")[:400] if data.get("is_error") else None))
        conn.commit()
        conn.close()
    except Exception as exc:
        # Không nuốt: ghi sổ hỏng thì nói ra. Im ở đây là quay lại đúng cái
        # điểm mù vừa vá — chỉ khác là lần này ta biết nó tồn tại.
        print(f"   (không ghi được chi phí vào sổ: {exc})", file=sys.stderr)


def mot_luot(cmd_base: list, loi_nhac: str, stub: dict, log_path: str,
             sid: str, nao_phu: dict = None) -> dict:
    """Chạy đúng một lượt và trả về những gì lượt đó bắn ra.

    `nao_phu` khác None thì lượt này chạy trên BỘ NÃO DỰ PHÒNG thay vì
    `claude -p`. Vì sao phải đo được cả hai: bản đầu của bộ ca thử tự dựng lệnh
    `claude -p`, nên nó chỉ biết đo đúng một bộ não — mà câu hỏi đáng tiền nhất
    lại là "não phụ làm được việc tới đâu so với Claude". Bộ đo mà không với
    tới thứ cần đo thì nó đang tự khen chính đường nó đi.
    """
    open(log_path, "w").close()          # log sạch để calls thuộc đúng lượt này
    env = {k: v for k, v in os.environ.items() if k not in SECRETS}
    env.update({
        "COMPANYSPEC_EVAL_ROOT": ROOT,
        "COMPANYSPEC_EVAL_LOG": log_path,
        "COMPANYSPEC_EVAL_STUB": json.dumps(stub or {}, ensure_ascii=False),
    })
    # Prompt y hệt bản chạy thật: câu admin CỘNG sổ tay do router chọn. Gateway
    # nối sổ tay vào tin nhắn (không vào system prompt) để giữ cache, nên ở đây
    # cũng phải nối vào tin nhắn — khác một chỗ là đo nhầm chỗ đó.
    sach, ten_sach = gateway.so_tay_block(loi_nhac)

    if nao_phu is not None:
        # Dispatcher GIẢ truyền bằng THAM SỐ, không bằng biến môi trường: một
        # biến đổi được cổng ra thì sớm muộn thành lỗ hổng thật ở đường chạy.
        kq = nao.chay(
            loi_nhac + sach, system_prompt=nao_phu["system_prompt"],
            lich_su=nao_phu["lich_su"], trace_id=f"evl_{sid[:8]}",
            session_id=sid, timeout=300,
            dispatch_py=os.path.join(SANDBOX, "ops", "dispatch.py"),
            cwd=SANDBOX, env_them={k: env[k] for k in env
                                   if k.startswith("COMPANYSPEC_EVAL")})
        calls = []
        with open(log_path, encoding="utf-8") as fh:
            for dong in fh:
                if dong.strip():
                    calls.append(json.loads(dong))
        ghi_so(sid, kq)
        # Trí nhớ giữa các lượt: Claude dùng --resume, não phụ thì phải tự
        # mang lịch sử theo. Không mang thì ca nhiều lượt đo nhầm — nó thành
        # hai ca một lượt đứng cạnh nhau.
        nao_phu["lich_su"] = (nao_phu["lich_su"]
                              + [{"vaiTro": "admin", "noiDung": loi_nhac},
                                 {"vaiTro": "bot",
                                  "noiDung": (kq.get("result") or "")[:1200]}])
        return {"calls": calls,
                "loiPhien": (kq.get("result") or "")[:300]
                            if kq.get("is_error") else None,
                "traLoi": (kq.get("result") or "")[:3000],
                "chiPhi": 0.0, "tienVnd": kq.get("tienVnd", 0.0),
                "soTay": ten_sach}

    proc = subprocess.run(cmd_base, cwd=SANDBOX, capture_output=True, text=True,
                          input=loi_nhac + sach, timeout=600, env=env)
    calls = []
    with open(log_path, encoding="utf-8") as fh:
        for dong in fh:
            if dong.strip():
                calls.append(json.loads(dong))
    try:
        data = json.loads(proc.stdout)
    except Exception:
        # O10 — phiên hỏng thì nói ra, đừng coi như "không gọi gì cả" rồi chấm
        # cho qua những ca mà đáp án đúng là im lặng.
        return {"calls": calls, "loiPhien": (proc.stderr or proc.stdout)[:300],
                "traLoi": "", "chiPhi": 0.0, "soTay": ten_sach}
    ghi_so(sid, data)
    return {
        "calls": calls,
        "loiPhien": data.get("result", "")[:300] if data.get("is_error") else None,
        # KHÔNG cắt 400 nữa: từ nay `khongDuocNoi` soát cả câu, mà lỗi câu chữ
        # thì hay nằm ở đoạn cuối — đúng đoạn bản cũ cắt mất.
        "traLoi": (data.get("result") or "")[:3000],
        "chiPhi": float(data.get("total_cost_usd") or 0.0),
        "soTay": ten_sach,
    }


def chay_mot_ca(ca: dict, co_profile: bool, nao_phu: dict = None) -> list:
    """Chạy hết các lượt của một ca trong CÙNG một phiên. Trả kết quả từng lượt."""
    log = tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8")
    log.close()
    sid = str(uuid.uuid4())
    ket_qua = []
    for i, luot in enumerate(cac_luot(ca)):
        cmd = [
            "claude", "-p",
            "--system-prompt", system_prompt(co_profile),
            "--settings", gateway.SETTINGS,   # deny list + hook guard y như thật
            "--output-format", "json",
            "--tools", "Bash",
            "--strict-mcp-config",
            "--setting-sources", "project",
            "--max-turns", "12",
        ]
        # Lượt đầu mở phiên, các lượt sau NỐI vào đúng phiên đó — đây là toàn
        # bộ điểm khác biệt của ca nhiều lượt. Phiên mới mỗi lượt thì ta lại đo
        # đúng cái cũ đã đo, chỉ tốn tiền hơn.
        cmd += ["--session-id", sid] if i == 0 else ["--resume", sid]
        kq = mot_luot(cmd, luot["cauAdmin"],
                      luot.get("traVe") or ca.get("traVe") or {}, log.name, sid,
                      nao_phu)
        kq["cauAdmin"] = luot["cauAdmin"]
        kq["mong"] = luot
        ket_qua.append(kq)
        if kq["loiPhien"]:
            break                    # phiên chết thì lượt sau vô nghĩa
    os.unlink(log.name)
    return ket_qua


# Dấu hiệu Markdown mà Telegram KHÔNG dựng lại được, nên admin nhìn thấy ký tự
# thô. SYSTEM.md cấm từ đầu, nhưng cấm bằng lời dặn thì không ai đo — nên tới
# giờ không ai biết CEO có nghe hay không.
MARKDOWN = [
    (re.compile(r"\*\*"),          "chữ đậm **…**"),
    (re.compile(r"^#{1,6} ", re.M), "tiêu đề ##"),
    (re.compile(r"`"),             "dấu backtick"),
    (re.compile(r"^\s*\|.*\|", re.M), "bảng Markdown"),
]


def cham_cau_chu(mong: dict, tra_loi: str) -> list:
    """Soát CÂU CHỮ CEO nói với admin — phần bộ ca thử cũ cố ý bỏ trống.

    Không đo được "câu này hay không" bằng code, và cũng không định đo. Chỉ đo
    những luật đã viết thành chữ trong SYSTEM.md và tra được bằng máy. Ba thứ:
    Markdown (Telegram hiện ra ký tự thô), câu bắt buộc phải có, câu cấm nói.

    `khongDuocNoi` là cột đáng giá nhất: nó bắt được kiểu hỏng mà `phaiGoi`
    chịu thua — CEO nói "đã ghi rồi ạ" trong khi không gọi gì cả. Chuỗi lời gọi
    lúc đó rỗng đúng như ca "không được gọi", nên ca vẫn ĐẠT, còn admin thì tin
    là việc đã xong.
    """
    loi = []
    if not tra_loi:
        return loi
    for mau, ten in MARKDOWN:
        if mau.search(tra_loi):
            loi.append(f"câu chữ: dùng {ten} — Telegram hiện ra ký tự thô")
    for can in mong.get("phaiNoi") or []:
        if can.lower() not in tra_loi.lower():
            loi.append(f"câu chữ: phải nhắc tới {can!r}")
    for cam in mong.get("khongDuocNoi") or []:
        if cam.lower() in tra_loi.lower():
            loi.append(f"câu chữ: KHÔNG được nói {cam!r}")
    return loi


def cham(ca: dict, calls: list) -> list:
    """Trả về danh sách lỗi. Rỗng = đạt."""
    loi = []
    da_goi = [f"{c['company']}.{c['capability']}" for c in calls]

    for mong in ca.get("phaiGoi") or []:
        ten = mong["goi"]
        khop = [c for c in calls if f"{c['company']}.{c['capability']}" == ten]
        if not khop:
            loi.append(f"thiếu lời gọi {ten}")
            continue
        for truong, cho_doi in (mong.get("truong") or {}).items():
            thay = [c["input"].get(truong) for c in khop]
            if all(v is None for v in thay):
                loi.append(f"{ten}: thiếu trường '{truong}'")
            elif isinstance(cho_doi, str) and cho_doi.startswith("~"):
                # "~abc" = chuỗi phải CHỨA abc. Dùng cho nội dung tự do: câu chữ
                # do model đặt thì không so bằng nhau được, nhưng vẫn phải giữ
                # đúng những mẩu admin đã gõ.
                can = cho_doi[1:]
                if not any(isinstance(v, str) and can in v for v in thay):
                    loi.append(f"{ten}.{truong}: phải chứa {can!r}, nhận {thay!r}")
            elif cho_doi != "*" and cho_doi not in thay:
                loi.append(f"{ten}.{truong}: cần {cho_doi!r}, nhận {thay!r}")

    for cam in ca.get("khongDuocGoi") or []:
        if cam in da_goi:
            loi.append(f"KHÔNG được gọi {cam} nhưng đã gọi")

    tran = ca.get("toiDaLoiGoi")
    if tran is not None and len(calls) > tran:
        loi.append(f"gọi {len(calls)} lần, quá trần {tran}")

    # Lời gọi bị cổng từ chối là hỏng thật, kể cả khi phần trên đã đạt: ngoài
    # đời nó thành một vòng đi-về vô ích, và đúng dạng bug "sai tên trường".
    for c in calls:
        if c.get("status") == "rejected":
            loi.append(f"{c['company']}.{c['capability']} bị từ chối: "
                       f"{c.get('loi') or c.get('vi')}")
    return loi


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="chỉ chạy ca có id này; nhiều ca thì ngăn bằng dấu phẩy")
    ap.add_argument("--nao", choices=("claude", "phu"), default="claude",
                    help="bộ não đem ra đo. phu = chuỗi dự phòng trong "
                         "registry/models.yaml (TỐN TIỀN THẬT nếu chuỗi có "
                         "nhà tính tiền), claude = tốn hạn mức gói Pro")
    ap.add_argument("--liet-ke", action="store_true", help="xem danh sách ca, không chạy")
    ap.add_argument("--khong-profile", action="store_true",
                    help="chạy không nạp PROFILE.md (mặc định có, cho giống thật)")
    args = ap.parse_args()

    with open(CASES, encoding="utf-8") as fh:
        cases = yaml.safe_load(fh)["cases"]
    if args.only:
        muon = [x.strip() for x in args.only.split(",") if x.strip()]
        cases = [c for c in cases if c["id"] in muon]
        # Gõ sai một id thì nói ra. Lặng lẽ chạy 3 ca khi người ta gọi 4 ca là
        # kiểu hỏng đúng bằng cách tệ nhất: báo cáo "tất cả đều đạt".
        thieu = set(muon) - {c["id"] for c in cases}
        if thieu:
            print(f"không có ca nào tên: {', '.join(sorted(thieu))}")
            return 1

    if args.liet_ke:
        for c in cases:
            lu = cac_luot(c)
            nhan = f"[{len(lu)} lượt] " if len(lu) > 1 else ""
            print(f"  {c['id']:32} {nhan}{lu[0]['cauAdmin']}")
        print(f"\n{len(cases)} ca.")
        return 0

    dat, tong_chi = 0, 0.0
    for i, ca in enumerate(cases, 1):
        luot = cac_luot(ca)
        nhan = f" ({len(luot)} lượt)" if len(luot) > 1 else ""
        print(f"\n[{i}/{len(cases)}] {ca['id']}{nhan}", flush=True)

        # Mỗi ca một `lich_su` MỚI: các lượt trong một ca chia chung phiên,
        # nhưng hai ca khác nhau thì phải trắng trí nhớ của nhau, y như hai
        # cuộc trò chuyện khác nhau ngoài đời.
        # Nạp ops/.env vào tiến trình CHA — não phụ gọi nhà cung cấp ngay
        # trong process này. Không nạp thì mọi ca "hỏng phiên: chưa có
        # GEMINI_API_KEY", và bộ đo sẽ báo 0/6 vì thiếu khoá chứ không phải vì
        # model kém: một con số sai theo hướng CHÊ, khó ngờ y như sai theo
        # hướng khen. Tiến trình con vẫn bị tước sạch khoá (xem SECRETS).
        if args.nao == "phu":
            gateway.nap_env()
        nao_phu = ({"system_prompt": system_prompt(not args.khong_profile),
                    "lich_su": []} if args.nao == "phu" else None)
        ket_qua = chay_mot_ca(ca, co_profile=not args.khong_profile,
                              nao_phu=nao_phu)
        loi_ca, hong = [], False
        for n, kq in enumerate(ket_qua, 1):
            tong_chi += kq["chiPhi"]
            dau = f"  lượt {n}" if len(luot) > 1 else "  "
            print(f"{dau} admin: {kq['cauAdmin']!r}"
                  f"   [sổ tay: {','.join(kq['soTay']) or 'không'}]")
            for c in kq["calls"]:
                print(f"      → {c['company']}.{c['capability']} "
                      f"{json.dumps(c['input'], ensure_ascii=False)}")
            if not kq["calls"]:
                print("      → (không gọi company nào)")
            if kq["loiPhien"]:
                print(f"   HỎNG PHIÊN: {kq['loiPhien']}")
                hong = True
                break
            # Lỗi của lượt nào thì gắn tên lượt đó — ca 3 lượt mà chỉ in
            # "thiếu lời gọi X" thì không biết đi sửa chỗ nào.
            tien_to = f"lượt {n}: " if len(luot) > 1 else ""
            loi_ca += [tien_to + l for l in cham(kq["mong"], kq["calls"])]
            loi_ca += [tien_to + l for l in cham_cau_chu(kq["mong"], kq["traLoi"])]

        if hong:
            continue
        if loi_ca:
            print("   TRƯỢT")
            for l in loi_ca:
                print(f"      · {l}")
            print(f"      CEO đáp: {ket_qua[-1]['traLoi'][:200]!r}")
        else:
            dat += 1
            chi = sum(k["chiPhi"] for k in ket_qua)
            print(f"   ĐẠT  (${chi:.4f})")

    print(f"\n{dat}/{len(cases)} ca đạt · tốn ${tong_chi:.4f}")
    print("Đã ghi vào sổ dưới nhãn `evl_`; xem tách riêng bằng:")
    print("  python3 backOffice/src/backoffice.py usage")
    return 0 if dat == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
