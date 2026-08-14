#!/usr/bin/env python3
"""supabaseClient — nói chuyện với Supabase qua PostgREST. Dùng chung mọi company.

Đứng cùng vai trò notionClient và repoClient: chỗ DUY NHẤT biết giao thức, để
company chỉ còn lo nghiệp vụ.

Chỉ dùng thư viện chuẩn — không cài `supabase-py`. Lý do: ta chỉ cần bốn động
tác REST trên vài bảng. Thêm một phụ thuộc để dùng 5% của nó là đổi rủi ro
chuỗi cung ứng lấy tiện lợi không đáng.

VỀ KHOÁ: hàm ở đây nhận khoá làm tham số, không tự đọc biến môi trường. Company
tự lấy khoá của dự án mình — nhờ vậy một company không thể vô tình dùng khoá
của dự án khác chỉ vì cùng tên biến.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 30


class SupabaseError(RuntimeError):
    """Supabase từ chối hoặc không phản hồi đúng."""


def _request(method: str, url: str, key: str, body=None,
             them_header: dict | None = None, token: str | None = None) -> tuple[int, object]:
    """`key` luôn là khoá công khai (header apikey — Supabase dùng nó để biết dự
    án nào). `token` là danh tính THẬT: JWT của tài khoản bot sau khi đăng nhập.
    Không truyền token thì hai thứ là một — chỉ đúng cho việc đọc công khai.
    """
    du_lieu = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(url, data=du_lieu, method=method)
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {token or key}")
    req.add_header("Content-Type", "application/json")
    for k, v in (them_header or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            tho = res.read().decode()
            return res.status, (json.loads(tho) if tho.strip() else None)
    except urllib.error.HTTPError as exc:
        chi_tiet = exc.read().decode()[:300]
        # KHÔNG bọc thêm chữ gì vào thông báo của Supabase: nó nói rất rõ cột
        # nào sai, ràng buộc nào vỡ. Diễn giải lại chỉ làm mất thông tin.
        raise SupabaseError(f"HTTP {exc.code}: {chi_tiet}")
    except urllib.error.URLError as exc:
        raise SupabaseError(f"Không nối được Supabase: {exc.reason}")


def _rest(base_url: str, bang: str) -> str:
    return f"{base_url.rstrip('/')}/rest/v1/{bang}"


def dang_nhap(base_url: str, khoa_cong_khai: str, email: str, mat_khau: str) -> str:
    """Đăng nhập tài khoản bot, trả về JWT dùng cho các lời gọi sau.

    VÌ SAO KHÔNG CẦM KHOÁ VẠN NĂNG: service_role bỏ qua toàn bộ RLS — cầm nó là
    đọc được cả hội thoại và thông tin liên hệ của khách. Đăng nhập bằng một tài
    khoản riêng thì quyền của company ĐÚNG BẰNG những gì luật RLS cho tài khoản
    đó, không hơn. Giới hạn nằm ở phía database, không nằm ở chỗ ta dặn dò.

    Token sống khoảng một tiếng. Mỗi lời gọi company là một tiến trình mới nên
    cứ đăng nhập lại — thêm một chặng HTTP, đổi lấy việc không phải cất token ở
    đâu cả.
    """
    url = f"{base_url.rstrip('/')}/auth/v1/token?grant_type=password"
    try:
        _, du_lieu = _request("POST", url, khoa_cong_khai,
                              {"email": email, "password": mat_khau})
    except SupabaseError as exc:
        raise SupabaseError(
            f"Tài khoản bot đăng nhập không được ({exc}). Kiểm email/mật khẩu "
            f"trong ops/.env, và xem tài khoản đã được xác nhận trong Supabase chưa.")
    token = (du_lieu or {}).get("access_token")
    if not token:
        raise SupabaseError("Đăng nhập xong nhưng Supabase không trả access_token")
    return token


def chon(base_url: str, key: str, bang: str, cot: str = "*",
         loc: dict | None = None, sap_xep: str | None = None,
         gioi_han: int | None = None, token: str | None = None) -> list:
    """SELECT. `loc` viết theo cú pháp PostgREST: {"status": "eq.draft"}."""
    tham_so = {"select": cot, **(loc or {})}
    if sap_xep:
        tham_so["order"] = sap_xep
    if gioi_han:
        tham_so["limit"] = str(gioi_han)
    url = _rest(base_url, bang) + "?" + urllib.parse.urlencode(tham_so)
    _, du_lieu = _request("GET", url, key, token=token)
    return du_lieu or []


def them(base_url: str, key: str, bang: str, ban_ghi: dict,
         token: str | None = None) -> dict:
    """INSERT, trả về bản ghi vừa tạo (cần Prefer: return=representation)."""
    _, du_lieu = _request("POST", _rest(base_url, bang), key, ban_ghi,
                          {"Prefer": "return=representation"}, token=token)
    if not du_lieu:
        raise SupabaseError(f"Thêm vào '{bang}' xong nhưng không nhận lại bản ghi")
    return du_lieu[0] if isinstance(du_lieu, list) else du_lieu


def sua(base_url: str, key: str, bang: str, loc: dict, thay_doi: dict,
        token: str | None = None) -> list:
    """UPDATE. `loc` BẮT BUỘC không rỗng — PostgREST không có WHERE thì sửa CẢ BẢNG."""
    if not loc:
        raise SupabaseError(
            "Từ chối UPDATE không điều kiện — sẽ sửa toàn bộ bảng "
            f"'{bang}'. Đây gần như luôn là lỗi lập trình.")
    url = _rest(base_url, bang) + "?" + urllib.parse.urlencode(loc)
    _, du_lieu = _request("PATCH", url, key, thay_doi,
                          {"Prefer": "return=representation"}, token=token)
    return du_lieu or []


def lam_moi_trang(site_url: str, secret: str, duong_dan: str) -> bool:
    """Gọi /api/revalidate của site Next.js.

    VÌ SAO BẮT BUỘC: Next.js dựng trang tĩnh sẵn. Ghi thẳng vào Supabase thì dữ
    liệu đúng nhưng TRANG CÔNG KHAI VẪN LÀ BẢN CŨ — bài mới không xuất hiện, và
    không có lỗi nào báo. Chính app của admin cũng gọi revalidate sau mỗi lần
    lưu bài; company ghi từ ngoài vào thì càng phải gọi.
    """
    req = urllib.request.Request(
        f"{site_url.rstrip('/')}/api/revalidate",
        data=json.dumps({"secret": secret, "path": duong_dan}).encode(),
        method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            return res.status == 200
    except urllib.error.HTTPError as exc:
        raise SupabaseError(
            f"Làm mới '{duong_dan}' hỏng (HTTP {exc.code}). "
            f"Bài đã ghi vào database nhưng trang công khai còn là bản cũ.")
    except urllib.error.URLError as exc:
        raise SupabaseError(f"Không gọi được site để làm mới: {exc.reason}")
