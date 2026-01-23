"""Fixer research node.

This node performs deep research when the diagnosis indicates knowledge gaps
(e.g. API misuse, missing documentation). It researches the correct usage
and generates a fix plan.
"""

import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from orchestrator.langgraph.state import WorkflowState
from orchestrator.agents.adapter import create_adapter, AgentType
from orchestrator.fixer.strategies import FixPlan, FixAction
from orchestrator.fixer.diagnosis import RootCause, DiagnosisResult

logger = logging.getLogger(__name__)


async def fixer_research_node(state: WorkflowState) -> dict[str, Any]:
    """Perform research and create a fix plan.

    Args:
        state: Current workflow state

    Returns:
        State updates with fix plan
    """
    project_dir = Path(state["project_dir"])
    current_fix = state.get("current_fix_attempt", {})
    
    if not current_fix:
        return {"next_decision": "escalate"}

    diagnosis_data = current_fix.get("diagnosis", {})
    if not diagnosis_data:
        return {"next_decision": "escalate"}

    # Reconstruct diagnosis object
    diagnosis = DiagnosisResult.from_dict(diagnosis_data)
    
    logger.info(f"Starting research for root cause: {diagnosis.root_cause.value}")

    # Initialize researcher
    researcher = create_adapter(AgentType.CLAUDE, project_dir)

    # Build research prompt
    prompt = f"""
I need to fix a bug related to {diagnosis.root_cause.value}.
Error: {diagnosis.error.message}

The diagnosis suggests: {diagnosis.explanation}

Your task:
1. Research the correct usage/pattern for this scenario.
2. Analyze the affected code (if any).
3. Generate a specific code fix.

Affected Files:
{json.dumps([f.to_dict() for f in diagnosis.affected_files], indent=2)}

Respond with a JSON object containing the fix actions:
{{
    "strategy_name": "research_based_fix",
    "confidence": 0.9,
    "actions": [
        {{
            "type": "modify_file",
            "target": "path/to/file",
            "description": "Explanation of change",
            "content": "New file content OR diff",
            "verify_command": "pytest tests/test_fix.py"
        }}
    ]
}}
"""
    
    try:
        result = await researcher.run_iteration(prompt, timeout=180)
        
        # Parse output
        import re
        
        match = re.search(r"```json\n(.*?)\n```", result.output, re.DOTALL)
        if not match:
            match = re.search(r"({.*})", result.output, re.DOTALL)
            
        if match:
            plan_data = json.loads(match.group(1))
            
            # Convert to FixPlan
            actions = []
            for action in plan_data.get("actions", []):
                # Map content/description to params if needed based on type
                params = action.get("params", {})
                if action.get("content"):
                    params["content"] = action.get("content")
                
                actions.append(FixAction(
                    action_type=action.get("type", "modify_file"),
                    target=action.get("target"),
                    params=params,
                    description=action.get("description", "Research based fix"),
                ))
                
            plan = FixPlan(
                diagnosis=diagnosis,
                strategy_name=plan_data.get("strategy_name", "research_fix"),
                actions=actions,
                confidence=plan_data.get("confidence", 0.8),
                requires_validation=True # Always validate research fixes
            )
            
            return {
                "current_fix_attempt": {
                    **current_fix,
                    "plan": plan.to_dict(),
                    "research_notes": result.output # Store full research context
                },
                "next_decision": "validate", # Go to validation
                "updated_at": datetime.now().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Research failed: {e}")
        
    return {
        "current_fix_attempt": {
            **current_fix,
            "error": "Research failed to produce a plan"
        },
        "next_decision": "escalate",
        "updated_at": datetime.now().isoformat()
    }
