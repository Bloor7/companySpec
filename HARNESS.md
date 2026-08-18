# HARNESS.md — đối chiếu companySpec với cách cộng đồng dựng harness

Viết ngày 2026-08-16, trả lời câu admin hỏi CEO trong thread 95:

> *"Anh thấy cái harness người ta dùng rất nhiều em hãy nghiên cứu nó và so sánh
> với hệ thống của anh, tạo ra prompt hoặc yêu cầu để có thể học theo"*

File này **không phải luật**. [PRINCIPLES.md](PRINCIPLES.md) mới là hiến pháp,
[CLAUDE.md](CLAUDE.md) là bản đồ. Đây là một lần đối chiếu ra ngoài, có hạn sử
dụng: cộng đồng đổi nhanh, đọc lại sau vài tháng thì phải đo lại.

---

## 1. "Harness" là gì, theo đúng nghĩa người ta đang dùng

Harness là **lớp bọc quanh vòng lặp model** — mọi thứ không phải model nhưng
quyết định model làm được gì: bộ nhớ bền vững, quyền hạn, ngân sách ngữ cảnh,
điều phối nhiều agent, tool.

Luận điểm gốc của phong trào này: *kiến trúc quyết định độ tin cậy, không phải
năng lực model*. Cùng một model, chỉ đổi harness, thứ hạng benchmark dịch hàng
chục bậc. Đó chính là điều dự án này đã tin từ đầu — **P1: code cứng giữ khung,
LLM giữ nội dung** — chỉ khác tên gọi.

Bản kiểm kê đầy đủ nhất hiện có chia harness thành **12 nguyên thể thiết kế**:
vòng lặp agent · lập kế hoạch · nạp và nén ngữ cảnh · thiết kế tool · skills và
MCP · quyền hạn · bộ nhớ và trạng thái · điều phối · kiểm chứng và eval · quan
sát · gỡ lỗi · người-trong-vòng-lặp.

Bốn chủ đề xuyên suốt, đáng chép ra vì cả bốn đều va thẳng vào dự án này:

1. **Harness ≠ model.**
2. **Ngữ cảnh là hạ tầng** — token là ngân sách, không phải tài nguyên vô hạn.
3. **Xác định bằng ràng buộc** — state machine, schema, permission context thay
   cho lời dặn bằng tiếng người. (Chính là **P2** của dự án này.)
4. **Tính chuyển được** — `CLAUDE.md`, `AGENTS.md`, skill manifest làm quyết
   định kiến trúc dùng lại được.

---

## 2. Đối chiếu 12 nguyên thể với hệ đang chạy

Cột "bằng chứng" là chỗ đọc được trên máy, không phải suy đoán.

