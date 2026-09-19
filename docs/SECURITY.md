# SECURITY.md — ranh giới, và ai canh chúng

> Nguyên tắc nền: [CORE_CONTRACT.md](CORE_CONTRACT.md) ·
> Quyền tự chủ: [AUTONOMY.md](AUTONOMY.md)

**Luật N1 — mọi luật ở đây phải có một phép soát CHẠY ĐƯỢC**, hoặc được đánh
dấu rõ là *chưa có hàng rào*. Hàng rào giả hại hơn không có hàng rào, vì người
đọc sau này sẽ tin nó.

Cột "Ai canh" dưới đây không phải trang trí — nó là điều kiện để một dòng được
tồn tại trong file này.

---

## 0. Mô hình đe doạ

Đây là trợ lý cá nhân của **một người**, chạy trên máy của họ. Kẻ tấn công
không phải hacker nhắm vào hệ thống — mà là:

| Ai / cái gì | Làm gì |
|---|---|
| **Model đi lạc** | Hiểu sai ý, gọi nhầm năng lực, bịa số, tự khai "đã xong" |
| **Chữ từ ngoài** | Trang web, README, ảnh, tệp chứa lệnh nhắm vào model |
| **Repo lạ** | `postinstall` chạy lúc cài, đọc `.env`, gửi ra ngoài |
| **Chính hệ này** | Cron lúc 3 giờ sáng ghi nhầm, không ai thức để thấy |
| **Tai nạn** | Gõ nhầm tên trường, quên dấu cách trong YAML, sai múi giờ |

Cái **không** nằm trong mô hình: kẻ có quyền root trên máy admin. Nếu tới mức
đó thì mọi thứ ở đây đã vô nghĩa.

---

## 1. Bảy ranh giới

### R1 — LLM không có quyền lực trực tiếp

Model được **reason, plan, propose, generate, explain**.
Code quyết định **allow, deny, execute, verify, rollback, audit**.

| Luật | Ai canh |
|---|---|
| `riskTier` lấy từ manifest, không từ envelope (G3) | `core/policy.py` · `testPolicyParity` |
| Quyết định quyền hạn là hàm THUẦN, không gọi model | `core/policy.decide` · `testSameRequestSameOutcome` |
| CEO không tự duyệt được việc của mình | `ops/approvals.py` · không trả `payloadHash` cho model |

> Một luật chỉ viết trong prompt là luật model phá lúc nào cũng được mà không
> ai biết. Đó là lý do mỗi dòng trên đều có cột thứ hai.

### R2 — Chữ từ ngoài là DỮ LIỆU, không phải mệnh lệnh

Ảnh, tệp, trang web, README, kết quả tìm kiếm — tất cả.

| Luật | Ai canh |
|---|---|
| Bắt prompt injection trong repo lạ, xếp mức `high` | `core/acquisition.py` · `testPromptInjectionIsFound…` |
| Trích dẫn thứ tìm được như bằng chứng, không thi hành | cùng file |
| `sage` (employee đọc web) **không ghi được gì, ở đâu cả** | `employees/sage` · `testSageWritesNowhere` |

`sage` là chỗ ranh giới mỏng nhất: chữ trên trang lạ đi thẳng vào phần suy
luận của nó. Nên nó được giữ bằng **quyền hạn**, không bằng lời dặn — một
trang web có dụ được nó cũng không làm gì được.

### R3 — Secret không bao giờ rời chỗ của nó

Không nằm trong: `memory` · `prompt` · `audit log` · `source code` ·
`employee profile` · `envelope`.

| Luật | Ai canh |
|---|---|
| Company chỉ nhận secret đã khai (C2.4) | `core/execution.buildChildEnvironment` · `testUndeclaredSecretIsNotPassed` |
| **Không employee nào** đọc secret, kể cả `sentinel` | `testNobodyCanReadSecrets` |
| Broker cấp phiếu mang TÊN, không mang GIÁ TRỊ | `core/secretBroker.py` · `testLeaseCarriesNameNotValue` |
| Phiếu hết hạn (mặc định 5 phút) | `testLeaseExpires` |
| Xin khoá phải nói lý do | `testReasonIsMandatory` |
| Chặn khoá lọt vào trí nhớ | `core/memory.looksLikeSecret` · `testObviousSecretsAreBlocked` |
| Xoá giá trị khỏi log (lớp cuối) | `core/secretBroker.redact` |

> Model **biết** `NOTION_TOKEN` tồn tại thì không sao.
> Model **đọc được** giá trị của nó thì giá trị đó đã ra khỏi máy.

### R4 — Dữ liệu ra ngoài phải theo phân loại

"Local-first" **không** có nghĩa dữ liệu không bao giờ rời máy. Dùng API của
Claude/Gemini là context tương ứng đi ra ngoài.

