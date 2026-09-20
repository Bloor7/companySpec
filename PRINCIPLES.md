# PRINCIPLES.md — Nguyên tắc nền của dự án `companySpec`

> **Trạng thái: đang chạy thật hằng ngày.** Đường truyền Telegram → CEO →
> dispatcher → company đã thông; guardrail đã được thử và chặn đúng. Số company
> và năng lực hiện tại xem [README.md](README.md) — đừng chép con số vào đây,
> chép là để nó cũ đi. (Dòng này ghi "Lát 2 đang chạy" từ 02/08 tới 14/08 trong
> khi hệ đã đi xa hơn nhiều — sửa vì lý do đó.)
>
> File này là hiến pháp của dự án. Mọi thiết kế, mọi PR, mọi prompt agent sau này
> phải trích dẫn được nguyên tắc mà nó tuân theo. Khi thực tế mâu thuẫn với file
> này, sửa file này trước — đừng lặng lẽ làm khác.

Ngày khởi tạo: 2026-08-02
Người dùng duy nhất: admin (1 người, cá nhân, không multi-tenant)

---

## 0. Dự án này là gì

Một trợ lý cá nhân dùng riêng cho một người. Admin nhắn qua Telegram, một "CEO"
chạy bằng Claude Code xử lý, giao việc cho các "company" chuyên môn hoá, rồi báo
cáo ngược lại.

Điều làm dự án này khác một con chatbot gắn tool: **cấu trúc công ty**. Không có
một agent to đùng ôm hết mọi thứ. Có một người ra quyết định, nhiều đơn vị làm
việc có ranh giới rõ ràng, và một bộ phận theo dõi ghi lại tất cả.

### Mục tiêu kinh tế: dùng hết gói Pro, không phải tiết kiệm tiền

Admin đã trả tiền gói Pro hằng tháng. Hạn mức không dùng thì **mất**, không cộng
dồn. Nên bài toán không phải "tiêu ít nhất" mà là "dùng hết mà không đụng trần
vào lúc cần nhất".

Điều này đổi nghĩa vài thứ trong file này:

- **"Ngân sách" (budget) = hạn mức, không phải tiền.** `total_cost_usd` chỉ là
  đơn vị đo tiện tay, không phải hoá đơn. Không có đồng nào bị trừ.
- **Lãng phí thật là chi phí cố định, không phải chi phí công việc.** 23k token
  nạp lại vì mở phiên nguội không đổi lấy giá trị gì. 23k token cho một việc khó
  thì hoàn toàn xứng đáng. Tối ưu vế đầu, đừng cắt vế sau.
- **Không có công cụ nào ngoài gói Pro.** Không API key trả tiền, không LLM local
  (máy không chạy nổi). Mọi trí tuệ trong hệ đều đi qua CLI của gói Pro; mọi thứ
  còn lại phải là code cứng. Đây vừa là ràng buộc vừa là kỷ luật thiết kế — nó ép
  P1 (code cứng giữ khung, LLM giữ nội dung) thành hiện thực thay vì khẩu hiệu.

### Phạm vi — hệ này phục vụ cái gì, và dứt khoát không phục vụ cái gì

**Có:** công việc admin đang làm, và quản lý cá nhân. Company giúp làm những việc
đó **tự động hoặc bán tự động**.

**Không:** sản phẩm của admin **không bao giờ** kết nối vào đây. Đây là trợ lý
riêng, không phải hạ tầng sản xuất. Ranh giới này là cứng — nó giữ cho một lỗi
trong hệ này không bao giờ chạm được vào thứ đang phục vụ người khác.

### File này sẽ thay đổi, và đó là chuyện bình thường

Đây là dự án mới. Nguyên tắc trong đây viết dựa trên hiểu biết của ngày đầu tiên;
khi hệ phình ra và va phải vấn đề thật, một số nguyên tắc sẽ sai. Quy tắc xử lý:

- **E1.** Sai thì sửa file này **trước**, rồi mới sửa code. Không lặng lẽ làm khác.
- **E2.** Mỗi lần sửa ghi vào §13 kèm **lý do**, không chỉ ghi "đã đổi". Sáu tháng
  sau lý do mới là thứ có giá trị.
- **E3.** Nguyên tắc bị phá nhiều lần mà lần nào cũng có lý → nó là nguyên tắc sai,
  bỏ đi. Đừng giữ luật mà thực tế liên tục phải lách.
- **E4.** Ngược lại: ba nguyên tắc gốc (P1/P2/P3) chỉ đổi khi có bằng chứng đo được,
  không đổi vì thấy bất tiện.

### Vì sao chọn hình thái "công ty" chứ không phải "một agent nhiều tool"

- Một agent nhiều tool sẽ phình prompt tuyến tính theo số kỹ năng. Chia thành
  company thì CEO chỉ cần biết *danh mục năng lực*, không cần biết chi tiết.
- Ranh giới công ty = ranh giới lỗi. Một company hỏng không kéo sập cả hệ.
- Ranh giới công ty = ranh giới dữ liệu. Mỗi company có sqlite riêng, nên
  "company SEO đọc nhầm dữ liệu tài chính" là chuyện không thể xảy ra về mặt vật lý,
  không phải chuyện được ngăn bằng lời dặn trong prompt.
- Ranh giới công ty = đơn vị báo cáo. backOffice có thể trả lời "tháng này
  company nào tốn tiền nhất, hỏng nhiều nhất" mà không cần phân tích log tự do.

---

## 1. Ba nguyên tắc gốc

Mọi thứ còn lại trong file này đều suy ra từ ba điều này. Nếu phải quên hết, nhớ ba điều này.

### P1 — Code cứng giữ khung, LLM giữ nội dung

Code cứng quyết định **được phép làm gì**: quyền, hạn mức, timeout, retry, thứ tự,
điều kiện dừng. Deterministic, đọc được bằng mắt, chạy lại bao nhiêu lần cũng ra
một kết quả.

LLM quyết định **làm gì**: hiểu ý admin, chọn company, soạn nội dung, tổng hợp báo cáo.

> **Nguyên tắc này từng viết là "n8n giữ khung".** Đổi ngày 2026-08-03 sau khi
> n8n bị gỡ khỏi mọi đường chạy: Telegram phải dùng long polling vì máy không có
> IP công khai, lịch định kỳ dùng systemd timer, dispatcher là một tiến trình
> Python. n8n chạy hai ngày mà không xử lý một tin nhắn nào.
>
> Tinh thần không đổi — chỉ là *cái gì* giữ khung thì không quan trọng bằng
> *nó phải là code cứng*. Gọi tên một công cụ trong nguyên tắc gốc là sai lầm
> ngay từ đầu: công cụ thay được, nguyên lý thì không (E3).

Ranh giới này không được nhoè. Cụ thể:
- Không bao giờ để LLM sinh ra thứ quyết định quyền của chính nó (không tự cấp
  quyền, không tự nâng hạn mức, không tự tắt guardrail, không tự đặt lại budget).
- Không bao giờ để LLM là thứ duy nhất đứng giữa một hành động nguy hiểm và việc
  nó xảy ra.

### P2 — Prompt không phải là biên giới an toàn

Câu "đừng làm X" trong system prompt là *gợi ý*, không phải *hàng rào*. Model có
thể hiểu sai, bị input của người khác lái đi (prompt injection từ nội dung web,
email, file), hoặc đơn giản là quên khi context dài.

Hàng rào thật phải nằm ở chỗ model không với tới được:
- Deny rules trong `settings.json` của Claude Code (model không sửa được file này
  vì nó nằm ngoài thư mục làm việc và bị chặn ghi).
- `PreToolUse` hook — chạy bằng code, veto được lời gọi tool trước khi nó xảy ra.
- Kiểm tra bằng code trong `gateway/cli/dispatch.py` — model gọi qua nó, không thay nó được.
- Credential không nằm trong tầm với của model: dispatcher chỉ truyền xuống
  company đúng những secret nó khai trong manifest (C2.4), lấy từ `ops/.env`
  chmod 600 mà model không đọc được.

**Hệ quả thực hành:** mỗi guardrail phải trả lời được câu "nếu model *cố tình*
lách thì cái gì chặn nó?". Nếu câu trả lời là "prompt bảo nó đừng", đó chưa phải
guardrail.

### P3 — Hình sao, không phải lưới

```
        admin
          │
        (CEO)  ←── mọi mũi tên đều đi qua đây
       ╱  │  ╲
      A   B   C        ← company không nói chuyện trực tiếp với nhau
```

Company **không bao giờ** gọi thẳng company khác. Khi nhiệm vụ cần nhiều kỹ năng,
CEO gọi A, nhận kết quả, rồi gọi B với kết quả đó.

Vì sao khắt khe vậy: mạng lưới N node có thể có chu trình; hình sao thì không.
Đây là biện pháp chống vòng lặp vô hạn *bằng cấu trúc* — mạnh hơn mọi bộ đếm.
Nếu sau này thấy "cho A gọi B trực tiếp cho nhanh", câu trả lời mặc định là
**không**, và phải sửa file này trước khi làm khác.

---

## 2. Kiến trúc tầng

```
┌──────────────────────────────────────────────────────────────┐
│ adminGateway     Telegram bot. Cửa duy nhất vào và ra.       │
│                  Chặn mọi chatId lạ. Rate limit.             │
└───────────────────────────┬──────────────────────────────────┘
                            │ adminMessage
┌───────────────────────────▼──────────────────────────────────┐
│ ceoLayer         Claude Code CLI (headless), chạy trên host.  │
│                  Hiểu ý → lập kế hoạch → giao việc →          │
│                  tổng hợp → trả lời. Không tự tay làm việc    │
│                  chuyên môn.                                  │
└───────────────────────────┬──────────────────────────────────┘
                            │ taskEnvelope
┌───────────────────────────▼──────────────────────────────────┐
│ dispatcher       gateway/cli/dispatch.py + hook chặn mọi đường khác.  │
│ (code cứng)      Kiểm manifest, schema, riskTier, whitelist,  │
│                  ngân sách, loopGuard. Đây là nơi nói KHÔNG.  │
│                  CEO không đi vòng qua tầng này được (§12b).  │
└───────────────────────────┬──────────────────────────────────┘
                            │
      ┌──────────┬──────────┼──────────┬──────────┐
      ▼          ▼          ▼          ▼          ▼
   company    company    company    company    company     ← mỗi cái có
   (skill)    (code)     (agent)    (repo)   (connector)      sqlite riêng
      │          │          │          │          │
      └──────────┴──────────┼──────────┴──────────┘
                            │ companyResult + event
┌───────────────────────────▼──────────────────────────────────┐
│ backOffice       Nhận event từ mọi tầng. Ghi log tổng hợp,    │
│                  tính chi phí, phát hiện bất thường, soạn     │
│                  báo cáo. CHỈ ĐỌC với dữ liệu của company.    │
└───────────────────────────┬──────────────────────────────────┘
                            │ report
                            ▼
                     ceoLayer → adminGateway → admin
```

### Quy tắc tầng

- **T1.** Không tầng nào được nhảy cóc. Company không nhắn thẳng Telegram cho admin.
  backOffice không tự nhắn admin. Muốn nói gì với admin thì trả về cho CEO.
- **T2.** dispatcher là điểm nghẽn cố ý (chokepoint): mọi lời gọi company đi qua
  đúng một chỗ, nên chỉ cần audit một chỗ. Nó là một **khái niệm**, có hai hiện
  thực — hook `PreToolUse` chặn mọi đường khác, và `gateway/cli/dispatch.py` gác cổng
  thật sự. Xem §12b.
- **T3.** backOffice chỉ đọc dữ liệu nghiệp vụ của company; nó ghi vào store của
  chính nó. Không bao giờ có chuyện backOffice sửa dữ liệu company.
- **T4.** Một `adminMessage` sinh ra đúng một `trace`. Mọi thứ xảy ra sau đó đều
  mang cùng `traceId`. Không có việc gì trong hệ thống không thuộc về một trace nào.

---

## 3. Company — bản hợp đồng chung

Đây là phần cốt lõi của dự án và là lý do repo tên `companySpec`.

### Nguyên tắc C1 — Ruột đa dạng, vỏ đồng nhất

Một company có thể được hiện thực bằng bất cứ thứ gì:

| runtime | nghĩa là | ví dụ |
|---|---|---|
| `skill` | một file SKILL.md + reference | `seoCompany` từ `claude-seo` |
| `code` | service/script có entrypoint rõ | company tính toán tài chính |
| `agent` | agent definition, CEO spawn ra | company viết nội dung dài |
| `workflow` | script thuần, gọi từ lịch định kỳ | company đồng bộ dữ liệu |
| `repo` | một repo độc lập được clone vào | công cụ bên thứ ba |
| `connector` | connector sẵn có (Notion, Calendar…) | bọc lại thành company |

**CEO không được biết sự khác nhau đó.** Với CEO, mọi company đều là: một cái tên,
một danh sách năng lực, và một cách gọi duy nhất. Ngày mai đổi `seoCompany` từ
skill sang service viết bằng Go, CEO không cần biết và không có gì phải sửa ở
tầng trên.

Cái làm cho điều đó thành sự thật là file **`companySpec.yaml`** — mỗi company bắt
buộc có đúng một file này, và dispatcher từ chối gọi bất cứ thứ gì không có nó.

### Nguyên tắc C2 — Company là hộp đen có mô tả tự thân

```yaml
# companies/seoCompany/companySpec.yaml   (phác thảo, chưa chốt field)
companyId: seoCompany              # camelCase, hậu tố "Company", là khoá duy nhất
displayName: "Phòng SEO"
version: 1.0.0
runtime: skill                     # skill | code | agent | workflow | repo | connector
entrypoint: ./SKILL.md

capabilities:
  - name: auditSite                # camelCase động từ + tân ngữ
    description: "Kiểm tra tổng thể SEO một website"
    riskTier: read                 # read | write | irreversible
    inputSchema: ./schemas/auditSite.input.json
    outputSchema: ./schemas/auditSite.output.json
    maxDurationSec: 300
    costHintUsd: 0.20

dataStore: ./store.sqlite
secrets: [DATAFORSEO_KEY]          # chỉ khai báo TÊN, không bao giờ chứa giá trị
canBeCalledBy: [ceo]               # luôn chỉ là [ceo] — xem P3
canCall: []                        # luôn rỗng — xem P3
healthCheck: ./scripts/health.sh
owner: admin
```

Quy tắc:
- **C2.1** Không có `companySpec.yaml` → không tồn tại với hệ thống. dispatcher
  từ chối, không có ngoại lệ, không có "gọi tạm".
- **C2.2** Năng lực không khai báo trong `capabilities` → không gọi được. CEO
  không được phép "sáng tạo" ra năng lực mới lúc chạy.
- **C2.3** Mọi input/output đều có JSON Schema và **được validate ở cả hai chiều**.
  Validate đầu vào để company không nhận rác từ LLM. Validate đầu ra để CEO không
  nhận rác từ company. Sai schema là lỗi, không phải chuyện "cố hiểu xem nó muốn gì".
  Schema **viết thẳng trong `companySpec.yaml`** khi ngắn, tách ra file riêng khi dài —
  cái quan trọng là có schema, không phải nó nằm ở đâu.
- **C2.5 — Từ vựng phải đóng ở chỗ cần nhất quán.** Trường nào mà giá trị cần
  gom nhóm được về sau (danh mục, trạng thái, mức ưu tiên) thì khai `enum`, đừng
  để chuỗi tự do. LLM luôn sinh ra biến thể: "Cà phê", "Trà sữa", "cafe", "Ăn
  uống" — mỗi cái là một nhóm mới, và cộng tổng thành vô nghĩa.
  *Đo được:* lần chạy thật đầu tiên của `expenseCompany`, CEO tự đặt danh mục
  "Cà phê". Hậu quả dây chuyền: luật whitelist khoá vào danh mục dùng đúng một
  lần, và `listExpenses` tìm "ăn uống" không thấy khoản vừa ghi.
  *Mở rộng từ vựng là hành động có chủ ý:* sửa `companySpec.yaml` **và** sửa
  Notion. Không phải tai nạn của model lúc chạy.
- **C2.6 — Danh mục năng lực phải kèm giá trị hợp lệ.** `dispatch.py list` trả
  luôn `enum` cho CEO. Rẻ hơn để nó đoán sai rồi bị chặn rồi gọi lại — mỗi vòng
  thừa là một lượt đi-về với model.
- **C2.4** `secrets` chỉ khai báo tên biến. Giá trị nằm ở `ops/.env` (chmod 600,
  bị `.gitignore` chặn). Dispatcher chỉ truyền xuống company đúng những biến
  nó khai — company không nhận cả `os.environ`.

### Nguyên tắc C3 — Mỗi company một sqlite, không dùng chung

Đường dẫn cố định: `companies/<companyId>/store.sqlite`

Bắt buộc mọi store phải có hai bảng chuẩn (tên cột camelCase):

```sql
-- lịch sử công việc: company này đã được giao gì, kết quả ra sao
CREATE TABLE taskLog (
  taskId TEXT PRIMARY KEY,
  traceId TEXT NOT NULL,
  capability TEXT NOT NULL,
  inputHash TEXT NOT NULL,
  status TEXT NOT NULL,          -- ok | failed | rejected | budgetExceeded | needsApproval
  summary TEXT,
  startedAt TEXT NOT NULL,
  finishedAt TEXT,
  durationMs INTEGER,
  costUsd REAL
);

-- nhật ký sự kiện: append-only, không bao giờ UPDATE hay DELETE
CREATE TABLE eventLog (
  eventId INTEGER PRIMARY KEY AUTOINCREMENT,
  taskId TEXT,
  traceId TEXT NOT NULL,
  eventType TEXT NOT NULL,
  payloadJson TEXT,
  createdAt TEXT NOT NULL
);
```

Ngoài hai bảng đó, company tự do định nghĩa bảng nghiệp vụ của mình.

### Nguyên tắc C5 — Hai company không được cùng trả lời một câu

Nếu hai company đều *có vẻ* làm được một việc, CEO sẽ phải đoán, và nó sẽ đoán
sai. Mô tả năng lực phải loại trừ lẫn nhau.

*Đo được:* `notesCompany.addNote` mô tả là "lưu một ghi chú" — đủ chung để CEO
đẩy câu "ghi nhật ký" vào đó với thẻ `["nhật ký"]`, thay vì gọi `journalCompany`.
Hậu quả: dữ liệu vào nhầm kho, và sinh ra luật whitelist rác.

- **C5.1** Company chỉ để kiểm thử thì khai `internal: true`. Dispatcher **ẩn nó
  khỏi danh mục** và **từ chối mọi lời gọi** trừ khi có cờ `--allow-internal` —
  cờ đó chỉ có ở terminal, CEO không bao giờ có.
- **C5.2** Trước khi thêm company mới, đọc lại mô tả của những company đã có.
  Chồng lấn thì phải sửa mô tả hoặc gộp/bỏ một cái, **trước khi** chạy thật.
- **C5.3** Giữ một company "đa dụng" là cách chắc chắn nhất để phá C4. Việc gì
  cũng nhét vừa nó, nên việc gì cũng có thể đi nhầm vào đó.

### Nguyên tắc C4 — Ranh giới company là CÔNG VIỆC, không phải công cụ

`expenseCompany` và `journalCompany` đều cất dữ liệu vào Notion, nhưng chúng là
hai company khác nhau. Notion chỉ là **nơi cất**, không phải nhiệm vụ.

*Vì sao:* gộp theo công cụ thì backOffice chỉ báo được "notionCompany chạy 200
lần" — vô nghĩa. Tách theo công việc thì báo được "chi tiêu 40 lần, nhật ký 12
lần", và mỗi cái có mức rủi ro, schema, whitelist riêng.

- **C4.1** Company được **dùng chung thư viện code** (`lib/notionClient.py`),
  nhưng **không bao giờ dùng chung kho dữ liệu** (C3.2). Chung code là tiết kiệm;
  chung dữ liệu là xoá ranh giới.
- **C4.2** Thư viện dùng chung không được chứa quyết định nghiệp vụ. Nó chỉ biết
  "gọi Notion thế nào", không biết "chi tiêu là gì".

- **C3.4 — Mở SQLite qua `lib/db.py`, không bao giờ gọi `sqlite3.connect` thẳng.**
  Hệ có nhiều tiến trình cùng chạy: poller, gateway, dispatcher, scheduler, và
  mỗi company là một tiến trình riêng. Chế độ mặc định của SQLite (`journal=delete`)
  khoá **cả file** khi ghi, kể cả với tiến trình chỉ muốn đọc.
  Bắt buộc `journal_mode=WAL` + `busy_timeout=15000`.
  *Đo được:* admin nhắn ba tin liên tiếp sau khi khởi động máy, trùng lúc
  scheduler chạy → `database is locked`. Bot trả về một câu vô nghĩa với người
  dùng cuối. Có 11 chỗ mở kết nối, mỗi chỗ một kiểu.
  *Luật chung:* thứ gì cả hệ đều dùng và dễ làm sai thì phải có **đúng một chỗ
  làm đúng**, mọi nơi khác gọi vào đó (giống `gateway/telegram/telegram.py` với đường ra).
