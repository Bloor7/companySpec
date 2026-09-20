#!/usr/bin/env python3
"""core.permissions — nạp employees/ thành Employee, và SOÁT chúng.

Không chỉ đọc. Một manifest employee sai là một hàng rào giả: người đọc thấy
`cannot: [production.deploy]` thì tin rằng có hàng rào, trong khi nếu viết sai
chính tả thì chẳng có gì cả và không ai báo.

Nên `loadEmployees()` ném lỗi ngay khi nạp, chứ không im lặng bỏ qua.
"""
from __future__ import annotations

import glob
import os

import yaml

from ..contracts import (
    ActionKind, DataClassification, Employee, Environment, Permission,
    ResourceKind,
)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # core/<goi>/ nen lui BA cap
EMPLOYEES_DIR = os.path.join(ROOT, "employees")


class EmployeeManifestError(ValueError):
    """Manifest employee sai. Ném ra chứ không nuốt (O10)."""


def loadEmployees(directory: str = EMPLOYEES_DIR) -> dict:
    """{employeeId: Employee}. Ném EmployeeManifestError nếu có cái nào sai."""
    employees = {}
    for path in sorted(glob.glob(os.path.join(directory, "*", "employee.yaml"))):
        employee = loadEmployee(path)
        if employee.employeeId in employees:
            raise EmployeeManifestError(
                f"{path}: trùng employeeId `{employee.employeeId}`")
        employees[employee.employeeId] = employee
    return employees


def loadEmployee(path: str) -> Employee:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    employeeId = raw.get("employeeId")
    if not employeeId:
        raise EmployeeManifestError(f"{path}: thiếu `employeeId`")
    folderName = os.path.basename(os.path.dirname(path))
    if employeeId != folderName:
        raise EmployeeManifestError(
            f"{path}: employeeId `{employeeId}` không trùng tên thư mục "
            f"`{folderName}`. Hai tên cho một người là chỗ để lạc đường.")
    if not raw.get("role"):
        raise EmployeeManifestError(f"{path}: thiếu `role`")

    return Employee(
        employeeId=employeeId,
        role=raw["role"],
        personality=tuple(raw.get("personality") or ()),
        expertise=tuple(raw.get("expertise") or ()),
        permissions=tuple(_parsePermission(employeeId, p, path)
                          for p in (raw.get("permissions") or ())),
        cannot=tuple(_parseCannot(raw.get("cannot") or (), path)),
        preferredBrains=tuple((raw.get("brains") or {}).get("preferred") or ()),
        fallbackBrains=tuple((raw.get("brains") or {}).get("fallback") or ()),
    )


def maxDataClassificationOf(path: str) -> DataClassification:
    """Mức dữ liệu cao nhất employee này được cầm.

    Đọc riêng thay vì nhét vào dataclass Employee, vì đây là chính sách ĐỊNH
    TUYẾN (brain nào được nhận), không phải thuộc tính của con người.
    """
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    value = raw.get("maxDataClassification", "internal")
    try:
        return DataClassification(value)
    except ValueError as exc:
        raise EmployeeManifestError(
            f"{path}: `maxDataClassification: {value}` không phải mức hợp lệ. "
            f"Chọn một trong: "
            f"{', '.join(c.value for c in DataClassification)}") from exc


# ══════════════════════════ soát từng mảnh ══════════════════════════

def _parsePermission(employeeId: str, raw, path: str) -> Permission:
    if not isinstance(raw, dict):
        raise EmployeeManifestError(
            f"{path}: mỗi permission phải là một object, nhận được {raw!r}")

    resource = _parseEnum(ResourceKind, raw.get("resource"), "resource", path)
    action = _parseEnum(ActionKind, raw.get("action"), "action", path)

    environment = None
    if raw.get("environment"):
        environment = _parseEnum(Environment, raw["environment"],
                                 "environment", path)

    return Permission(
        subject=employeeId,
        resource=resource,
        action=action,
        projectId=raw.get("projectId"),
        environment=environment,
        branchNotIn=tuple(raw.get("branchNotIn") or ()),
    )


def _parseCannot(raw, path: str) -> tuple:
    """`cannot` viết dạng `resource.action`, và PHẢI trỏ vào thứ có thật.

    Viết sai chính tả (`producton.deploy`) thì luật cấm biến mất trong im lặng —
    đúng họ "hàng rào giả". Nên soát ngay lúc nạp.
    """
    parsed = []
    for item in raw:
        if not isinstance(item, str) or item.count(".") != 1:
            raise EmployeeManifestError(
                f"{path}: `cannot` phải viết dạng `resource.action`, "
                f"nhận được {item!r}")
        resourceName, actionName = item.split(".")
        _parseEnum(ResourceKind, resourceName, f"cannot `{item}` resource", path)
        _parseEnum(ActionKind, actionName, f"cannot `{item}` action", path)
        parsed.append(item)
    return tuple(parsed)


def _parseEnum(enumClass, value, label: str, path: str):
    try:
        return enumClass(value)
    except ValueError as exc:
        raise EmployeeManifestError(
            f"{path}: {label} `{value}` không hợp lệ. Chọn một trong: "
            f"{', '.join(member.value for member in enumClass)}") from exc


# ══════════════════════════ tra cứu ══════════════════════════

def whoCanDo(employees: dict, resource: ResourceKind, action: ActionKind,
             projectId: str = None, environment: Environment = None,
             branch: str = None) -> tuple:
    """Những employee được phép làm việc này. Rỗng nghĩa là KHÔNG AI.

    Rỗng là một câu trả lời hợp lệ và quan trọng: nó nói rằng việc này cần
    admin, chứ không phải rằng ta chọn nhầm người.
    """
    return tuple(sorted(
        employeeId for employeeId, employee in employees.items()
        if employee.mayDo(resource, action, projectId, environment, branch)))
