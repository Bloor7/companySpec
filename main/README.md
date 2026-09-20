# main/ — vùng TIN ĐƯỢC, đối lập với `lab/`

```text
LAB                     MAIN
thử nghiệm              production
không đáng tin          tin được
hỏng cũng được          KHÔNG được hỏng
thay được               có kiểm toán
        └──── promotion ────┘
```

Đây là nơi thứ đã qua `lab/` hạ cánh sau khi **admin duyệt**. Xem
[`core/lab/__init__.py`](../core/lab/__init__.py) → `checkPromotionReadiness`.

---

## Thư mục này đang TRỐNG, và đó là đúng

Chưa có thứ gì từ ngoài được thăng cấp. Nói ra điều đó thẳng thắn quan trọng
hơn là làm nó trông có vẻ đầy đặn.

Một `main/` trống nghĩa là: hệ chưa tiếp nhận mã của ai cả. Đó là trạng thái
an toàn nhất, và nó chỉ nên thay đổi khi có lý do đo được.

---

## Vào đây bằng cách nào

Không có đường tắt. `promote()` chặn nếu thiếu bất kỳ thứ nào:

| Đòi | Vì sao |
|---|---|
| Báo cáo soi repo | Không soi thì không biết mình đang nhận gì |
| 0 điểm `high` chưa xử lý | `postinstall`, prompt injection, với tay vào khoá SSH |
| Giấy phép xác định | Không có giấy phép nghĩa là **KHÔNG được phép dùng**, chứ không phải tự do dùng |
| Nguồn nằm **trong** `lab/` | Thăng cấp thứ chưa từng qua cách ly là bỏ qua cả quy trình |
| Đích nằm **ngoài** `lab/` | Bằng không thì đó không phải thăng cấp |

Từ cấp `dependency` trở lên (mã người lạ **chạy trong hệ**) còn đòi thêm:

- **benchmark** — số đo, không phải ấn tượng
- **admin duyệt** — quyết định cuối là của admin, đó là cả điểm của P7

> "Trông có vẻ tốt" không phải lý do.

---

## Sau khi vào rồi

Thăng cấp **không phải là hết chuyện**. §34 của kế hoạch kết thúc vòng đời
bằng `Monitor`, không bằng `Promote`:

```text
… → Approval / Policy → Promote → MONITOR
```

Một thứ chạy tốt trong sandbox vẫn có thể hỏng khi gặp dữ liệu thật. Nên thứ
nằm ở đây vẫn phải đi qua Policy và Verification như mọi thứ khác — vào `main/`
không cấp cho nó quyền nào cả.
