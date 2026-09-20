# DEFINITION_OF_DONE.md — 24 ô của §43, và ô nào thật sự tick được

> Cập nhật 2026-09-20. Mỗi dòng có **cách tự kiểm** — một ô tick mà không kiểm
> được thì nó là lời khai, không phải bằng chứng (V-1 áp cho chính tài liệu này).

Ba mức, và sự khác nhau giữa chúng là điều quan trọng nhất ở đây:

| | Nghĩa |
|---|---|
| ✅ | Đã dựng **và** đang chạy trong hệ thật |
| 🔶 | Đã dựng, kiểm được, nhưng **chưa nối** vào đường chạy |
| ⬜ | Chưa làm |

> 🔶 **không phải** ✅. Dựng xong mà chưa nối thì ta có hai bản của cùng một
> luật — đúng thứ đã gây vụ "hạn mức ăn uống" ra hai con số mà cả hai đều
> không lỗi.

---

## Core

| | Mục §43 | Ở đâu | Tự kiểm |
|---|---|---|---|
| ✅ | Core quản lý task | `core/task/` | bảng `ALLOWED_TRANSITIONS` chặn `created → completed` |
| ✅ | Policy là điểm quyết định quyền | `core/policy/` | `tests/run.py --only PolicyParity` |
| ✅ | Permission có scope | `core/permissions/` | `travis.py employees` |
| ✅ | Execution có lifecycle | `core/execution/` + `core/task/` | `tests/run.py --only Execution` |
| ✅ | Execution có verification | `core/verification/` | `travis.py why <taskId>` |
| ✅ | Audit có đầy đủ evidence | `core/audit/` | `travis.py why <taskId>` |

## Người và bộ não

| | Mục §43 | Ở đâu | Tự kiểm |
|---|---|---|---|
| ✅ | Employee có identity riêng | `employees/` | `travis.py employees` · và từ 20/09 employee NẰM TRÊN đường chạy: `travis.py why <taskId>` in tên người gọi, không còn "(CEO gọi thẳng)" |
| ✅ | Brain độc lập với Employee | `brains/` | đổi `brains.preferred` không mất employee |
| ✅ | Data boundary theo classification | `brains/router.py` | `travis.py brains sensitive` |
| ✅ | Brain Council có kiểm soát | `brains/council.py` | `unsourcedClaims` nêu tên số không nguồn |

## Dữ liệu và mục tiêu

| | Mục §43 | Ở đâu | Tự kiểm |
|---|---|---|---|
| ✅ | Project có registry | `projects/` | `travis.py` đọc được `projects/registry.yaml` |
| ✅ | Mission là first-class object | `core/missions/` | `travis.py mission list` |
| ✅ | Secrets không nằm trong memory | `core/memory.looksLikeSecret` | `tests/run.py --only Memory` |
| 🔶 | Memory được phân tầng | `core/memory/` | LUẬT đã gom (`contracts.isStillValid`, gateway hỏi core) — `tests/run.py --only MemoryParity`. KHO thì vẫn tách, cố ý: xem dưới |
| ✅ | Secret access có scope | `core/secrets/` | `travis.py secrets` — phiếu GÁNH VIỆC: không có phiếu thì khoá không vào tiến trình con |

## Lab

| | Mục §43 | Ở đâu | Tự kiểm |
|---|---|---|---|
| ✅ | Lab cô lập khỏi Main | `lab/` ↔ `main/` | `isInsideLab` dùng đường dẫn chuẩn hoá |
| ✅ | Repo bên ngoài được quarantine | `core/lab/` | `travis.py acquire <đường dẫn>` |
| ✅ | Acquisition có security/license/dependency review | `core/lab/acquisition.py` | `tests/run.py --only Acquisition` |
| ✅ | Promotion từ Lab → Main có policy | `core/lab.promote` | `checkPromotionReadiness` |

## Chủ động và tự chủ

| | Mục §43 | Ở đâu | Tự kiểm |
|---|---|---|---|
| ✅ | Scheduler hỗ trợ health/review | `core/events/review.py` + lịch `weeklyReview` | `scheduler.py run --force weeklyReview` |
| ✅ | Events cho phép Travis proactive | `core/events/` | bus chạy trong nhịp 15 phút (`scheduler.duyet_su_kien`), đề xuất được ĐẨY tới admin |
| ✅ | Autonomy có nhiều level | `core/policy/autonomy.py` | `travis.py autonomy` — cột cuối nói năng lực nào ĐANG tự chạy. Policy đọc mức từ 2026-09-20 |
| 🔶 | Travis có thể đề xuất self-improvement | `core/events/review.py` | `proposals()` — nêu chỗ hỏng dần, kèm SỐ. Dừng ở CHỮ, cố ý |

