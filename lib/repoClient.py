#!/usr/bin/env python3
"""repoClient — bản sao làm việc của một dự án code. Dùng chung cho MỌI project company.

Đứng đúng vai trò của notionClient: chỗ DUY NHẤT biết cách nói chuyện với git,
để mỗi project company chỉ còn manifest + entrypoint mỏng. Đây là điều kiện để
C4 vẫn đúng khi hệ vươn ra ngoài — thêm dự án không đụng CEO, không đụng
dispatcher.

BA LUẬT CỨNG, đặt ở đây chứ KHÔNG đặt trong lời dặn CEO. Lời dặn thì model có
thể hiểu sai hoặc bị nội dung lạ lái đi; code thì không.

  R1. Company chỉ đụng bản clone CỦA CHÍNH NÓ, dưới workspaces/<companyId>/.
      Không bao giờ chạm thư mục làm việc của admin. Ở đó có việc đang làm dở
      (sẽ bị giẫm) và có .env chứa khoá thật (sẽ bị đọc).

  R2. Nhánh bảo vệ — khai trong registry/projects.yaml — không ai ghi được
      ngoài admin. Company đẩy nhánh phụ.

  R3. Clone mà lòi ra file secret thì DỪNG NGAY, không làm tiếp.
      Bình thường không xảy ra: .env luôn bị gitignore nên bản clone sạch — đó
      chính là thứ khiến R1 an toàn. Nhưng nếu một dự án lỡ commit .env thì lập
      luận đó sụp, và ta phải biết ngay lập tức chứ không phải im lặng chạy
      tiếp với khoá thật nằm trong tay một tiến trình đọc nội dung từ internet.
"""
import os
import subprocess

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DANH_MUC = os.path.join(ROOT, "registry", "projects.yaml")
WORKSPACES = os.path.join(ROOT, "workspaces")

GIT_TIMEOUT = 180

# R3 — tên file không bao giờ được phép nằm trong một bản clone.
MAU_SECRET = (".env", ".envrc", "id_rsa", "id_ed25519",
              ".pem", ".key", ".p12", ".pfx", "credentials.json")


class RepoError(Exception):
    """Hỏng ở mức phải dừng: sai cấu hình, phạm luật, hoặc git thất bại."""


# ───────────────────────── danh mục ─────────────────────────

def doc_du_an(project_id: str) -> dict:
    """Khối khai báo của một dự án. Thiếu field bắt buộc thì hỏng NGAY tại đây.

    Thà chết lúc đọc cấu hình còn hơn chết giữa chừng khi đã clone xong và đang
    cầm nửa trạng thái.
    """
    try:
        with open(DANH_MUC, encoding="utf-8") as fh:
            danh_muc = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        raise RepoError(f"Chưa có danh mục dự án: {DANH_MUC}")

    du_an = (danh_muc.get("projects") or {}).get(project_id)
    if not du_an:
        co = ", ".join(sorted((danh_muc.get("projects") or {}))) or "chưa có dự án nào"
        raise RepoError(f"Không có dự án '{project_id}' trong danh mục. Đang có: {co}")

    for field in ("repo", "nhanhBaoVe"):
        if not du_an.get(field):
            raise RepoError(f"Dự án '{project_id}' thiếu '{field}' trong danh mục")
    return du_an


def danh_sach_du_an() -> list[str]:
    with open(DANH_MUC, encoding="utf-8") as fh:
        return sorted((yaml.safe_load(fh) or {}).get("projects") or {})


# ───────────────────────── R1: chỗ làm việc ─────────────────────────

def thu_muc(company_id: str) -> str:
    """Đường dẫn bản clone của một company. R1 được ép ở đây.

    companyId đi vào tên thư mục nên phải lọc: một companyId kiểu '../../..' là
    đường thoát ra khỏi workspaces, và từ đó ra tới thư mục của admin.
    """
    if not company_id or not company_id.replace("-", "").replace("_", "").isalnum():
        raise RepoError(f"companyId không hợp lệ: {company_id!r}")

    duong_dan = os.path.abspath(os.path.join(WORKSPACES, company_id))
    if os.path.commonpath([duong_dan, os.path.abspath(WORKSPACES)]) != os.path.abspath(WORKSPACES):
        raise RepoError(f"R1 — đường dẫn thoát ra ngoài workspaces: {duong_dan}")
    return duong_dan


def _git(cwd: str, *args: str, cho_phep_loi: bool = False) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                          text=True, timeout=GIT_TIMEOUT)
    if proc.returncode != 0 and not cho_phep_loi:
        raise RepoError(f"git {' '.join(args)} hỏng: {proc.stderr.strip()[:300]}")
    return proc.stdout.strip()


# ───────────────────────── R3: quét secret ─────────────────────────

def quet_secret(cwd: str) -> list[str]:
    """File secret ĐANG NẰM TRONG repo (theo git, không phải theo đĩa).

    Quét theo `git ls-files` chứ không quét cây thư mục: thứ đáng sợ là cái đã
    bị commit và phát tán, không phải file rác nằm cạnh. Quét cây còn phải lội
    qua node_modules — chậm và vô nghĩa.
    """
    xau = []
    for duong_dan in _git(cwd, "ls-files").splitlines():
        ten = os.path.basename(duong_dan).lower()
        if any(ten == m or ten.startswith(m + ".") or ten.endswith(m)
               for m in MAU_SECRET):
            xau.append(duong_dan)
    return xau


