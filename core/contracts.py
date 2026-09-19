#!/usr/bin/env python3
"""core.contracts — 15 primitive của Travis, dạng code.

Hợp đồng chữ ở docs/CORE_CONTRACT.md. File này là bản thi hành của nó.

BA LUẬT CỦA FILE NÀY

  1. KHÔNG I/O. Không đọc file, không mở sqlite, không gọi mạng, không đọc giờ
     hệ thống ngoài `utcNow()`. Nhờ vậy mọi thứ ở đây test được không cần mạng,
     và một quyết định quyền hạn kiểm được bằng một dòng assert thay vì phải
     dựng cả một phiên Telegram.

  2. KHÔNG NGHIỆP VỤ. Ở đây không có khái niệm "chi tiêu" hay "lời nhắc".
     Thêm company mới KHÔNG được sửa file này (W3′).

  3. Tên tiếng Anh camelCase, kể cả biến Python — PRINCIPLES §7 và docs/NAMING.md
     luật L2. Trường JSON và tên trong code TRÙNG NHAU thì không còn điểm dịch
     nào để tên trôi, và tên trôi là con bug đắt nhất dự án này.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


# ══════════════════════════ nền ══════════════════════════

def utcNow() -> str:
    """Mốc thời gian ISO 8601 UTC. Một định dạng duy nhất cho cả hệ.

    Hai nơi tự định dạng theo kiểu riêng thì sớm muộn có chỗ so chuỗi ngày với
    nhau và không bao giờ khớp — đã xảy ra thật với Notion
    (`2026-08-14T12:20:00.000+07:00` so với schema 10 ký tự).
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def newId(prefix: str) -> str:
    """Định danh có tiền tố, theo §7: `tsk_`, `trc_`, `exe_`, `apr_`.

    Tiền tố không phải để đẹp: nhìn một id trong log là biết ngay nó thuộc loại
    gì, không phải đi tra bảng.
    """
    return f"{prefix}_{secrets.token_hex(8)}"


