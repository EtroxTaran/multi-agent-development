"""Fixer validation node.

This node optionally validates fix plans with an external agent
(Cursor or Gemini) before applying them.
"""

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from ..state import WorkflowState

logger = logging.getLogger(__name__)


async def fixer_validate_node(state: WorkflowState) -> dict[str, Any]:
    """Validate a fix plan with an external agent.

    This node:
    1. Builds a validation prompt
    2. Calls the configured validation agent (Cursor/Gemini)
    3. Parses the response
    4. Routes to apply or escalate based on approval

    Args:
        state: Current workflow state

    Returns:
        State updates with validation result
    """
    project_dir = Path(state["project_dir"])
    current_fix = state.get("current_fix_attempt", {})

    if not current_fix:
        logger.warning("Fixer validate called but no current fix attempt")
        return {
            "next_decision": "escalate",
            "updated_at": datetime.now().isoformat(),
        }

    plan_data = current_fix.get("plan", {})
    diagnosis_data = current_fix.get("diagnosis", {})

    if not plan_data:
        logger.warning("No fix plan to validate")
        return {
            "next_decision": "escalate",
            "updated_at": datetime.now().isoformat(),
        }

    # Load project config to get validation agent
    config_file = project_dir / ".project-config.json"
    validation_agent = "cursor"  # default
    if config_file.exists():
        try:
            config = json.loads(config_file.read_text())
            validation_agent = config.get("fixer", {}).get("validation_agent", "cursor")
        except json.JSONDecodeError:
            pass

    logger.info(f"Validating fix plan with {validation_agent}")

    # Build validation prompt
    prompt = _build_validation_prompt(diagnosis_data, plan_data)

    # Call validation agent
    try:
        validation_result = await _call_validation_agent(
            validation_agent,
            prompt,
            project_dir,
        )
    except Exception as e:
        logger.error(f"Validation agent call failed: {e}")
        # Proceed with caution - skip validation but add warning
        validation_result = {
            "approved": True,
            "warnings": [f"Validation agent unavailable: {e}"],
            "reason": "Proceeding without external validation",
        }

    approved = validation_result.get("approved", False)
    logger.info(f"Validation result: approved={approved}")

    # Update fix attempt with validation
    updated_fix = {
        **current_fix,
        "validation": {
            "agent": validation_agent,
            "result": validation_result,
            "timestamp": datetime.now().isoformat(),
        },
    }

    if approved:
        return {
            "current_fix_attempt": updated_fix,
            "next_decision": "apply",
            "updated_at": datetime.now().isoformat(),
        }
    else:
        return {
            "current_fix_attempt": updated_fix,
            "next_decision": "escalate",
            "errors": [{
                "type": "fixer_validation_failed",
                "message": validation_result.get("reason", "Fix plan rejected by validation agent"),
                "concerns": validation_result.get("concerns", []),
                "timestamp": datetime.now().isoformat(),
            }],
            "updated_at": datetime.now().isoformat(),
        }


def _build_validation_prompt(diagnosis_data: dict, plan_data: dict) -> str:
    """Build a prompt for validation agent."""
    error_info = diagnosis_data.get("error", {})
    actions = plan_data.get("actions", [])

    prompt = f"""Review this automated fix plan and determine if it's safe to apply.

## Error Being Fixed
- Type: {error_info.get('error_type', 'unknown')}
- Message: {error_info.get('message', 'N/A')[:500]}

## Root Cause Analysis
- Root Cause: {diagnosis_data.get('root_cause', 'unknown')}
- Confidence: {diagnosis_data.get('confidence', 'low')}
- Explanation: {diagnosis_data.get('explanation', 'N/A')[:300]}

## Affected Files
"""
    for af in diagnosis_data.get("affected_files", [])[:5]:
        prompt += f"- {af.get('path', 'unknown')}"
        if af.get("line_number"):
            prompt += f" (line {af['line_number']})"
        prompt += "\n"

    prompt += f"""
## Proposed Fix Actions
"""
    for i, action in enumerate(actions[:10], 1):
        prompt += f"{i}. [{action.get('action_type')}] {action.get('description', 'N/A')}\n"
        prompt += f"   Target: {action.get('target', 'N/A')}\n"

    prompt += """
## Validation Checklist
Please verify:
1. The fix addresses the root cause (not just symptoms)
2. No protected or sensitive files are modified
3. The scope is appropriate (not too broad)
4. No security vulnerabilities are introduced
5. The fix won't break existing functionality

## Response Format
Respond with JSON:
```json
{
  "approved": true/false,
  "reason": "Brief explanation",
  "concerns": ["List of concerns if any"],
  "suggestions": ["Optional improvements"]
}
```
"""
    return prompt


async def _call_validation_agent(
    agent: str,
    prompt: str,
    project_dir: Path,
) -> dict:
    """Call the validation agent and parse response."""
    if agent == "cursor":
        cmd = ["cursor-agent", "--print", "--output-format", "json", prompt]
    else:
        cmd = ["gemini", "--yolo", prompt]

    try:
        result = subprocess.run(
            cmd,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0 and result.stdout:
            # Try to parse JSON from output
            output = result.stdout
            # Find JSON block if present
            if "```json" in output:
                start = output.find("```json") + 7
                end = output.find("```", start)
                if end > start:
                    output = output[start:end]

            try:
                return json.loads(output)
            except json.JSONDecodeError:
                # Try to extract approval from text
                output_lower = output.lower()
                approved = "approved" in output_lower or "safe to apply" in output_lower
                return {
                    "approved": approved,
                    "reason": "Parsed from text response",
                    "raw_response": output[:500],
                }

        return {
            "approved": False,
            "reason": f"Agent returned error: {result.stderr[:200]}",
        }

    except subprocess.TimeoutExpired:
        return {
            "approved": False,
            "reason": "Validation agent timed out",
        }
    except FileNotFoundError:
        return {
            "approved": True,
            "warnings": [f"Agent '{agent}' not found - proceeding without validation"],
            "reason": "Agent unavailable",
        }
