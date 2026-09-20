"""brains.local — model chạy trên máy nhà.

CHƯA CÓ. Gói này là chỗ đứng cho mức dữ liệu private và sensitive:
registry/brainPolicy.yaml ghi preferred [local] cho cả hai mức, nghĩa là hôm
nay chúng chỉ còn đúng claude.

⚠ ĐỪNG GỌI HỆ LÀ "local-first" CHỪNG NÀO FILE NÀY CHƯA CHẠY ĐƯỢC.
§29 nói thẳng: dùng API của Claude hay Gemini là context tương ứng RỜI MÁY.
Chừng nào local chưa chạy thật, "local-first" mới là HƯỚNG ĐI, chưa phải
trạng thái — và nói ngược lại là nói dối về thứ nguy hiểm nhất để nói dối.

Kế hoạch §41 xếp "local LLM orchestration phức tạp" vào nhóm KHÔNG làm sớm,
nên gói này trống là có chủ ý, không phải vì quên.
"""
from ..base import ProviderBrain


class LocalBrain(ProviderBrain):
    brainId = "local"
    defaultModel = ""