| # | Nguyên thể | Hệ này | Bằng chứng |
|---|---|---|---|
| 1 | **Vòng lặp agent** | Có, thuê ngoài. CEO là một phiên Claude Code, vòng lặp do CLI lo. Có cắt phiên theo thời gian và số lượt | `registry/gateway.yaml` — `windowMinutes: 30`, `maxTurnsPerSession: 25` |
| 2 | **Lập kế hoạch** | **Một phần (18/08).** Sổ tay `viec-nhieu-buoc` dạy CEO nói kế hoạch trước khi làm, dừng giữa chừng thì nói rõ đã tới đâu, và đọc khối "Phiên trước" làm checkpoint. Vẫn chưa có kế hoạch dạng dữ liệu mà CEO tự sửa được | `ceo/playbooks/viec-nhieu-buoc.md` |
| 3 | **Nạp và nén ngữ cảnh** | Nạp **hơn chuẩn**: "Bức tranh hiện tại" tra sẵn mỗi lượt bằng code cứng. Nén **có bản bị động (18/08)**: đóng phiên thì ghi tóm tắt (giờ, việc đã chạy xong lấy từ `taskLog`), phiên sau nạp lại. Nén CHỦ ĐỘNG trước khi chạm trần thì vẫn chưa | `gateway.dong_phien()`, `nho_lai()` |
| 4 | **Thiết kế tool** | **Hơn chuẩn rõ rệt.** Mỗi năng lực có JSON Schema đóng (`additionalProperties: false`), có `riskTier`, có `maxDurationSec`, có lý do chọn runtime. Cộng đồng gọi đây là "typed schemas at every boundary" và phần lớn repo không làm nổi | `companies/*/companySpec.yaml` |
| 5 | **Skills / MCP** | **Có, bản có ranh giới (18/08).** Ba sổ tay nạp theo việc; router bằng code cứng nằm NGOÀI model, nên CEO vẫn không có tool `Skill`. Không dùng MCP — cố ý | `ceo/playbooks/`, `gateway.chon_so_tay()` |
| 6 | **Quyền hạn** | **Hơn chuẩn rõ rệt.** Deny list ghim ở CEO, hook `PreToolUse` chặn bằng code, phê duyệt có TTL, whitelist học dần có hạn 90 ngày và trần mỗi ngày | `ceo/settings.json`, `ceo/hooks/guard.py`, `ops/approvals.py` |
| 7 | **Bộ nhớ và trạng thái** | Có, một lớp. `profileCompany` giữ điều luôn đúng về admin, nhét cuối prompt. Không có bộ nhớ phân tầng, không có nén chủ động. Bản lưu hội thoại bị cắt còn 800 ký tự, nạp lại còn 400 | `ops/gateway.py:1045`, `nho_lai()` |
| 8 | **Điều phối** | Hình sao có chủ đích (**P3**), một tầng, không fan-out. Ngoại lệ duy nhất là `researchCompany` chạy nhiều luồng đọc bên trong phiên nhốt kín của nó. Không có chuyên môn hoá vai (planner / reviewer / critic) | `ops/dispatch.py`, `companies/researchCompany/` |
| 9 | **Kiểm chứng và eval** | **Có (16/08, mở rộng 18/08).** 19 ca chạy khô: chuỗi lời gọi, hành vi nhiều lượt, và vài luật câu chữ tra được. Cộng `codemap --check` soát luật kiến trúc tĩnh | `ops/evals/`, `ops/codemap.py --check` |
| 10 | **Quan sát** | Tốt. Chi phí, hạn mức, lỗi, lý do CEO chết đều tra được bằng lệnh | `backOffice/src/backoffice.py report` |
| 11 | **Gỡ lỗi** | **Tốt (18/08).** Phát lại được quỹ đạo một phiên: admin nói gì, CEO gọi gì, đổi gì ngoài đời, sổ tay nào đã nạp — gộp bốn nguồn theo trục thời gian. Cộng ảnh chụp Notion trước khi phá | `backoffice.py trace`, `ops/snapshot.py` |
| 12 | **Người trong vòng lặp** | **Hơn chuẩn rõ rệt.** Duyệt trước hành động phá huỷ, nút bấm ngay trong Telegram, mã dùng một lần, đối chiếu payload để CEO không đổi nội dung sau khi admin đã đọc | `ops/approvals.py`, `PRINCIPLES.md` §5 |

**Đọc bảng theo cột dọc:** hệ này mạnh ở nhóm *an toàn và ranh giới* (4, 6, 10,
12) — mạnh hơn phần lớn thứ đang được chia sẻ ngoài kia, vì nó được dựng cho
một người thật có ví tiền thật. Yếu ở nhóm *tiết kiệm ngữ cảnh và tự kiểm*
(2, 3, 5, 9) — đúng những thứ chỉ đau khi hệ lớn lên, mà hệ thì đang lớn.

---

## 3. Ba khoảng trống, xếp theo giá trị

### Khoảng trống 1 — Skills: mọi thứ nạp mỗi lượt