- **C3.5 — Mở kết nối ở chế độ tự commit.** Mặc định của Python là ngầm mở giao
  dịch trước mỗi `INSERT`/`UPDATE`/`DELETE` và bắt gọi `commit()`. Quên **một** chỗ
  là kết nối giữ khoá ghi vô thời hạn, và mọi tiến trình khác đứng chờ rồi chết.
  *Đo được:* `sweep_orphans()` chạy `UPDATE` nhưng chỉ commit khi dọn được ít nhất
  một dòng. Không có dòng nào kẹt → không commit → **dispatcher tự khoá chính nó**,
  rồi `create_request` ở kết nối thứ hai chết vì `database is locked`.
  Đây không phải tranh chấp giữa hai người dùng; là một tiến trình tự chặn mình.
  WAL không cứu được, vì WAL chỉ tách người đọc khỏi người ghi.
  *Luật rút ra:* **đừng sửa từng chỗ quên commit — hãy làm cho việc quên commit
  không gây hậu quả.** Sửa từng chỗ thì lần sau vẫn quên.
- **C3.1** `eventLog` là append-only. Không sửa lịch sử. Sai thì ghi sự kiện đính chính.
- **C3.2** Không company nào mở file sqlite của company khác. Muốn dữ liệu của nhau
  thì đi qua CEO (P3).
- **C3.3** Backup theo company, restore theo company. Một company hỏng dữ liệu
  không kéo theo cái khác.

---

## 4. Hai bản hợp đồng dữ liệu

Cả hệ thống chỉ có hai hình dạng message đi qua dispatcher. Ít hình dạng =
dễ validate = dễ debug.

### `taskEnvelope` — CEO giao việc xuống

```jsonc
{
  "taskId": "tsk_01J8XQ...",        // ULID, duy nhất toàn hệ
  "traceId": "trc_01J8XQ...",       // gốc từ adminMessage
  "parentTaskId": null,
  "companyId": "seoCompany",
  "capability": "auditSite",
  "input": { "url": "https://..." },
  "context": {
    "adminIntent": "câu tóm tắt ý admin, để company hiểu bối cảnh",
    "priorResults": []              // kết quả company trước, do CEO chọn lọc
  },
  "budget": {
    "depth": 1,
    "maxDepth": 2,
    "stepsUsed": 3,
    "maxSteps": 20,
    "deadlineAt": "2026-08-02T12:40:00Z",
    "costUsedUsd": 0.12,
    "maxCostUsd": 1.00
  },
  "policy": {
    "riskTier": "read",
    "approvalToken": null,
    "dryRun": false
  },
  "issuedBy": "ceo",
  "issuedAt": "2026-08-02T12:30:00Z"
}
```

### `companyResult` — company trả lên

```jsonc
{
  "taskId": "tsk_01J8XQ...",
  "traceId": "trc_01J8XQ...",
  "status": "ok",                   // ok | needsApproval | needsInput | failed
                                    // | budgetExceeded | rejected
  "output": { },                    // đúng outputSchema đã khai báo
  "summary": "≤500 ký tự, viết cho CEO đọc, không phải cho admin đọc",
  "artifacts": [                    // file lớn thì trả đường dẫn, KHÔNG nhét vào output
    { "path": "companies/seoCompany/out/audit-123.md", "kind": "report" }
  ],
  "sideEffects": [                  // mọi thứ đã thay đổi ngoài thế giới thực
    { "type": "notion.createPage", "target": "page_abc",
      "idempotencyKey": "...", "reversible": true }
  ],
  "usage": { "steps": 7, "durationMs": 42000, "costUsd": 0.18 },
  "error": null
}
```

Quy tắc:
- **D1.** Payload lớn không đi qua envelope. Ghi ra file, trả `artifacts`. Envelope
  luôn nhỏ và đọc được bằng mắt.
- **D2.** `summary` là thứ CEO đọc. `output` là thứ máy đọc. Đừng trộn.
- **D3.** `sideEffects` là bắt buộc khai báo. Company làm gì ra ngoài mà không khai
  báo trong đây là **vi phạm nghiêm trọng** — đó là cơ sở duy nhất để hoàn tác và
  để backOffice biết chuyện gì đã xảy ra.
- **D5 — Sửa thì phải ghi lại giá trị cũ.** Mọi thao tác ghi đè bản ghi đã có
  bắt buộc khai `sideEffects[].previousValue`. Thêm mới thì sai lầm chỉ là một
  dòng thừa; **ghi đè thì giá trị cũ biến mất vĩnh viễn** nếu không ai chép lại.
  `previousValue` là thứ duy nhất cho phép quay lại — cả admin lẫn backOffice
  đều đọc từ đó.
- **D7 — Việc xoá phải ĐỐI CHIẾU, không chỉ định danh.** Năng lực xoá nhận thêm
  vài trường mô tả bản ghi (số tiền, ngày) — **không phải để tìm kiếm mà để
  kiểm chứng**. Admin bấm duyệt dựa trên câu *"xoá 20.000đ ngày 03/08"*; nếu id
  lại trỏ tới bản ghi khác thì company từ chối.
  Không có bước này thì chuỗi "CEO tìm → CEO xoá" có một mắt xích không ai kiểm:
  admin duyệt cái mình đọc được, hệ xoá cái id trỏ tới, và hai thứ đó có thể
  khác nhau vì CEO nhầm hoặc vì dữ liệu đổi giữa chừng.
- **D10 — `sideEffects.target` phải là ĐỊNH DANH THẬT, không phải nhãn dễ đọc.**
  Ghi `video/001` thì người đọc log hiểu ngay, nhưng không khôi phục được:
  API `search` của Notion không trả về trang trong thùng rác, nên **mất id là
  mất đường về** dù bản ghi vẫn nằm đó 30 ngày.
  *Đã trả giá thật:* video 001 bị ẩn lúc kiểm chứng; không lấy lại được bản gốc,
  phải dựng bản mới và **mất trường `KPI chính`** vì nó không có trong
  `previousValue`. Muốn dễ đọc thì thêm nhãn vào `previousValue`, đừng thay id.
- **W7 — Phép thử chạm tới thêm/sửa/xoá phải TỰ khôi phục được.**
  Không dựa vào thùng rác, undo hay "nền tảng giữ 30 ngày" của bên thứ ba — đó
  là **hy vọng, không phải kế hoạch phục hồi**. Trước khi thử, tự chụp đủ trạng
  thái; sau khi thử, tự dựng lại và **kiểm chứng là đã về đúng như cũ**.
  Ba việc bắt buộc, theo thứ tự:
  1. `python3 ops/snapshot.py save <sổ>` — chụp ĐẦY ĐỦ mọi property, không chọn lọc
  2. Chạy phép thử
  3. `python3 ops/snapshot.py diff <sổ>` → phải không lệch gì. Lệch thì `restore --apply`
  *Vì sao chụp đầy đủ:* chọn lọc chính là chỗ mất mát. `previousValue` lần trước
  chỉ giữ 4 trường, nên dựng lại xong vẫn thiếu `KPI chính`. Không biết trước
  cái gì sẽ cần thì giữ hết.
  *Đã trả giá thật:* admin **không khôi phục được** video 001. Trường `KPI chính`
  mất vĩnh viễn vì tôi tin vào thùng rác của Notion thay vì tự lo lấy đường về.
- **W6 — KHÔNG kiểm chứng năng lực phá huỷ trên dữ liệu thật.** `--dry-run` có
  sẵn cho đúng việc này (W2), và nếu phải chạy thật thì tạo một bản ghi rác
  trước, thao tác trên nó, rồi xoá.
  *Đã trả giá thật:* tớ chạy `archiveTask` thẳng lên video 001 trong kế hoạch
  90 video của admin. "Khôi phục được trong 30 ngày" chỉ đúng khi biết đường về —
  và lúc đó thì không.
- **D9 — `previousValue` phải đủ để dựng lại, không chỉ để nhận ra.** Vừa dùng
  thật: video 001 bị ẩn lúc kiểm chứng, và `previousValue` (`001|GD1|GIAI MA|Mơ
  thấy bị rượt đuổi`) chứa đủ mọi trường để tạo lại y nguyên — không cần mò
  thùng rác Notion.
  Nếu chỉ ghi id thì lúc cần khôi phục sẽ biết *mất cái gì đó* mà không biết
  *mất cái gì*.
- **D8 — Xoá thì không bao giờ whitelist.** Khai năng lực xoá **không có**
  `whitelistScope`, để G12 tự chặn: lần nào cũng phải hỏi. *"Luôn cho phép xoá
  chi tiêu ăn uống"* là câu không ai thật sự muốn nói.
- **D6 — Không tìm thấy thì báo, đừng tạo mới.** Company nhận lệnh sửa một bản
  ghi không tồn tại phải trả `needsInput`, tuyệt đối không âm thầm tạo bản ghi
  mới. "Sửa nhầm thành thêm mới" là kiểu hỏng im lặng tệ nhất: dữ liệu trông vẫn
  đúng, chỉ là nằm ở chỗ không ai ngờ.
- **D4.** `status` chỉ nhận đúng 6 giá trị trên. Không có trạng thái "gần xong",
  "chắc là ổn". Mơ hồ thì là `failed`.

---

## 5. Guardrail: rủi ro + whitelist học dần

Đã chốt: **phân loại theo rủi ro, cộng whitelist do admin bấm nút để hệ tự học.**

### Ba mức rủi ro

| riskTier | định nghĩa | mặc định |
|---|---|---|
| `read` | Không thay đổi gì bên ngoài. Đọc, tìm, phân tích, tính toán. | Tự chạy |
| `write` | Thay đổi được nhưng hoàn tác được. Tạo trang Notion, thêm sự kiện lịch, ghi file trong vùng dự án. | Chạy nếu khớp whitelist **và** còn quota; ngược lại hỏi admin |
| `irreversible` | Không hoàn tác được hoặc người khác nhìn thấy được. Gửi mail/tin nhắn ra ngoài, đăng công khai, xoá dữ liệu, chi tiền, đổi credential. | **Luôn hỏi.** Không whitelist được. |

- **G1.** Nghi ngờ thì nâng mức, không hạ. `write` mà "hình như không hoàn tác được"
  → xếp `irreversible`.
- **G2.** `irreversible` không có cơ chế "luôn cho phép". Đây là điều tuyệt đối,
  đổi lại admin phải bấm nút vài lần mỗi tuần — chấp nhận được với hệ dùng cá nhân.
- **G3.** riskTier được gán trong `companySpec.yaml` và **model không sửa được lúc chạy**.
  dispatcher đọc từ manifest trên đĩa, không đọc từ envelope.

### Luồng phê duyệt

```
company cần làm việc write/irreversible
   → dispatcher chặn, trả status = needsApproval
   → CEO soạn câu hỏi ngắn gọn: "làm gì / với cái gì / hậu quả gì"
   → Telegram, nút:  [Cho phép 1 lần]  [Luôn cho phép]  [Từ chối]
   → admin bấm
   → sinh approvalToken  →  dispatcher chạy lại đúng lời gọi cũ
```

- **G4.** `approvalToken` gắn với `payloadHash` của chính lời gọi đã hiện cho admin
  xem, dùng **một lần**, TTL ngắn (đề xuất 10 phút). Điều này chặn kịch bản
  "xin duyệt việc vô hại rồi đổi nội dung thành việc nguy hiểm" — đổi một ký tự
  là hash sai, token vô hiệu.
- **G5.** **Mọi** câu hệ nói với admin phải nói **hậu quả**, không phải tên hàm
  và không phải mã nguyên tắc. "Gửi mail cho anh Bình, nội dung: …" chứ không
  phải "gọi gmail.send". Áp cho cả thông báo sau khi làm xong, không riêng câu
  hỏi duyệt.
  *Đo được:* câu "Đã ghi luật: addExpense với {category: ăn uống} — tối đa
  20/ngày, hết hạn 2026-10-31 (G7)" bị hiểu thành **dữ liệu sẽ bị xoá sau 20
  ngày**. Câu nào nói về *quyền* thì phải nói rõ là quyền, và nói luôn dữ liệu
  không bị ảnh hưởng.
- **G6.** Không trả lời trong TTL = **từ chối**. Im lặng không bao giờ là đồng ý.
- **G13 — Đường duyệt phải là thứ model KHÔNG tự đi được.**
  Chỉ có một cách duyệt: `--approval-id <id>`, và nó chỉ qua khi trong kho có
  bản ghi `status='approved'` — trạng thái đó **chỉ** do gateway đặt khi admin
  bấm nút Telegram thật. Không có đường nào khác.
  *Đo được — lỗ hổng nặng nhất tính đến nay:* Lát 1 có cờ `--approve <payloadHash>`
  để duyệt tay từ terminal, mà dispatcher lại **trả chính payloadHash đó về cho
  CEO** trong `approvalRequest`. CEO chỉ cần đọc rồi truyền ngược lại là tự duyệt
  cho mình. Đã xảy ra thật: một mục nhật ký được ghi vào Notion mà admin chưa
  bấm nút nào. Đã bỏ hẳn cờ đó.
  *Luật rút ra:* **đừng đưa model thứ nó không cần.** Mỗi mẩu dữ liệu trả về cho
  LLM phải trả lời được câu "nó dùng cái này làm gì?" — không trả lời được thì cắt.
- **G15 — Không việc nào được rơi vào chỗ không với tới.** G14 gắn nút đúng cho
  lượt hiện tại, nhưng để lại một lỗ: yêu cầu duyệt sinh ra ở lượt TRƯỚC thì
  không còn nút nào. CEO nhắc tới nó — *"đang chờ admin bấm nút"* — mà admin
  không có gì để bấm, phải mở luồng mới làm lại từ đầu.
  Bắt buộc có một lối vào luôn dùng được: lệnh `/duyet` liệt kê mọi yêu cầu còn
  treo kèm nút. Chạy bằng code cứng nên vẫn dùng được khi CEO treo hoặc hạn mức
  cạn (O7).
- **G14 — Nút duyệt chỉ gắn cho việc của LƯỢT NÀY.**
  Một yêu cầu cũ còn treo mà bị gắn nút vào tin nhắn báo "đã xong" thì admin
  tưởng đang duyệt việc vừa nhắc, thực ra duyệt việc khác. Lọc theo mốc thời
  gian bắt đầu lượt, không chỉ theo phiên.
- **G11.** Tách hai đồng hồ, đừng lẫn: **yêu cầu duyệt** sống lâu (đề xuất 12 giờ —
  admin còn ngủ), nhưng **approvalToken** sinh ra sau khi bấm nút thì TTL ngắn
  (10 phút) và dùng một lần. Nếu gộp làm một, mọi việc gửi lúc nửa đêm đều tự
  từ chối trước khi admin kịp thấy.

### Whitelist học dần

Khi admin bấm *Luôn cho phép*, ghi một dòng:

```jsonc
{
  "ruleId": "wl_01J8...",
  "companyId": "notionCompany",
  "capability": "createPage",
  "scope": { "databaseId": "db_congViec" },  // hẹp nhất có thể
  "maxPerDay": 20,
  "expiresAt": "2026-11-02T00:00:00Z",       // BẮT BUỘC có hạn
  "createdFromTaskId": "tsk_...",
  "createdAt": "2026-08-02T..."
}
```

- **G7.** Whitelist luôn có hạn dùng. Mặc định đề xuất 90 ngày. Quyền không bao giờ
  là vĩnh viễn — hệ tự co lại khi admin ngừng chú ý, thay vì tự phình ra.
- **G8.** Whitelist luôn có `scope` hẹp nhất suy ra được từ lần duyệt đó. "Cho phép
  tạo trang trong database Công Việc", không phải "cho phép tạo trang".
- **G9.** Whitelist chỉ áp dụng cho `write`. Không bao giờ cho `irreversible` (G2).
- **G12.** Scope của một luật whitelist do **chính company khai báo**, qua trường
  `whitelistScope` trong `companySpec.yaml` — liệt kê những field mà luật được
  phép khớp theo. Capability không khai trường này thì **không whitelist được**,
  lần nào cũng phải hỏi. Mặc định an toàn.
  *Vì sao:* dispatcher không biết field nào của một company là "hẹp" và field nào
  là "rộng". `tags` thì hẹp, `text` thì rộng — chỉ company mới biết. Để dispatcher
  tự đoán thì hoặc quá rộng (nguy hiểm) hoặc quá hẹp (whitelist vô dụng).
- **G10.** Admin xem và thu hồi whitelist bằng lệnh Telegram bất kỳ lúc nào; báo cáo
  định kỳ của backOffice liệt kê những rule sắp hết hạn và những rule chưa dùng lần nào.

---

## 6. Chống vòng lặp và chống chạy hoang

Vòng lặp vô hạn là rủi ro số một của hệ đa agent, và nó đốt hạn mức thật. Ở đây có
**năm lớp**, độc lập nhau, đều là code cứng.

- **L1 — Cấu trúc.** Hình sao (P3). Không có cạnh nào từ company sang company nên
  không có chu trình nào tồn tại được. Đây là lớp mạnh nhất.
- **L2 — Độ sâu.** `maxDepth` mặc định 2. CEO → company là 1. Company không gọi
  ai nên không có 3. Vượt là chặn.
- **L3 — Ngân sách theo trace.** Mỗi `adminMessage` có trần cứng: số lượt CEO suy
  nghĩ, tổng số task, tổng chi phí USD, và **deadline tuyệt đối theo đồng hồ tường**.
  Hết là dừng và báo cáo dở dang — *không* tự xin thêm.
- **L4 — loopGuard theo dấu vân tay.** Băm `(companyId, capability, inputHash)`.
  Cùng một dấu vân tay lặp quá N lần (đề xuất N=2) trong một trace → chặn, đánh dấu
  `rejected`, báo CEO là "anh đang lặp lại chính mình". Bắt được kiểu lặp mà bộ đếm
  độ sâu không thấy: CEO thử đi thử lại cùng một việc và mong kết quả khác.
- **L5 — Không tự kích hoạt.** `companyResult` **không bao giờ** tự tạo task mới.
  Chỉ CEO tạo task, và chỉ khi đang xử lý một `adminMessage` hoặc một cron đã đăng ký.
  Không có đường nào để hệ tự nói chuyện với chính nó qua đêm.

Thêm:
- **L6 — Có phanh tay.** Lệnh Telegram `/stop` giết toàn bộ trace đang chạy ngay lập
  tức, không hỏi lại. Việc này phải chạy được kể cả khi CEO đang treo.
- **L7 — Hết hạn mức thì BÁO, không đoán trước.** *(viết lại 2026-08-16 — bản cũ
  ở cuối mục này)* Nguồn sự thật duy nhất về hạn mức là **Anthropic tự nói**:
  phiên trả lỗi hết hạn mức hoặc mã 429. Bắt được thì báo admin ngay, kèm loại
  cửa sổ (5 tiếng / tuần) và giờ mở lại nếu có, và ghi vào `quotaHit` để báo cáo
  sáng nhắc lại. Hệ **không** tự cộng chi phí rồi đoán xem còn bao nhiêu.

  Vì sao bỏ cách cũ — bản cũ đọc: *"chạm ngưỡng cảnh báo của cửa sổ 5 tiếng hoặc
  của tuần → hệ tự chuyển sang chế độ chỉ đọc"*, ngưỡng đặt ở `registry/gateway.yaml`:

  1. **Con số không bám thực tế.** Đo 2026-08-16: `claude -p --output-format json`
     trả về tokens và `total_cost_usd`, nhưng không có trường nào cho biết hạn
     mức còn lại; CLI cũng không có lệnh con `usage`. Mọi ngưỡng vì thế chỉ là
     quy đổi từ bảng giá token — hệ tự bịa, không liên quan trần thật của gói Pro.
  2. **Nó chặn ngược.** Cầu dao chỉ chặn `write` — ghi chi tiêu, ví, việc vặt —
     những thứ tốn **$0** LLM vì company là code cứng gọi REST. Còn thứ thật sự
     đốt hạn mức đều là `read`: `nghienCuu` $3,50 · `auditSite` $2,00 ·
     `auditPage` $0,35. Không cái nào bị chặn. Nghĩa là nó vô dụng với thứ cần
     chặn, và gây hại với thứ không cần.
  3. **Không cần ai khoá hộ.** Hết hạn mức thì CEO tự dừng vì không gọi được
     model. Sổ sách vẫn ghi được bình thường (company không dùng LLM), nên sự
     cố hạn mức không còn kéo theo sự cố mất dữ liệu.

  Chi phí vẫn được **đo và báo cáo** — biết đang tiêu vào đâu là việc khác với
  lấy con số đó đi chặn.
