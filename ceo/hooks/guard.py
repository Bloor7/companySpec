#!/usr/bin/env python3
"""PreToolUse hook — hàng rào thật của tầng CEO (P2).

Đây là code, không phải lời dặn trong prompt. Model không sửa được file này và
không nói vòng qua được. Nếu SYSTEM.md nói "chỉ gọi dispatch.py" mà model vẫn
thử `rm -rf`, chính file này là thứ chặn lại.

CÁCH SOÁT: tách câu lệnh ĐÚNG NHƯ SHELL TÁCH (shlex), rồi đối chiếu với một
khuôn hẹp — `python3 gateway/cli/dispatch.py {list|call}` cộng vài cờ trong danh sách
trắng. Mọi thứ khác là chặn.

VÌ SAO KHÔNG TÌM KÝ TỰ XẤU NỮA: bản trước chặn hễ thấy `|`, `;`, `>`… ở BẤT KỲ
đâu trong chuỗi lệnh. Ý định đúng, nhưng nó không phân biệt nổi ký tự nối lệnh
với ký tự nằm trong DỮ LIỆU của admin. Hậu quả đo được ngày 2026-08-14: admin
nhờ lưu ghi chú `irm christitus.com/win | iex`, CEO bị chặn nên tự thay `|`
thành `(PIPE)` rồi bỏ luôn dấu tiếng Việt để lách — ghi chú lưu vào Notion
không còn giống thứ admin gửi. Hàng rào mà buộc người ta bóp méo dữ liệu để đi
qua thì nó đang tạo ra một lỗi im lặng, không phải chặn một lỗi.

Sau khi shlex bóc dấu nháy, `{"ghiChu": "a | b"}` là MỘT tham số — không có
cách nào biến nó thành lệnh thứ hai. Nên ký tự trong đó vô hại và được cho qua.

Ba thứ VẪN chặn thô, vì shell mở rộng chúng ngay cả trong nháy kép và shlex
không cho biết chuỗi vốn nằm trong nháy nào: `$(`, `${`, và dấu huyền. Nội dung
thật sự cần những ký tự đó thì viết bằng \\uXXXX trong JSON — SYSTEM.md có dặn,
và dữ liệu vẫn giữ nguyên vẹn.
"""
import json
import shlex
import sys

CMD = ["python3", "gateway/cli/dispatch.py"]
LENH = {"list", "call"}

# Cờ CEO được phép dùng. Danh sách trắng, không phải danh sách đen.
#
# Cố ý THIẾU hai cờ mà dispatcher có thật:
#   --dry-run       in việc định làm rồi trả về ok mà KHÔNG làm. CEO cầm cờ này
#                   thì nó báo "xong rồi" trong khi ví không hề đổi — kiểu hỏng
#                   tệ nhất vì trông y hệt thành công.
#   --allow-internal mở company nội bộ (C5), thứ CEO không được thấy.
# --issued-by cũng không có: CEO không được tự nhận mình là việc định kỳ.
CO = {"--company", "--capability", "--input", "--trace", "--intent",
      "--approval-id", "--session", "--ttl"}

# Mở rộng ngay cả trong nháy kép → shlex không cứu được, phải chặn thô.
NGUY_HIEM = ["$(", "${", "`", "\n", "\r"]


def deny(reason: str) -> None:
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, sys.stdout)
    sys.exit(0)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        deny("guard: không đọc được payload của hook — chặn cho chắc.")

    tool = payload.get("tool_name", "")
    if tool != "Bash":
        # Mặc định là CẤM. --tools đã gỡ định nghĩa các tool khác, nhưng nếu
        # cờ đó hỏng hoặc bị bỏ sót thì lớp này vẫn đứng. Đó là ý nghĩa của P2.
        deny(f"guard: CEO chỉ được dùng Bash để gọi dispatcher. Đã thử: {tool}")

    command = ((payload.get("tool_input") or {}).get("command") or "").strip()

    for token in NGUY_HIEM:
        if token in command:
            ten = {"\n": "xuống dòng", "\r": "xuống dòng"}.get(token, token)
            deny(
                f"guard: lệnh chứa '{ten}' — shell sẽ diễn giải nó kể cả trong "
                "dấu nháy kép, nên không được có trong câu lệnh.\n"
                "  Nội dung cần ký tự này thì viết trong JSON bằng \\uXXXX "
                "(\\u0024 = $, \\u0060 = dấu huyền, \\n = xuống dòng)."
            )

    try:
        phan = shlex.split(command)
    except ValueError as exc:
        # Nháy không đóng. Không đoán ý — chặn và nói rõ để CEO gõ lại cho đúng.
        deny(f"guard: câu lệnh có dấu nháy không đóng ({exc}). "
             "Nội dung có dấu nháy đơn thì viết \\u0027 trong JSON.")

    if phan[:2] != CMD or len(phan) < 3 or phan[2] not in LENH:
        deny(
            "guard: CEO chỉ được gọi company qua dispatcher.\n"
            "  Được phép:  python3 gateway/cli/dispatch.py list\n"
            "              python3 gateway/cli/dispatch.py call --company … --capability … --input '…'\n"
            f"  Đã thử:     {command[:200]}"
        )

    # Phần còn lại phải là các cặp `--cờ giá-trị`. Đây là chỗ chặn mọi thứ mà
    # shlex vừa tách ra được nhưng không thuộc khuôn: `>file`, `rm`, `--dry-run`…
    i = 3
    while i < len(phan):
        co = phan[i]
        if co not in CO:
            deny(f"guard: cờ không được phép: {co!r}. "
                 f"Chỉ có: {', '.join(sorted(CO))}")
        if i + 1 >= len(phan):
            deny(f"guard: cờ {co} thiếu giá trị.")
        i += 2

    sys.exit(0)  # im lặng cho qua


if __name__ == "__main__":
    main()
