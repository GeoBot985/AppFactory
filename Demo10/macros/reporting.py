import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from .library import MacroLibraryManager

class MacroReporting:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.library_manager = MacroLibraryManager(workspace_root)
        self.reports_dir = workspace_root / "runtime_data" / "macros" / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def generate_inventory_report(self) -> Path:
        macros = self.library_manager.list_macros()
        library = self.library_manager.load_library()

        inventory = []
        for m in macros:
            is_active = library.active_versions.get(m.name) == m.version
            inventory.append({
                "macro_id": m.macro_id,
                "name": m.name,
                "version": m.version,
                "status": m.verification_status,
                "active": is_active,
                "source_fragment_id": m.source_fragment_id
            })

        report_path = self.reports_dir / "macro_inventory.json"
        with open(report_path, "w") as f:
            json.dump({
                "generated_at": datetime.now().isoformat(),
                "macros": inventory
            }, f, indent=2)

        return report_path

    def generate_html_inventory(self) -> Path:
        macros = self.library_manager.list_macros()
        library = self.library_manager.load_library()

        rows = ""
        for m in macros:
            is_active = "Yes" if library.active_versions.get(m.name) == m.version else "No"
            rows += f"""
            <tr>
                <td>{m.name}</td>
                <td>{m.version}</td>
                <td>{m.verification_status}</td>
                <td>{is_active}</td>
                <td>{m.source_fragment_id}</td>
            </tr>
            """

        html = f"""
        <html>
        <head>
            <title>Macro Library Inventory</title>
            <style>
                body {{ font-family: sans-serif; }}
                table {{ width: 100%; border-collapse: collapse; }}
                th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
                th {{ background-color: #f4f4f4; }}
                .active {{ font-weight: bold; color: green; }}
            </style>
        </head>
        <body>
            <h1>Macro Library Inventory</h1>
            <p>Generated at: {datetime.now().isoformat()}</p>
            <table>
                <tr>
                    <th>Name</th>
                    <th>Version</th>
                    <th>Status</th>
                    <th>Active</th>
                    <th>Source Fragment</th>
                </tr>
                {rows}
            </table>
        </body>
        </html>
        """

        report_path = self.reports_dir / "macro_library.html"
        with open(report_path, "w") as f:
            f.write(html)

        return report_path
