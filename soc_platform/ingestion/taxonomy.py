"""Published OCSF activity ids used by the Windows normalizer.

Only values this codebase relies on are listed. Unmapped activities use id 99.
"""

from __future__ import annotations

from dataclasses import dataclass

from soc_platform.domain.canonical import (
    APPLICATION_LIFECYCLE,
    AUTHENTICATION,
    EVENT_LOG_ACTIVITY,
    FILE_ACTIVITY,
    EventClass,
    GROUP_MANAGEMENT,
    NETWORK_ACTIVITY,
    PROCESS_ACTIVITY,
    USER_MANAGEMENT,
)


@dataclass(frozen=True)
class ActivityRule:
    event_class: EventClass
    activity_id: int
    activity_name: str
    outcome: str
    severity: str


_SECURITY: dict[int, ActivityRule] = {
    4624: ActivityRule(AUTHENTICATION, 1, "Logon", "success", "informational"),
    4625: ActivityRule(AUTHENTICATION, 1, "Logon", "failure", "medium"),
    4634: ActivityRule(AUTHENTICATION, 2, "Logoff", "success", "informational"),
    4647: ActivityRule(AUTHENTICATION, 2, "Logoff", "success", "informational"),
    4688: ActivityRule(PROCESS_ACTIVITY, 1, "Launch", "success", "informational"),
    4689: ActivityRule(PROCESS_ACTIVITY, 2, "Terminate", "success", "informational"),
    4720: ActivityRule(USER_MANAGEMENT, 1, "Create", "success", "informational"),
    4726: ActivityRule(USER_MANAGEMENT, 99, "Delete", "success", "medium"),
    4732: ActivityRule(GROUP_MANAGEMENT, 99, "Add Member", "success", "medium"),
    1102: ActivityRule(EVENT_LOG_ACTIVITY, 99, "Clear", "success", "high"),
    7045: ActivityRule(APPLICATION_LIFECYCLE, 99, "Install", "success", "medium"),
}

_SYSMON: dict[int, ActivityRule] = {
    1: ActivityRule(PROCESS_ACTIVITY, 1, "Launch", "success", "informational"),
    3: ActivityRule(NETWORK_ACTIVITY, 1, "Open", "success", "informational"),
    5: ActivityRule(PROCESS_ACTIVITY, 2, "Terminate", "success", "informational"),
    11: ActivityRule(FILE_ACTIVITY, 1, "Create", "success", "informational"),
}

ACTIVITY_RULES: dict[str, dict[int, ActivityRule]] = {
    "security": _SECURITY,
    "sysmon": _SYSMON,
}
