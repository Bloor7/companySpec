# CONSTITUTION_REVIEW.md — luật nào giữ, luật nào phá

> Admin, 2026-09-19: *"Đừng để hiến pháp được sinh ra từ kiến thức hạn hẹp của
> tớ mà làm yếu đi sức mạnh của dự án. Tớ chấp nhận rủi ro để thay đổi."*

File này là câu trả lời. Nó soát **từng** luật lớn trong
[PRINCIPLES.md](../PRINCIPLES.md) và [../CLAUDE.md](../CLAUDE.md), rồi nói rõ:
giữ, sửa, hay bỏ — kèm lý do.

Mục đích là để admin **soát được tớ phá cái gì**, chứ không phải tin lời tớ.

---

## Tiêu chí phân loại

Một luật rơi vào đúng một trong hai loại:

### Loại E — luật từ **bằng chứng**

Sinh ra sau một sự cố thật đã đo được. Mỗi luật loại này là hoá đơn của một
lần hỏng: báo cáo in "thu 0đ" nhiều tuần, cửa vào sập vì `TimeoutExpired`,
ví sai 110.000đ, hệ chết 61 giờ không một dòng lỗi.

> **Phá luật loại E là mua lại một lần hỏng đã trả tiền rồi.** Không phá.
> Được phép **tổng quát hoá** cho mạnh hơn, không được phép nới lỏng.

### Loại G — luật từ **phỏng đoán cấu trúc**

Sinh ra trên bàn giấy, lúc chưa biết hệ sẽ lớn tới đâu. Chúng đúng với một hệ
có một bộ não và vài company. Chúng **sai** với một hệ có nhiều employee,
mission dài hạn và một cái Lab.

> Đây là chỗ phá. Và phá thì phải nói rõ thay bằng gì.

---

## Bảng phán quyết

| Luật | Loại | Phán quyết |
|---|---|---|
| Bảng bẫy trong `CLAUDE.md` (toàn bộ) | **E** | **GIỮ NGUYÊN** — đây là tài sản quý nhất của dự án |
| C2.4 — company chỉ nhận secret đã khai | **E** | **GIỮ**, tổng quát thành `secretBroker` |
| G4 — approval khoá vào `payloadHash` | **E** | **GIỮ** |
| G3 — `riskTier` lấy từ manifest, không từ model | **E** | **GIỮ**, mở rộng sang `PolicyDecision` |
| O8 — cửa vào không được phép sập | **E** | **GIỮ** |
| O10 — không nuốt lỗi thành giá trị hợp lệ | **E** | **GIỮ** |
| L8 — khai `paidApi`, có cầu dao tiền thật | **E** | **GIỮ** |
| L4 — chống lặp vô hạn | **E** | **GIỮ** |
| S3 — cron chỉ được đọc | **E** | **GIỮ** |
| C1 — envelope vào stdin, result ra stdout | **E** | **GIỮ** |
| §11 luật 11 — repo không công khai | **E** | **GIỮ** |
| §7 — tiếng Anh camelCase mọi nơi | **E** | **GIỮ và THI HÀNH** (đang bị phá 209 lần) |
| **CEO là một khối duy nhất** | **G** | **PHÁ** → tầng Employee |
| **`ops/` là tầng điều phối** | **G** | **PHÁ** → `core/` + `gateway/` |
| **Chỉ CEO được ghép việc** | **G** | **PHÁ** → Core/Mission ghép bằng code |
| **CEO không có tool Read/Write/Web** | **G** | **PHÁ** → chính sách theo từng Employee |
| **`riskTier` chỉ có 3 bậc** | **G** | **PHÁ** → Policy 5 chiều |
| **"Xong" = company trả `status: ok`** | **G** | **PHÁ** → `Verification` |
| **Trí nhớ = `profileCompany` + session** | **G** | **PHÁ** → `Memory` phân tầng |
| **Hệ chỉ chạy khi admin gõ hoặc cron tới giờ** | **G** | **PHÁ** → `Event bus` |
| P3 — company không gọi company | **G/E** | **GIỮ hình, ĐỔI chủ** (xem dưới) |
| W3 — thêm company không được sửa CEO | **G** | **NÂNG CẤP** (xem dưới) |

---

## Sáu vụ phá lớn

### 1. CEO thôi làm trời

