# ARCHITECTURE.md — Travis: hôm nay, đích đến, và đường đi

> Từ vựng: [CORE_CONTRACT.md](CORE_CONTRACT.md) · Luật nền:
> [../PRINCIPLES.md](../PRINCIPLES.md) · Bảo mật: [SECURITY.md](SECURITY.md) ·
> Quyền tự chủ: [AUTONOMY.md](AUTONOMY.md) · Đặt tên: [NAMING.md](NAMING.md)

**Không có con số nào trong file này.** Số company, số năng lực, số file đều
đếm bằng lệnh — chép tay thì lặng lẽ cũ đi:

```bash
python3 ops/codemap.py
```

---

## 0. Travis là gì

Một **Personal AI Operating System** chạy local-first cho đúng một người.
Không phải chatbot gọi được nhiều tool. Khác nhau ở chỗ: chatbot **nói** rằng
nó đã làm; hệ điều hành **chứng minh** được nó đã làm, và chứng minh được vì
sao nó được phép làm.

Mục tiêu không phải làm cho AI không bao giờ sai. Mục tiêu là: AI **có thể**
sai, nhưng thiệt hại bị chặn trần, cái sai bị phát hiện, kết quả được kiểm
chứng, và hệ học được từ đó.

---

## 1. Hôm nay hệ đang đứng ở đâu

Đây là phần **đo được**, không phải phần mong muốn.

```text
Telegram ──> ops/poller.py ──> ops/gateway.py ──> phiên CEO (Claude CLI)
                                     │                    │
                                     │                    └──> ops/dispatch.py
                                     │                              │
                              ops/approvals.py <────────────────────┤
                                     │                              ↓
                              admin bấm nút                  companies/<x>/src/main.py
                                                                    │
                                                             backOffice/store.sqlite
```

Cửa vào thứ hai là `ops/scheduler.py` (cron), cửa thứ ba là `ops/cau.py`
(từ hộp `hop/`).

### Cái đã có, và có tốt

`ops/dispatch.py` hôm nay **đã là một policy engine**, chỉ là chưa ai gọi nó
bằng tên đó. Nó đã làm đủ:

| Thứ Travis cần | Đã có ở đâu |
|---|---|
| Task envelope (`taskId`, `traceId`, budget, policy) | `dispatch.cmdCall` |
| Risk tier lấy từ manifest, không từ model | `dispatch` G3 |
| Approval khoá vào nội dung bằng hash | `ops/approvals.py` G4 |
| Whitelist có phạm vi và trần ngày | `approvals.whitelistMatch` G8 |
| Audit: `taskLog`, `sideEffectLog` | `backOffice/store.sqlite` |
| Secret theo phạm vi company | `dispatch` C2.4 |
| Chống lặp vô hạn | `dispatch` L4 |
| Cầu dao tiền thật | `dispatch` L8 |
| Kiểm schema hai chiều | `dispatch.validate` C2.3 |
| Bộ não thay được + chuỗi dự phòng | `ops/nao.py` |
| Đo hành vi bằng ca thử | `ops/evals/` |
| Danh mục dự án | `registry/projects.yaml` |

Đây là lý do **không rewrite**. Phần khó nhất — ranh giới quyền và dấu vết —
đã đứng vững qua nhiều sự cố thật, mỗi sự cố để lại một dòng trong bảng bẫy
của `CLAUDE.md`. Vứt đi là vứt luôn những bài học đó.

### Cái còn thiếu

| Thiếu | Hậu quả hôm nay |
|---|---|
| `PolicyDecision` tường minh | Quyết định nằm rải trong một hàm dài; không unit-test được |
| Tầng `Employee` | Không có ai để giao việc; mọi thứ đổ lên một CEO duy nhất |
| `Brain` như interface | `nao.py` đã thay não được nhưng chưa có hợp đồng chung |
| `Mission` | Không có mục tiêu dài hạn; mỗi lượt là một tờ giấy trắng |
| `Verification` | "Xong" vẫn là **lời khai**, không phải bằng chứng |
| `Memory` phân tầng | Trí nhớ nằm rải giữa gateway, `profileCompany`, `ceo/store.sqlite` |
| `Event bus` | Hệ chỉ phản ứng khi admin gõ, hoặc khi cron tới giờ |
| `Lab` / `Acquisition` | Không có chỗ an toàn để thử repo lạ |
| `tests/regression/` | Không có lưới; mọi refactor là đánh bạc |
| Tên thống nhất | §7 ra luật tiếng Anh camelCase — thực tế đã lệch khỏi luật đó |

---

## 2. Đích đến

```text
Telegram / CLI
      ↓
  Travis Core
      ↓
Mission ──> Task
      ↓
  Employee
      ↓
 Brain Router
      ↓
 Policy Engine
      ↓
Execution Engine
      ↓
Companies / Capabilities
      ↓
 Verification
      ↓
Audit + Memory
      ↓
Notification
```

Mô hình khái niệm đổi như sau:

| Cũ | Mới |
|---|---|
| CEO → Company → Capability | Mission → Task → Employee → Capability → Execution |

Nghĩa của từng vai:

```text
Core     = luật + quyền + execution
Employee = người
Brain    = bộ não
Company  = công cụ / bộ phận thực thi
Project  = nơi làm việc
Mission  = mục tiêu
Lab      = nơi học và thử cái mới
```

### Lab và Main

```text
              Travis Core
                   │
         ┌─────────┴─────────┐
         ↓                   ↓
        LAB                MAIN
   research / test       production
   acquisition          trusted tools
   experiments          real projects
   sandbox              real credentials
         │                   │
         └──── promotion ────┘
```

Lab **được phép thất bại**. Main thì không. Repo bên ngoài là **đầu vào không
đáng tin**: không bao giờ `clone → install → run → Main`.

