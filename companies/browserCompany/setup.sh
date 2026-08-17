#!/usr/bin/env bash
# Dựng môi trường cho browserCompany. Chạy lại được nhiều lần.
#
#     bash companies/browserCompany/setup.sh
#
# VÌ SAO CẦN SCRIPT RIÊNG: browser-use đòi Python >= 3.11, máy đang chạy 3.10.
# Nên company có .venv riêng, dựng bằng `uv` — uv tự tải đúng bản Python vào
# thư mục người dùng, không cần sudo và không đụng python3 của hệ.
#
# F4 — repo là ĐẶC TẢ, không phải môi trường: .venv và Chromium KHÔNG nằm trong
# git (.gitignore đã chặn). Mất máy thì chạy lại script này là có lại.
#
# Tốn khoảng 500MB: Python riêng (~50MB) + thư viện + Chromium (~150MB).
set -euo pipefail

CTY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "── 1/4 · uv (trình quản môi trường, tự tải Python riêng)"
if ! command -v uv >/dev/null 2>&1; then
  echo "   chưa có uv. Cài bằng lệnh chính thức:"
  echo "     curl -LsSf https://astral.sh/uv/install.sh | sh"
  echo "   rồi mở lại terminal và chạy lại script này."
  exit 1
fi
echo "   uv: $(uv --version)"

echo "── 2/4 · .venv với Python 3.12"
uv venv --python 3.12 "$CTY/.venv"

echo "── 3/4 · browser-use"
VIRTUAL_ENV="$CTY/.venv" uv pip install --python "$CTY/.venv/bin/python" browser-use

echo "── 4/4 · Chromium cho Playwright"
"$CTY/.venv/bin/python" -m playwright install chromium --with-deps 2>/dev/null \
  || "$CTY/.venv/bin/python" -m playwright install chromium

echo
echo "Xong. Kiểm bằng:"
echo "  companies/browserCompany/.venv/bin/python -c 'import browser_use; print(browser_use.__version__)'"
echo
echo "Còn một việc NỮA phải làm bằng tay: thêm khoá vào ops/.env"
echo "  GEMINI_API_KEY=..."
echo "Lấy ở https://aistudio.google.com/apikey — API này TÍNH TIỀN THẬT (L8),"
echo "trần tháng đặt ở registry/gateway.yaml (đang là 100.000đ)."
