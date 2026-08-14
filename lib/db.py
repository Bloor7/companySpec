#!/usr/bin/env python3
"""Mở SQLite đúng cách. Mọi nơi trong hệ đều phải đi qua đây.

VÌ SAO CẦN: hệ này có nhiều tiến trình cùng chạy — poller, gateway, dispatcher,
scheduler, và mỗi company là một tiến trình riêng. Tất cả cùng ghi vào vài file
SQLite.

Chế độ mặc định của SQLite là `journal=delete`: khi một tiến trình ghi, nó khoá
CẢ FILE, kể cả với tiến trình chỉ muốn đọc. Admin nhắn ba tin liên tiếp trong
lúc scheduler chạy là đủ để đụng nhau, và lỗi hiện ra là "database is locked" —
một câu không nói được gì cho người dùng cuối. Đã xảy ra thật ngày 2026-08-04.

WAL sửa đúng chỗ đó: một người ghi và nhiều người đọc chạy song song được,
người đọc không bao giờ bị chặn.

C4.1 — đây là thư viện dùng chung. Nó chỉ biết "mở kết nối thế nào", không biết
bảng nào của ai.
"""
import os
import sqlite3

BUSY_TIMEOUT_MS = 15000   # chờ 15 giây rồi mới chịu thua, thay vì hỏng ngay


def connect(path: str, timeout: float = 15.0) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    # isolation_level=None = TỰ COMMIT từng câu lệnh.
    #
    # Mặc định của Python là ngầm mở giao dịch trước mỗi INSERT/UPDATE/DELETE và
    # bắt gọi commit(). Quên một chỗ là kết nối giữ khoá ghi vô thời hạn — và
    # đây là hệ nhiều tiến trình, nên "vô thời hạn" nghĩa là mọi tiến trình khác
    # đứng chờ rồi chết vì hết giờ.
    #
    # Đã xảy ra thật 2026-08-04: sweep_orphans() chạy UPDATE nhưng chỉ commit khi
    # dọn được ít nhất một dòng. Không có dòng nào kẹt → không commit → dispatcher
    # tự khoá chính nó, rồi create_request ở kết nối thứ hai chết vì "database is
    # locked". Bot báo lỗi vô nghĩa với admin.
    #
    # Tự commit làm cả lớp lỗi đó không tồn tại được. Đổi lại mất tính nguyên tử
    # nhiều câu lệnh — hệ này không cần: mỗi lần ghi là một dòng nhật ký độc lập.
    conn = sqlite3.connect(path, timeout=timeout, isolation_level=None)
    conn.row_factory = sqlite3.Row

    # WAL bám vào file, đặt một lần là xong — nhưng cứ đặt lại cho chắc,
    # phòng khi file bị tạo mới bởi một tiến trình chưa qua module này.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    # An toàn với WAL: mất điện có thể mất giao dịch cuối, không hỏng file.
    # Đổi lại nhanh hơn nhiều. Đây là nhật ký công việc, không phải sổ ngân hàng.
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn
