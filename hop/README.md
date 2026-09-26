# `hop/` — cái hộp: kẻ thực thi ngồi riêng, nối vào hệ bằng đúng một cửa

CEO là **bộ não**: nó nghĩ, nó nói chuyện với admin, và nó chỉ có đúng một
quyền — `Bash(python3 gateway/cli/dispatch.py:*)`. Hộp là **đôi tay**: nó sửa mã, chạy
lệnh, mở trình duyệt, làm những việc dài mà bộ não cố ý không được phép làm.

Trang này là hợp đồng giữa hai thứ đó. Đọc hết trước khi nới bất cứ điều gì —
mọi dòng ở đây đều là một cánh cửa đang đóng, và cánh nào cũng có lý do.

---

## Vì sao hộp tồn tại

Đo 18/09/2026, 30 ngày gần nhất: **5.713 lời gọi company**, trong đó 3.857 là
scheduler tự dò nhắc, 762 là bức tranh tự tra, 131 là shim ca thử. Thật sự do
admin sai khiến: **~960 lượt**, và gần như toàn bộ là **tiền và lịch**.

Bốn company biết *làm việc* — `researchCompany`, `writerCompany`, `seoCompany`,
`panharmonCompany` — **không được gọi một lần nào** trong 30 ngày đó.

Đọc hai con số cạnh nhau thì ra chẩn đoán: hệ này có rất nhiều **sổ** và gần
như không có **tay**. Hộp sinh ra để lấp đúng chỗ đó, và **không** để thay thế
CEO: bộ não vẫn ở nguyên chỗ cũ, với nguyên bộ hàng rào cũ.

---

## Ranh giới — bốn điều không được vượt

### 1. Hộp không giữ khoá nào của hệ

Hộp chạy trong **distro WSL riêng** (`openclaw`), hệ tệp tách hẳn với
`/home/tsix`. Nó **không đọc được `ops/.env`** — không phải vì được dặn đừng
đọc, mà vì file đó không tồn tại trong tầm nhìn của nó.

Muốn chạm ví tiền, Notion, lịch? Gọi ngược qua **cầu dispatch**, và đi qua
đúng bộ máy cũ: phiếu duyệt, mã dùng một lần, hạn mức, nhật ký. **T2 còn
nguyên** — `dispatch.py` vẫn là cổng duy nhất ra mọi company.

Điều này biến một câu hỏi bảo mật khó thành một câu hỏi dễ: không phải *"hộp
có bị dụ làm bậy không"* (không trả lời được), mà *"hộp có gì để mất"* (trả lời
được: không có gì).

### 2. Hộp làm trên BẢN SAO, không làm trên repo thật

Workspace của hộp là `~/work/companySpec` — một clone git, **không có**
`ops/.env`, **không có** sổ sqlite dữ liệu thật. Hộp làm xong thì đẩy lên một
nhánh `y/<mã việc>` và **dừng ở đó**.

**Hộp không bao giờ tự gộp vào `main` của repo thật.** Admin xem diff rồi mới
gộp. Đây là chỗ nói "không" dứt khoát chứ không phải chỗ để cân nhắc: một kẻ
thực thi tự gộp là một kẻ thực thi không ai soát được.

### 3. Skill của người lạ: mỗi lần một cái, đọc mã, ghim hash

`VoltAgent/awesome-openclaw-skills` liệt kê **5.300+ skill** trong 28 nhóm —
sau khi đã **loại ~7.215 mục** khỏi registry gốc vì spam, trùng lặp, mô tả rác
và **mã độc phát hiện qua audit bảo mật**. Ngay dưới đó, chính repo ấy ghi:
*"curated, not audited"*.

Đọc hai câu ấy cạnh nhau là đủ hiểu: người lọc phải vứt đi hơn bảy nghìn mục,
rồi vẫn không dám bảo đảm phần còn lại. Cộng thêm hai sự cố có thật của 2026:
chiến dịch ClawHavoc hồi tháng 1 (skill ghi thẳng vào `MEMORY.md`/`SOUL.md` để
bám qua nhiều phiên) và bản demo rút dữ liệu của Cisco hồi tháng 3.

**Luật:**

- Danh sách đó dùng như **tài liệu tham khảo để TỰ VIẾT**, không phải để nạp cả rổ.
- Buộc phải cài: **mỗi lần một cái**, đọc mã trước, ghim `source` +
  `computedHash` vào `skills-lock.json` — cơ chế repo đã có sẵn, không cần
  nghĩ ra cái mới.
- Không cài "cho đủ bộ". Đây đúng thứ `HARNESS.md` §5 xếp vào *KHÔNG nên học
  theo*.

### 4. Hạn mức là túi chung — CEO được ưu tiên

