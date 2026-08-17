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
# VÌ SAO CÀI PLAYWRIGHT DÙ browser-use KHÔNG DÙNG NÓ NỮA: bản 0.13 điều khiển
# trình duyệt bằng CDP (`cdp-use`) và MẶC ĐỊNH nối vào Chrome/Edge ĐANG CHẠY
# của người dùng. Ở đây không được phép làm vậy — trình duyệt admin đang mở có
# đủ cookie Notion, Gmail, ngân hàng, mà company này đã chốt là KHÔNG đăng nhập
# gì hết. Nên ta chỉ mượn playwright đúng một việc: tải về một bản Chromium
# riêng, sạch, để agent chạy trong đó (`executable_path` trong runner.py).
#
# Tốn khoảng 900MB: Python riêng + thư viện + Chromium.
set -euo pipefail

CTY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$CTY/.venv/bin/python"

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

echo "── 3/4 · browser-use + playwright (playwright chỉ để lấy Chromium)"
uv pip install --python "$PY" browser-use playwright

echo "── 4/4 · Chromium riêng"
"$PY" -m playwright install chromium

# Chromium cần vài thư viện đồ hoạ mà WSL bản gọn không có sẵn. Kiểm THẬT bằng
# cách chạy thử, đừng đoán theo tên bản phân phối.
CHROME="$(ls -d "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux*/chrome 2>/dev/null | sort -r | head -1 || true)"
echo
if [ -n "$CHROME" ] && "$CHROME" --version >/dev/null 2>&1; then
  echo "Chromium chạy được: $("$CHROME" --version)"
else
  echo "⚠ Chromium tải xong nhưng THIẾU THƯ VIỆN HỆ THỐNG, chưa chạy được."
  echo "  Thiếu: $(ldd "$CHROME" 2>/dev/null | grep 'not found' | awk '{print $1}' | sort -u | tr '\n' ' ')"
  echo
  echo "  Cài bằng (cần sudo, chạy MỘT lần):"
  echo "    sudo $PY -m playwright install-deps chromium"
  echo
  echo "  Hoặc gọn hơn:"
  echo "    sudo apt install -y libatk1.0-0 libatk-bridge2.0-0 libxcomposite1 libxdamage1 libatspi2.0-0"
fi

echo
echo "Còn một việc NỮA: chọn model, khai vào ops/.env. Hai đường, chọn một."
echo
echo "  A· MODEL LOCAL — không tốn đồng nào, ưu tiên dùng:"
echo "       BROWSER_LLM_BASE_URL=http://$(ip route show default 2>/dev/null | awk '{print $3}'):11434/v1"
echo "       BROWSER_LLM_MODEL=qwen3:8b"
echo "     Ollama/LM Studio chạy trên Windows phải cho WSL gọi vào được:"
echo "       Ollama    → đặt biến OLLAMA_HOST=0.0.0.0 rồi khởi động lại Ollama"
echo "       LM Studio → bật 'Serve on Local Network' trong tab Developer"
echo
echo "  B· GEMINI — TÍNH TIỀN THẬT (L8), chỉ dùng khi không có A:"
echo "       GEMINI_API_KEY=..."
echo "     Lấy ở https://aistudio.google.com/apikey · trần tháng ở"
echo "     registry/gateway.yaml (đang là 100.000đ), mỗi lần gọi đều hỏi duyệt."