**Hôm nay.** Đúng một phiên Claude đọc `ceo/SYSTEM.md` làm tất: hiểu ý admin,
chọn company, ghép nhiều bước, nói lại kết quả. Mọi thứ đổ lên một bộ não.

**Vì sao yếu.**

- Một bộ não hỏng là **cả hệ câm**. Đã xảy ra thật: hết phiên `claude /login`
  thì không ghi nổi một khoản chi, dù mọi company vẫn chạy tốt.
- Không có chuyên môn. Cùng một prompt phải vừa giỏi kiến trúc, vừa giỏi sửa
  code, vừa giỏi bảo mật. Kết quả là giỏi tầm tầm mọi thứ.
- Không có trí nhớ riêng theo vai. Bài học của lần sửa SEO không ở lại với ai.
- `SYSTEM.md` chỉ có thể **dài thêm**. Mỗi luật mới là thêm chữ vào cùng một
  prompt, và prompt dài thì model bỏ qua chính giữa.

**Thay bằng.** `Employee`: mỗi người có `identity + role + personality +
expertise + memory + permissions + brainPreference`. CEO tụt xuống thành **một
employee điều phối**, không phải tầng trời.

**Rủi ro nhận lấy.** Nhiều employee = nhiều lời gọi model = tốn hơn. Giảm bằng
cách: việc đã biết trước cách làm thì **không** giao employee, viết kịch bản
cứng — đúng bài học "agent 4–9 phút ba lần đều trượt, kịch bản cứng 16 giây".

---

### 2. `ops/` thôi làm tầng điều phối

**Hôm nay.** `ops/` vừa là cửa vào (poller, cầu), vừa là luật (dispatch), vừa
là lịch (scheduler), vừa là bộ não dự phòng (nao). `gateway.py` một mình hơn
hai nghìn dòng.

**Vì sao yếu.** Luật trộn với vận chuyển thì **không unit-test được luật**.
Muốn biết "sửa production có bị chặn không" thì phải dựng cả một phiên Telegram.

**Thay bằng.**

```text
core/     ← luật thuần, không I/O, test được không cần mạng
gateway/  ← vận chuyển: telegram, cli
```

`ops/` co thành lớp vỏ mỏng. Không xoá — nó vẫn là chỗ mọi thứ đang chạy, và
bị bỏ lại từng mảnh một, có adapter, có test.

---

### 3. Quyền ghép việc chuyển từ model sang code

**P3 giữ hình, đổi chủ.**

Luật cũ: *company không gọi company* — nên chỉ CEO ghép được nhiều bước. Ý
định đúng (không có cạnh ẩn giữa các company), nhưng hệ quả là **một model trở
thành kẻ ghép việc duy nhất**, và nó ghép bằng cách đoán.

Luật mới: cạnh giữa company vẫn **cấm**. Nhưng kẻ ghép là `core/mission` và
`core/task` — **code**, không phải model. Model **đề xuất** kế hoạch; code
duyệt kế hoạch đó rồi mới chạy.

Đây là P3 mạnh hơn, không phải P3 yếu đi. Trước: một model tuỳ ý ghép. Sau:
một planner kiểm được, mỗi bước vẫn qua đúng cánh cửa Policy.

---

### 4. Cấm tool → chính sách theo từng Employee

**Hôm nay.** "CEO không có tool `Read`, `WebFetch`, `WebSearch`, `Write`" —
vì mở ra là nó đọc được `ops/.env`.

**Vì sao yếu.** Đây là cấm **bằng búa**. Hệ quả đã thấy: admin nhắn "làm thử
cái todolist", CEO đáp "em không tự viết file HTML được" trong khi `xuongCompany`
làm được đúng việc ấy, vừa dựng xong cùng ngày. Cấm quá rộng thì cái đúng cũng
chết theo.

**Thay bằng.** Sandbox theo từng Employee (§27 kế hoạch):

```yaml
forge:
  filesystem: [/workspace/panharmon]
  network:    [github.com, npmjs.com]
  secrets:    [PANHARMON_DEV]
  production: deny

sage:
  filesystem: [/lab/research]
  network:    [web]
  secrets:    []
  production: deny
```

Mục tiêu bảo vệ không đổi (không ai đọc được `ops/.env`), nhưng đạt bằng
**phạm vi** thay vì bằng **cấm tiệt**. Giai đoạn đầu là cô lập logic; sau mới
container.