Hộp và CEO ăn chung một gói Claude Pro. Hộp cày cả ngày rồi 11 giờ đêm admin
nhắn "ghi 50k ăn tối" mà Claude báo hết hạn mức, thì hệ tụt xuống `naoPhu` —
vẫn ghi được, nhưng đó là **đánh đổi thứ đang chạy rất tốt để lấy thứ đang thử
nghiệm**. Không đáng.

Nên hộp phải:

- **Dừng ngay khi `quotaSignal` kêu** — gọi `xuongCompany.tamDung` với
  `lyDo: hetHanMuc` và `tiepLuc` đúng giờ nhà cung cấp báo reset.
- **Ghi sổ mọi lượt.** Bài học "bộ đo tự đứng ngoài phép đo": thứ nào tiêu hạn
  mức thì phải nằm trong cùng bảng đang đếm, tách bằng nhãn — hai bảng thì sớm
  muộn có người cộng một bảng rồi tưởng đã cộng hết.

---

## Vòng làm việc

```
admin nhắn ý tưởng bất cứ lúc nào  ("/tay them <ý tưởng>", hoặc nói với CEO)
   └─► xuongCompany.themViec                    (sổ, không phải tay)
            │
timer 5 phút trong hộp (hop-tho.timer)
   └─────► xuongCompany.nhanViec                → GÓI TIẾP TỤC
            │   việc là gì · các bước đã xong · MỘT CÂU "bước kế tiếp" · nhánh git
            │
            ├─ làm trên ~/work/companySpec, nhánh y/<mã việc>
            ├─ mỗi bước: xuongCompany.ghiBuoc   (cũng là một nhịp tim)
            ├─ tự kiểm: codemap --check → tests/evals/run.py → chạy thử
            │
            ├─ hết hạn mức / mất mạng ─► xuongCompany.tamDung + tiepLuc
            ├─ mất điện ───────────────► không ai ghi gì; nhịp tim tắt
            │                            máy bật lại → donDep → nhanViec
            └─ xong ───────────────────► xuongCompany.xongViec (choXem)
                                             │
                             admin xem diff rồi tự gộp vào main
```

**Mất điện không cần ai ghi lại.** Nhịp tim tắt là đủ: `dsViec` gọi thẳng việc
đó là **ĐỨT GÁNH** ngay lúc đọc, `donDep` đưa nó về hàng đợi, và `nhanViec` trả
lại đúng gói tiếp tục cũ. Không phải đọc lại từ đầu — đó là toàn bộ điểm của
thiết kế này.

---

## Hai loại việc — và vì sao phải tách

| | `repo` | `duAn` |
|---|---|---|
| Là gì | sửa chính repo companySpec | một dự án riêng: web, bot, script |
| Làm ở đâu | bản sao `~/work/companySpec`, nhánh `y/<mã việc>` | `~/work/duan/<mã việc>-<tên>`, git riêng |
| Lời nhắc cho não | "đọc CLAUDE.md trước, nhất là bảng Đã sửa rồi" | "đây là dự án riêng, đừng đi tìm CLAUDE.md" |
| Thước đo "xong" | `codemap --check` thoát 0 | có tệp thật **và** có README nói cách chạy |
| Giao kết quả | đẩy nhánh lên gương, admin xem diff rồi gộp | admin mở thẳng từ Windows Explorer |

Đường Windows của một dự án: `\\wsl.localhost\openclaw\home\hop\work\duan\<mã việc>-<tên>`.

**Vì sao không gộp một loại cho gọn:** thước đo là chỗ khác nhau thật sự.
`codemap --check` nói được điều gì đó về repo companySpec, và **không nói gì**
về một web todolist. Dùng một thước cho cả hai thì hoặc chặn oan một dự án
đúng, hoặc gật bừa cho một dự án rỗng. Lời nhắc cũng thế: bảo não "đọc
CLAUDE.md trước" trong một thư mục trống là dạy nó đi tìm thứ không tồn tại.

Tên thư mục **bỏ dấu tiếng Việt** — không phải vì Linux hay Windows không mở
được, mà vì đường dẫn ấy còn đi qua dòng lệnh, npm, git remote và những script
viết vội, mỗi chỗ một cơ hội hỏng vì lý do chẳng liên quan gì tới việc đang làm.

## Thực đơn `/tay` — nói chuyện với xưởng mà không đánh thức CEO

`gateway/telegram/poller.py` bắt tiền tố `/tay` và gọi thẳng company, không mở phiên CEO:

