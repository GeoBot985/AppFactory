import pytest
from unittest.mock import MagicMock
from pathlib import Path
from services.input_compiler.compiler import NaturalInputCompiler
from services.input_compiler.models import CompileStatus, OperationType, CompiledSpecIR, OperationIR
from services.context.context_snapshot import ContextSnapshot

@pytest.fixture
def mock_ollama():
    return MagicMock()

@pytest.fixture
def compiler(mock_ollama, tmp_path):
    # Ensure runtime_data/session directory exists
    (tmp_path / "Demo10/runtime_data/session").mkdir(parents=True, exist_ok=True)
    return NaturalInputCompiler(mock_ollama, workspace_root=tmp_path, persistence_dir=tmp_path / "compiler_runs")

def test_rule_1_missing_filename(compiler, mock_ollama, tmp_path):
    mock_ollama.run_prompt.return_value = """
    {
      "title": "Create a spec for Demo10",
      "objective": "Objective",
      "operations": [
        {
          "op_type": "create_file",
          "target": "",
          "instruction": "create a spec for Demo10"
        }
      ]
    }
    """
    ir, issues = compiler.compile("m", "create a spec for Demo10")
    # Rule 1 should have filled the target
    assert ir.operations[0].target == "create_a_spec_for_demo10.py"
    assert "RULE_001_AUTO_TARGET_FILENAME" in ir.defaults_applied
    assert ir.compile_status == CompileStatus.COMPILED_WITH_WARNINGS

def test_rule_3_next_spec_resolution(compiler, mock_ollama, tmp_path):
    # Create some existing spec files
    (tmp_path / "spec_001.md").write_text("...")
    (tmp_path / "spec_002.md").write_text("...")

    mock_ollama.run_prompt.return_value = """
    {
      "title": "Next spec",
      "objective": "Objective",
      "operations": [
        {
          "op_type": "write_spec",
          "target": "next",
          "instruction": "generate next spec"
        }
      ]
    }
    """
    ir, issues = compiler.compile("m", "generate next spec")
    assert ir.operations[0].target == "spec_003.md"
    assert "RULE_003_NEXT_SPEC_RESOLUTION" in ir.defaults_applied

def test_rule_4_single_candidate(compiler, mock_ollama, tmp_path):
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src/pipeline.py").write_text("...")

    mock_ollama.run_prompt.return_value = """
    {
      "title": "Update pipeline",
      "objective": "Objective",
      "operations": [
        {
          "op_type": "modify_file",
          "target": "pipeline",
          "instruction": "update pipeline"
        }
      ]
    }
    """
    ir, issues = compiler.compile("m", "update pipeline")
    assert ir.operations[0].target == "src/pipeline.py"
    assert "RULE_004_SINGLE_CANDIDATE_DISAMBIGUATION" in ir.defaults_applied

def test_rule_5_recent_file(compiler, mock_ollama, tmp_path):
    # Setup session with one recent file
    from services.session_memory.working_set_manager import WorkingSetManager
    ws_manager = WorkingSetManager()
    session = compiler.session_manager.load_or_create_session(str(tmp_path))
    ws_manager.update_primary_files(session.working_set, ["main.py"], "test", "run_1")
    compiler.session_manager.save_session()

    mock_ollama.run_prompt.return_value = """
    {
      "title": "Modify the file",
      "objective": "Objective",
      "operations": [
        {
          "op_type": "modify_file",
          "target": "",
          "instruction": "modify the file"
        }
      ]
    }
    """
    ir, issues = compiler.compile("m", "modify the file")
    assert ir.operations[0].target == "main.py"
    assert "RULE_005_RECENT_FILE_INFERENCE" in ir.defaults_applied

def test_destructive_op_safety(compiler, mock_ollama, tmp_path):
    # Destructive op without target should remain blocked if multiple candidates exist
    (tmp_path / "file1.py").write_text("...")
    (tmp_path / "file2.py").write_text("...")

    mock_ollama.run_prompt.return_value = """
    {
      "title": "Delete something",
      "objective": "Objective",
      "operations": [
        {
          "op_type": "modify_file",
          "target": "",
          "instruction": "delete the file"
        }
      ]
    }
    """
    ir, issues = compiler.compile("m", "delete the file")
    # It might NOT find candidates if we haven't implemented a "find candidates for delete" rule that is NOT Rule 4
    # Rule 4 applies if target is NOT in context.files but matches ONE.
    # Here target is empty, so Rule 4 doesn't apply to op.target if it's empty.

    # Actually my Rule 4: if op.target and op.target not in context.files: ...
    # If op.target is empty, Rule 4 doesn't fire.
    # Rule 5 fires if exactly ONE recent file.

    assert ir.compile_status == CompileStatus.BLOCKED
    assert any(issue.code == "MISSING_REQUIRED_TARGET" for issue in issues)