---

### 5. `status: ok` thôi là "xong"

**Hôm nay.** Company trả `status: ok` + output đúng schema là Task completed.

**Vì sao yếu.** Đúng schema không có nghĩa đúng việc. Đã xảy ra: hộp dựng xong
web todolist hoàn chỉnh rồi đặt việc về `choXem` và im lặng; cùng tối admin
hỏi "cái web làm sao xem" và CEO đáp "em không viết file HTML được". Không bộ
phận nào hỏng — chỉ là **không ai chứng minh gì cả**.

**Thay bằng.** `Verification` là một tầng riêng. Task chỉ `completed` khi có
bằng chứng hợp với loại việc: sửa code thì typecheck + lint + build; sửa UI
thì thêm browser + visual; ghi sổ thì đọc lại đúng cái vừa ghi.

**Đây là vụ phá đắt nhất** (mọi việc chậm hơn) và **đáng nhất**: nó xoá cả một
họ lỗi — "hệ báo xong trong khi chưa xong".

---

### 6. Hệ thôi chờ bị gõ

**Hôm nay.** Hai cửa vào: admin gõ Telegram, hoặc cron tới giờ chạy một việc
cố định.

**Vì sao yếu.** Hệ **không bao giờ tự phát hiện vấn đề**. 61 giờ chết không
một dòng lỗi là ví dụ: mọi thứ báo xanh, không ai hỏi "sao hai ngày rồi không
có tin nào".

**Thay bằng.** `Event bus`. Event **đề xuất** Task, không **cấp quyền** cho
Task — Task do event đẻ ra vẫn qua đúng Policy đó.

---

## Một luật được NÂNG CẤP, không phá

**W3 — thêm company không được sửa CEO.**

Giữ, và nới rộng thành:

> **W3′ — thêm bất cứ thứ gì cũng không được sửa Core.**
> Thêm company, employee, brain, project, mission, verification check đều phải
> là **thêm dữ liệu**, không phải sửa code Core. Phải sửa Core nghĩa là hợp
> đồng đang rò.

Đây là cách duy nhất Travis lớn được mà không nát.

---

## Ba luật MỚI, sinh ra từ chính việc đọc lại hiến pháp

### N1 — Hàng rào phải soát được bằng code

Luật chỉ sống trong prompt là luật model phá lúc nào cũng được mà không ai
biết. Dự án đã học điều này hai lần: `pattern:` khai trong manifest mà
`validate()` chưa từng đọc, và hội đồng bịa số cho tới khi có `_soKhongNguon`.

> Mọi luật trong `docs/` phải có **một phép soát chạy được**, hoặc được đánh
> dấu rõ là **chưa có hàng rào**. Hàng rào giả hại hơn không có hàng rào.

### N2 — Giá trị rỗng phải nói rõ nghĩa

`whitelistScope: []` nghĩa là **ĐÓNG**, và điều đó đã tốn của admin hàng tháng
bấm nút. Từ đây mọi trường trong manifest phải khai rõ rỗng nghĩa là gì, và
`codemap --check` phải hỏi lại chính bộ đọc thay vì tin mắt người.

### N3 — Ai là người đầu tiên biết việc đã xong

Sau khi dựng bất cứ dây chuyền nào, phải trả lời được: *"ai là người đầu tiên
biết việc đã xong, và họ biết bằng cách nào."* Trả lời được bằng **tên một
hàm** thì mới xong. Trạng thái nằm trong sổ **không phải** là thông báo.

---

## Cái tớ KHÔNG dám phá, và nói thẳng vì sao

**Bảng bẫy trong `CLAUDE.md`.** Đây là thứ giá trị nhất trong repo — quý hơn
code. Mỗi dòng là một sự cố đã lần ra, và phần lớn là loại lỗi **không gây
crash, không sai schema, không ai kêu** — chỉ lặng lẽ cho ra số sai theo hướng
trấn an.

Không có bảng đó, Travis sẽ dựng lại đúng những cái bẫy ấy bằng tên tiếng Anh
mới. Nên nó **đi theo nguyên vẹn** sang kiến trúc mới, và mọi hàng rào trong
`core/` phải chỉ được về đúng dòng nó đang canh.
