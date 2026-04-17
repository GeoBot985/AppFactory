import pytest
from unittest.mock import MagicMock
from pathlib import Path
from services.input_compiler.compiler import NaturalInputCompiler
from services.input_compiler.models import CompileStatus, OperationType
from services.input_compiler.issues import NO_SUPPORTED_OPERATION, MISSING_REQUIRED_TARGET, CONFLICTING_ACTIONS

@pytest.fixture
def mock_ollama():
    return MagicMock()

@pytest.fixture
def compiler(mock_ollama, tmp_path):
    return NaturalInputCompiler(mock_ollama, workspace_root=tmp_path, persistence_dir=tmp_path)

def test_clean_compile(compiler, mock_ollama):
    mock_ollama.run_prompt.return_value = """
    {
      "title": "Generate spec 041",
      "objective": "Generate spec 041 for Demo10 and save it as spec_041.md",
      "operations": [
        {
          "op_type": "write_spec",
          "target": "spec_041.md",
          "instruction": "Generate the spec content"
        }
      ]
    }
    """
    ir, issues = compiler.compile("m", "Generate spec 041 for Demo10 and save it as spec_041.md")
    assert ir.compile_status == CompileStatus.COMPILED_CLEAN
    assert len(ir.operations) == 1
    assert ir.operations[0].op_type == OperationType.WRITE_SPEC

def test_blocked_missing_operation(compiler, mock_ollama):
    mock_ollama.run_prompt.return_value = """
    {
      "title": "Better Demo10",
      "objective": "Demo10 needs to be better",
      "operations": []
    }
    """
    ir, issues = compiler.compile("m", "Demo10 needs to be better")
    assert ir.compile_status == CompileStatus.BLOCKED
    assert any(issue.code == NO_SUPPORTED_OPERATION for issue in issues)

def test_blocked_missing_target(compiler, mock_ollama):
    mock_ollama.run_prompt.return_value = """
    {
      "title": "Update file",
      "objective": "Update the file with the fix",
      "operations": [
        {
          "op_type": "modify_file",
          "target": "",
          "instruction": "Apply the fix"
        }
      ]
    }
    """
    ir, issues = compiler.compile("m", "Update the file with the fix")
    assert ir.compile_status == CompileStatus.BLOCKED
    assert any(issue.code == MISSING_REQUIRED_TARGET for issue in issues)

def test_blocked_conflicting_actions(compiler, mock_ollama):
    mock_ollama.run_prompt.return_value = """
    {
      "title": "Conflict",
      "objective": "Delete but keep",
      "operations": [
        {
          "op_type": "modify_file",
          "target": "pipeline.py",
          "instruction": "Delete this file"
        },
        {
          "op_type": "modify_file",
          "target": "pipeline.py",
          "instruction": "Keep this file unchanged"
        }
      ]
    }
    """
    ir, issues = compiler.compile("m", "Delete pipeline.py but keep it unchanged")
    assert ir.compile_status == CompileStatus.BLOCKED
    assert any(issue.code == CONFLICTING_ACTIONS for issue in issues)

def test_internal_failure(compiler, mock_ollama):
    mock_ollama.run_prompt.side_effect = Exception("Ollama crash")
    ir, issues = compiler.compile("m", "any input")
    assert ir.compile_status == CompileStatus.BLOCKED
    assert any(issue.code == "COMPILER_INTERNAL_FAILURE" for issue in issues)
