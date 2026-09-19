# employees/ — người, không phải bộ não

Mỗi thư mục là **một danh tính bền vững**. Đọc
[docs/CORE_CONTRACT.md](../docs/CORE_CONTRACT.md) §6 trước khi thêm ai.

```text
Employee = identity + role + personality + expertise
         + responsibilities + memory + permissions + brainPreference
```

---

## Hai luật, và vì sao chúng tồn tại

### E-1 — Đổi Brain không làm mất Employee

`forge` hôm nay chạy bằng Claude, mai bằng Gemini, vẫn là `forge`: vẫn giữ
nguyên trí nhớ, quyền hạn và cách làm việc.

Đây không phải chuyện thẩm mỹ. Hệ đã chết một lần vì cả bộ não là một hằng số
trong code: hết hạn mức gói Pro thì không ghi nổi một khoản chi, dù mọi company
vẫn chạy tốt — chúng là code cứng, chỉ là người gọi đã chết.

### E-2 — `cannot` là luật CỨNG

`cannot` thắng mọi thứ khác, kể cả `permissions` khai ngay bên dưới nó. Một
luật cấm mà có thể bị một luật cho phép lấn qua thì nó không phải luật cấm.

> **Personality KHÔNG tạo permission.** `forge` được mô tả là "mạnh dạn" không
> vì thế mà được deploy production. Tính cách và quyền hạn là hai hệ độc lập —
> tính cách nói *cách* làm, permission nói *được làm gì*.

---

## Vì sao chỉ có năm người

Kế hoạch §41 xếp "20+ employee" vào nhóm **không làm sớm**, và có lý do đo
được: bảng bẫy ghi rằng để agent lái một việc đã biết trước cách làm thì tốn
4–9 phút và ba lần đều trượt, trong khi kịch bản cứng chạy 16 giây, đúng mọi
lần, 0đ.

> Employee chỉ đáng dùng khi **không biết trước** phải làm gì.
> Việc lặp lại thì viết thẳng thành company.

Thêm người thứ sáu thì phải trả lời được: *việc này không biết trước cách làm
ở chỗ nào, và vì sao bốn người kia không làm được?*

---

## Năm người

| Employee | Vai | Không được làm |
|---|---|---|
| `atlas` | Kiến trúc, kế hoạch, nợ kỹ thuật | Sửa code, deploy |
| `forge` | Viết code, sửa lỗi | Chạm production, đọc secret |
| `iris` | Giao diện, trải nghiệm, kiểm thị giác | Chạm hạ tầng |
| `sage` | Nghiên cứu, kiểm nguồn | Ghi bất cứ đâu |
| `sentinel` | Bảo mật, soát quyền, kiểm chứng | Tự sửa thứ mình vừa soát |

`sentinel` không được sửa thứ nó vừa soát là có chủ ý: người gác cửa mà tự mở
cửa cho mình thì không còn là người gác cửa.

---

## Thêm một người

Thêm **dữ liệu**, không sửa Core (W3′):

```bash
mkdir employees/<tên>
$EDITOR employees/<tên>/employee.yaml
python3 -c "from core.employeeRegistry import loadEmployees; loadEmployees()"
python3 tests/regression/run.py --only employee
```

Phải sửa `core/` để thêm được một employee nghĩa là hợp đồng đang rò. Sửa hợp
đồng, đừng sửa Core.
