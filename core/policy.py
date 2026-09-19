#!/usr/bin/env python3
"""core.policy — điểm quyết định quyền hạn, dạng một hàm THUẦN.

    outcome = decide(PolicyRequest(...))

HÔM NAY logic này nằm rải trong `ops/dispatch.py:cmd_call`, trộn với việc mở
sqlite, sinh phiếu duyệt, chạy tiến trình con và ghi sổ. Hệ quả: muốn biết
"cron có ghi được không" thì phải chạy thật cả một lượt, và câu trả lời phụ
thuộc vào trạng thái của bốn cái bảng.

Ở đây thì:

    cùng đầu vào → cùng quyết định, luôn luôn.

Không đọc file, không mở sqlite, không gọi mạng, không đọc giờ. Thứ gì cần
biết từ thế giới bên ngoài thì NGƯỜI GỌI phải tra trước và đưa vào
`PolicyRequest` — ví dụ "whitelist có khớp không", "tháng này đã tiêu bao
nhiêu tiền thật". Nhờ vậy mọi luật dưới đây kiểm được bằng một dòng assert.

⚠ FILE NÀY CHƯA THAY THẾ `ops/dispatch.py`. Nó là bản bóc ra để kiểm được;
việc chuyển người gọi sang đây là bước sau, có adapter và có test — xem
docs/ARCHITECTURE.md §5. Đừng sửa luật ở một chỗ mà quên chỗ kia: ca
tests/regression/testPolicyParity.py canh đúng chuyện đó.
"""
from __future__ import annotations

from .contracts import (
    Capability, IssuedBy, PolicyDecision, PolicyOutcome, PolicyRequest,
    RiskTier, canonicalJson,
)


def decide(request: PolicyRequest) -> PolicyOutcome:
    """Quyết định cho một lời gọi. Thứ tự các luật ở đây là CÓ CHỦ Ý.

    Luật chặn đứng TRƯỚC luật cho phép, và luật rẻ đứng trước luật đắt. Đảo thứ
    tự là đổi hành vi: nếu xét whitelist trước S3 thì một quyền đứng sẽ mở được
    cửa cho cron ghi, đúng thứ S3 sinh ra để cấm.
    """
    capability = request.capability

    for rule in (_ruleScheduledTriggerIsReadOnly,
                 _ruleExternalSpendCap,
                 _ruleDryRunNeverAsks,
                 _ruleReadIsFree,
                 _ruleScheduleMustWait,
                 _ruleWhitelistGrant,
                 _ruleApprovalToken):
        outcome = rule(request, capability)
        if outcome is not None:
            return outcome

    return _needApproval(request, capability,
                         "Cần admin duyệt trước khi thực hiện")


# ══════════════════════════ từng luật ══════════════════════════

def _ruleScheduledTriggerIsReadOnly(request: PolicyRequest,
                                    capability: Capability):
    """S3 — việc định kỳ chỉ được phép ĐỌC.

    Kiểm ở ĐÂY chứ không tin registry/schedules.yaml: lịch là dữ liệu,
    policy là luật. Khai nhầm một lịch thành `write` thì bị chặn ở đây, không
    phải chạy rồi mới biết.

    NGOẠI LỆ DUY NHẤT: lời gọi mang theo PHIẾU HẸN admin đã ký sẵn. Đó không
    phải "cho cron quyền ghi" — cron vẫn không có quyền gì; nó chỉ mở một chữ
    ký của admin đúng vào giờ đã hẹn, khoá vào đúng một nội dung, dùng một lần.

    Whitelist thì KHÔNG nâng được S3: whitelist là quyền ĐỨNG, không gắn với
    nội dung nào, nên nó mở một cánh cửa rộng chứ không phải một khe.
    """
    if request.identity is not IssuedBy.scheduledTrigger:
        return None
    if capability.riskTier is RiskTier.read:
        return None
    if request.hasSignedSchedule:
        return None
    return PolicyOutcome(
        decision=PolicyDecision.deny,
        reason=(f"S3 — việc định kỳ chỉ được phép ĐỌC. "
                f"'{capability.name}' là '{capability.riskTier.value}'. "
                "Cron quan sát và chuẩn bị; muốn hành động thì chờ admin, "
                "hoặc dùng phiếu hẹn admin đã ký trước."))


def _ruleExternalSpendCap(request: PolicyRequest, capability: Capability):
    """L8 — cầu dao TIỀN THẬT.

    Khác hạn mức gói Pro (dùng hết thì thôi, tháng sau lại có), đây là tiền trừ
    vào thẻ của admin: đo được từng lời gọi và có hoá đơn đối chiếu. Đây mới là
    chỗ cầu dao có ý nghĩa.

    CỐ Ý KHÔNG có cầu dao cho hạn mức token ở đây. Bản cũ từng cộng giá token
    rồi khoá việc GHI, và nó sai hai tầng: con số là hệ tự bịa từ bảng giá
    (Anthropic không phơi ra hạn mức còn lại), và nó chặn NGƯỢC — chỉ chặn
    `write` vốn tốn $0 vì company là code cứng, trong khi thứ thật sự đốt hạn
    mức lại toàn là `read`.
    """
    if not capability.paidApi or request.isDryRun:
        return None
    if not request.externalSpendWouldExceedCap:
        return None
    return PolicyOutcome(
        decision=PolicyDecision.deny,
        reason=("L8 — lời gọi này vượt trần tiền thật của tháng. "
                "Muốn tiêu thêm thì sửa `chiTieuNgoai.tranThangVnd` trong "
                "registry/gateway.yaml."))


