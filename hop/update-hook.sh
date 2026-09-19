#!/bin/bash
# Hook `update` của kho gương — HÀNG RÀO BẰNG MÃ, không phải lời hứa.
#
# Hộp đẩy mã về đây qua git daemon trên 127.0.0.1. Hook này chạy TRƯỚC khi ref
# được cập nhật, và nó chỉ cho đúng một hình: `refs/heads/y/<mã việc>`.
#
# VÌ SAO PHẢI LÀ MÃ chứ không phải một dòng trong hop/README.md: "hộp không tự
# gộp vào main" mà chỉ viết trong tài liệu thì nó đúng cho tới lần đầu có ai —
# người hay agent — quên mất. Viết ở đây thì `git push` vào main bị từ chối
# ngay tại chỗ, kèm câu giải thích, và không cần ai nhớ gì cả.
#
# Cài: cp hop/update-hook.sh <kho-guong>/hooks/update && chmod +x
set -euo pipefail
ref="$1"

case "$ref" in
  refs/heads/y/*)
    exit 0
    ;;
  refs/heads/main)
    echo "TỪ CHỐI: hộp không được đẩy vào main." >&2
    echo "Xong việc thì đẩy nhánh 'y/<mã việc>'; đại ca xem diff rồi tự gộp." >&2
    exit 1
    ;;
  *)
    echo "TỪ CHỐI: '$ref' không đúng hình cho phép." >&2
    echo "Chỉ nhận 'refs/heads/y/<mã việc>' — một nhánh cho một việc trong xưởng." >&2
    exit 1
    ;;
esac
