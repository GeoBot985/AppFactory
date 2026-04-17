import uuid
from pathlib import Path
from typing import List, Optional
from services.input_compiler.models import CompiledSpecIR
from .models import RoutingDecision, GoalSignature, MacroMatch, RoutingRule
from .signature import SignatureEngine
from .rules import RuleManager
from .matcher import RoutingMatcher
from .scorer import RoutingScorer
from .binder import RoutingBinder
from .audit import RoutingAuditor
from Demo10.macros.library import MacroLibraryManager
from Demo10.macros.models import WorkflowMacro

class RoutingEngine:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.rule_manager = RuleManager(workspace_root)
        self.matcher = RoutingMatcher(self.rule_manager)
        self.scorer = RoutingScorer()
        self.binder = RoutingBinder()
        self.auditor = RoutingAuditor(workspace_root)
        self.macro_library = MacroLibraryManager(workspace_root)

    def route_to_macros(self, ir: CompiledSpecIR) -> RoutingDecision:
        decision_id = f"route_{uuid.uuid4().hex[:8]}"

        # 1. Build signature
        sig = SignatureEngine.build_signature(ir)

        # 2. Load rules and macros
        rules = self.rule_manager.load_rules()
        self.auditor.record_rules_snapshot(rules)
        macros = self.macro_library.list_macros()

        # 3. Find matches
        matches = self.matcher.find_matches(sig, macros, rules)

        # 4. Score matches
        ranked_matches = self.scorer.score_matches(matches, sig, rules)

        reasons = []
        selected_macros = []
        fallback_used = True

        rule_map = {r.rule_id: r for r in rules}

        # 5. Rule Selection & Composition
        if ranked_matches:
            # First, try single macro match that covers ALL operations
            for match in ranked_matches:
                rule = rule_map.get(match.rule_id)
                if not self._covers_all(rule, sig):
                    continue

                macro = self.macro_library.get_macro(
                    self._get_macro_name(match.macro_id, macros),
                    match.version
                )
                if macro:
                    inputs = self.binder.bind_inputs(macro, ir)
                    if inputs is not None:
                        selected_macros = [match.macro_id]
                        fallback_used = False
                        reasons.append(f"matched_macro:{match.macro_id}")
                        reasons.extend(match.reasons)
                        break
                    else:
                        reasons.append(f"binding_failed:{match.macro_id}")

            # If no single macro, try composition of 2
            if fallback_used and len(ranked_matches) >= 2:
                for i in range(len(ranked_matches)):
                    for j in range(len(ranked_matches)):
                        if i == j: continue
                        m1 = ranked_matches[i]
                        m2 = ranked_matches[j]

                        # Composition must cover all operations
                        if not self._composition_covers_all(rule_map[m1.rule_id], rule_map[m2.rule_id], sig):
                            continue

                        comp_res = self._attempt_composition(m1, m2, ir, macros)
                        if comp_res:
                            selected_macros = [m1.macro_id, m2.macro_id]
                            fallback_used = False
                            reasons.append("composition_successful")
                            reasons.append(f"comp1:{m1.macro_id}")
                            reasons.append(f"comp2:{m2.macro_id}")
                            break
                    if not fallback_used: break

            if fallback_used and not reasons:
                reasons.append("matches_found_but_none_covered_all_operations")
        else:
            reasons.append("no_matching_rules")

        decision = RoutingDecision(
            decision_id=decision_id,
            goal_signature_id=sig.signature_id,
            selected_macros=selected_macros,
            fallback_used=fallback_used,
            reasons=reasons
        )

        # 6. Audit
        self.auditor.record_decision(decision, ranked_matches, rules)

        return decision

    def _covers_all(self, rule: RoutingRule, sig: GoalSignature) -> bool:
        pattern_ops = rule.goal_pattern.get("operation_types", [])
        if not pattern_ops: return False
        return sorted(pattern_ops) == sorted(sig.operation_types)

    def _composition_covers_all(self, r1: RoutingRule, r2: RoutingRule, sig: GoalSignature) -> bool:
        ops1 = r1.goal_pattern.get("operation_types", [])
        ops2 = r2.goal_pattern.get("operation_types", [])
        combined = sorted(ops1 + ops2)
        return combined == sorted(sig.operation_types)

    def _attempt_composition(self, m1_match, m2_match, ir: CompiledSpecIR, macros: List) -> bool:
        macro1 = self.macro_library.get_macro(self._get_macro_name(m1_match.macro_id, macros), m1_match.version)
        macro2 = self.macro_library.get_macro(self._get_macro_name(m2_match.macro_id, macros), m2_match.version)

        if not macro1 or not macro2: return False

        # Conflict Check: Targets must not overlap
        # Simplistic v1: check produced_outputs
        targets1 = set(macro1.output_contract.produced_outputs)
        targets2 = set(macro2.output_contract.produced_outputs)
        if targets1.intersection(targets2):
            return False

        # Binding Check
        # We need to see if both can be bound.
        # In a real composition, macro2 might depend on macro1 outputs.
        # Spec says: "output of macro A must satisfy input contract of macro B (explicitly)"

        # For v1, we just check if both bind to IR independently and don't conflict
        bind1 = self.binder.bind_inputs(macro1, ir)
        bind2 = self.binder.bind_inputs(macro2, ir)

        if bind1 is None or bind2 is None:
            return False

        return True

    def get_macro_by_id(self, macro_id: str) -> Optional[WorkflowMacro]:
        name = ""
        version = "v1"
        if ":" in macro_id:
            name, version = macro_id.split(":", 1)
        else:
            name = macro_id
        return self.macro_library.get_macro(name, version)

    def _get_macro_name(self, macro_id: str, macros: List) -> str:
        for m in macros:
            if m.macro_id == macro_id:
                return m.name
        return ""
