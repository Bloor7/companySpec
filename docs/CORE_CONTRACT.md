# CORE_CONTRACT.md — từ vựng chung của Travis

> Đây là **hợp đồng từ vựng**, không phải mô tả code. Mọi tầng — gateway,
> policy, executor, employee, brain, company — phải dùng đúng những danh từ
> dưới đây với đúng nghĩa dưới đây.
>
> Luật nền: [PRINCIPLES.md](../PRINCIPLES.md) · Bản đồ đi đường:
> [../CLAUDE.md](../CLAUDE.md) · Kiến trúc: [ARCHITECTURE.md](ARCHITECTURE.md)

---

## Vì sao cần file này

Dự án đã có một bài học đắt nhất, ghi ở dòng đầu bảng bẫy trong `CLAUDE.md`:
**sai tên trường đầu vào** làm báo cáo tối in "thu 0đ · chi 0đ" suốt nhiều tuần
mà không ai biết. Nguyên nhân gốc không phải người viết ẩu — mà là **cùng một
khái niệm có nhiều tên**, và không nơi nào chép lại tên đúng.

File này là nơi đó.

Quy tắc đọc: một khái niệm ở đây có **đúng một tên**. Thấy tên khác trong code
nghĩa là code sai, không phải file này thiếu.

---

## Bảng 15 primitive

| Primitive | Một câu | Ai sở hữu |
|---|---|---|
| `Task` | Một đơn vị công việc có thể chạy và kiểm được | `core/task` |
| `Capability` | Một khả năng hệ thống thực thi được, do company khai | `companySpec.yaml` |
| `Policy` | Luật quyết định một Task được phép đi tiếp hay không | `core/policy` |
| `Permission` | Quyền CÓ PHẠM VI của một chủ thể lên một tài nguyên | `core/permission` |
| `Execution` | Một lần chạy thật của một Task, kèm mọi dấu vết | `core/execution` |
| `Employee` | Một "người" có danh tính, vai trò, trí nhớ và quyền riêng | `employees/` |
| `Brain` | Bộ não suy luận (model/provider), thay được | `brains/` |
| `Project` | Nơi làm việc: repo, workspace, môi trường | `registry/projects.yaml` |
| `Mission` | Mục tiêu dài hạn, đẻ ra nhiều Task | `core/mission` |
| `Memory` | Thứ hệ nhớ được, phân tầng và phân loại | `core/memory` |
| `Secret` | Giá trị nhạy cảm, KHÔNG BAO GIỜ là Memory | `core/secret` |
| `Event` | Một điều đã xảy ra, có thể kích hoạt Task | `core/event` |
| `Approval` | Chữ ký của admin cho đúng MỘT nội dung | `core/policy/approval` |
| `Verification` | Bằng chứng rằng kết quả đúng, không phải lời khai | `core/verification` |
| `Audit` | Sổ không sửa được: ai làm gì, vì sao được phép | `core/audit` |

---

## 1. `Task`

**Purpose.** Đơn vị nhỏ nhất mà hệ thống có thể cho phép, chạy, kiểm và ghi sổ.
Không có gì chạy ngoài một Task.

**Input.**

```json
{
  "taskId": "tsk_...",
  "traceId": "trc_...",
  "parentTaskId": null,
  "missionId": null,
  "projectId": null,
  "employeeId": null,
  "companyId": "expenseCompany",
  "capability": "addExpense",
  "input": {},
  "riskTier": "write",
  "issuedBy": "admin",
  "issuedAt": "2026-09-19T13:00:00Z"
}
```

**Output.** Một `Execution` và một trạng thái cuối.

**Owner.** `core/task`. Chỉ Core được đổi trạng thái Task; company không bao giờ
tự đặt trạng thái của chính mình.

**Lifecycle.**

```text
created → planned → approvalRequired → approved → running → verifying → completed
```

Các nhánh kết thúc khác: `failed`, `cancelled`, `denied`, `quarantined`,
`blocked`, `budgetExceeded`, `needsInput`, `scheduled`.

> **Luật T-1.** Trạng thái là thứ Core ghi, không phải thứ Task tự nhận. Bài học
> `is_done()` trong `CLAUDE.md`: agent tự gọi "done" với nội dung là câu kế
> hoạch. Từ đây "xong" chỉ đến từ `Verification`, không đến từ lời khai.

**Security boundary.** `riskTier` **luôn lấy từ manifest**, không bao giờ từ
envelope hay từ model (G3). Model đề xuất Task; model không tự hạ rủi ro của nó.

---

## 2. `Capability`

**Purpose.** Một việc cụ thể mà một company làm được, khai bằng dữ liệu chứ
không bằng code.

