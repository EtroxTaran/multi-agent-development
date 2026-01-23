"""Audit trail system for CLI invocations.

Provides comprehensive logging of all agent invocations for:
- Debugging failed tasks
- Understanding agent behavior
- Cost tracking and analysis
- Compliance and accountability

Audit entries are stored in append-only JSONL format with:
- Command details and timing
- Exit codes and output
- Session information
- Parsed results
"""

from .trail import AuditConfig, AuditEntry, AuditTrail, create_audit_trail, get_project_audit_trail

__all__ = [
    "AuditTrail",
    "AuditEntry",
    "AuditConfig",
    "create_audit_trail",
    "get_project_audit_trail",
]
