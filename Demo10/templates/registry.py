from __future__ import annotations
from typing import Dict, List, Optional
from .models import DraftTemplate, TemplateParameter, TemplateParameterType

class TemplateRegistry:
    def __init__(self):
        self._templates: Dict[str, DraftTemplate] = {}
        self._register_initial_templates()

    def register(self, template: DraftTemplate):
        self._templates[template.template_id] = template

    def get_template(self, template_id: str) -> Optional[DraftTemplate]:
        return self._templates.get(template_id)

    def list_templates(self) -> List[DraftTemplate]:
        return list(self._templates.values())

    def _register_initial_templates(self):
        # 1. build_small_app
        self.register(DraftTemplate(
            template_id="build_small_app",
            version=1,
            title="Build Small App",
            description="Create a new standalone application with standard structure.",
            supported_task_kinds=["build_app"],
            parameters=[
                TemplateParameter("app_name", TemplateParameterType.STRING, "Name of the application"),
                TemplateParameter("ui_type", TemplateParameterType.ENUM, "UI Framework to use", choices=["tkinter", "cli", "web"], default="cli"),
                TemplateParameter("persistence", TemplateParameterType.BOOLEAN, "Include persistence layer?", default=False),
                TemplateParameter("include_tests", TemplateParameterType.BOOLEAN, "Generate initial tests?", default=True),
                TemplateParameter("package_name", TemplateParameterType.STRING, "Python package name", default="app"),
                TemplateParameter("entrypoint", TemplateParameterType.PATH, "Main entrypoint file", default="main.py")
            ],
            skeleton={
                "title": "Build ${app_name}",
                "description": "Scaffold a new ${ui_type} application named ${app_name}.",
                "intent": {
                    "task_kind": "build_app",
                    "summary": "Build ${app_name} using ${ui_type}"
                },
                "targets": {
                    "inferred_entrypoints": ["${entrypoint}"]
                },
                "tasks": [
                    {"id": "init_package", "type": "create_file", "path": "${package_name}/__init__.py", "summary": "Initialize package"},
                    {"id": "create_main", "type": "create_file", "path": "${entrypoint}", "summary": "Create entrypoint for ${app_name}"}
                ]
            }
        ))

        # 2. add_feature
        self.register(DraftTemplate(
            template_id="add_feature",
            version=1,
            title="Add Feature",
            description="Add a new feature or capability to an existing module.",
            supported_task_kinds=["add_feature"],
            parameters=[
                TemplateParameter("feature_name", TemplateParameterType.STRING, "Name of the feature"),
                TemplateParameter("target_module", TemplateParameterType.PATH, "Module to add feature to"),
                TemplateParameter("include_tests", TemplateParameterType.BOOLEAN, "Add tests for the feature?", default=True)
            ],
            skeleton={
                "title": "Add Feature: ${feature_name}",
                "description": "Implement ${feature_name} in ${target_module}.",
                "intent": {
                    "task_kind": "add_feature",
                    "summary": "Implement ${feature_name}"
                },
                "targets": {
                    "inferred_editable_paths": ["${target_module}"]
                },
                "tasks": [
                    {"id": "implement_feature", "type": "patch_file", "path": "${target_module}", "summary": "Implement ${feature_name} logic"}
                ]
            }
        ))

        # 3. fix_bug
        self.register(DraftTemplate(
            template_id="fix_bug",
            version=1,
            title="Fix Bug",
            description="Identify and resolve a bug in the codebase.",
            supported_task_kinds=["fix_bug"],
            parameters=[
                TemplateParameter("bug_description", TemplateParameterType.STRING, "Description of the bug"),
                TemplateParameter("failing_file", TemplateParameterType.PATH, "File where the bug is located"),
                TemplateParameter("failing_test", TemplateParameterType.PATH, "Test file that reproduces the bug", required=False)
            ],
            skeleton={
                "title": "Fix Bug: ${bug_description}",
                "intent": {
                    "task_kind": "fix_bug",
                    "summary": "Fix ${bug_description}"
                },
                "targets": {
                    "inferred_editable_paths": ["${failing_file}"]
                },
                "tasks": [
                    {"id": "fix_logic", "type": "patch_file", "path": "${failing_file}", "summary": "Fix bug: ${bug_description}"}
                ]
            }
        ))

        # 4. add_tests
        self.register(DraftTemplate(
            template_id="add_tests",
            version=1,
            title="Add Tests",
            description="Add unit or integration tests for a module.",
            supported_task_kinds=["add_tests"],
            parameters=[
                TemplateParameter("target_module", TemplateParameterType.PATH, "Module to test"),
                TemplateParameter("test_file", TemplateParameterType.PATH, "Path for the new tests")
            ],
            skeleton={
                "title": "Add Tests for ${target_module}",
                "intent": {
                    "task_kind": "add_tests",
                    "summary": "Increase test coverage for ${target_module}"
                },
                "tasks": [
                    {"id": "create_tests", "type": "create_file", "path": "${test_file}", "summary": "Add tests for ${target_module}"},
                    {"id": "run_new_tests", "type": "run_tests", "path": "${test_file}", "summary": "Verify new tests pass", "depends_on": ["create_tests"]}
                ]
            }
        ))

        # 5. patch_existing_module
        self.register(DraftTemplate(
            template_id="patch_existing_module",
            version=1,
            title="Patch Module",
            description="Apply a small patch or refactor to an existing file.",
            supported_task_kinds=["refactor", "patch_file"],
            parameters=[
                TemplateParameter("target_file", TemplateParameterType.PATH, "File to patch"),
                TemplateParameter("patch_summary", TemplateParameterType.STRING, "What is being changed")
            ],
            skeleton={
                "title": "Patch ${target_file}",
                "intent": {
                    "task_kind": "refactor",
                    "summary": "${patch_summary}"
                },
                "tasks": [
                    {"id": "apply_patch", "type": "patch_file", "path": "${target_file}", "summary": "${patch_summary}"}
                ]
            }
        ))

        # 6. add_ui_screen
        self.register(DraftTemplate(
            template_id="add_ui_screen",
            version=1,
            title="Add UI Screen",
            description="Create a new UI screen or window.",
            supported_task_kinds=["add_feature", "add_ui"],
            parameters=[
                TemplateParameter("screen_name", TemplateParameterType.STRING, "Name of the UI screen"),
                TemplateParameter("ui_framework", TemplateParameterType.ENUM, "UI Framework", choices=["tkinter", "custom"], default="tkinter"),
                TemplateParameter("target_file", TemplateParameterType.PATH, "File to add screen to")
            ],
            skeleton={
                "title": "Add UI Screen: ${screen_name}",
                "intent": {
                    "task_kind": "add_feature",
                    "summary": "Create ${screen_name} screen using ${ui_framework}"
                },
                "tasks": [
                    {"id": "implement_ui", "type": "patch_file", "path": "${target_file}", "summary": "Implement ${screen_name} screen"}
                ]
            }
        ))
