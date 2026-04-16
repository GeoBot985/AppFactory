from __future__ import annotations

import ast
import shutil
import tempfile
from pathlib import Path
from typing import Optional
from .models import ValidationReport, EditResult, EditStatus


class SafeWriteService:
    def __init__(self, project_root: Path, run_folder: Path):
        self.project_root = project_root
        self.run_folder = run_folder
        self.backups_dir = run_folder / "backups"
        self.backups_dir.mkdir(parents=True, exist_ok=True)

    def backup(self, relative_path: str) -> Path:
        source = self.project_root / relative_path
        if not source.exists():
             # For new files, no backup needed or empty backup
             return Path("")

        backup_path = self.backups_dir / relative_path
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, backup_path)
        return backup_path

    def validate_python(self, content: str) -> ValidationReport:
        try:
            ast.parse(content)
            return ValidationReport(syntax_ok=True, symbol_check_ok=True)
        except SyntaxError as e:
            return ValidationReport(
                syntax_ok=False,
                symbol_check_ok=False,
                error_message=f"Syntax error at line {e.lineno}: {e.msg}"
            )
        except Exception as e:
            return ValidationReport(
                syntax_ok=False,
                symbol_check_ok=False,
                error_message=str(e)
            )

    def verify_symbol(self, content: str, symbol_name: str, symbol_type: str) -> bool:
        """
        Verify that the symbol exists in the content.
        symbol_type: 'function' or 'class'
        """
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if symbol_type == "function" and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name == symbol_name:
                        return True
                if symbol_type == "class" and isinstance(node, ast.ClassDef):
                    if node.name == symbol_name:
                        return True
            return False
        except:
            return False

    def commit(self, relative_path: str, content: str) -> str:
        target = self.project_root / relative_path

        # Use a temporary file for atomic-like replacement
        with tempfile.NamedTemporaryFile(mode='w', delete=False, dir=target.parent, encoding='utf-8') as tf:
            tf.write(content)
            temp_name = tf.name

        try:
            shutil.move(temp_name, target)
        except Exception as e:
            if Path(temp_name).exists():
                Path(temp_name).unlink()
            raise e

        return str(target)
