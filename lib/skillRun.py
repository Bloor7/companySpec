#!/usr/bin/env python3
"""Chạy một phiên Claude Code NHỐT KÍN cho một company. Dùng chung.

VÌ SAO Ở ĐÂY CHỨ KHÔNG CHÉP VÀO TỪNG COMPANY: hàm này chứa phần kiểm tra
an toàn, không phải chỉ chứa mã lặp. Nó là chỗ duy nhất biết rằng
`permission_denials` không rỗng nghĩa là KẾT QUẢ KHÔNG ĐÁNG TIN. Chép làm hai
bản thì sớm muộn một bản quên mất luật đó, và company ấy sẽ trả về `ok` kèm
một câu trả lời bịa — kiểu hỏng không ai phát hiện được, vì nó trông y hệt
thành công.

C4.1 — thư viện dùng chung: nó chỉ biết "chạy một phiên bị nhốt thế nào",
không biết company nào đang gọi hay đang hỏi gì.

ĐỌC DẦN, KHÔNG CHỜ TỚI CUỐI (L7.1). Với `--output-format json`, CLI im lặng
suốt rồi in một cục JSON lúc kết thúc — cắt ngang là mất sạch, kể cả con số chi
phí. Với `stream-json` nó phát từng dòng NDJSON dọc đường; đo được 2026-08-14:
dòng tới lúc 1,59s · 2,70s · 4,31s · 6,35s, không hề bị đệm tới cuối. Nên ở đây
đọc từng dòng và cộng dồn ngay trong tiến trình cha: giết con lúc nào cũng vẫn
còn số liệu đã gom.
"""
import json
import subprocess
import threading
import time

import quotaSignal  # cùng tầng lib/ — C4.1: kỹ thuật thuần, không biết nghiệp vụ

# ───────────────────────── bảng giá ─────────────────────────
#
# Đơn vị: đô-la trên MỘT TRIỆU token.
#
#   ghi5m / ghi1h = ghi vào cache, 1,25 lần và 2 lần giá vào
#   doc           = đọc từ cache, ~0,1 lần giá vào
#
# KHÔNG TRA TÀI LIỆU RỒI CHÉP VÀO — GIẢI NGƯỢC TỪ SỐ THẬT. `modelUsage` trong
# kết quả CLI có đủ token VÀ `costUSD`, nên giải ra được đơn giá và đối chiếu.
# Đo 2026-08-14, khớp chính xác đến từng đồng:
#   haiku-4-5 : 529×$1 + 17×$5                            = $0,000614 ✓
#   sonnet-5  : 2×$3 + 53×$15 + 1302×$0,30 + 2908×$6,00   = $0,0186396 ✓
# (Phiên ở đây ghi cache theo TTL 1 GIỜ — nên vế ghi là 2 lần giá vào, không
# phải 1,25. Tra tài liệu suông sẽ đoán nhầm vế này.)
#
# CHỈ DÙNG KHI PHIÊN CHẾT GIỮA CHỪNG. Phiên chạy trọn thì lấy `total_cost_usd`
# CLI tự tính — luôn đúng hơn bảng này. Bảng có hạn sử dụng: giá đổi thì con số
# ở đây lặng lẽ sai, nên đừng dùng nó cho việc gì ngoài ước lượng cho cầu dao.
GIA = {
    "claude-sonnet-5":   {"vao": 3.00, "ra": 15.00,
                          "ghi5m": 3.75, "ghi1h": 6.00, "doc": 0.30},
    "claude-sonnet-4-6": {"vao": 3.00, "ra": 15.00,
                          "ghi5m": 3.75, "ghi1h": 6.00, "doc": 0.30},
    "claude-opus-5":     {"vao": 5.00, "ra": 25.00,
                          "ghi5m": 6.25, "ghi1h": 10.00, "doc": 0.50},
    "claude-haiku-4-5":  {"vao": 1.00, "ra": 5.00,
                          "ghi5m": 1.25, "ghi1h": 2.00, "doc": 0.10},
}
# Model lạ thì tính theo mức ĐẮT NHẤT trong bảng, không phải mức quen thuộc:
# cầu dao thà tưởng đã tiêu nhiều rồi mà dừng sớm, còn hơn tưởng còn rảnh.
GIA_MAC_DINH = GIA["claude-opus-5"]
# Tên model không khớp dòng nào — gom lại để báo ra, đừng nuốt. Bản trước rơi
# vào nhánh mặc định mà không kêu một tiếng, nên `claude-sonnet-5` bị tính theo
# giá sonnet-4-6 suốt mà không ai biết (may là hai model cùng giá).
LA = set()


