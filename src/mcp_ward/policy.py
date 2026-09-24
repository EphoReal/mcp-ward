"""Consumer-oriented gates over one canonical finding stream."""
from __future__ import annotations

PROFILES = {
    # observe: report only, never gate.
    "observe": set(),
    # unknown means "this change is outside the v0.1 projection"; every
    # gating profile therefore fails closed on it.
    "wire": {"breaking", "unknown"},
    "agent": {"breaking", "review", "unknown"},
    "strict": {"breaking", "review", "additive", "cosmetic", "unknown"},
}


def profile_blocks(profile: str, finding) -> bool:
    """Return whether a finding should produce a non-zero gate result."""
    try:
        blocked = PROFILES[profile]
    except KeyError as exc:
        raise ValueError(f"unknown profile: {profile}") from exc
    # Strict is deliberately fail-closed for future impact names too. Other
    # profiles retain their explicit allow/block sets for known taxonomy.
    if profile == "strict" and finding.impact not in blocked:
        return True
    return finding.impact in blocked


def report_blocks(profile: str, report) -> bool:
    """Return whether any finding in a report blocks the selected profile."""
    if profile not in PROFILES:
        raise ValueError(f"unknown profile: {profile}")
    return any(profile_blocks(profile, finding) for finding in report.findings)
