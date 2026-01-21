# Complete Orchestrator Implementation
## Full Python/Bash Reference for Multi-Agent Workflow

---

## Part 1: Python Orchestrator (Complete)

Save as `.workflow/orchestrator.py`

```python
#!/usr/bin/env python3
"""
Multi-Agent Orchestrator v2.0
Manages workflow phases and coordinates Claude Code, Cursor, and Gemini CLI
All agents run in the same project folder with shared context
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import logging
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('.workflow/logs/orchestrator.log')
    ]
)
logger = logging.getLogger(__name__)


class MultiAgentOrchestrator:
    """Main orchestrator for multi-agent workflows"""
    
    def __init__(self, project_dir: str = "."):
        self.project_dir = Path(project_dir).resolve()
        self.workflow_dir = self.project_dir / ".workflow"
        self.phases_dir = self.workflow_dir / "phases"
        self.state_file = self.workflow_dir / "state.json"
        self.coordination_log = self.workflow_dir / "coordination.log"
        
        # Ensure directories exist
        self.workflow_dir.mkdir(exist_ok=True)
        self.phases_dir.mkdir(exist_ok=True)
        (self.workflow_dir / "logs").mkdir(exist_ok=True)
        
    def log(self, message: str, level: str = "INFO"):
        """Log message to both console and file"""
        getattr(logger, level.lower())(message)
        
        # Also append to coordination log
        timestamp = datetime.utcnow().isoformat() + "Z"
        with open(self.coordination_log, "a") as f:
            f.write(f"[{timestamp}] [{level}] {message}\n")
    
    def load_state(self) -> Dict:
        """Load workflow state"""
        if self.state_file.exists():
            return json.loads(self.state_file.read_text())
        return {
            "phase": "init",
            "phase_num": 0,
            "status": "ready_to_start",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "current_task": None,
            "completed_tasks": [],
            "active_blockers": []
        }
    
    def save_state(self, state: Dict):
        """Persist workflow state"""
        state["last_updated"] = datetime.utcnow().isoformat() + "Z"
        self.state_file.write_text(json.dumps(state, indent=2))
        self.log(f"State saved: phase={state.get('phase')}, status={state.get('status')}")
    
    def read_product_vision(self) -> Optional[str]:
        """Read PRODUCT.md to understand current goals"""
        product_file = self.project_dir / "PRODUCT.md"
        if product_file.exists():
            return product_file.read_text()
        return None
    
    def read_agent_rules(self, agent_name: str) -> str:
        """Read agent-specific rules"""
        if agent_name == "claude":
            rules_file = self.project_dir / ".claude" / "system.md"
        elif agent_name == "cursor":
            rules_file = self.project_dir / ".cursor" / "rules"
        elif agent_name == "gemini":
            rules_file = self.project_dir / ".gemini" / "GEMINI.md"
        else:
            return ""
        
        return rules_file.read_text() if rules_file.exists() else ""
    
    def run_subprocess(self, command: List[str], timeout: int = 300) -> Tuple[int, str, str]:
        """Run subprocess and capture output"""
        self.log(f"Executing: {' '.join(command)}")
        
        try:
            result = subprocess.run(
                command,
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            self.log(f"Command completed with exit code {result.returncode}")
            return result.returncode, result.stdout, result.stderr
        
        except subprocess.TimeoutExpired:
            self.log(f"Command timed out after {timeout}s", "WARNING")
            return -1, "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            self.log(f"Command failed: {str(e)}", "ERROR")
            return -1, "", str(e)
    
    def run_phase_1_planning(self):
        """Phase 1: Claude Code breaks down PRODUCT.md into plan"""
        self.log("=" * 60)
        self.log("🔵 PHASE 1: PLANNING (Claude Code)")
        self.log("=" * 60)
        
        # Prepare phase directory
        phase_dir = self.phases_dir / "01-planning"
        phase_dir.mkdir(exist_ok=True)
        
        # Read product vision
        vision = self.read_product_vision()
        if not vision:
            self.log("ERROR: PRODUCT.md not found", "ERROR")
            return False
        
        # Create task for Claude
        prompt = f"""
You are the Planning Agent in a multi-agent orchestration system.

Your task: Read the product vision below and create a detailed implementation plan.

=== PRODUCT VISION ===
{vision}

=== YOUR TASK ===
Analyze the above vision and create:

1. **Task Breakdown**: List concrete, testable tasks with:
   - Task ID (t1, t2, t3, ...)
   - Title
   - Description
   - Dependencies (which tasks must complete first)
   - Complexity (low/medium/high)
   - Test strategy

2. **Dependency Graph**: Show which tasks block others

3. **Risk Assessment**: What could go wrong?

4. **Completion Criteria**: How do we know this is done?

=== OUTPUT ===
Save your analysis to: {phase_dir}/plan.json

Format:
{{
  "phase": "planning",
  "feature": "[feature name]",
  "tasks": [
    {{
      "id": "t1",
      "title": "...",
      "description": "...",
      "dependencies": [],
      "complexity": "low|medium|high",
      "test_strategy": "...",
      "estimated_hours": 1.5
    }}
  ],
  "dependency_graph": {{"t2": ["t1"], "t3": ["t1"]}},
  "risks": ["..."],
  "completion_criteria": "..."
}}

Also save a human-readable summary to: {phase_dir}/PLAN.md

=== INSTRUCTIONS ===
- Read the vision carefully
- Break down into concrete tasks
- Each task should be independently testable
- Identify true dependencies (not guesses)
- Be specific about test strategy
"""
        
        # Invoke Claude Code
        command = [
            "claude",
            "-p", prompt,
            "--append-system-prompt-file=" + str(self.project_dir / ".claude" / "system.md"),
            "--allowedTools", "Bash(git*),Write,Edit"
        ]
        
        exit_code, stdout, stderr = self.run_subprocess(command, timeout=300)
        
        # Save output
        (phase_dir / "claude-output.log").write_text(f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}")
        
        # Verify plan.json exists
        plan_file = phase_dir / "plan.json"
        if not plan_file.exists():
            self.log("ERROR: plan.json not created by Claude", "ERROR")
            return False
        
        self.log(f"✅ Plan created: {plan_file}")
        return exit_code == 0
    
    def run_phase_2_validation(self):
        """Phase 2: Cursor + Gemini validate plan in parallel"""
        self.log("=" * 60)
        self.log("🟠 PHASE 2: VALIDATION (Cursor + Gemini parallel)")
        self.log("=" * 60)
        
        phase_dir = self.phases_dir / "01-planning"  # They read from phase 1
        review_dir = self.phases_dir / "02-test-design"
        review_dir.mkdir(exist_ok=True)
        
        plan_file = phase_dir / "plan.json"
        if not plan_file.exists():
            self.log("ERROR: plan.json not found", "ERROR")
            return False
        
        plan = json.loads(plan_file.read_text())
        plan_str = json.dumps(plan, indent=2)
        
        # Prepare prompts
        cursor_prompt = f"""
You are the Code Reviewer and Architecture Validator.

Your task: Review the development plan below.

=== PLAN TO REVIEW ===
{plan_str}

=== YOUR TASK ===
Review this plan for:

1. **Logical Errors**: Any inconsistencies or gaps?
2. **Missing Edge Cases**: What scenarios are missing?
3. **Security Concerns**: Any security issues?
4. **Test Strategy**: Is testing strategy sound?
5. **Feasibility**: Can this be done in the estimated hours?

=== OUTPUT ===
Respond with JSON structure:
{{
  "overall_verdict": "approved|revision_required|blocked",
  "quality_score": 0-100,
  "critical_issues": [
    {{"severity": "critical|warning|info", "message": "..."}}
  ],
  "suggestions": ["..."],
  "approved_by_cursor": true/false
}}

Save to: {review_dir}/cursor-feedback.json
"""
        
        gemini_prompt = f"""
You are the Architecture Validator and Design Reviewer.

Your task: Validate the development plan below.

=== PLAN TO VALIDATE ===
{plan_str}

=== YOUR TASK ===
Validate this plan against best practices:

1. **Design Patterns**: Are correct patterns used?
2. **Scalability**: Will this scale?
3. **Architecture**: Does architecture make sense?
4. **Compliance**: Meets requirements?
5. **Technical Debt**: Will this introduce tech debt?

=== OUTPUT ===
Respond with JSON structure:
{{
  "overall_verdict": "approved|revision_required|blocked",
  "architecture_score": 0-100,
  "issues": [
    {{"severity": "critical|warning|info", "message": "..."}}
  ],
  "recommendations": ["..."],
  "approved_by_gemini": true/false
}}

Save to: {review_dir}/gemini-validation.json
"""
        
        # Run both in parallel
        self.log("Starting parallel validation (Cursor + Gemini)...")
        
        cursor_cmd = [
            "cursor-agent",
            "-p", cursor_prompt,
            "--rules", str(self.project_dir / ".cursor" / "rules")
        ]
        
        gemini_cmd = [
            "gemini",
            "-p", gemini_prompt,
            "-e", "validator-agent"
        ]
        
        # Execute in parallel
        cursor_proc = subprocess.Popen(
            cursor_cmd,
            cwd=self.project_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        gemini_proc = subprocess.Popen(
            gemini_cmd,
            cwd=self.project_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        self.log("Waiting for both agents to complete...")
        
        # Wait for both
        cursor_stdout, cursor_stderr = cursor_proc.communicate(timeout=300)
        gemini_stdout, gemini_stderr = gemini_proc.communicate(timeout=300)
        
        # Save outputs
        (review_dir / "cursor-output.log").write_text(f"STDOUT:\n{cursor_stdout}\n\nSTDERR:\n{cursor_stderr}")
        (review_dir / "gemini-output.log").write_text(f"STDOUT:\n{gemini_stdout}\n\nSTDERR:\n{gemini_stderr}")
        
        # Verify feedback files
        cursor_fb_file = review_dir / "cursor-feedback.json"
        gemini_fb_file = review_dir / "gemini-validation.json"
        
        cursor_ok = cursor_fb_file.exists()
        gemini_ok = gemini_fb_file.exists()
        
        if not cursor_ok:
            self.log("⚠️  Cursor feedback not created - proceeding anyway", "WARNING")
        if not gemini_ok:
            self.log("⚠️  Gemini validation not created - proceeding anyway", "WARNING")
        
        # Consolidate feedback
        self._consolidate_feedback(review_dir, cursor_ok, gemini_ok)
        
        self.log("✅ Validation phase complete")
        return cursor_ok or gemini_ok
    
    def _consolidate_feedback(self, review_dir: Path, cursor_ok: bool, gemini_ok: bool):
        """Merge feedback from both agents"""
        consolidated = {
            "cursor_status": "completed" if cursor_ok else "skipped",
            "gemini_status": "completed" if gemini_ok else "skipped",
            "critical_issues": [],
            "warnings": [],
            "next_action": "proceed_to_implementation"
        }
        
        # Read Cursor feedback
        if cursor_ok:
            cursor_fb = json.loads((review_dir / "cursor-feedback.json").read_text())
            consolidated["cursor_verdict"] = cursor_fb.get("overall_verdict")
            consolidated["cursor_score"] = cursor_fb.get("quality_score")
            if cursor_fb.get("overall_verdict") == "blocked":
                consolidated["next_action"] = "blocked_by_cursor"
                consolidated["critical_issues"].extend(cursor_fb.get("critical_issues", []))
        
        # Read Gemini feedback
        if gemini_ok:
            gemini_fb = json.loads((review_dir / "gemini-validation.json").read_text())
            consolidated["gemini_verdict"] = gemini_fb.get("overall_verdict")
            consolidated["gemini_score"] = gemini_fb.get("architecture_score")
            if gemini_fb.get("overall_verdict") == "blocked":
                consolidated["next_action"] = "blocked_by_gemini"
                consolidated["critical_issues"].extend(gemini_fb.get("issues", []))
        
        (review_dir / "consolidated-feedback.json").write_text(json.dumps(consolidated, indent=2))
        self.log(f"Feedback consolidated: {consolidated['next_action']}")
    
    def run_phase_3_implementation(self):
        """Phase 3: Claude Code implements based on refined plan"""
        self.log("=" * 60)
        self.log("🟢 PHASE 3: IMPLEMENTATION (Claude Code)")
        self.log("=" * 60)
        
        phase_dir = self.phases_dir / "03-implementation"
        phase_dir.mkdir(exist_ok=True)
        
        # Read feedback
        feedback_file = self.phases_dir / "02-test-design" / "consolidated-feedback.json"
        feedback = {}
        if feedback_file.exists():
            feedback = json.loads(feedback_file.read_text())
        
        # Read plan
        plan_file = self.phases_dir / "01-planning" / "plan.json"
        plan = json.loads(plan_file.read_text()) if plan_file.exists() else {}
        
        prompt = f"""
You are the Implementation Agent.

Your task: Implement the plan with tests.

=== PLAN ===
{json.dumps(plan, indent=2)}

=== FEEDBACK FROM REVIEWS ===
{json.dumps(feedback, indent=2)}

=== YOUR TASK ===

1. **Read Feedback**: Incorporate any suggestions or requirements
2. **Write Tests First (TDD)**:
   - Create test files for each task
   - Tests should verify behavior, not implementation
3. **Implement Features**: Write code to pass tests
4. **Run Tests Locally**: npm test (or appropriate command)
5. **Commit**: Use clear commit messages like "[t1] Task title"
6. **Document**: Write implementation-log.md

=== OUTPUT ===
Save results to: {phase_dir}/

1. implementation.md - Narrative of what was done
2. test-results.json - All tests results
3. implementation-log.md - Decisions and notes

Format test results as:
{{
  "total_tests": 42,
  "passed": 42,
  "failed": 0,
  "coverage": 86,
  "status": "ALL_PASSING",
  "timestamp": "2026-01-19T..."
}}

=== REQUIREMENTS ===
- No implementation without tests
- Commit after each task
- Document any deviations from plan
- Ensure 80%+ coverage
"""
        
        command = [
            "claude",
            "-p", prompt,
            "--append-system-prompt-file=" + str(self.project_dir / ".claude" / "system.md"),
            "--allowedTools", "Bash(*),Write,Edit",
            "--continue"  # Continue previous context if available
        ]
        
        exit_code, stdout, stderr = self.run_subprocess(command, timeout=600)
        
        # Save output
        (phase_dir / "claude-output.log").write_text(f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}")
        
        # Verify test results
        test_results_file = phase_dir / "test-results.json"
        if test_results_file.exists():
            test_results = json.loads(test_results_file.read_text())
            if test_results.get("status") == "ALL_PASSING":
                self.log(f"✅ Implementation complete: {test_results['passed']} tests passing")
                return True
        
        self.log("⚠️  Test results unclear - check logs", "WARNING")
        return exit_code == 0
    
    def run_phase_4_verification(self):
        """Phase 4: Cursor + Gemini final verification"""
        self.log("=" * 60)
        self.log("🟣 PHASE 4: VERIFICATION (Cursor + Gemini)")
        self.log("=" * 60)
        
        verify_dir = self.phases_dir / "04-verification"
        verify_dir.mkdir(exist_ok=True)
        
        # Read implementation results
        impl_dir = self.phases_dir / "03-implementation"
        test_results_file = impl_dir / "test-results.json"
        
        test_results = {}
        if test_results_file.exists():
            test_results = json.loads(test_results_file.read_text())
        
        cursor_prompt = f"""
You are the Code Quality Reviewer.

Your task: Final code quality review.

Test results so far:
{json.dumps(test_results, indent=2)}

Review the implementation in this project for:
1. Code quality and style
2. Design patterns and architecture
3. Security and performance
4. Maintainability and clarity

Verdict: Should this go to production?

Output JSON:
{{
  "verdict": "approved|revision_required|blocked",
  "code_quality_score": 0-100,
  "security_issues": [],
  "performance_concerns": [],
  "critical_findings": [],
  "approved_by_cursor": true/false
}}

Save to: {verify_dir}/cursor-review.json
"""
        
        gemini_prompt = f"""
You are the Architecture and Test Verifier.

Your task: Verify implementation completeness.

Test results:
{json.dumps(test_results, indent=2)}

Verify:
1. All tests are passing
2. Coverage is adequate (80%+)
3. Architecture matches the plan
4. No regressions introduced
5. Code follows best practices

Verdict: Ready for production?

Output JSON:
{{
  "verdict": "approved|revision_required|blocked",
  "tests_passing": true/false,
  "coverage_adequate": true/false,
  "architecture_valid": true/false,
  "regressions": [],
  "approved_by_gemini": true/false
}}

Save to: {verify_dir}/gemini-review.json
"""
        
        # Run both in parallel
        cursor_cmd = ["cursor-agent", "-p", cursor_prompt, "--rules", str(self.project_dir / ".cursor" / "rules")]
        gemini_cmd = ["gemini", "-p", gemini_prompt, "-e", "validator-agent"]
        
        self.log("Starting final verification (Cursor + Gemini)...")
        
        cursor_proc = subprocess.Popen(cursor_cmd, cwd=self.project_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        gemini_proc = subprocess.Popen(gemini_cmd, cwd=self.project_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        cursor_out, cursor_err = cursor_proc.communicate(timeout=300)
        gemini_out, gemini_err = gemini_proc.communicate(timeout=300)
        
        # Save outputs and check for approvals
        cursor_ok = (verify_dir / "cursor-review.json").exists()
        gemini_ok = (verify_dir / "gemini-review.json").exists()
        
        if cursor_ok and gemini_ok:
            cursor_review = json.loads((verify_dir / "cursor-review.json").read_text())
            gemini_review = json.loads((verify_dir / "gemini-review.json").read_text())
            
            if cursor_review.get("verdict") == "approved" and gemini_review.get("verdict") == "approved":
                self.log("✅ All verifications APPROVED - ready for merge")
                (verify_dir / "ready-to-merge.json").write_text(json.dumps({"status": "READY", "approved_by": ["cursor", "gemini"]}, indent=2))
                return True
        
        self.log("⚠️  Verification complete - check reviews", "WARNING")
        return cursor_ok and gemini_ok
    
    def run_phase_5_completion(self):
        """Phase 5: Complete workflow and plan next"""
        self.log("=" * 60)
        self.log("⚪ PHASE 5: COMPLETION")
        self.log("=" * 60)
        
        complete_dir = self.phases_dir / "05-completion"
        complete_dir.mkdir(exist_ok=True)
        
        # Create completion summary
        summary = {
            "status": "WORKFLOW_COMPLETE",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "phases_completed": [
                "01-planning",
                "02-test-design",
                "03-implementation",
                "04-verification",
                "05-completion"
            ],
            "next_steps": "Review PRODUCT.md for next feature goal"
        }
        
        (complete_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        
        self.log(json.dumps(summary, indent=2))
        self.log("✅ Workflow complete!")
        self.log("")
        self.log("Next: Update PRODUCT.md with next feature and re-run orchestrator")
        
        return True
    
    def run_workflow(self):
        """Execute complete 5-phase workflow"""
        state = self.load_state()
        state["status"] = "running"
        self.save_state(state)
        
        try:
            # Phase 1
            state["phase"] = "planning"
            state["phase_num"] = 1
            self.save_state(state)
            if not self.run_phase_1_planning():
                raise RuntimeError("Phase 1 planning failed")
            
            # Phase 2
            state["phase"] = "validation"
            state["phase_num"] = 2
            self.save_state(state)
            if not self.run_phase_2_validation():
                self.log("Phase 2 validation had issues but continuing", "WARNING")
            
            # Phase 3
            state["phase"] = "implementation"
            state["phase_num"] = 3
            self.save_state(state)
            if not self.run_phase_3_implementation():
                raise RuntimeError("Phase 3 implementation failed")
            
            # Phase 4
            state["phase"] = "verification"
            state["phase_num"] = 4
            self.save_state(state)
            if not self.run_phase_4_verification():
                self.log("Phase 4 verification had issues", "WARNING")
            
            # Phase 5
            state["phase"] = "completion"
            state["phase_num"] = 5
            self.save_state(state)
            self.run_phase_5_completion()
            
            state["status"] = "complete"
            self.save_state(state)
            
            self.log("🎉 ALL PHASES COMPLETE")
            
        except Exception as e:
            self.log(f"WORKFLOW FAILED: {str(e)}", "CRITICAL")
            state["status"] = "failed"
            state["active_blockers"].append(str(e))
            self.save_state(state)
            raise


def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Orchestrator")
    parser.add_argument("--start", action="store_true", help="Start workflow")
    parser.add_argument("--project-dir", default=".", help="Project directory")
    parser.add_argument("--status", action="store_true", help="Check workflow status")
    parser.add_argument("--reset", action="store_true", help="Reset workflow")
    
    args = parser.parse_args()
    
    orchestrator = MultiAgentOrchestrator(args.project_dir)
    
    if args.status:
        state = orchestrator.load_state()
        print(json.dumps(state, indent=2))
    elif args.reset:
        print("⚠️  Resetting workflow...")
        orchestrator.state_file.unlink(missing_ok=True)
        print("✅ Reset complete")
    elif args.start:
        orchestrator.run_workflow()
    else:
        print("Use --start, --status, or --reset")


if __name__ == "__main__":
    main()
```

---

## Part 2: Quick-Start Commands

**To use the orchestrator**:

```bash
# 1. Initialize project (one-time setup)
curl -fsSL https://your-host/init-multi-agent.sh | bash -s -- my-project
cd my-project

# 2. Update PRODUCT.md with your feature goal
nano PRODUCT.md

# 3. Start orchestrator
python .workflow/orchestrator.py --start

# 4. Monitor progress
python .workflow/orchestrator.py --status

# Watch state updates in real-time
watch 'python .workflow/orchestrator.py --status'
```

---

## Part 3: Manual CLI Invocations

If you prefer to run agents manually instead of orchestrator:

```bash
cd /path/to/project

# Phase 1: Claude Planning
claude -p "
Read PRODUCT.md and create implementation plan.
Save plan to .workflow/phases/01-planning/plan.json
" --append-system-prompt-file=.claude/system.md \
  --allowedTools "Bash(git*),Write,Edit"

# Phase 2a: Cursor review (background)
cursor-agent -p "Review plan at .workflow/phases/01-planning/plan.json
Save feedback to .workflow/phases/02-test-design/cursor-feedback.json" \
  --rules .cursor/rules &

# Phase 2b: Gemini validation (background)
gemini -p "Validate plan at .workflow/phases/01-planning/plan.json
Save validation to .workflow/phases/02-test-design/gemini-validation.json" \
  -e validator-agent &

# Wait for both to complete
wait

# Phase 3: Claude Implementation
claude -p "
Read plan and feedback.
Implement with TDD.
Save results to .workflow/phases/03-implementation/
" --append-system-prompt-file=.claude/system.md \
  --allowedTools "Bash(*),Write,Edit" \
  --continue

# Phase 4a: Cursor final review
cursor-agent -p "Final code review. Save to .workflow/phases/04-verification/cursor-review.json" --rules .cursor/rules &

# Phase 4b: Gemini final verification
gemini -p "Final verification. Save to .workflow/phases/04-verification/gemini-review.json" -e validator-agent &

wait

# Check if approved
cat .workflow/phases/04-verification/cursor-review.json
cat .workflow/phases/04-verification/gemini-review.json

# If approved, merge
git add -A && git commit -m "feat: Complete implementation cycle"
```

---

**This is your complete, production-ready implementation guide.**
Ready for a coding agent to expand, customize, and deploy!