def canonicalJson(value: Any) -> str:
    """JSON tất định — khoá sắp xếp, không khoảng trắng thừa.

    Dùng cho mọi phép băm. Không tất định thì cùng một nội dung ra hai hash
    khác nhau, và chữ ký duyệt (G4) mất hiệu lực một cách ngẫu nhiên.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def payloadHash(companyId: str, capability: str, inputValue: dict) -> str:
    """Vân tay của MỘT nội dung cụ thể.

    Chữ ký của admin khoá vào đây (G4): đổi nội dung là chữ ký hết giá trị.
    Nếu không có nó thì "duyệt ghi 20.000đ" cũng duyệt luôn "ghi 20.000.000đ".
    """
    material = canonicalJson([companyId, capability, inputValue])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


# ══════════════════════════ 1. Task ══════════════════════════

class TaskStatus(str, Enum):
    """Vòng đời của một Task.

    LUẬT T-1: trạng thái là thứ CORE ghi, không phải thứ Task tự nhận.

    Bài học `is_done()` (bảng bẫy CLAUDE.md): agent tự gọi "done" với nội dung
    là câu kế hoạch → company báo XONG → CEO nói với admin đã gửi form → thật
    ra chưa gửi gì. Từ đây `completed` chỉ đến từ Verification.
    """
    created = "created"
    planned = "planned"
    approvalRequired = "approvalRequired"
    approved = "approved"
    scheduled = "scheduled"
    running = "running"
    verifying = "verifying"
    completed = "completed"

    failed = "failed"
    cancelled = "cancelled"
    denied = "denied"
    quarantined = "quarantined"
    blocked = "blocked"
    budgetExceeded = "budgetExceeded"
    needsInput = "needsInput"

    @property
    def isTerminal(self) -> bool:
        return self in _TERMINAL_STATUSES

    @property
    def isSuccess(self) -> bool:
        """CHỈ `completed`.

        Cố ý không có `isDone()`. "Đã chạy xong" và "đã làm được việc" là hai
        câu khác nhau, và lần nhầm hai câu đó CEO đã nói với admin rằng form đã
        gửi trong khi chưa gửi gì. Không chắc thì tính là CHƯA XONG.
        """
        return self is TaskStatus.completed


_TERMINAL_STATUSES = frozenset({
    TaskStatus.completed, TaskStatus.failed, TaskStatus.cancelled,
    TaskStatus.denied, TaskStatus.quarantined, TaskStatus.budgetExceeded,
})


class RiskTier(str, Enum):
    """Nặng cỡ nào. LẤY TỪ MANIFEST, không bao giờ từ envelope (G3).

    Model đề xuất việc; model không tự hạ rủi ro của việc nó đề xuất.
    """
    read = "read"
    low = "low"
    write = "write"
    high = "high"
    irreversible = "irreversible"

    @property
    def needsApprovalByDefault(self) -> bool:
        return self in (RiskTier.write, RiskTier.high, RiskTier.irreversible)

    @property
    def canEverBeWhitelisted(self) -> bool:
        """G9 — `irreversible` KHÔNG BAO GIỜ đi đường whitelist.

        Whitelist là quyền ĐỨNG, không gắn với một nội dung nào; nó mở một cánh
        cửa rộng chứ không phải một khe. Với thứ không hoàn tác được thì cửa
        rộng là sai.
        """
        return self in (RiskTier.low, RiskTier.write)


class IssuedBy(str, Enum):
    """Ai phát ra Task. Quyết định cửa nào mở.

    `ceo` KHÁC `admin`, và sự khác đó là có chủ ý: CEO hành động THAY MẶT admin
    chứ không phải LÀ admin. Gộp hai thứ lại thì sau này không viết nổi một luật
    dạng "việc này chỉ admin gõ tay mới được làm".
    """
    admin = "admin"
    ceo = "ceo"
    employee = "employee"
    scheduledTrigger = "scheduledTrigger"
    eventTrigger = "eventTrigger"
    system = "system"


@dataclass
class Task:
    """Đơn vị công việc. Không có gì chạy ngoài một Task."""
    companyId: str
    capability: str
    inputValue: dict
    riskTier: RiskTier

    taskId: str = field(default_factory=lambda: newId("tsk"))
    traceId: str = field(default_factory=lambda: newId("trc"))
    parentTaskId: Optional[str] = None
    missionId: Optional[str] = None
    projectId: Optional[str] = None
    employeeId: Optional[str] = None

    status: TaskStatus = TaskStatus.created
    issuedBy: IssuedBy = IssuedBy.admin
    issuedAt: str = field(default_factory=utcNow)
    adminIntent: str = ""

    @property
    def fingerprint(self) -> str:
        return payloadHash(self.companyId, self.capability, self.inputValue)

    def toEnvelope(self, budget: "Budget", policy: "PolicyOutcome") -> dict:
        """Hợp đồng C1 — thứ đi vào stdin của company.

        Giữ NGUYÊN hình dạng mà ops/dispatch.py đang gửi. Đổi hình ở đây là bắt
        cả 22 company sửa cùng lúc, và đó đúng là thứ W3′ cấm.
        """
        return {
            "taskId": self.taskId,
            "traceId": self.traceId,
            "parentTaskId": self.parentTaskId,
            "companyId": self.companyId,
            "capability": self.capability,
            "input": self.inputValue,
            "context": {"adminIntent": self.adminIntent},
            "budget": budget.toDict(),
            "policy": {
                "riskTier": self.riskTier.value,
                "approvalToken": policy.approvalId,
                "dryRun": policy.decision is PolicyDecision.dryRun,
            },
            "issuedBy": self.issuedBy.value,
            "issuedAt": self.issuedAt,
        }


@dataclass
class Budget:
    """Trần của một lần chạy: sâu bao nhiêu, bao lâu, bao nhiêu tiền."""
    deadlineAt: str
    depth: int = 1
    maxDepth: int = 2
    stepsUsed: int = 0
    maxSteps: int = 20
    costUsedUsd: float = 0.0
    maxCostUsd: float = 1.0

    def toDict(self) -> dict:
        return {
            "depth": self.depth, "maxDepth": self.maxDepth,
            "stepsUsed": self.stepsUsed, "maxSteps": self.maxSteps,
            "deadlineAt": self.deadlineAt,
            "costUsedUsd": self.costUsedUsd, "maxCostUsd": self.maxCostUsd,
        }


# ══════════════════════════ 2. Capability ══════════════════════════

@dataclass
class Capability:
    """Một năng lực đã khai trong companySpec.yaml.

    Đọc từ manifest, KHÔNG dựng bằng tay trong code — manifest là nguồn chân lý
    duy nhất cho tên năng lực và tên trường.
    """
    companyId: str
    name: str
    description: str
    riskTier: RiskTier
    maxDurationSec: int
    inputSchema: dict = field(default_factory=dict)
    outputSchema: dict = field(default_factory=dict)
    whitelistScope: tuple = ()
    paidApi: Optional[dict] = None

    #: Tài nguyên năng lực này chạm vào, và chạm kiểu gì.
    #:
    #: Manifest khai được (`resource: repository`); không khai thì suy từ
    #: `riskTier`. Suy chứ không đoán bừa: phần lớn company ở đây ghi vào sổ
    #: của chính nó hoặc vào Notion, tức là `database`.
    resource: Optional[ResourceKind] = None

    @property
    def qualifiedName(self) -> str:
        return f"{self.companyId}.{self.name}"

    @property
    def touches(self) -> tuple:
        """(ResourceKind, ActionKind) — để soát quyền của Employee.

        Mặc định `database` là có chủ ý và nói ra được: company của hệ này
        hoặc ghi sổ sqlite riêng, hoặc ghi Notion. Company nào chạm thứ khác
        (repo, web, telegram) thì KHAI `resource:` trong manifest — và khai
        sai thì `codemap --check` bắt, vì tên phải khớp enum.
        """
        resource = self.resource or ResourceKind.database
        action = {
            RiskTier.read: ActionKind.read,
            RiskTier.low: ActionKind.read,
            RiskTier.write: ActionKind.modify,
            RiskTier.high: ActionKind.modify,
            RiskTier.irreversible: ActionKind.delete,
        }[self.riskTier]
        return resource, action

    @property
    def canWhitelist(self) -> bool:
        """G8/G12 — nút "Luôn cho phép" chỉ hiện khi company CHO PHÉP.

        ⚠ `whitelistScope: []` là ĐÓNG, không phải "không giới hạn". Danh sách
        rỗng là falsy. Đã tốn của admin hàng tháng bấm nút vì đọc ngược dòng
        này — xem bảng bẫy CLAUDE.md và ca
        tests/regression/testManifestContract.py.

        Việc tốn TIỀN THẬT thì không bao giờ whitelist được, kể cả riskTier
        `read`: đọc không đổi gì của admin, nhưng vẫn trừ tiền.
        """
        if self.paidApi:
            return False
        if not self.riskTier.canEverBeWhitelisted:
            return False
        return bool(self.whitelistScope)

    @classmethod
    def fromManifest(cls, companyId: str, raw: dict,
                     companyResource: Optional[str] = None) -> "Capability":
        # Năng lực khai được riêng; không khai thì lấy của company (tham số
        # `companyResource`); vẫn không có thì suy từ riskTier.
        #
        # Khai ở tầng COMPANY là đủ cho hầu hết trường hợp: một company là một
        # lĩnh vực có ranh giới, và cả lĩnh vực đó thường chạm cùng một loại
        # tài nguyên. Một dòng cho cả company, thay vì một dòng cho mỗi năng lực.
        declaredResource = raw.get("resource") or companyResource
        return cls(
            companyId=companyId,
            name=raw["name"],
            description=raw.get("description", ""),
            riskTier=RiskTier(raw["riskTier"]),
            maxDurationSec=int(raw.get("maxDurationSec", 120)),
            inputSchema=raw.get("inputSchema") or {},
            outputSchema=raw.get("outputSchema") or {},
            whitelistScope=tuple(raw.get("whitelistScope") or ()),
            paidApi=raw.get("paidApi"),
            # Khai sai tên thì NÉM ngay lúc nạp, không nuốt thành mặc định:
            # một `resource: repositry` bị nuốt sẽ lặng lẽ thành `database`, và
            # quyền của employee được soát trên một tài nguyên sai (O10).
            resource=ResourceKind(declaredResource) if declaredResource else None,
        )


# ══════════════════════════ 3. Policy ══════════════════════════

class PolicyDecision(str, Enum):
    """Đúng SÁU câu trả lời. Không có câu thứ bảy, không có "tuỳ".

    Hôm nay sáu câu này nằm rải trong một hàm dài ở ops/dispatch.py và chỉ đọc
    ra được bằng cách chạy thật. Đặt tên cho chúng là bước đầu để kiểm chúng
    bằng một dòng assert.
    """
    allow = "allow"
    allowWithVerify = "allowWithVerify"
    allowWithApproval = "allowWithApproval"
    dryRun = "dryRun"
    deny = "deny"
    quarantine = "quarantine"

    @property
    def letsExecutionStart(self) -> bool:
        return self in (PolicyDecision.allow, PolicyDecision.allowWithVerify,
                        PolicyDecision.dryRun)


class ResourceKind(str, Enum):
    repository = "repository"
    filesystem = "filesystem"
    database = "database"
    telegram = "telegram"
    web = "web"
    production = "production"
    secret = "secret"


class ActionKind(str, Enum):
    read = "read"
    create = "create"
    modify = "modify"
    delete = "delete"
    deploy = "deploy"
    send = "send"
    publish = "publish"


class Environment(str, Enum):
    lab = "lab"
    dev = "dev"
    staging = "staging"
    production = "production"


@dataclass(frozen=True)
class PolicyRequest:
    """Câu hỏi đặt cho Policy. Bất biến — hỏi lại là hỏi cùng một câu."""
    identity: IssuedBy
    capability: Capability
    inputValue: dict
    environment: Environment = Environment.dev
    isDryRun: bool = False
    approvalId: Optional[str] = None
    scheduledAt: Optional[str] = None
    hasSignedSchedule: bool = False
    whitelistGrant: Optional[str] = None
    externalSpendWouldExceedCap: bool = False


@dataclass
class PolicyOutcome:
    """Câu trả lời của Policy — kèm LÝ DO đọc được.

    `reason` không phải để trang trí. Dashboard phải trả lời được "vì sao việc
    này được phép", và câu trả lời đó phải đọc được sau nhiều tuần.
    """
    decision: PolicyDecision
    reason: str
    approvalId: Optional[str] = None
    consequence: str = ""
    canWhitelist: bool = False
    requiredVerifications: tuple = ()

    @property
    def isAllowed(self) -> bool:
        return self.decision.letsExecutionStart


# ══════════════════════════ 4. Permission ══════════════════════════

@dataclass(frozen=True)
class Permission:
    """Quyền CÓ PHẠM VI.

    Đây là thứ phân biệt "Forge được ghi repo" với "Forge được ghi repo
    Panharmon, môi trường dev, không đụng nhánh main".

    LUẬT PM-1: không có quyền ngầm định. Không khai = không có.
    """
    subject: str
    resource: ResourceKind
    action: ActionKind
    projectId: Optional[str] = None
    environment: Optional[Environment] = None
    branchNotIn: tuple = ()

    def covers(self, resource: ResourceKind, action: ActionKind,
               projectId: Optional[str] = None,
               environment: Optional[Environment] = None,
               branch: Optional[str] = None) -> bool:
        if self.resource is not resource or self.action is not action:
            return False
        if self.projectId is not None and self.projectId != projectId:
            return False
        if self.environment is not None and self.environment is not environment:
            return False
        if branch is not None and branch in self.branchNotIn:
            return False
        return True


# ══════════════════════════ 5. Execution ══════════════════════════

@dataclass
class SideEffect:
    """Một thay đổi ra THẾ GIỚI BÊN NGOÀI.

    Quan trọng hơn vẻ ngoài: khi output sai schema mà company đã khai
    sideEffects, thì việc ĐÃ làm rồi — chỉ có kết quả là không đọc được. Không
    nói rõ chỗ đó thì CEO báo "chưa làm gì", admin thử lại, và việc chạy hai
    lần. Đã xảy ra 2026-08-04 với một bảng kế hoạch trên Notion.
    """
    type: str
    target: str = ""
    isReversible: bool = False


@dataclass
class Execution:
    """Một lần chạy thật, và toàn bộ dấu vết của nó."""
    taskId: str
    traceId: str
    companyId: str
    capability: str
    policyDecision: PolicyDecision
    inputHash: str

    executionId: str = field(default_factory=lambda: newId("exe"))
    employeeId: Optional[str] = None
    brainId: Optional[str] = None
    status: TaskStatus = TaskStatus.running
    summary: str = ""
    outputValue: Optional[dict] = None
    errorText: Optional[str] = None
    filesChanged: tuple = ()
    sideEffects: tuple = ()
    verification: Optional["Verification"] = None
    costUsd: float = 0.0
    paidVnd: float = 0.0
    durationMs: int = 0
    startedAt: str = field(default_factory=utcNow)
    finishedAt: Optional[str] = None

    @property
    def touchedTheWorld(self) -> bool:
        return bool(self.sideEffects)


# ══════════════════════════ 6–7. Employee và Brain ══════════════════════════

@dataclass
class Employee:
    """Danh tính bền vững, TÁCH KHỎI model đang dùng.

    LUẬT E-1: đổi Brain không làm mất Employee. `forge` hôm nay chạy bằng
    Claude, mai bằng GPT, vẫn là `forge`, vẫn giữ trí nhớ và quyền.

    LUẬT E-2: `cannot` là luật CỨNG, thắng mọi thứ khác. Personality không tạo
    permission — employee "mạnh dạn" không vì thế mà được deploy production.
    """
    employeeId: str
    role: str
    personality: tuple = ()
    expertise: tuple = ()
    permissions: tuple = ()
    cannot: tuple = ()
    preferredBrains: tuple = ()
    fallbackBrains: tuple = ()

    def isForbidden(self, what: str) -> bool:
        return what in self.cannot

    def mayDo(self, resource: ResourceKind, action: ActionKind,
              projectId: Optional[str] = None,
              environment: Optional[Environment] = None,
              branch: Optional[str] = None) -> bool:
        # `cannot` xét TRƯỚC. Một luật cấm mà có thể bị một luật cho phép lấn
        # qua thì nó không phải luật cấm.
        if self.isForbidden(f"{resource.value}.{action.value}"):
            return False
        return any(p.covers(resource, action, projectId, environment, branch)
                   for p in self.permissions)


class DataClassification(str, Enum):
    """Dữ liệu này được phép rời máy không, và tới đâu.

    "Local-first" KHÔNG có nghĩa dữ liệu không bao giờ rời máy: dùng API của
    Claude/Gemini/GPT là context tương ứng đi ra ngoài.

    Đã đo: một lượt gửi ra 37.282 byte, trong đó có hồ sơ đời tư (giờ dậy,
    nghề, nơi ở) và số dư từng ví — sang một nhà miễn phí mà admin chưa từng
    đọc điều khoản.
    """
    public = "public"
    internal = "internal"
    private = "private"
    sensitive = "sensitive"
    secret = "secret"


@dataclass
class BrainReply:
    text: str
    brainId: str
    costUsd: float = 0.0
    isError: bool = False
    rawText: str = ""

    @property
    def failed(self) -> bool:
        """LUẬT A-4: mã thoát 0 KHÔNG có nghĩa là chạy được.

        Phiên OAuth hết hạn trả `{"is_error": true, "result": "Failed to
        authenticate…"}` mà thoát MÃ 0; cùng sự cố hôm trước lại thoát mã 1.
        Bản cũ chỉ soi mã thoát nên nhánh mã-0 đi thẳng qua: admin nhận nguyên
        câu tiếng Anh làm "câu trả lời của CEO".
        """
        return self.isError or not self.text.strip()


# ══════════════════════════ 8–9. Project và Mission ══════════════════════════

@dataclass
class Project:
    projectId: str
    displayName: str
    repository: str = ""
    workspacePath: str = ""
    protectedBranch: str = "main"
    environments: tuple = ()
    allowedEmployees: tuple = ()
    allowedCapabilities: tuple = ()


class MissionStatus(str, Enum):
    draft = "draft"
    active = "active"
    blocked = "blocked"
    stalled = "stalled"
    completed = "completed"
    abandoned = "abandoned"


@dataclass
class Mission:
    missionId: str
    objective: str
    projectId: Optional[str] = None
    status: MissionStatus = MissionStatus.draft
    taskIds: tuple = ()
    metrics: tuple = ()
    risks: tuple = ()
    reviewAt: Optional[str] = None
    createdAt: str = field(default_factory=utcNow)


# ══════════════════════════ 10. Memory ══════════════════════════

class MemoryTier(str, Enum):
    session = "session"
    working = "working"
    project = "project"
    employee = "employee"
    personal = "personal"
    system = "system"


class MemoryKind(str, Enum):
    """LUẬT M-1: không biến `inference` thành `fact`.

    Nhiều model đồng thuận KHÔNG phải bằng chứng — chúng học từ cùng một mớ chữ
    nên sai giống nhau, và ba lần đoán biến thành một lần "đồng thuận".
    """
    fact = "fact"
    decision = "decision"
    inference = "inference"


@dataclass
class MemoryItem:
    tier: MemoryTier
    kind: MemoryKind
    content: str
    memoryId: str = field(default_factory=lambda: newId("mem"))
    source: str = ""
    confidence: Optional[float] = None
    createdAt: str = field(default_factory=utcNow)
    expiresAt: Optional[str] = None

    def validate(self) -> list:
        """Lỗi khai báo, dạng đọc được. Rỗng nghĩa là hợp lệ."""
        errors = []
        if self.kind is MemoryKind.inference:
            # Suy đoán không nguồn là thứ phải NÓI LẠI cho admin, không phải
            # thứ được cất như sự thật.
            if self.confidence is None:
                errors.append("inference phải có `confidence`")
            if not self.source:
                errors.append("inference phải có `source`")
        return errors

    @property
    def isExpired(self) -> bool:
        """LUẬT M-2 — thứ chỉ đúng TRONG MỘT QUÃNG phải có ngày rụng.

        Admin nói một hoàn cảnh đang diễn ra (đang yêu, đang trông khách sạn
        thay người) — không phải cảm giác một ngày, cũng không phải điều luôn
        đúng. Cất mà không hẹn ngày hết thì tệ hơn không cất: hồ sơ nạp vào mọi
        lượt và không bao giờ tự hết hạn.
        """
        return bool(self.expiresAt) and self.expiresAt < utcNow()


# ══════════════════════════ 11–12. Secret và Event ══════════════════════════

@dataclass(frozen=True)
class SecretRequest:
    """Xin một credential. KHÔNG BAO GIỜ mang giá trị, chỉ mang TÊN.

    Secret không bao giờ nằm trong: memory · prompt · audit log · source code ·
    employee profile · envelope.
    """
    subject: str
    secretName: str
    projectId: Optional[str] = None
    reason: str = ""


class EventKind(str, Enum):
    taskFailed = "taskFailed"
    taskCompleted = "taskCompleted"
    repositoryChanged = "repositoryChanged"
    dependencyUpdated = "dependencyUpdated"
    productionDown = "productionDown"
    buildFailed = "buildFailed"
    budgetNearLimit = "budgetNearLimit"
    missionStalled = "missionStalled"
    repositoryAdded = "repositoryAdded"
    scheduledCheck = "scheduledCheck"
    quotaHit = "quotaHit"


@dataclass
class Event:
    """Một điều ĐÃ xảy ra.

    LUẬT EV-1: Event ĐỀ XUẤT Task, không CẤP QUYỀN cho Task. Task do event đẻ
    ra vẫn đi qua đúng cánh cửa Policy như mọi Task khác.
    """
    kind: EventKind
    payload: dict = field(default_factory=dict)
    eventId: str = field(default_factory=lambda: newId("evt"))
    createdAt: str = field(default_factory=utcNow)
    source: str = ""


# ══════════════════════════ 13–15. Approval, Verification, Audit ══════════

class ApprovalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"
    consumed = "consumed"


@dataclass
class Approval:
    """Chữ ký của admin cho ĐÚNG MỘT nội dung."""
    approvalId: str
    traceId: str
    companyId: str
    capability: str
    payloadHash: str
    riskTier: RiskTier
    consequence: str
    status: ApprovalStatus = ApprovalStatus.pending
    scheduledAt: Optional[str] = None
    createdAt: str = field(default_factory=utcNow)

    def matches(self, fingerprint: str) -> bool:
        """G4 — đổi nội dung là chữ ký hết giá trị."""
        return secrets.compare_digest(self.payloadHash, fingerprint)


class CheckStatus(str, Enum):
    passed = "passed"
    failed = "failed"
    skipped = "skipped"
    inconclusive = "inconclusive"


#: Trạng thái KHÔNG chặn. Một nguồn sự thật duy nhất cho cả contracts.py và
#: core/verification.py — hai bản của cùng một luật là cách nó lệch đi.
_VERIFICATION_ACCEPTABLE = (CheckStatus.passed, CheckStatus.skipped)


@dataclass
class VerificationCheck:
    name: str
    status: CheckStatus
    detail: str = ""


@dataclass
class Verification:
    """Bằng chứng, không phải lời khai.

    LUẬT V-1: không có bằng chứng thì Task KHÔNG completed. "Không chắc" tính
    là CHƯA XONG.
    """
    checks: tuple = ()
    verifiedAt: str = field(default_factory=utcNow)

    @property
    def isVerified(self) -> bool:
        """`inconclusive` tính là TRƯỢT. `skipped` thì KHÔNG.

        Đây là chỗ bài học `is_done()` được đóng đinh bằng code: một bộ kiểm
        không kết luận được thì không phải một bộ kiểm đã qua.

        ⚠ `skipped` KHÁC `inconclusive`, và nhầm chúng đã xảy ra HAI LẦN:
          · lần đầu ở core/verification.py:concludeTask
          · lần hai ở ĐÂY — sửa file kia rồi quên file này, nên một lời gọi
            `read` có mọi phép kiểm đạt vẫn bị gắn nhãn `unverified`
        Đúng dòng bẫy "cùng một bài học, vá một file quên file kia".

        skipped      = CÓ NGƯỜI KHAI RÕ là không áp dụng (đọc được trong file)
        inconclusive = KHÔNG chứng minh được gì (thiếu lệnh, quá giờ)
        """
        if not self.checks:
            return False
        return all(c.status in _VERIFICATION_ACCEPTABLE for c in self.checks)

    @property
    def failedCheckNames(self) -> tuple:
        return tuple(c.name for c in self.checks
                     if c.status not in _VERIFICATION_ACCEPTABLE)

    def toDict(self) -> dict:
        return {
            "status": "verified" if self.isVerified else "unverified",
            "verifiedAt": self.verifiedAt,
            "checks": [{"name": c.name, "status": c.status.value,
                        "detail": c.detail} for c in self.checks],
        }


@dataclass
class AuditEntry:
    """Một dòng trong sổ không sửa được.

    LUẬT A-1: lần bị CHẶN cũng là dữ liệu (O5). Ghi cả cái bị từ chối — không
    tra được thì không sửa được.
    """
    taskId: str
    traceId: str
    companyId: str
    capability: str
    riskTier: RiskTier
    policyDecision: PolicyDecision
    policyReason: str
    status: TaskStatus
    inputHash: str = ""
    employeeId: Optional[str] = None
    brainId: Optional[str] = None
    costUsd: float = 0.0
    paidVnd: float = 0.0
    durationMs: int = 0
    createdAt: str = field(default_factory=utcNow)

    def toRow(self) -> dict:
        """Tên khoá TRÙNG tên cột sqlite — docs/NAMING.md luật L2.

        Trùng nhau thì không còn điểm dịch nào để tên trôi.
        """
        return {
            "taskId": self.taskId,
            "traceId": self.traceId,
            "companyId": self.companyId,
            "capability": self.capability,
            "riskTier": self.riskTier.value,
            "policyDecision": self.policyDecision.value,
            "policyReason": self.policyReason,
            "status": self.status.value,
            "inputHash": self.inputHash,
            "employeeId": self.employeeId,
            "brainId": self.brainId,
            "costUsd": self.costUsd,
            "paidVnd": self.paidVnd,
            "durationMs": self.durationMs,
            "createdAt": self.createdAt,
        }
