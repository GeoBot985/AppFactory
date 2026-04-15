
import sys
from pathlib import Path
sys.path.append(str(Path.cwd() / "Demo10"))

from services.restore_service import RestoreService, FilePreview
from services.bundle_service import WorkingSetBundle, BundleFile
from services.bundle_edit_service import CandidateBundle, CandidateFile

def test_restore_preview():
    service = RestoreService()
    project_root = Path("test_project").resolve()

    # Ensure exact content
    (project_root / "existing.txt").write_text("old content", encoding="utf-8")
    (project_root / "unchanged.txt").write_text("unchanged content", encoding="utf-8")

    # Bundle for testing
    bundle = WorkingSetBundle(
        project_root=str(project_root),
        source_spec_text="test spec",
        built_at="2023-01-01T00:00:00",
        status="completed",
        primary_files=[
            BundleFile(
                relative_path="new_file.txt",
                selection_kind="primary_editable",
                file_content="new content",
                content_status="included",
                included_reason="test"
            ),
            BundleFile(
                relative_path="existing.txt",
                selection_kind="primary_editable",
                file_content="modified content",
                content_status="included",
                included_reason="test"
            ),
            BundleFile(
                relative_path="unchanged.txt",
                selection_kind="primary_editable",
                file_content="unchanged content",
                content_status="included",
                included_reason="test"
            ),
            BundleFile(
                relative_path="skipped.txt",
                selection_kind="primary_editable",
                file_content="skipped content",
                content_status="blocked",
                included_reason="test"
            )
        ]
    )

    preview = service.compute_bundle_preview(project_root, bundle)

    print(f"Total files: {preview.total_files}")
    print(f"New count: {preview.new_count}")
    print(f"Modified count: {preview.modified_count}")
    print(f"Unchanged count: {preview.unchanged_count}")
    print(f"Skipped count: {preview.skipped_count}")

    for f in preview.files:
        print(f"File: {f.relative_path}, Change: {f.change_type}")

    assert preview.total_files == 4
    assert preview.new_count == 1
    assert preview.modified_count == 1
    assert preview.unchanged_count == 1
    assert preview.skipped_count == 1
    print("Test passed!")

if __name__ == "__main__":
    test_restore_preview()