| Gõ | Làm gì |
|---|---|
| `/tay` | in thực đơn |
| `/tay xem` | xưởng đang làm gì, việc nào chờ đại ca xem |
| `/tay nhatky` | mấy hôm nay xưởng làm được những gì |
| `/tay them <ý tưởng>` | **sửa hệ này** — việc loại `repo` |
| `/tay duan <ý tưởng>` | **dự án riêng** — việc loại `duAn` |
| `/tay api <từ khoá>` | tra danh mục API công khai |

**Cố ý không có lệnh tuỳ ý.** Mỗi mục gọi một năng lực đã khai sẵn trong
manifest; không mục nào chạy chữ do admin gõ. Và **không mục nào sai khiến cái
hộp** — hộp tự lấy việc theo timer của nó, nên chiều host→hộp không tồn tại để
mà lỡ nới ra.

Ba lý do đi thẳng company thay vì qua CEO, xếp theo sức nặng: **rẻ** (một phiên
CEO tốn hạn mức gói Pro — thứ đang là nút thắt), **chắc** (việc đã biết trước
cách làm thì viết thẳng), **rõ** (thực đơn đếm được).

## `hop` KHÔNG được mang uid 1000

Các distro WSL2 chạy chung một máy ảo, nên chung **một cây cgroup**. `tsix`
(Ubuntu) và `hop` cùng uid 1000 thì cùng tranh
`/user.slice/user-1000.slice/user@1000.service`. Ngày 25/09/2026 hộp dựng
trước Ubuntu ba giây, systemd 249 của Ubuntu chết `219/CGROUP`, và cả ngày
không có poller, không cron, không hẹn giờ — dù terminal mở suốt. Hôm trước
Ubuntu tới trước nên chạy được: một cuộc đua, không phải một cấu hình.

Sửa một lần, chạy từ Windows (thợ đang làm dở thì đợi xong, và ĐÓNG mọi tab
terminal openclaw — một phiên `-bash` của `hop` còn mở là `usermod` từ chối
"user hop is currently used by process", đã dính lần chạy đầu 26/09):

```powershell
wsl -d openclaw -u root -- sh -c "loginctl disable-linger hop; loginctl terminate-user hop; systemctl stop user@1000; pkill -9 -u hop; sleep 2; usermod -u 2000 hop && groupmod -g 2000 hop && chown -R hop:hop /home/hop; loginctl enable-linger hop; id hop"
wsl -d Ubuntu-22.04 -u root -- systemctl restart user@1000   # dừng user@1000 bên hộp có thể giết cgroup chung
python ops/soatHop.py                                        # phải in "uid tách nhau"
```

## Hộp cách ly tới đâu — ĐO 26/09, không đoán

| Thứ | Hiện trạng |
|---|---|
| sudo, ổ Windows, `wsl.exe` | không có ✓ |
| Tiến trình của Ubuntu | không thấy (pid namespace riêng) ✓ |
| localhost của Ubuntu | chỉ với tới `8787` (cầu) ✓ |
| RAM / swap / CPU / số tiến trình | có trần: `gioi-han-hop.conf` — thử phá xin 3,5 GB → OOM giết TRONG hộp, Ubuntu không hề hấn ✓ |
| Kernel, cây cgroup | **chung** với Ubuntu ✗ — gốc của sự cố 25/09 |
| Mạng ra Internet | **mở hoàn toàn** ✗ — CHƯA chặn vì thợ cần API Claude và npm/pip; chặn là quyết định của admin, không phải chỗ để đoán |
| Tiến trình mở bằng `wsl -u hop` | rơi vào `init.scope`, **không** chịu trần slice. Thợ thật (`hop-tho.service`) thì chịu. Đừng đo trần bằng `wsl -u hop` — nó báo "không bị chặn" và sai |

Tức là: hộp là **ranh giới quyền và dữ liệu** (không khoá, không ổ, một cửa),
đã có **trần tài nguyên**, nhưng CHƯA là sandbox mạng hay sandbox kernel.
Trước khi cho thợ chạy thứ lạ (skill người lạ, repo chưa soát) thì hai ô ✗
cuối phải được quyết.

## Cách kiểm

```bash
python3 gateway/cli/dispatch.py list                    # hộp có xuất hiện không
python3 ops/codemap.py --check                  # luật kiến trúc
wsl.exe -l -v                                   # distro openclaw có sống không
```

Trong hộp:

```bash
wsl -d openclaw -u hop -- systemctl --user list-timers hop-tho.timer
wsl -d openclaw -u hop -- journalctl --user -u hop-tho -n 20
```

Và phép kiểm thật sự của cả trang này, chạy được bất cứ lúc nào: **rút điện
giữa lúc hộp đang làm, bật lại, rồi xem nó có tự nói được mình đang dở việc gì
không.** Đọc mã thì không trả lời được câu đó.
