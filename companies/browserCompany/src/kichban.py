#!/usr/bin/env python3
"""Kịch bản CỨNG — mở trang và thao tác theo từng bước đã định, KHÔNG dùng LLM.

Nhận JSON trên stdin, trả JSON trên stdout. Chạy bằng Python trong .venv của
company (cần playwright + Chromium riêng).

VÌ SAO CÓ FILE NÀY, BÊN CẠNH runner.py:

Đo 2026-08-17 trên form của panharmon.com. Cùng một việc — mở trang, điền ô,
bấm nút, đọc phản hồi:

    agent (qwen2.5:3b lái)   4-9 phút · ba lần đều KHÔNG xong · trả về câu
                             kế hoạch thay vì kết quả
    kịch bản cứng ở đây      ~20 giây · đúng mọi lần · 0đ

Agent chỉ đáng dùng khi KHÔNG BIẾT TRƯỚC phải bấm gì. Việc lặp lại hằng ngày
trên một trang đã biết thì viết thẳng ra là hơn: nhanh hơn hai chục lần, không
tốn tiền model, và quan trọng nhất — KẾT QUẢ GIỐNG NHAU MỖI LẦN CHẠY. Một bộ
canh gác mà lúc báo lúc không thì chẳng ai tin nó nữa.

Ba việc mà bản agent làm sai còn bản này làm đúng, đều đo được:
  · phân biệt hai nút TRÙNG TÊN "Giải mã ngay" (một ở header, một trong form)
  · biết trang thật sự gọi API hay chỉ đứng im
  · biết trang có dựng tường đăng nhập không, thay vì đoán
"""
import asyncio
import json
import os
import sys


def tim_chromium():
    """Chromium riêng của company. Giống runner.py — cố ý chép lại 6 dòng thay
    vì import lẫn nhau: hai file này chạy độc lập, và một cái hỏng thì cái kia
    vẫn phải chạy được."""
    import glob
    mau = os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")
    for p in sorted(glob.glob(mau), reverse=True):
        if os.access(p, os.X_OK):
            return p
    return None


async def chay(yc: dict) -> dict:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        return {"loi": f"chưa cài playwright trong .venv: {exc}"}
    chrome = tim_chromium()
    if not chrome:
        return {"loi": "không tìm thấy Chromium. Chạy: bash companies/browserCompany/setup.sh"}

    goi_api, buoc_da_lam = [], []
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, executable_path=chrome)
        # Hồ sơ TRẮNG như bản agent: không cookie, không phiên đăng nhập.
        ctx = await b.new_context()
        pg = await ctx.new_page()
        pg.on("response", lambda r: goi_api.append(
            {"ma": r.status, "phuongThuc": r.request.method, "url": r.url[:120]})
            if ("/api" in r.url or r.status >= 400) else None)

        try:
            resp = await pg.goto(yc["url"], wait_until="networkidle", timeout=45000)
            buoc_da_lam.append(f"mở {yc['url']}")
            ma_http = resp.status if resp else 0

            # Điền ô nhập, nếu có yêu cầu.
            if yc.get("dienVao"):
                o = await pg.query_selector(yc["dienVao"])
                if not o:
                    return {"loi": f"không tìm thấy ô nhập theo '{yc['dienVao']}'"}
                await o.fill(yc.get("noiDung") or "")
                buoc_da_lam.append(f"điền vào {yc['dienVao']}")

            truoc = len(await pg.inner_text("body"))

            # Bấm nút. `nutThu` chọn CÁI THỨ MẤY trong số các nút trùng tên —
            # trang thật hay có nút header trùng tên với nút trong form, và
            # bấm nhầm thì không có gì xảy ra mà cũng không báo lỗi.
            if yc.get("bamNut"):
                nut = await pg.query_selector_all(yc["bamNut"])
                thu = int(yc.get("nutThu") or 0)
                if len(nut) <= thu:
                    return {"loi": f"tìm thấy {len(nut)} nút theo '{yc['bamNut']}', "
                                   f"không có cái thứ {thu}"}
                await nut[thu].click(timeout=10000)
                buoc_da_lam.append(f"bấm nút thứ {thu} theo {yc['bamNut']}")
                await pg.wait_for_timeout(int(yc.get("choMs") or 8000))

            than = await pg.inner_text("body")
            tim = {t: (t in than) for t in (yc.get("timChu") or [])}

            return {
                "maHttp": ma_http,
                "tieuDe": await pg.title(),
                "soNut": len(await pg.query_selector_all("button")),
                "soOnhap": len(await pg.query_selector_all("input, textarea")),
                "chuThayDoi": len(than) - truoc,
                "timChu": tim,
                "goiApi": goi_api[:10],
                "buocDaLam": buoc_da_lam,
                "trichDoan": than[:400],
            }
        except Exception as exc:
            # O10 — hỏng thì nói hỏng ở BƯỚC NÀO, đừng chỉ nói tên ngoại lệ.
            return {"loi": f"{type(exc).__name__}: {exc}",
                    "buocDaLam": buoc_da_lam}
        finally:
            await b.close()


def main() -> int:
    try:
        yc = json.load(sys.stdin)
    except Exception as exc:
        json.dump({"loi": f"stdin không phải JSON: {exc}"}, sys.stdout); print()
        return 0
    try:
        kq = asyncio.run(chay(yc))
    except Exception as exc:
        kq = {"loi": f"{type(exc).__name__}: {exc}"}
    json.dump(kq, sys.stdout, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
