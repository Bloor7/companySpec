"""Nhận ra lúc Anthropic nói "hết hạn mức" — nguồn sự thật DUY NHẤT về quota.

VÌ SAO TỒN TẠI: hệ từng tự cộng chi phí token rồi so với một ngưỡng đoán,
và dùng con số đó để khoá việc ghi. Hai điều sai:

  1. Con số đó KHÔNG bám thực tế. Đo 2026-08-16: `claude -p --output-format
     json` trả về tokens và `total_cost_usd`, nhưng KHÔNG có một trường nào
     nói hạn mức còn lại bao nhiêu. CLI cũng không có lệnh con `usage`. Nên
     mọi con số "3,95/5" hệ từng in ra là hệ tự bịa từ bảng giá, không liên
     quan tới trần thật của gói Pro.
  2. Nó chặn NGƯỢC. Cầu dao chỉ chặn `write` — ghi chi tiêu, ví, việc vặt —
     những thứ tốn $0 LLM vì company là code cứng. Còn thứ thật sự đốt hạn
     mức đều là `read`: nghienCuu $3,50 · auditSite $2,00 · auditPage $0,35.
     Không cái nào bị chặn. Vô dụng với thứ cần chặn, gây hại với thứ không.

Nên bỏ cách đoán. Thay bằng: đợi Anthropic tự nói, rồi báo admin.

MẪU CHƯA ĐO ĐƯỢC TRÊN MÁY NÀY. Hệ chưa từng chạm trần (ceoRunLog không có
lượt lỗi nào), nên các mẫu dưới lấy từ dạng thông báo Anthropic dùng, chứ
không phải từ một lần hỏng thật đã bắt được. Vì thế bộ nhận diện bắt RỘNG và
có nhánh cuối cùng dựa vào mã 429 — thà nhận nhầm một lỗi mạng thành "hết hạn
mức" (admin đọc thấy sai thì biết ngay) còn hơn im lặng đúng lúc cần nói.
Bắt được mẫu thật lần đầu thì chép nguyên văn vào đây.
"""
import re

# Thứ tự có ý nghĩa: mẫu hẹp trước, rộng sau.
MAU_TUAN = re.compile(r"weekly|per week|tuần|7[- ]day", re.I)
MAU_5H = re.compile(r"5[- ]?hour|five[- ]hour|5 tiếng", re.I)
MAU_QUOTA = re.compile(
    r"usage limit|rate limit|rate_limit|limit reached|quota|"
    r"exceeded your|too many requests|hết hạn mức|quá giới hạn|"
    # Thứ tự chữ đảo lại vẫn phải bắt được: "reached your 5-hour limit" từng
    # lọt lưới vì mẫu trên chỉ khớp đúng cụm "limit reached".
    r"reached your[^.]{0,40}limit|\d+[- ]?hour limit|weekly limit|"
    r"out of (?:usage|credit)|"
    # MẪU THẬT, chép nguyên văn 2026-09-11 từ sổ `quotaHit` — ba lần giống hệt
    # (18/08, 19/08, 31/08): "You've hit your session limit · resets 3:40am
    # (Asia/Bangkok)". Không mẫu nào ở trên khớp nó: nó nói "hit your" chứ
    # không "reached your", và "session limit" chứ không "usage limit".
    #
    # Tức là suốt từ đầu, việc nhận ra hết hạn mức SỐNG NHỜ MÃ 429 đi kèm —
    # nhánh dự phòng cuối cùng — chứ câu chữ chưa bao giờ khớp. Hôm nào
    # Anthropic đổi mã hoặc CLI không phơi `api_error_status` ra (đo 11/09:
    # trường đó là None trong một lỗi khác) thì hết hạn mức sẽ đi qua lặng lẽ,
    # CEO không chuyển não, và admin nhận một câu tiếng Anh làm câu trả lời.
    # Docstring trên đã dặn "bắt được mẫu thật thì chép vào" — bắt ba lần rồi
    # mà không ai chép, vì mọi lần đều đã có 429 đỡ hộ.
    r"hit your[^.]{0,40}limit|session limit",
    re.I)
# "resets at 3pm", "will reset at 15:00", "reset lúc 3pm"
MAU_RESET = re.compile(
    r"reset[s]?\s*(?:at|lúc)?\s*([0-9]{1,2}[:h][0-9]{2}\s*(?:am|pm)?|"
    r"[0-9]{1,2}\s*(?:am|pm))", re.I)


def phat_hien(loi: str = "", api_error_status=None) -> dict | None:
    """Trả về {loai, resetLuc, nguyenVan} nếu là hết hạn mức, ngược lại None.

    `loai` ∈ {"tuần", "5 tiếng", "không rõ"} — Anthropic có hai cửa sổ, và
    admin cần biết là chờ vài tiếng hay chờ sang tuần. Không đoán được thì nói
    "không rõ", đừng chọn bừa một cái: đoán "5 tiếng" trong khi thật ra là hạn
    tuần sẽ khiến admin ngồi đợi cả buổi vô ích.
    """
    text = (loi or "").strip()
    la_quota = bool(text and MAU_QUOTA.search(text))

    # Mã 429 là tín hiệu của chính giao thức, không phải câu chữ — tin nó kể
    # cả khi lời lẽ không khớp mẫu nào (thông báo có thể đổi bất cứ lúc nào).
    if not la_quota and str(api_error_status) == "429":
        la_quota = True
    if not la_quota:
        return None

    if MAU_TUAN.search(text):
        loai = "tuần"
    elif MAU_5H.search(text):
        loai = "5 tiếng"
    else:
        loai = "không rõ"

    m = MAU_RESET.search(text)
    return {"loai": loai,
            "resetLuc": m.group(1).strip() if m else None,
            "nguyenVan": text[:300]}


def cau_bao_admin(hit: dict) -> str:
    """Câu nhắn cho admin. Nói ĐIỀU CẦN LÀM, không nói mã lỗi.

    Việc ghi chép vẫn chạy được khi hết hạn mức: company là code cứng gọi
    Notion, không dùng LLM. Thứ dừng là CEO — tức là không nhắn cho bot được
    nữa, chứ dữ liệu không mất và sổ không khoá. Phải nói rõ chỗ đó, nếu không
    admin tưởng cả hệ chết.
    """
    khi = {"tuần": "Hạn mức TUẦN đã hết",
           "5 tiếng": "Hạn mức 5 tiếng đã hết"}.get(hit["loai"],
                                                    "Hạn mức Claude đã hết")
    mo_lai = f" Mở lại lúc {hit['resetLuc']}." if hit.get("resetLuc") else (
        " Hạn tuần thì phải chờ sang tuần." if hit["loai"] == "tuần"
        else " Cửa sổ trượt nên vài tiếng nữa sẽ tự mở lại.")
    return (f"{khi}.{mo_lai}\n\n"
            "Em tạm thời không trả lời được, nhưng dữ liệu không sao: sổ sách "
            "và lịch vẫn nguyên, việc định kỳ vẫn chạy. Đại ca nhắn lại sau là "
            "em làm tiếp.")
