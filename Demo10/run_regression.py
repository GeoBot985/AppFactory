#!/usr/bin/env python3
import sys
import argparse
import json
from pathlib import Path
from verification.regression_runner import RegressionRunner

def main():
    parser = argparse.ArgumentParser(description="Demo10 Regression Runner")
    parser.add_argument("suite", help="Name of the regression suite to run")
    parser.add_argument("--update-baseline", action="store_true", help="Update golden baselines")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument("--regression-root", default="regression", help="Regression suites root directory")
    parser.add_argument("--model", default="granite4:3b", help="LLM model name")

    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    regression_root = project_root / args.regression_root

    runner = RegressionRunner(project_root, regression_root, model_name=args.model)

    print(f"Running regression suite: {args.suite}")
    summary = runner.run_suite(args.suite, update_baseline=args.update_baseline)

    if "error" in summary:
        print(f"Error: {summary['error']}")
        sys.exit(1)

    print(f"Total: {summary['total']}")
    print(f"Passed: {summary['passed']}")
    print(f"Failed: {summary['failed']}")

    if summary['failed'] > 0:
        print("\nFailures:")
        for res in summary['results']:
            if res['status'] == 'fail':
                print(f"  - {res['case']}: {res.get('error') or res.get('mismatches')}")
        sys.exit(1)

    print("\nAll regression cases passed.")

if __name__ == "__main__":
    main()
