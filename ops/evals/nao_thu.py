#!/usr/bin/env python3
"""Thử bộ não dự phòng bằng một nhà cung cấp GIẢ. Không tốn đồng nào, không cần mạng.

    python3 ops/evals/nao_thu.py

VÌ SAO PHẢI CÓ: `ops/evals/run.py` đo CEO thật — nó gọi model thật, tốn tiền
thật, và kết quả đổi theo tâm trạng của model. Thứ cần kiểm ở đây khác hẳn:
KHUNG XƯƠNG của vòng lặp não phụ. Model trả về tool_call thì có gọi dispatcher
không, gọi xong có nhét kết quả trở lại không, nhà đầu chuỗi hỏng thì có nhảy
nhà không, hết lượt thì có nói thật là chưa xong không. Toàn những thứ ĐÚNG SAI
RÕ RÀNG, nên phải kiểm bằng một nhà cung cấp giả đứng yên một chỗ, chứ không
kiểm bằng cách nhắn thử vài câu rồi thấy "hình như chạy được".

Nhà giả là một HTTP server nói đúng giao thức OpenAI, chạy trên localhost, trả
về đúng kịch bản mỗi ca. Nhờ vậy ca thử chạy trong vài giây, lặp lại y hệt, và
chạy được cả lúc không có khoá của nhà nào.

Lời gọi company trong đây cố ý trỏ tới một company KHÔNG TỒN TẠI: dispatcher
trả `rejected` ngay ở bước C2.1, không đụng vào Notion, không ghi gì vào sổ của
admin. Ca thử không được để lại dấu vết trong dữ liệu thật (W7).
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "ops"))
import nao  # noqa: E402

# Kịch bản của nhà giả: mỗi phần tử là một câu trả lời, lấy lần lượt.
KICH_BAN = []
DA_NHAN = []          # thân request đã nhận, để soi model được gửi gì


class NhaGia(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        than = json.loads(self.rfile.read(n) or b"{}")
        DA_NHAN.append(than)

        # Model tên "hong" thì luôn hỏng — để thử nhánh nhảy nhà.
        if than.get("model") == "hong":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"nha nay dang hong"}}')
            return
        # "hong-mang" trả thân lỗi dạng MẢNG, đúng như Gemini lúc quá tải
        # (đo thật 27/08: HTTP 503, thân là `[{"error": {...}}]`). Bản đầu của
        # llmClient ném AttributeError ở đây — một lỗi KHÔNG phải LLMError nên
        # chuỗi dự phòng không bắt được và không nhảy nhà nào.
        if than.get("model") == "hong-mang":
            self.send_response(503)
            self.end_headers()
            self.wfile.write(
                b'[{"error":{"code":503,"message":"The model is overloaded."}}]')
            return

        buoc = KICH_BAN.pop(0) if KICH_BAN else {"chu": "hết kịch bản"}
        tin = {"role": "assistant", "content": buoc.get("chu") or ""}
        if buoc.get("goi"):
            tin["tool_calls"] = [{
                "id": "call_1", "type": "function",
                # Trường LẠ mà nhà cung cấp tự gắn vào. Gemini 3.x gắn
                # `thought_signature` đúng chỗ này và bắt gửi lại y nguyên.
                "thought_signature": "chu-ky-cua-nha",
                "function": {"name": buoc["goi"]["ten"],
                             "arguments": json.dumps(buoc["goi"]["thamSo"])}}]
        d = {"choices": [{"message": tin, "finish_reason": "stop"}],
             "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
        ra = json.dumps(d).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(ra)))
        self.end_headers()
        self.wfile.write(ra)

    def log_message(self, *a):
        pass          # im lặng, không rác ra màn hình ca thử


def cau_hinh(port: int, chuoi: list, luot: int = 4) -> dict:
    return {
        "nha": {"gia": {"baseUrl": f"http://127.0.0.1:{port}/v1",
                        "khoaEnv": None, "mienPhi": True,
                        "giaVao": 0, "giaRa": 0}},
        "nao": {"macDinh": "phu", "chuoi": chuoi, "soLuotToiDa": luot,
                "chapNhanTraTien": False},
    }


GOI_HONG = {"ten": "goiCompany",
            "thamSo": {"company": "khongCoCompany", "capability": "abc",
                       "input": {}}}

CA = []


def ca(ten):
    def bọc(fn):
        CA.append((ten, fn))
        return fn
    return bọc


@ca("trả lời thẳng, không gọi company nào")
def _c1(port):
    KICH_BAN[:] = [{"chu": "Dạ xong rồi đại ca."}]
    kq = nao.chay("chào em", system_prompt="bạn là CEO",
                  cfg=cau_hinh(port, [{"nha": "gia", "model": "m1"}]))
    assert "xong rồi" in kq["result"], kq["result"]
    assert kq["num_turns"] == 1, kq["num_turns"]
    assert not kq["is_error"], kq
    assert kq["total_cost_usd"] == 0.0     # không đụng hạn mức Claude


@ca("gọi company rồi đọc kết quả trả về")
def _c2(port):
    KICH_BAN[:] = [{"goi": GOI_HONG},
                   {"chu": "Em gọi rồi nhưng bị dispatcher từ chối."}]
    kq = nao.chay("ghi giúp em", system_prompt="bạn là CEO",
                  cfg=cau_hinh(port, [{"nha": "gia", "model": "m1"}]))
    assert kq["num_turns"] == 2, kq["num_turns"]
    assert "từ chối" in kq["result"], kq["result"]
    # Kết quả dispatcher phải ĐI NGƯỢC vào prompt của lượt sau — đây mới là
    # thứ dễ hỏng nhất và cũng khó thấy nhất khi nhắn thử bằng tay.
    cuoi = DA_NHAN[-1]["messages"][-1]
    assert cuoi["role"] == "tool", cuoi
    assert "C2.1" in cuoi["content"], cuoi["content"][:200]
    # Lượt assistant gửi lại phải là BẢN GỐC, giữ cả trường lạ của nhà cung cấp.
    # Dựng lại tay là mất `thought_signature` — đo thật 27/08: Gemini 3.x trả
    # HTTP 400 ở đúng lượt này, tức là gọi được company rồi chết khi đọc kết quả.
    truoc = DA_NHAN[-1]["messages"][-2]
    assert truoc["role"] == "assistant", truoc
    assert truoc["tool_calls"][0].get("thought_signature") == "chu-ky-cua-nha", \
        "đã dựng lại lượt model và làm mất trường riêng của nhà cung cấp"


@ca("model viết JSON trong chữ thay vì dùng tool_calls")
def _c3(port):
    KICH_BAN[:] = [{"chu": "```json\n" + json.dumps(GOI_HONG["thamSo"]) + "\n```"},
                   {"chu": "Dạ em thử rồi ạ."}]
    kq = nao.chay("ghi giúp em", system_prompt="bạn là CEO",
                  cfg=cau_hinh(port, [{"nha": "gia", "model": "m1"}]))
    assert kq["num_turns"] == 2, kq["num_turns"]
    assert DA_NHAN[-1]["messages"][-1]["role"] == "tool"


@ca("nhà đầu chuỗi hỏng thì nhảy sang nhà sau")
def _c4(port):
    KICH_BAN[:] = [{"chu": "Nhà thứ hai trả lời."}]
    kq = nao.chay("hỏi tí", system_prompt="bạn là CEO",
                  cfg=cau_hinh(port, [{"nha": "gia", "model": "hong"},
                                      {"nha": "gia", "model": "m1"}]))
    assert "thứ hai" in kq["result"], kq["result"]
    assert kq["moTaNao"] == "gia/m1", kq["moTaNao"]


@ca("thân lỗi dạng MẢNG (Gemini 503) vẫn thành LLMError, vẫn nhảy nhà")
def _c4b(port):
    KICH_BAN[:] = [{"chu": "nhà sau đỡ được"}]
    kq = nao.chay("hỏi tí", system_prompt="bạn là CEO",
                  cfg=cau_hinh(port, [{"nha": "gia", "model": "hong-mang"},
                                      {"nha": "gia", "model": "m1"}]))
    assert "nhà sau" in kq["result"], kq["result"]
    # Câu lỗi phải moi được chữ nhà cung cấp thật sự nói, không phải "HTTP 503".
    assert "overloaded" in json.dumps(kq.get("daThu"), ensure_ascii=False), kq


@ca("cả chuỗi hỏng thì báo lỗi tử tế, không ném")
def _c5(port):
    KICH_BAN[:] = []
    kq = nao.chay("hỏi tí", system_prompt="bạn là CEO",
                  cfg=cau_hinh(port, [{"nha": "gia", "model": "hong"}]))
    assert kq["is_error"], kq
    assert "ops/nao.py kiem" in kq["result"], kq["result"]


@ca("hết trần lượt thì nói thật là CHƯA XONG")
def _c6(port):
    KICH_BAN[:] = [{"goi": GOI_HONG} for _ in range(10)]
    kq = nao.chay("làm mãi đi", system_prompt="bạn là CEO",
                  cfg=cau_hinh(port, [{"nha": "gia", "model": "m1"}], luot=3))
    assert kq["num_turns"] == 3, kq["num_turns"]
    assert kq["is_error"], kq
    assert "chưa" in kq["result"].lower(), kq["result"]


@ca("nhà tính tiền bị bỏ qua khi chưa cho phép trả tiền")
def _c7(port):
    cfg = cau_hinh(port, [{"nha": "gia", "model": "m1"}])
    cfg["nha"]["gia"]["mienPhi"] = False
    kq = nao.chay("hỏi tí", system_prompt="bạn là CEO", cfg=cfg)
    assert kq["is_error"], kq
    assert "tính tiền thật" in kq["result"], kq["result"]


# ───────────────────────── hội đồng ─────────────────────────
#
# Cùng một nhà giả, cùng một lý do: cái cần kiểm là KHUNG XƯƠNG cuộc họp —
# vắng người thì có nói ra không, chủ toạ trả về rác thì có vứt cả cuộc họp
# không, vòng 2 có thật sự chạy thêm một lượt không. Chất lượng câu chữ thì
# không kiểm bằng ca thử được, và cũng không nên giả vờ là kiểm được.

sys.path.insert(0, os.path.join(ROOT, "companies", "hoiDongCompany", "src"))
import main as hoidong  # noqa: E402


def cau_hinh_hd(port: int, models: list, chu_toa: str = None,
                du_bi: str = None) -> dict:
    hd = {"thanhVien": [{"nha": "gia", "model": m} for m in models],
          "chuToa": {"nha": "gia", "model": chu_toa or models[0]},
          "chapNhanTraTien": False}
    if du_bi:
        hd["chuToaDuPhong"] = {"nha": "gia", "model": du_bi}
    return {
        "nha": {"gia": {"baseUrl": f"http://127.0.0.1:{port}/v1",
                        "khoaEnv": None, "mienPhi": True,
                        "giaVao": 0, "giaRa": 0}},
        "hoiDong": hd,
    }


def _dat_cfg(cfg):
    hoidong.llmClient.nap = lambda path="": cfg


CHOT = {"chu": json.dumps({"ketLuan": "Chọn phương án B.",
                           "dongThuan": ["cả hai đều thấy A chậm"],
                           "batDong": ["A nói rủi ro cao, B nói thấp"]},
                          ensure_ascii=False)}


@ca("hội đồng ba người, chủ toạ chốt bằng JSON")
def _c8(port):
    _dat_cfg(cau_hinh_hd(port, ["m1", "m2", "m3"]))
    KICH_BAN[:] = [{"chu": "ý kiến 1"}, {"chu": "ý kiến 2"}, {"chu": "ý kiến 3"},
                   CHOT]
    out, tom, se, tien = hoidong.hoi_y({"cauHoi": "chọn A hay B, vì sao"}, 120)
    assert out["ketLuan"] == "Chọn phương án B.", out["ketLuan"]
    assert out["batDong"] and "rủi ro" in out["batDong"][0], out["batDong"]
    assert all(t["traLoi"] for t in out["thanhVien"]), out["thanhVien"]
    assert tien["paidVnd"] == 0, tien          # nhà miễn phí thì phải là 0
    assert se == []                            # chỉ nghĩ, không đổi gì


@ca("một thành viên vắng thì vẫn họp, và NÓI RA là vắng")
def _c9(port):
    _dat_cfg(cau_hinh_hd(port, ["m1", "hong", "m3"], chu_toa="m1"))
    KICH_BAN[:] = [{"chu": "ý kiến 1"}, {"chu": "ý kiến 3"}, CHOT]
    out, tom, _, _ = hoidong.hoi_y({"cauHoi": "chọn A hay B, vì sao"}, 120)
    vang = [t for t in out["thanhVien"] if not t["traLoi"]]
    assert len(vang) == 1 and vang[0]["loi"], out["thanhVien"]
    assert "vắng" in tom, tom[:200]


@ca("chỉ một người trả lời được thì KHÔNG gọi là hội đồng")
def _c10(port):
    _dat_cfg(cau_hinh_hd(port, ["m1", "hong", "hong"], chu_toa="m1"))
    KICH_BAN[:] = [{"chu": "ý kiến 1"}, CHOT]
    try:
        hoidong.hoi_y({"cauHoi": "chọn A hay B, vì sao"}, 120)
    except RuntimeError as exc:
        assert "không thành cuộc họp" in str(exc), str(exc)
        return
    raise AssertionError("phải ném RuntimeError khi chỉ có một ý kiến")


@ca("chủ toạ trả về không phải JSON thì giữ nguyên chữ, không bịa danh sách")
def _c11(port):
    _dat_cfg(cau_hinh_hd(port, ["m1", "m2"]))
    KICH_BAN[:] = [{"chu": "ý kiến 1"}, {"chu": "ý kiến 2"},
                   {"chu": "Tôi nghĩ nên chọn B, vì nó rẻ hơn."}]
    out, tom, _, _ = hoidong.hoi_y({"cauHoi": "chọn A hay B, vì sao"}, 120)
    assert out["ketLuan"].startswith("Tôi nghĩ"), out["ketLuan"]
    assert out["dongThuan"] == [] and out["batDong"] == []
    assert "Không tách được" in tom, tom[-200:]


@ca("hai vòng thì mỗi người được hỏi thêm một lần")
def _c12(port):
    _dat_cfg(cau_hinh_hd(port, ["m1", "m2"]))
    KICH_BAN[:] = [{"chu": "ý kiến 1"}, {"chu": "ý kiến 2"},
                   {"chu": "vẫn giữ ý 1"}, {"chu": "đổi sang B"}, CHOT]
    out, _, _, _ = hoidong.hoi_y(
        {"cauHoi": "chọn A hay B, vì sao", "soVong": 2}, 200)
    # 2 (vòng 1) + 2 (vòng 2) + 1 (chủ toạ) = 5 lời gọi
    assert len(DA_NHAN) == 5, len(DA_NHAN)
    assert out["soVong"] == 2
    # Vòng 2 phải ĐƯA Ý KIẾN NGƯỜI KHÁC vào prompt, nếu không thì nó chỉ là
    # hỏi lại cùng một câu — đắt gấp đôi mà không thảo luận gì.
    vong_hai = [t for t in DA_NHAN if any("Ý kiến" in (m.get("content") or "")
                                          for m in t["messages"])]
    assert vong_hai, "không lượt nào được đọc ý kiến của người khác"


@ca("chủ toạ chính câm thì ghế dự bị chốt, và NÓI RA là đã thay người")
def _c13(port):
    # Đây là cảnh thật khi hết hạn mức Pro: ghế chính là Claude, câm giữa
    # chừng, còn bốn ý kiến thì đã lấy về xong rồi.
    _dat_cfg(cau_hinh_hd(port, ["m1", "m2"], chu_toa="hong", du_bi="m1"))
    KICH_BAN[:] = [{"chu": "ý kiến 1"}, {"chu": "ý kiến 2"}, CHOT]
    out, tom, _, _ = hoidong.hoi_y({"cauHoi": "chọn A hay B, vì sao"}, 120)
    assert out["chuToa"] == "gia/m1", out["chuToa"]
    assert "Chủ toạ chính không chốt được" in out["ketLuan"], out["ketLuan"]
    assert "Chốt bởi: gia/m1" in tom, tom[-200:]


@ca("không ai chốt được thì vẫn đưa các ý kiến ra, không vứt cuộc họp")
def _c14(port):
    _dat_cfg(cau_hinh_hd(port, ["m1", "m2"], chu_toa="hong", du_bi="hong"))
    KICH_BAN[:] = [{"chu": "ý kiến 1"}, {"chu": "ý kiến 2"}]
    out, tom, _, _ = hoidong.hoi_y({"cauHoi": "chọn A hay B, vì sao"}, 120)
    assert out["chuToa"] == "", out["chuToa"]
    assert "Chưa ai chốt được" in out["ketLuan"]
    # Ý kiến đã lấy về được thì phải còn nguyên trong tay CEO.
    assert "ý kiến 1" in out["ketLuan"] and "ý kiến 2" in out["ketLuan"]


# ───────────────── cái gì RA KHỎI MÁY ─────────────────
#
# Đây là ca thử quan trọng nhất trong file, vì nó canh một lời hứa với admin
# chứ không canh một hành vi kỹ thuật: "chế độ canTrong thì hồ sơ đời tư và số
# dư ví KHÔNG đi ra nhà ngoài". Lời hứa kiểu đó rất dễ mục ruỗng — chỉ cần một
# hôm nào đó ai đó nối thêm một khối vào prompt là nó thành lời nói suông, mà
# không có dòng lỗi nào kêu lên. Nên phải bắt tận gói tin.

import gateway  # noqa: E402


def _chay_ceo_qua_nha_gia(port, muc, brief, them):
    cfg = {
        "nha": {"gia": {"baseUrl": f"http://127.0.0.1:{port}/v1",
                        "khoaEnv": None, "mienPhi": True,
                        "giaVao": 0, "giaRa": 0}},
        "nao": {"macDinh": "phu", "chuoi": [{"nha": "gia", "model": "m1"}],
                "soLuotToiDa": 2, "chapNhanTraTien": False, "riengTu": muc},
    }
    gateway.llmClient_nap = lambda: cfg
    nao.llmClient.nap = lambda path="": cfg
    nao.che_do = lambda c=None: ("phu", "ca thử")     # không đụng sổ thật
    KICH_BAN[:] = [{"chu": "ok"}]
    gateway.run_ceo("50k ck ăn sáng", "phien-thu-rieng-tu", resume=False,
                    them=them, brief=brief)
    return [m for m in DA_NHAN[0]["messages"] if m["role"] == "system"][0]["content"]


@ca("chế độ canTrong: hồ sơ và bức tranh KHÔNG ra khỏi máy")
def _c15(port):
    he = _chay_ceo_qua_nha_gia(
        port, "canTrong",
        brief="\n\nBức tranh hiện tại\nVí tiền mặt: 23.020đ\n",
        them="\n\nSổ tay tiền: ghi chi thì trừ ví.\n")
    # Dò DỮ LIỆU, không dò tiêu đề: chữ "Bức tranh hiện tại" cũng nằm trong
    # lõi SYSTEM.md (chỗ dạy CEO cách dùng khối đó), nên dò tiêu đề là ca thử
    # tự trượt trên chính mình. Bản đầu của ca này trượt đúng vì lẽ ấy.
    assert "23.020đ" not in he, "SỐ DƯ VÍ đã lọt ra ngoài"
    assert "## Hồ sơ admin" not in he, "HỒ SƠ ĐỜI TƯ đã lọt ra ngoài"
    # Cắt khối đi thì phải NÓI với model là đã cắt, nếu không nó đọc trong
    # SYSTEM.md rằng "cuối prompt có Bức tranh hiện tại", không thấy đâu, rồi
    # hoặc bịa ra số dư hoặc bảo admin là hệ hỏng.
    assert "chế độ riêng tư" in he.lower(), "chưa báo cho model biết là đã cắt"
    # Nhưng vẫn phải đủ để làm việc: danh mục và sổ tay còn nguyên.
    assert "Danh mục company" in he
    assert "Sổ tay tiền" in he


@ca("chế độ dayDu: gửi đủ, đúng như đã hứa")
def _c16(port):
    he = _chay_ceo_qua_nha_gia(
        port, "dayDu",
        brief="\n\nBức tranh hiện tại\nVí tiền mặt: 23.020đ\n", them="")
    assert "23.020đ" in he and "Bức tranh hiện tại" in he


@ca("chế độ toiThieu: không tin cũ, không sổ tay")
def _c17(port):
    he = _chay_ceo_qua_nha_gia(
        port, "toiThieu",
        brief="\n\nBức tranh hiện tại\nVí tiền mặt: 23.020đ\n",
        them="\n\nSổ tay tiền: ghi chi thì trừ ví.\n")
    assert "23.020đ" not in he and "Sổ tay tiền" not in he
    assert "Danh mục company" in he
    # Trí nhớ hội thoại cũng bị cắt ở mức này.
    assert not [m for m in DA_NHAN[0]["messages"] if m["role"] == "assistant"]


@ca("router 'họp' không dính 'phù hợp' / 'trường hợp' / 'hợp đồng'")
def _c18(port):
    # Bỏ dấu xong thì họp và hợp là một chữ. Chỗ khác trong router nạp thừa một
    # sổ là rẻ; ở đây nạp thừa nghĩa là mời CEO mở một cuộc họp tốn tiền cho
    # câu admin không hề nhờ — nên ca này canh cả hai chiều.
    for cau in ("họp chiến lược kênh youtube", "hop chien luoc kenh yt",
                "thảo luận giúp anh vụ này", "anh hỏi hội đồng vụ này"):
        assert gateway.goi_hop(cau), f"trượt: {cau}"
        assert "hoi-dong" in gateway.chon_so_tay(cau), cau
    for cau in ("cái này có phù hợp không em", "trường hợp anh nghỉ thì sao",
                "hợp đồng thuê nhà hết hạn khi nào", "50k ck ăn sáng"):
        assert not gateway.goi_hop(cau), f"dính oan: {cau}"
        assert "hoi-dong" not in gateway.chon_so_tay(cau), cau


@ca("chạm trần tháng thì KHÔNG tiêu tiền thật nữa")
def _c19(port):
    # Nhà giả khai `mienPhi: false` = nhà tính tiền. Cho phép trả tiền, nhưng
    # bảo hàm đọc sổ rằng tháng này đã chạm trần → phải tự hạ xuống miễn phí,
    # tức là bỏ qua nhà đó chứ không gọi.
    cfg = cau_hinh(port, [{"nha": "gia", "model": "m1"}])
    cfg["nha"]["gia"]["mienPhi"] = False
    cfg["nao"]["chapNhanTraTien"] = True
    goc = nao._con_tra_tien_duoc
    nao._con_tra_tien_duoc = lambda: (False, "đã tiêu 100.000đ, chạm trần.")
    try:
        kq = nao.chay("hỏi tí", system_prompt="bạn là CEO", cfg=cfg)
    finally:
        nao._con_tra_tien_duoc = goc
    assert kq["is_error"], kq
    assert "tính tiền thật" in kq["result"], kq["result"]
    assert "chạm trần" in kq["result"], kq["result"]
    assert not DA_NHAN, "đã gọi nhà tính tiền dù chạm trần"


@ca("dữ kiện đi vào prompt, và luật căn cứ đi cùng")
def _c20(port):
    _dat_cfg(cau_hinh_hd(port, ["m1", "m2"]))
    KICH_BAN[:] = [{"chu": "ý 1"}, {"chu": "ý 2"}, CHOT]
    hoidong.hoi_y({"cauHoi": "chọn A hay B, vì sao",
                   "duKien": ["Nền tảng X đổi chính sách ngày 01/08 (nguồn: "
                              "trang trợ giúp)"]}, 120)
    hoi = DA_NHAN[0]["messages"][-1]["content"]
    assert "DỮ KIỆN đã tra được" in hoi, hoi[:300]
    assert "01/08" in hoi
    he = DA_NHAN[0]["messages"][0]["content"]
    assert "[CHƯA KIỂM]" in he, "thiếu luật gắn nhãn cho khẳng định không nguồn"


@ca("không có dữ kiện thì NÓI RA, không lặng lẽ suy đoán")
def _c21(port):
    _dat_cfg(cau_hinh_hd(port, ["m1", "m2"]))
    KICH_BAN[:] = [{"chu": "ý 1"}, {"chu": "ý 2"}, CHOT]
    out, tom, _, _ = hoidong.hoi_y({"cauHoi": "chọn A hay B, vì sao"}, 120)
    assert any("KHÔNG có dữ kiện" in c for c in out["chuaKiemChung"]), \
        out["chuaKiemChung"]
    assert "CHƯA KIỂM CHỨNG" in tom, tom[-300:]
    # Câu hỏi gửi đi cũng phải nói rõ là không có gì đã kiểm.
    assert "KHÔNG có dữ kiện" in DA_NHAN[0]["messages"][-1]["content"]


@ca("số trong kết luận mà không có trong dữ kiện thì bị nêu tên")
def _c22(port):
    _dat_cfg(cau_hinh_hd(port, ["m1", "m2"]))
    chot_bia = {"chu": json.dumps(
        {"ketLuan": "Nên chờ 90 ngày, vì tỉ lệ giữ chân phải trên 30% và "
                    "kênh cần 1000 người theo dõi. Ngân sách 12 triệu là đủ.",
         "dongThuan": [], "batDong": [], "chuaKiemChung": []},
        ensure_ascii=False)}
    KICH_BAN[:] = [{"chu": "ý 1"}, {"chu": "ý 2"}, chot_bia]
    out, tom, _, _ = hoidong.hoi_y(
        {"cauHoi": "có nên mở kênh mới không",
         "duKien": ["Kênh hiện tại có 1000 người theo dõi (nguồn: trang kênh)"]},
        120)
    la = " ".join(out["chuaKiemChung"])
    # 90, 30%, 12 là số chủ toạ tự nghĩ ra → phải bị nêu.
    for so in ("90", "30%", "12"):
        assert so in la, f"bỏ sót số bịa {so}: {la}"
    # 1000 CÓ trong dữ kiện → không được kêu oan.
    assert "1000" not in la.split("Số chưa có nguồn")[-1], la
    assert "CHƯA KIỂM CHỨNG" in tom


@ca("mỗi ghế nhận một góc nhìn KHÁC nhau, và giữ nó sang vòng hai")
def _c23(port):
    _dat_cfg(cau_hinh_hd(port, ["m1", "m2"]))
    KICH_BAN[:] = [{"chu": "ý 1"}, {"chu": "ý 2"},
                   {"chu": "vẫn ý 1"}, {"chu": "vẫn ý 2"}, CHOT]
    out, _, _, _ = hoidong.hoi_y(
        {"cauHoi": "chọn A hay B, vì sao", "soVong": 2}, 200)
    he = [t["messages"][0]["content"] for t in DA_NHAN[:2]]
    assert "Người soi mặt trái" in he[0] or "Người soi mặt trái" in he[1]
    assert "Người hỏi tới gốc" in he[0] or "Người hỏi tới gốc" in he[1]
    assert he[0] != he[1], "hai ghế nhận cùng một lời dặn"
    # Vòng hai phải GIỮ vai, nếu không nó kéo mọi người về giọng trung dung.
    he2 = [t["messages"][0]["content"] for t in DA_NHAN[2:4]]
    assert any("Ghế của bạn" in h for h in he2), "vòng hai mất vai"
    assert {t["vai"] for t in out["thanhVien"]} == {"Người soi mặt trái",
                                                    "Người hỏi tới gốc"}


@ca("vai lạ thì TỪ CHỐI, không lặng lẽ bỏ ghế trống")
def _c24(port):
    _dat_cfg(cau_hinh_hd(port, ["m1", "m2"]))
    KICH_BAN[:] = [{"chu": "ý 1"}, {"chu": "ý 2"}, CHOT]
    try:
        hoidong.hoi_y({"cauHoi": "chọn A hay B", "vai": ["nguoc", "khongCo"]}, 120)
    except ValueError as exc:
        assert "khongCo" in str(exc) and "Đang có" in str(exc), str(exc)
        return
    raise AssertionError("phải ném ValueError với tên vai lạ")


@ca("chủ toạ được biết ghế nào nói gì, nhưng KHÔNG biết nhà nào")
def _c25(port):
    _dat_cfg(cau_hinh_hd(port, ["m1", "m2"]))
    KICH_BAN[:] = [{"chu": "ý 1"}, {"chu": "ý 2"}, CHOT]
    hoidong.hoi_y({"cauHoi": "chọn A hay B, vì sao"}, 120)
    chot = DA_NHAN[-1]["messages"][-1]["content"]
    assert "ghế: Người soi mặt trái" in chot, chot[:400]
    for lo in ("gia/m1", "gia/m2", "groq", "gemini"):
        assert lo not in chot, f"lộ tên nhà: {lo}"


def main() -> int:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), NhaGia)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    hong = 0
    for ten, fn in CA:
        DA_NHAN.clear()
        try:
            fn(port)
            print(f"  ĐẠT   {ten}")
        except AssertionError as exc:
            hong += 1
            print(f"  TRƯỢT {ten}\n        {exc}")
        except Exception as exc:      # O3 — hỏng thì hỏng to, kèm loại lỗi
            hong += 1
            print(f"  VỠ    {ten}\n        {type(exc).__name__}: {exc}")
    srv.shutdown()
    print(f"\n{len(CA) - hong}/{len(CA)} ca đạt")
    return 1 if hong else 0


if __name__ == "__main__":
    sys.exit(main())
