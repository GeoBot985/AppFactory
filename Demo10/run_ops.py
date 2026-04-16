#!/usr/bin/env python3
import sys
import argparse
import json
from pathlib import Path
from Demo10.ops.ops_service import OpsService
from Demo10.ops.health import HealthEvaluator
from Demo10.ops.rebuild import RebuildService

def main():
    parser = argparse.ArgumentParser(description="Demo10 Operations CLI")
    parser.add_argument("command", choices=["dashboard", "health", "queues", "runs", "approvals", "rebuild-indices"])
    parser.add_argument("--project-root", default=".", help="Project root directory")

    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()
    ops = OpsService(project_root)
    health_eval = HealthEvaluator(project_root)

    if args.command == "dashboard":
        data = ops._load_json("dashboard_summary.json", {})
        print(json.dumps(data, indent=2))
    elif args.command == "health":
        data = health_eval.evaluate()
        print(json.dumps(data.to_dict(), indent=2))
    elif args.command == "queues":
        data = ops._load_json("queue_index.json", [])
        print(json.dumps(data, indent=2))
    elif args.command == "runs":
        data = ops._load_json("run_index.json", [])
        print(json.dumps(data, indent=2))
    elif args.command == "approvals":
        data = ops._load_json("approval_index.json", [])
        print(json.dumps(data, indent=2))
    elif args.command == "rebuild-indices":
        rebuild = RebuildService(project_root)
        rebuild.rebuild_all()

if __name__ == "__main__":
    main()
