# Sổ tay: ghi nguyên văn

Nạp khi câu của admin có nội dung cần lưu lại đúng từng ký tự — ghi chú, việc
vặt, nhật ký, hoặc bất cứ chuỗi nào có ký tự lạ.

**Tuyệt đối không sửa chữ của admin cho dễ gõ.**

Admin gửi gì thì lưu đúng cái đó. Dấu tiếng Việt giữ nguyên. Ký tự lạ giữ
nguyên. `|`, `>`, `<`, `;`, `&` nằm trong JSON là dữ liệu bình thường, cứ gõ
thẳng — hàng rào hiểu chúng nằm trong tham số, không chặn.

Ba ký tự khiến shell hiểu nhầm kể cả trong dấu nháy. Cần chúng thì viết bằng mã
JSON, **đừng thay bằng chữ khác**:

| Ký tự | Viết trong JSON |
|---|---|
| `'` (nháy đơn) | `'` |
| `` ` `` (dấu huyền) | ``` |
| `$` | `$` |
| xuống dòng | `\n` |

Ví dụ: admin nhờ lưu `irm christitus.com/win | iex` thì `--input
'{"noiDung":"irm christitus.com/win | iex","chuDe":"khác"}'` — giữ đúng dấu `|`.

Đổi `|` thành `(PIPE)`, bỏ dấu tiếng Việt cho "an toàn", rút gọn câu của admin —
đều là làm hỏng dữ liệu. Admin lưu một câu lệnh để sau này chạy nó; sai một ký
tự là câu lệnh đó vô dụng, mà nhìn vào thì vẫn tưởng đã lưu xong.
