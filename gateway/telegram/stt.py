#!/usr/bin/env python3
"""Nghe tin thoại admin gửi, đổi thành chữ. Chạy HOÀN TOÀN trên máy admin.

Giọng nói không rời khỏi máy: mô hình nằm ở đây, không có lời gọi mạng nào.
Đó là lý do chọn cách này thay vì một dịch vụ chuyển giọng nói trực tuyến —
tin thoại của admin thường là chuyện tiền nong và đời sống riêng.

Chạy trong môi trường riêng (.venv-stt) chứ không phải python hệ thống, nên
gateway gọi nó bằng subprocess chứ không import. Đổi lại: cài hỏng phần này
cũng không làm chết cả hệ.

    python3 gateway/telegram/stt.py nghe <đường-dẫn-audio>
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VENV_PY = os.path.join(ROOT, ".venv-stt", "bin", "python")

# medium (~1,5GB). Chậm hơn base khoảng 4 lần nhưng là cỡ nhỏ nhất nghe ĐÚNG
# được tiếng Việt.
#
# Đo trên hai tin thoại thật của admin, cùng một câu "bây giờ là mấy giờ":
#   base   2,5s   "Mày là mấy á"            · "Anh nói biểu là mấy..."
#   small  4,5s   "Mìa là mìa"              · "à nỏi bây giờ làm mấy giờ"
#   medium 12,7s  "Bây giờ là mấy đứa"      · "Anh hỏi bây giờ là mấy giờ?"
#
# base sai tới mức CEO tưởng admin hỏi "em là ai" và đi tự giới thiệu. Với việc
# ghi tiền thì nghe nhầm một con số là ghi sai sổ, nên 10 giây chờ thêm rẻ hơn
# nhiều so với một lần nghe nhầm. Đổi bằng STT_MODEL nếu máy yếu.
#
# ĐÃ THỬ large-v3 (~3GB) và BỎ — to hơn KHÔNG đúng hơn, trên cùng ba file thật:
#   "16.000 mua bò húc"  → medium ĐÚNG · large-v3 nghe thành "bò hút"
#   "bây giờ là mấy giờ" → cả hai đều đúng
#   file thứ ba          → cả hai đều sai (âm thanh tự nó không rõ)
# large-v3 còn chậm hơn ~1,5 lần. Đừng nâng cỡ nữa nếu chưa đo lại bằng file
# thật của admin — giọng miền Nam câu ngắn không phải chỗ mô hình to thắng.
MODEL = os.environ.get("STT_MODEL", "medium")

# Tin thoại dài quá thì gần như chắc chắn là admin bấm nhầm nút ghi âm.
TRAN_GIAY = 300


def san_sang() -> bool:
    return os.path.isfile(VENV_PY)


def _thoi_luong(duong_dan: str) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", duong_dan],
            capture_output=True, text=True, timeout=20)
        return float((r.stdout or "0").strip() or 0)
    except Exception:
        return 0.0


def nghe(duong_dan: str) -> tuple:
    """Trả (chữ nghe được, câu báo lỗi). Một trong hai luôn rỗng."""
    if not os.path.isfile(duong_dan):
        return "", "Không thấy file tin thoại."
    if not san_sang():
        return "", ("Bộ nghe chưa được cài. Dựng lại bằng: python3 -m venv "
                    ".venv-stt && .venv-stt/bin/pip install -r requirements-stt.txt")

    giay = _thoi_luong(duong_dan)
    if giay > TRAN_GIAY:
        return "", f"Tin thoại dài {giay:.0f} giây, quá {TRAN_GIAY} giây em không nghe."

    ma = (
        "import sys, json\n"
        "from faster_whisper import WhisperModel\n"
        f"m = WhisperModel({MODEL!r}, device='cpu', compute_type='int8')\n"
        "seg, info = m.transcribe(sys.argv[1], language='vi', beam_size=1,\n"
        "                         vad_filter=True)\n"
        "print(json.dumps({'text': ' '.join(s.text.strip() for s in seg).strip()},\n"
        "                 ensure_ascii=False))\n"
    )
    try:
        # Lần đầu phải tải mô hình (~150MB) nên để rộng thời gian; những lần sau
        # mô hình nằm trong cache của thư viện, chỉ còn thời gian nghe thật.
        proc = subprocess.run([VENV_PY, "-c", ma, duong_dan],
                              capture_output=True, text=True, timeout=900)
        if proc.returncode != 0:
            return "", f"Bộ nghe lỗi: {proc.stderr.strip()[:200]}"
        import json
        chu = (json.loads(proc.stdout.strip().splitlines()[-1]).get("text") or "").strip()
        if not chu:
            return "", "Em nghe không ra chữ nào — đại ca nói to hơn hoặc gõ giúp em."
        return chu, ""
    except subprocess.TimeoutExpired:
        return "", "Nghe lâu quá, em bỏ. Đại ca gõ giúp em."
    except Exception as exc:
        return "", f"Bộ nghe hỏng: {type(exc).__name__}"


def main() -> int:
    if len(sys.argv) < 3 or sys.argv[1] != "nghe":
        print(__doc__)
        return 1
    chu, loi = nghe(sys.argv[2])
    print(chu or f"[lỗi] {loi}")
    return 0 if chu else 1


if __name__ == "__main__":
    sys.exit(main())