**Input / Output.** `inputSchema` và `outputSchema` trong `companySpec.yaml`.
Cả hai đều `additionalProperties: false` — trường không khai là trường bị chặn.

**Owner.** File `companies/<x>/companySpec.yaml`. Đây là **nguồn chân lý duy
nhất** cho tên năng lực và tên trường.

**Lifecycle.** Khai → `codemap --check` soát → xuất hiện trong danh mục của CEO
→ gọi được.

**Security boundary.**

- Capability ≠ Permission. Có `repository.write` không có nghĩa được ghi **mọi**
  repository. Phạm vi do `Permission` quyết định.
- Khai `paidApi` nếu tiêu tiền thật (L8). Quên khai thì `codemap --check` bắt.
- `whitelistScope: []` nghĩa là **ĐÓNG**, không phải "không giới hạn". Xem bảng
  bẫy trong `CLAUDE.md`.

---

## 3. `Policy`

**Purpose.** Điểm quyết định duy nhất cho câu hỏi "Task này có được đi tiếp
không". Hôm nay logic ấy nằm rải trong `ops/dispatch.py:cmdCall`; Core biến nó
thành một hàm thuần có thể kiểm bằng unit test.

**Input.**

```text
identity  ← ai yêu cầu (admin | employee | scheduler | system | brain)
resource  ← chạm vào cái gì (repository | filesystem | database | telegram | web | secret | production)
action    ← làm gì (read | create | modify | delete | deploy | send | publish)
environment ← ở đâu (lab | dev | staging | production)
riskTier  ← nặng cỡ nào (read | low | write | high | irreversible)
```

**Output.** Đúng một `PolicyDecision`:

```text
allow              — đi thẳng
allowWithVerify    — được chạy, nhưng chưa xong tới khi Verification pass
allowWithApproval   — phải có chữ ký admin
dryRun             — chạy giả, không tác động ra ngoài
deny               — chặn
quarantine         — chặn và cách ly vật thể vào
```

**Owner.** `core/policy`.

**Lifecycle.** Thuần tuý: cùng đầu vào → cùng quyết định. Không đọc mạng, không
đọc giờ, không gọi model.

**Security boundary.**

> **Luật P-1.** Policy là **code**, không phải prompt. Một luật chỉ viết trong
> `SYSTEM.md` là luật model phá lúc nào cũng được mà không ai biết. Mọi ranh
> giới thật phải có một phép soát bằng code — như `_soKhongNguon` đã làm với
> hội đồng.

> **Luật P-2.** Policy không tin envelope. `riskTier`, danh sách secret, hạn
> chót đều đọc từ file trên đĩa.

---

## 4. `Permission`

**Purpose.** Quyền **có phạm vi**. Đây là thứ phân biệt "Forge được ghi repo"
với "Forge được ghi repo Panharmon, nhánh phụ, môi trường dev".

**Input.**

```yaml
subject: forge            # employee | company | scheduler
resource: repository
action: write
scope:
  projectId: panharmon
  environment: dev
  branchNotIn: [main]
```

**Output.** `true` / `false` kèm lý do đọc được.

**Owner.** `core/permission`, dữ liệu ở `employees/<x>/employee.yaml` và
`registry/projects.yaml`.

**Security boundary.**

> **Luật PM-1.** Không có quyền ngầm định. Không khai = không có.

> **Luật PM-2.** Personality không tạo Permission (P3 của kế hoạch Travis).
> Employee "mạnh dạn" không vì thế mà được deploy production.

---

## 5. `Execution`

**Purpose.** Một lần chạy thật, và **toàn bộ dấu vết** của nó.

**Output.**

```json
{
  "executionId": "exe_...",
  "taskId": "tsk_...",
  "employeeId": "forge",
  "brainId": "claude",
  "policyDecision": "allowWithVerify",
  "inputHash": "...",
  "filesChanged": [],
  "sideEffects": [],
  "verification": {},
  "costUsd": 0.0,
  "paidVnd": 0,
  "startedAt": "...",
  "finishedAt": "..."
}
```

**Owner.** `core/execution`.

**Security boundary.**

- Executor **không chứa nghiệp vụ**. Nó biết tiến trình, timeout, retry, huỷ,
  giới hạn tài nguyên, thu output — không biết chi tiêu là gì.
- Timeout tầng ngoài phải **lớn hơn hẳn** ngân sách tầng trong; timeout tầng
  dispatcher phải **nhỏ hơn hẳn** ngân sách. Hai chiều ngược nhau, cả hai đều
  đã gây sự cố thật (xem `CLAUDE.md`).
