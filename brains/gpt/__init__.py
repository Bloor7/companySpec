"""brains.gpt — nhà OpenAI-compatible.

CHƯA BẬT: registry/models.yaml không khai nhà này, và registry/brainPolicy.yaml
không cho nó nhận mức dữ liệu nào. Gói này tồn tại để §11 của kế hoạch có chỗ
đứng — "không hardcode model = vai" — chứ không phải để dùng ngay.

Bật nó là HAI việc, và phải làm cả hai:
  1. khai nhà trong registry/models.yaml (baseUrl, khoaEnv, giá)
  2. cho nó vào dataBoundary của mức dữ liệu tương ứng

Làm một mà quên hai thì nó im lặng không nhận được việc nào — hành vi ĐÚNG
(mặc định ĐÓNG), chỉ là dễ làm người ta tưởng hệ hỏng. Nên nếu bạn vừa khai
nhà mà không thấy nó chạy, đọc lại bước 2 trước khi đi tìm lỗi chỗ khác.
"""
from ..base import ProviderBrain


class GptBrain(ProviderBrain):
    brainId = "gpt"
    defaultModel = ""
