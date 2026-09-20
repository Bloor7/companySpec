"""brains.claude — Claude của gói Pro.

⚠ KHÔNG gọi bằng HTTP. Anthropic không phát khoá API cho gói thuê bao: thứ
admin trả tiền hằng tháng là lệnh `claude` đã đăng nhập sẵn trên máy. Nên nhà
này chạy kiểu `cli` — `lib/llmClient.py` gọi `claude -p` với `--tools ''` rồi
đọc JSON.

`mienPhi: true` trong models.yaml nghĩa là KHÔNG TRỪ THẺ, không có nghĩa là rẻ:
nó ăn vào hạn mức gói Pro — thứ đắt theo một kiểu khác, và là chính thứ mà cơ
chế não phụ sinh ra để đỡ.

ĐO THẬT 2026-08-27, một lời gọi bốn token: 11.790 token ghi cache, $0,071.
Phần lớn là prompt nền của chính CLI, không phải câu ta hỏi.
"""
from ..base import ProviderBrain


class ClaudeBrain(ProviderBrain):
    brainId = "claude"
    defaultModel = ""     # CLI tự chọn model theo ceo/settings.json
