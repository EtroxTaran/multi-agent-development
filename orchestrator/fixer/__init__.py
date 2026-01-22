"""Fixer Agent module for self-healing workflow errors.

The Fixer Agent automatically diagnoses and repairs errors in the Conductor workflow.
When errors occur, the fixer intercepts before human escalation, analyzes logs,
diagnoses root causes, plans fixes, optionally consults other agents for validation,
applies the fix, and resumes the workflow.

Key Components:
- FixerAgent: Main agent class for diagnosing and fixing errors
- CircuitBreaker: Prevents infinite fix loops
- Triage: Categorizes and prioritizes errors
- Diagnosis: Analyzes errors to determine root causes
- Strategies: Fix strategies for different error types
- Validator: Validates fixes before and after application

Usage:
    from orchestrator.fixer import FixerAgent, CircuitBreaker

    fixer = FixerAgent(project_dir)
    diagnosis = await fixer.diagnose(error, context)
    fix_plan = await fixer.plan_fix(diagnosis)
    result = await fixer.apply_fix(fix_plan)
"""

from .circuit_breaker import CircuitBreaker, CircuitState
from .triage import (
    ErrorTriage,
    TriageResult,
    TriageDecision,
    ErrorCategory,
    FixerError,
)
from .diagnosis import (
    DiagnosisEngine,
    DiagnosisResult,
    RootCause,
    DiagnosisConfidence,
)
from .strategies import (
    FixStrategy,
    FixPlan,
    FixResult,
    RetryStrategy,
    ImportErrorFixStrategy,
    SyntaxErrorFixStrategy,
    TestFailureFixStrategy,
    ConfigurationFixStrategy,
    TimeoutFixStrategy,
    DependencyFixStrategy,
    get_strategy_for_error,
)
from .validator import (
    FixValidator,
    ValidationResult,
    PreValidation,
    PostValidation,
)
from .known_fixes import (
    KnownFixDatabase,
    KnownFix,
    FixPattern,
)
from .agent import FixerAgent, create_fixer_agent

__all__ = [
    # Main agent
    "FixerAgent",
    "create_fixer_agent",
    # Circuit breaker
    "CircuitBreaker",
    "CircuitState",
    # Triage
    "ErrorTriage",
    "TriageResult",
    "TriageDecision",
    "ErrorCategory",
    "FixerError",
    # Diagnosis
    "DiagnosisEngine",
    "DiagnosisResult",
    "RootCause",
    "DiagnosisConfidence",
    # Strategies
    "FixStrategy",
    "FixPlan",
    "FixResult",
    "RetryStrategy",
    "ImportErrorFixStrategy",
    "SyntaxErrorFixStrategy",
    "TestFailureFixStrategy",
    "ConfigurationFixStrategy",
    "TimeoutFixStrategy",
    "DependencyFixStrategy",
    "get_strategy_for_error",
    # Validator
    "FixValidator",
    "ValidationResult",
    "PreValidation",
    "PostValidation",
    # Known fixes
    "KnownFixDatabase",
    "KnownFix",
    "FixPattern",
]