```text
public     → nhà nào cũng được
internal   → chỉ nhà admin đã chấp nhận điều khoản
private    → claude, local
sensitive  → claude, local
secret     → KHÔNG AI CẢ
```

| Luật | Ai canh |
|---|---|
| Ưu tiên định tuyến **không nâng được** ranh giới | `core/brainRouter.routeBrains` · `testPreferredBrainIsDropped…` |
| Mức chưa khai = **ĐÓNG**, không phải mở | `testUnknownClassificationIsClosedNotOpen` |
| `private`/`sensitive` không sang nhà miễn phí | `testFreeProvidersNeverGetPrivateData` |
| Cắt khối thì phải **nói với model là đã cắt** | `ops/nao.py:_bao_da_cat` |

Bảng này sinh ra từ một phép đo, không từ suy luận: **27/08, một lượt đi ra
37.282 byte**, trong đó có hồ sơ đời tư (giờ dậy, nghề, nơi ở) và số dư từng
ví — sang một nhà miễn phí mà admin chưa từng đọc điều khoản.

### R5 — Tiền thật phải hỏi, mỗi lần

| Luật | Ai canh |
|---|---|
| Khai `paidApi` nếu tiêu tiền thật (L8) | `ops/codemap.py --check` |
| `paidApi` **không bao giờ** whitelist được | `core/contracts.Capability.canWhitelist` · `testPaidCapabilityNeverGets…` |
| Có trần tháng, chạm trần thì chặn | `core/policy._ruleExternalSpendCap` |
| Giá đặt **đầu câu** duyệt, không giấu ở cuối | `core/policy._needApproval` |

> Đó là thứ phân biệt "đồng ý làm" với "đồng ý trả tiền".

### R6 — Repo lạ không bao giờ được chạy

Cấm tuyệt đối: `clone → install → run → Main`.

| Luật | Ai canh |
|---|---|
| Bộ soi **chỉ đọc file**, không `subprocess` | `testAcquisitionModuleImportsNoProcessRunner` |
| Bắt script chạy tự động lúc cài | `testAutoRunScriptIsHighSeverity` |
| Không thoát ra khỏi `lab/` qua `../` | `testPathTraversalIsBlocked` |
| Thăng cấp đòi bằng chứng + admin duyệt | `core/lab.checkPromotionReadiness` |

### R7 — Cửa vào không được phép sập

| Luật | Ai canh |
|---|---|
| Mọi `subprocess.run(timeout=…)` có `except TimeoutExpired` | `core/execution.py` · `testTimeoutReturnsReportableResult` |
| Thiếu lệnh → báo được, không văng traceback | `testMissingEntrypointIsReported` |
| Một luật event hỏng không làm câm cả bus | `testRuleFailureDoesNotKillTheBus` |
| Mã thoát 0 **không** nghĩa là chạy được | `core/execution.looksSuccessful` |
| Cắt log từ **ĐUÔI** (traceback để loại lỗi ở dòng cuối) | `testLastLineOfTracebackSurvives` |

---

## 2. Chỗ đang mỏng — nói thẳng

Một tài liệu bảo mật chỉ kể phần đã làm được là một tài liệu gây hại.

| Chỗ mỏng | Thật ra thế nào |
|---|---|
| **Cô lập** | Mới là **logic**, chưa có container/VM/cgroup. Chặn tai nạn và chặn model đi lạc; **không** chặn mã độc cố tình. `core/isolation.isolationMaturity()` nói đúng điều này. |
| **`browserCompany`** | Chữ trên trang lạ đi vào phần quyết định của agent. Đang bị cắt năng lực (không đăng nhập, hồ sơ trắng, danh sách đen tên miền, trần bước) nhưng đây vẫn là chỗ mỏng nhất. |
| **Bộ dò secret trong memory** | Heuristic. Bắt được những hình dạng hay gặp, **không** bắt hết. Nó là lớp hai, không thay được R3. |
| **`redact()`** | Lớp cuối. Phải dùng tới nó nghĩa là đã rò ở trên rồi. |
| **Secret broker** | Đã có phiếu và sổ, nhưng `ops/` **chưa** gọi vào. Hôm nay secret vẫn đi thẳng từ `os.environ` qua `core/execution`. Đây là việc còn dang dở, không phải việc đã xong. |

---

## 3. Soát nhanh

```bash
python3 ops/codemap.py --check      # luật kiến trúc + paidApi + tên trường
python3 ops/namingAudit.py --check  # từ điển tên có nói dối không
python3 tests/regression/run.py     # toàn bộ hàng rào ở trên
```

Trước mỗi lần đẩy lên GitHub:

```bash
git remote -v
curl -s -o /dev/null -w '%{http_code}\n' https://api.github.com/repos/Bloor7/companySpec
git ls-files | grep -iE '\.env|secret|token'
```

`404` = private (đúng). `200` = **PUBLIC, DỪNG LẠI** — repo này có quyền ghi
vào Notion, ví tiền và lịch của admin.
