# HANDOFF.md — đọc file này trước khi làm tiếp Travis

> Viết 2026-09-20, cuối một đợt dài. Mục đích: người (hoặc phiên) tiếp theo
> không phải dò lại từ đầu.
>
> Trạng thái đo được: `git tag travis-plan-complete-2026-09-20`

---

## 1. Chạy ba lệnh này trước khi tin bất cứ điều gì dưới đây

```bash
python3 tests/run.py            # cả bộ — từng mảnh + cả dây chuyền (nó tự in số ca)
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

**§43 Definition of Done:** xem [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md),
nó có **cách tự kiểm từng ô** (đừng chép số ô vào đây — số chép tay thì lặng
lẽ cũ đi).

---

## 2b. Vừa xong 2026-09-20: Policy đọc mức tự chủ (mục (a) cũ)

Admin chốt hàng rào **OPT-IN**: company phải tự khai `autonomyOptIn` cho từng
năng lực trong `companySpec.yaml`. Không khai = không bao giờ tự chạy, dù
thống kê đẹp tới đâu. Chi tiết ba điều kiện: DEFINITION_OF_DONE.md.

**Nhưng phần đáng đọc là cái phát hiện ra lúc nối dây.**

`trackRecordRows` đang đếm cả lưu lượng của bộ đo. `recordWrite` có 227 dòng
thì 194 là `e2e_`, 33 là `demo_` — không một lời gọi thật nào, mà bảng in ra
mức 2. Chừng nào con số ấy chỉ để NHÌN thì nó là một phép đo bẩn; từ lúc
Policy đọc nó thì nó là **một cánh cửa mở được bằng `python3 tests/run.py`**.

Đã loại `reg_ evl_ e2e_ demo_` khỏi phép tính. Hậu quả: `xuongCompany.nhanViec`
tụt 77% → 20%, `ghiBuoc` 69% → 0%. **Con số cũ đẹp phần lớn là của bộ đo** —
đó mới là tỉ lệ thật, và nó nói xuongCompany còn xa mức tự chủ.

Hôm nay chưa năng lực `write` nào tự chạy. Năng lực duy nhất khai opt-in là
`travisSelfTestCompany.recordWriteAuto` và nó đang ở mức 1.

⚠ `recordWrite` **cố ý KHÔNG khai** opt-in: nó là chốt canh cho ba ca
`TestWritePathNeedsASignature`. Đừng khai cho nó — đặt chốt canh lên chính
cánh cửa nó canh thì ca thử sẽ xanh theo cửa đang mở.

---

## 2c. Cũng xong 2026-09-20: Memory · Secret broker · Event bus

Ba mục (b)(c)(d) của bản HANDOFF cũ. Chi tiết ở
[DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md); ở đây chỉ ghi thứ người sau
cần biết trước khi chạm vào.

**Memory — gom LUẬT, cố ý KHÔNG dời DỮ LIỆU.** Viết test đối chiếu trước như
HANDOFF dặn, và nó đỏ ngay: 3/4 mốc trong một ngày cho kết quả khác nhau giữa
`core/memory` và `session.profile_block`. Nay luật ngày rụng ở
`contracts.isStillValid`, ba nơi cùng đọc.

⚠ **Kho thì vẫn tách, và đừng "dọn" nó.** PROFILE.md thuộc `profileCompany`,
có đường ghi qua nút duyệt, admin sửa tay được. Dời vào sqlite là phá C2 và
lấy mất khả năng sửa tay. Trí nhớ phiên (`message`, `threadSummary`) cũng ở
lại: năm nơi đang đọc, và nó không cần tầng/nhãn/ngày rụng.

**Secret broker — phiếu GÁNH VIỆC.** `allowedSecretNames` dựng từ PHIẾU, không
từ manifest, nên broker từ chối thì khoá không vào tiến trình con. Tra bằng
`travis.py secrets`.

⚠ Cách nối SAI và dễ hơn: cấp phiếu chỉ để có dòng trong sổ, vẫn bơm theo
manifest. Lúc đó §30 trả lời rất đẹp trong khi phiếu không kiểm soát gì.

**Event bus — chỉ đề xuất.** Chạy trong nhịp 15 phút sẵn có. Chống nhắn lặp
bằng `eventId` TẤT ĐỊNH theo nội dung sự cố, không bằng bảng trạng thái thứ
hai.

⚠ Đừng nhét mốc thời gian quét vào `deterministicEventId` — mỗi lần quét sẽ
đẻ một id mới, tức là quay lại đúng 21 tin lúc nửa đêm, chỉ khác là lần này
có cả một hàm trông như đang chống lặp.

---

## 2d. Cũng xong 2026-09-20 (đợt chiều): bốn chỗ hỏng THẬT + Employee lên đường chạy

Đợt này **không xây thêm tính năng** — đi soát, và soát ra bốn chỗ hỏng mà ba
bộ kiểm đều xanh suốt:

| Hỏng | Triệu chứng |
|---|---|
| `poller.GATEWAY` trỏ vào file chưa từng tồn tại | **Mọi tin nhắn admin** ra "Hệ gặp lỗi khi xử lý", từ §36 |
| `session.py` tự gọi lại mình qua tên cũ | "Bức tranh hiện tại" không bao giờ làm mới — `Popen` nuốt cả stderr |
| `codemap` tìm ca thử ở thư mục cũ | Hàng rào **tự tắt**, bỏ qua 29 ca, vẫn in "SOÁT LUẬT: sạch" |
| Thợ hỏi "có việc không?" bằng lệnh GHI | **219 thẻ duyệt/ngày** cho một xưởng trống |

⚠ Cái đầu nằm im **không ai biết** vì admin chưa nhắn lần nào sau khi đổi tên
— journal có ĐÚNG 0 dòng `gateway lỗi`. Bài học chung: **ca thử xanh chỉ
chứng minh thứ nó chạy qua; nó không chứng minh đường thật có chạy.**

**Employee lên đường chạy.** Đo được: 6/6.146 lời gọi thật mang `employeeId`
— 0,1%. Nay `dispatch` mặc định `employeeId = ceo`, và `employees/ceo/
employee.yaml` khai quyền **đo từ cả danh mục**, không từ lưu lượng.

⚠ Mặc định nằm ở **dispatcher**, không ở prompt — CEO tự gõ lệnh và `guard.py`
chỉ cho vài cờ, nên một luật sống trong lời dặn là luật model phá được.

⚠ Kèm theo: manifest nay khai được `action:` (`riskTier` nói NẶNG CỠ NÀO,
`action` nói LÀM GÌ). Không khai thì vẫn suy như cũ — 87 năng lực còn lại
không đổi hành vi.

---

## 3. Việc tiếp theo

**§43 chỉ còn một ô ⬜: sandbox cứng** (container/VM, cgroup, netns, seccomp).
§41 xếp nó vào nhóm KHÔNG làm sớm, và `isolationMaturity()` nói thẳng cái chưa
có. Một hệ nói dối về mức cô lập nguy hiểm hơn hệ không cô lập gì.

Hai ô 🔶 còn lại đều là **quyết định**, không phải nợ — đọc lý do trong
DEFINITION_OF_DONE trước khi "hoàn thiện" chúng.

Việc đáng làm hơn, xếp theo giá trị:

**a. Cho một năng lực `write` THẬT leo thang tự chủ.** Cửa đã dựng và đã kiểm
hai chiều, nhưng chưa ai trèo: năng lực duy nhất khai `autonomyOptIn` là
company nội bộ. Ứng viên gần nhất là `nhacCompany.datNhac` — nhưng nó đang ở
mức 1, và `xuongCompany` thì tỉ lệ đạt thật chỉ 20%. Việc thật ở đây là **đi
tìm vì sao tỉ lệ đạt thấp**, không phải nới hàng rào.

**b. Soát lại những con số đang được tin.** Hai lần trong một ngày 20/09, một
phép đo bẩn lộ ra ngay lúc có ai đó định dùng nó để quyết định. Còn con số nào
trong hệ đang được đọc mà chưa ai hỏi "ai đã ghi những dòng này"?

**c. Thêm luật cho event bus.** Bộ luật hiện có năm cái, đều chỉ BÁO. Luật thứ
sáu phải qua `proposalsAreReadOnly` — và ca thử
`testEveryDefaultRuleProposesOnlyReadWork` chạy mọi luật với event thật, nên
nó đỏ ở bàn làm việc chứ không đỏ lúc 3 giờ sáng.

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

   ⚠ **Con số 77% đó đã bị chính đợt 20/09 bác bỏ** — đừng đọc nó như trạng
   thái hiện tại. Nó chỉ đúng chừng nào còn đếm cả lưu lượng bộ đo; lọc
   `reg_ evl_ e2e_ demo_` ra thì `xuongCompany.nhanViec` quay về **20%**.
   Tức là lần sửa ấy đúng về LUẬT (needsApproval không phải trượt) nhưng con
   số nó khoe ra lại đến từ một mẫu bẩn. Hai cái sai ngược chiều nhau che mất
   nhau, và cả hai đều không có dòng lỗi nào. Xem mục 2b.

Cả bốn cùng một họ với bảng bẫy trong [../CLAUDE.md](../CLAUDE.md) — **đọc
bảng đó trước khi viết mã đụng vào cùng chỗ.**

---

## 7. Repo ĐÃ đẩy lên GitHub — `Bloor7/companySpec`, PRIVATE

> Dòng cũ ở đây ghi "CHƯA đẩy". Sai từ lúc nào không rõ, và không ai phát
> hiện vì không ai chạy `git remote -v` — đúng loại tài liệu chép tay rồi
> lặng lẽ cũ đi mà `CLAUDE.md` đã dặn tránh. Cách biết là CHẠY, không phải đọc.

Theo luật trong `CLAUDE.md`: chỉ đẩy khi admin bảo, và chỉ kho `companySpec`.
Không đụng kho nào khác của `Bloor7` — nhất là `handoff_panharmon`.

Soát trước mỗi lần đẩy:

```bash
git remote -v
curl -s -o /dev/null -w '%{http_code}\n' https://api.github.com/repos/Bloor7/companySpec
git ls-files | grep -iE '\.env|secret|token'
```

⚠ **Từ 20/09/2026 kho để PUBLIC — admin chốt**, để nhờ người và model khác
review kiến trúc. Nên `200` là ĐÚNG, đừng dừng vì nó. Luật đã viết lại trong
[../CLAUDE.md](../CLAUDE.md): điều §11 luật 11 lo thì vẫn nguyên, chỉ đổi chỗ
— repo không còn được che, nên thứ nhạy cảm phải KHÔNG NẰM TRONG repo.

Đã soát: `ops/.env` và mọi sổ `.sqlite` không trong git, chatId/tên bot không
trong git (F6). Còn `companies/profileCompany/PROFILE.md` **thì có** và nó
mang hồ sơ đời tư — admin chưa quyết gỡ.

Và một phép soát nữa, rẻ, trả lời câu "đẩy lần này có ghi đè của ai không":

```bash
git fetch origin
git merge-base --is-ancestor origin/main HEAD && echo "đẩy thẳng được"
```