## Cô lập cứng

| | Mục §43 | Ở đâu | Tự kiểm |
|---|---|---|---|
| ⬜ | Sandbox có filesystem/network/resource limits | `core/permissions/isolation.py` | mới là cô lập **LOGIC** — `isolationMaturity()` nói thẳng |

---

## Vì sao hai ô còn 🔶, và một ô còn ⬜

**Memory: gom LUẬT, cố ý KHÔNG dời DỮ LIỆU.** (2026-09-20)

Làm đúng theo lời dặn của HANDOFF: **test đối chiếu trước**
(`tests/regression/testMemoryParity.py`), và nó đỏ ngay — đo được **3 trên 4
mốc trong một ngày** cho kết quả khác nhau giữa `core/memory` và
`session.profile_block`. Hai nguyên nhân, cả hai đã có tên trong bảng bẫy: so
chuỗi ngày 10 ký tự với mốc ISO 20 ký tự, và lọc theo UTC trong khi ngày của
admin tính theo giờ VN. Cái sai nghiêng về hướng **mất trí nhớ của admin**:
`[đến 15/10]` rụng ngay 00:00 ngày 15/10 thay vì hết ngày.

Nay định nghĩa gốc nằm ở `core/contracts.isStillValid` — tầng thấp nhất, **ba
nơi** cùng đọc (SQL của `recall`, `MemoryItem.isExpired`, và gateway). Ma trận
SQL↔Python ép hai thân nói giống nhau, và chính nó bắt thêm một lỗ: `expiresAt
= ""` **ghi vào được mà không bao giờ đọc ra**.

Ô này giữ 🔶 vì **kho vẫn tách**, và đó là quyết định chứ không phải việc còn
nợ: PROFILE.md thuộc `profileCompany`, có đường ghi qua nút duyệt, và admin
sửa tay được. Dời nó vào `core/memory.sqlite` là phá C2, bắt viết lại đường
ghi, và lấy mất khả năng sửa tay — đổi một thứ đang chạy tốt lấy một sơ đồ
gọn hơn. Trí nhớ PHIÊN (`message`, `threadSummary`) cũng ở lại chỗ cũ: năm
nơi đang đọc nó, và nó không cần tầng/nhãn/ngày rụng.

**Secret broker đã nối, và phiếu GÁNH VIỆC.** (2026-09-20)

`ProcessLimits.allowedSecretNames` nay dựng **từ phiếu cấp được**, không từ
manifest. Nghĩa là broker từ chối thì khoá KHÔNG đi vào tiến trình con — chứ
không phải vẫn đi vào mà sổ ghi là đã từ chối. Cách nối sai (và dễ hơn) là
cấp phiếu chỉ để có dòng trong sổ: lúc đó `auditTrail()` trả lời rất đẹp cho
§30 trong khi cái phiếu không kiểm soát gì. Đó là hàng rào giả.

`travis.py secrets` trả lời được câu §30 "khoá nào đã bị chạm". Sổ phiếu TÁCH
lưu lượng bộ đo (một lượt `tests/run.py` đẻ ~190 phiếu) và tự dọn phiếu bộ đo
đã hết hạn quá 2 ngày, ở đúng nhịp 15 phút đang dọn dòng cron.

**Autonomy: Policy đã ĐỌC mức, và hàng rào là OPT-IN.** (admin chốt 20/09)

`core/policy._ruleEarnedAutonomy` bỏ qua cửa duyệt khi **cả ba** điều kiện
cùng đúng. Ba điều kiện độc lập với nhau là có chủ ý — gỡ một cái thì hai cái
kia vẫn giữ:

1. company **tự khai** `autonomyOptIn` cho đúng năng lực đó trong
   `companySpec.yaml` (`Capability.canEverActOnEarnedAutonomy`);
2. mức đã **kiếm được** ≥ 2, tính từ sổ audit thật;
3. trần rủi ro cho phép — `irreversible` và `paidApi` **không bao giờ** đi
   đường này, dù thống kê đẹp tới đâu.

Kết quả luôn là `allowWithVerify`, không bao giờ là `allow` trần: được tự do
hơn thì phải chứng minh nhiều hơn, không phải ít hơn.

Vì sao opt-in chứ không để bằng chứng tự quyết: thống kê nói năng lực đó CHẠY
ĐÚNG, nó không nói **hậu quả của một lần sai** là gì. Chỉ người viết company
biết điều đó.

**Cùng ngày, phát hiện một phép đo bẩn — và nó là phần quan trọng hơn.**