class SkillError(RuntimeError):
    """Phiên chạy xong nhưng kết quả không dùng được.

    MANG THEO CHI PHÍ (L7.1). Phiên hỏng vẫn đốt hạn mức thật — đo được
    2026-08-13: một lần nghienCuu chạy 133 giây rồi hỏng, backOffice ghi $0.00.
    Cầu dao L7 đếm bằng đúng con số đó, nên mọi lần hỏng đều tàng hình với nó.

    `qua_gio` phân biệt "hết giờ" với "hỏng" — company cần biết để trả về
    `budgetExceeded` thay vì `failed`, và để khuyên admin đúng thứ.
    `uoc_luong` = con số chi phí là ƯỚC từ token, không phải CLI tự tính.
    """

    def __init__(self, message: str, cost_usd: float = 0.0,
                 qua_gio: bool = False, uoc_luong: bool = False):
        super().__init__(message)
        self.cost_usd = cost_usd
        self.qua_gio = qua_gio
        self.uoc_luong = uoc_luong


def _gia_cua(ten_model: str) -> dict:
    """Khớp theo TIỀN TỐ: CLI trả 'claude-haiku-4-5-20251001' còn bảng ghi
    'claude-haiku-4-5'. So bằng nhau thì trượt hết, mà trượt thì lặng lẽ."""
    for khoa, gia in GIA.items():
        if (ten_model or "").startswith(khoa):
            return gia
    LA.add(ten_model or "(không tên)")
    return GIA_MAC_DINH


def _cong_tien(usage: dict, ten_model: str) -> float:
    """Quy usage của MỘT lượt assistant ra đô-la."""
    g = _gia_cua(ten_model)
    tao = usage.get("cache_creation") or {}
    # Không có phần tách 5m/1h thì coi cả cục là 5m — mức rẻ hơn, để bên ước
    # lượng nghiêng về phía ĐẾM THIẾU chứ không thổi phồng.
    ghi_1h = tao.get("ephemeral_1h_input_tokens") or 0
    ghi_5m = tao.get("ephemeral_5m_input_tokens")
    if ghi_5m is None:
        ghi_5m = max(0, (usage.get("cache_creation_input_tokens") or 0) - ghi_1h)
    return (
        (usage.get("input_tokens") or 0) * g["vao"]
        + (usage.get("output_tokens") or 0) * g["ra"]
        + ghi_5m * g["ghi5m"]
        + ghi_1h * g["ghi1h"]
        + (usage.get("cache_read_input_tokens") or 0) * g["doc"]
    ) / 1_000_000


