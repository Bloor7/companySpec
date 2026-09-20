"""brains — bộ não, TÁCH KHỎI người dùng nó (§11 kế hoạch).

    brains/
      router.py    chọn nhà nào, và CHẶN theo ranh giới dữ liệu (§12, §29)
      council.py   nhiều góc nhìn, có phản biện (§26)
      claude/  gemini/  gpt/  local/      từng nhà, cùng một giao diện

LUẬT GỐC (§11): **không hardcode model = vai**. Model chỉ là SỞ THÍCH.

Đổi bộ não không làm mất Employee (E-1). `forge` hôm nay chạy bằng Claude, mai
bằng Gemini, vẫn là `forge` — vẫn giữ trí nhớ, quyền hạn và cách làm việc.

Đây không phải chuyện thẩm mỹ. Hệ đã chết một lần vì bộ não là hằng số trong
code: hết hạn mức gói Pro thì không ghi nổi một khoản chi, dù mọi company vẫn
chạy tốt — chúng là code cứng, chỉ là người gọi đã chết.

⚠ PHẦN GỌI THẬT nằm ở `lib/llmClient.py`, và cố ý để yên ở đó: nó đã có chuỗi
dự phòng, đo chi phí, chế độ CLI cho Claude, và đã chạy thật qua nhiều sự cố.
Các gói `claude/`, `gemini/`, `gpt/`, `local/` ở đây là lớp vỏ CÓ KIỂU trên
nó, không phải bản viết lại.
"""
