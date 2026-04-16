import pytest
from services.draft_spec.models import DraftSpec, DraftTask, DraftIntent, DraftTargets, Certainty
from services.draft_spec.validator import DraftSpecValidator
from services.compiler.compiler import DraftSpecCompiler
from services.compiler.models import CompileStatus

def test_draft_spec_basic_validation():
    validator = DraftSpecValidator()

    # Valid draft
    draft = DraftSpec(
        title="Test App",
        tasks=[DraftTask(id="t1", type="create_file", path="main.py", summary="init")]
    )
    errors = validator.validate_draft_spec_basic(draft)
    assert len(errors) == 0

    # Missing title
    draft.title = ""
    errors = validator.validate_draft_spec_basic(draft)
    assert any(e["field"] == "title" for e in errors)

def test_compiler_basic():
    compiler = DraftSpecCompiler()

    # Valid draft compiles
    draft = DraftSpec(
        title="Test App",
        tasks=[DraftTask(id="t1", type="create_file", path="main.py", summary="init")]
    )
    plan, report = compiler.compile(draft)
    assert report.status == CompileStatus.SUCCESS
    assert plan.plan_id != "failed"
    assert "t1" in plan.execution_graph

def test_compiler_dependency_cycle():
    compiler = DraftSpecCompiler()

    # Cycle: t1 -> t2 -> t1
    draft = DraftSpec(
        title="Cycle App",
        tasks=[
            DraftTask(id="t1", type="create_file", path="a.py", summary="a", depends_on=["t2"]),
            DraftTask(id="t2", type="create_file", path="b.py", summary="b", depends_on=["t1"])
        ]
    )
    plan, report = compiler.compile(draft)
    assert report.status == CompileStatus.FAILED
    assert any(e.code == "dependency_cycle" for e in report.errors)
