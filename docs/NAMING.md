# NAMING.md — một khái niệm, một tên, ở mọi nơi

> Thi hành [PRINCIPLES.md §7](../PRINCIPLES.md). Đây không phải quy ước mới —
> đây là quy ước cũ **chưa từng được thi hành**.

---

## 1. Vì sao file này tồn tại

§7 của hiến pháp đã ra luật từ đầu:

> *"Tiếng Anh, `camelCase`, thống nhất ở **mọi nơi**: biến, field JSON, cột
> SQLite, key YAML."*

Thực tế đếm được trong manifest hôm nay: phần lớn tên trường là tiếng Việt, và
tên năng lực lẫn lộn hai thứ tiếng trong **cùng một company**:

```text
expenseCompany:
  addExpense(soTien, danhMuc, ghiChu, ngay)   → {amount, category, date}
  suaExpense(expenseId, soTien, ghiChu)
  listExpenses(tuNgay, denNgay, gioiHan, tuKhoa)
```

Vào tiếng Việt, ra tiếng Anh, tên hàm thì nửa nọ nửa kia. Đếm lại bằng:

```bash
python3 ops/namingAudit.py
```

### Đây chính là con bug đắt nhất dự án

Dòng đầu bảng bẫy trong `CLAUDE.md`:

> *Gọi company bằng tên trường không có trong `companySpec.yaml` → `rejected`.
> Báo cáo tối in "thu 0đ · chi 0đ" suốt nhiều tuần.*

Và dòng khác, cùng họ:

> *Ca mới lọt ra ngoài vùng phủ. Lọt ngay lần đầu dùng: viết `tenSuKien` trong
> khi manifest khai `ten`.*

Nguyên nhân gốc không phải người viết ẩu. Nguyên nhân là **cùng một khái niệm
có nhiều tên**, và không có cách nào đoán ra tên đúng:

- "số tiền" là `soTien` khi vào, `amount` khi ra;
- "ngày" là `ngay`, `date`, `tuNgay`, `denNgay`, `datLuc`, `hetHan`, `han`;
- "tên" là `ten` ở company này, `tieuDe` ở company kia, `title` ở company thứ ba.

Model phải **đoán**, và nó đoán bằng thứ tiếng Việt hợp lý nhất — vốn thường
sai. Mỗi lần đoán sai là một lời gọi `rejected`, một vòng lặp thêm, và đôi khi
là một con số sai lặng lẽ.

---

## 2. Luật

### L1 — Tiếng Anh, camelCase, mọi nơi

Áp dụng cho: **tên company · tên năng lực · trường input · trường output ·
cột SQLite · key YAML · tên hàm Python · tên biến Python · tên file `.py`**.

Ngoại lệ duy nhất: biến môi trường giữ `UPPER_SNAKE` theo chuẩn shell.

### L2 — Python cũng camelCase, và đây là chỗ tớ đi ngược PEP 8 có chủ ý

Python thường dùng `snake_case`. Dự án này **không**, vì một lý do đo được:

Lỗi tốn công nhất ở đây là **tên trường lệch giữa JSON/YAML và code**. Khi JSON
là `camelCase` còn biến Python là `snake_case`, **mỗi ranh giới là một điểm
dịch**, và mỗi điểm dịch là một chỗ trôi:

```python
# hai tên cho một khái niệm → chỗ để bug nấp
soTien = inp["soTien"]        # cũ: còn phải nhớ Việt-Anh nữa
amount_value = inp["amount"]  # snake_case: còn phải nhớ đổi kiểu chữ
```

```python
# một tên duy nhất → không còn gì để trôi
amount = inp["amount"]
```

Đã có tiền lệ thật trong repo: `inp['amount']` sót lại sau khi schema đổi sang
`soTien`, gây `KeyError` **đúng lúc cần báo lỗi tử tế**.

> **Đổi tên là rẻ. Điểm dịch là đắt.** Bỏ PEP 8 ở đây mua lại việc xoá hẳn một
> họ lỗi.

### L3 — Năng lực là **động từ + tân ngữ**

```text
addExpense · listExpenses · auditSite · createPlan · sendReport
```

Không đặt theo người gọi (N3 cũ): `auditSite`, không `ceoAudit`.

### L4 — Không viết tắt

`traceId` chứ không `tid`. `configuration` chứ không `cfg`. Ngoại lệ chỉ những
từ đã là tiêu chuẩn ngành: `id`, `url`, `api`, `http`, `json`, `yaml`, `sql`,
`db`, `ms`, `sec`, `usd`, `vnd`, `utc`, `iso`, `kpi`, `seo`, `ui`, `ux`.

### L5 — Hậu tố mang nghĩa

| Hậu tố | Nghĩa | Ví dụ |
|---|---|---|
| `At` | một mốc thời gian ISO 8601 UTC | `createdAt`, `deadlineAt`, `expiresAt` |
| `Ms` / `Sec` | thời lượng | `durationMs`, `maxDurationSec` |
| `Usd` / `Vnd` | tiền | `costUsd`, `paidVnd` |
| `Id` | định danh | `taskId`, `employeeId` |
| `Count` | số lượng | `stepCount`, `retryCount` |
| `is` / `has` / `can` | boolean (tiền tố) | `isReversible`, `hasApproval`, `canRetry` |

### L6 — Mã ngôn ngữ giữ nguyên

`vi`, `en`, `zh`, `ja`, `ko` là **mã ISO 639-1**, không phải chữ viết tắt tiếng
Việt. Giữ nguyên, không đổi thành `vietnamese`.

### L7 — Một khái niệm một tên, kể cả khi trái tai

