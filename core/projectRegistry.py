#!/usr/bin/env python3
"""core.projectRegistry — nạp registry/projects.yaml thành Project.

File dữ liệu đã có từ trước và đã đúng hình: dự án là DỮ LIỆU, không phải một
tầng trong sơ đồ gọi. Thêm dự án thứ hai = thêm một khối trong file đó, không
đẻ company mới, không đụng Core (W3′).

Ở đây chỉ thêm phần SOÁT và phần tra cứu có kiểu.
"""
from __future__ import annotations

import os

import yaml

from .contracts import Environment, Project

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS_PATH = os.path.join(ROOT, "registry", "projects.yaml")


class ProjectManifestError(ValueError):
    pass


def loadProjects(path: str = PROJECTS_PATH) -> dict:
    """{projectId: Project}."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    projects = {}
    for projectId, block in (raw.get("projects") or {}).items():
        block = block or {}
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
