# AUTONOMY.md — nới quyền bằng bằng chứng, không bằng niềm tin

> Bảo mật: [SECURITY.md](SECURITY.md) · Từ vựng: [CORE_CONTRACT.md](CORE_CONTRACT.md)
> · Code: [`core/autonomy.py`](../core/autonomy.py)

---

## Câu nói gốc

> **Autonomy không đồng nghĩa với quyền lực tuyệt đối.**
> Nó phải tăng **cùng lúc** với verification, permission, isolation và evidence.

Tăng autonomy là tăng thứ hệ được làm **mà không hỏi**. Chỉ an toàn khi bốn
thứ kia tăng theo — bằng không ta chỉ đang bịt mắt rồi đi nhanh hơn.

---

## Năm mức

| Mức | Được làm | Chưa được |
|---|---|---|
| **0** | Chỉ đọc | Mọi thứ khác |
| **1** | Chạy việc an toàn | Tự kết luận là xong |
| **2** | Chạy **và tự kiểm chứng** | Tự sửa khi trượt |
| **3** | Chạy, kiểm chứng, **tự sửa khi trượt** | Tự lái mục tiêu dài |
| **4** | Tự lái mission dài hơi | — |

Hai điều kiện để làm mà không hỏi, **không phải một**:

```python
mayActWithoutAsking(level, riskTier)   # level >= 2 VÀ rủi ro cho phép
```

---

## Trần cứng theo rủi ro — không thương lượng

```text
read          → tối đa mức 4
low           → tối đa mức 3
write         → tối đa mức 2
high          → tối đa mức 1
irreversible  → mãi mãi mức 0
```

> **Không bằng chứng nào nâng qua được trần này.**
>
> `irreversible` dừng ở 0 vĩnh viễn. "Hệ đã làm đúng 500 lần" không phải lý lẽ
> với thứ không lấy lại được — lần thứ 501 vẫn xoá mất thứ không có bản sao.

---

## Mức được **tính ra**, không được **đặt**

Không có file cấu hình nào ghi "forge được mức 3". Mức tính từ lịch sử đo được
trong sổ audit:

```python
earnedAutonomy(trackRecord, riskTier)
```

Vì sao không đặt tay: một con số gõ vào file chỉ phản ánh **niềm tin của người
gõ vào hôm đó**. Niềm tin không có hạn sử dụng; bằng chứng thì có.

### Bốn luật tính

**1. Chưa chạy lần nào → tỉ lệ thành công là `0.0`, không phải `1.0`.**

"Chưa hỏng lần nào" và "luôn chạy đúng" là hai câu rất khác nhau. Nhầm chúng
là cách một thứ chưa ai thử được trao quyền tự chạy — cùng họ với O10, đừng để
con số 0 trông như một kết quả tốt.

**2. Chỉ `completed` tính là thành công.**

`ok` của company nghĩa là "chạy trót lọt", **không** phải "đã kiểm chứng". Chỉ
[Verification](../core/verification.py) mới đẩy được lên `completed`.

**3. Một lần hỏng không hoàn tác được → tụt thẳng về 0.**

Bất kể thống kê đẹp cỡ nào. Trung bình che mất cái đuôi, mà **cái đuôi mới là
thứ giết người**: 99 lần ghi đúng không bù được một lần xoá nhầm.

**4. Thang đi xuống được.**

Một cái thang chỉ đi lên là một cái thang không ai dám trèo.

---

## Nghịch lý có chủ ý

> **Càng được tự do thì càng phải chứng minh NHIỀU hơn.**

```python
requiresVerification(level)   # True từ mức 2 trở lên
```

Trực giác nói ngược: tin tưởng hơn thì kiểm ít hơn. Nhưng làm vậy là công thức
để một hệ trôi dần vào chỗ không ai biết nó đang làm gì — và lúc phát hiện thì
đã trôi rất xa.

Tương tự, **tự sửa khi trượt là đặc quyền của mức 3**. Dưới mức đó, hỏng thì
**dừng và báo**. Tự thử lại khi chưa biết vì sao hỏng là cách biến một lỗi
thành một vòng lặp — và `L4` tồn tại vì điều đó đã xảy ra thật.

---

## Mức đề xuất theo loại việc

| Loại việc | Mức | Vì sao |
|---|---|---|
| Nghiên cứu, đọc web | 2–3 | Không đổi gì của admin |
| Sửa code ở `dev` | 2–3 | Có test, có build, hoàn tác được bằng git |
| Thí nghiệm trong Lab | 2–3 | Lab **được phép** hỏng (P6) |
| Deploy staging | 2 + policy | Hoàn tác được, nhưng có người nhìn thấy |
| Deploy production | **Admin duyệt** | — |
| Đổi chính sách quyền | **Admin duyệt** | Đổi luật là đổi mọi thứ luật đang giữ |
| Đổi Core security | **Admin duyệt** | — |

---

## Hôm nay hệ đang ở đâu

Nói thẳng, vì một tài liệu autonomy nói quá lên thì chính nó là rủi ro:

| | Trạng thái |
|---|---|
| Thang mức, trần rủi ro, phép tính | **Xong** — `core/autonomy.py`, 30 ca thử |
| Verification làm cổng lên mức 2 | **Xong** — `core/verification.py`, chạy trên mọi lời gọi company |
| Sổ audit ghi đủ để TÍNH được mức | **Xong** — `policyDecision` + `verificationJson` trong `taskLog` |
| Đọc được mức đã kiếm | **Xong** — `python3 ops/travis.py autonomy` |
| `ops/` **áp** mức đó để bớt hỏi admin | **CHƯA** |
| Hệ thật đang chạy ở | **mức 1** với mọi thứ: chạy được, nhưng mọi việc `write` vẫn hỏi admin |

Có một lý do cụ thể khiến mức chưa nhích lên, và nó đáng đọc: sổ hiện **chưa
có dòng nào `completed`**. Company trả `ok` nghĩa là "chạy trót lọt", và
`recordFromAuditRows` cố ý chỉ đếm `completed` là thành công. Nên
`earnedAutonomy` trả về 1 cho mọi thứ — **đúng**, không phải hỏng.

Muốn nhích lên thì phải có đường đóng dấu `completed` vào sổ, và đường đó phải
đi qua Verification. Đó là việc tiếp theo, không phải một con số cần chỉnh.

Nghĩa là: cái thang đã dựng và đã kiểm, nhưng **chưa ai trèo**. Đó là trạng
thái đúng — nới quyền phải là một hành động có chủ ý của admin, không phải
thứ tự xảy ra vì code đã sẵn sàng.

---

## Nới mức một cách có chủ ý

```bash
# 1. Xem lịch sử đo được của một năng lực
python3 backOffice/src/backoffice.py report --days 30

# 2. Xem mức nó đã KIẾM ĐƯỢC, và vì sao
python3 -c "
import sys; sys.path.insert(0, '.')
from core.autonomy import TrackRecord, explainAutonomy
from core.contracts import RiskTier
print(explainAutonomy(
    TrackRecord('expenseCompany', 'addExpense',
                totalRuns=40, verifiedSuccesses=40),
    RiskTier.write))
"
```

Câu trả lời luôn kể ra **vì sao** — số lần chạy, tỉ lệ đạt, và trần rủi ro đã
chạm chưa. Không có câu đó thì "hệ được mức 3" là một con số không ai cãi được,
và một con số không ai cãi được là một con số không ai kiểm.
