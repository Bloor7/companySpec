#!/bin/sh
# Bộ canh NẰM NGOÀI thứ nó canh — chạy bằng root, do systemd HỆ THỐNG gọi
# (companyspec-canh.timer), không nằm trong user manager của admin.
#
# Vì sao: 25/09 `user@1000.service` chết lúc bật máy (219/CGROUP, hai distro
# chung uid — xem hop/README.md). Poller, cron, hẹn giờ đều nằm TRONG user
# manager nên chết theo, và `travis health` biết hệ im lặng 23 giờ mà không nói
# được với ai: bộ báo nằm trong chính thứ đã chết. Terminal mở cả ngày, CEO câm.
#
# Việc của file này hẹp, cố ý: thấy chết thì DỰNG LẠI và GHI LẠI. Không nhắn
# Telegram — cửa ra Telegram là gateway (T1), và file này không cầm token.
# Poller lúc khởi động đọc dấu vết ở $DAU_VET rồi báo admin (poller._bao_canh).
#
# Cài (một lần, bằng root):
#   cp ops/companyspec-canh.service ops/companyspec-canh.timer /etc/systemd/system/
#   systemctl daemon-reload && systemctl enable --now companyspec-canh.timer
set -u

NGUOI="${1:?thiếu tên user, vd: canhHe.sh tsix}"
UID_NGUOI=$(id -u "$NGUOI") || exit 2
NHA=$(getent passwd "$NGUOI" | cut -d: -f6)
DAU_VET="$NHA/companySpec/ops/.canhHe.log"
BAY_GIO=$(date '+%Y-%m-%dT%H:%M:%S%z')

ghi() {
    # Ghi cho journal (người soi sau) VÀ cho poller (người báo admin).
    echo "[canh] $1"
    printf '%s\t%s\n' "$BAY_GIO" "$1" >> "$DAU_VET"
    chown "$NGUOI": "$DAU_VET" 2>/dev/null
}

trang_thai=$(systemctl is-active "user@$UID_NGUOI.service")
if [ "$trang_thai" != "active" ]; then
    # Lấy dòng lỗi CUỐI (không phải đầu) — dòng nói hỏng vì cái gì nằm ở đuôi.
    ly_do=$(journalctl -b -u "user@$UID_NGUOI.service" -n 30 --no-pager -o cat 2>/dev/null \
            | grep -E 'status=|Failed' | tail -1)
    # Ghi TRƯỚC khi dựng: poller vừa lên là đọc sổ ngay, ghi sau thì nó đọc
    # trúng lúc sổ còn trống và lần chết này thành vô hình.
    ghi "user manager '$trang_thai' → dựng lại. ${ly_do:-không rõ lý do}"
    systemctl restart "user@$UID_NGUOI.service"
    sleep 3
    sau=$(systemctl is-active "user@$UID_NGUOI.service")
    [ "$sau" = "active" ] || ghi "dựng lại user manager HỎNG ($sau) — lượt sau thử tiếp"
    exit 0
fi

# User manager sống nhưng poller có thể đã dừng hẳn (Restart=on-failure không
# dựng lại một lần thoát mã 0, hay một lần 'stop' tay rồi quên).
poller=$(runuser -u "$NGUOI" -- env XDG_RUNTIME_DIR="/run/user/$UID_NGUOI" \
         systemctl --user is-active companyspec-gateway.service)
case "$poller" in
    active|activating|reloading) ;;
    *)
        ghi "poller '$poller' → khởi động lại"
        runuser -u "$NGUOI" -- env XDG_RUNTIME_DIR="/run/user/$UID_NGUOI" \
            systemctl --user start companyspec-gateway.service \
            || ghi "khởi động lại poller HỎNG — lượt sau thử tiếp"
        ;;
esac
exit 0
