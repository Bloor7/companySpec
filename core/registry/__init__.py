#!/usr/bin/env python3
"""core.registry — nạp registry/projects.yaml thành Project.

File dữ liệu đã có từ trước và đã đúng hình: dự án là DỮ LIỆU, không phải một
tầng trong sơ đồ gọi. Thêm dự án thứ hai = thêm một khối trong file đó, không
đẻ company mới, không đụng Core (W3′).

Ở đây chỉ thêm phần SOÁT và phần tra cứu có kiểu.
"""
from __future__ import annotations

import os

import yaml

from ..contracts import Environment, Project

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # core/<goi>/ nen lui BA cap
#: §15/§35 — mỗi dự án MỘT FILE trong projects/, kèm một danh mục.
#:
#: Tách ra từ registry/projects.yaml ngày 2026-09-20. Một file một dự án thì
#: thêm dự án là thêm file, và diff của một thay đổi chỉ chạm đúng dự án đó —
#: không còn cảnh hai người sửa hai dự án mà đụng nhau trong một file.
PROJECTS_DIR = os.path.join(ROOT, "projects")
PROJECTS_REGISTRY = os.path.join(PROJECTS_DIR, "registry.yaml")


class ProjectManifestError(ValueError):
    pass


def listProjectIds(registryPath: str = PROJECTS_REGISTRY) -> tuple:
    """Dự án nào ĐANG hoạt động, theo danh mục.

    Đọc danh mục chứ không quét thư mục: một file bỏ quên trong `projects/` mà
    không có tên trong danh mục là dự án đã ngừng. Quét thư mục thì nó sống
    dậy trong im lặng, và không ai nhớ vì sao nó lại chạy.
    """
    if not os.path.exists(registryPath):
        return ()
    with open(registryPath, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return tuple(raw.get("projects") or ())


def loadProjects(directory: str = PROJECTS_DIR) -> dict:
    """{projectId: Project} — mỗi dự án một file (§15)."""
    projects = {}
    for projectId in listProjectIds(os.path.join(directory, "registry.yaml")):
        path = os.path.join(directory, f"{projectId}.yaml")
        if not os.path.exists(path):
            # Danh mục nói có mà file không có: NÓI RA, đừng bỏ qua. Im lặng ở
            # đây nghĩa là một dự án biến mất khỏi hệ mà không ai được báo.
            raise ProjectManifestError(
                f"danh mục khai dự án `{projectId}` nhưng không có "
                f"{os.path.relpath(path, ROOT)}")
        with open(path, encoding="utf-8") as fh:
            block = yaml.safe_load(fh) or {}
        projects[projectId] = Project(
            projectId=projectId,
            displayName=block.get("displayName", projectId),
            repository=block.get("repo", "") or "",
            workspacePath=(block.get("workspace") or {}).get("path", "")
            if isinstance(block.get("workspace"), dict) else "",
            # Khoá tiếng Việt `nhanhBaoVe` còn nguyên trong file dữ liệu đang
            # chạy — đọc nó chứ không bắt admin đổi file. Đọc cả tên tiếng Anh
            # để dự án mới viết theo §7 mà không phải sửa bộ nạp.
            protectedBranch=block.get("protectedBranch")
            or block.get("nhanhBaoVe") or "main",
            environments=tuple(block.get("environments") or ()),
            allowedEmployees=tuple(block.get("allowedEmployees") or ()),
            allowedCapabilities=tuple(block.get("allowedCapabilities") or ()),
        )
    return projects


def mayEmployeeWorkOn(project: Project, employeeId: str) -> bool:
    """Danh sách RỖNG nghĩa là CHƯA AI ĐƯỢC, không phải "ai cũng được".

    Đây là chỗ `whitelistScope: []` đã dạy một bài đắt: giá trị rỗng trong
    manifest thường mang nghĩa NGƯỢC với trực giác, và người đọc sau này sẽ
    đoán sai. Ở đây mặc định nghiêng về phía ĐÓNG, và nói rõ trong tên hàm là
    nó trả lời câu "được phép chưa", không phải "có bị cấm không".
    """
    return employeeId in project.allowedEmployees


def isProtectedBranch(project: Project, branch: str) -> bool:
    """R2 — nhánh chính chỉ admin ghi. Company và employee đẩy nhánh phụ."""
    return branch == project.protectedBranch


def workspaceIsSafe(project: Project, path: str) -> bool:
    """Company KHÔNG BAO GIỜ được trỏ vào thư mục làm việc thật của admin.

    Ở đó có việc đang làm dở và có `.env.local` chứa khoá Supabase, Resend
    thật. Company tự clone một bản riêng — đó là lý do `workspace.path` tồn tại
    tách khỏi chỗ admin ngồi làm.
    """
    if not path:
        return False
    normalised = os.path.normpath(path)
    home = os.path.expanduser("~")
    # Thư mục ngay dưới HOME mang đúng tên dự án là chỗ admin hay ngồi.
    adminWorkspace = os.path.normpath(os.path.join(home, project.projectId))
    return normalised != adminWorkspace


def environmentsOf(project: Project) -> tuple:
    parsed = []
    for name in project.environments:
        try:
            parsed.append(Environment(name))
        except ValueError:
            raise ProjectManifestError(
                f"{project.projectId}: môi trường `{name}` không hợp lệ. "
                f"Chọn: {', '.join(e.value for e in Environment)}")
    return tuple(parsed)
