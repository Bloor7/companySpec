#!/usr/bin/env python3
"""Thư viện gọi Notion — dùng chung cho mọi company cất dữ liệu vào Notion.

C4.2 — file này chỉ biết "gọi Notion thế nào", KHÔNG biết "chi tiêu là gì".
Không có quyết định nghiệp vụ nào ở đây. Company nào cần gì thì tự dựng payload.

File này cố ý chỉ dùng thư viện chuẩn — Notion API là REST, kéo thêm SDK vào
chỉ để gọi bốn endpoint là đổi một phụ thuộc lấy sự tiện lợi không đáng.
Đó là lựa chọn riêng cho file này, KHÔNG phải luật chung của dự án: F4 nói về
việc không commit môi trường chạy vào repo, không cấm thư viện ngoài.
"""
import json
import os
import time
import urllib.error
import urllib.request

API = "https://api.notion.com/v1"
VERSION = "2022-06-28"


class NotionError(RuntimeError):
    """Lỗi từ phía Notion. Company bắt cái này rồi trả companyResult status=failed."""


# Timeout PHẢI nhỏ hơn hẳn ngân sách của năng lực, không được bằng.
#
# Bản cũ để 20 giây — đúng bằng `maxDurationSec: 20` của 33 năng lực. Khi Notion
# chậm thì hai đồng hồ chạm vạch cùng lúc và dispatcher luôn thắng: nó GIẾT tiến
# trình trước khi company kịp bắt NotionError để trả về một câu tử tế. Admin nhận
# "Quá 20s — cắt.", không ai biết là Notion chậm, và dòng taskLog trong sổ riêng
# của company nằm lại 'running' vĩnh viễn.
#
# Đo được 2026-08-13: calendarCompany.upcomingEvents kẹt 'running' 6 lần liên
# tiếp từ 12:39Z đến 13:59Z, rồi tự khỏi lúc 14:15Z và chạy đều 620ms từ đó.
# Một lời gọi bình thường mất ~0,4 giây, nên 8 giây là gấp 20 lần mức thường —
# thừa sức cho lúc Notion ì, mà vẫn chừa 12 giây để company kịp trả lời tử tế.
#
# Cần lâu hơn (quét cả sổ, ghi hàng loạt) thì TRUYỀN timeout riêng, đừng nâng
# con số này lên: nâng ở đây là nâng cho cả 36 năng lực đang có ngân sách ≤ 20s.
def _request(method: str, path: str, token: str, body: dict | None = None,
             timeout: int = 8, thu_lai: int = 1) -> dict:
    """Gọi Notion, thử lại MỘT lần khi trục trặc là do đường truyền.

    VÌ SAO THỬ LẠI, VÀ VÌ SAO CHỈ MỘT LẦN: đo 2026-08-16 trên 3 ngày —
    calendarCompany.upcomingEvents chạy 215 lần trót lọt (trung bình 825ms) và
    hỏng 21 lần, tất cả nằm gọn trong một chùm 6 tiếng đêm 15/08, mỗi lần đều
    tốn đúng 8.206ms tức chờ hết timeout mà chưa bắt tay xong SSL. Chùm dài như
    thế thì thử lại bao nhiêu cũng vô ích — nhưng những lần chập một hai giây
    thì một lần thử lại là đủ, và đó là loại hay gặp hơn.

    NGÂN SÁCH: 33 năng lực khai `maxDurationSec: 20`, nên tổng thời gian của
    MỌI lần thử phải nằm dưới đó — nếu không dispatcher giết tiến trình trước
    khi company kịp trả về một câu tử tế (đúng cái bẫy "timeout bằng ngân sách"
    trong CLAUDE.md). Hai lần × 8s + 0,5s nghỉ = 16,5s, còn chừa 3,5s. Muốn
    thử thêm lần nữa thì phải hạ `timeout`, đừng chỉ tăng `thu_lai`.

    KHÔNG thử lại với lỗi 4xx: token sai, id sai, schema sai thì gọi lại vẫn
    sai — chỉ tổ chờ lâu gấp đôi rồi báo cùng một lỗi. 5xx và lỗi mạng thì có.
    """
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API}{path}", data=data, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": VERSION,
            "Content-Type": "application/json",
        },
    )
    for lan in range(thu_lai + 1):
        con_thu = lan < thu_lai
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                msg = json.loads(raw).get("message", raw)
            except json.JSONDecodeError:
                msg = raw
            if con_thu and exc.code >= 500:
                time.sleep(0.5)
                continue
            raise NotionError(f"Notion {exc.code}: {msg[:300]}") from None
        except Exception as exc:
            if con_thu:
                time.sleep(0.5)
                continue
            # Nói rõ ĐÃ THỬ LẠI, để lần sau đọc log không phải đoán xem con số
            # thời gian gấp đôi là do mạng ì hay do có nhánh thử lại ở đây.
            da_thu = f" (đã thử {thu_lai + 1} lần)" if thu_lai else ""
            raise NotionError(
                f"Không gọi được Notion{da_thu}: {type(exc).__name__}: {exc}") from None


