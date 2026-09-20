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
| ✅ | Employee có identity riêng | `employees/` | `travis.py employees` |
| ✅ | Brain độc lập với Employee | `brains/` | đổi `brains.preferred` không mất employee |
| ✅ | Data boundary theo classification | `brains/router.py` | `travis.py brains sensitive` |
| ✅ | Brain Council có kiểm soát | `brains/council.py` | `unsourcedClaims` nêu tên số không nguồn |

## Dữ liệu và mục tiêu

| | Mục §43 | Ở đâu | Tự kiểm |
|---|---|---|---|
| ✅ | Project có registry | `projects/` | `travis.py` đọc được `projects/registry.yaml` |
| ✅ | Mission là first-class object | `core/missions/` | `travis.py mission list` |
| ✅ | Secrets không nằm trong memory | `core/memory.looksLikeSecret` | `tests/run.py --only Memory` |
| 🔶 | Memory được phân tầng | `core/memory/` | **CHƯA NỐI** — gateway vẫn tự lo trí nhớ phiên |
| 🔶 | Secret access có scope | `core/secrets/` | **CHƯA NỐI** — secret vẫn đi thẳng từ `os.environ` |

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
| 🔶 | Events cho phép Travis proactive | `core/events/` | soát tuần + chống nhắn lặp **đã chạy**; event bus (đẻ Task) **chưa nối** |
| 🔶 | Autonomy có nhiều level | `core/policy/autonomy.py` | Thang **LEO ĐƯỢC THẬT** — `travis.py autonomy`. Chưa dùng để bớt hỏi admin |
| 🔶 | Travis có thể đề xuất self-improvement | `core/events/review.py` | `proposals()` — nêu chỗ hỏng dần, kèm SỐ. Dừng ở CHỮ, cố ý |

## Cô lập cứng

| | Mục §43 | Ở đâu | Tự kiểm |
|---|---|---|---|
| ⬜ | Sandbox có filesystem/network/resource limits | `core/permissions/isolation.py` | mới là cô lập **LOGIC** — `isolationMaturity()` nói thẳng |

---

## Vì sao ba ô còn 🔶, và một ô còn ⬜

**Memory chưa nối.** `gateway/telegram/session.py` có bộ nhớ phiên riêng đã
chạy qua nhiều tháng. Nối vào `core/memory` là đổi thứ đang giữ trí nhớ của
admin — phải có test đối chiếu trước, giống `testPolicyParity`. Chưa có test
đó thì nối là đánh bạc.

**Secret broker chưa nối.** `core/execution` đang bơm secret thẳng từ
`os.environ` theo danh sách trong manifest (C2.4), và cách đó **đã an toàn**.
Broker thêm được hạn dùng và sổ tra; nó là cải tiến, không phải vá lỗ.

**Autonomy: thang đã LEO ĐƯỢC, nhưng chưa ai dùng nó để bớt hỏi admin.**

Trước 2026-09-20 nó kẹt ở mức 1 cho mọi thứ vì sổ không có dòng `completed`
nào. Nay `completed` được **SUY RA TỪ BẰNG CHỨNG**: `core/audit` đọc
`verificationJson` thay vì đọc tên trạng thái.

Không đổi `taskLog.status` thành `completed` là có chủ ý — **năm chỗ** đang
đọc đúng chuỗi `ok` (trần whitelist ngày, thống kê backOffice, trí nhớ CEO
trong một trace, báo cáo và dọn dòng cron của scheduler). Đổi là gãy cả năm
trong im lặng.

Đo thật hôm nay:

| Năng lực | Mức | Vì sao |
|---|---|---|
| `nhacCompany.dsNhac` | **4** | 200/200 đã kiểm chứng, `read` nên trần là 4 |
| `travisSelfTestCompany.recordWrite` | **2** | 23/23 đã kiểm chứng — **chạm trần `write`** |
| `xuongCompany.nhanViec` | 1 | tỉ lệ đạt 77% < 90% |

Việc còn lại là để Policy ĐỌC mức đó rồi bớt hỏi admin. Đó phải là một quyết
định có chủ ý của admin, không phải thứ tự xảy ra vì code đã sẵn sàng.

**Sandbox cứng chưa làm.** §41 xếp nó vào nhóm không làm sớm, và
`isolationMaturity()` nói thẳng cái chưa có (container/VM, cgroup, netns,
seccomp). Một hệ nói dối về mức cô lập nguy hiểm hơn hệ không cô lập gì — vì
người dùng nó sẽ dám làm những việc đáng ra không dám.

---

## Tự kiểm toàn bộ

```bash
python3 tests/run.py            # 209 ca — từng mảnh + cả dây chuyền
python3 ops/codemap.py --check  # luật kiến trúc
python3 gateway/cli/travis.py verify   # chính Verification Engine soi repo này
python3 gateway/cli/travisDemo.py      # một lời gọi đi hết dây chuyền
```
