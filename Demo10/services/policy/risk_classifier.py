import fnmatch
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from services.task_service import Task, TaskType
from .models import RiskClass, RiskAssessment, PolicyConfig

class RiskClassifier:
    def __init__(self, policy_config: PolicyConfig):
        self.policy_config = policy_config

    def classify(self, tasks: List[Task], spec_data: Optional[Dict[str, Any]] = None) -> RiskAssessment:
        task_risks = []
        for task in tasks:
            task_risks.append(self.classify_task(task))

        # Overall spec risk is the maximum of task risks
        overall_risk = RiskClass.R0_LOW
        for tr in task_risks:
            tr_class = RiskClass(tr["risk"])
            if tr_class > overall_risk:
                overall_risk = tr_class

        # Spec risk hints comparison (Requirement 23)
        spec_risk = overall_risk
        if spec_data and "risk_hints" in spec_data:
            hinted_risk_str = spec_data["risk_hints"].get("expected_risk")
            if hinted_risk_str:
                try:
                    hinted_risk = RiskClass(hinted_risk_str)
                    if hinted_risk > spec_risk:
                        spec_risk = hinted_risk
                except ValueError:
                    pass

        # Estimate promotion risk (will be re-evaluated before actual promotion)
        promotion_risk = self._estimate_promotion_risk(tasks, task_risks)

        return RiskAssessment(
            spec_risk=spec_risk.value,
            task_risks=task_risks,
            promotion_risk_estimate=promotion_risk.value,
            overall_risk=overall_risk.value
        )

    def classify_task(self, task: Task) -> Dict[str, Any]:
        risk = RiskClass.R0_LOW
        reasons = []

        # 1. Task-type based classification (Requirement 7)
        type_risk, type_reasons = self._classify_by_type(task)
        if type_risk > risk:
            risk = type_risk
        reasons.extend(type_reasons)

        # 2. Path-based escalation (Requirement 7)
        path_risk, path_reasons = self._classify_by_path(task.target)
        if path_risk > risk:
            risk = path_risk
        reasons.extend(path_reasons)

        # 3. Command escalation
        if task.type == TaskType.RUN:
             cmd_risk, cmd_reasons = self._classify_command(task)
             if cmd_risk > risk:
                 risk = cmd_risk
             reasons.extend(cmd_reasons)

        return {
            "task_id": task.id,
            "risk": risk.value,
            "reasons": reasons
        }

    def _classify_by_type(self, task: Task) -> tuple[RiskClass, List[str]]:
        if task.type == TaskType.CREATE:
            return RiskClass.R0_LOW, ["CREATE task"]

        if task.type == TaskType.MODIFY:
            # Check for delete_block (Requirement 7)
            if task.constraints:
                try:
                    data = json.loads(task.constraints)
                    if data.get("operation") == "delete_block":
                        return RiskClass.R2_HIGH, ["MODIFY with delete_block"]
                except:
                    pass
            return RiskClass.R1_MODERATE, ["MODIFY task"]

        if task.type == TaskType.DELETE:
            return RiskClass.R2_HIGH, ["DELETE task"]

        if task.type == TaskType.RUN:
            return RiskClass.R1_MODERATE, ["RUN task"]

        if task.type == TaskType.VALIDATE:
            return RiskClass.R0_LOW, ["VALIDATE task"]

        return RiskClass.R0_LOW, [f"Unknown task type: {task.type}"]

    def _classify_by_path(self, target: str) -> tuple[RiskClass, List[str]]:
        risk = RiskClass.R0_LOW
        reasons = []

        critical_patterns = self.policy_config.protected_paths.get("critical", [])
        high_risk_patterns = self.policy_config.protected_paths.get("high_risk", [])

        for pattern in critical_patterns:
            if fnmatch.fnmatch(target, pattern) or target.startswith(pattern.replace("/**", "")):
                return RiskClass.R3_CRITICAL, [f"Touches critical path: {target} (matches {pattern})"]

        for pattern in high_risk_patterns:
            if fnmatch.fnmatch(target, pattern) or target.startswith(pattern.replace("/**", "")):
                risk = RiskClass.R2_HIGH
                reasons = [f"Touches high-risk path: {target} (matches {pattern})"]
                break

        return risk, reasons

    def _classify_command(self, task: Task) -> tuple[RiskClass, List[str]]:
        risk = RiskClass.R1_MODERATE
        reasons = []

        # Check for denied executables (Requirement 15)
        denied = self.policy_config.command_rules.get("denied_executables", [])
        for d in denied:
            if d in task.target:
                return RiskClass.R3_CRITICAL, [f"Contains denied executable: {d}"]

        # Shell strings escalation (Requirement 16)
        # Assuming if task.target contains spaces or special chars, it might be a shell string
        # In this system, 'target' for RUN task is the command itself
        if " " in task.target or ";" in task.target or "|" in task.target:
             if self.policy_config.command_rules.get("shell_string_commands_require_approval"):
                 risk = RiskClass.R2_HIGH
                 reasons.append("Shell string command detected")

        # Runtime override escalation
        if task.constraints:
            try:
                data = json.loads(task.constraints)
                if "runtime_override" in data:
                    timeout = data["runtime_override"].get("timeout_seconds", 0)
                    threshold = self.policy_config.command_rules.get("runtime_override_timeout_above_seconds_requires_approval", 300)
                    if timeout > threshold:
                        risk = RiskClass.R2_HIGH
                        reasons.append(f"Runtime timeout override ({timeout}s) above threshold ({threshold}s)")
            except:
                pass

        return risk, reasons

    def _estimate_promotion_risk(self, tasks: List[Task], task_risks: List[Dict[str, Any]]) -> RiskClass:
        # Initial estimate based on tasks
        risk = RiskClass.R0_LOW

        # If any task is R2 or above, promotion is likely R2
        for tr in task_risks:
            tr_class = RiskClass(tr["risk"])
            if tr_class >= RiskClass.R2_HIGH:
                risk = RiskClass.R2_HIGH
                break

        # If many files are touched (Requirement 7)
        unique_files = {t.target for t in tasks if t.type != TaskType.RUN}
        if len(unique_files) > self.policy_config.execution_rules.get("max_auto_changed_files", 5):
            if RiskClass.R2_HIGH > risk:
                risk = RiskClass.R2_HIGH

        return risk

    def classify_actual_promotion(self, facts: Dict[str, Any]) -> tuple[RiskClass, List[str]]:
        # Requirement 13: Promotion policy must evaluate actual observed change set
        risk = RiskClass.R0_LOW
        reasons = []

        changed_count = facts.get("changed_file_count", 0)
        max_auto = self.policy_config.execution_rules.get("max_auto_changed_files", 5)
        if changed_count > max_auto:
            risk = RiskClass.R2_HIGH
            reasons.append(f"Changed file count ({changed_count}) exceeds threshold ({max_auto})")

        if facts.get("contains_deletion"):
            if RiskClass.R2_HIGH > risk:
                risk = RiskClass.R2_HIGH
            reasons.append("Contains file or block deletion")

        if facts.get("touches_protected_path"):
            # Already escalated in classify_task, but we re-check here on actual promoted paths
            if RiskClass.R2_HIGH > risk:
                 risk = RiskClass.R2_HIGH
            reasons.append("Touches protected or critical path")

        if facts.get("touches_critical_path"):
            risk = RiskClass.R3_CRITICAL
            reasons.append("Touches critical path")

        # Verification result (Requirement 7)
        status = facts.get("final_status")
        if status == "COMPLETED_WITH_WARNINGS":
            if RiskClass.R2_HIGH > risk:
                risk = RiskClass.R2_HIGH
            reasons.append("Promotion requested with warnings")

        return risk, reasons