def token_from_env(var: str = "NOTION_TOKEN") -> str:
    tok = os.environ.get(var, "")
    if not tok:
        raise NotionError(
            f"Thiếu {var}. Chạy: python3 ops/setup-notion.py"
        )
    return tok


# ───────────────────────── thao tác ─────────────────────────

def whoami(token: str) -> dict:
    return _request("GET", "/users/me", token)


def search(token: str, query: str = "", object_type: str = "page",
           page_size: int = 20) -> list:
    """Chỉ tìm được trong những trang admin đã chia sẻ cho integration.

    Đây là tính chất bảo mật quan trọng: integration KHÔNG thấy toàn bộ Notion,
    chỉ thấy đúng thứ được chia sẻ. Phạm vi do admin quyết, không do code.
    """
    body = {"page_size": page_size,
            "filter": {"value": object_type, "property": "object"}}
    if query:
        body["query"] = query
    return _request("POST", "/search", token, body).get("results", [])


def create_database(token: str, parent_page_id: str, title: str,
                    properties: dict) -> dict:
    return _request("POST", "/databases", token, {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"type": "text", "text": {"content": title}}],
        "properties": properties,
    })


def get_database(token: str, database_id: str) -> dict:
    return _request("GET", f"/databases/{database_id}", token)


def update_database(token: str, database_id: str, properties: dict) -> dict:
    """Đổi cấu trúc cột. Dùng để nâng cấp schema, không dùng lúc chạy thường."""
    return _request("PATCH", f"/databases/{database_id}", token,
                    {"properties": properties})


def rename_database(token: str, database_id: str, title: str) -> dict:
    return _request("PATCH", f"/databases/{database_id.replace('-', '')}", token,
                    {"title": [{"type": "text", "text": {"content": title[:200]}}]})


def set_database_description(token: str, database_id: str, text: str) -> dict:
    """Ghi mô tả cho database.

    Dùng để gắn siêu dữ liệu SỐNG CÙNG bảng: xoá store nội bộ thì vẫn đọc lại
    được, vì nó nằm trên Notion chứ không nằm ở máy.
    """
    return _request("PATCH", f"/databases/{database_id.replace('-', '')}", token,
                    {"description": [{"type": "text", "text": {"content": text[:2000]}}]})


def db_description(d: dict) -> str:
    return "".join(t.get("plain_text", "") for t in d.get("description", [])).strip()


def archive_database(token: str, database_id: str) -> dict:
    """Bỏ cả một database vào thùng rác Notion (giữ 30 ngày, khôi phục được)."""
    return _request("PATCH", f"/databases/{database_id.replace('-', '')}", token,
                    {"archived": True})


def get_page(token: str, page_id: str) -> dict:
    return _request("GET", f"/pages/{page_id.replace('-', '')}", token)


def archive_page(token: str, page_id: str) -> dict:
    """Bỏ bản ghi vào thùng rác Notion. Khôi phục được trong 30 ngày —
    nên đây là 'write' hoàn tác được, không phải 'irreversible'."""
    return _request("PATCH", f"/pages/{page_id.replace('-', '')}", token,
                    {"archived": True})


def unarchive_page(token: str, page_id: str) -> dict:
    """Lấy lại một bản ghi từ thùng rác.

    Chỉ làm được khi CÒN page_id: API search của Notion không trả về trang đã
    archived, nên mất id là mất đường về — dù bản ghi vẫn nằm đó 30 ngày.
    Đó là lý do sideEffects.target phải là id thật, không phải nhãn dễ đọc.
    """
    return _request("PATCH", f"/pages/{page_id.replace('-', '')}", token,
                    {"archived": False})


def update_page(token: str, page_id: str, properties: dict) -> dict:
    """Sửa bản ghi đã có.

    Khác create_page ở chỗ nó GHI ĐÈ giá trị cũ. Company gọi hàm này phải đọc
    giá trị cũ trước và khai vào sideEffects, nếu không thì không hoàn tác được.
    """
    return _request("PATCH", f"/pages/{page_id.replace('-', '')}", token,
                    {"properties": properties})


def create_page(token: str, database_id: str, properties: dict,
                children: list | None = None) -> dict:
    body = {"parent": {"database_id": database_id}, "properties": properties}
    if children:
        body["children"] = children
    return _request("POST", "/pages", token, body)


def block_children(token: str, block_id: str, page_size: int = 100) -> list:
    return _request("GET", f"/blocks/{block_id}/children?page_size={page_size}",
                    token).get("results", [])


def paragraphs(text: str) -> list:
    """Chia văn bản dài thành các block đoạn văn.

    Mỗi rich_text của Notion tối đa 2000 ký tự, nên nội dung dài phải cắt.
    Cắt theo dòng trống trước, chỉ cắt cứng khi một đoạn tự nó quá dài.
    """
    blocks = []
    for chunk in text.split("\n\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        while chunk:
            part, chunk = chunk[:1900], chunk[1900:]
            blocks.append({
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [
                    {"type": "text", "text": {"content": part}}]},
            })
    return blocks