def chay(prompt: str, *, settings: str, tools: str, max_turns: int,
         system_prompt: str, cwd: str, timeout: int,
         require_result: bool = True) -> dict:
    """Chạy `claude -p` bị nhốt, trả về JSON kết quả. Hỏng thì ném SkillError.

    KHÁC BẢN CŨ: không dùng `subprocess.run(timeout=…)` nữa. Cách đó giết tiến
    trình rồi ném `TimeoutExpired` tay không — mất cả kết quả lẫn chi phí. Ở đây
    tiến trình cha đọc từng dòng và cộng dồn, nên lúc bị cắt vẫn còn số liệu.

    `require_result=False` cho company mà THÀNH QUẢ LÀ FILE, không phải câu trả
    lời. Phiên có thể ghi xong báo cáo rồi kết thúc bằng một lượt trống — lúc đó
    `result` rỗng nhưng việc đã xong, mà báo hỏng thì vứt luôn thứ vừa làm ra.
    Company nào truyền cờ này thì phải TỰ kiểm file trên đĩa.
    """
    proc = subprocess.Popen(
        [
            "claude", "-p", prompt,
            "--system-prompt", system_prompt,
            "--settings", settings,
            "--tools", tools,
            "--strict-mcp-config",       # B6 — không nạp connector nào
            "--setting-sources", "project",
            "--max-turns", str(max_turns),
            # stream-json bắt buộc đi kèm --verbose. Đây là điều kiện để đọc
            # dần được; đổi về `json` là quay lại cảnh mất trắng khi bị cắt.
            "--output-format", "stream-json", "--verbose",
            "--no-session-persistence",  # mỗi lần gọi là một phiên sạch
        ],
        cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )

    # Gom theo message.id và GHI ĐÈ, không cộng dồn. Hai lý do, đo 2026-08-14:
    #  1. Cùng một message có thể lên luồng nhiều lần; cộng mù thì khoản GHI
    #     CACHE bị tính đôi — mà nó chiếm ~93% chi phí một lượt (2.905 token
    #     ghi = $0,0174 trên tổng $0,0187), nên tính đôi là lệch +82%.
    #  2. Bản sau của cùng message đầy đủ hơn bản trước: usage trên luồng là số
    #     TẠM, chưa chốt — đo được out=2 trong luồng trong khi thật là out=61.
    #     Ghi đè thì luôn giữ bản mới nhất.
    ket_qua, luot, rac = None, {}, 0
    bat_dau = time.monotonic()
    # Đồng hồ hẹn giờ giết tiến trình. Phải là hẹn giờ chứ không kiểm trong vòng
    # lặp: vòng lặp CHẶN ở `for dong in proc.stdout` cho tới khi có dòng mới,
    # nên một phiên treo im lặng sẽ không bao giờ chạm tới lệnh kiểm giờ.
    hen_gio = threading.Timer(timeout, proc.kill)
    hen_gio.daemon = True
    hen_gio.start()
    try:
        for dong in proc.stdout:
            dong = dong.strip()
            if not dong:
                continue
            try:
                d = json.loads(dong)
            except (json.JSONDecodeError, ValueError):
                rac += 1
                continue
            if d.get("type") == "result":
                ket_qua = d
            elif d.get("type") == "assistant":
                m = d.get("message") or {}
                khoa = m.get("id") or f"_{len(luot)}"
                luot[khoa] = (m.get("usage") or {}, m.get("model") or "")
    finally:
        hen_gio.cancel()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    giay = round(time.monotonic() - bat_dau)
    bi_cat = proc.returncode is not None and proc.returncode < 0
    gom_tien = sum(_cong_tien(u, m) for u, m in luot.values())
    so_luot = len(luot)

    # ── phiên bị cắt ngang: không có `result`, chỉ còn số gom dọc đường ──
    if ket_qua is None:
        stderr = (proc.stderr.read() or "").strip()[:200] if proc.stderr else ""
        raise SkillError(
            ("hết giờ, đã cắt" if bi_cat else f"phiên thoát mã {proc.returncode}")
            + f" sau {giay}s ({so_luot} lượt"
            + (f", {rac} dòng không đọc được" if rac else "") + ")"
            + (f": {stderr}" if stderr else "")
            + (f" [model lạ, giá là ước: {', '.join(sorted(LA))}]" if LA else ""),
            round(gom_tien, 6), qua_gio=bi_cat, uoc_luong=True)

    gia = ket_qua.get("total_cost_usd") or 0.0

    # O3 — hỏng thì hỏng TO.
    # Tool bị chặn quyền thì phiên vẫn viết ra một "câu trả lời" nói rằng nó
    # không làm được — và company vẫn trả về ok. Kết quả rỗng đội lốt thành công
    # là kiểu hỏng tệ nhất: admin tin là đã xong. CLI trả sẵn permission_denials.
    denials = ket_qua.get("permission_denials") or []
    if denials:
        ten = ", ".join(sorted({d.get("tool_name", "?") for d in denials}))
        raise SkillError(
            f"phiên bị chặn quyền dùng: {ten}. Kết quả không đáng tin — bổ sung "
            f"vào permissions.allow của {settings}", gia)

    # Khi hỏng, CLI KHÔNG trả trường `result`; nó trả `subtype`, `errors`,
    # `terminal_reason`. Đo được 2026-08-13 với --max-turns 1:
    # {"is_error":true,"subtype":"error_max_turns",...} và không hề có `result`.
    if ket_qua.get("is_error") or (require_result
                                   and not (ket_qua.get("result") or "").strip()):
        ly_do = ket_qua.get("subtype") or ket_qua.get("terminal_reason") or "không rõ lý do"
        them = "; ".join(str(e) for e in (ket_qua.get("errors") or []))[:200]

        # HẾT HẠN MỨC nói riêng ra, đừng gộp vào "phiên không trả về nội dung".
        # Company và CEO dùng chung một gói: hết là hết cả hai. Admin cần đọc
        # được "chờ vài tiếng" thay vì một câu lỗi kỹ thuật khiến họ tưởng
        # company hỏng rồi đi sửa nhầm chỗ.
        hit = quotaSignal.phat_hien(
            f'{ket_qua.get("result") or ""} {ly_do} {them}',
            ket_qua.get("api_error_status"))
        if hit:
            raise SkillError(quotaSignal.cau_bao_admin(hit), gia)

        raise SkillError(
            f"phiên không trả về nội dung: {ly_do} {them} "
            f"({ket_qua.get('num_turns')} lượt, {giay}s)".strip(), gia)

    return ket_qua
