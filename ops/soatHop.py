#!/usr/bin/env python3
"""Mã trong HỘP có phải mã trong repo không?

    python3 ops/soatHop.py          # so, in ra chỗ lệch
    python3 ops/soatHop.py --chep   # chép repo → hộp (sao lưu trước)

═══════════════════════════════════════════════════════════════════════
VÌ SAO CÔNG CỤ NÀY TỒN TẠI
═══════════════════════════════════════════════════════════════════════

Ngày 2026-09-20: vá `hop/tho.py`, ca thử xanh, commit sạch — và thợ VẪN gửi
thẻ duyệt mỗi 5 phút. Vì thợ không chạy từ repo. Nó chạy trong distro WSL
`openclaw`, ở `/home/hop/tho.py`, một BẢN SAO từ 18/09.

Không có đường đồng bộ nào. Bản sao ấy lặng lẽ cũ đi, và admin phải hỏi lần
thứ hai mới lộ ra.

Bài học, và nó đáng dán lên tường:

    **Sửa xong thì hỏi: thứ ĐANG CHẠY có phải thứ vừa sửa không?**

═══ VÌ SAO KHÔNG PHẢI MỘT CA THỬ ═══

Đã thử viết thành ca trong `tests/regression/`. Nó luôn SKIP: distro Ubuntu
tắt interop (`/proc/sys/fs/binfmt_misc/WSLInterop` không tồn tại), nên từ
trong WSL không gọi được `wsl.exe` để với sang hộp.

Một hàng rào không bao giờ chạy được thì tệ hơn không có hàng rào — người
đọc sau sẽ tin nó. Nên nó nằm ở `ops/` (công cụ cho NGƯỜI, không trên đường
chạy) và phải chạy từ Windows, nơi với tới được cả hai distro.
"""
import argparse
import hashlib
import os
import subprocess
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Mỗi dòng: (file trong repo, đường dẫn trong hộp).
#:
#: Danh sách này phải NGẮN và khai tay. Đồng bộ cả thư mục thì có ngày mang
#: sang hộp một thứ nó cố ý không được có — hộp không giữ khoá nào của hệ, và
#: đó là lý do câu hỏi bảo mật về nó trả lời được (xem hop/README.md).
DONG_BO = [
    (os.path.join("hop", "tho.py"), "/home/hop/tho.py"),
]

DISTRO = "openclaw"


def _giai_ma(raw: bytes) -> str:
    """Giải mã đầu ra của `wsl.exe`.

    KHÔNG dùng `text=True`: trên Windows nó giải mã theo bảng mã của console
    (cp1252), và mọi chữ tiếng Việt trong file sẽ ném `UnicodeDecodeError`.
    `wsl.exe` cũng có bản trả UTF-16LE, nên thử cả hai rồi mới chịu thua.
    """
    for bang_ma in ("utf-8", "utf-16-le"):
        try:
            return raw.decode(bang_ma)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


class _KetQuaWsl:
    def __init__(self, proc):
        self.returncode = proc.returncode
        self.stdout = _giai_ma(proc.stdout or b"")
        self.stderr = _giai_ma(proc.stderr or b"")


def _wsl(*lenh) -> "_KetQuaWsl":
    return _KetQuaWsl(subprocess.run(
        ["wsl.exe", "-d", DISTRO, "--", *lenh],
        capture_output=True, timeout=120))


def _bam(noi_dung: bytes) -> str:
    return hashlib.sha256(noi_dung).hexdigest()[:12]


def _chi_ma(noi_dung: str) -> list:
    """Bỏ dòng trống và chú thích — so phần CHẠY, không so văn.

    Bản trong hộp có thể lệch vài dòng docstring sau một lần đổi tên mà không
    ai chép lại. Báo đỏ vì một dấu chấm là cách làm công cụ mất uy tín.
    """
    ra = []
    for dong in noi_dung.splitlines():
        bo = dong.strip()
        if bo and not bo.startswith("#"):
            ra.append(bo)
    return ra


