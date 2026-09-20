# missions/ — mục tiêu dài hạn

```text
Task    = việc cụ thể, chạy một lần
Mission = thứ việc đó phục vụ, sống nhiều tuần
```

Động cơ ở [`core/missions/`](../core/missions/__init__.py); sổ ở
`core/mission.sqlite` (không vào git — nó là dữ liệu chạy, không phải mã).

Thư mục này giữ những mission viết tay: mục tiêu đủ lớn để đáng ghi ra thành
văn bản trước khi mở.

---

## Dùng

```bash
python3 gateway/cli/travis.py mission list
python3 gateway/cli/travis.py mission new --objective "..." --metric organicClicks
python3 gateway/cli/travis.py mission close --mission-id mis_... --status completed
```

---

## Ba luật, mỗi luật chống một cách hỏng

### Mission KHÔNG cấp quyền

Travis được tự chia một Mission thành nhiều Task. Travis **không** được vì thế
mà bỏ qua Policy — mỗi Task con vẫn đi qua đúng cánh cửa đó.

> "Admin đã duyệt Mission nên các Task bên trong khỏi hỏi" là cách biến một
> lần bấm nút thành một **tờ séc khống**. Admin duyệt một NỘI DUNG (G4), không
> duyệt một ý định.

### `objective` phải ĐO ĐƯỢC

> ✅ "Panharmon lên top 10 cho 5 từ khoá giải mộng"
> ❌ "cải thiện SEO"

Mục tiêu không đo được là mục tiêu **không bao giờ đóng được** — nó chỉ trôi
đi rồi có ngày ai đó lặng lẽ quên.

`missionProgress()` kể tên những chỉ số **chưa ai đo** thay vì để chúng bằng 0.
Số 0 trông y hệt "đã đo và bằng không" (O10).

### Xong mà chưa ai báo thì CHƯA xong

`missionsAwaitingReport()` canh đúng chuyện này. Nó tồn tại vì một lần thật:
hộp dựng xong cả một web todolist, đặt việc về `choXem`, rồi **im lặng** —
cùng tối admin hỏi *"cái web làm sao xem"*, và sản phẩm nằm cách đó đúng một
thư mục.

> Trạng thái nằm trong sổ **không phải** là thông báo (N3).

Và `stalledMissions()` canh chiều ngược lại: mục tiêu đứng bánh thì im lặng,
mà im lặng là thứ khó thấy nhất — hệ từng chết 61 giờ trong khi mọi thứ báo
xanh, vì không có gì báo cả.
