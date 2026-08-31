#!/usr/bin/env python3
"""Gọi model qua giao diện OpenAI-compatible — nhiều nhà, một hàm. Dùng chung.

C4.2 — file này chỉ biết "gọi một model thế nào", KHÔNG biết ai gọi và để làm
gì. Không có quyết định nghiệp vụ nào ở đây: chọn nhà nào, chấp nhận trả tiền
hay không, hỏng thì nói gì với admin — đều là việc của tầng trên.

VÌ SAO TỰ VIẾT CHỨ KHÔNG DỰNG PROXY: ý tưởng lấy từ ProxyGateLLM — gom nhiều
nhà cung cấp sau một endpoint OpenAI rồi tự chuyển khi một bên hỏng. Nhưng bản
của họ là một server Node chạy thường trực: thêm một tiến trình để hỏng, thêm
một cổng mở trên máy admin, thêm một chỗ nữa giữ khoá. Phần thật sự cần chỉ là
mấy chục dòng HTTP, vì HÀNG CHỤC NHÀ ĐỀU NÓI CHUNG MỘT GIAO THỨC —
POST /chat/completions, cùng hình dáng messages và tool_calls. Đổi nhà là đổi
baseUrl với tên khoá, không phải đổi mã.

CHỈ DÙNG THƯ VIỆN CHUẨN, cùng lý do với lib/notionClient.py: kéo SDK về chỉ để
gọi một endpoint là đổi một phụ thuộc lấy tiện lợi không đáng.

CHƯA ĐO ĐƯỢC GÌ NHIỀU ở file này (viết 2026-08-27). Con số duy nhất đáng tin là
thứ `ops/nao.py kiem` in ra lúc chạy thật; mọi giá tiền trong registry/models.yaml
đều là tra tài liệu, chưa đối chiếu hoá đơn.
"""
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

import quotaSignal  # cùng tầng lib/ — C4.1

# Đường mặc định tới danh sách nhà. Đặt tương đối theo VỊ TRÍ FILE NÀY, không
# theo thư mục làm việc: company chạy bằng đường dẫn tuyệt đối do dispatcher
# dựng, còn cwd thì mỗi nơi một khác.
CAU_HINH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "registry", "models.yaml")


class LLMError(RuntimeError):
    """Một lời gọi hỏng. Mang theo ĐỦ thứ để tầng trên quyết định, không chỉ câu chữ.

    nha/model  — hỏng ở đâu, để chuỗi dự phòng còn biết đường bỏ qua.
    ma         — mã HTTP, hoặc None khi hỏng trước lúc chạm tới server.
    het_luot   — 429. Khác hẳn "sai khoá": chờ là chạy lại được.
    """

    def __init__(self, message, *, nha="", model="", ma=None, het_luot=False):
        super().__init__(message)
        self.nha, self.model, self.ma, self.het_luot = nha, model, ma, het_luot


