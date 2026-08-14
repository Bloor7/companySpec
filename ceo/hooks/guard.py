#!/usr/bin/env python3
"""PreToolUse hook — hàng rào thật của tầng CEO (P2).

Đây là code, không phải lời dặn trong prompt. Model không sửa được file này và
không nói vòng qua được. Nếu SYSTEM.md nói "chỉ gọi dispatch.py" mà model vẫn
thử `rm -rf`, chính file này là thứ chặn lại.

Luật: lệnh Bash duy nhất được phép là gọi dispatcher, và không được nối chuỗi.
"""
import json
import re
import sys

ALLOWED = re.compile(r"^python3?\s+ops/dispatch\.py\s+(list|call)\b")

# Ký tự cho phép nối/chuyển hướng lệnh — có mặt là chặn, kể cả khi phần đầu hợp lệ.
CHAINING = ["&&", "||", ";", "|", "`", "$(", ">", "<", "\n", "\r"]


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

    command = (payload.get("tool_input") or {}).get("command", "")

    for token in CHAINING:
        if token in command:
            deny(
                f"guard: lệnh chứa '{token}' — không được nối chuỗi hay chuyển hướng. "
                "Chỉ được gọi đúng một lệnh dispatcher."
            )

    if not ALLOWED.match(command.strip()):
        deny(
            "guard: CEO chỉ được gọi company qua dispatcher.\n"
            "  Được phép:  python3 ops/dispatch.py list\n"
            "              python3 ops/dispatch.py call --company … --capability … --input '…'\n"
            f"  Đã thử:     {command[:200]}"
        )

    sys.exit(0)  # im lặng cho qua


if __name__ == "__main__":
    main()
