# companySpec

Trợ lý cá nhân dùng riêng cho một người. Đọc [PRINCIPLES.md](PRINCIPLES.md) trước —
đó là hiến pháp; file này chỉ nói cách chạy.

**Đang ở: 15 company · 56 năng lực** — Telegram, phê duyệt bằng nút, whitelist học dần,
việc định kỳ, cầu dao hạn mức, tra web. Cắm theo [ops/SETUP.md](ops/SETUP.md).

<!-- Bỏ số "Lát N" khỏi dòng trên ngày 2026-08-14. Lát 1–4 có ghi trong bảng
     thay đổi của PRINCIPLES; Lát 5–10 thì KHÔNG ở đâu định nghĩa cả — con số
     cứ được cộng dần mà không có gốc để đối chiếu, tới lúc admin hỏi lại thì
     không ai trả lời được. Hai con số còn lại đếm được bằng code nên không
     lệch âm thầm:
       ls companies/*/companySpec.yaml | wc -l
     Muốn đánh số lát trở lại thì viết Lát 5–10 vào bảng thay đổi TRƯỚC. -->


Năm company tiền bạc tách rời có chủ ý (C3/C4): `incomeCompany` tiền vào,
`expenseCompany` tiền ra, `savingsCompany` để dành theo mục tiêu, `walletCompany`
số dư thực (mốc kiểm kê), `budgetCompany` hạn mức dự định.
Không company nào đọc sổ của company khác — câu "tháng này còn dư bao nhiêu" là
CEO gọi cả ba rồi tự trừ.

Mọi con số đều do admin nhập theo thực tế, không có khai báo định kỳ nào: sổ chỉ
chứa tiền đã thật sự vào hoặc ra. Việc đều đặn duy nhất là lời NHẮC mùng 1 —
nó hỏi, admin trả lời, rồi tiền mới được ghi.

---

## Chạy thử

Qua Telegram (sau khi làm xong [ops/SETUP.md](ops/SETUP.md)):

```bash
set -a && source ops/.env && set +a && python3 ops/serve.py
```

Không cần bot — nạp thẳng một Update giả vào gateway:

```bash
export COMPANYSPEC_ADMIN_CHAT_ID=<chatId>
echo '{"message":{"chat":{"id":<chatId>},"text":"Tớ có ghi chú nào?"}}' \
  | python3 gateway/telegram/session.py handle
```

Hoặc dùng bản dòng lệnh cũ, không qua Telegram:

```bash
python3 ops/ask.py "Tớ đang có những ghi chú nào?"
```

Gọi thẳng dispatcher, không qua CEO — dùng khi cần kiểm tra guardrail:

```bash
python3 gateway/cli/dispatch.py list
python3 gateway/cli/dispatch.py call --company notesCompany --capability listNotes --input '{}'
python3 gateway/cli/dispatch.py call --company notesCompany --capability addNote \
  --input '{"text":"ghi chú thử"}' --dry-run
```

---

## Ai làm gì

| Thành phần | Vai | Nguyên tắc |
|---|---|---|
| `gateway/telegram/session.py` | **adminGateway.** sessionPolicy R1–R4, nút duyệt, whitelist, nhớ 10 tin gần nhất khi mở phiên mới (giữ 7 ngày), đọc nội dung tin admin bấm Reply, bức tranh hiện tại (cache 10 phút, làm mới ở nền) | T1, §12 Q2 |
| `core/policy/approvals.py` | Kho phê duyệt (2 đồng hồ) + whitelist có hạn, có scope | G7–G11 |
| `core/events/scheduler.py` | Việc định kỳ (§12c). systemd timer gọi 15 phút/lần | S1–S7 |
| `gateway/telegram/telegram.py` | Đường ra Telegram duy nhất | T1 |
| `ceo/SYSTEM.md` | System prompt của CEO. Tiếng Việt | Q10 |
| `ceo/settings.json` | Deny rules — lớp phòng thủ thứ hai | P2 |
| `ceo/hooks/guard.py` | **Hàng rào thật.** Chặn mọi lệnh Bash không phải dispatcher | P2 |
| `gateway/telegram/media.py` | Đọc **ảnh** admin gửi bằng một tiến trình RIÊNG, quyền hẹp hơn CEO (`ceo/settings-media.json`). Hỏng thì thử lại 1 lần, ghi lý do vào `backOffice/media-loi.jsonl` | P2 |
| `searchCompany` | Tra web NHANH, trả chữ thẳng vào Telegram (~20s, ~$0,06). Quyền hẹp nhất hệ: chỉ WebSearch/WebFetch, không Read/Write/Bash | RP3, B6 |
| `researchCompany` | Nghiên cứu SÂU: nhiều luồng đọc song song, ghi báo cáo HTML rồi trả đường dẫn (5–15 phút, ~$1). Tách khỏi `searchCompany` để hai khoản tiền rất lệch nhau nằm hai dòng riêng trong backOffice | RP3, D1 |
| `core/execution/brainRunner.py` | Chạy phiên Claude nhốt kín cho company. Giữ ở một chỗ vì nó chứa luật "`permission_denials` không rỗng = kết quả KHÔNG đáng tin" | C4.1, O3 |
| `gateway/telegram/stt.py` | Nghe **tin thoại**, đổi thành chữ. Mô hình chạy tại máy — giọng nói không rời máy | F2 |
| `gateway/cli/dispatch.py` | **Dispatcher.** Điểm nghẽn cố ý — nơi nói KHÔNG | T2 |
| `companies/*/companySpec.yaml` | Hợp đồng của company. Không có file này thì company không tồn tại | C2.1 |
| `companies/*/store.sqlite` | Dữ liệu riêng từng company, không ai đọc của ai | C3 |
| `ops/snapshot.py` | Chụp/so lệch/dựng lại một sổ Notion. **Chạy `save` trước mọi phép thử chạm dữ liệu** | W7 |
| `lib/notionClient.py` | Thư viện dùng chung. Chỉ biết gọi Notion, không biết nghiệp vụ | C4.1, C4.2 |
| `goalCompany` | **Mỗi kế hoạch một bảng Notion riêng** (`KH: <tên>`). Bản đồ tên→bảng ở store, mất thì tự quét lại | C3 |
| `companies/profileCompany/PROFILE.md` | Hồ sơ admin. Gateway nối vào system prompt CEO **mỗi lượt** — sửa tay được | C1, G5 |
| `backOffice/store.sqlite` | Log tổng hợp: taskLog, sideEffectLog, ceoRunLog, approvalRequest | O5, O6 |
| `backOffice/src/backoffice.py` | Báo cáo + thanh hạn mức + cầu dao L7. Hạ tầng, không phải company | Q7, L7 |

Đường đi một tin nhắn:

```
admin → ask.py → CEO (claude -p) → guard.py → dispatch.py → company → sqlite
                    ↑                                          │
                    └──────────── companyResult ───────────────┘
```

---

## Thêm một company mới

1. `mkdir companies/<tên>Company`
2. Viết `companySpec.yaml` — khai `capabilities`, mỗi cái có `riskTier` và
   `inputSchema`/`outputSchema`
3. Viết entrypoint: đọc `taskEnvelope` trên stdin, ghi `companyResult` ra stdout
4. Xong. **Không sửa gì ở CEO** — nếu phải sửa CEO thì hợp đồng đang rò rỉ (W3)

Company mới luôn bắt đầu ở `read` (W1). Muốn lên `write` thì phải có `dryRun` trước (W2).

---

## Kiểm tra hệ còn lành

```bash
# hook có chặn không
echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}' | python3 ceo/hooks/guard.py

# hạn mức đã dùng
python3 -c "
import sqlite3
c=sqlite3.connect('backOffice/store.sqlite')
print('tổng:', round(sum(r[0] for r in c.execute('SELECT costUsd FROM ceoRunLog')),4))"

# việc gì đã đổi ngoài thế giới thực
python3 -c "
import sqlite3
c=sqlite3.connect('backOffice/store.sqlite')
[print(r) for r in c.execute('SELECT type,target,reversible FROM sideEffectLog')]"
```

---

## Chưa có, sẽ có ở lát sau

| Việc | Nội dung |
|---|---|
| tiếp | Hiệu chuẩn ngưỡng L7 bằng `/usage` (cần admin làm tay) |
| sau | `docsCompany`; company gửi mail — `irreversible` đầu tiên |

## Việc định kỳ

Khai trong `registry/schedules.yaml`, chạy bằng systemd timer 15 phút một lần.

| Lịch | Khi nào | Làm gì |
|---|---|---|
| `morningReport` | 05:30 hằng ngày | **Lịch hôm nay**, hạn mức, hoạt động 24h, việc chờ duyệt, quyền sắp hết hạn, tiến độ video |
| `quotaWatch` | mỗi 2 tiếng | Chỉ nhắn khi hạn mức sắp chạm trần (S7) |
| `calendarWatch` | mỗi 15 phút | Sự kiện sắp bắt đầu trong 30 phút. Mỗi sự kiện nhắc đúng một lần |
| `savingsNudge` | 08:00 mùng 1 | Thanh tiến độ từng quỹ, cần nạp bao nhiêu để kịp hạn, rồi hỏi tháng này nạp bao nhiêu |
| `dailyMoney` | 21:00 hằng ngày | Số dư ước tính, thu chi hôm nay, % ngân sách từng danh mục, cảnh báo vượt |
| `goalNudge` | 08:00 thứ Hai | Bước kế hoạch quá hạn hoặc tới hạn trong 7 ngày. Không có thì im |
| `weeklyPlan` | 08:00 thứ Hai | Tiến độ 100 video |

Nhịp khai được: `at` + `days` (thứ trong tuần), `everyHours`, hoặc `dayOfMonth`
(khai 31 mà tháng ngắn hơn thì chạy ngày cuối tháng).

Cron **chỉ được đọc** (S3) — dispatcher chặn, không tin file lịch. CEO không được tự đặt lịch (S2).

## Lệnh Telegram (không tốn hạn mức)

```
/duyet    việc đang chờ duyệt, kèm nút
/hanmuc   đã dùng bao nhiêu, còn bao nhiêu
/baocao   hoạt động 7 ngày qua
/quyen    các quyền tự chạy đang có
/stop     dừng mọi việc đang chạy (L6)
/moi      mở luồng hội thoại mới
```

Chúng chạy bằng code cứng, không gọi CEO — nên vẫn trả lời được khi hạn mức đã cạn.
Hỏi "còn bao nhiêu hạn mức" mà phải tốn hạn mức để biết thì là thiết kế sai.