- Mọi `subprocess.run(timeout=…)` phải có `except TimeoutExpired` trả kết quả
  **báo được** (O8). Cửa vào không được phép sập.

---

## 6. `Employee`

**Purpose.** Danh tính bền vững, tách khỏi model đang dùng.

```text
Employee = identity + role + personality + expertise
         + responsibilities + memory + permissions + brainPreference
```

**Owner.** `employees/<employeeId>/employee.yaml`.

**Security boundary.**

> **Luật E-1.** Đổi Brain không làm mất Employee. `forge` hôm nay chạy bằng
> Claude, mai bằng GPT, vẫn là `forge`, vẫn giữ nguyên trí nhớ và quyền.

> **Luật E-2.** `cannot:` trong manifest là **luật cứng**, thắng mọi thứ khác.

---

## 7. `Brain`

**Purpose.** Bộ não suy luận. Thay được, xếp hàng dự phòng được.

**Interface.**

```python
class Brain:
    def reason(self, prompt: str, context: BrainContext) -> BrainReply: ...
    def generate(self, prompt: str, context: BrainContext) -> BrainReply: ...
    def review(self, subject: str, context: BrainContext) -> BrainReply: ...
```

**Owner.** `brains/<brainId>/`, danh mục ở `registry/models.yaml`.

**Security boundary.**

- **Data boundary.** Prompt gửi ra nhà ngoài phải **cắt được theo khối**, và
  phải **nói với model là đã cắt**. Bài học đã đo: một lượt đi ra 37.282 byte
  có cả hồ sơ đời tư và số dư ví. Không nói đã cắt thì model đi tìm, không
  thấy, rồi **bịa số**.
- Tên model chỉ tin khi `nao kiem` vừa hỏi thật nhà cung cấp. Nhà rút model mà
  không báo ai.
- Nhiều model đồng thuận **không phải** bằng chứng. Chúng học từ cùng một mớ
  chữ nên sai giống nhau.

---

## 8. `Project`

**Purpose.** Nơi làm việc: repo nào, thư mục nào, môi trường nào, ai được vào.

**Owner.** `registry/projects.yaml` (đã tồn tại).

**Security boundary.** Company **không bao giờ** trỏ vào thư mục làm việc thật
của admin — ở đó có việc dở và có `.env.local` chứa khoá thật. Company tự clone
bản riêng.

---

## 9. `Mission`

**Purpose.** Mục tiêu dài hạn đẻ ra nhiều Task. `Task` = việc cụ thể;
`Mission` = thứ việc đó phục vụ.

```text
Mission = objective + projects + tasks + metrics + risks + schedule + review
```

**Owner.** `core/mission`, dữ liệu ở `missions/`.

**Security boundary.** Travis được tự chia Mission thành Task. Travis **không**
được vì thế mà bỏ qua Policy: mỗi Task con vẫn đi qua đúng cánh cửa đó.

---

## 10. `Memory`

**Purpose.** Thứ hệ nhớ được qua các phiên.

**Phân tầng.**

| Tầng | Sống bao lâu | Ví dụ |
|---|---|---|
| `sessionMemory` | một cuộc trò chuyện | tin nhắn gần nhất |
| `workingMemory` | một Task / Mission đang chạy | việc đang làm, thứ đang vướng |
| `projectMemory` | đời của Project | tech stack, quyết định cũ, bug đã biết |
| `employeeMemory` | đời của Employee | cách làm từng đúng, lỗi từng mắc |
| `personalMemory` | dài hạn về admin | thói quen, cách làm việc |
| `systemMemory` | đời của hệ | luật bảo mật, quyết định kiến trúc |

**Phân loại.** Mỗi mẩu nhớ phải mang đúng một nhãn:

```text
fact       — sự thật kiểm được
decision   — một lựa chọn đã chốt, kèm lý do
inference  — suy đoán; BẮT BUỘC có confidence + source + createdAt
```

**Security boundary.**

> **Luật M-1.** Không biến `inference` thành `fact`. Suy đoán không nguồn là
> thứ phải nói lại cho admin, không phải thứ được cất như sự thật.

> **Luật M-2.** Thứ chỉ đúng **trong một quãng** phải có ngăn riêng kèm ngày
> rụng (`expiresAt`). Cất mà không hẹn ngày hết còn tệ hơn không cất.

> **Luật M-3.** `Secret` không bao giờ là `Memory`.

---

## 11. `Secret`

**Purpose.** Khoá, token, mật khẩu.

**Security boundary.** Tuyệt đối không nằm trong:

```text
memory · prompt · audit log · source code · employee profile · envelope
```

