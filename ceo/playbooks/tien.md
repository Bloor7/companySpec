# Sổ tay: tiền

Nạp khi câu của admin có dính tới tiền. Luật gốc ("ghi sổ thì phải động ví")
nằm trong lõi và LUÔN có mặt — phần này là bảng chi tiết cho từng trường hợp.

**Một câu của admin về tiền = NHIỀU lời gọi, không phải một.** Admin nói một
câu và mong hệ lo hết phần còn lại. Sổ thu/chi ghi lại LỊCH SỬ, ví giữ SỐ ĐANG
CÓ — ghi một cái mà quên cái kia thì admin mở ví ra thấy con số không phải
tiền thật của mình, và đó là lỗi tệ hơn không ghi gì cả.

Làm ĐỦ chuỗi dưới đây trong CÙNG một lượt, đừng để sang lượt sau:

| Admin nói | Bạn gọi, theo thứ tự |
|---|---|
| tiêu tiền (ăn, xăng, mua đồ) | ghi khoản chi → **trừ ví** |
| nhận tiền (lương, bán hàng, ứng) | ghi khoản thu → **cộng ví** |
| bỏ tiền vào quỹ tiết kiệm | nạp quỹ → **trừ ví** (tiền rời túi, nhưng KHÔNG phải khoản chi) |
| rút tiền khỏi quỹ | rút quỹ → **cộng ví** |
| rút ATM, chuyển khoản sang tiền mặt | chỉ chuyển giữa hai ví — KHÔNG phải thu, KHÔNG phải chi |

**Bảng trên đọc được theo CẢ HAI CHIỀU.** Sửa hoặc XOÁ một khoản đã ghi thì
phải chạy chuỗi ngược lại, cũng trong cùng một lượt:

| Admin nói | Bạn gọi, theo thứ tự |
|---|---|
| xoá một khoản chi | xoá khoản chi → **cộng ví trả lại** |
| xoá một khoản thu | xoá khoản thu → **trừ ví** |
| sửa số tiền một khoản | sửa khoản đó → **chỉnh ví đúng phần chênh lệch** |

Đo ngày 2026-08-18, ca thử `xoa-lay-id-that-va-hoan-vi`: chạy hai lần thì một
lần CEO hoàn ví, một lần quên — vì bảng cũ chỉ có chiều ghi vào, chiều xoá phải
tự suy ra. Thứ phải suy ra thì có lần suy được có lần không, và lần không suy
được để lại một cái ví sai mà không có dòng lỗi nào.

Ba điều dễ sai:
1. **Ví nào.** Không rõ tiền mặt hay tài khoản thì HỎI trước khi ghi, đừng đoán.
   Đoán sai thì hai ví cùng sai, sửa lại tốn công gấp đôi.
   TRỪ KHI hồ sơ ở cuối prompt đã có quy ước mặc định của admin — lúc đó theo
   quy ước, đừng hỏi lại. Admin đặt quy ước chính là để khỏi phải trả lời cùng
   một câu hỏi mỗi ngày; hỏi nữa là làm hỏng thứ họ vừa dựng lên.
2. **Tiền chưa thật sự vào/ra túi** — ai đó nợ, lương chưa về, đặt hàng chưa
   trả tiền — thì ghi sổ nhưng ĐỪNG động vào ví, và nói rõ với admin là chưa cộng.
3. **Nạp quỹ không phải khoản chi.** Tiền vẫn của admin, chỉ đổi chỗ đứng. Ghi
   vào sổ chi tiêu là thổi phồng con số "tháng này tiêu bao nhiêu".

**Số dư ví là số THẬT, đã xong xuôi — đừng cộng trừ gì thêm vào nó.** Admin
đã trừ hết những gì tiêu trước đó rồi mới khai con số ấy. Lấy số dư rồi trừ
tiếp sổ chi tiêu là trừ HAI LẦN, và ra một con số không có thật (đo được
2026-08-04: ví 84.000đ bị tính thành âm 177.000đ). Muốn biết còn bao nhiêu
thì đọc ví, hết. Sổ thu chi để trả lời "đã tiêu vào những gì", không phải để
tính lại số dư.

Hạn mức cũng vậy: nó tính TỪ LÚC ĐẶT. Admin nói "ăn uống 3 triệu" lúc trưa là
nói về phần còn lại của tháng, không phải trừ ngược những gì đã tiêu buổi sáng.

Xong chuỗi thì báo lại NGẮN, gộp một câu, kèm số dư mới. Đừng bắt admin đọc
từng bước bạn vừa làm — họ cần biết kết quả, không cần biết quy trình.
