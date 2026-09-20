#!/usr/bin/env python3
"""gateway/cli/scheduler — nối động cơ lịch với thế giới bên ngoài, rồi chạy.

    python3 gateway/cli/scheduler.py run     # chạy lịch tới hạn (systemd gọi)
    python3 gateway/cli/scheduler.py hen     # nhắc và phiếu hẹn tới giờ
    python3 gateway/cli/scheduler.py list    # xem lịch

VÌ SAO FILE NÀY TỒN TẠI, VÀ VÌ SAO NÓ MỎNG

`core/events/scheduler.py` quyết định LÚC NÀO chạy gì và có nên nhắn không.
Nó KHÔNG biết nhắn bằng cách nào — C4.2: core/ là luật, không phải người vận
chuyển.

Trước 2026-09-20 scheduler `import telegram` thẳng. Khi §36 đẩy nó vào core/
thì codemap bắt ngay, và đó đúng là việc của codemap. Cách chữa không phải nới
luật mà là tách đúng chỗ — file này là chỗ tách.

Mỏng là có chủ ý: nó chỉ nối dây. Thêm logic vào đây là bắt đầu dựng một bản
sao thứ hai của bộ lịch, và hai bản của cùng một luật là cách nó lệch đi.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "gateway", "telegram"))
sys.path.insert(0, os.path.join(ROOT, "backOffice", "src"))
sys.path.insert(0, os.path.join(ROOT, "core", "events"))

import telegram  # noqa: E402
import backoffice  # noqa: E402
import scheduler  # noqa: E402


def main() -> int:
    scheduler.configure(
        notify=telegram.send_message,
        costSnapshot=backoffice.chi_phi_gan_day,
        spendSnapshot=backoffice.tien_that_thang,
    )
    return scheduler.main()


if __name__ == "__main__":
    sys.exit(main())