def _ruleDryRunNeverAsks(request: PolicyRequest, capability: Capability):
    """W2 — chạy khô thì không hỏi ai, vì nó không làm gì.

    Đã soát cả 22 company: chúng chặn `dryRun` TRƯỚC khi chạm handler và trước
    cả khi lấy token. Nên đường này không đụng Notion, không đụng mạng.
    """
    if not request.isDryRun:
        return None
    return PolicyOutcome(
        decision=PolicyDecision.dryRun,
        reason="W2 — chạy khô: in ra việc định làm, không làm.")


def _ruleReadIsFree(request: PolicyRequest, capability: Capability):
    """Đọc thì không đổi gì của admin → không cần chữ ký.

    TRỪ khi nó tốn TIỀN THẬT. Rủi ro lúc đó không nằm ở dữ liệu mà ở ví, nên
    `paidApi` phải qua cửa duyệt dù riskTier là `read`.
    """
    if capability.paidApi:
        return None
    if capability.riskTier.needsApprovalByDefault:
        return None
    return PolicyOutcome(
        decision=PolicyDecision.allow,
        reason=f"riskTier `{capability.riskTier.value}` — không đổi gì, không hỏi.")


def _ruleScheduleMustWait(request: PolicyRequest, capability: Capability):
    """Hẹn giờ thì KHÔNG BAO GIỜ chạy ngay, kể cả khi whitelist đã cho phép.

    Whitelist trả lời câu "được làm không"; hẹn giờ trả lời câu "làm lúc nào".
    Cho whitelist nuốt luôn cái hẹn thì việc chạy ngay lập tức — đúng thứ admin
    vừa bảo là đừng làm.
    """
    if not request.scheduledAt:
        return None
    return _needApproval(
        request, capability,
        f"hẹn tới {request.scheduledAt}",
        consequencePrefix=f"[HẸN {request.scheduledAt}] ",
        consequenceSuffix=" — admin ký bây giờ, hệ chạy đúng giờ đã hẹn.")


def _ruleWhitelistGrant(request: PolicyRequest, capability: Capability):
    """G8 — quyền đứng admin đã cấp trước, có phạm vi và có trần ngày.

    G9: `irreversible` và `paidApi` KHÔNG BAO GIỜ đi đường này. "Luôn cho phép
    tiêu tiền" là câu không ai thật sự muốn nói.
    """
    if not request.whitelistGrant:
        return None
    if not capability.canWhitelist:
        return None
    return PolicyOutcome(
        decision=PolicyDecision.allowWithVerify,
        reason=f"whitelist {request.whitelistGrant}")


def _ruleApprovalToken(request: PolicyRequest, capability: Capability):
    """Admin đã bấm duyệt cho đúng nội dung này.

    Người gọi đã `consume()` phiếu và chỉ truyền `approvalId` vào đây khi phiếu
    hợp lệ. Policy KHÔNG tự đọc bảng phiếu — đó là I/O, và I/O trong hàm quyết
    định là thứ làm nó hết tất định.
    """
    if not request.approvalId:
        return None
    return PolicyOutcome(
        decision=PolicyDecision.allowWithVerify,
        reason=f"admin đã duyệt ({request.approvalId})",
        approvalId=request.approvalId)


# ══════════════════════════ dựng câu hỏi duyệt ══════════════════════════

def _needApproval(request: PolicyRequest, capability: Capability, reason: str,
                  consequencePrefix: str = "",
                  consequenceSuffix: str = "") -> PolicyOutcome:
    """G5 — nói HẬU QUẢ, không nói tên hàm.

    Admin bấm nút dựa trên câu này, nên nó phải nói cái sẽ xảy ra với thế giới
    thật. Với việc tốn tiền thật thì GIÁ chính là hậu quả cần thấy, và nó đặt
    lên ĐẦU câu chứ không giấu ở cuối: đó là thứ phân biệt "đồng ý làm" với
    "đồng ý trả tiền".
    """
    money = ""
    if capability.paidApi:
        price = float(capability.paidApi.get("giaUocVnd", 0) or 0)
        provider = capability.paidApi.get("nhaCungCap", "API ngoài")
        money = f"TỐN TIỀN THẬT ~{price:,.0f}đ ({provider}). "

    consequence = (f"{consequencePrefix}{money}{capability.description} "
                   f"Nội dung: {_shorten(request.inputValue)}"
                   f"{consequenceSuffix}")

    return PolicyOutcome(
        decision=PolicyDecision.allowWithApproval,
        reason=reason,
        consequence=consequence,
        # Nút "Luôn cho phép" chỉ hiện khi company CHO PHÉP, và không bao giờ
        # hiện cho việc tốn tiền thật.
        canWhitelist=capability.canWhitelist,
    )


def _shorten(value, limit: int = 160) -> str:
    text = canonicalJson(value)
    return text if len(text) <= limit else text[:limit] + "…"
