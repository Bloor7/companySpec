"""brains.gemini — Google AI Studio.

Nhà chính của CHUỖI DỰ PHÒNG. Admin chốt 2026-08-27: chỗ này cần một model
ĐÁNG TIN, không cần rẻ. Nó chỉ chạy trong những quãng gói Pro cạn giữa chu kỳ
— lúc đó admin vẫn phải ghi được khoản chi và tra được lịch, và một model miễn
phí lúc được lúc không thì đúng vào lúc cần lại hỏng.

TÍNH TIỀN THẬT, có trần tháng canh ở registry/gateway.yaml.

HAI model chứ không một: đo 27/08 thấy gemini-3.7-flash và alias
gemini-flash-latest trả 503 cả ngày trong khi 3.5 và 3.1-lite chạy 0,9s.
Một tên model là một điểm hỏng đơn.
"""
from ..base import ProviderBrain


class GeminiBrain(ProviderBrain):
    brainId = "gemini"
    defaultModel = "gemini-3.1-flash-lite"
