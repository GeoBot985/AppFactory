import unittest
import os
import shutil
from pathlib import Path
from Demo10.routing.engine import RoutingEngine
from Demo10.routing.models import RoutingRule
from Demo10.routing.signature import SignatureEngine
from Demo10.macros.models import WorkflowMacro, MacroInputContract, MacroOutputContract, MacroSafetyContract, MacroRollbackContract
from Demo10.macros.library import MacroLibraryManager
from services.input_compiler.models import CompiledSpecIR, OperationIR, OperationType, CompileStatus

class TestRouting(unittest.TestCase):
    def setUp(self):
        self.workspace = Path("test_routing_ws")
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
        self.workspace.mkdir()

        self.engine = RoutingEngine(self.workspace)
        self.macro_mgr = MacroLibraryManager(self.workspace)

        # Setup a verified macro
        self.macro_v1 = WorkflowMacro(
            macro_id="write_spec_fragment:v1",
            name="write_spec_fragment",
            version="v1",
            source_fragment_id="frag1",
            description="Write a spec fragment",
            step_template=[{"step_type": "write_file", "target": "{{target}}", "inputs": {"content": "test"}}],
            input_contract=MacroInputContract(required_inputs=["target", "instruction"]),
            output_contract=MacroOutputContract(produced_outputs=["target"]),
            dependency_shape={},
            safety_contract=MacroSafetyContract(),
            rollback_contract=MacroRollbackContract(),
            verification_status="verified"
        )
        self.macro_mgr.add_macro_version(self.macro_v1)

        # Setup a second version
        self.macro_v2 = WorkflowMacro(
            macro_id="write_spec_fragment:v2",
            name="write_spec_fragment",
            version="v2",
            source_fragment_id="frag1",
            description="Write a spec fragment v2",
            step_template=[{"step_type": "write_file", "target": "{{target}}", "inputs": {"content": "test v2"}}],
            input_contract=MacroInputContract(required_inputs=["target", "instruction"]),
            output_contract=MacroOutputContract(produced_outputs=["target"]),
            dependency_shape={},
            safety_contract=MacroSafetyContract(),
            rollback_contract=MacroRollbackContract(),
            verification_status="verified"
        )
        self.macro_mgr.add_macro_version(self.macro_v2)

    def tearDown(self):
        if self.workspace.exists():
            shutil.rmtree(self.workspace)

    def test_exact_match_routing(self):
        # 1. Setup rule
        rule = RoutingRule(
            rule_id="rule1",
            goal_pattern={"operation_types": ["write_spec"]},
            macro_name="write_spec_fragment",
            priority=100
        )
        self.engine.rule_manager.save_rules([rule])

        # 2. Setup IR
        ir = CompiledSpecIR(
            request_id="req1",
            title="Write spec",
            objective="I want to write a spec",
            operations=[OperationIR(op_type=OperationType.WRITE_SPEC, target="spec.md", instruction="write it")],
            compile_status=CompileStatus.COMPILED_CLEAN
        )

        # 3. Route
        decision = self.engine.route_to_macros(ir)

        self.assertFalse(decision.fallback_used)
        self.assertEqual(decision.selected_macros, ["write_spec_fragment:v2"]) # v2 chosen because it's higher version
        self.assertIn("matched_macro:write_spec_fragment:v2", decision.reasons)

    def test_version_selection(self):
        # Already partially covered by test_exact_match_routing (v2 was chosen)
        # Let's try with min_version
        rule = RoutingRule(
            rule_id="rule1",
            goal_pattern={"operation_types": ["write_spec"]},
            macro_name="write_spec_fragment",
            min_version="v2"
        )
        self.engine.rule_manager.save_rules([rule])

        ir = CompiledSpecIR(
            request_id="req1",
            title="Write spec",
            objective="I want to write a spec",
            operations=[OperationIR(op_type=OperationType.WRITE_SPEC, target="spec.md", instruction="write it")],
            compile_status=CompileStatus.COMPILED_CLEAN
        )

        decision = self.engine.route_to_macros(ir)
        self.assertEqual(decision.selected_macros, ["write_spec_fragment:v2"])

    def test_binding_failure(self):
        # Setup macro that requires 'unprovided_field'
        macro_fail = WorkflowMacro(
            macro_id="fail_macro:v1",
            name="fail_macro",
            version="v1",
            source_fragment_id="frag_f",
            description="Failing macro",
            step_template=[],
            input_contract=MacroInputContract(required_inputs=["unprovided_field"]),
            output_contract=MacroOutputContract(produced_outputs=[]),
            dependency_shape={},
            safety_contract=MacroSafetyContract(),
            rollback_contract=MacroRollbackContract(),
            verification_status="verified"
        )
        self.macro_mgr.add_macro_version(macro_fail)

        rule = RoutingRule(
            rule_id="rule_f",
            goal_pattern={"operation_types": ["run_command"]},
            macro_name="fail_macro"
        )
        self.engine.rule_manager.save_rules([rule])

        ir = CompiledSpecIR(
            request_id="req2",
            title="Run cmd",
            objective="run echo",
            operations=[OperationIR(op_type=OperationType.RUN_COMMAND, target=None, instruction="echo hi")],
            compile_status=CompileStatus.COMPILED_CLEAN
        )

        decision = self.engine.route_to_macros(ir)
        self.assertTrue(decision.fallback_used)
        self.assertIn("binding_failed:fail_macro:v1", decision.reasons)

    def test_fallback_no_match(self):
        self.engine.rule_manager.save_rules([])

        ir = CompiledSpecIR(
            request_id="req3",
            title="No match",
            objective="nothing",
            operations=[OperationIR(op_type=OperationType.ANALYZE_CODEBASE, target=None, instruction="analyze")],
            compile_status=CompileStatus.COMPILED_CLEAN
        )

        decision = self.engine.route_to_macros(ir)
        self.assertTrue(decision.fallback_used)
        self.assertIn("no_matching_rules", decision.reasons)

    def test_audit_persistence(self):
        rule = RoutingRule(
            rule_id="rule1",
            goal_pattern={"operation_types": ["write_spec"]},
            macro_name="write_spec_fragment"
        )
        self.engine.rule_manager.save_rules([rule])

        ir = CompiledSpecIR(
            request_id="req4",
            title="Audit test",
            objective="testing audit",
            operations=[OperationIR(op_type=OperationType.WRITE_SPEC, target="a.md", instruction="write")],
            compile_status=CompileStatus.COMPILED_CLEAN
        )

        decision = self.engine.route_to_macros(ir)

        decision_file = self.workspace / "runtime_data" / "routing" / "decisions" / f"{decision.decision_id}.json"
        self.assertTrue(decision_file.exists())

        matches_file = self.workspace / "runtime_data" / "routing" / "matches" / f"{decision.decision_id}.json"
        self.assertTrue(matches_file.exists())

    def test_composition(self):
        # Setup two macros covering different operations
        macro_a = WorkflowMacro(
            macro_id="macro_a:v1",
            name="macro_a", version="v1", source_fragment_id="f1", description="A",
            step_template=[],
            input_contract=MacroInputContract(required_inputs=["instruction"]),
            output_contract=MacroOutputContract(produced_outputs=["a.txt"]),
            dependency_shape={}, safety_contract=MacroSafetyContract(), rollback_contract=MacroRollbackContract(),
            verification_status="verified"
        )
        macro_b = WorkflowMacro(
            macro_id="macro_b:v1",
            name="macro_b", version="v1", source_fragment_id="f2", description="B",
            step_template=[],
            input_contract=MacroInputContract(required_inputs=["instruction"]),
            output_contract=MacroOutputContract(produced_outputs=["b.txt"]),
            dependency_shape={}, safety_contract=MacroSafetyContract(), rollback_contract=MacroRollbackContract(),
            verification_status="verified"
        )
        self.macro_mgr.add_macro_version(macro_a)
        self.macro_mgr.add_macro_version(macro_b)

        # Rules that don't cover full IR alone
        rule_a = RoutingRule(rule_id="r_a", goal_pattern={"operation_types": ["write_spec"]}, macro_name="macro_a")
        rule_b = RoutingRule(rule_id="r_b", goal_pattern={"operation_types": ["modify_file"]}, macro_name="macro_b")
        self.engine.rule_manager.save_rules([rule_a, rule_b])

        ir = CompiledSpecIR(
            request_id="req_comp", title="Comp", objective="Comp",
            operations=[
                OperationIR(op_type=OperationType.WRITE_SPEC, target="a", instruction="write"),
                OperationIR(op_type=OperationType.MODIFY_FILE, target="b", instruction="modify")
            ],
            compile_status=CompileStatus.COMPILED_CLEAN
        )

        decision = self.engine.route_to_macros(ir)
        self.assertFalse(decision.fallback_used)
        self.assertEqual(len(decision.selected_macros), 2)
        self.assertIn("macro_a:v1", decision.selected_macros)
        self.assertIn("macro_b:v1", decision.selected_macros)

    def test_conflict_rejection(self):
        macro_a = WorkflowMacro(
            macro_id="macro_a:v1",
            name="macro_a", version="v1", source_fragment_id="f1", description="A",
            step_template=[],
            input_contract=MacroInputContract(required_inputs=["instruction"]),
            output_contract=MacroOutputContract(produced_outputs=["same.txt"]),
            dependency_shape={}, safety_contract=MacroSafetyContract(), rollback_contract=MacroRollbackContract(),
            verification_status="verified"
        )
        macro_b = WorkflowMacro(
            macro_id="macro_b:v1",
            name="macro_b", version="v1", source_fragment_id="f2", description="B",
            step_template=[],
            input_contract=MacroInputContract(required_inputs=["instruction"]),
            output_contract=MacroOutputContract(produced_outputs=["same.txt"]),
            dependency_shape={}, safety_contract=MacroSafetyContract(), rollback_contract=MacroRollbackContract(),
            verification_status="verified"
        )
        # Make them fail single
        macro_a.input_contract.required_inputs.append("missing")
        macro_b.input_contract.required_inputs.append("missing")

        self.macro_mgr.add_macro_version(macro_a)
        self.macro_mgr.add_macro_version(macro_b)

        # Now try to compose them (they both match rule)
        rule_a = RoutingRule(rule_id="r_a", goal_pattern={"operation_types": ["write_spec"]}, macro_name="macro_a")
        rule_b = RoutingRule(rule_id="r_b", goal_pattern={"operation_types": ["write_spec"]}, macro_name="macro_b")
        self.engine.rule_manager.save_rules([rule_a, rule_b])

        ir = CompiledSpecIR(
            request_id="req_conf", title="Conf", objective="Conf",
            operations=[
                OperationIR(op_type=OperationType.WRITE_SPEC, target="a", instruction="i"),
                OperationIR(op_type=OperationType.MODIFY_FILE, target="b", instruction="j")
            ],
            compile_status=CompileStatus.COMPILED_CLEAN
        )

        decision = self.engine.route_to_macros(ir)
        self.assertTrue(decision.fallback_used) # Should fail because of target conflict in composition

    def test_governance_block(self):
        # Setup macro that is NOT verified
        macro_unverified = WorkflowMacro(
            macro_id="unv:v1",
            name="unv", version="v1", source_fragment_id="f", description="U",
            step_template=[],
            input_contract=MacroInputContract(required_inputs=["instruction"]),
            output_contract=MacroOutputContract(produced_outputs=[]),
            dependency_shape={}, safety_contract=MacroSafetyContract(), rollback_contract=MacroRollbackContract(),
            verification_status="pending"
        )
        self.macro_mgr.add_macro_version(macro_unverified)

        rule = RoutingRule(rule_id="r", goal_pattern={"operation_types": ["write_spec"]}, macro_name="unv")
        self.engine.rule_manager.save_rules([rule])

        ir = CompiledSpecIR(
            request_id="req_unv", title="U", objective="U",
            operations=[OperationIR(op_type=OperationType.WRITE_SPEC, target="t", instruction="i")],
            compile_status=CompileStatus.COMPILED_CLEAN
        )

        decision = self.engine.route_to_macros(ir)
        self.assertTrue(decision.fallback_used)
        self.assertIn("no_matching_rules", decision.reasons) # Because it was filtered out by matcher

if __name__ == "__main__":
    unittest.main()