- **L7.1 — Việc hỏng vẫn phải khai chi phí.** Một phiên LLM chết giữa chừng đã
  đốt hạn mức y như một phiên chạy xong; ghi `costUsd = 0` cho nó là nói dối cầu
  dao. Hệ quả ngược đời: **càng hỏng nhiều, cầu dao càng tưởng hệ đang rảnh** —
  nó mù đúng vào lúc cần nhất, vì hỏng thường đi theo chùm (API nghẽn, hết lượt,
  bị cắt giờ) và mỗi lần thử lại lại đốt thêm.
  Đo được 2026-08-13: một lần `nghienCuu` chạy 133 giây rồi hỏng, backOffice ghi
  $0,00. Bản vá: `SkillError` mang theo `cost_usd`, company đọc lại bằng
  `getattr(exc, "cost_usd", 0.0)` trước khi trả kết quả.
  Đây là ràng buộc lên **cách đo**, không phải lên cách báo cáo — nên nó nằm ở
  đây chứ không nằm trong O10, dù cùng gốc "nuốt lỗi thì mất luôn con số".

  **Nhánh bị CẮT NGANG đã lấp (2026-08-14).** `--output-format json` im lặng
  tới lúc kết thúc rồi mới in một cục, nên cắt ngang là mất trắng. Đổi sang
  `stream-json` + đọc từng dòng trong tiến trình cha (`core/execution/brainRunner.py`): số
  liệu nằm sẵn trong bộ nhớ cha, giết tiến trình con lúc nào cũng còn. Đo được:
  cắt ở giây thứ 6 vẫn thu về $0,0108 — trước đó là $0,00.

  **Con số nhánh này là ƯỚC LƯỢNG, và phải được gọi đúng tên.** Phiên chạy trọn
  thì lấy `total_cost_usd` CLI tự tính; phiên bị cắt thì quy token ra tiền bằng
  bảng giá trong `brainRunner.GIA`. Ba điều đã đo, đừng phát hiện lại:
  1. **Lệch −6%, luôn về phía đếm THIẾU** (đo 3 lần: −5,7% · −5,9% · −7,0%).
     Vì có model chạy ngầm không lên luồng, và `output_tokens` trên luồng là số
     TẠM — đo được out=2 trong luồng trong khi thật là out=61.
  2. **Phải gom theo `message.id` và GHI ĐÈ, không cộng dồn.** Một message lên
     luồng hai lần mà cộng mù thì khoản ghi cache bị tính đôi — nó chiếm ~93%
     chi phí một lượt, nên lệch vọt lên **+82%**.
  3. **Bảng giá giải ngược từ `modelUsage`, không chép từ tài liệu.** Trường đó
     có đủ token VÀ `costUSD` nên giải ra đơn giá rồi đối chiếu khớp đến từng
     đồng. Tra tài liệu suông sẽ đoán nhầm vế ghi cache: phiên ở đây dùng TTL
     1 giờ (2 lần giá vào), không phải 5 phút (1,25 lần).

  Model lạ không có trong bảng thì tính theo mức ĐẮT NHẤT và kêu tên nó ra —
  thà tưởng đã tiêu nhiều mà dừng sớm, còn hơn tưởng còn rảnh. Bản trước lặng
  lẽ rơi vào nhánh mặc định, nên `claude-sonnet-5` bị tính bằng giá
  `claude-sonnet-4-6` suốt mà không ai biết — may là hai model cùng giá.

- **L8 — Tiền THẬT ra ngoài thì phải khai, phải hỏi, và có trần.** *(thêm
  2026-08-16)* Năng lực nào gọi dịch vụ tính tiền bên ngoài phải khai khối
  `paidApi` trong manifest, gồm `nhaCungCap` và `giaUocVnd`. Khai rồi thì
  dispatcher tự động bật ba thứ:

  1. **Hỏi duyệt MỌI lần**, kể cả khi `riskTier: read`. Đọc thì không đổi gì
     của admin, nhưng vẫn trừ tiền — rủi ro ở đây nằm ở ví, không nằm ở dữ liệu.
  2. **Không có đường whitelist.** "Luôn cho phép tiêu tiền" là câu không ai
     thật sự muốn nói (cùng lẽ với G9).
  3. **Trần theo tháng dương** ở `registry/gateway.yaml`, chạm thì chặn cứng.
     Theo tháng dương vì hoá đơn nhà cung cấp cũng theo tháng — admin đối chiếu
     được; cửa sổ trượt 30 ngày đẹp về kỹ thuật nhưng không khớp thứ họ nhìn
     thấy khi mở bảng thanh toán.

  Nút duyệt phải nói **GIÁ trước tiên** — đó là thứ phân biệt "đồng ý làm" với
  "đồng ý trả tiền" (G5). Sổ `chiTieuNgoai` tách hẳn khỏi `taskLog.costUsd`:
  hai loại tiền khác bản chất, gộp một chỗ thì lúc đối chiếu hoá đơn không tách
  ra được. Ghi con số company **báo về thật**, không ghi giá ước trong manifest;
  company không báo thì ghi theo ước và nói rõ trong `ghiChu` là ước.

  **Vì sao có luật này:** admin bị Google AI Studio trừ 144.000đ mà không thu
  được sản phẩm ưng ý (08/2026). Khoản đó tiêu ngoài hệ, nhưng nó chỉ đúng ra
  cái lỗ sắp mở: company đầu tiên dùng Gemini/Veo mà quên khai sẽ tiêu tiền
  thật trong im lặng — không nút duyệt, không trần, không dòng nào trong sổ.
  Nên `codemap --check` soát luôn: company cầm chìa khoá một dịch vụ tính tiền
  (`GEMINI_*`, `OPENAI_*`, `REPLICATE_*`…) mà không năng lực nào khai `paidApi`
  thì phạm luật.

  **Phân biệt rạch ròi với L7.** Hạn mức gói Pro dùng hết thì thôi, tháng sau
  lại có, và Anthropic không phơi ra số còn lại — nên hệ **không** đoán và
  **không** chặn theo nó. Tiền ở L8 thì trừ vào thẻ, đo được từng lời gọi, có
  hoá đơn — nên ở đây chặn là đúng. Cùng là "chi phí" nhưng ngược nhau về cách
  xử lý; lẫn hai thứ này chính là sai lầm của cầu dao cũ.

---

## 7. Quy ước đặt tên

Tiếng Anh, `camelCase`, thống nhất ở **mọi nơi**: biến, field JSON, cột SQLite,
key YAML, tên biến môi trường trong tài liệu.

| Loại | Quy ước | Ví dụ |
|---|---|---|
| companyId | camelCase + hậu tố `Company` | `seoCompany`, `notionCompany`, `financeCompany` |
| capability | động từ + tân ngữ | `auditSite`, `createPage`, `sendReport` |
| bảng SQLite | camelCase số ít | `taskLog`, `eventLog`, `approvalRule` |
| cột SQLite | camelCase | `createdAt`, `costUsd`, `traceId` |
| field JSON | camelCase | `taskId`, `riskTier`, `maxCostUsd` |
| id có tiền tố | `<viết tắt>_<ULID>` | `tsk_`, `trc_`, `wl_`, `apr_` |
| thời gian | ISO 8601 UTC, hậu tố `At` | `createdAt`, `deadlineAt` |
| tiền | hậu tố `Usd` | `costUsd`, `maxCostUsd` |
| thời lượng | hậu tố `Ms` / `Sec` | `durationMs`, `maxDurationSec` |
| boolean | `is` / `has` / `can` | `isReversible`, `hasApproval`, `canRetry` |
| thư mục company | **trùng `companyId`** | `companies/seoCompany/` |
| tên file khác | kebab-case | `docker-compose.yml`, `audit-site.schema.json` |
| biến môi trường | UPPER_SNAKE (ngoại lệ duy nhất, theo chuẩn shell) | `DATAFORSEO_KEY` |

- **N1.** Không viết tắt trừ khi đã có trong bảng này. `cfg`, `msg`, `tmp` → không.
  `traceId` chứ không `tid`.
- **N2.** Một khái niệm một tên, ở khắp nơi. Đã là `taskId` thì SQLite, JSON, log,
  tên trong log đều là `taskId`. Không có `task_id` ở chỗ này và `taskID` ở chỗ kia.
- **N3.** Tên phải nói *cái gì*, không nói *ai gọi*. `auditSite` chứ không `ceoAudit`.

---

## 8. Cấu trúc thư mục (đề xuất)

```
companySpec/
├── PRINCIPLES.md              ← file này
├── ARCHITECTURE.md            ← chi tiết kỹ thuật, viết sau khi chốt mục 12
├── schemas/                   ← nguồn chân lý cho mọi hợp đồng dữ liệu
│   ├── taskEnvelope.schema.json
│   ├── companyResult.schema.json
│   └── companySpec.schema.json
├── registry/
│   ├── companies.yaml         ← danh mục company đang hoạt động
│   ├── riskPolicy.yaml        ← bảng phân loại rủi ro toàn cục
│   └── whitelist.jsonl        ← append-only, do hệ ghi, admin đọc
├── ceo/
│   ├── SYSTEM.md              ← system prompt của CEO (thay hẳn prompt mặc định)
│   ├── settings.json          ← deny rules — model KHÔNG sửa được (P2)
│   ├── hooks/guard.py         ← PreToolUse — hàng rào thật
│   └── store.sqlite           ← thread ↔ sessionId, nhật ký quyết định phiên
├── ops/
│   ├── dispatch.py            ← DISPATCHER — điểm nghẽn cố ý (T2)
│   └── ask.py                 ← adminGateway bản local, tạm thay Telegram
├── companies/
│   └── <companyId>/
│       ├── companySpec.yaml   ← BẮT BUỘC
│       ├── store.sqlite
│       ├── schemas/
│       └── (SKILL.md | src/ | workflow.json | …)
├── backOffice/
│   ├── store.sqlite
│   └── reports/
└── ops/
    ├── docker-compose.yml
    └── backup/
```

- **F1.** Không có logic nào chỉ tồn tại trong giao diện của một công cụ bên
  ngoài. Mọi thứ quyết định hành vi phải là file trong repo, đọc được bằng mắt,
  so sánh được giữa hai phiên bản.
  *Vì sao:* dự án từng định để n8n giữ khung. Workflow sống trong giao diện thì
  không ai review được, không git diff được, và mất theo container.
- **F2.** Không có secret nào nằm trong repo. Chúng ở `ops/.env`, chmod 600,
  bị `.gitignore` chặn.
- **F3.** `store.sqlite` không commit. Backup riêng.
- **F5.** **Dự án này bắt đầu từ số 0.** Không nạp lại token, chat id, credential,
  container, volume hay workflow của bất cứ dự án nào trước đó — kể cả khi chúng
  còn dùng được và kể cả để "thử cho nhanh". Hạ tầng dùng chung được, nhưng phải
  là instance riêng của dự án này.
  *Vì sao:* state cũ mang theo cấu hình mình không đọc hết, và một dự án chỉ sạch
  đúng một lần — lúc bắt đầu. Tiết kiệm 10 phút bây giờ đổi lấy một tháng nghi ngờ
  "cái này ở đâu ra" về sau.
- **F6.** Định danh cá nhân (chat id, email, tên máy) không nằm trong repo. Đọc
  từ biến môi trường hoặc file `*.local.yaml` bị `.gitignore` chặn. Repo phải
  clone sang máy khác mà không lộ gì.
- **F4.** Không giữ thứ tái tạo được: `.venv`, `node_modules`, `__pycache__`, build
  artifact. Giữ file khai báo (`requirements.txt`, `package.json`), dựng lại khi cần.
  Repo này là **đặc tả**, không phải môi trường chạy.

---

## 9. Vận hành: mọi thứ phải quan sát được

- **O1.** Mọi tác động ra ngoài đều có `idempotencyKey`. Chạy lại một task không
  được tạo ra hai email, hai sự kiện lịch, hai lần chi tiền.
- **O2.** Retry chỉ dành cho `read`. `write` và `irreversible` không tự retry —
  hỏi lại admin. Retry mù là cách nhanh nhất để gửi cùng một cái mail ba lần.
- **O3.** Hỏng thì hỏng to. Không có "im lặng bỏ qua rồi làm tiếp". Lỗi → dừng
  nhánh đó → ghi log → báo cáo. CEO được phép nói "việc này em chưa làm được".
- **O4.** Báo cáo cho admin phải nói được: đã làm gì, chưa làm gì và **vì sao**,
  đã thay đổi gì ra ngoài, tốn bao nhiêu. Không có báo cáo kiểu "đã xong ạ".
- **O5.** Mọi thứ có `traceId`. Từ một tin nhắn Telegram phải dựng lại được toàn
  bộ chuỗi sự kiện bằng một câu truy vấn.
- **O8 — Hỏng ngoài dự kiến vẫn phải để lại dấu.** Ngoại lệ không lường trước
  làm dispatcher văng traceback rồi thoát: CEO chỉ thấy stdout rỗng, admin thấy
  một câu lỗi vô nghĩa, và trong log **không có gì**. Không tra được thì không
  sửa được. Mọi điểm vào phải bọc `try/except` cuối cùng, trả `companyResult`
  hợp lệ và ghi log trước khi chết.
- **O9 — Model không được tự đoán là hệ sẽ chặn nó.** CEO từng từ chối làm lại
  một việc admin nhắc lại, lý do là "hai lần trước đã hỏng nên lần ba sẽ bị
  chặn" — trong khi lỗi đã được sửa giữa chừng và bộ đếm chặn lặp thậm chí chưa
  hề đếm gì. Bộ đếm nằm ở dispatcher; **để nó tự nói khi thật sự chặn.**
  Model tự áp guardrail lên chính mình dựa trên trí nhớ lỗi thời là một dạng
  hỏng ngầm: admin tưởng hệ đang bảo vệ, thực ra hệ đang từ chối làm việc.
- **O10 — Lỗi không được hoá trang thành giá trị hợp lệ.** `or {}`, `or 0`,
  `except: return ""` biến một lời gọi hỏng thành một con số trông như thật.
  Đây là kiểu hỏng **tệ hơn cả văng traceback**: traceback thì ai cũng thấy, còn
  `0đ` không phân biệt được với "hôm nay không tiêu gì" — báo cáo vẫn gửi đúng
  giờ, vẫn đẹp, và vẫn sai suốt nhiều tuần mà không ai nghi ngờ gì.

  Ba lần đo được, cùng một bệnh, trong hai ngày 13–14/08/2026:

  | Chỗ hỏng | Nuốt bằng | Admin nhìn thấy |
  |---|---|---|
  | Báo cáo tối gọi sổ thu/chi sai tên trường → `rejected` | `or {}` → `or 0` | "thu 0đ · chi 0đ" mỗi tối, trong khi hỏi lại CEO thì số đúng |
  | Đọc ảnh hỏng | `except Exception: return ""` | "em đọc không ra gì", không nơi nào ghi vì sao |
  | CEO chết lúc khởi động | `ceoRunLog` chỉ lưu số | `numTurns=0` — hết hạn OAuth và API nghẽn trông y hệt nhau |

  Hai điều phải giữ:
  1. Lời gọi không `ok` thì **nói ra**, đừng thay bằng giá trị mặc định. Không
     chắc thì thà không in con số nào còn hơn in một con số bịa.
  2. Mọi lần hỏng phải để lại **lý do ở nơi tra lại được**, không chỉ nhắn cho
     admin đúng một lần rồi thôi. Lỗi "lâu lâu mới bị" không tái hiện theo yêu
     cầu được; thứ duy nhất lần ra nó là một cuốn sổ ghi từng lần hỏng.

  Liên quan O3 (hỏng thì hỏng to) và O8 (hỏng ngoài dự kiến vẫn để lại dấu).
  Khác chỗ: O3/O8 nói về lúc hỏng ồn ào; O10 nói về lúc hỏng **êm ru**.
  Trường hợp riêng cho chi phí nằm ở **L7.1** — nuốt mất con số ở đó không làm
  sai báo cáo, mà làm hỏng cầu dao.
- **O7 — Lệnh tra cứu không được phụ thuộc LLM.** "Còn bao nhiêu hạn mức",
  "quyền nào đang có", "tuần này làm được gì" đều là câu hỏi deterministic —
  code cứng trả lời được, và **phải** trả lời được kể cả khi hạn mức đã cạn hoặc
  CEO đang treo. Bắt admin tốn hạn mức để biết còn bao nhiêu hạn mức là thiết kế
  tự mâu thuẫn.
- **L7 (bổ sung) — HẾT HIỆU LỰC 2026-08-16.** Bản cũ: *"chạm trần thì khoá
  `write` và `irreversible`, nhưng vẫn cho tra cứu"*. Không còn chỗ nào khoá
  theo ngưỡng đoán nữa, nên luật này không còn đối tượng áp dụng. Tinh thần của
  nó — **sự cố hạn mức không được biến thành sự cố mất dịch vụ** — thì giữ
  nguyên và nay được bảo đảm bằng chính kiến trúc: company là code cứng, nên
  ghi chép vẫn chạy kể cả khi CEO không gọi được model.
- **O6.** backOffice gửi tổng kết định kỳ: chi phí theo company, tỉ lệ lỗi, số lần
  hỏi duyệt, whitelist sắp hết hạn, whitelist chưa dùng lần nào.

---

## 10. Quy tắc phát triển

- **W1.** Company mới bắt đầu ở `read`. Chỉ nâng lên `write` sau khi đã chạy thật
  và đọc log thấy ổn.
- **W2.** Mỗi company phải có chế độ `dryRun` in ra việc *định* làm mà không làm.
  Không có dryRun thì không được lên `write`.
- **W3.** Thêm company không được sửa CEO. Nếu phải sửa CEO để thêm company, tức
  là bản hợp đồng ở mục 3 đang rò rỉ — sửa hợp đồng, đừng sửa CEO.
- **W4.** Xoá dễ hơn thêm. Company không dùng 60 ngày → backOffice đề nghị gỡ.
- **W5.** Mỗi nguyên tắc trong file này có mã (P1, C2.3, G7…). Comment trong code
  và prompt agent trích mã đó. Khi ai đó muốn phá luật, phải nói rõ phá luật nào.

---

## 11. Những điều dứt khoát KHÔNG làm

1. Không để LLM sinh và chạy SQL/shell tuỳ ý trên store thật.
2. Không cho company gọi company (P3).
3. Không có tool nào vừa đọc vừa ghi mà không khai báo `sideEffects`.
4. Không whitelist `irreversible` (G2).
5. Không có quyền vĩnh viễn (G7).
6. Không tự retry việc có tác động ra ngoài (O2).
7. Không nhét secret vào prompt, log, hay `companySpec.yaml`.
8. Không để company nhắn thẳng cho admin (T1).
9. Không dựa vào prompt để chặn hành vi nguy hiểm (P2).
10. Không mở rộng phạm vi vì "tiện thể". Hệ này phục vụ một người; nhỏ và đúng
    hơn là to và mơ hồ.
11. **Không nối sản phẩm của admin vào hệ này** (§0 Phạm vi). Trợ lý riêng, không
    phải hạ tầng sản xuất.
12. Không để cron làm việc `write`/`irreversible` (S3).
13. Không để CEO tự đặt lịch chạy (S2).
14. Không thay lỗi bằng `0`, `""` hay `{}` rồi đi tiếp như không có gì (O10).

---

## 11b. Ràng buộc thật của tầng CEO (đo trên máy, 2026-08-02)

Không phải suy đoán — chạy thật và đọc số.

### Xác nhận về gói Pro

```json
{ "authMethod": "claude.ai", "apiProvider": "firstParty", "subscriptionType": "pro" }
```

CLI đang đăng nhập bằng tài khoản claude.ai gói Pro. **Đúng, chỉ trả tiền gói Pro,
không tốn thêm phí API.** Mọi lần gọi trừ vào hạn mức gói, không trừ vào ví API.

### Con số quan trọng nhất: chi phí cố định mỗi phiên mới

Chạy thử `claude -p "Reply with exactly: OK"` — một câu vô nghĩa nhất có thể:

```
total_cost_usd : 0.140804
cache_creation_input_tokens : 23,359
output_tokens : 4
```

**23.359 token nạp vào trước khi làm bất cứ việc gì.** Đó là system prompt +
định nghĩa tool + CLAUDE.md + danh mục 39 skill và 24 agent đang cài ở
`~/.claude/`. Trả lời "OK" tốn 4 token; phần còn lại là tiền vé vào cửa.

Ba hệ quả bắt buộc phải thiết kế theo:

- **B1 — Mỗi tin nhắn một phiên mới là phương án đắt nhất.** Cùng một câu hỏi,
  phiên mới trả giá `cache_creation`, phiên tiếp trả giá `cache_read` (rẻ hơn
  khoảng một bậc). Đây là lý do kỹ thuật để giữ phiên, không phải chuyện tiện tay.
- **B2 — Skill/agent cài ở `~/.claude/` là chi phí chung của mọi phiên.** 31 skill
  SEO đang nằm ở global, nghĩa là CEO gánh chúng kể cả khi admin hỏi về lịch họp.
  Cái này **vi phạm C2** (company phải là hộp đen): ruột của `seoCompany` đang rò
  vào context của CEO ở mọi lượt. Xem B4.
- **B3 — Số `total_cost_usd` là thước đo, không phải hoá đơn.** Gói Pro không trừ
  tiền, nhưng đây là đại lượng duy nhất đo được để dựng thanh tiến trình. Cộng dồn
  nó là cách theo dõi hạn mức khả thi nhất.

### B4 — Cô lập tài sản của company khỏi context của CEO