Company **chỉ nhận đúng những secret nó đã khai** trong manifest (C2.4). Danh
sách lấy từ đĩa, không từ envelope — model không nới được.

Đích đến là `secretBroker`: cấp credential **phạm vi hẹp, sống ngắn**, theo
từng lần hỏi, thay vì để một chủ thể cầm cả chùm khoá.

---

## 12. `Event`

**Purpose.** Một điều đã xảy ra, có thể đẻ ra Task.

```text
taskFailed · taskCompleted · repoChanged · dependencyUpdated
productionDown · buildFailed · budgetNearLimit · missionStalled
repositoryAdded · scheduledCheck · quotaHit
```

**Security boundary.** Event **đề xuất** Task, không **cấp quyền** cho Task.
Task do Event đẻ ra vẫn đi qua Policy như mọi Task khác — `scheduledTrigger`
chỉ được đọc, trừ khi cầm phiếu hẹn admin đã ký (S3).

> **Luật EV-1.** Lỗi hạ tầng lặp lại thì nhắn lần đầu, lặp thì im, khỏi thì báo
> kèm số lần. 21 tin giống hệt lúc nửa đêm dạy admin bỏ qua thông báo.

---

## 13. `Approval`

**Purpose.** Chữ ký của admin cho **đúng một nội dung**.

**Security boundary.**

- Khoá vào nội dung bằng `payloadHash` (G4). Đổi nội dung là chữ ký hết giá trị.
- Dùng **đúng một lần**.
- `irreversible` và `paidApi` **không bao giờ** đi đường whitelist.
- Trả lời cái bấm **ngay khi nhận**, đừng đợi việc chạy xong: Telegram chỉ nhận
  `answerCallbackQuery` trong ~15 giây, và nút báo đỏ dạy admin rằng nút duyệt
  không đáng tin.

---

## 14. `Verification`

**Purpose.** Biến "đã xong" từ **lời khai** thành **bằng chứng**.

**Output.**

```json
{
  "status": "verified",
  "checks": [
    { "name": "typecheck", "status": "passed" },
    { "name": "build",     "status": "passed" },
    { "name": "visual",    "status": "passed" }
  ]
}
```

**Bộ kiểm.** `tests · typecheck · lint · build · security · browser · visual · data`

**Security boundary.**

> **Luật V-1.** Không có bằng chứng thì Task **không** completed. "Không chắc"
> tính là **chưa xong**.

> **Luật V-2.** Bộ đo phải đứng trong phép đo. Thứ nào tiêu hạn mức thì phải
> ghi sổ, kể cả công cụ của chính hệ. Ghi chung một bảng, tách bằng nhãn.

---

## 15. `Audit`

**Purpose.** Trả lời được, sau nhiều tuần, câu: *chuyện gì đã xảy ra và vì sao
nó được phép*.

**Mỗi Execution phải ghi.**

```text
task · employee · brain · capability · policyDecision · inputHash
outputs · filesChanged · sideEffects · verification · cost · timestamps
```

**Security boundary.**

> **Luật A-1.** Lần bị **chặn** cũng là dữ liệu (O5). Ghi cả cái bị từ chối.

> **Luật A-2.** Không nuốt lỗi thành giá trị hợp lệ. `or {}`, `or 0`,
> `except: return ""` biến số 0 thành "hôm nay không tiêu gì" (O10).

> **Luật A-3.** Cắt log lỗi từ **đuôi**, không từ đầu: traceback Python để loại
> lỗi ở dòng cuối.

> **Luật A-4.** Mã thoát 0 **không** có nghĩa là chạy được. Soi cả `isError`
> trong JSON.

---

## Quan hệ giữa các primitive

```text
Mission ──┬─> Task ──> Policy ──> Execution ──> Verification ──> Audit
          │              ↑            │
          │              │            └─> Memory
          │         Permission
          │              ↑
          └─────── Employee ──> Brain

Project ──> (scope cho Permission)
Event ────> (đẻ ra Task, KHÔNG cấp quyền)
Secret ───> (chỉ qua secretBroker, không bao giờ vào Memory)
```

---

## Definition of Done cho từng primitive

Một primitive coi là **xong** khi có đủ bốn thứ:

1. Một dataclass/enum trong `core/` — không phải dict trần.
2. Một hàm thuần kiểm được bằng unit test, không cần mạng.
3. Một mục trong `tests/regression/` đóng băng hành vi hiện tại.
4. Một dòng trong `Audit` khi nó chạy thật.

Thiếu (3) thì mọi thay đổi sau này là đánh bạc. Thiếu (4) thì không ai trả lời
được câu "vì sao nó được phép".
