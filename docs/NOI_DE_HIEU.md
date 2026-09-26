# Nói cho đại ca hiểu

Luật viết cho MỌI chữ hệ gửi admin: câu CEO trả lời, tin báo tự động (máy phụ
xong việc, bộ canh dựng lại hệ, báo cáo tối), và cả lời Claude Code giải thích
trong phiên làm việc.

**Vì sao có trang này.** 26/09 admin chụp màn hình tin "Hộp làm xong một việc…
→ choXem sau 5 bước. ??" rồi nói: *"anh không biết xem thế nào luôn… bộ ca là
ca gì, hộp là hộp gì"*. Các từ `hộp`, `xưởng`, `gương`, `ca thử`, `choXem` là
**biệt danh nội bộ** — đặt ra để người viết mã gọi cho nhanh, rồi lặng lẽ tràn
ra câu gửi admin. Người viết thấy quen nên không nhận ra; người đọc thì không
có cách nào đoán.

## Năm luật

Rút từ hướng dẫn "plain language" (ngôn ngữ dễ hiểu) của chính phủ Mỹ —
[digital.gov](https://digital.gov/guides/plain-language/principles) — chọn
những điều hợp với tiếng Việt và với một người đọc trên điện thoại:

1. **Kết quả trước.** Câu đầu nói chuyện gì đã xảy ra với ĐẠI CA (xong chưa,
   có mất gì không), không nói máy đã chạy những bước gì.
2. **Từ thường, không biệt danh.** Tra bảng dưới. Thuật ngữ nào buộc phải
   dùng thì giải thích MỘT lần trong ngoặc, ngay chỗ nó xuất hiện lần đầu.
3. **Câu ngắn, một ý một câu.** Trên điện thoại, câu dài hơn hai dòng là câu
   bị đọc lướt.
4. **Không dán đầu ra máy.** Không `??`, không mã trạng thái (`choXem`,
   `needsApproval`), không tên hàm, tên tệp, trừ khi admin hỏi đúng thứ đó.
5. **Câu cuối là việc đại ca cần làm** — hoặc nói rõ "đại ca không cần làm
   gì". Tin mà không cho biết phải làm gì tiếp là tin bắt người đọc đoán.

Tham khảo thêm, cho người dịch thuật ngữ máy tính sang tiếng Việt:
[Microsoft Vietnamese Localization Style Guide](https://download.microsoft.com/download/b/f/e/bfecb1b4-21ab-48fd-a48c-c2471b026f8f/vie-vnm-StyleGuide.pdf).

## Bảng đổi từ

| Biệt danh nội bộ | Nói với đại ca là |
|---|---|
| hộp, openclaw | máy phụ (máy ảo riêng nơi AI tự viết mã, không đụng được dữ liệu thật) |
| thợ | AI ở máy phụ |
| xưởng, xuongCompany | danh sách việc giao cho máy phụ |
| ca thử, ca | bài kiểm tra tự động |
| bộ ca, lưới an toàn | bộ bài kiểm tra |
| xanh / đỏ | đạt / không đạt |
| nhánh `y/…` | bản nháp |
| gương | kho chứa bản nháp |
| gộp (merge) | đưa bản nháp vào hệ đang chạy |
| commit | lưu một mốc |
| đẩy (push) | gửi lên GitHub |
| diff | những chỗ thay đổi |
| `choXem` | chờ đại ca đồng ý |
| `codemap --check` sạch | kiểm tra cấu trúc hệ: đạt |
| company | bộ phận (bộ phận chi tiêu, bộ phận lịch…) |
| năng lực, capability | việc bộ phận làm được |
| dispatcher, cổng | cổng kiểm soát (nơi mọi việc phải đi qua để được cho phép) |
| phiếu duyệt | nút duyệt trên Telegram |
| whitelist, luôn cho phép | lần sau tự làm, không hỏi lại |
| secret, khoá | mật khẩu / khoá truy cập dịch vụ |
| poller | phần nhận tin Telegram |
| user manager, systemd | phần tự khởi động các dịch vụ nền |
| bộ canh | bộ tự sửa (thấy hệ chết thì tự bật lại) |
| cron, scheduler | lịch tự chạy |
| não phụ | AI dự phòng (khi Claude không dùng được) |

## Ví dụ

ĐỪNG:
> Hộp làm xong một việc, chờ đại ca xem
> y_9b309f16ef (Ca thử: secret broker lùi về manifest không được r) → choXem
> sau 5 bước. ?? tests/regression/testSecretBrokerFallbackBounded.py
> codemap --check: sạch. Nhánh y/y_9b309f16ef đã đẩy lên gương

HÃY:
> Máy phụ đã làm xong: thêm một bài kiểm tra tự động cho phần giữ mật khẩu.
> Nó tự kiểm tra: đạt. Việc này mới là bản nháp, chưa vào hệ đang chạy.
> Muốn dùng: mở Claude Code và nói "duyệt việc y_9b309f16ef".

Thêm một biệt danh mới vào hệ thì thêm luôn một dòng vào bảng trên.