> **Đã lấp, 2026-08-18.** `ceo/playbooks/` — ba sổ tay (`tien`,
> `ghi-nguyen-van`, `viec-nhieu-buoc`); `SYSTEM.md` từ 14.143 xuống 9.270 ký tự.
> Router `gateway.chon_so_tay()` chọn sổ theo từ khoá, **bằng code cứng, phía
> ngoài model** — nên KHÔNG phải mở tool `Skill` cho CEO, deny list giữ nguyên.
>
> Ba tính chất khiến việc này không đánh đổi an toàn lấy gọn gàng:
>
> · **Mỗi khối rời đi để lại một câu NEO trong lõi.** Router trượt thì CEO mất
>   bảng chi tiết, không mất luật gốc — hỏng nhẹ một bậc, không hỏng câm.
> · **Sổ tay nối vào tin nhắn**, nên trong phiên đang nối nó còn lại ở các lượt
>   sau. Router chỉ cần đúng ở lượt ĐẦU của một câu chuyện. Đo được: lượt "em
>   ghi chưa đấy" không nạp sổ tiền mà CEO vẫn xử lý đúng chuỗi.
> · **Đo trên dữ liệu thật**, không trên ví dụ tự nghĩ: 143 câu admin trong
>   `ceo/store.sqlite` → 0 lần trượt sổ "tiền", 21% lượt không nạp sổ nào (toàn
>   chuyện phiếm, hỏi giờ, gửi ảnh). Bốn từ khoá phải thêm sau khi đo, trong đó
>   `xoa`/`sua` (xoá khoản chi cũng là việc phải hoàn ví) và `bao nhieu` ("Anh
>   còn bn riền" — hỏi số dư mà gõ sai chữ "tiền").
>
> Câu hỏi cũ ("prompt có dài quá không") đổi thành câu hỏi mới ("router có bỏ
> sót không"), nên câu hỏi mới phải tra được: `python3 ops/gateway.py
> soat-so-tay --thieu` liệt kê những lượt không nạp sổ nào.

`ceo/SYSTEM.md` dài 184 dòng và **được nạp nguyên vẹn ở mọi lượt**, kể cả lượt
admin chỉ hỏi "mấy giờ rồi". Trong đó có nguyên một bảng dài về chuỗi thu/chi
cộng trừ ví, một bảng dài về đề nghị ghi nhớ, một bảng về trạng thái trả về.

Cộng đồng gọi cách chữa là **progressive disclosure**: chia làm ba tầng nạp —
frontmatter (tên + mô tả, luôn ở trong context), thân skill (chỉ nạp khi được
chọn), file tham chiếu (chỉ đọc khi cần). Trần khuyến nghị cho thân skill là
~500 dòng / ~5.000 token, phần dư đẩy xuống `references/`.

Cái được không chỉ là tiền. Cái được lớn hơn: **quy trình tách khỏi prompt thì
sửa được, thử được, và bớt loãng**. Bảng chuỗi thu/chi hiện phải cạnh tranh chỗ
đứng với hai chục thứ khác trong cùng một khối chữ.

Cái mất phải nói thẳng: hệ này **cố ý** không cho CEO tool `Skill` — nó nằm
trong deny list ở `ceo/settings.json`. Mở tool đó là mở một bề mặt mới cho một
tiến trình đang giữ hồ sơ cá nhân của admin. Nên không được bê nguyên pattern
vào; phải làm phiên bản có ranh giới (xem prompt 1).

### Khoảng trống 2 — Không có cách biết CEO có đang tệ đi không

> **Đã lấp một phần, 2026-08-16.** `ops/evals/` — 12 ca thử chạy khô, chấm bằng
> chuỗi lời gọi CEO bắn ra. Xem mục "Cách kiểm, thay vì tin" trong CLAUDE.md.
>
> **Lấp nốt hai nửa còn lại, 2026-08-18** — 19 ca:
>
> · **Nhiều lượt.** Ca có khoá `luot:` chạy nối nhau trong CÙNG một phiên
>   (`--resume`), chấm từng lượt. Ba ca mới: không ghi lại lần hai (ghi trùng
>   thì sổ Notion thành sổ đôi mà không có dòng lỗi nào), xoá thì tra trước rồi
>   mới xoá, hỏi đủ dữ kiện rồi mới ghi.
> · **Câu chữ.** `phaiNoi` / `khongDuocNoi`, cộng một phép soát Markdown chạy
>   TỰ ĐỘNG cho mọi ca. Nó bắt bug ngay lần chạy đầu: CEO vi phạm luật "không
>   Markdown" — đối chiếu hội thoại thật ngày 16/08 thì đúng là vi phạm suốt.
>   Luật cũ nằm cuối prompt, viết trừu tượng, và bản thân nó viết bằng Markdown.
>   Đã viết lại bằng ví dụ ĐỪNG/HÃY cụ thể; chạy lại ca đó thì đạt.
>
> Vẫn còn trống, nói thẳng: chất lượng SUY NGHĨ của CEO thì không đo được bằng
> code, và ở đây không định đo.

Đây là khoảng trống tớ thấy đáng lo nhất, vì nó **im lặng**.

Mọi thay đổi prompt hiện nay được nghiệm thu bằng cảm giác: sửa `SYSTEM.md`,
nhắn thử một câu, thấy ổn thì thôi. Không có bộ ca thử, nên không ai biết sửa
một dòng cho việc A có làm hỏng việc B hay không. Con bug tốn công nhất dự án —
sai tên trường đầu vào, báo cáo tối in "thu 0đ · chi 0đ" suốt nhiều tuần — thuộc
đúng loại này: hỏng mà trông y hệt bình thường.

`codemap --check` đã bịt được đúng một mặt của nó (lời gọi viết cứng). Mặt còn
lại — CEO dựng lời gọi động, chọn sai company, quên nửa sau của chuỗi thu/chi —
vẫn đang trống.

### Khoảng trống 3 — Phiên đứt là mất trí nhớ

> **Đã lấp, 2026-08-18.** `ops/gateway.py` — `dong_phien()` ghi một đoạn tóm tắt
> đúng lúc phiên đóng, `nho_lai()` nạp lại đoạn đó. Tóm tắt dựng bằng **code
> cứng, không gọi model nào**: giờ giấc + lý do đóng lấy từ bảng `thread`, việc
> đã làm lấy từ `taskLog` theo traceId (T4), câu chữ vẫn do sổ tin nhắn lo.
> Thêm bảng `threadSummary`, sống 7 ngày, chỉ nạp nếu chưa quá 24 tiếng.
>
> **Vì sao không nhờ model tóm tắt** — ba lẽ, xếp theo sức nặng: (1) lúc hết hạn
> mức là lúc phiên hay đứt nhất, và cũng đúng là lúc lời gọi tóm tắt sẽ hỏng —
> trí nhớ phải còn khi mọi thứ khác hỏng, không phải mất theo; (2) phiên đóng
> lúc admin không ngồi đó, model tóm sai thì cái sai đi thẳng vào phiên sau mà
> không ai soát; (3) phiên đóng nhiều lần mỗi ngày, mỗi lần một lời gọi nữa là
> trả tiền cho thứ code làm được (P1).
>
> Vẫn còn trống: **nén chủ động** đúng nghĩa — tóm tắt *trước khi* chạm trần
> bằng chính phiên đang sống. Cái đó buộc phải có model, nên để lại.

Hết 30 phút hoặc 25 lượt thì phiên đứt, CEO chỉ được nạp lại vài tin gần nhất,
mỗi tin cắt còn 400 ký tự. Cộng đồng chữa bằng **nén chủ động**: agent tự tóm
tắt *trước khi* chạm trần, thay vì bị cắt ngang. Đo được là hơn hẳn cách nén bị
động, vì nén bị động luôn rơi vào đúng lúc đang làm dở việc.

Việc này nhỏ hơn hai việc trên, và có cách chữa rẻ: khi đóng phiên thì ghi một
đoạn tóm tắt ngắn vào store, phiên sau nạp đoạn đó thay vì nạp tin thô cắt cụt.

---

## 4. Prompt sẵn dùng

Dán từng cái vào Claude Code trong thư mục `/home/tsix/companySpec`. **Làm một
cái một, chạy thật, thấy đúng rồi mới sang cái sau** — và đặt mốc git sau mỗi
cái, theo mục "Phiên bản và cách quay về" trong CLAUDE.md.

### Prompt 1 — Tách SYSTEM.md thành các lớp nạp dần

```
Đọc ceo/SYSTEM.md và PRINCIPLES.md §11b (ràng buộc thật của tầng CEO).

Việc: giảm phần LUÔN nạp của prompt CEO, mà không mở thêm tool nào cho CEO.
Tool Skill đang nằm trong deny list của ceo/settings.json và PHẢI ở nguyên đó —
đọc lý do trong PRINCIPLES.md P2 trước khi đề xuất bất cứ điều gì.

Trước tiên ĐO, đừng sửa gì:
- SYSTEM.md hiện chiếm bao nhiêu token trong mỗi lượt CEO?
- Tra ceo/store.sqlite: trong 50 lượt gần nhất, bao nhiêu lượt thật sự cần tới
  bảng chuỗi thu/chi? bao nhiêu lượt cần bảng đề nghị ghi nhớ?
Báo cáo hai con số đó cho tớ trước khi làm tiếp.

Sau khi tớ đọc số, hãy đề xuất cách chia SYSTEM.md thành phần lõi luôn nạp và
các khối chỉ nạp khi cần, do gateway.py quyết định bằng CODE CỨNG (giống cách
brief_block() và nho_lai() đang làm) — KHÔNG phải do CEO tự chọn. Nêu rõ khối
nào nạp theo điều kiện gì, và điều gì hỏng nếu đoán sai điều kiện.
```

### Prompt 2 — Dựng bộ ca thử cho CEO

```
Hệ này chưa có cách nào biết một thay đổi trong ceo/SYSTEM.md có làm hỏng hành
vi cũ hay không. Dựng cái đó.

Đọc trước: ceo/SYSTEM.md, ops/dispatch.py, ops/gateway.py, và bảng "Đã sửa rồi
— đừng làm lại" trong CLAUDE.md.

Yêu cầu:
- Một bộ ca thử, mỗi ca là: câu admin nhắn → chuỗi lời gọi company MONG ĐỢI
  (tên company, tên năng lực, các trường đầu vào bắt buộc).
- Lấy ca thử từ hai nguồn THẬT, không bịa: (a) mỗi dòng trong bảng "Đã sửa rồi"
  thành ít nhất một ca, (b) các lượt thật trong ceo/store.sqlite.
- Chạy được bằng một lệnh, in ra ca nào trượt và trượt ở đâu.
- Chạy ở chế độ KHÔNG chạm dữ liệu thật: không ghi Notion, không đổi ví.
  Nêu rõ cậu chặn bằng cách nào, và làm sao chắc chắn nó chặn thật.

Đừng viết code ngay. Đề xuất thiết kế trước, nêu rõ cái gì KHÔNG kiểm được bằng
cách này.
```

### Prompt 3 — Tóm tắt khi đóng phiên

```
Trong ops/gateway.py, phiên CEO bị cắt khi quá 30 phút hoặc quá 25 lượt. Lúc đó
nho_lai() nạp lại vài tin gần nhất, mỗi tin cắt còn 400 ký tự, và bản lưu ở
gateway.py:1045 vốn đã bị cắt còn 800.

Việc: khi một phiên đóng, ghi lại một đoạn tóm tắt ngắn về việc đang làm dở, để
phiên sau nạp đoạn đó thay vì nạp tin thô cắt cụt.

Trước khi viết code, trả lời:
- Tóm tắt sinh ra bằng gì? Nếu bằng LLM thì tốn thêm bao nhiêu mỗi phiên, và
  ai trả — đối chiếu với cầu dao trong registry/gateway.yaml.
- Phiên đứt giữa chừng, tiến trình chết — thì ai ghi tóm tắt?
- Tóm tắt sai thì hệ hỏng thế nào? So với hôm nay là hỏng nặng hơn hay nhẹ hơn?

O10: không được nuốt lỗi. Không sinh được tóm tắt thì phải nói ra, không được
lặng lẽ trả về chuỗi rỗng.
```

### Prompt 4 — Đọc một repo harness và chỉ rút cái dùng được

```
Đọc repo <DÁN URL>. Rồi đối chiếu với hệ ở /home/tsix/companySpec: đọc
CLAUDE.md, PRINCIPLES.md và HARNESS.md trước.

Với mỗi ý trong repo đó, xếp vào đúng một trong bốn nhóm, và phải nêu bằng
chứng trong mã của hệ này:
1. Hệ này đã có, làm theo cách khác — cách nào tốt hơn, vì sao?
2. Hệ này chưa có và ĐÁNG thêm — nó chữa nỗi đau nào có thật ở đây?
3. Hệ này chưa có và KHÔNG nên thêm — nguyên tắc nào cấm? (P2, P3, T2, §11)
4. Không áp dụng được — vì hệ này chỉ phục vụ một người.

Không viết code. Không cài gì. Không thêm phụ thuộc. Đầu ra là một bảng bốn
nhóm, mỗi dòng một câu.
```

---

## 5. Cái KHÔNG nên học theo

Ba thứ đang thịnh hành mà hệ này nên đứng ngoài:

- **MCP để nối dịch vụ ngoài.** Một MCP server là một cửa mới vào hệ, nằm ngoài
  `dispatch.py`. Vi phạm **T2** — cổng duy nhất. Cần dịch vụ mới thì viết
  company mới; đắt hơn, nhưng vẫn đi qua duyệt, hạn mức và nhật ký.
- **Cài nhiều skill/plugin cùng lúc cho đủ bộ.** Mỗi thứ cài thêm là mã chạy
  bằng quyền của admin trên máy có `ops/.env`. Hệ này cấm công khai repo vì
  đúng lý do đó (**§11 luật 11**).
- **Fan-out nhiều agent cho việc thường.** Nghe hiện đại, nhưng ở đây mỗi phiên
  mới có chi phí cố định đã đo (`PRINCIPLES.md` §11b) và cầu dao hạn mức là
  thật. Fan-out chỉ đáng khi việc thật sự song song được — `researchCompany`
  đã là đúng chỗ cho nó, và cái giá của nó hiện thành một dòng riêng trong
  backOffice, đúng như thiết kế.

---

## Nguồn

- [Effective harnesses for long-running agents — Anthropic](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [awesome-harness-engineering — 12 nguyên thể thiết kế](https://github.com/ai-boost/awesome-harness-engineering)
- [Agent Harness Engineering — Addy Osmani](https://addyosmani.com/blog/agent-harness-engineering/)
- [Skill Issue: Harness Engineering for Coding Agents — HumanLayer](https://www.humanlayer.dev/blog/skill-issue-harness-engineering-for-coding-agents)
- [Progressive Disclosure Pattern — microsoft/agent-skills](https://deepwiki.com/microsoft/agent-skills/5.3-progressive-disclosure-pattern)
- [Claude Code Harness and Environment Engineering](https://hidekazu-konishi.com/entry/claude_code_harness_and_environment_engineering_guide.html)
