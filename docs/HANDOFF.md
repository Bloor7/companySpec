# HANDOFF.md — đọc file này trước khi làm tiếp Travis

> Viết 2026-09-20, cuối một đợt dài. Mục đích: người (hoặc phiên) tiếp theo
> không phải dò lại từ đầu.
>
> Trạng thái đo được: `git tag travis-plan-complete-2026-09-20`

---

## 1. Chạy ba lệnh này trước khi tin bất cứ điều gì dưới đây

```bash
python3 tests/run.py            # 218 ca — từng mảnh + cả dây chuyền
python3 ops/codemap.py --check  # luật kiến trúc
python3 gateway/cli/travisDemo.py   # nhìn một lời gọi đi hết dây chuyền
```

Ba lệnh này không tốn tiền, không cần mạng, không đụng dữ liệu của admin.
Nếu chúng đỏ thì mọi thứ dưới đây là lời khai, không phải sự thật.

---

## 2. Hệ đang ở đâu

**Cấu trúc §35 đã dựng xong** — `core/` (12 gói) · `gateway/{telegram,cli}` ·
`brains/` · `employees/` · `projects/` · `missions/` · `lab/` ↔ `main/`.
`ops/` **không còn là tầng điều phối** (xem [ops/README.md](../ops/README.md)).

**Một lời gọi đi qua:**

```text
gateway/cli/dispatch.py
  → C2.1/C2.2 → Employee → core/policy → C2.3 → L4
  → core/execution → C2.3 ra → core/verification → core/audit
```

Tra lại bất kỳ lời gọi nào: `python3 gateway/cli/travis.py why <taskId>`.

**§43 Definition of Done:** 19 ✅ · 4 🔶 · 1 ⬜ —
xem [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md), nó có **cách tự kiểm từng ô**.

---

## 3. Bốn việc tiếp theo, xếp theo giá trị

### a. Để Policy ĐỌC mức tự chủ rồi bớt hỏi admin

Thang **đã leo được thật** (`travis.py autonomy`): `nhacCompany.dsNhac` đạt
mức 4 với 200/200 lần đã kiểm chứng. Nhưng `core/policy.decide()` chưa đọc nó,
nên mọi việc `write` vẫn hỏi.

Việc: thêm `earnedAutonomyLevel` vào `PolicyRequest`, và ở
`_ruleApprovalToken`/trước đó, cho phép bỏ qua cửa duyệt khi
`mayActWithoutAsking(level, riskTier)`.

⚠ Đây là **nới quyền**. Phải là quyết định có chủ ý của admin, không phải thứ
tự xảy ra vì code đã sẵn sàng. Làm xong phải có ca thử chứng minh
`irreversible` vẫn không bao giờ tự chạy.

### b. Nối Memory vào phiên CEO

`core/memory/` đã có phân tầng, nhãn `fact/decision/inference`, ngày rụng, và
chặn secret ở cửa vào. `gateway/telegram/session.py` vẫn giữ trí nhớ riêng.

⚠ Đây là thứ đang giữ trí nhớ của admin. **Phải có test đối chiếu trước**,
giống `tests/regression/testPolicyParity.py` đã làm cho policy — chứng minh
hai bên trả về cùng một thứ trước khi chuyển người gọi.

### c. Nối Secret broker

`core/secrets/` cấp phiếu mang TÊN (không mang giá trị), có hạn 5 phút, có sổ
tra. `core/execution` hiện bơm secret thẳng từ `os.environ` theo manifest
(C2.4) — cách đó **đã an toàn**, broker là cải tiến chứ không phải vá lỗ.

Giá trị thật: `auditTrail()` trả lời được câu §30 "secret nào đã bị chạm".

### d. Event bus đẻ Task

`core/events/` đã có luật chống nhắn lặp (đang chạy trong scheduler) và bản
soát tuần. Phần `EventBus` + `TaskProposal` chưa ai gọi.

⚠ EV-1: event **đề xuất** Task, không **cấp quyền**. Task do event đẻ ra vẫn
qua đúng cánh cửa Policy — `proposalsAreReadOnly()` canh chuyện đó.

---

## 4. Bảy dòng `travis health` đang kêu — KHÔNG phải lỗi mới

`Lời gọi KHÔNG qua Policy: 7` — đó là dòng cũ từ bộ ca thử, ghi **trước** khi
nhãn `evl_` được gắn. Chúng tự rụng khỏi cửa sổ 7 ngày. Đừng đi sửa gì.

Cách xác nhận: chúng đều là `khongCoCompany.abc` (company giả của ca thử) và
mốc thời gian đều là 2026-09-19T19:02.

---

## 5. Những chỗ CỐ Ý không làm, đừng "sửa" chúng

| Thứ | Vì sao để vậy |
|---|---|
| `taskLog.status` vẫn là `ok`, không phải `completed` | **Năm chỗ** đọc đúng chuỗi ấy: trần whitelist ngày, thống kê backOffice, trí nhớ CEO, báo cáo và dọn dòng cron. `completed` được SUY RA từ `verificationJson` |
| Không đổi tên hàng loạt code cũ sang tiếng Anh | Admin chốt 19/09. `registry/naming.yaml` là **TỪ ĐIỂN** cho code mới |
| `main/` trống | Chưa thứ gì từ ngoài được thăng cấp. Đó là trạng thái an toàn nhất |
| Cô lập mới là **logic**, chưa có container | §41 xếp vào nhóm không làm sớm. `isolationMaturity()` nói thẳng |
| `brains/gpt/` và `brains/local/` trống | Chỗ đứng cho §11, chưa khai trong `models.yaml` |
| Company được import `brainRunner` từ `core/` | Ngoại lệ CÓ TÊN trong `ops/codemap.py:NGOAI_LE_CORE_CHO_COMPANY`. Hẹp tới một module |

---

## 6. Bốn cái bẫy đã dính trong đợt này — đừng dính lại

1. **Module trùng tên gói.** Có `gateway/` và `gateway.py` cùng lúc thì
   `import gateway` trả về một gói **rỗng**. Không lỗi lúc nạp, chỉ vỡ ở chỗ
   dùng đầu tiên. Vì vậy module ấy tên `session.py`.

2. **`core/` không được là người vận chuyển.** Scheduler `import telegram` →
   codemap bắt. Cách chữa **không phải** nới luật mà là tách: động cơ ở
   `core/events/scheduler.py`, dây dẫn ở `gateway/cli/scheduler.py`.

3. **Báo động về quá khứ.** Đếm dòng cũ hơn cột `policyDecision` ra "5288 lời
   gọi không qua cửa". Sàn phải **suy từ dữ liệu**, không viết cứng ngày.

4. **`needsApproval` không phải trượt.** Đếm nó vào mẫu số làm tỉ lệ đạt tụt
   vô nghĩa (20% → 77% sau khi sửa), và cái sai nghiêng về phía CHẶT nên nó
   im lặng.

Cả bốn cùng một họ với bảng bẫy trong [../CLAUDE.md](../CLAUDE.md) — **đọc
bảng đó trước khi viết mã đụng vào cùng chỗ.**

---

## 7. Repo CHƯA đẩy lên GitHub

Theo luật trong `CLAUDE.md`: chỉ đẩy khi admin bảo, và chỉ kho `companySpec`.
Soát trước mỗi lần đẩy:

```bash
git remote -v
curl -s -o /dev/null -w '%{http_code}\n' https://api.github.com/repos/Bloor7/companySpec
git ls-files | grep -iE '\.env|secret|token'
```

`404` = private (đúng). `200` = **PUBLIC, DỪNG LẠI**.
