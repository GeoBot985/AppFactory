from typing import List
from .models import GoalSignature, RoutingRule, MacroMatch
from Demo10.macros.models import WorkflowMacro

class RoutingScorer:
    @staticmethod
    def score_matches(matches: List[MacroMatch], sig: GoalSignature, rules: List[RoutingRule]) -> List[MacroMatch]:
        rule_map = {r.rule_id: r for r in rules}

        for match in matches:
            rule = rule_map.get(match.rule_id)
            if not rule: continue

            score = 0

            # +100 if exact operation_types match
            pattern_ops = rule.goal_pattern.get("operation_types", [])
            if pattern_ops and sorted(pattern_ops) == sorted(sig.operation_types):
                score += 100
                match.reasons.append("exact_operation_match")

            # +50 if target pattern matches
            if "target_pattern" in rule.goal_pattern:
                score += 50
                match.reasons.append("target_pattern_match")

            # +20 if constraints match
            if "required_constraints" in rule.goal_pattern:
                score += 20
                match.reasons.append("constraints_match")

            # +10 if higher version (within active set)
            # (In this context, we just add it if it's > v1 for now)
            try:
                v_num = int(match.version.lstrip('v'))
                if v_num > 1:
                    score += 10
                    match.reasons.append("recent_version")
            except:
                pass

            # -100 if any soft constraint mismatch (placeholder for v1)

            match.score = score

        # Tie-breakers: higher priority, higher score, higher version, lexical macro_id
        # We'll sort by (priority, score, version_num, macro_id)

        def get_v_num(v):
            try: return int(v.lstrip('v'))
            except: return 0

        # Sort criteria (priority DESC, score DESC, version DESC, macro_id ASC)
        matches.sort(key=lambda m: (
            -rule_map[m.rule_id].priority,
            -m.score,
            -get_v_num(m.version),
            m.macro_id
        ))

        return matches