def main() -> int:
    ap = argparse.ArgumentParser(description="soát mã trong hộp openclaw")
    ap.add_argument("--chep", action="store_true",
                    help="chép repo → hộp. SAO LƯU bản cũ trước khi đè.")
    args = ap.parse_args()

    thu = _wsl("true")
    if thu.returncode != 0:
        print(f"Không gọi được distro `{DISTRO}`. Chạy lệnh này TỪ WINDOWS —\n"
              f"trong WSL Ubuntu thì interop đang tắt nên không với sang được.",
              file=sys.stderr)
        return 2

    lech = 0
    for trong_repo, trong_hop in DONG_BO:
        duong_dan = os.path.join(ROOT, trong_repo)
        with open(duong_dan, "rb") as fh:
            ban_repo = fh.read()

        doc = _wsl("cat", trong_hop)
        if doc.returncode != 0:
            print(f"✗ {trong_hop}: KHÔNG ĐỌC ĐƯỢC trong hộp "
                  f"({doc.stderr.strip()[:80]})")
            lech += 1
            continue

        ban_hop = doc.stdout.encode("utf-8")
        ma_repo, ma_hop = _chi_ma(ban_repo.decode("utf-8")), _chi_ma(doc.stdout)

        if ma_repo == ma_hop:
            print(f"✓ {trong_repo} khớp với {DISTRO}:{trong_hop}")
            print(f"    {len(ma_repo)} dòng mã · băm {_bam(ban_repo)}")
            continue

        lech += 1
        print(f"✗ {trong_repo} LỆCH với {DISTRO}:{trong_hop}")
        print(f"    repo: {len(ma_repo)} dòng mã · băm {_bam(ban_repo)}")
        print(f"    hộp : {len(ma_hop)} dòng mã · băm {_bam(ban_hop)}")
        print("    → thứ ĐANG CHẠY không phải thứ trong repo.")

        if not args.chep:
            continue

        # SAO LƯU trước khi đè. Hộp có thể có sửa riêng mà không ai biết, và
        # một bản sao lưu rẻ hơn nhiều so với việc đi tìm lại nó.
        moc = datetime.now().strftime("%Y-%m-%d-%H%M")
        sao_luu = f"{trong_hop}.bak-{moc}"
        if _wsl("cp", trong_hop, sao_luu).returncode != 0:
            print(f"    ✗ không sao lưu được → KHÔNG chép đè.")
            continue

        # Đẩy thẳng qua stdin. Không file tạm nào cả — bản đầu viết một file
        # `.tho-tam` ở gốc repo, và `testPathsPointAtRealFiles` bắt ngay:
        # một đường dẫn viết cứng trỏ vào thứ không tồn tại. Hàng rào bắt
        # đúng mã của người vừa dựng ra nó, và đó là dấu hiệu nó thật.
        with open(duong_dan, "rb") as fh:
            ghi = subprocess.run(
                ["wsl.exe", "-d", DISTRO, "--", "tee", trong_hop],
                stdin=fh, capture_output=True, timeout=120)

        if ghi.returncode != 0:
            print(f"    ✗ chép hỏng: {ghi.stderr.decode()[:120]}")
            continue

        bien_dich = _wsl("python3", "-m", "py_compile", trong_hop)
        if bien_dich.returncode != 0:
            print(f"    ✗ chép xong nhưng KHÔNG BIÊN DỊCH ĐƯỢC — khôi phục.")
            _wsl("cp", sao_luu, trong_hop)
            continue
        print(f"    ✓ đã chép, biên dịch sạch · bản cũ ở {sao_luu}")

    print()
    if lech:
        print(f"{lech} chỗ lệch. `--chep` để đồng bộ.")
        print("Chép xong nhớ xem lượt chạy kế tiếp trong journal của hộp:")
        print(f"  wsl -d {DISTRO} -- journalctl --user -u hop-tho -n 5")
    else:
        print("Hộp đang chạy đúng mã trong repo.")
    return 1 if lech else 0


if __name__ == "__main__":
    raise SystemExit(main())
