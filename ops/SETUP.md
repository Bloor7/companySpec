# Cắm vào — 3 bước

Không cần Docker, không cần n8n, không cần URL công khai.

---

## 1. Tạo bot Telegram

Nhắn [@BotFather](https://t.me/BotFather):

```
/newbot
```

Đặt tên hiển thị, rồi username kết thúc bằng `bot`. Nó trả về token dạng `1234:AAF…`.

Khoá bot lại cho riêng mình:

```
/setjoingroups   → Disable
/setprivacy      → Enable
```

Rồi chạy:

```bash
cd ~/companySpec && bash ops/setup-bot.sh
```

Script hỏi token (gõ ẩn), bảo cậu nhắn cho bot một câu, tự tìm `chatId`, ghi
`ops/.env` với quyền 600.

## 2. Cắm Notion

Vào <https://www.notion.so/my-integrations> → **New integration** → copy
*Internal Integration Secret*.

Mở trang Notion muốn chứa các sổ → **⋯** → **Connections** → chọn integration.
Integration **chỉ thấy trang cậu chia sẻ**, không thấy gì khác.

```bash
python3 ops/setup-notion.py
```

Tự tạo sổ **Chi tiêu** và **Nhật ký** đúng schema. Sổ đã có thì giữ nguyên.
Bảng kế hoạch do cậu tự dựng — script chỉ nhận lại, không tạo đè.

## 3. Chạy nền

```bash
mkdir -p ~/.config/systemd/user
cp ops/companyspec-gateway.service ops/companyspec-scheduler.{service,timer} \
   ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now companyspec-gateway companyspec-scheduler.timer
loginctl enable-linger "$USER"
```

Nhắn `/giupdo` cho bot để kiểm tra.

---

## Vì sao không dùng webhook

Telegram chỉ gọi được vào URL công khai có HTTPS. Máy này sau NAT, không có IP
công khai. Muốn webhook thì phải mở một cửa từ internet vào máy — cái giá quá
đắt cho một trợ lý giữ dữ liệu riêng.

Polling thì ngược lại: máy tự hỏi Telegram, không ai gọi vào được.

## Khi có gì không chạy

| Hiện tượng | Chỗ xem |
|---|---|
| Bot im lặng | `journalctl --user -u companyspec-gateway -f` |
| Sai chatId | `ops/.env` — sai thì gateway bỏ qua, đúng thiết kế |
| Lịch không chạy | `systemctl --user list-timers companyspec-scheduler.timer` |
| Muốn xem hệ nghĩ gì | `python3 ops/gateway.py check` |
| Có việc gì đang chạy | `pgrep -af "claude -p"` |