def nap(path: str = "") -> dict:
    """Đọc registry/models.yaml. Hỏng thì NÉM, đừng trả dict rỗng.

    O10 — file cấu hình hỏng mà trả {} thì tầng trên thấy "không có nhà nào" và
    kết luận "chưa cấu hình", trong khi sự thật là "cấu hình có mà đọc sai".
    Hai chuyện đó cần hai câu trả lời khác nhau cho admin.
    """
    import yaml                       # nạp muộn: chỉ file này cần, không bắt cả lib
    p = path or CAU_HINH
    if not os.path.isfile(p):
        raise LLMError(f"Không thấy danh sách model ở {p}.")
    with open(p, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    if not isinstance(cfg, dict) or not cfg.get("nha"):
        raise LLMError(f"{p} không có mục `nha` nào.")
    return cfg


def khoa_cua(nha_cfg: dict) -> str:
    """Khoá của một nhà, lấy từ môi trường. Nhà không cần khoá thì trả chuỗi rỗng.

    Trả chuỗi rỗng cho CẢ HAI trường hợp "không cần khoá" và "cần mà chưa có" là
    con bug O10 kinh điển, nên chỗ gọi phải dùng thieu_khoa() để phân biệt.
    """
    ten = nha_cfg.get("khoaEnv")
    return os.environ.get(ten, "") if ten else ""


def thieu_khoa(nha_cfg: dict) -> bool:
    ten = nha_cfg.get("khoaEnv")
    return bool(ten) and not os.environ.get(ten)


def la_cli(nha_cfg: dict) -> bool:
    """Nhà này chạy bằng LỆNH trên máy chứ không bằng HTTP.

    Đúng một nhà như thế: Claude của gói Pro. Anthropic không phát khoá API cho
    gói thuê bao — thứ admin trả tiền là lệnh `claude` đã đăng nhập sẵn. Nên
    muốn Claude ngồi ghế chủ toạ thì phải gọi qua CLI, không có đường HTTP nào.
    """
    return (nha_cfg or {}).get("kieu") == "cli"


def tien_vnd(usage: dict, nha_cfg: dict) -> float:
    """Quy token ra đồng theo giá khai trong models.yaml. Nhà miễn phí ra 0."""
    vao = (usage or {}).get("prompt_tokens") or 0
    ra = (usage or {}).get("completion_tokens") or 0
    return round((vao * float(nha_cfg.get("giaVao") or 0)
                  + ra * float(nha_cfg.get("giaRa") or 0)) / 1_000_000, 2)


def boc_json(chu: str):
    """Bóc một khối JSON ra khỏi văn model. Không có thì trả None.

    Model được dặn "trả về đúng một khối JSON" vẫn thường gói nó trong rào
    ```json, hoặc viết một câu dẫn trước khi mở ngoặc. Đây là chỗ chịu đựng
    thói quen đó, và nó CHỈ bóc — không phán xét bên trong có gì; việc đó thuộc
    về người gọi, vì mỗi nơi chờ một hình dạng khác nhau.

    GOM VỀ MỘT CHỖ (2026-08-31): đúng tám dòng này từng nằm hai bản, một trong
    `ops/nao.py` và một trong `hoiDongCompany`. Chép hai bản thì sớm muộn một
    bản học được cách bóc một định dạng lạ mà bản kia không — và cái hỏng sẽ
    chỉ hiện ra ở một trong hai đường, tức là loại lỗi khó ngờ nhất.
    """
    kho = chu or ""
    if "```" in kho:
        kho = max(kho.split("```"), key=len)
        if kho.lstrip().startswith("json"):
            kho = kho.lstrip()[4:]
    dau, cuoi = kho.find("{"), kho.rfind("}")
    if dau < 0 or cuoi <= dau:
        return None
    try:
        d = json.loads(kho[dau:cuoi + 1])
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


def _doc_loi(exc: urllib.error.HTTPError) -> str:
    """Moi câu lỗi nhà cung cấp thật sự nói ra, thay vì in "HTTP 400" trống trơn.

    Cùng loại lỗi với _ly_do_chet bên gateway: server báo lỗi trong THÂN phản
    hồi, đọc nhầm chỗ thì admin nhận một con số không sửa được gì.
    """
    try:
        than = exc.read().decode("utf-8", "replace")[:600]
    except Exception:
        return ""
    try:
        d = json.loads(than)
    except ValueError:
        return than[:400]

    # THÂN LỖI KHÔNG PHẢI LÚC NÀO CŨNG LÀ MỘT OBJECT. Đo thật 2026-08-27:
    # Gemini lúc quá tải trả HTTP 503 với thân là một MẢNG `[{"error": {...}}]`.
    # Bản đầu gọi thẳng `d.get("error")` nên nó ném AttributeError — tức là bộ
    # đọc lỗi tự vỡ trong lúc đang đọc lỗi, và lỗi mới đó KHÔNG phải LLMError
    # nên chuỗi dự phòng không bắt được, không nhảy nhà nào cả.
    # Đúng chỗ tệ nhất để hỏng: nó chỉ chạy khi có thứ khác đã hỏng trước.
    if isinstance(d, list):
        d = next((x for x in d if isinstance(x, dict)), {})
    if not isinstance(d, dict):
        return than[:400]
    loi = d.get("error")
    if isinstance(loi, dict):
        return str(loi.get("message") or than)[:400]
    return str(loi or than)[:400]


def _phang(messages: list) -> tuple:
    """Gộp danh sách messages thành (system_prompt, một khối chữ).

    CLI chỉ nhận MỘT prompt, không nhận mảng lượt. Nên phần hội thoại phải dán
    lại thành chữ có nhãn. Mất định dạng lượt, đổi lại giữ được nội dung —
    và với việc chốt phương án (một câu hỏi, vài ý kiến) thì không cần lượt.
    """
    he = "\n\n".join(m["content"] for m in messages
                     if m.get("role") == "system" and m.get("content"))
    dong = []
    for m in messages:
        vai = m.get("role")
        if vai == "system" or not m.get("content"):
            continue
        dong.append(("Bạn đã trả lời:\n" if vai == "assistant" else "")
                    + m["content"])
    return he, "\n\n".join(dong)


def _goi_cli(*, nha_cfg: dict, nha: str, model: str, messages: list,
             timeout: int, settings: str = "") -> dict:
    """Gọi Claude qua lệnh `claude -p`. Tiêu HẠN MỨC GÓI PRO, không tiêu tiền.

    Vì thế `tienVnd` luôn là 0 còn `costUsd` mang con số CLI tự tính. Trộn hai
    thứ đó vào một cột là làm hỏng đúng phép đối chiếu hoá đơn mà sổ
    `chiTieuNgoai` sinh ra để phục vụ.

    KHÔNG CÓ TOOL NÀO (`--tools ''`). Ở đây Claude chỉ đọc chữ rồi viết chữ;
    mọi tác động ra ngoài vẫn phải đi qua dispatcher ở tầng trên. Một phiên
    ngồi ghế chủ toạ mà cầm được Bash thì nó không còn là chủ toạ nữa.

    Nội dung đi qua STDIN chứ không làm tham số của `-p` — cùng bài học với
    gateway: chuỗi bắt đầu bằng dấu trừ sẽ bị CLI hiểu thành tên tuỳ chọn.
    """
    he, than = _phang(messages)
    argv = [nha_cfg.get("lenh") or "claude", "-p",
            "--output-format", "json",
            "--tools", "",
            "--strict-mcp-config",
            "--setting-sources", "project",
            "--max-turns", "1",
            "--no-session-persistence"]
    if he:
        argv += ["--system-prompt", he]
    if model:
        argv += ["--model", model]
    if settings:
        argv += ["--settings", settings]

    bat_dau = time.monotonic()
    try:
        proc = subprocess.run(argv, input=than, capture_output=True, text=True,
                              timeout=timeout)
    except FileNotFoundError:
        raise LLMError(f"{nha}: không thấy lệnh {argv[0]} trên máy",
                       nha=nha, model=model)
    except subprocess.TimeoutExpired:
        raise LLMError(f"{nha}/{model}: quá {timeout}s không trả lời",
                       nha=nha, model=model)

    try:
        d = json.loads(proc.stdout)
    except ValueError:
        raise LLMError(f"{nha}/{model}: CLI trả về thứ không đọc được — "
                       + (proc.stderr or proc.stdout or "")[-300:],
                       nha=nha, model=model)

    chu = str(d.get("result") or "").strip()
    # HẾT HẠN MỨC phải nhận ra cho bằng được, vì đây chính là ca mà cả cơ chế
    # dự phòng sinh ra để đỡ: `het_luot=True` là tín hiệu cho tầng trên đổi
    # sang một model miễn phí thay vì bỏ luôn cuộc họp.
    hit = quotaSignal.phat_hien(chu + " " + (proc.stderr or ""),
                                d.get("api_error_status"))
    if d.get("is_error") or proc.returncode != 0 or hit:
        raise LLMError(
            f"{nha}/{model}: " + (quotaSignal.cau_bao_admin(hit) if hit
                                  else (chu or (proc.stderr or "")[-300:]
                                        or f"thoát mã {proc.returncode}")),
            nha=nha, model=model, het_luot=bool(hit))
    if not chu:
        raise LLMError(f"{nha}/{model}: phiên không trả về nội dung nào",
                       nha=nha, model=model)

    u = d.get("usage") or {}
    return {"chu": chu, "goiTool": [], "lyDoDung": d.get("stop_reason") or "",
            "usage": {"prompt_tokens": u.get("input_tokens") or 0,
                      "completion_tokens": u.get("output_tokens") or 0},
            "tienVnd": 0.0, "costUsd": float(d.get("total_cost_usd") or 0.0),
            "nha": nha, "model": model,
            "giay": round(time.monotonic() - bat_dau, 2)}


def goi(*, nha: str, model: str, messages: list, cfg: dict,
        tools: list = None, timeout: int = 60, max_tokens: int = 1500,
        temperature: float = 0.3, settings: str = "") -> dict:
    """Một lời gọi tới một model. Trả dict, hỏng thì ném LLMError.

    Trả về:
      chu       — phần chữ model viết (có thể rỗng khi nó chỉ gọi tool)
      goiTool   — [{id, ten, thamSo}] đã tách sẵn, thamSo là dict đã parse
      usage     — nguyên văn của nhà cung cấp
      tienVnd   — quy ra đồng theo bảng giá; nhà miễn phí thì 0
      giay      — thời gian thật của lời gọi này

    tools theo đúng định dạng OpenAI. Nhà nào không hỗ trợ gọi tool thì thường
    vẫn nhận tham số rồi lờ đi — nên tầng trên PHẢI đọc được cả trường hợp model
    trả lời bằng chữ thuần.
    """
    nha_cfg = (cfg.get("nha") or {}).get(nha)
    if not nha_cfg:
        raise LLMError(f"models.yaml không khai nhà {nha}.", nha=nha, model=model)
    if la_cli(nha_cfg):
        return _goi_cli(nha_cfg=nha_cfg, nha=nha, model=model,
                        messages=messages, timeout=timeout, settings=settings)
    if thieu_khoa(nha_cfg):
        raise LLMError(f"thiếu {nha_cfg['khoaEnv']} trong môi trường",
                       nha=nha, model=model)

    body = {"model": model, "messages": messages,
            "max_tokens": max_tokens, "temperature": temperature}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"

    khoa = khoa_cua(nha_cfg)
    dau = {"Content-Type": "application/json; charset=utf-8",
           # PHẢI TỰ KHAI TÊN. urllib mặc định gửi `Python-urllib/3.10`, và
           # tường lửa của nhà cung cấp coi đó là bot: đo thật 2026-08-31, groq
           # và cerebras đều trả `HTTP 403 — error code: 1010` (mã của
           # Cloudflare, nghĩa là chặn theo chữ ký trình khách). Đổi đúng một
           # dòng header thì cùng lời gọi đó đi lọt tới tận API và trả về lỗi
           # thật ("model không tồn tại") — tức là khoá vẫn tốt, chỉ là chưa
           # bao giờ được chào hỏi tử tế.
           #
           # Kiểu hỏng này rất dễ lần nhầm: 403 trông như sai khoá, và người ta
           # sẽ đi tạo lại khoá mấy lần trước khi nghĩ tới header.
           "User-Agent": "companySpec/0.1 (personal assistant; python-urllib)"}
    if khoa:
        dau["Authorization"] = f"Bearer {khoa}"
    req = urllib.request.Request(
        nha_cfg["baseUrl"].rstrip("/") + "/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=dau, method="POST")

    bat_dau = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise LLMError(f"{nha}/{model}: HTTP {exc.code} — {_doc_loi(exc)}",
                       nha=nha, model=model, ma=exc.code,
                       het_luot=exc.code == 429)
    except urllib.error.URLError as exc:
        raise LLMError(f"{nha}/{model}: không nối được — {exc.reason}",
                       nha=nha, model=model)
    except TimeoutError:
        raise LLMError(f"{nha}/{model}: quá {timeout}s không trả lời",
                       nha=nha, model=model)
    except ValueError as exc:
        raise LLMError(f"{nha}/{model}: trả về không phải JSON — {exc}",
                       nha=nha, model=model)

    lua = (d.get("choices") or [{}])[0]
    tin = lua.get("message") or {}
    goi_tool = []
    for t in tin.get("tool_calls") or []:
        ham = t.get("function") or {}
        tho = ham.get("arguments")
        try:
            tham = json.loads(tho) if isinstance(tho, str) else (tho or {})
        except ValueError:
            # Model bịa ra JSON hỏng là chuyện thường. Giữ nguyên văn để tầng
            # trên nói lại cho nó sửa, đừng nuốt thành dict rỗng — dict rỗng
            # trông y hệt "gọi tool không tham số" và sẽ chạy nhầm.
            tham = {"_hong": str(tho)[:500]}
        goi_tool.append({"id": t.get("id") or f"call_{len(goi_tool)}",
                         "ten": ham.get("name") or "", "thamSo": tham})

    usage = d.get("usage") or {}
    return {"chu": (tin.get("content") or "").strip(),
            # NGUYÊN VĂN lượt model trả về. Bắt buộc phải giữ, vì tầng trên
            # phải gửi LẠI đúng nó ở lượt sau chứ không được tự dựng lại.
            #
            # ĐO THẬT 2026-08-27: Gemini 3.x gắn `thought_signature` vào phần
            # tool_calls, và nếu lượt sau gửi lên một bản dựng lại thiếu chữ ký
            # đó thì nhà trả HTTP 400 "Function call is missing a
            # thought_signature". Nghĩa là não phụ gọi được company ở lượt 1
            # rồi CHẾT ở lượt 2 — đúng lúc đã tiêu tiền và đã chạm vào sổ.
            # Dựng lại lượt của model bao giờ cũng là canh bạc: nhà nào cũng có
            # quyền gắn thêm trường riêng, và ta không biết trường nào đáng.
            "tinGoc": tin,
            "goiTool": goi_tool,
            "lyDoDung": lua.get("finish_reason") or "",
            "usage": usage,
            "tienVnd": tien_vnd(usage, nha_cfg),
            # Nhà HTTP không đụng hạn mức gói Pro — giữ khoá này để tầng trên
            # cộng một kiểu cho mọi nhà, khỏi phải hỏi "nhà này loại gì".
            "costUsd": 0.0,
            "nha": nha, "model": model,
            "giay": round(time.monotonic() - bat_dau, 2)}


def goi_chuoi(chuoi: list, *, cfg: dict, chi_mien_phi: bool = True,
              **kw) -> dict:
    """Thử lần lượt cả chuỗi, ai trả lời trước thì lấy. Kèm sổ những lần đã thử.

    KHÔNG PHẢI CIRCUIT BREAKER. ProxyGateLLM có hẳn máy trạng thái
    CLOSED - OPEN - HALF_OPEN để nhớ nhà nào đang hỏng. Ở đây cố ý chưa làm, vì
    company chạy trong tiến trình MỚI mỗi lần gọi: trí nhớ trong RAM chết theo
    tiến trình, còn nhớ ra đĩa thì là thêm một cái sổ nữa phải dọn. Chuỗi 3–4
    nhà, mỗi lần hỏng mất một hai giây — chưa đáng. Đo thấy đau rồi hãy làm.

    chi_mien_phi=True — bỏ qua mọi nhà tính tiền thật. Đây là hàng rào L8 cho
    những chỗ chạy tự động, không có nút duyệt nào chen vào được.

    Cả chuỗi hỏng thì ném LLMError kể tên TỪNG nhà và lý do. Một câu "không gọi
    được model nào" không sửa được gì; "groq 429, cerebras thiếu khoá, ollama
    không nối được" thì admin biết phải đi đâu.
    """
    da_thu, loi = [], []
    for buoc in chuoi or []:
        ten, model = buoc.get("nha"), buoc.get("model")
        nha_cfg = (cfg.get("nha") or {}).get(ten) or {}
        if not nha_cfg:
            loi.append(f"{ten}: models.yaml không khai nhà này")
            continue
        if chi_mien_phi and not nha_cfg.get("mienPhi"):
            loi.append(f"{ten}: bỏ qua vì tính tiền thật")
            continue
        if thieu_khoa(nha_cfg):
            loi.append(f"{ten}: chưa có {nha_cfg['khoaEnv']}")
            continue
        try:
            kq = goi(nha=ten, model=model, cfg=cfg, **kw)
            kq["daThu"] = da_thu
            return kq
        except LLMError as exc:
            da_thu.append({"nha": ten, "model": model, "loi": str(exc)})
            loi.append(str(exc))
    raise LLMError(("không nhà nào trả lời được — " + " · ".join(loi)) if loi
                   else "chuỗi model rỗng")


def song_song(viec: list, *, cfg: dict, timeout: int = 60, **kw) -> list:
    """Hỏi nhiều model CÙNG LÚC. Trả về danh sách cùng thứ tự với viec.

    Mỗi phần tử là {"ok": True, ...kết quả} hoặc {"ok": False, "loi": ...} —
    KHÔNG ném. Hội đồng ba người mà một người vắng thì hai người còn lại vẫn
    họp được; ném ra ngoài là vứt luôn những bản trả lời đã lấy về được.

    Chạy bằng thread chứ không phải tiến trình: việc ở đây là CHỜ MẠNG, không
    phải tính toán, nên GIL không cản gì.

    Mỗi việc được mang `messages` RIÊNG của nó; thiếu thì dùng bản chung trong
    `kw`. Có chỗ này thì vòng phản biện — mỗi người đọc ý của những người KHÁC,
    tức mỗi người một prompt — cũng chạy song song được. Bản trước phải gọi
    tuần tự, và 4 thành viên × 60 giây là vỡ ngân sách của cả năng lực.
    """
    import threading
    ket = [None] * len(viec)

    def chay(i, b):
        try:
            rieng = dict(kw)
            if b.get("messages"):
                rieng["messages"] = b["messages"]
            kq = goi(nha=b["nha"], model=b["model"], cfg=cfg,
                     timeout=timeout, **rieng)
            kq["ok"] = True
            ket[i] = kq
        except LLMError as exc:
            ket[i] = {"ok": False, "nha": b.get("nha", ""),
                      "model": b.get("model", ""), "loi": str(exc)}

    luong = [threading.Thread(target=chay, args=(i, b), daemon=True)
             for i, b in enumerate(viec)]
    for t in luong:
        t.start()
    # Chờ dài hơn timeout của từng lời gọi một chút: bản thân lời gọi đã tự cắt
    # rồi, thread chỉ còn phần dọn dẹp. Chờ đúng bằng timeout thì gặp lúc chậm
    # sẽ trả về một ô None — mà None ở đây nghĩa là "không biết chuyện gì", thứ
    # tệ hơn cả một lỗi rõ ràng.
    for t in luong:
        t.join(timeout + 10)
    for i, k in enumerate(ket):
        if k is None:
            ket[i] = {"ok": False, "nha": viec[i].get("nha", ""),
                      "model": viec[i].get("model", ""),
                      "loi": "thread không trả về kịp"}
    return ket