# ───────────────────────── đồng bộ ─────────────────────────

def dong_bo(project_id: str, company_id: str) -> dict:
    """Đảm bảo company có một bản clone sạch, mới. Trả về trạng thái repo.

    Chưa có thì clone; có rồi thì fetch. CHỈ fast-forward khi đang đứng trên
    nhánh bảo vệ và cây sạch — không bao giờ reset --hard, vì sau này company
    sẽ có nhánh việc riêng ở đây và một cú reset là mất trắng công của nó.
    """
    du_an = doc_du_an(project_id)
    cwd = thu_muc(company_id)
    nhanh_bao_ve = du_an["nhanhBaoVe"]

    if not os.path.isdir(os.path.join(cwd, ".git")):
        os.makedirs(WORKSPACES, exist_ok=True)
        proc = subprocess.run(
            ["git", "clone", "--branch", nhanh_bao_ve, du_an["repo"], cwd],
            capture_output=True, text=True, timeout=GIT_TIMEOUT)
        if proc.returncode != 0:
            raise RepoError(f"Clone hỏng: {proc.stderr.strip()[:300]}")
        vua_clone = True
    else:
        _git(cwd, "fetch", "--prune", "origin")
        vua_clone = False

    # R3 — kiểm NGAY sau khi có mã nguồn, trước khi ai kịp đọc gì từ nó.
    lo = quet_secret(cwd)
    if lo:
        # Từ chối làm việc mà vẫn để khoá nằm trên đĩa là nửa vời. Vừa clone
        # xong thì xoá luôn — không mất gì, vì chưa ai kịp làm gì trong đó.
        # Còn bản có sẵn thì KHÔNG xoá: trong đó có thể có nhánh việc chưa đẩy,
        # và xoá công của người khác để dọn rác là cái giá quá đắt.
        if vua_clone:
            subprocess.run(["rm", "-rf", cwd], timeout=60)
            them = "Bản clone đã bị xoá."
        else:
            them = f"CẢNH BÁO: bản clone cũ ở {cwd} vẫn đang giữ file này."
        raise RepoError(
            f"R3 — repo của '{project_id}' có file secret bị commit: "
            f"{', '.join(lo[:5])}. Dừng lại. {them} Gỡ khỏi lịch sử git và đổi "
            f"khoá trước khi cho company đụng vào dự án này.")

    nhanh = _git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    ban = _git(cwd, "status", "--porcelain")
    if not vua_clone and nhanh == nhanh_bao_ve and not ban:
        _git(cwd, "merge", "--ff-only", f"origin/{nhanh_bao_ve}", cho_phep_loi=True)

    return trang_thai(project_id, company_id)


def trang_thai(project_id: str, company_id: str) -> dict:
    """Ảnh chụp repo: đang ở nhánh nào, mới tới đâu, có gì chưa commit."""
    du_an = doc_du_an(project_id)
    cwd = thu_muc(company_id)
    if not os.path.isdir(os.path.join(cwd, ".git")):
        raise RepoError(f"Chưa có bản clone cho '{company_id}'. Gọi dong_bo() trước.")

    nhanh_bao_ve = du_an["nhanhBaoVe"]
    ban = [d for d in _git(cwd, "status", "--porcelain").splitlines() if d]
    commits = [
        {"hash": d.split(" ", 1)[0], "tieuDe": d.split(" ", 1)[1] if " " in d else ""}
        for d in _git(cwd, "log", "-5", "--pretty=%h %s").splitlines()
    ]
    return {
        "duAn": project_id,
        "nhanh": _git(cwd, "rev-parse", "--abbrev-ref", "HEAD"),
        "nhanhBaoVe": nhanh_bao_ve,
        "commitMoiNhat": commits[0] if commits else None,
        "commits": commits,
        "soFileChuaCommit": len(ban),
        "nhanhPhu": [n.strip() for n in _git(cwd, "branch", "--format=%(refname:short)").splitlines()
                     if n.strip() and n.strip() != nhanh_bao_ve],
    }


# ───────────────────────── R2: chặn nhánh bảo vệ ─────────────────────────

def kiem_nhanh_ghi(project_id: str, nhanh: str) -> None:
    """Gọi TRƯỚC mọi thao tác ghi. Nhánh bảo vệ thì ném, không hỏi lại.

    Chưa có capability ghi nào dùng tới — đây là ổ khóa lắp sẵn cho lúc gắn
    chìa. Lắp trước thì không ai quên; lắp sau thì có ngày quên.
    """
    nhanh_bao_ve = doc_du_an(project_id)["nhanhBaoVe"]
    if nhanh.strip() == nhanh_bao_ve:
        raise RepoError(
            f"R2 — '{nhanh_bao_ve}' là nhánh bảo vệ của '{project_id}'. "
            f"Company không ghi vào đây. Dùng nhánh phụ, admin tự gộp.")