`trackRecordRows` đếm cả lưu lượng của bộ đo. Trong 227 dòng của
`travisSelfTestCompany.recordWrite` có 194 dòng `e2e_` và 33 dòng `demo_` —
**không một lời gọi thật nào**, mà bảng mức tự chủ in ra mức 2. Chừng nào con
số ấy chỉ để NHÌN thì đó là một phép đo bẩn; từ lúc Policy đọc nó thì nó là
một cánh cửa mở được bằng `python3 tests/run.py` chạy vài lần.

Đã loại `reg_ evl_ e2e_ demo_`. Con số thật sau khi lọc khác hẳn:

| Năng lực | Trước | Sau | Ghi chú |
|---|---|---|---|
| `nhacCompany.dsNhac` | mức 4 (200/200) | **mức 4** (200/200) | `read`, vốn đã không phải hỏi |
| `travisSelfTestCompany.recordWrite` | mức 2 (26/26) | **biến mất** | 100% là lưu lượng bộ đo |
| `xuongCompany.nhanViec` | tỉ lệ 77% | **20%** | tỉ lệ đẹp phần lớn là của `reg_` |
| `xuongCompany.ghiBuoc` | tỉ lệ 69% | **0%** | |

Hôm nay **chưa năng lực `write` nào tự chạy**. Năng lực duy nhất khai opt-in
là `travisSelfTestCompany.recordWriteAuto` (company nội bộ, tác động là một
dòng trong sổ sqlite của chính nó), và nó đang ở mức 1 vì chưa có lời gọi
THẬT nào. Đó là trạng thái đúng: cửa đã dựng, đã kiểm hai chiều, và nó sẽ chỉ
mở cho năng lực nào kiếm được bằng chứng ngoài bộ đo.

Không đổi `taskLog.status` thành `completed` vẫn là có chủ ý — **năm chỗ**
đang đọc đúng chuỗi `ok` (trần whitelist ngày, thống kê backOffice, trí nhớ
CEO trong một trace, báo cáo và dọn dòng cron của scheduler). `completed` được
**SUY RA TỪ BẰNG CHỨNG**: `core/audit` đọc `verificationJson`.

**Event bus đã nối, và nó CHỈ đề xuất.** (2026-09-20)

`scheduler.duyet_su_kien()` chạy trong nhịp 15 phút sẵn có: tra sự cố thật
(lời gọi hỏng, chạm trần hạn mức, mission đứng bánh, im lặng quá lâu) →
`core.events.eventsFromFacts` (hàm THUẦN) → bus → `proposalsAreReadOnly` →
**đẩy tin tới admin**. Không thi hành gì.

Ba thứ được canh bằng ca thử, mỗi thứ là một hoá đơn cũ:

· **EV-1 bằng code.** Có đề xuất việc GHI thì bỏ TOÀN BỘ, không lọc bớt — một
  bộ luật đã đẻ ra thứ nó không được phép đẻ thì không đáng tin phần còn lại.
· **Không nhắn lặp.** `eventId` tất định theo NỘI DUNG sự cố, nên 6 tiếng sự
  cố × quét 15 phút một lần vẫn ra đúng một tin. Không có bảng trạng thái thứ
  hai để lệch. Bẫy 21 tin lúc nửa đêm.
· **Có người được báo.** Vòng nào chạy xong mà người cần biết không biết thì
  tính là CHƯA XONG.

Đo thật 20/09 trên sổ tạm có một sự cố thật: quét lần 1 ra 2 đề xuất và một
tin; quét lần 2 im lặng. Trên sổ THẬT thì 0 đề xuất — 2.210 dòng hỏng trong 6
giờ đều mang nhãn bộ đo (`reg_ e2e_ demo_`) nên bị loại, đúng như phải thế.

`taskFailed` cố ý KHÔNG đề xuất chạy lại: tự thử lại khi chưa biết vì sao
hỏng là cách biến một lỗi thành một vòng lặp, và đó là đặc quyền của mức tự
chủ 3 mà chưa năng lực nào đạt tới.

**Sandbox cứng chưa làm.** §41 xếp nó vào nhóm không làm sớm, và
`isolationMaturity()` nói thẳng cái chưa có (container/VM, cgroup, netns,
seccomp). Một hệ nói dối về mức cô lập nguy hiểm hơn hệ không cô lập gì — vì
người dùng nó sẽ dám làm những việc đáng ra không dám.

---

## Tự kiểm toàn bộ

```bash
python3 tests/run.py            # cả bộ — từng mảnh + cả dây chuyền (nó tự in số ca)
python3 ops/codemap.py --check  # luật kiến trúc
python3 gateway/cli/travis.py verify   # chính Verification Engine soi repo này
python3 gateway/cli/travisDemo.py      # một lời gọi đi hết dây chuyền
```