Đừng cài skill/plugin của company vào `~/.claude/`. Để trong thư mục company và
nạp có chọn lọc khi dispatcher gọi:

```
claude -p --plugin-dir companies/seoCompany/plugin --settings companies/seoCompany/settings.json
```

CEO chỉ cần biết `seoCompany` có năng lực `auditSite` — không cần 31 file SKILL.md
nằm trong đầu nó suốt ngày.

**Đã thực hiện và đo lại (cùng ngày).** Chuyển 31 skill + 18 agent SEO từ
`~/.claude/` sang `companies/seoCompany/plugin/`, rồi chạy lại đúng câu lệnh cũ:

| | Trước | Sau | |
|---|---|---|---|
| `cache_creation_input_tokens` | 23.359 | **8.230** | −65% |
| `total_cost_usd` | 0,1408 | **0,0542** | −61% |

Một lần dọn dẹp cắt gần hai phần ba chi phí cố định của **mọi** phiên nguội, mãi
mãi. Đây là bằng chứng cụ thể nhất cho C2: ranh giới company không phải chuyện
sạch sẽ về mặt thẩm mỹ, nó là tiền hạn mức.

Suy ra một luật vận hành:

- **B8 — `--tools` là NẠP, `allow` là CHẠY. Hai chuyện khác nhau.**
  Khai một tool trong `--tools` mới chỉ đưa định nghĩa vào context. Muốn nó thật
  sự chạy được thì tên tool phải có trong `permissions.allow`. Thiếu vế sau, ở
  chế độ headless tool bị từ chối im lặng.
  *Đo được:* lần chạy `seoCompany` đầu tiên có `--tools WebFetch` nhưng không có
  `allow`, nên skill không đọc nổi trang web — mà vẫn viết ra một "báo cáo" và
  company trả `status: ok`. **Báo cáo vô dụng đội lốt thành công là kiểu hỏng tệ
  nhất**, vì admin tin là xong.
  *Cách bắt:* CLI trả sẵn `permission_denials` trong JSON. Có phần tử nào thì
  kết quả không đáng tin — trả `failed`, đừng trả `ok`.
- **B7 — Không thừa hưởng ngầm. Mặc định là RỖNG.**
  Dự án chỉ dùng những thứ nó **tự khai báo**. Bất cứ gì có sẵn trong `~/.claude`
  — MCP server, skill, agent, hook, settings, `CLAUDE.md` của thư mục cha — đều
  **không được tự động áp vào**, kể cả khi nó hữu ích, kể cả khi nó đã ở đó sẵn.
  Muốn dùng thì phải khai vào `companySpec.yaml` hoặc `ceo/settings.json`, và
  admin phải biết.
  *Vì sao:* thừa hưởng ngầm nghĩa là hành vi của hệ phụ thuộc vào thứ nằm ngoài
  repo. Sáu tháng sau admin cài một skill cho việc khác, CEO đổi hành vi, và
  không ai truy được vì sao. Repo phải mô tả đủ chính nó.
  *Kiểm chứng:* CEO chạy với `--tools Bash --strict-mcp-config
  --setting-sources project`. Hỏi nó có tool gì, phải trả lời đúng một chữ: Bash.
- **B6 — CEO phải chạy trong môi trường kín.** Claude Code mặc định nạp mọi thứ
  quanh nó: MCP server đã cấu hình, `CLAUDE.md` của thư mục cha, skill global,
  settings của máy. Với CEO thì đó **vừa tốn token vừa thủng guardrail**.
  Đo được: 4 connector của gói Pro (Gmail, Drive, Calendar, Notion) tự nạp vào
  mọi phiên, nghĩa là CEO **gửi được email mà không đi qua dispatcher** — không
  riskTier, không hỏi admin, không ghi `sideEffects`. Toàn bộ §5 bị vòng qua.
  Bắt buộc: `--strict-mcp-config` (không MCP nào) và `--setting-sources project`
  (không thừa hưởng settings máy). Muốn CEO dùng Notion thì **bọc thành company
  có manifest**, không phải để nó cầm sẵn.
  Cắt xong: token nạp mới mỗi phiên nguội **14.247 → 3.705 (−74%)**.
- **B5 — Không cài gì vào `~/.claude/`.** Global chỉ chứa thứ *mọi* phiên CEO đều
  cần. Tài sản của company nằm trong thư mục company. Trước khi cài bất cứ skill,
  agent hay plugin nào ở global, hỏi: "CEO có cần cái này ở **mọi** câu hỏi
  không?" Không → nó thuộc về một company.

### Theo dõi hạn mức 5 tiếng / tuần

**Sự thật khó chịu:** không có API công khai trả về "còn bao nhiêu %". Lệnh
`/usage` chỉ chạy được trong phiên tương tác, tiến trình nền không gọi được.

Cách làm được:

1. **Tự cộng dồn.** Mỗi lần gọi CEO dùng `--output-format json`, kết quả trả về
   sẵn `total_cost_usd`, `usage`, `modelUsage` (tách theo từng model), `num_turns`,
   `duration_ms`. Ghi hết vào `backOffice/store.sqlite`, gộp theo cửa sổ 5 tiếng
   trượt và theo tuần ISO.
2. **Hiệu chuẩn tay, định kỳ.** Thỉnh thoảng mở `claude` tương tác, gõ `/usage`,
   so với số tự cộng dồn, suy ra hệ số quy đổi. Làm một lần rồi ghi lại hằng số.
3. **Bắt lúc chạm trần.** Khi hết hạn mức, kết quả JSON có `is_error: true` và
   `api_error_status`. Gateway bắt cái này → gửi Telegram kèm giờ reset → bật
   cầu dao L7 (chuyển toàn hệ sang chỉ đọc cho tới khi reset).

Thanh tiến trình dựng từ (1), độ chính xác đến từ (2), an toàn đến từ (3).

### Xác thực

CEO chạy bằng phiên `claude.ai` đã đăng nhập sẵn trên máy (keychain của host).
Không cần token riêng. Đó cũng là lý do CEO phải chạy trên host chứ không trong
container (Q1) — bê credential vào container là thêm một chỗ để rò rỉ.

### Model mặc định

Lần chạy thử dùng `claude-sonnet-4-6` cho lượt chính và `claude-haiku-4-5` cho tác
vụ phụ. CEO nên chạy model mạnh; company đơn giản có thể ép model rẻ để tiết kiệm
hạn mức — khai báo trong `companySpec.yaml`.

---

## 12. Chưa chốt — cần quyết trước khi viết code

### Đã chốt (2026-08-02)

| # | Câu hỏi | Chốt |
|---|---|---|
| Q1 | CEO chạy ở đâu, xác thực kiểu gì | Chạy thẳng trên máy local (WSL), CLI dùng gói Pro qua `claude.ai` auth có sẵn. `gateway/telegram/poller.py` gọi bằng `subprocess`. |
| Q2 | Phiên mới hay `--resume` | **Luật cứng 4 tầng, không dùng LLM** — xem `sessionPolicy` bên dưới. |
| Q5 | Ba company đầu tiên | `notionCompany` (connector) → `seoCompany` (plugin/skill) → `notesCompany` (code). Ba runtime khác nhau, đúng ý đồ thử lửa hợp đồng. |
| Q9 | Ollama / hạ tầng dự án cũ | **Bỏ ollama** — máy không chạy nổi, và dự án này cố ý chỉ dựa vào gói Pro (§0). Để dành khe cắm ở `sessionPolicy` R5 cho sau này. **Không tái sử dụng bất cứ thứ gì của dự án cũ** — xem F5. |
| Q11 | Gỡ skill SEO khỏi `~/.claude/` | **Đã làm.** 31 skill + 18 agent đã chuyển sang `companies/seoCompany/plugin/`. Global giờ chỉ còn 8 skill + 6 agent của hạ tầng dream. |
| Q12 | Xoá `.venv` 541M | **Đã xoá** cùng `__pycache__`. Repo 543M → 2,4M. `requirements.txt` giữ nguyên nên dựng lại được. Thành luật F4. |
| Q6 | Thư mục company đặt tên kiểu gì | **Trùng `companyId`**: `companies/seoCompany/`. Một khái niệm một tên (N2). File khác vẫn kebab-case. |

#### `sessionPolicy` — chốt cho Q2

Ý tưởng gốc là dùng một mô hình nhỏ để phân loại "tin nhắn này có liên quan tới
việc đang làm không". **Bỏ mô hình, giữ ý tưởng** — máy hiện tại không chạy nổi
LLM local, và gọi CEO chỉ để phân loại thì tự mâu thuẫn (tốn đúng cái mình muốn
tiết kiệm). Thay bằng luật cứng, không tốn token nào:

1. Mỗi luồng hội thoại có `threadId` và một `sessionId` (UUID) do **ta tự sinh**.
   Dùng `claude --session-id <uuid>` để **gán**, không phải đoán. CLI hỗ trợ sẵn.

2. **Thứ tự luật, dừng ở luật đầu tiên khớp:**

   | | Luật | Kết quả |
   |---|---|---|
   | R1 | Admin dùng chức năng **Reply** của Telegram | Nối vào đúng thread của tin được reply |
   | R2 | Tin nhắn mở đầu bằng `/moi` (hoặc `/new`) | Thread mới |
   | R3 | Cách lượt cuối **≤ N phút** | Nối thread gần nhất |
   | R4 | Ngoài cửa sổ đó | Thread mới |

   R1 là luật quan trọng nhất và rẻ nhất: Telegram đã gửi sẵn `reply_to_message`
   trong payload. Đây là cách con người vẫn phân biệt ngữ cảnh — mượn luôn, không
   cần máy đoán hộ.

3. **Trần phiên (code cứng):** một `sessionId` sống tối đa N lượt hoặc T token.
   Vượt → đóng phiên, mở phiên mới kèm tóm tắt mang sang. Không có phiên vô hạn —
   nếu không, chi phí mỗi lượt tăng dần cho tới lúc không dùng được.

4. Ghi log mọi quyết định (thread cũ/mới, luật nào khớp) để sau chỉnh ngưỡng N.

5. **Chỗ để dành cho bộ phân loại ngữ nghĩa:** khi có máy chạy được LLM local,
   cắm nó vào **giữa R3 và R4** — chỗ duy nhất còn mơ hồ. Ba luật kia vẫn giữ
   nguyên vì chúng chính xác tuyệt đối và miễn phí. Thiết kế sẵn khe cắm, đừng
   thiết kế sẵn sự phụ thuộc.

| Q3 | Trần chi phí | **Chưa cần trần bằng tiền.** Đang dùng gói Pro, không có hoá đơn — chỉ cần L7 canh hạn mức. Khi nào có company phải gọi Claude API trả tiền thì mới đặt trần USD, và đặt riêng cho company đó. |
| Q8 | Cron kích hoạt kiểu gì | **`scheduledTrigger`** — xem khung bên dưới. |
| Q10 | Ngôn ngữ | **Tiếng Việt**, luôn luôn. Trừ khi admin hỏi bằng ngôn ngữ khác. Tên biến/mã vẫn tiếng Anh (§7). |
| Q13 | Xác thực connector | **Admin làm thủ công.** Connector nào không tự kết nối được thì admin thiết đặt tay. Hệ không tự đi xin quyền — nó chỉ báo "connector X chưa xác thực" rồi dừng. |

### Còn lại

Không còn câu nào chặn việc bắt đầu.

---

## 12c. Q8 — `scheduledTrigger`: cửa vào thứ hai

L5 nói "chỉ CEO tạo task, và chỉ khi đang xử lý một `adminMessage` hoặc một cron
đã đăng ký". Vế thứ hai là một cái lỗ nếu không định nghĩa chặt: cron mà tự do thì
hệ chạy cả đêm, đốt hạn mức, và làm những việc admin chưa biết.

**Vấn đề cốt lõi:** với `adminMessage` thì admin đang cầm điện thoại — hỏi được.
Với cron thì admin đang ngủ. Guardrail dựa trên "hỏi admin" mất tác dụng.

Chốt:

- **S1 — Cron không phải "admin giả".** Nó là loại trigger riêng, `traceId` mang
  tiền tố `trc_cron_` để backOffice tách được ngay.
- **S2 — Phải khai báo trước.** Mỗi lịch là một mục trong `registry/schedules.yaml`
  với: chạy lúc nào, gọi company nào, năng lực nào, `maxRiskTier`, ngân sách riêng.
  Không có lịch nào sinh ra lúc chạy. CEO **không được tự đặt lịch**.
- **S3 — Trần rủi ro của cron là `read`.** Cron không tự làm `write` hay
  `irreversible`. Không whitelist nào nâng được — whitelist là quyền ĐỨNG,
  không gắn với nội dung nào, nên nó mở một cánh cửa chứ không phải một khe.

  **Ngoại lệ duy nhất, mở 2026-08-31 — PHIẾU HẸN.** Cron được chạy một lời gọi
  `write` khi và chỉ khi nó mang theo một phiếu duyệt có `henLuc` mà admin đã
  ký trước. Đây không phải quyền của cron: cron chỉ MỞ một chữ ký admin đặt sẵn
  cho đúng một nội dung, đúng một thời điểm. Bốn hàng rào đi kèm, tất cả đã có
  sẵn từ trước và không cái nào được nới:

  1. `payloadHash` khoá vào đúng nội dung admin đã đọc (G4) — đổi một ký tự là
     phiếu vô hiệu.
  2. Dùng **một lần** rồi chết, như mọi token duyệt khác.
  3. `consume()` từ chối nếu **chưa tới giờ** — không có phép kiểm này thì "hẹn
     giờ" chỉ là một cái nhãn, ai cầm mã là chạy được ngay.
  4. Quá **cửa sổ 60 phút** sau giờ hẹn thì thôi, không chạy một việc hẹn từ
     đêm qua.

  Vì sao mở: admin cần "việc đã duyệt thì tới giờ tự làm", và cách duy nhất
  khác là bắt họ bấm nút lúc 3 giờ sáng. Rủi ro mà S3 gốc canh — cron gây hại
  lúc admin ngủ và không ai nói không được — vẫn được canh, vì admin ĐÃ nói có
  cho đúng việc đó, đúng nội dung đó, trước khi đi ngủ. Sai thì sai đúng một
  lần, không thành vòng lặp.

  Việc chỉ NHẮC (không đụng sổ sách) thì không cần phiếu: `nhacCompany` giữ sổ,
  scheduler đọc (`read`) rồi nhắn qua T1 — nằm gọn trong S3 gốc.
- **S4 — Việc cần ghi thì xếp hàng, không hỏi lúc nửa đêm.** Cron phát hiện việc
  cần `write`+ → không thực thi, đẩy vào `pendingApproval`, gộp vào **một báo cáo
  buổi sáng**. Admin duyệt gộp một lần thay vì bị đánh thức từng cái.
- **S5 — Phiên riêng, ngân sách riêng.** Cron không bao giờ `--resume` phiên hội
  thoại của admin — nó làm bẩn ngữ cảnh và làm admin bối rối. Phiên riêng, ngân
  sách thấp hơn `adminMessage`.
- **S7 — Cảnh báo định kỳ chỉ nhắn khi có chuyện.** Lịch nào chỉ để canh chừng
  thì khai `quietIfEmpty: true`: bình thường im lặng, có bất thường mới lên tiếng.
  Cảnh báo nhắn đều đặn mỗi hai tiếng sẽ bị bỏ qua trong một tuần, và đúng hôm
  có chuyện thật thì admin cũng lướt qua.
  Ngược lại, báo cáo *định kỳ* (sáng, đầu tuần) thì vẫn gửi dù không có gì lạ —
  "hôm qua không có việc nào" cũng là thông tin.
- **S6 — Cron không đánh thức cron.** Một trace cron không tạo được
  `scheduledTrigger` mới. Đây là L5 áp cho chính cửa vào này.

Kết quả: cron là một **con đường hẹp hơn hẳn** đường của admin. Nó quan sát và
chuẩn bị; nó không hành động ra ngoài. Muốn hành động thì phải chờ admin thức dậy.

---

## 12b. Q14 — Giá của một lời gọi company (đã đo, 2026-08-02)

Cả file này từng ngầm giả định "CEO giao việc cho company" là thao tác rẻ. Đã dựng
`echoCompany` tối giản (một SKILL.md chỉ trả lại chuỗi) và đo thật, 3 lần mỗi cách.

### Kết quả

| Lời gọi | **A** — tiến trình riêng mỗi lần | **B** — cùng một phiên |
|---|---|---|
| #1 | 0,0651 | 0,0651 |
| #2 | 0,0642 | **0,0161** |
| #3 | 0,0651 | **0,0171** |
| **Tổng 3 lời gọi** | **0,1944** | **0,0983** |

Token nạp mới (`cache_creation_input_tokens`) — chỗ nhìn rõ nhất cái đắt:

| | A | B |
|---|---|---|
| Lời gọi #1 | 8.638 | 8.634 |
| Lời gọi #2 | 8.479 | **220** |
| Lời gọi #3 | 8.635 | **358** |

### Đọc số

- **Lời gọi thứ hai trở đi, A đắt gấp ~3,9 lần B** (0,065 so với 0,017).
- Về token nạp mới, A gấp **~30 lần** B (≈8.600 so với ≈290).
- Khoảng cách **giãn ra theo số lời gọi**: 3 lời gọi thì B rẻ hơn 49%; 5 lời gọi
  thì A ≈ 0,325 còn B ≈ 0,133 — rẻ hơn 59%.
- Trong cách A, khoảng **8.300 token mỗi lời gọi là thuế nạp lại, không mua được gì.**

### Chốt: `runtimePolicy`

- **RP1 — Mặc định là C.** Company nào làm được bằng code/workflow/connector thì
  không được dùng LLM. Rẻ nhất, deterministic nhất, dễ test nhất.
- **RP2 — Cần hiểu ngôn ngữ tự nhiên thì dùng B.** Chạy trong phiên CEO, dispatcher
  là `PreToolUse` hook. Đây là mặc định cho runtime `skill` và `agent`.
- **RP3 — Chỉ dùng A khi có lý do nêu được thành lời**, và ghi lý do vào
  `companySpec.yaml`. Lý do hợp lệ: cần cách ly tiến trình (code không tin cậy),
  cần chạy song song thật, cần môi trường/secret khác hẳn. "Cho sạch kiến trúc"
  **không** phải lý do hợp lệ — nó tốn gấp 4.

### Hệ quả: T2 phải viết lại

Nguyên văn cũ: *"dispatcher là điểm nghẽn cố ý — node n8n"*. Sai. Bản mới:

> **T2 (sửa).** Dispatcher là một **khái niệm**: mọi lời gọi company đi qua đúng
> một chỗ, và chỗ đó không phải là prompt. Hiện thực là `gateway/cli/dispatch.py`, và
> hook `PreToolUse` chặn mọi đường vòng. Cả hai đều là code cứng nằm ngoài tầm
> với của model, nên **P2 vẫn nguyên vẹn**.

### Kéo theo — chốt luôn Q4 và Q7

- **Q4 — CEO được tự làm việc nhỏ.** Với cách B, "gọi company" và "tự làm" gần như
  cùng giá, nên ranh giới đặt theo *ý nghĩa* chứ không theo chi phí: việc nào có
  `sideEffects` hoặc cần lưu lịch sử riêng thì phải là company; đọc file, tính toán,
  định dạng lại văn bản thì CEO tự làm.
- **Q7 — backOffice là hạ tầng, không phải company.** Nó không cần LLM (RP1), và
  bắt nó qua dispatcher chỉ tổ vòng vo. Nó là code đọc sqlite rồi ghi báo cáo.

---

## 13. Nhật ký thay đổi

