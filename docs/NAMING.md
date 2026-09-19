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

## 4. Cách chuyển đổi

Không sửa tay 50 file. Đổi bằng máy, soát bằng máy:

```bash
python3 ops/namingAudit.py                  # xem còn tên nào lệch luật
python3 ops/renameIdentifiers.py --plan     # in ra sẽ đổi gì, KHÔNG đổi
python3 ops/renameIdentifiers.py --apply    # đổi thật
python3 ops/codemap.py --check              # luật kiến trúc còn đứng không
python3 tests/regression/run.py             # hành vi có đổi không
```

Thứ tự bắt buộc: **`--plan` trước, đọc kỹ, rồi mới `--apply`.**

### Những thứ KHÔNG được đổi tự động

Máy không được tự đụng vào bốn chỗ này, vì đổi sai thì hỏng lặng lẽ:

1. **Tên thuộc tính trên Notion.** Chúng là dữ liệu thật của admin, nằm ngoài
   repo. Company dịch tên trường ↔ tên thuộc tính Notion; chỉ đổi phía repo.
2. **Giá trị `enum` tiếng Việt.** `danhMuc: [ăn uống, đi lại, …]` là **giá
   trị**, không phải **tên**. Đổi giá trị là làm hỏng dữ liệu lịch sử trên
   Notion và làm chết mọi whitelist đang khoá vào chúng.
3. **Văn xuôi tiếng Việt.** Mô tả, comment, playbook, `SYSTEM.md` vẫn tiếng
   Việt — admin đọc chúng. Chỉ đổi **định danh** nằm trong đó.
4. **Dữ liệu lịch sử đã ghi.** `whitelist.jsonl`, `approvals.sqlite`,
   `store.sqlite` cần **migration riêng**, không phải tìm-và-thay.

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
