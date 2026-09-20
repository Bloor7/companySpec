# ops/ — công cụ vận hành. KHÔNG còn là tầng điều phối.

Trước 2026-09-20, `ops/` là tầng điều phối: gateway, dispatcher, scheduler,
poller đều ở đây. §36 của kế hoạch đã xoá vai đó.

## Mọi thứ đã đi đâu

| Cũ | Nay | Vì sao |
|---|---|---|
| `ops/gateway.py` | `gateway/telegram/session.py` | §36 — cửa vào thuộc `gateway/` |
| `ops/poller.py` | `gateway/telegram/poller.py` | |
| `ops/cau.py` | `gateway/telegram/cau.py` | |
| `ops/telegram.py` | `gateway/telegram/telegram.py` | |
| `ops/media.py`, `ops/stt.py` | `gateway/telegram/` | |
| `ops/dispatch.py` | `gateway/cli/dispatch.py` | luật đã sang `core/policy` + `core/execution`; còn lại là cổng dòng lệnh |
| `ops/approvals.py` | `core/policy/approvals.py` | §36 — approval là một phần của Policy |
| `ops/scheduler.py` | `core/events/scheduler.py` + `gateway/cli/scheduler.py` | động cơ ở Core, dây dẫn ở gateway |
| `ops/nao.py` | `brains/fallback.py` | bộ não thì thuộc `brains/` |
| `ops/travis.py` | `gateway/cli/travis.py` | |
| `ops/evals/` | `tests/evals/` | ca thử thì thuộc `tests/` |
| `lib/skillRun.py` | `core/execution/brainRunner.py` | §36 — cách chạy một bộ não là việc của execution |

Đổi tên `gateway.py` → `session.py` là **bắt buộc**, không phải thẩm mỹ: có
một GÓI tên `gateway/` và một MODULE tên `gateway.py` cùng lúc thì Python thấy
thư mục trước, coi nó là namespace package, và `import gateway` trả về một gói
**rỗng**. Không có lỗi lúc nạp — nó chỉ vỡ ở chỗ dùng đầu tiên, bằng
`AttributeError: module 'gateway' has no attribute 'run_ceo'`.

---

## Còn lại gì ở đây

Công cụ cho **người phát triển**, không nằm trên đường chạy của hệ:

| Công cụ | Làm gì |
|---|---|
| `codemap.py` | Bản đồ mã + soát luật kiến trúc (`--check`) |
| `namingAudit.py` | Từ điển tên, soát §7 |
| `snapshot.py` | Chụp dữ liệu Notion trước khi thử phá (W7) |
| `setup-notion.py`, `setup-bot.sh` | Dựng lần đầu |
| `dung_giaotrinh.py` | Dựng giáo trình ngoại ngữ |
| `*.service`, `*.timer` | Unit systemd — nguồn, cài vào `~/.config/systemd/user/` |

**Không có gì ở đây được nằm trên đường chạy của một lời gọi.** Một lời gọi đi
từ `gateway/` → `core/` → `companies/`, và không đi qua `ops/` ở bất cứ chặng
nào. Thêm thứ gì vào đây mà hệ CẦN lúc chạy là dựng lại đúng tầng vừa xoá.
