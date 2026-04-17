import sys
from pathlib import Path

# Add Demo10/services to path
sys.path.append(str(Path(__file__).parent.parent))

from services.input_compiler.compiler import NaturalInputCompiler
from services.input_compiler.models import CompiledSpecIR, OperationType, OperationIR, CompileStatus
from services.input_compiler.issues import (
    CompileIssue, AMBIGUOUS_TARGET_FILE, MISSING_REQUIRED_TARGET, CONFLICTING_ACTIONS
)
from services.input_compiler.repair_models import RepairAction

class MockOllamaService:
    def run_prompt(self, model, prompt):
        return "{}"

def test_ambiguous_target_repair():
    print("Testing AMBIGUOUS_TARGET_FILE repair...")
    compiler = NaturalInputCompiler(MockOllamaService())

    # Create IR with ambiguous target issue
    ir = CompiledSpecIR(
        request_id="test_req",
        title="Test",
        objective="Test Ambiguity",
        operations=[
            OperationIR(op_type=OperationType.MODIFY_FILE, target=None, instruction="update the file")
        ]
    )

    issue = CompileIssue(
        severity="error",
        code=AMBIGUOUS_TARGET_FILE,
        message="Multiple files match 'the file': pipeline.py, graph.py",
        field="operations[0].target",
        repairable=True,
        repair_type="select_option"
    )

    repairs = compiler.generate_repairs([issue])
    assert len(repairs) > 0
    repair = repairs[0]
    assert repair.action_type == "select_from_candidates"
    assert "pipeline.py" in repair.candidates

    # Apply repair
    updated_ir = compiler.apply_repairs(ir, [RepairAction(
        action_id=repair.action_id,
        issue_code=repair.issue_code,
        action_type=repair.action_type,
        target_field=repair.target_field,
        value="pipeline.py"
    )])

    assert updated_ir.operations[0].target == "pipeline.py"
    print("SUCCESS: Ambiguous target repaired.")

def test_missing_target_repair():
    print("Testing MISSING_REQUIRED_TARGET repair...")
    compiler = NaturalInputCompiler(MockOllamaService())

    ir = CompiledSpecIR(
        request_id="test_req_missing",
        title="Test",
        objective="Test Missing",
        operations=[
            OperationIR(op_type=OperationType.CREATE_FILE, target="", instruction="create a file")
        ]
    )

    issue = CompileIssue(
        severity="error",
        code=MISSING_REQUIRED_TARGET,
        message="Create file requires a target",
        field="operations[0].target",
        repairable=True,
        repair_type="provide_value"
    )

    repairs = compiler.generate_repairs([issue])
    assert len(repairs) > 0
    repair = repairs[0]
    assert repair.action_type == "add_missing_field"

    # Apply repair
    updated_ir = compiler.apply_repairs(ir, [RepairAction(
        action_id=repair.action_id,
        issue_code=repair.issue_code,
        action_type=repair.action_type,
        target_field=repair.target_field,
        value="new_module.py"
    )])

    assert updated_ir.operations[0].target == "new_module.py"
    print("SUCCESS: Missing target repaired.")

def test_conflict_repair():
    print("Testing CONFLICTING_ACTIONS repair...")
    compiler = NaturalInputCompiler(MockOllamaService())

    ir = CompiledSpecIR(
        request_id="test_req_conflict",
        title="Test",
        objective="Test Conflict",
        operations=[
            OperationIR(op_type=OperationType.MODIFY_FILE, target="app.py", instruction="keep it"),
            OperationIR(op_type=OperationType.MODIFY_FILE, target="app.py", instruction="delete it")
        ]
    )

    issue = CompileIssue(
        severity="error",
        code=CONFLICTING_ACTIONS,
        message="Conflict for app.py",
        field="operations[1]",
        repairable=True,
        repair_type="remove_conflict"
    )

    repairs = compiler.generate_repairs([issue])
    assert len(repairs) > 0
    repair = repairs[0]
    assert repair.action_type == "remove_operation"

    # Apply repair (remove operations[1])
    updated_ir = compiler.apply_repairs(ir, [RepairAction(
        action_id=repair.action_id,
        issue_code=repair.issue_code,
        action_type=repair.action_type,
        target_field="operations[1]"
    )])

    assert len(updated_ir.operations) == 1
    assert updated_ir.operations[0].instruction == "keep it"
    print("SUCCESS: Conflict repaired by removal.")

if __name__ == "__main__":
    test_ambiguous_target_repair()
    test_missing_target_repair()
    test_conflict_repair()
    print("\nAll repair loop tests passed.")
