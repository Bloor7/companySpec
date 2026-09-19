"""core — hệ điều hành của Travis: luật, quyền, execution.

Đọc docs/CORE_CONTRACT.md trước khi thêm gì vào đây.

RANH GIỚI CỦA GÓI NÀY

  · KHÔNG nghiệp vụ. Ở đây không có "chi tiêu", không có "lời nhắc". Thêm
    company mới không được sửa một dòng nào trong `core/` (W3′).
  · KHÔNG I/O trong phần quyết định. `core.policy` phải tất định: cùng đầu vào
    ra cùng quyết định. Thứ cần biết từ thế giới ngoài thì người gọi tra trước
    rồi đưa vào.
  · Tên tiếng Anh camelCase, kể cả biến Python (PRINCIPLES §7, docs/NAMING.md).
"""