---

## 3. Bốn nguyên tắc chi phối mọi quyết định dưới đây

**A1 — LLM không có quyền lực trực tiếp.** Model được reason, plan, propose,
generate, explain. Code quyết định allow, deny, execute, verify, rollback.
Một luật chỉ viết trong prompt là luật model phá lúc nào cũng được mà không ai
biết — nên mọi ranh giới thật phải có **một phép soát bằng code**.

**A2 — "Xong" phải có bằng chứng.** Bài học `is_done()`: agent tự gọi "done"
với nội dung là câu kế hoạch, company báo XONG, CEO nói với admin đã gửi form,
thật ra chưa gửi gì.

**A3 — Thêm company không được sửa Core.** Phải sửa Core để thêm company nghĩa
là hợp đồng đang rò. Sửa hợp đồng, đừng sửa Core.

**A4 — Đo trước khi chốt.** Mọi quyết định kiến trúc lớn trong dự án này đều
đến từ một phép đo. Chưa đo thì nói rõ là chưa đo.

---

## 4. Cấu trúc đích

```text
companySpec/
├── core/                  ← hệ điều hành: luật, quyền, execution
│   ├── contracts.py           15 primitive, dataclass + enum
│   ├── policy/                quyết định allow/deny/approval
│   ├── permission/            quyền có phạm vi
│   ├── execution/             tiến trình, timeout, retry, rollback
│   ├── verification/          bằng chứng
│   ├── memory/                phân tầng + phân loại
│   ├── secret/                broker, credential sống ngắn
│   ├── event/                 event bus
│   ├── mission/               mục tiêu dài hạn
│   ├── audit/                 sổ không sửa được
│   └── registry/              nạp manifest, project, employee
│
├── gateway/               ← cửa vào
│   ├── telegram/
│   └── cli/
│
├── brains/                ← bộ não, thay được
│   ├── claude/  gemini/  gpt/  local/
│
├── employees/             ← người
│   ├── atlas/  forge/  iris/  sage/  sentinel/
│
├── companies/             ← công cụ thực thi (giữ nguyên)
├── projects/              ← nơi làm việc
├── missions/              ← mục tiêu
├── lab/                   ← nơi thử
│   ├── quarantine/  sandboxes/  experiments/
│   ├── benchmarks/  candidates/  rejected/
├── backOffice/            ← theo dõi và báo cáo
├── tests/
│   ├── regression/            đóng băng hành vi cũ
│   └── security/              chứng minh hàng rào đứng
└── docs/
```

`ops/` **không biến mất**. Nó co lại thành lớp vỏ mỏng gọi vào `core/`.

---

## 5. Migration map

Không rewrite. Mỗi dòng là một đường đi, không phải một lần xoá.

| Hôm nay | Đích | Cách đi |
|---|---|---|
| `ops/dispatch.py` | `core/policy` + `core/execution` | Bóc hàm thuần ra trước, `dispatch` gọi vào |
| `ops/approvals.py` | `core/policy/approval` | Đổi chỗ, giữ nguyên bảng sqlite |
| `ops/gateway.py` | `gateway/telegram` + `core/memory/session` | Bóc từng khối, file này to nhất nên đi cuối |
| `ops/scheduler.py` | `core/event/scheduler` | Giữ nguyên tới khi có event bus |
| `ops/nao.py` | `brains/` + `core/brainRouter` | Interface trước, mới chuyển |
| `lib/skillRun.py` | `core/execution/brainRunner` | |
| `backOffice/store.sqlite` | `core/audit` | Không đổi schema, chỉ đổi người ghi |
| `companies/*` | giữ nguyên | Đây là phần đang chạy tốt |
| `ceo/SYSTEM.md` | `employees/` + system policy | CEO thành một employee, không phải trời |
| `profileCompany` | `core/memory/personal` | |

Mỗi bước đi theo đúng một khuôn:

```text
logic cũ → interface mới → adapter tương thích → test → chuyển người gọi → xoá bản cũ
```

**Không bao giờ** xoá bản cũ trước khi test xanh và người gọi đã chuyển hết.

---

## 6. Thứ tự phụ thuộc

Đây là thứ tự **bắt buộc**, vì mỗi tầng đứng trên tầng dưới:

```text
0  Baseline: regression tests + docs          ← lưới an toàn
1  Naming: một khái niệm một tên               ← nền cho mọi thứ sau
2  Core contracts: 15 primitive                ← từ vựng
3  Policy + Permission                         ← luật
4  Execution Engine                            ← tay chân
5  Employee + Brain                            ← người và não
6  Memory + Project                            ← trí nhớ
7  Mission + Verification                      ← mục tiêu và bằng chứng
8  Lab + Acquisition                           ← học cái mới
9  Event + Proactive                           ← tự phát hiện
10 Autonomy                                    ← nới quyền, có bằng chứng
11 Brain Council                               ← nhiều góc nhìn
12 Hard isolation + Secret broker              ← sandbox thật
```

Chặng **1 phải đi sớm**: dựng `core/` trên nền tên lộn xộn thì sau này phải
đổi tên cả `core/` nữa.

---

## 7. Những thứ cố ý KHÔNG làm sớm

```text
20+ employee            Vector DB khổng lồ       multi-agent chat vô hạn
tự sửa Core             autonomous deploy        Kubernetes / microservices
dashboard khổng lồ      local LLM phức tạp
```

Lý do chung: **Core ổn định trước, capability sau.** Và một lý do riêng đã đo
được — để agent lái một việc đã biết trước cách làm thì tốn 4–9 phút, ba lần
đều trượt; kịch bản cứng chạy 16 giây, đúng mọi lần, 0đ. Agent chỉ đáng dùng
khi **không biết trước** phải bấm gì.