def read_paragraphs(blocks: list) -> str:
    """Ghép các block đoạn văn trở lại thành văn bản.

    Đọc được cả hai dạng: block Notion TRẢ VỀ (có `plain_text`) và block ta tự
    DỰNG để gửi đi (chỉ có `text.content`). Nhờ vậy paragraphs() ↔ read_paragraphs()
    kiểm chứng được mà không cần gọi mạng.
    """
    out = []
    for b in blocks:
        if b.get("type") != "paragraph":
            continue
        parts = []
        for t in b["paragraph"].get("rich_text", []):
            parts.append(t.get("plain_text") or (t.get("text") or {}).get("content", ""))
        out.append("".join(parts))
    return "\n\n".join(x for x in out if x)


# Trần số vòng phân trang. Con số này neo vào NGÂN SÁCH THỜI GIAN, không phải
# vào một số tròn cho đẹp: `sumExpenses`/`sumIncomes` khai `maxDurationSec: 20`,
# một lần gọi Notion đo được trung bình 825ms, nên 10 vòng ≈ 8,3s — còn chừa
# chỗ cho một lần chập mạng phải thử lại (xem `_request`). Muốn kéo nhiều hơn
# thì phải nâng `maxDurationSec` trong manifest TRƯỚC, đừng chỉ sửa số ở đây.
MAX_TRANG = 10


def query_database(token: str, database_id: str, filter_: dict | None = None,
                   sorts: list | None = None, page_size: int = 100,
                   fetch_all: bool = False) -> list:
    """Truy vấn một bảng Notion.

    Mặc định trả về TỐI ĐA `page_size` dòng, đúng như trước — đó là thứ mọi lời
    gọi kiểu "20 khoản gần nhất" đang cần.

    `fetch_all=True` thì lặp con trỏ cho tới hết. Dùng khi kết quả đem đi CỘNG:
    Notion trả tối đa 100 dòng mỗi lần và báo còn nữa bằng `has_more`, mà bản cũ
    không hề đọc cờ đó — nên mọi phép cộng vượt 100 dòng đều thiếu, im lặng, và
    thiếu theo hướng dễ chịu.

    Đo được 2026-08-25: tháng 8 có 110 khoản chi. `sumExpenses` báo 6.788.746đ
    "qua 100 khoản", trong khi cộng hai nửa tháng ra 7.151.746đ — hụt 363.000đ,
    và con số hụt lớn dần về cuối tháng. Không cổng nào bắt được vì kết quả vẫn
    là một con số hợp lệ; chỉ có ai đó ngồi cộng tay mới thấy.
    """
    body: dict = {"page_size": 100 if fetch_all else min(page_size, 100)}
    if filter_:
        body["filter"] = filter_
    if sorts:
        body["sorts"] = sorts

    ket_qua: list = []
    for _ in range(MAX_TRANG if fetch_all else 1):
        res = _request("POST", f"/databases/{database_id}/query", token, body)
        ket_qua.extend(res.get("results", []))
        if not fetch_all or not res.get("has_more"):
            return ket_qua
        body["start_cursor"] = res.get("next_cursor")

    # Chạm trần mà Notion vẫn báo còn nữa: KÊU LÊN, đừng trả về phần đã lấy.
    # O10 — trả thiếu ở đây thì người gọi cộng ra một con số trông hoàn toàn
    # bình thường, tức là tái phạm đúng con bug vừa sửa, chỉ ở ngưỡng cao hơn.
    raise NotionError(
        f"Bảng có hơn {MAX_TRANG * 100} dòng trong khoảng đang tra — vượt trần "
        "phân trang nên em không dám cộng, số ra sẽ thiếu. Thu hẹp khoảng ngày "
        "lại, hoặc nâng MAX_TRANG cùng với maxDurationSec của năng lực.")


# ───────────────────────── đọc giá trị ─────────────────────────

def plain(prop: dict):
    """Rút giá trị thường dùng ra khỏi cấu trúc property của Notion."""
    if prop is None:
        return None
    kind = prop.get("type")
    if kind == "title":
        return "".join(t.get("plain_text", "") for t in prop.get("title", []))
    if kind == "rich_text":
        return "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))
    if kind == "number":
        return prop.get("number")
    if kind == "select":
        return (prop.get("select") or {}).get("name")
    if kind == "date":
        return (prop.get("date") or {}).get("start")
    if kind == "checkbox":
        return prop.get("checkbox")
    return None


def title_prop(text: str) -> dict:
    return {"title": [{"type": "text", "text": {"content": text[:2000]}}]}


def text_prop(text: str) -> dict:
    return {"rich_text": [{"type": "text", "text": {"content": text[:2000]}}]}


def number_prop(value) -> dict:
    return {"number": value}


def select_prop(name: str) -> dict:
    return {"select": {"name": name[:100]}}


def date_prop(iso_date: str) -> dict:
    return {"date": {"start": iso_date}}


def checkbox_prop(value: bool) -> dict:
    return {"checkbox": bool(value)}