Đã chọn `amount` cho "số tiền" thì **mọi** company dùng `amount`, kể cả
`walletCompany` vốn quen gọi là `soDu`. Số dư là `balance`; số tiền của một
giao dịch là `amount`. Hai khái niệm khác nhau thì hai tên khác nhau — nhưng
**một** khái niệm thì dứt khoát **một** tên.

---

## 3. Hàng rào

> Luật N1 (xem [CONSTITUTION_REVIEW.md](CONSTITUTION_REVIEW.md)): mọi luật phải
> có một phép soát chạy được. Hàng rào giả hại hơn không có hàng rào.

| Luật | Ai canh | Chạy bằng |
|---|---|---|
| L1, L3, L4, L5, L6 | `ops/namingAudit.py` | `python3 ops/namingAudit.py --check` |
| L1 cho manifest | `ops/codemap.py --check` | có sẵn, mở rộng thêm |
| L7 (một khái niệm một tên) | `registry/naming.yaml` | bản đồ chuẩn, soát được |
| Không sót handler | `tests/regression/testManifestContract.py` | mọi năng lực phải có handler |

`registry/naming.yaml` là **nguồn chân lý**: nó ghi mỗi tên tiếng Việt cũ ứng
với tên tiếng Anh nào. Đây vừa là bản đồ chuyển đổi, vừa là bộ từ điển cho
người viết company mới — thêm khái niệm mới thì thêm một dòng ở đó trước.

---

## 4. Phạm vi: áp cho code MỚI, không đổi code cũ

**Quyết định 2026-09-19 (admin chốt):** không đổi tên hàng loạt code đang chạy.

Đã đo thử phạm vi của một lần đổi toàn bộ: **3.265 chỗ · 60 file · 38 cột
SQLite có dữ liệu sống**. Và khi soi kỹ thì nó không hề "mechanical" như vẻ
ngoài — có ít nhất ba lớp bẫy khiến thay-tự-động là thay-sai:

- **Từ tiếng Việt không dấu trùng định danh.** `ngay` vừa là trường "ngày",
  vừa là từ "ngay lập tức" nằm trong câu báo lỗi cho admin đọc. Thay mù biến
  *"phải chặn ngay"* thành *"phải chặn date"* — không lỗi cú pháp, không ai báo.
- **Tên trùng giá trị.** `tamDung` vừa là tên năng lực, vừa là **giá trị** của
  `trangThai` trong `WHERE trangThai IN ('moi','tamDung')`. `xong` cũng vậy.
  Thay tên thì hỏng dữ liệu.
- **Cột SQLite có dữ liệu sống.** Đổi cột mà sót một chỗ đọc là hỏng lặng lẽ,
  đúng loại lỗi đắt nhất dự án.

Giá phải trả cao, thứ mua lại được thì thấp: code cũ **đang chạy đúng**.

### Vậy file này để làm gì

`registry/naming.yaml` là **từ điển**, không phải danh sách việc phải làm.

Viết company mới, năng lực mới, trường mới, hay code trong `core/` thì **tra từ
điển trước**, để không đẻ thêm tên thứ ba cho một khái niệm đã có tên:

```bash
python3 ops/namingAudit.py           # xem từ điển và mọi định danh đang có
python3 ops/namingAudit.py --check   # chỉ kêu khi SAI THẬT (xem dưới)
```

`--check` chỉ đỏ với hai thứ, vì chúng là lỗi thật chứ không phải nợ cũ:

| Kêu khi | Vì sao |
|---|---|
| Mục từ điển trỏ vào thứ không tồn tại | Từ điển nói dối người tra nó |
| Tên không phải camelCase | Phạm §7 về hình thức, sửa rẻ |

### Bốn chỗ vĩnh viễn KHÔNG đụng

1. **Tên thuộc tính Notion** (`"Số tiền"`, `"Ngày"`) — dữ liệu thật của admin,
   nằm ngoài repo.
2. **Giá trị `enum` tiếng Việt** — `[ăn uống, đi lại, …]` là **giá trị**, không
   phải **tên**. Đổi là làm hỏng lịch sử và giết mọi whitelist khoá vào chúng.
3. **Văn xuôi tiếng Việt** — mô tả, comment, playbook, `SYSTEM.md`. Admin đọc
   chúng.
4. **Dữ liệu lịch sử đã ghi** — `whitelist.jsonl`, `store.sqlite`.

---

## 5. Từ điển gốc

Bản đầy đủ ở [`registry/naming.yaml`](../registry/naming.yaml). Vài khái niệm
hay nhầm nhất:

| Tiếng Việt | Chuẩn | Ghi chú |
|---|---|---|
| `soTien` | `amount` | tiền của MỘT giao dịch |
| `soDu` | `balance` | tiền CÒN LẠI trong ví — khác `amount` |
| `danhMuc` | `category` | |
| `ngay` | `date` | |
| `tuNgay` / `denNgay` | `fromDate` / `toDate` | khoảng thời gian |
| `hetHan` | `expiresAt` | có hậu tố `At` theo L5 |
| `ghiChu` | `note` | |
| `tieuDe` / `ten` | `title` / `name` | `title` cho nội dung, `name` cho thực thể |
| `noiDung` | `content` | |
| `trangThai` | `status` | |
| `uuTien` | `priority` | |
| `gioiHan` | `limit` | |
| `tuKhoa` | `keyword` | |
| `lyDo` | `reason` | |
| `nguon` | `source` | |
| `hanChot` | `dueDate` | |
| `viecId` | `taskId` | **cùng** khái niệm với `taskId` của Core |
| `moTa` | `description` | |
| `ketQua` | `result` | |
| `mucTieu` | `objective` | |

> Dòng `viecId → taskId` là ví dụ rõ nhất của L7: hai tầng đang gọi **cùng một
> thứ** bằng hai tên, và đó chính là chỗ người đọc code lạc đường.