| Ngày | Thay đổi | Lý do |
|---|---|---|
| 2026-08-02 | Khởi tạo khung sườn: 3 nguyên tắc gốc, kiến trúc 5 tầng, hợp đồng company, guardrail 3 mức + whitelist, 5 lớp chống lặp + 2 phanh khẩn, quy ước tên | Chốt khung trước khi viết code |
| 2026-08-02 | Thêm §11b (số đo thật của CLI trên máy); chốt Q1/Q2/Q5; thêm `sessionPolicy`; thêm Q11 về việc gỡ skill SEO khỏi global | Đo thật thay vì suy đoán; phát hiện chi phí 23k token/phiên nguội làm đổi thiết kế phiên |
| 2026-08-02 | Xoá `.venv` + `__pycache__` (543M → 2,4M); thêm luật F4 (repo là đặc tả, không phải môi trường chạy) | Chưa code gì nên không giữ artifact chạy |
| 2026-08-03 | **Bịt lỗ hổng tự duyệt.** Bỏ hẳn cờ `--approve <payloadHash>`; ngừng trả `payloadHash` cho CEO. Thêm **G13** và **G14** | CEO đọc `payloadHash` dispatcher trả về rồi truyền ngược lại là tự duyệt được cho chính mình — bỏ qua hoàn toàn nút bấm của admin. Đã xảy ra thật trên Telegram |
| 2026-08-04 | Thêm **W7** và công cụ `ops/snapshot.py` (chụp đầy đủ / so lệch / dựng lại một sổ Notion) | Admin không khôi phục được video 001 và mất trường `KPI chính`. Luật do admin yêu cầu: phép thử chạm tới thêm/sửa/xoá thì phải **tự** khôi phục được, không trông vào thùng rác của bên thứ ba |
| 2026-08-04 | Thêm **D10** (`target` phải là id thật) và **W6** (không test phá huỷ trên dữ liệu thật). Sửa `archiveTask` ghi `pageId`; `previousValue` của kế hoạch thêm `KPI chính` và trạng thái; thêm `notionClient.unarchive_page` | Kiểm chứng `archiveTask` bằng video 001 THẬT của admin. Không khôi phục được vì `target` ghi `video/001` chứ không phải page id, và `previousValue` thiếu `KPI chính` |
| 2026-08-04 | Thêm `deleteEntry` (nhật ký) và `archiveTask` (kế hoạch), cùng khuôn D7+D8. Thêm **D9** | Kế hoạch dùng "ẩn" thay vì "xoá" — 90 video là dữ liệu admin soạn công phu. Đối chiếu bằng chủ đề vì STT gần nhau cùng giai đoạn, kiểm giai đoạn không bắt được nhầm |
| 2026-08-04 | Thêm `deleteExpense` cho `expenseCompany`. Thêm **D7** (xoá phải đối chiếu) và **D8** (xoá không bao giờ whitelist) | Admin muốn xoá khoản chi mà không phải mở Notion. Xoá khác ghi: ghi sai thì thừa một dòng, xoá sai thì mất dữ liệu và admin không biết mất cái gì |
| 2026-08-04 | Thêm lệnh `/duyet` và **G15** | G14 để lại lỗ: yêu cầu duyệt của lượt trước không còn nút, CEO nhắc tới nó mà admin không bấm được gì — kẹt hoàn toàn |
| 2026-08-04 | Thêm **O8** (bọc try/except ở điểm vào dispatcher) và **O9** (CEO đừng tự đoán là sẽ bị chặn). Siết `SYSTEM.md`: lỗi hạ tầng thì báo nguyên văn, đừng khuyên admin chạy `lsof` | Tin nhắn của admin lúc 06:20 **không hề chạm tới dispatcher** — CEO nối phiên cũ, thấy hai lần hỏng từ trước khi sửa, rồi tự kết luận lần ba sẽ bị L4 chặn. Hai lần hỏng đó cũng không có trong log vì dispatcher văng traceback thô |
| 2026-08-06 | `approvals.create_request` **gộp phiếu trùng**: đã có phiếu `pending` cùng company + capability + payloadHash, chưa hết hạn, thì trả lại phiếu cũ thay vì INSERT dòng mới | Admin nhận HAI nút duyệt cho cùng một khoản 228.000đ, cách nhau 2 phút 24 giây, từ cùng một phiên. Bấm cả hai là ghi trùng tiền, mà nhìn vào không có cách nào biết đó là một khoản hay hai |
| 2026-08-06 | `walletCompany.adjustBalance` **kiểm dấu `soTien` khớp với `loai`**, lệch thì từ chối | Hợp đồng bắt khai hai trường cùng nói một điều nhưng không ai kiểm chúng đồng ý. CEO gửi `+228.000` kèm `loai: "chi"`; ví được CỘNG cho một khoản admin vừa TIÊU, tóm tắt in đúng dòng `1.128.766 + 228.000 (chi)` mà không chặn. Hai trường nói ngược nhau nghĩa là bên gọi đang nhầm — đoán ý lúc đó là cách chắc nhất để ghi sai tiền |
| 2026-08-14 | **Thêm O10 — lỗi không được hoá trang thành giá trị hợp lệ**, luật 14 ở §11, và **L7.1 — việc hỏng vẫn phải khai chi phí**. Kèm bản vá ba chỗ: báo cáo tối in ra lỗi thay vì nuốt bằng `or {}`; đọc ảnh thử lại 1 lần rồi ghi lý do vào `backOffice/media-loi.jsonl`; `ceoRunLog` thêm cột `loi` và `backOffice report` in lý do CEO chết, gom theo lý do | Ba lỗi khác nhau trong hai ngày hoá ra cùng một bệnh: thất bại bị thay bằng `0`/`""` rồi đi tiếp. Báo cáo tối in "thu 0đ · chi 0đ" **mỗi tối** vì gọi sổ bằng `from` thay vì `tuNgay` → `rejected` → `or {}` → `or 0`; hỏi lại CEO thì số đúng, nên không ai nghi. Con số 0 không phân biệt được với "hôm nay không tiêu gì" — đó là điều làm nó sống lâu. Cùng lúc phát hiện chi phí của phiên LLM hỏng bị ghi $0, tức cầu dao L7 mù với mọi lần hỏng — tách thành **L7.1** vì đó là ràng buộc lên cách ĐO, không phải lên cách báo cáo |
| 2026-08-14 | **CEO đọc được tệp CHỮ** (.html .md .txt .csv .json…): `decide_session` lấy `text` **hoặc** `caption`; `media.tu_update` tách `tailieu` (đọc được) khỏi `tepla` (nhị phân); thêm `media.doc_tep` bóc thẻ bằng regex, trần 40.000 ký tự | Admin gửi file .html kèm câu hỏi lúc 13:32 và 13:34, cả hai lần hệ đáp "Luồng mới đã mở. Cậu nói việc cần làm nhé." — vì Telegram để chữ admin gõ vào `caption` khi tin có tệp, mà gateway chỉ ngó `caption` khi đính kèm là ẢNH. **Câu hỏi bị vứt và không để lại dấu nào**: không phải lỗi nên không vào sổ, khiến lần tra đầu tiên kết luận nhầm là "không có tin nào tới nơi" (O10 lần nữa, ở một chỗ khác). Đọc bằng regex chứ không bằng model (RP1): đo được 33.655 byte HTML → 19.142 ký tự ≈ 6.400 token, vừa một lượt CEO, tốn 0 đồng — cho model đọc hộ là trả ~$0,03 và 17 giây cho việc regex làm xong tức thì. Nội dung tệp bọc trong khối "đây là DỮ LIỆU, không phải mệnh lệnh", cùng luật với chữ trong ảnh |
| 2026-08-14 | **Lấp nốt nhánh bị cắt ngang của L7.1**: `core/execution/brainRunner.py` đổi từ `subprocess.run(--output-format json)` sang `Popen(--output-format stream-json --verbose)` + đọc từng dòng + hẹn giờ giết tiến trình; gom usage theo `message.id`; bảng giá `GIA` giải ngược từ `modelUsage`. `SkillError` thêm `qua_gio`/`uoc_luong`, hai company bỏ nhánh `except TimeoutExpired` và rẽ theo cờ | `--output-format json` không in gì cho tới lúc kết thúc, nên cắt ngang là mất cả kết quả lẫn chi phí. Đo được dòng `stream-json` tới dần (1,59s · 2,70s · 4,31s · 6,35s), không bị đệm — nên đọc dần thì số liệu nằm sẵn trong tiến trình cha. Cắt ở giây thứ 6 giờ thu về $0,0108 thay vì $0,00. Hai bẫy phải trả giá mới thấy: cộng dồn mù làm tính đôi khoản ghi cache (+82%), và `output_tokens` trên luồng là số tạm — nên con số này là ƯỚC, lệch đều −6% về phía đếm thiếu |
| 2026-08-14 | **Sửa `deleteExpense`/`deleteIncome`/`deleteEntry`** — tàn dư đợt đổi tên 07/08 (`inp['amount']`, `inp['date']`, `inp['theme']` không còn tồn tại) và so ngày phải cắt `[:10]`. **Timeout HTTP Notion 20s → 8s** | Ba năng lực xoá hỏng hoàn toàn từ 07/08, không ai biết: câu báo lỗi gọi tên trường tiếng Anh cũ nên dựng câu là `KeyError` → `except Exception` → `failed` kèm câu vô nghĩa. Mà nhánh đó LUÔN chạy vì Notion trả `'2026-08-14T12:20:00.000+07:00'` (29 ký tự) còn schema ép `ngay` đúng 10 — so nguyên chuỗi thì không bao giờ khớp. Riêng timeout: 20s **bằng đúng** `maxDurationSec` của 33 năng lực, nên khi Notion ì thì dispatcher giết tiến trình trước lúc company kịp bắt `NotionError`; đo được 13/08 calendarCompany kẹt `running` 6 lần liên tiếp rồi tự khỏi. Timeout phải nhỏ hơn HẲN ngân sách, đừng bằng |
| 2026-08-16 | **Bỏ cầu dao hạn mức đoán mò; viết lại L7 thành "hết hạn mức thì BÁO"**. Thêm `lib/quotaSignal.py` nhận tín hiệu thật (câu báo của Anthropic hoặc mã 429), gateway và `skillRun` cùng dùng; ghi bảng `quotaHit`; gỡ đoạn khoá `write` trong dispatcher; bỏ lịch `quotaWatch`; `backoffice usage` đổi từ thanh ngưỡng sang chi phí đã tiêu + lần chạm trần thật | Admin chỉ ra con số không bám thực tế. Đo 2026-08-16: `claude -p --output-format json` KHÔNG trả về hạn mức còn lại và CLI không có lệnh `usage` — nên mọi ngưỡng chỉ là quy đổi từ bảng giá token, hệ tự bịa. Tệ hơn, nó chặn NGƯỢC: chỉ khoá `write` (ghi chi tiêu, ví, việc vặt — tốn $0 LLM vì company là code cứng), trong khi thứ thật sự đốt hạn mức đều là `read` (`nghienCuu` $3,50 · `auditSite` $2,00) và không hề bị chặn. Vô dụng với thứ cần chặn, gây hại với thứ không cần. Hết hạn mức thì CEO tự dừng vì không gọi được model, nên không cần ai khoá hộ |
| 2026-08-17 | **Thêm L8 — tiền THẬT ra ngoài phải khai `paidApi`, hỏi duyệt mỗi lần, có trần tháng**. Dispatcher ép duyệt kể cả `riskTier: read` và cấm whitelist; sổ `chiTieuNgoai` tách khỏi `taskLog.costUsd`; trần 100.000đ/tháng ở `registry/gateway.yaml`; `codemap --check` bắt company cầm khoá dịch vụ tính tiền mà quên khai. Kèm: `notionClient` thử lại 1 lần khi lỗi đường truyền (không thử lại với 4xx), và scheduler chỉ nhắn LẦN ĐẦU của một sự cố kéo dài rồi báo khi khỏi | Admin bị Google AI Studio trừ 144.000đ mà không thu được sản phẩm ưng ý. Khoản đó tiêu ngoài hệ, nhưng chỉ ra đúng lỗ sắp mở khi videoCompany vào repo: company dùng Gemini/Veo mà quên khai sẽ tiêu tiền thật trong im lặng. Đây mới là chỗ cầu dao có nghĩa — khác hạn mức Pro (dùng hết thì thôi, không đo được), tiền thật đo được từng lời gọi và có hoá đơn. Phần calendar: đo 3 ngày thấy 21 lần hỏng nằm gọn trong chùm 6 tiếng đêm 15/08, mỗi lần đúng 8.206ms tức chờ hết timeout — thử lại không cứu được chùm dài, nhưng cứu được lần chập lẻ; và 21 tin lỗi giống hệt nhau chỉ không tới tay admin vì Telegram đứt cùng lúc, tức là một lần đánh thức 21 lần lúc nửa đêm đang chờ sẵn |
| 2026-08-11 | Bộ nghe đổi mặc định từ `base` sang **`medium`**; bức tranh thêm dòng **"Bây giờ: HH:MM thứ … dd/mm/yyyy"** | Admin gửi tin thoại hỏi "bây giờ là mấy giờ", CEO đi tự giới thiệu "Em là CEO…" — vì `base` nghe thành "Mày là mấy á". Đo trên hai tin thoại THẬT: base 2,5s sai hẳn · small 4,5s gần đúng · medium 12,7s **đúng nguyên câu**. Nghe nhầm một con số khi ghi tiền thì sai sổ, nên 10 giây chờ thêm rẻ hơn nhiều. **Đã thử `large-v3` (~3GB) và bỏ**: to hơn không đúng hơn — nó nghe "bò húc" thành "bò hút" trong khi medium đúng, và chậm hơn ~1,5 lần. Đừng nâng cỡ nữa nếu chưa đo lại bằng file thật. Và kể cả nghe đúng, CEO vẫn không trả lời được vì **model không có đồng hồ** — không biết giờ thì không hẹn lịch, không nói được "còn hai tiếng nữa", không phân biệt "hôm nay" với "hôm qua" |
| 2026-08-10 | Đọc ảnh: đưa **đường dẫn TUYỆT ĐỐI** cho tiến trình xem ảnh, và viết lại `ceo/settings-media.json` bằng đường tuyệt đối | Bản cũ cố ý dùng đường tương đối cho khớp luật `Read(backOffice/media/**)`. Hỏng thật: `/home/tsix` cũng có `.claude/` và `CLAUDE.md`, nên model có lúc lấy chỗ đó làm gốc rồi đọc `/home/tsix/backOffice/media/…` — sai chỗ, bị chặn, admin nhận về "em không đọc được ảnh này". Đo được 20:17 ngày 10/08 khi admin gửi ảnh Payoneer; tái hiện được 100% bằng đường tuyệt đối đưa vào bản cũ. Sau khi sửa: đọc đúng 3/3 lần. **Đường tương đối là thứ mơ hồ khi có nhiều gốc dự án lồng nhau** |
| 2026-08-10 | **Siết hộp cát `seoCompany`**: cấm đọc `~/panharmon/**`, `workspaces/**`, mọi company khác, mọi `.env`/`*.pem`/`*.key`, và 11 thư mục dự án anh em trong `~` | Đo được chuỗi tấn công HOÀN CHỈNH: seoCompany là company duy nhất đọc web tự do (cửa prompt injection), và nó **đọc được `~/panharmon/.env.local`** — file chứa `SUPABASE_SERVICE_ROLE_KEY`, `RESEND_API_KEY`, `ANTHROPIC_API_KEY` — rồi **WebFetch tới tên miền bất kỳ** để gửi đi. Danh sách cấm cũ chỉ kể tên 3 company trong companySpec. Cũng đo được: luật cấm `Read(...)` CÓ lan sang lệnh `Bash` (`cat ops/.env` bị chặn), nhưng cấm rộng `Read(//home/tsix/**)` thì **đè cả phần allow**, nên buộc phải kể tên từng chỗ — và mỗi dự án/company mới PHẢI thêm vào |
| 2026-08-10 | Nội dung tin nhắn đi qua **stdin** thay vì làm tham số của `claude -p`; và `run_ceo` **tự mở phiên mới** khi CLI báo `No conversation found` | Admin nhắn `-200k khoản này…` → `error: unknown option '-200k khoản này…'`: dấu `-` đầu câu biến tin nhắn thành tên tuỳ chọn. Nói chuyện tiền mà gõ số âm là bình thường. Dùng dấu `--` không cứu được vì nó biến mọi cờ phía sau thành nội dung. Lỗi này còn đẻ ra lỗi thứ hai: lượt hỏng không tạo được phiên nhưng luồng vẫn trỏ vào mã phiên đó, nên **mọi tin nhắn sau đều chết** — một lỗi tạm biến thành lỗi vĩnh viễn |
| 2026-08-09 | Bức tranh **quá hạn thì bị xoá số dư ví** trước khi đưa cho CEO (`bo_so_du`) | Dặn "phải gọi getBalance" không đủ: lời dặn chỉ có tác dụng khi bản dặn đã nằm trong cache, và con số vẫn nằm ngay cạnh để model đọc. Cắn hai lần trong một buổi — 06:24 đáp số của 70 phút trước, 06:50 đáp số đã bị hoàn tác — cả hai lần đều trả lời trong 5 giây, tức đọc thẳng bức tranh. Không đưa số ra thì không có gì để đọc nhầm |
| 2026-08-09 | Dòng ví trong bức tranh ghi rõ **"ảnh chụp HH:MM, CÓ THỂ ĐÃ CŨ"** kèm lệnh bắt buộc gọi `getBalance` khi admin hỏi số dư | Bức tranh cache 10 phút và khi quá hạn vẫn trả bản cũ ngay. Với câu hỏi kèm việc ghi thì vô hại — CEO nhận số dư mới trong kết quả ghi. Nhưng câu THUẦN ĐỌC thì không gì buộc nó đi hỏi ví. Đo được 06:24 ngày 09/08: admin nhắn "Anh còn bao tiền", CEO đáp "28.000đ / 282.766đ" — số của 70 phút trước — mà **không gọi getBalance lần nào**; số thật là 50.000đ / 237.766đ. Sau khi vá: CEO gọi getBalance rồi mới trả lời, ra đúng số |
| 2026-08-08 | `walletCompany.adjustBalance`: **`soTien` thành ĐỘ LỚN luôn dương**, `loai` là nguồn duy nhất quyết chiều; `điều chỉnh` tách thành `tăng`/`giảm`. Bỏ hàm kiểm dấu | Chốt kiểm dấu (06/08) bắt được lỗi thật **ba lần** — 228.000đ, 70.000đ, 45.000đ — nhưng cả ba lần CEO đều gửi số dương kèm `loai: chi`. Hợp đồng bắt khai chiều tiền hai lần (bằng dấu và bằng `loai`) nên nó mời gọi đúng một kiểu sai; chốt chỉ thu phí một lượt gọi lại chứ không chữa. Bỏ dấu đi thì không còn cách nào diễn đạt sai. Đo: gửi `+11.000` kèm `chi` → ví trừ đúng |
| 2026-08-08 | Danh mục trong prompt CEO **kèm giá trị enum** cho trường bắt buộc (+457 token, tổng 1.201) | Sau khi thống nhất tên trường, 4/4 lần bị từ chối ngày 08/08 đều là sai **giá trị** enum (`loai`, `danhMuc`, `vi`) — biết tên mà không biết giá trị thì vẫn trượt. Đo sau khi thêm: lời gọi ghi chi tiêu ra `danhMuc: đi lại` đúng ngay lần đầu, không lần từ chối nào |
| 2026-08-08 | `session.nap_env()` — đọc `ops/.env` mỗi lần xử lý tin nhắn; `handle_callback` mở phiên MỚI khi phiếu duyệt không có `sessionId`; `create_request` kéo phiếu gộp sang phiên đang hỏi; `/duyet` quét bỏ phiếu quá hạn | Bốn lỗi hạ tầng lộ ra trong một buổi dùng thật: (1) systemd chỉ đọc `.env` lúc khởi động nên biến thêm sau không bao giờ tới nơi; (2) phiếu sinh ngoài luồng trò chuyện làm gateway văng traceback ngay khi admin bấm nút; (3) bản vá gộp phiếu làm **mất nút bấm** vì phiếu vẫn mang phiên cũ; (4) phiếu `pending` không tự hết hạn nên `/duyet` mời bấm cả phiếu đã chết. Cả bốn chỉ hiện ra ở đường thật từ Telegram, không phép thử nội bộ nào bắt được |
| 2026-08-07 | **Thống nhất tên trường ĐẦU VÀO sang tiếng Việt** trên toàn bộ company: `amount→soTien`, `category→danhMuc`, `note→ghiChu`, `date→ngay`, `from→tuNgay`, `to→denNgay`, `limit→gioiHan`, `content→noiDung`, `theme→chuDe`. Giữ nguyên thuật ngữ kỹ thuật (`url`, `slug`, `postId`, `stt`, `*Id`) và **giữ nguyên outputSchema** | Nhét danh mục vào prompt chỉ chữa triệu chứng; bệnh là một khái niệm có nhiều tên. Chỉ đổi ĐẦU VÀO vì C2.3 chỉ phát sinh từ đầu vào, còn đầu ra đang được scheduler và báo cáo sáng đọc — đổi là mở rộng vùng rủi ro vô ích. 4 rule whitelist được viết lại khoá nên admin **không mất quyền nào**. Đo sau khi đổi: 18/18 năng lực `read` chạy, tên cũ bị từ chối đúng, CEO trả lời câu thu-chi trong **3 lượt** |
| 2026-08-07 | **Nhét danh mục company vào prompt CEO** (`session.danh_muc_block`, ~730 token) và cho `C2.1` liệt kê company đang có | 07/08 có 16 lời gọi bị từ chối, **13 là C2.3 sai tên trường**. Gốc rễ: hợp đồng không nhất quán — "số tiền" là `amount` ở expense/income/savings, `soTien` ở wallet, `hanMuc` ở budget; "loại" có đủ `category`/`nguon`/`danhMuc`/`loai`; incomeCompany trộn `amount` với `nguon` trong cùng lời gọi. Trước đó CEO còn đoán tên company (wordpress/content/dream/blog) vì C2.1 không gợi ý gì → chạm trần lượt, chết giữa chừng. Đo sau khi sửa: cùng một câu hỏi, 13 lượt + chết → **2 lượt, không lỗi** |
| 2026-08-06 | `session._ly_do_chet` đọc lỗi từ **stdout JSON** thay vì `proc.stderr`, và có nhánh riêng cho `stop_reason: tool_use` | Với `--output-format json`, CLI ghi lỗi vào stdout còn stderr rỗng, nên mọi lần CEO chết admin chỉ nhận "mã 1" trống trơn (OAuth hết hạn sáng 06/08 mất cả buổi mới lần ra). Riêng ca chạm trần `--max-turns` thì JSON không có trường `result`, đổ nguyên khối JSON ra Telegram |
| 2026-08-04 | `isolation_level=None` (tự commit) trong `lib/db.py`. Thêm **C3.5** | WAL vẫn chưa đủ: dispatcher tự khoá chính nó vì `sweep_orphans()` quên commit khi không có gì để dọn. Không phải tranh chấp giữa hai bên — một tiến trình tự chặn mình |
| 2026-08-04 | Thêm `lib/db.py` — mở SQLite bằng WAL + busy_timeout 15s, thay 11 chỗ gọi `sqlite3.connect` thẳng. Thêm **C3.4** | Sau khi khởi động máy, admin nhắn 3 tin liên tiếp trùng lúc scheduler chạy → `database is locked`, bot không ghi được chi tiêu. Chế độ mặc định của SQLite khoá cả file khi ghi |
| 2026-08-03 | **Sửa P1** từ "n8n giữ khung" thành "code cứng giữ khung". Gỡ n8n hoàn toàn: xoá container, volume, và 559 dòng code chết (`serve.py`, `ask.py`, `n8n.sh`, `docker-compose.yml`, workflow JSON). Viết lại F1, C2.4, T2, §11b, `ops/SETUP.md` | n8n chạy hai ngày mà không xử lý một tin nhắn nào: Telegram phải polling (không có IP công khai), lịch dùng systemd timer, dispatcher là tiến trình Python. **Gọi tên một công cụ trong nguyên tắc gốc là sai lầm ngay từ đầu** — công cụ thay được, nguyên lý thì không (E3) |
| 2026-08-03 | Dọn: xoá `notesCompany` (W4 — đã thừa từ khi có `journalCompany`), xoá `.venv` 36M của seoCompany, hiệu chuẩn sơ bộ ngưỡng L7 xuống 5,0 (5 tiếng) và 30,0 (tuần) | `notesCompany` từng là đồ thử, nhưng giữ một company đa dụng là cách chắc nhất để phá C4 (xem C5.3). Ngưỡng cũ 12/70 là đoán mò; neo lại theo việc đắt nhất — một auditPage = 0,72 |
| 2026-08-03 | **Lát 4 — `scheduledTrigger`.** `registry/schedules.yaml` (3 lịch), `core/events/scheduler.py`, systemd timer 15 phút. **S3 kiểm ở dispatcher chứ không tin file lịch.** Tách `gateway/telegram/telegram.py` thành đường ra duy nhất (T1) | Cron chạy lúc admin ngủ, nên mọi guardrail dựa trên "hỏi admin" mất tác dụng. Bù bằng cách thu hẹp cửa: chỉ đọc, chỉ lịch khai trước, mặc định không LLM |
| 2026-08-03 | Thêm **S7**: `quietIfEmpty` — cảnh báo định kỳ chỉ nhắn khi có chuyện | Cảnh báo nhắn suốt thì admin ngừng đọc, và lúc có chuyện thật cũng bỏ qua |
| 2026-08-03 | **Lát 3.** backOffice báo cáo (`usage`/`report`/`whitelist`/`check`), cầu dao **L7** trong dispatcher, 5 lệnh Telegram chạy bằng code cứng. `KillMode=process` để restart không giết việc đang chạy. Dispatcher tự dọn bản ghi kẹt `running` | Sau `seoCompany` thì hạn mức thành rủi ro thật: một `auditPage` = 0,72, bằng ~50 lần ghi chi tiêu |
| 2026-08-03 | Thêm **O7**: lệnh tra cứu phải chạy được khi hạn mức đã cạn | Hỏi "còn bao nhiêu hạn mức" mà phải tốn hạn mức để biết thì là thiết kế sai |
| 2026-08-03 | **`seoCompany`** hoàn thiện — company đầu tiên `runtime: skill`, chạy cả một phiên Claude Code riêng bên trong. Thêm **B8**. Dispatcher lấy hạn chót từ `maxDurationSec` của manifest thay vì hằng số; `runtime` thành nhãn chính sách, không còn là nhánh rẽ | RP3 có lý do thật: skill SEO cần WebFetch/WebSearch/Task — tool mà CEO tuyệt đối không được có. Cách ly tiến trình là cách duy nhất giữ ranh giới |
| 2026-08-03 | **`planCompany`** — company đầu tiên SỬA bản ghi đã có. Thêm **D5** (`previousValue` bắt buộc khi ghi đè) và **D6** (không tìm thấy thì báo, đừng tạo mới). Nâng cột `Trạng thái` của bảng 100 video từ checkbox lên 5 bước; sửa 6 dòng lẫn cột | Thêm mới sai thì thừa một dòng; ghi đè sai thì mất giá trị cũ vĩnh viễn. Hai loại rủi ro khác hẳn nhau |
| 2026-08-03 | Thêm **C5** (hai company không được cùng trả lời một câu) và cờ `internal: true`. Ẩn `notesCompany` khỏi CEO, thu hồi 2 luật whitelist rác | Lần chạy thật đầu tiên của journal: CEO đẩy "ghi nhật ký" vào `notesCompany.addNote` với thẻ ["nhật ký"] thay vì gọi `journalCompany`. Mô tả chồng lấn thì model sẽ đoán, và đoán sai |
| 2026-08-03 | **`journalCompany`** — company thứ hai dùng Notion. Thêm thân trang + cắt block vào `notionClient` (nội dung dài không nhét vừa property 2000 ký tự). Gộp `setup-notion.py` thành một điểm cắm cho mọi sổ | C4 chứng minh được: thêm company mới không đụng CEO, không đụng dispatcher — chỉ một manifest và một entrypoint |
| 2026-08-03 | Mở rộng **G5**: mọi câu nói với admin phải nói hậu quả, không riêng câu hỏi duyệt. Viết lại thông báo whitelist bằng lời thường | Câu "tối đa 20/ngày, hết hạn 2026-10-31 (G7)" bị hiểu thành dữ liệu sẽ bị xoá. Mã nguyên tắc là để lập trình viên đọc, không phải để admin đọc |
| 2026-08-03 | Thêm **C2.5** (từ vựng đóng bằng `enum`) và **C2.6** (`list` trả kèm giá trị hợp lệ). Đổi `category` thành enum 8 giá trị; thu hồi luật whitelist rác | Lần chạy thật đầu tiên CEO tự đặt danh mục "Cà phê" → whitelist vô dụng, `listExpenses` tìm "ăn uống" không ra khoản vừa ghi. Schema phải chặn, không phải dặn trong prompt |
| 2026-08-02 | **`expenseCompany`** — company thật đầu tiên. Notion làm bộ nhớ thứ hai. Thêm `lib/notionClient.py` dùng chung (C4.1) | Ranh giới theo công việc: `journalCompany`, `docsCompany` sau này cũng dùng Notion nhưng là company riêng |
| 2026-08-02 | Siết **C2.4** trong dispatcher: company chỉ nhận đúng secret nó khai trong manifest, không nhận cả `os.environ` | Trước đó `notesCompany` cũng đọc được `NOTION_TOKEN`. "Mỗi company một phạm vi" chỉ là lời nói nếu không cắt biến môi trường |
| 2026-08-02 | Thêm **C4**: ranh giới company là công việc, không phải công cụ. Company dùng chung thư viện được, dùng chung dữ liệu thì không | Admin muốn Notion làm bộ nhớ thứ hai cho 5 việc khác nhau. Gộp thành một `notionCompany` sẽ phá chính nguyên tắc "mỗi company một nhiệm vụ" |
| 2026-08-02 | Thêm **B7** (không thừa hưởng ngầm — mặc định rỗng) và `--tools Bash` | Sau khi cắt MCP vẫn thấy CEO cầm `CronCreate`, `TaskCreate`, `SendMessage`, `Artifact`, `Read`, `Skill`. `--allowedTools` chỉ chặn quyền chạy, không gỡ định nghĩa tool. `CronCreate` vi phạm thẳng luật 13. Nay CEO có đúng 1 tool |
| 2026-08-02 | Thêm **B6**: CEO phải chạy kín — `--strict-mcp-config` + `--setting-sources project` + ghim model. Token phiên nguội 14.247 → 3.705 | Phát hiện CEO đang cầm sẵn tool Gmail/Drive/Calendar/Notion của gói Pro, gửi email được mà không qua dispatcher. Lỗ thủng guardrail nghiêm trọng |
| 2026-08-02 | Bỏ n8n khỏi đường Telegram, thay bằng long polling (`gateway/telegram/poller.py`) | Telegram webhook cần URL công khai HTTPS; máy nằm sau NAT. n8n giữ lại cho `scheduledTrigger` — loại chạy từ trong ra, không cần ai gọi vào |
| 2026-08-02 | **Lát 2 chạy được.** adminGateway (R1–R4), kho phê duyệt hai đồng hồ (G11), nút Telegram, whitelist học dần có scope + hạn dùng, n8n riêng của dự án, ống dẫn HTTP host↔container. Đã xác minh: chatId lạ bị bỏ qua, whitelist cùng scope tự chạy / khác scope vẫn hỏi, token đổi nội dung bị chặn, token dùng lại lần 2 bị chặn | Lát cắt dọc thứ hai — guardrail đầy đủ |
| 2026-08-02 | Thêm **G12**: scope của whitelist do CHÍNH COMPANY khai báo (`whitelistScope`), không khai thì không whitelist được | Lúc dựng mới thấy: nếu dispatcher tự đoán scope thì hoặc quá rộng (nguy hiểm) hoặc quá hẹp (vô dụng). Company biết dữ liệu của nó nhất |
| 2026-08-02 | Thêm **F5** (không tái sử dụng gì của dự án cũ) và **F6** (định danh cá nhân không nằm trong repo) | Lúc bắt đầu Lát 2 đã lỡ nạp token + chatId của dự án cũ vào `registry/gateway.yaml`. Admin bắt được. Đã gỡ. Viết thành luật để không tái diễn |
| 2026-08-02 | **Lát 1 chạy được đầu-đến-cuối.** dispatcher + guard hook + notesCompany + adminGateway local. Đã xác minh bằng chạy thật: C2.1/C2.2/C2.3 chặn đúng, G4 chống sửa nội dung sau khi duyệt, L4 chặn lặp, W2 dryRun, D3 ghi sideEffect. Thêm README.md | Lát cắt dọc mỏng nhất, chưa Telegram/n8n |
| 2026-08-02 | Sửa lỗ hổng quan sát phát hiện lúc chạy thật: `needsApproval` và các lời gọi bị từ chối trước đây **không được ghi log** → vi phạm O6. Nay mọi lời gọi đều để lại dấu; L4 đổi sang chỉ đếm lần **thật sự chạy** (nếu tính cả lần hỏi duyệt thì luồng "hỏi rồi duyệt" bị chặn oan) | O5/O6 — không có việc gì không thuộc về một trace |
| 2026-08-02 | Nới C2.3: schema được viết thẳng trong `companySpec.yaml` khi ngắn; cập nhật §8 cho khớp cấu trúc thật (`ceo/SYSTEM.md`, `gateway/cli/dispatch.py`, `ops/ask.py`) | Thực tế khác bản phác thảo — sửa hiến pháp trước (E1) |
| 2026-08-02 | Chốt nốt Q3/Q8/Q10/Q13 (§12c cho `scheduledTrigger`); thêm §0 Phạm vi (sản phẩm của admin không nối vào) và E1–E4 (file này sẽ thay đổi, cách xử lý); thêm luật 11–13 vào §11 | Hết câu chặn — bắt đầu Lát 1 |
| 2026-08-02 | **Đo Q14** → thêm §12b: A đắt gấp 3,9 lần B từ lời gọi thứ hai. Chốt `runtimePolicy` (RP1/RP2/RP3), viết lại T2 (dispatcher có hai hiện thực), chốt luôn Q4 và Q7 | Giả định "gọi company là rẻ" sai với runtime skill/agent nếu sinh tiến trình riêng |
| 2026-08-02 | Rà soát nhất quán: sửa mâu thuẫn CEO "trong container" (§2) vs chốt Q1 chạy host; chốt Q6 (thư mục = companyId); thêm G11 (tách TTL yêu cầu duyệt / TTL token); sửa vài số liệu sai; **thêm Q14 — câu hỏi chặn về giá của một lời gọi company** | Đọc lại toàn file trước khi bắt đầu code |
| 2026-08-02 | Thêm mục tiêu kinh tế vào §0 (dùng hết gói Pro, không phải tiết kiệm tiền); bỏ ollama khỏi `sessionPolicy`, thay bằng 4 luật cứng dựa trên `reply_to_message` của Telegram; L7 đổi từ "cầu dao chi phí" thành "cầu dao hạn mức"; thực hiện Q11 (dọn 31 skill + 18 agent SEO về `seoCompany`) | Máy không chạy được LLM local; ràng buộc "chỉ có gói Pro" ép P1 thành hiện thực |
| 2026-08-18 | Trí nhớ qua phiên (`dong_phien`/`threadSummary`); tách `SYSTEM.md` thành lõi + `ceo/playbooks/` với router code cứng; ca thử nhiều lượt và soát câu chữ; `backoffice trace`; `codemap` soi cả ca nhiều lượt | Lấp ba khoảng trống HARNESS.md §3 mà không nới deny list của CEO — việc chọn sổ tay nằm NGOÀI model nên không phải mở tool `Skill`. Đo trên 143 câu admin thật: 0 lần trượt sổ "tiền" |
| 2026-08-21 | **Hồ sơ admin có HẠN DÙNG.** Thêm nhóm `trạng thái` + trường `hetHan` cho `profileCompany`; gateway lọc dòng quá hạn khi nạp vào prompt (không sửa file — dọn dẹp là việc của company). Bộ soát schema của dispatcher nay hiểu `pattern` — trước đó nó lặng lẽ bỏ qua, tức là một luật khai trong manifest trông như đang được canh mà thật ra không. Danh mục company in cả **trường tuỳ chọn** sau dấu `+` (+796 ký tự) | Đo trên lượt thật 21/08 00:50: admin nhờ viết một câu về trạng thái yêu của mình, CEO đáp "không có thông tin trong hồ sơ" — và đáp ĐÚNG, vì hồ sơ chỉ nhận "điều LUÔN đúng" nên không có ngăn nào cất một hoàn cảnh đang diễn ra. Trí nhớ có bốn lớp và cả bốn đều bỏ rơi loại này: phiên chết sau 30 phút (90/453 lượt), 10 tin gần nhất bị mấy lượt ghi chi đẩy trôi, tóm tắt phiên **cố ý** chỉ kể việc ĐÃ LÀM, còn PROFILE.md thì chỉ nhận điều vĩnh viễn. Nhưng nhớ mà không hẹn ngày rụng còn tệ hơn: hồ sơ nạp vào MỌI lượt và không tự hết hạn, nên một câu cũ ba tháng vẫn được đọc như đang đúng — cùng lý lẽ với TOM_TAT_GIO. Trường tuỳ chọn thì do chính ca thử mới bắt được: CEO chọn đúng nhóm, đúng ngày, rồi nhét ngày vào `noiDung` vì danh mục chưa bao giờ cho nó thấy `hetHan` là một trường — cùng gốc với việc `ghiChu` bỏ trống ở 4 khoản chi mà admin phàn nàn hôm 20/08 |
| 2026-08-24 | **`ngoaiNguCompany`** — sổ câu ngoại ngữ admin tự thêm ngay trong lúc chat (`themCau`/`dsCau`/`danhDauThuoc`/`xoaCau`), nguồn sự thật là `CAU-CUA-TOI.yaml` người đọc được. Tin học 05:30 và bốn lần nhắc trong ngày gửi kèm 4 câu tự thêm, xoay vòng theo ngày trong năm. Sổ tay `ceo/playbooks/ngoai-ngu.md` + từ khoá router; trang giáo trình dựng kèm câu tự thêm để có nút NGHE. Hai ca thử mới | Giáo trình 12 bài là thứ SOẠN TRƯỚC nên nó đoán việc admin làm hằng ngày — admin nói thẳng "có vài câu anh không xài nhiều". Câu admin cần thật lại đến vào lúc gặp khách, tức là lúc đang cầm điện thoại chứ không phải lúc ngồi sửa file YAML, và trước hôm nay không có cửa nào để nhét nó vào. Xoay vòng theo NGÀY chứ không theo một cột "đã ôn": cron chỉ được ĐỌC (S3) nên trí nhớ giữa các lần gửi không thể nằm trong sổ — cửa sổ trượt giải đúng bài toán đó mà không cần nhớ gì |
| 2026-08-25 | **Hai bản vá số liệu tiền.** (1) Bộ lọc ngày neo vào `+07:00` ở `expenseCompany`, `incomeCompany`, `calendarCompany`, `journalCompany` — trước đó Notion đếm ngày theo UTC nên khoản ghi từ 00:00–07:00 giờ VN rơi sang hôm trước. (2) `notionClient.query_database` biết phân trang (`fetch_all`), `sumExpenses`/`sumIncomes` dùng nó; trần vòng lặp neo vào `maxDurationSec`, chạm trần thì ném lỗi chứ không trả phần đã lấy. Thêm luật ĐỢI KẾT QUẢ vào `ceo/playbooks/tien.md` | Admin nhờ xoá một khoản chi ghi nhầm, bấm duyệt HAI lần, cả hai lần đều bị từ chối: danh sách trả về khoản đó ở ngày 24 (lọc theo UTC) còn phép đối chiếu lúc xoá đọc ra ngày 25 (giờ VN), và tra ngày 25 thì RỖNG — không có đường nào chạm tới khoản đó ở đúng ngày của nó. Lần lại thì thấy con thứ hai nằm sẵn cạnh đó: tổng tháng cộng trên 100 dòng đầu, tháng 8 có 110 khoản nên hụt 363.000đ và hụt lớn dần về cuối tháng. Cả hai đều sai theo hướng TRẤN AN — báo tiêu ít hơn thật — nên không ai đi tìm chúng; chúng chỉ lộ ra vì một khoản không xoá được. Con thứ ba lộ ra lúc sửa xong: CEO hoàn ví TRƯỚC khi biết lệnh xoá có chạy không, làm hai lượt hai kiểu mà lượt nào cũng báo xong |
| 2026-08-27 | **CEO không còn treo vào một bộ não duy nhất.** `registry/models.yaml` (danh sách nhà + chuỗi thử, chỉ chứa TÊN biến môi trường), `lib/llmClient.py` (client OpenAI-compatible thuần stdlib, nhiều nhà một hàm), `brains/fallback.py` — ba chế độ `claude` / `tu` / `phu`, đổi được ngay từ Telegram bằng `/nao`. Não phụ có ĐÚNG MỘT công cụ `goiCompany`, argv dựng bằng tay nên không qua shell — hẹp hơn hẳn Claude CLI vốn phải rào tool Bash bằng deny-list; T2 giữ nguyên, vẫn đúng một cổng `dispatch.py`. `ceoRunLog` thêm cột `nao` và `tienVnd`. Kèm **`hoiDongCompany.hoiY`** — hỏi nhiều model KHÁC NHÀ cùng một câu, tuỳ chọn thêm một vòng cho họ đọc ý nhau rồi sửa ý mình, chủ toạ đọc bản GIẤU TÊN rồi chốt, và luôn trả về chỗ BẤT ĐỒNG. Và `tests/evals/nao_thu.py` — một bộ ca chạy trên một nhà cung cấp GIẢ tại localhost: không tốn tiền, không cần mạng, không cần khoá | Admin đặt hai yêu cầu, cả hai đều đúng chỗ đau. (1) Hết hạn mức gói Pro là cả hệ CÂM — mọi company vẫn chạy tốt vì chúng là code cứng, nhưng không ai gọi được chúng vì người gọi đã chết; một trợ lý sống nhờ hạn mức của một nhà thì nó không phải của admin. Chưa kể thiếu lệnh `claude` trên máy thì `subprocess.run` ném `FileNotFoundError` KHÔNG AI BẮT và làm sập cả gateway — cùng họ với vụ `TimeoutExpired` ngày 19/08, O8 lại thủng thêm một lỗ. (2) Một model trả lời câu hỏi có đánh đổi thì bao giờ cũng trôi chảy và tự tin, kể cả khi bỏ quên nguyên một mặt — mà cái nó bỏ quên thì chính nó không thấy, hỏi lại lần nữa vẫn đi đúng lối cũ. Model khác nhà trượt ở chỗ khác; chỗ hai bên trượt khác nhau mới là thứ đáng đọc, nên hội đồng phải kể ra bất đồng chứ không làm mượt cho hoà cả làng. Ý tưởng gom nhiều nhà sau một giao diện lấy từ ProxyGateLLM, nhưng KHÔNG lấy mã: bản của họ là một server Node chạy thường trực — thêm một tiến trình để hỏng, thêm một cổng mở, thêm một chỗ giữ khoá — trong khi phần thật sự cần chỉ là mấy chục dòng HTTP, vì hàng chục nhà đều nói chung một giao thức. **CHƯA ĐO CHẤT LƯỢNG:** bộ ca thử chỉ chứng minh KHUNG XƯƠNG đúng (gọi tool → chạy dispatcher → nhét kết quả ngược lại, nhà hỏng thì nhảy nhà, hết lượt thì nói thật là chưa xong, vắng người thì nói ra là vắng). Não phụ làm được việc tới đâu so với Claude thì phải chạy `tests/evals/run.py` ở chế độ `phu` mới biết, và tới lúc viết dòng này máy chưa có khoá miễn phí nào nên chưa chạy được. Chuyển não CỐ Ý chỉ xảy ra khi Claude hỏng theo kiểu CHẮC CHẮN CHƯA LÀM GÌ — thiếu lệnh, hết hạn mức, hết phiên đăng nhập; treo hay chạm trần lượt thì KHÔNG chuyển, vì lúc đó việc có thể đã làm một nửa và cho bộ não khác chạy lại là ghi hai lần vào sổ của admin |
| 2026-08-27 | **Claude ngồi ghế chủ toạ hội đồng.** `lib/llmClient.py` có thêm đường truyền `kieu: cli` — gọi `claude -p` với `--tools ''` (không nạp tool nào) rồi đọc JSON, vì Anthropic KHÔNG phát khoá API cho gói thuê bao: thứ admin trả tiền là lệnh đã đăng nhập sẵn trên máy. Nhờ vậy `costUsd` (hạn mức Pro) và `tienVnd` (tiền trừ thẻ) đi hai đường riêng suốt từ client lên tới `usage` của company. Ghế chủ toạ có **người dự bị** (`hoiDong.chuToaDuPhong`): Pro cạn thì một model miễn phí chốt thay và câu kết luận NÓI RA là đã thay người; không ai chốt được thì vẫn đưa nguyên các ý kiến cho CEO. Thêm `chuToa` vào outputSchema, thêm `companies/hoiDongCompany/settings.json` (deny sạch làm lớp thứ hai). Thành viên mở rộng sang openrouter + mistral để hội đồng có nhiều họ model khác nhau | Admin muốn "claude làm chủ và các model kia phụ để thảo luận và chốt phương án hay nhất". Xếp Claude làm chủ toạ chứ KHÔNG cho bàn cùng, vì thứ cần ở nó không phải thêm một ý kiến nữa mà là khả năng đọc mấy ý kiến trái nhau rồi tách ra chỗ nào thật sự khác nhau — cho nó bàn cùng thì bản của nó nằm trong đống nó chấm, và nó sẽ chấm bản của nó cao. Chủ toạ vẫn đọc bản GIẤU TÊN, kể cả khi có bản của họ nhà Claude trong đó. Đo thật 27/08 với hai ý kiến trái chiều về SQLite/Postgres: Claude chốt SQLite và bắt đúng chỗ đáng bắt — một thành viên tự nhận "không chắc về chi phí vận hành", nó lấy chính câu đó làm lý do hạ trọng số ý kiến ấy. Giá: **$0,0815 một lần chốt**, trong đó ~11.790 token là prompt nền của chính CLI chứ không phải câu ta hỏi — nên `fallback.py kiem` CỐ Ý không hỏi thử nhà `cli` (phải thêm `--ca-claude`): một lệnh kiểm tra cho yên tâm mà đắt hơn việc thật thì admin sẽ thôi chạy nó |
| 2026-08-27 | **Cắt được phạm vi dữ liệu gửi ra nhà ngoài.** `fallback.riengTu` ba mức — `dayDu` / `canTrong` (mặc định) / `toiThieu`; `brief` tách khỏi `them` trong `run_ceo` để cắt được theo KHỐI chứ không phải dò chuỗi con; `_bao_da_cat()` nói thẳng với model là khối nào đã bị cắt; `brains/fallback.py xem-goi` in ra đúng gói tin SẼ gửi mà không gửi; ba ca thử bắt tận gói tin để canh lời hứa đó. Kèm một bản vá: `profile_block` gỡ khối `<!-- -->` trước khi đọc dòng | Admin hỏi "dùng API của model phụ có rò rỉ thông tin không". Câu đó chỉ trả lời tử tế được bằng cách MỞ GÓI TIN RA XEM — trả lời bằng lời hứa là loại câu nghe rất yên tâm và không kiểm được. Đo thật: một lượt hỏi "tháng này tiêu bao nhiêu" đi ra **37.282 byte**, system prompt **28.443 ký tự**, bên trong có hồ sơ đời tư của admin và số dư từng ví — sang máy một nhà miễn phí mà admin chưa từng đọc điều khoản. Với Claude thì admin đã chấp nhận điều đó khi mua gói; với nhà miễn phí đó là một quyết định KHÁC và không được để mã mặc định giùm. Mặc định `canTrong` vì đúng thứ não phụ sinh ra để làm — ghi chi, tra sổ, đặt lịch — chỉ cần DANH MỤC company; cái mất là CEO phải hỏi lại "ví nào" thay vì tự biết quy ước. Hai thứ lộ ra trong lúc làm: (1) ca thử bắt gói tin cho thấy cắt khối mà không báo thì model đọc SYSTEM.md thấy dặn "cuối prompt có Bức tranh hiện tại", tìm không ra, và sẽ làm đúng cái tệ nhất là bịa một con số nghe hợp lý — nên phải có `_bao_da_cat`; (2) soi prompt thật thì thấy `profile_block` đang nạp cả dòng VÍ DỤ nằm trong khối chú thích của PROFILE.md (`lstrip()` nuốt luôn dòng thụt lề), tức CEO được dạy một "sự thật về admin" vô nghĩa ở mỗi lượt kể từ 21/08 — không sai schema, không gây lỗi, không ai kêu, chỉ lộ ra khi có người mở gói tin ra đọc |
| 2026-08-27 | **Chia lại vai ba bộ não.** Não phụ = **Gemini** (`gemini-3.1-flash-lite` → `gemini-3.5-flash`), bật `chapNhanTraTien` và thêm cầu dao trần tháng NGAY TRONG `fallback.py` (`_con_tra_tien_duoc`, đọc cùng sổ `chiTieuNgoai` mà dispatcher ghi; chạm trần thì tự hạ xuống nhà miễn phí và nói ra, chứ không tiêu lố rồi mới báo). Model phụ miễn phí rút hẳn khỏi chuỗi hằng ngày, chỉ còn ngồi bàn họp. Sổ tay `ceo/playbooks/hoi-dong.md` + router `goi_hop()` bật khi admin gõ "họp"; luật hội đồng rời khỏi danh mục, để lại một câu neo. `llmClient` giữ **nguyên văn** lượt model trả về (`tinGoc`) thay vì dựng lại | Admin chốt: gói Pro gia hạn hằng tháng nhưng có lúc cạn giữa chu kỳ, và lúc đó cần một model **đáng tin** làm việc đơn giản — model local không đủ sức, model miễn phí lúc được lúc không. Model phụ chỉ để **họp**: bàn với nhau rồi Claude chốt. Đo trong lúc làm, bốn thứ đều là loại hỏng-ngầm: (1) `gemini-2.5-flash` và `gemini-2.5-flash-lite` đã bị RÚT (404 "no longer available") còn alias `gemini-flash-latest` trả 503 cả ngày — mà `browserCompany` đang lấy đúng alias đó làm mặc định; (2) Gemini lúc 503 trả thân lỗi dạng **mảng**, làm `_doc_loi` ném AttributeError — bộ đọc lỗi tự vỡ trong lúc đọc lỗi, và lỗi mới đó không phải LLMError nên chuỗi dự phòng không bắt được, không nhảy nhà nào; (3) Gemini 3.x gắn `thought_signature` vào tool_calls và đòi nhận lại y nguyên, nên bản dựng-lại-lượt-model làm não phụ **gọi được company ở lượt 1 rồi chết ở lượt 2** — đúng lúc đã tiêu tiền và đã chạm vào sổ; (4) `fallback.py trang-thai` không nạp `.env` nên báo "thiếu GEMINI_API_KEY" cho một khoá đang có — sai theo hướng doạ, đủ để admin đi tìm một lỗi không tồn tại. Sau khi sửa, chạy thật với PATH không có `claude`: câu "ví anh còn bao nhiêu" → 2 lượt, 3,3 giây, **51,59đ**, số đúng lấy từ Notion. Giá: một lượt ~25đ, một tin nhắn 2–3 lượt nên ~50–75đ; trần 100.000đ ≈ 1.300–2.000 tin, thừa cho vài ngày Pro cạn. Từ khoá "họp" CỐ Ý không khớp chuỗi con: bỏ dấu thì "họp" và "hợp" là một chữ, mà "phù hợp"/"trường hợp"/"hợp đồng" là chữ admin dùng hằng ngày — nạp thừa ở đây nghĩa là mời CEO mở một cuộc họp tốn tiền cho câu admin không hề nhờ |
| 2026-08-27 | **Hội đồng phải có CĂN CỨ, không được suy đoán.** Thêm đầu vào `duKien` (mảng dữ kiện đã tra, tách hẳn khỏi `boiCanh`) và đầu ra `chuaKiemChung`; `LUAT_CAN_CU` bắt mọi khẳng định không nằm trong `duKien` phải mang nhãn `[CHƯA KIỂM]`; vòng 2 đổi từ "đọc ý nhau rồi sửa" thành **soi căn cứ trước, sửa ý sau**; chủ toạ có thêm việc LỌC RÁC và không được nâng một khẳng định thành căn cứ chỉ vì nhiều ý kiến cùng nói. Lớp thứ hai bằng CODE: `_so_khong_nguon()` nêu tên mọi con số xuất hiện trong kết luận mà không truy được về dữ kiện đầu vào; `chuaKiemChung` được nhét vào cả `summary` để CEO không đọc lướt. Sổ tay dạy CEO gọi `searchCompany.traNhanh` TRƯỚC rồi mới họp. Kèm ba bản vá: `browserCompany` bỏ alias `gemini-flash-latest` (503) sang `gemini-3.1-flash-lite`; vòng phản biện chạy SONG SONG (`llmClient.song_song` nhận messages riêng cho từng việc); ghế chủ toạ được cấp 180s riêng và ngân sách chia theo đồng hồ thật | Admin: "cái quan trọng là cần có cái gì đó xác thực thông tin cho chính xác, suy luận phải dựa theo thông tin thật, không được suy đoán vô căn cứ". Đúng chỗ hội đồng dễ hỏng nhất — và hỏng theo kiểu tệ nhất: một model đơn lẻ bịa số thì còn ngờ được, ba model cùng bịa một kiểu thì thành "đồng thuận" và admin sẽ tin. Đo thật 27/08: cho hai thành viên cố tình bịa (90 ngày sandbox, nghiên cứu Tubics 73%, CPM 8 đô, cạnh tranh gấp 40 lần, ngân sách tối thiểu 12 triệu) rồi để Claude ngồi ghế chủ toạ với đúng MỘT dữ kiện thật (kênh có 1000 người theo dõi). Kết quả: bắt đủ 7 khẳng định bịa, mỗi cái kèm câu tra cụ thể, và tự nhận ra rủi ro "nhiều mô hình có thể cùng trích dẫn một nguồn không tồn tại"; kết luận neo vào đúng dữ kiện thật duy nhất và vẫn đứng vững khi bỏ hết phần chưa kiểm. Chi phí: $0,161 hạn mức Pro cho ghế chủ toạ, 0đ tiền thẻ. Hai cái bẫy ngân sách lộ ra trong chính phép đo này: (1) chủ toạ Claude chạy qua CLI phải khởi động cả tiến trình node nên 60s là cắt giữa chừng — cuộc họp rơi xuống ghế dự bị sau khi đã trả tiền cho mọi ý kiến, tức mất đúng thứ đáng giá nhất; (2) vòng phản biện gọi tuần tự nên 4 thành viên × 60s = 240s ăn trọn ngân sách, một lỗi sẽ không lộ ra lúc thử với 2 người mà lộ đúng hôm admin mời đủ 4 người |
| 2026-08-27 | **Mỗi ghế hội đồng một GÓC NHÌN** (`companies/hoiDongCompany/vai.yaml` + đầu vào `vai`). Bốn góc: soi mặt trái (pre-mortem, chi phí không lấy lại được), hỏi tới gốc (bài toán thật là gì, có lựa chọn thứ ba nào không), lo phần chạy được (tuần này làm bước nào, thử nhỏ trước), đòi con số (đại lượng nào chi phối, số nào đang thiếu). Vai giữ nguyên sang vòng phản biện; chủ toạ được biết GHẾ nào nói gì nhưng vẫn không biết NHÀ nào; tên vai lạ thì từ chối chứ không bỏ ghế trống. Thêm sẵn nhà `xai` (Grok) và `openai` (GPT) vào models.yaml, chờ khoá | Admin gửi hai repo skill và hỏi có nên nối vào không. **nuwa-skill** (chưng cất cách nghĩ của một người thành skill) — đọc SKILL.md thì thấy: 6 subagent tra web song song, 5 phase, 30–90 phút, tác giả tự ghi giá "hàng chục đô" mỗi lần chạy tiêu chuẩn, và nó cần WebSearch + Task + Write, ba tool CEO tuyệt đối không được có. Bọc thành company thì nó thành thứ đắt nhất hệ, gấp cả chục lần `researchCompany.nghienCuu` ($3,47) vốn đã bị đánh dấu "KHÔNG BAO GIỜ tự chọn". Nên **lấy ý tưởng, không lấy pipeline**: giữ ba trong năm lớp của nó (khung tư duy, luật ra quyết định, ranh giới) và viết tay thành bốn vai — 0đ, chạy ngay, và không có bước tra web nào để mà bịa. **mattpocock-skills-zh-CN** là skill cho agent LẬP TRÌNH (tdd, code-review, to-spec), không dính gì tới CEO — CEO không viết code; nó thuộc về phiên Claude Code của admin, và bản gốc tiếng Anh hợp hơn bản dịch tiếng Trung với người đọc tiếng Việt. Điểm chung phải nói ra: skill là CHỮ RA LỆNH cho model, nên thêm một repo skill là thêm một người được quyền viết luật vào đầu agent — đọc trước, ghim phiên bản, đừng để tự cập nhật, và đừng cài vào repo này nơi CLAUDE.md/PRINCIPLES.md đang là luật. **KHÔNG ĐÓNG VAI NGƯỜI THẬT**: bảo model "hãy là Munger" thì nó bịa lời Munger rất trôi chảy vì đã đọc hàng nghìn trang về ông — một cái tên thật làm lời bịa nghe đáng tin gấp bội, đúng thứ `chuaKiemChung` vừa dựng lên để chặn. Mỗi vai vì thế là một BỘ CÂU HỎI, không phải một con người. Đo thật 27/08 với CÙNG MỘT model cho cả hai ghế (để khác biệt chỉ có thể đến từ vai): hai bản trả lời rẽ hẳn hai hướng, và chủ toạ Claude bắt được một lỗi thật mà ghế "hỏi tới gốc" nói sai — "1000 người theo dõi là đã vượt rào cản khó nhất" trong khi điều kiện bật kiếm tiền còn cần số giờ xem; nó chỉ luôn chỗ tra (YouTube Studio > Kiếm tiền). Giá: 10,05đ tiền thẻ + $0,147 hạn mức Pro cho cả cuộc họp hai ghế |
| 2026-08-31 | **Dọn chỗ cho skill của dự án, sau khi ĐO xem nó có chạm được vào CEO không.** Thêm `.claude/README.md` (repo trước nay không hề có `.claude/`) ghi rõ ranh giới và luật cài skill; thêm một gạch đầu dòng vào mục "Ranh giới không được vượt" của CLAUDE.md. Mỗi vai hội đồng nay tự khai `ranhGioi` — phần nó KHÔNG lo — và vai.yaml có sẵn ba phép thử để xét một vai mới | Admin muốn cài `mattpocock-skills` làm skill của dự án. Trước khi gật phải trả lời một câu chưa ai hỏi: CEO chạy `--setting-sources project` với cwd là gốc repo, nên `.claude/` của repo NẰM TRONG TẦM ĐỌC của phiên CEO — một đường vào không hiển nhiên, xưa nay vô hại chỉ vì repo chưa từng có thư mục đó. Đo 31/08 trong một workspace cô lập đã bấm tin tưởng (`hasTrustDialogAccepted: true`, vì lần đo đầu ở workspace chưa tin thì CLI tự bỏ qua `permissions.allow` — đo hụt mà trông như đã đo), với `.claude/settings.json` mở toang `allow: [Bash, Read, Write, WebSearch]` và `hooks: {}`: CEO vẫn bị `ceo/hooks/guard.py` chặn khi thử `echo XINCHAO123`, `permission_denials` ghi lại đúng lời gọi đó. Kết luận: **PreToolUse hook trả `deny` thắng `permissions.allow` của project**, nên trình cài skill có lỡ ghi settings vào đó cũng không nới được quyền cho CEO — nhưng đó là kết quả của một phép đo chứ không phải điều đương nhiên, và nó chỉ còn đúng chừng nào hook còn nguyên. Về phần vai: học tiếp từ khung chưng cất của nuwa-skill, lấy phép thử ĐỘC QUYỀN (một vai chỉ đáng có ghế nếu nó nói được điều các vai khác không nói — chỗ hay trượt nhất, vì thêm một vai "người cẩn thận" nghe rất hợp lý mà chỉ là bản nhạt của "soi mặt trái") và lớp RANH GIỚI TỰ KHAI. Ranh giới là thứ bắt buộc chứ không phải trang trí: model được luyện để trả lời cho cân đối, không cấm thì nó tự nói nốt phần của ghế khác và bốn ghế lại thành bốn bản na ná — tức mất sạch lý do chia vai |
| 2026-08-31 | **Hội đồng chạy thật lần đầu.** `llmClient` tự khai `User-Agent`; mọi tên model trong `registry/models.yaml` thay bằng tên hỏi thẳng `/models` của từng nhà; ghế hội đồng xếp lại theo kết quả `fallback.py kiem`; thêm một ghế đỡ cùng nhà để MỘT khoá cũng đủ họp | Admin cắm bốn khoá miễn phí rồi chạy thử — và hỏng ba kiểu khác nhau, cả ba đều đáng ghi. (1) groq và cerebras trả `HTTP 403 — error code: 1010`, trông y hệt sai khoá; thật ra là Cloudflare chặn theo chữ ký trình khách vì `urllib` mặc định tự xưng `Python-urllib/3.10`. Thêm một dòng header thì cùng lời gọi đó đi lọt tới API và trả về lỗi thật ("model không tồn tại"). Kiểu hỏng này dắt người ta đi sai đường rất xa: 403 thì ai cũng đi tạo lại khoá, không ai nghĩ tới header. (2) MỌI tên model trong file đều đã cũ dù mới viết bốn ngày trước — groq không còn llama-3.x nào (còn 14 model, phần lớn là whisper/TTS/prompt-guard), openrouter đã đẩy deepseek-v3 và llama-3.3 khỏi gói free, `mistral-large` không nằm trong tier miễn phí. Đây đúng là thứ dòng cảnh báo đầu file đã nói trước, và nó thành thật chỉ sau bốn ngày. (3) cerebras trả 402 "payment required" — khoá đúng, tài khoản chưa bật thanh toán; nó CÓ khoá nên `_loc_thanh_vien` không loại được (bộ lọc chỉ biết thiếu khoá hay không), nên phải đẩy xuống cuối hàng bằng tay: một ghế ngồi xuống rồi mới hỏng là một ghế mất trắng. Sau khi sửa, họp thật với ba nhà miễn phí + Claude chủ toạ, ba họ model khác nhau (gpt-oss · mistral · nemotron) và ba vai khác nhau: **0đ tiền thẻ, $0,17 hạn mức Pro**. Chủ toạ tìm ra 5 điểm bất đồng — trong đó có một điểm NGẦM (một thành viên tránh nhắc "phong thủy" trong khi thành viên khác coi đó là hướng an toàn, tức hai bên ngầm đánh giá rủi ro khác nhau mà không ai nói ra) — và 5 khẳng định chưa kiểm, gồm một câu bịa ngược logic ("affiliate thường yêu cầu nội dung có tính đánh bạc") và một mốc "sáu tháng" không có căn cứ nào. Đúng thứ một model đơn lẻ không tự bắt được về chính mình |
| 2026-08-31 | **Đo chất lượng não phụ — bộ ca thử nay đo được CẢ HAI bộ não** (`run.py --nao phu`). Đường dispatcher giả truyền bằng THAM SỐ (`dispatch_py`/`cwd`/`env_them`), không bằng biến môi trường. Thêm khoá model vào `SECRETS` (tiến trình con không được cầm) và nạp `.env` cho tiến trình CHA khi đo não phụ. Bật thêm một ghế groq MIỄN PHÍ cuối chuỗi dự phòng. Gateway nhắc admin soát ví khi não phụ có động vào sổ | Mốc 31/08 ghi "chưa đo chất lượng não phụ" — và bộ đo cũ không với tới được, vì nó tự dựng lệnh `claude -p` nên chỉ biết đo đúng một bộ não. Bộ đo mà không với tới thứ cần đo thì nó đang tự khen chính đường nó đi, cùng họ với "bộ đo tự đứng ngoài phép đo". **Kết quả:** việc MỘT LƯỢT thì não phụ làm được — 3/4 ca đạt, kể cả chuỗi tiền hai vế và mảng object lồng nhau; ca thứ tư chết vì CẢ HAI model Gemini cùng trả 503, tức hỏng vì nhà cung cấp chứ không vì model, và đó là bằng chứng cho việc chuỗi một-nhà vẫn là điểm hỏng đơn → bật ghế groq cuối hàng (chỉ chạy khi Gemini sập cả nhà, lúc Claude cũng đã câm). Việc NHIỀU LƯỢT thì kém, và kém theo hướng NGUY HIỂM: 1/3 ca. Admin hỏi "em ghi chưa đấy" thì nó GHI LẠI LẦN HAI rồi đáp "em ghi ngay lúc đại ca nhắn rồi ạ" — sổ đôi, ví trừ hai lần, và chính câu nói đó khiến không ai đi kiểm. Thêm luật vào `KHOI_DAN` (kể lại đúng hai lỗi đã mắc, không dặn chung chung) thì ca đó chuyển sang ĐẠT. Nhưng lỗi thứ hai — xoá khoản chi mà quên hoàn ví — chạy lại BA lần đều quên, dù luật đã nằm trong prompt. Lời dặn chữa không nổi, nên thay vì giả vờ đã chữa: gateway đếm số lời gọi company của lượt đó và nhắc admin soát lại ví và sổ. Cùng một lý lẽ với `chuaKiemChung` của hội đồng — thứ không sửa được thì phải NÓI RA cho người còn kiểm được. Và cũng vá một lỗi của chính đợt này: bộ ca thử tước secret khỏi tiến trình con nhưng tiến trình cha cũng không có khoá, nên lần chạy đầu ra 0/6 vì "chưa có GEMINI_API_KEY" — một con số sai theo hướng CHÊ, khó ngờ y như sai theo hướng khen |
| 2026-08-31 | **Hẹn giờ: nhắc đúng phút, và việc đã ký thì tới giờ tự chạy.** Sửa **S3** — mở đúng MỘT khe: cron được chạy `write` khi lời gọi mang phiếu duyệt có `henLuc` admin ký trước. `approvals` thêm cột `henLuc` + `hen_den_han()`; token của phiếu hẹn sống tới qua giờ hẹn thay vì 10 phút; `consume()` từ chối khi chưa tới giờ; cửa sổ 60 phút sau giờ hẹn thì thôi. `dispatch --hen-luc` sinh phiếu hẹn thay vì chạy ngay, và không bao giờ để whitelist nuốt mất cái hẹn. Thêm **`nhacCompany`** (sổ sqlite, `datNhac`/`dsNhac`/`huyNhac`) cho loại chỉ-nhắc-không-làm. Timer thứ hai `companyspec-hen.timer` nhịp **1 phút**, `AccuracySec=5s` | Admin: "một số việc tự động đã được anh duyệt thì tới giờ đó tự làm", và "cái nào anh bảo nhắc thì tới giờ thông báo một tiếng" — trước hôm nay nói gì cũng không có gì xảy ra, vì mọi lịch đều khai cứng trong `schedules.yaml` nên không có ngăn nào chứa một lời hẹn MỘT LẦN, và timer 15 phút thì hẹn 3h sáng kêu lúc 3h14. Không đi đường Google Calendar dù admin có nhắc tới: push của GCal cần một URL HTTPS công khai, mà máy nằm sau NAT — đó chính là lý do Telegram ở đây phải long polling từ 02/08. Nên bot vẫn phải TỰ HỎI, mà đã tự hỏi thì hỏi một bảng sqlite rẻ hơn hỏi API Google rất nhiều, lại không thêm một bộ khoá OAuth có quyền ghi vào lịch thật, và không đẻ ra hai cuốn lịch song song (C5). Chỗ GCal thật sự hơn là đánh thức CON NGƯỜI — báo thức điện thoại chắc hơn tin nhắn bot — nên hai việc để hai chỗ. Về S3: whitelist CỐ Ý vẫn không nâng được nó, vì whitelist là quyền đứng không gắn nội dung; phiếu hẹn thì khoá vào đúng một payloadHash, dùng một lần, và từ chối nếu chưa tới giờ — một khe chứ không phải một cánh cửa. Đo đầu-đến-cuối 31/08: đặt lời nhắc, timer kêu ĐÚNG MỘT LẦN, chạy lại thì im. Và bắt được một bug im lặng ngay trong lúc đo — `dsNhac` chỉ trả lời nhắc TƯƠNG LAI nên cái vừa tới giờ biến mất khỏi danh sách trước khi scheduler kịp thấy: chuông sẽ không bao giờ kêu, mà không có dòng lỗi nào. Thêm `gomDenHan` mở cửa sổ một giờ về quá khứ cho đúng người đọc cần nó |
| 2026-08-31 | **Nâng ngân sách năm năng lực cron đọc Notion** (`upcomingEvents`, `dueSteps`, `progressReport`, `fundProgress`, `listTodos`: 20/25 → 35s), và câu báo lỗi của scheduler nói bằng tiếng người thay vì tiếng dispatcher | Admin gửi ảnh chụp một tin lúc 23:03: "Không chạy được calendarCompany.upcomingEvents: Quá 20s — cắt." Đo trên 508 lần chạy thật của lịch canh: 493 lần `ok` với TRUNG BÌNH 1.517 ms — nhưng 11 lần `failed` ở ~16.870 ms và 4 lần `budgetExceeded` ở đúng 20.040 ms. Đọc ra ngay: khi Notion chập, `notionClient` thử hai lần (8s + 0,5s nghỉ + 8s = 16,5s) rồi mới báo lỗi tử tế, mà ngân sách 20s chỉ chừa 3,5s — khởi động tiến trình ăn hết chỗ đó nên dispatcher GIẾT trước. Đúng bẫy "timeout phải nhỏ hơn HẲN ngân sách" đã có tên trong CLAUDE.md, chỉ là lần này nó nằm ở phía ngân sách chứ không phải phía timeout. Nâng lên 35 KHÔNG làm Notion nhanh hơn — nó đổi một cái chết câm (`budgetExceeded`, mất luôn lý do) thành một câu lỗi đọc được (`failed`, có lý do). Phần thứ hai quan trọng ngang: admin nhận tin đó lúc 11 giờ đêm và không sửa được gì cho tới sáng, nên câu "Quá 20s — cắt" chỉ làm họ lo mà không nói có mất gì không. Nay là "Notion trả lời chậm quá nên em cắt. Không mất gì, 15 phút nữa em thử lại." Cơ chế im-khi-lỗi-lặp vốn đã chạy đúng (tin 21:32 tự khai "hỏng 1 lần liên tiếp trước đó"), nên không đụng tới |
| 2026-09-01 | **Lời nhắc phải nói THỨ và NGÀY, không được nói "mai".** `nhacCompany` trả thêm trường `ngay` ("thứ Tư 02/09"), `datNhac` nhét thẳng vào câu tóm tắt kèm lời dặn "nói lại cho admin cả thứ và ngày", `dsNhac` liệt kê bằng thứ+ngày+giờ thay vì chuỗi ISO thô. Mô tả năng lực nói rõ luật "mai" sau nửa đêm | Đo trên lượt thật 01/09: admin nhắn lúc **00:14** "Mai 5h30 gọi anh dậy". CEO tính "mai" theo lịch ra **02/09**, trong khi người thức lúc 0 giờ nói "mai 5h30" là chỉ buổi sáng sắp tới, cách đó năm tiếng. Toàn bộ máy móc chạy ĐÚNG — phiếu duyệt `used`, dòng vào sổ, timer 1 phút chạy đều — chỉ sai đúng một ngày, và im lặng: 5h30 không có gì kêu, admin kết luận "tính năng không hoạt động". Chỗ hỏng thật không nằm ở việc hiểu sai, mà ở **câu xác nhận**: CEO đáp "5h30 sáng mai hệ sẽ gọi dậy" — nó LẶP LẠI đúng chữ mơ hồ của admin, nên cái sai không có cách nào lộ ra. Sửa ở tầng company chứ không phải tầng prompt: khi chính dữ liệu trả về đã mang "thứ Tư 02/09" thì CEO không còn gì mơ hồ để lặp lại. Cùng một họ với "lọc ngày theo UTC, đối chiếu theo giờ VN" (25/08): sai một ngày là loại sai rẻ nhất để tạo ra và đắt nhất để phát hiện |
| 2026-09-01 | **Dọn dòng thăm dò của cron, giữ nguyên nhịp gọi.** `scheduler.don_dong_cron()` xoá dòng `taskLog` có `traceId LIKE 'trc_cron_%'` VÀ `status='ok'` VÀ cũ hơn 7 ngày, chạy ở nhịp 15 phút; `nhacCompany` tự dọn `taskLog` trong sổ riêng của mình ở đường ghi. Timer 1 phút giữ nguyên | Admin hỏi timer 1 phút có tốn token không, và dọn dẹp có ảnh hưởng hiệu quả không. Đo: timer chạy **296 lần/ngày, $0,0000, trung bình 48ms** — Python đọc sqlite, không gọi model lần nào. Nên nó KHÔNG phải thứ thừa: 69 giây CPU mỗi ngày là cái giá của độ chính xác từng phút, bỏ đi thì hẹn 5h30 kêu lúc 5h44. Thứ thừa là DÒNG LOG để lại vĩnh viễn: đo 01/09, cron chiếm **3.336/5.453 dòng (61%)** và cộng thêm 1.440 dòng mỗi ngày. Ba hàng rào cho phép dọn mà không mất gì: chỉ tiền tố `trc_cron_` (trí nhớ CEO đọc taskLog theo trace của PHIÊN nó — đo được **0 dòng cron nằm trong trace CEO nào**, nên dọn không chạm tới được dù muốn), chỉ `status='ok'` (88 dòng hỏng giữ mãi, đó là bằng chứng lúc đi tìm nguyên nhân), chỉ cũ hơn 7 ngày (`report --days 3` vẫn đủ). Chạy thật: 5.454 → 3.727 dòng, 2.117 dòng CEO còn nguyên. Và company tự dọn nhà mình chứ ops không thò tay vào (C2) — `datNhac` là đường ghi duy nhất nó có, nên dọn ở đó |
| 2026-09-01 | **CEO phủ nhận một thứ CÓ THẬT, hai lần liền, không tra lấy một lần.** `SYSTEM.md` tách hai loại "không biết" bằng một câu hỏi phân loại — *thứ này CÔNG KHAI hay của riêng admin?* — và cấm nói "X không có thật" khi chưa gọi `searchCompany`. Thêm ca thử `ten-la-thi-tra-dung-phan` | Admin đưa hướng dẫn cài "Google Antigravity". CEO đáp "không có thật, đây là thông tin bịa". Admin gửi ảnh chụp trang web; CEO lùi một bước rồi **BỊA TIẾP, cụ thể hơn lần đầu** — "chỉ là một trang web vui kiểu Easter egg của Google". Admin hỏi "em chắc chứ" thì mới lùi về "em không chắc". Sự thật: Antigravity là IDE agent-first của Google, bản xem trước 18/11/2025, 2.0.1 tháng 5/2026, chạy Gemini 3.1 Pro và hỗ trợ cả Claude Sonnet 4.6 — hướng dẫn admin đọc được là ĐÚNG. Dấu vết cho thấy gốc rễ: **cả ba lượt gọi 0 company**, trong khi `searchCompany.traNhanh` nằm sẵn trong danh mục và câu đó tra năm giây là ra. Và chỗ đáng nói nhất — lỗi nằm trong CHÍNH `SYSTEM.md`: đoạn chống bịa có câu "Tra web cũng không cứu được: bạn sẽ tìm ra một bài viết na ná rồi tưởng nó trả lời đúng câu đang hỏi". Câu ấy viết cho ca quyền-riêng-tư-của-một-link (20/08), nơi web thật sự vô dụng — nhưng đọc chung chung thì nó DẠY CEO ĐỪNG TRA. Một luật đúng cho một ca, đặt không có rào, thành luật sai cho ca khác. Sửa bằng cách cho ranh giới một câu hỏi phân loại thay vì một danh sách ví dụ: tra web chỉ thấy thứ công khai, không bao giờ nhìn thấy đồ của riêng một người. Lần sửa đầu chưa đủ sắc và làm ca cũ TRƯỢT NGƯỢC (CEO đem luật mới áp cả sang câu hỏi về link riêng) — bộ ca thử bắt được ngay, đúng việc nó sinh ra để làm. Sau khi sắc lại: 2/2 |
| 2026-09-11 | **Hai lỗ trên đường chuyển não, cùng lộ ra từ một câu hỏi của admin.** `session._chay_claude` soi cả `is_error` trong JSON chứ không chỉ `returncode`; `quotaSignal.MAU_QUOTA` thêm mẫu THẬT (`hit your…limit`, `session limit`); câu báo hết phiên đăng nhập viết lại cho không lẫn với hết hạn mức, và bỏ backtick | Admin hỏi "còn hạn mức tại sao CEO bảo hết hạn mức rồi". Tra sổ: KHÔNG phải hạn mức — phiên OAuth hết hạn từ 10/09, lần chạm trần hạn mức gần nhất là 31/08. Bốn thứ lòi ra từ đó. (1) Câu cũ "Phiên đăng nhập Claude hết hạn" bị admin đọc thành hết hạn mức nên ngồi chờ nó tự hồi — mà hai sự cố này cần hai phản ứng NGƯỢC nhau: hạn mức thì chờ vài tiếng là xong, hết phiên thì chờ bao lâu cũng không khỏi. (2) Câu đó còn có backtick quanh `claude /login`, đúng thứ SYSTEM.md cấm vì Telegram hiện ra ký tự thô. (3) CLI trả `is_error: true` mà thoát MÃ 0 — cùng sự cố hôm trước thoát mã 1 — nên nhánh mã-0 đi thẳng qua `_chay_claude`: admin nhận nguyên câu tiếng Anh làm câu trả lời và não phụ không hề nhảy vào, đúng lúc nó sinh ra để đỡ. (4) Nặng nhất: `quotaSignal` chưa bao giờ khớp câu Anthropic thật sự gửi. Mẫu viết từ phỏng đoán ("usage limit", "reached your…limit") trong khi câu thật là "You've hit your session limit · resets 3:40am". Ba lần chạm trần 18/08, 19/08, 31/08 đều nằm trong sổ `quotaHit` với nguyên văn ấy — chúng lọt lưới nhờ mã **429** đi kèm, tức nhánh dự phòng cuối cùng đỡ hộ suốt, và chính vì được đỡ nên không ai thấy lớp chính đã hỏng. Docstring của file tự dặn "bắt được mẫu thật thì chép nguyên văn vào đây"; bắt ba lần rồi mà chưa ai chép. Cách phát hiện rẻ và nên làm định kỳ: lấy `nguyenVan` đã lưu trong sổ cho chạy lại qua chính bộ nhận diện — nó phải trả True. |
| 2026-09-20 | **Policy đọc mức tự chủ — và phát hiện bộ đo đang tự kiếm quyền cho hệ.** Thêm `Capability.autonomyOptIn` (company TỰ KHAI trong manifest) + `PolicyRequest.earnedAutonomyLevel` + luật `_ruleEarnedAutonomy` đứng CUỐI hàng. Và quan trọng hơn: `core/audit.trackRecordRows` loại `reg_ evl_ e2e_ demo_` khỏi phép tính mức | Admin chốt hàng rào opt-in: thống kê nói năng lực CHẠY ĐÚNG, nó không nói **hậu quả của một lần sai** là gì — chỉ người viết company biết, nên họ phải nói ra bằng một dòng đọc được trong manifest. Ba điều kiện độc lập (khai · mức ≥2 · trần rủi ro), kết quả luôn `allowWithVerify` chứ không bao giờ `allow` trần. Nhưng thứ đáng ghi ở đây là cái lòi ra lúc nối dây: `trackRecordRows` đang đếm cả lưu lượng của chính bộ đo. Đo được: trong 227 dòng của `travisSelfTestCompany.recordWrite` có **194 dòng `e2e_` và 33 dòng `demo_`** — KHÔNG một lời gọi thật nào, mà bảng `travis.py autonomy` in ra mức 2; `nhacCompany.dsNhac` cũng có 136 dòng `reg_` góp vào mức 4. Tiền lệ `evl_` ở `ceoRunLog` và `reg_` ở báo cáo backOffice đã có sẵn trong bảng bẫy, nhưng cả hai lần con số ấy chỉ đi vào một BÁO CÁO; lần này nó đi vào một QUYẾT ĐỊNH QUYỀN HẠN, tức là một cánh cửa mở được bằng cách chạy `python3 tests/run.py` vài lần. Lọc xong thì tỉ lệ đạt thật lộ ra và nó xấu hơn hẳn: `xuongCompany.nhanViec` 77% → **20%**, `ghiBuoc` 69% → **0%** — con số đẹp trước đây phần lớn là của bộ đo, và nó nghiêng về hướng TRẤN AN nên không ai đi tìm. Bài học: **một phép đo bẩn nằm im cho tới ngày có ai đó dùng nó để quyết định.** Trước khi nối một con số vào cửa quyền, hỏi "ai đã ghi những dòng này". Cách nó lộ ra cũng đáng ghi: ba ca `TestWritePathNeedsASignature` đồng loạt đỏ ngay lần chạy đầu — vì tớ đã khai opt-in cho đúng năng lực đang làm CHỐT CANH cho cửa duyệt. Đặt chốt canh lên chính cánh cửa nó canh thì ca thử sẽ xanh theo cửa đang mở; đã tách thành `recordWrite` (giữ vai chốt) và `recordWriteAuto` (mang opt-in) |
| 2026-09-20 | **Nối Memory · Secret broker · Event bus — và mỗi lần nối lại lòi ra một con số không ai kiểm.** Luật ngày rụng gom về `contracts.isStillValid` (ba nơi cùng đọc, có ca ma trận SQL↔Python); `ProcessLimits.allowedSecretNames` dựng TỪ PHIẾU chứ không từ manifest, thêm `travis.py secrets`; event bus chạy trong nhịp 15 phút với `eventId` tất định theo nội dung sự cố | **Memory.** HANDOFF dặn "test đối chiếu trước", và ca ấy đỏ ngay: đo được **3 trên 4 mốc trong một ngày** cho kết quả khác nhau giữa `core/memory` và `session.profile_block`. Hai nguyên nhân đều đã có tên trong bảng bẫy — so chuỗi ngày 10 ký tự với mốc ISO 20 ký tự (chuỗi ngắn là tiền tố nên luôn nhỏ hơn), và lọc theo UTC trong khi ngày của admin là ngày ở Đà Lạt. Hậu quả nếu cứ nối: `[đến 15/10]` rụng ngay 00:00 ngày 15/10 thay vì hết ngày — một điều admin dặn ta nhớ mất đúng một ngày cuối, mãi mãi, không dòng lỗi nào. Quyết định kèm theo: **gom LUẬT, không dời DỮ LIỆU** — PROFILE.md ở lại với `profileCompany` (có đường ghi qua nút duyệt, admin sửa tay được), trí nhớ phiên ở lại chỗ cũ (năm nơi đang đọc, và nó không cần tầng/nhãn/ngày rụng). Dời chúng là đổi một thứ đang chạy tốt lấy một sơ đồ gọn hơn. Và chính ca ma trận bắt thêm một lỗ không ai thấy bằng mắt: `expiresAt = ""` **ghi vào được mà không bao giờ đọc ra**. **Secret broker.** Cách nối sai và dễ hơn là cấp phiếu chỉ để có dòng trong sổ, vẫn bơm secret theo manifest — lúc đó §30 trả lời rất đẹp trong khi cái phiếu không kiểm soát gì, tức là một hàng rào giả nữa, cùng họ với `pattern:` và `anyOf` khai mà không ai soát. Nên `allowedSecretNames` dựng TỪ phiếu: broker từ chối là khoá vắng mặt thật. Sổ phiếu tách lưu lượng bộ đo (~190 phiếu mỗi lượt `tests/run.py`) và tự dọn ở đúng nhịp đang dọn dòng cron. **Event bus.** EV-1 bằng code: có đề xuất việc ghi thì bỏ TOÀN BỘ, không lọc bớt. Chống nhắn lặp bằng `eventId` TẤT ĐỊNH theo nội dung sự cố chứ không bằng bảng trạng thái thứ hai — 6 tiếng sự cố × quét 15 phút vẫn ra đúng một tin, và không có trạng thái nào để lệch. Chỗ dễ sai nhất đã viết ra: khoá theo SỐ GIỜ im lặng thì mỗi lần quét đẻ một id mới, tức là quay về đúng 21 tin lúc nửa đêm với một hàm trông như đang chống lặp. Đo thật trên sổ tạm: quét 1 ra 2 đề xuất + 1 tin, quét 2 im lặng; trên sổ THẬT ra 0 vì cả 2.210 dòng hỏng trong 6 giờ đều là của bộ đo |
