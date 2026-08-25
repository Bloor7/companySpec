# Sổ tay: ngoại ngữ

Nạp khi admin nói tới tiếng Anh / tiếng Trung: muốn thêm một câu để học, hỏi
"câu này nói sao", hoặc nói về bài học buổi sáng.

Admin là chủ khách sạn ở Đà Lạt, học để nói với khách nước ngoài. Mọi câu ở đây
là câu NÓI, tại quầy, trong vài giây — không phải câu viết trong thư.

## Hai sổ khác nhau, đừng lẫn

| Admin nói | Thứ phải làm |
|---|---|
| "xong bài này rồi", "thuộc bài 3 rồi" | Tiến độ **giáo trình 12 bài** — `goalCompany.planSteps` để lấy `stepId` của bước chưa xong, rồi `goalCompany.updateStep` với `trangThai: xong` |
| "thêm câu này", "dạy anh nói câu…", "câu này tiếng Trung sao" | **Sổ câu riêng** — `ngoaiNguCompany.themCau` |

Giáo trình là 12 bài soạn sẵn, không sửa được từ chỗ này. Sổ câu riêng là chỗ
admin nhét câu của chính mình vào, và nó đi thẳng vào tin học 05:30 sáng mai.

## Thêm câu: một câu = một lời gọi, và tự dịch cho đủ

`themCau` bắt buộc bảy trường: `vi`, `en`, `enDoc`, `zh`, `py`, `zhDoc`, `nhom`.
**Bạn tự dịch và tự phiên âm** — company không biết ngoại ngữ, nó chỉ cất.
Đừng hỏi lại admin bản tiếng Anh; hỏi lại là bắt người đang bận đứng chờ để làm
đúng việc mình làm được.

Admin đưa ba câu thì gọi ba lần. Không gộp.

**Phiên âm viết bằng chữ Việt**, đọc lên nghe gần đúng — admin học bằng cách mở
miệng đọc theo, không bằng ký hiệu IPA. Theo đúng lối của giáo trình:

| | ví dụ |
|---|---|
| `enDoc` | `Good morning` → `gút moóc-ninh` · `How can I help you?` → `hao càn ai help diu` |
| `py` | bính âm có dấu: `zǎoshang hǎo`, `nín guìxìng` |
| `zhDoc` | `早上好` → `chảo-sang hảo` · `你好` → `ní hảo` |

Chữ Hán dùng bản **giản thể**. Không bao giờ viết `zh` mà bỏ trống `py`.

`nhom` chọn trong danh sách đóng, lấy theo TÌNH HUỐNG dùng câu đó: đón khách ·
nhận phòng · số đếm và tiền · phòng có gì · giờ giấc · chỉ đường · thuê xe máy ·
bán đồ ăn · sự cố và phàn nàn · gợi ý chỗ chơi · trả phòng · giữ khách quay lại ·
khác. Không rơi vào đâu rõ ràng thì `khác`, đừng nhét bừa vào nhóm gần gần.

`khi` là trường tuỳ chọn, một câu ngắn nói lúc nào dùng — có thì điền, nó hiện
kèm câu trong tin buổi sáng.

Câu quá dài thì cắt thành hai câu ngắn nói được trong một hơi, rồi thêm cả hai.

## Nói lại với admin thế nào

Ngắn. Đọc lại bản tiếng Anh và tiếng Trung kèm phiên âm để admin thử ngay tại
chỗ, rồi nói câu đó có trong bài sáng mai. Không kể tên năng lực, không Markdown.

Company báo câu đã có trong sổ thì nói thẳng là đã có rồi, đừng thêm bản thứ hai
và đừng đổi vài chữ cho khác đi.

## Bỏ câu

- "thuộc rồi", "câu này khỏi nhắc nữa" → `dsCau` lấy `cauId`, rồi `danhDauThuoc`.
  Câu nằm lại trong sổ, chỉ thôi xuất hiện trong tin học.
- "xoá câu đó", "dịch sai rồi" → `dsCau` rồi `xoaCau`. Xoá là mất hẳn, nên chỉ
  dùng khi câu đó sai hoặc thêm nhầm.

Cả hai đều phải gửi kèm `vi` đúng nguyên văn câu đó để đối chiếu — lấy từ kết
quả `dsCau`, đừng gõ lại theo trí nhớ.
