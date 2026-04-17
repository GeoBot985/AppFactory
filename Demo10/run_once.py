import argparse
import sys
import uuid
from pathlib import Path

from orchestrator.single_command import SingleCommandOrchestrator
from orchestrator.models import SingleCommandRequest
from services.input_compiler.compiler import NaturalInputCompiler
from services.ollama_service import OllamaService
from services.planner.plan_builder import PlanBuilder
from verification.harness import VerificationHarness
from services.policy.promotion_engine import PromotionEngine
from services.policy.models import PromotionPolicy, EnvironmentPolicy, Environment
from services.policy.audit import PromotionAuditService

def main():
    parser = argparse.ArgumentParser(description="Demo10 Single Command Mode")
    parser.add_argument("input", help="Natural language input")
    parser.add_argument("--env", choices=["dev", "staging", "prod"], default="dev", help="Target environment")
    parser.add_argument("--strictness", choices=["strict", "tolerant", "debug"], default="strict", help="Verification strictness")
    parser.add_argument("--workspace", choices=["in_place", "temp_workspace"], default="temp_workspace", help="Workspace mode")

    args = parser.parse_args()

    workspace_root = Path.cwd()

    # Setup dependencies (Simplified for CLI)
    ollama = OllamaService()
    compiler = NaturalInputCompiler(ollama, workspace_root)
    plan_builder = PlanBuilder(workspace_root)
    verification_harness = VerificationHarness(workspace_root)

    # Mock Policy for Demo
    policy = PromotionPolicy(
        environment_rules={
            "dev": EnvironmentPolicy(
                required_verdict="pass_with_warnings",
                allow_warn=True,
                allow_not_comparable=True,
                blocked_drift_categories=[],
                max_failures=5,
                require_exact_match=False
            ),
            "prod": EnvironmentPolicy(
                required_verdict="pass",
                allow_warn=False,
                allow_not_comparable=False,
                blocked_drift_categories=["plan_drift", "output_drift"],
                max_failures=0,
                require_exact_match=True
            )
        }
    )
    audit_service = PromotionAuditService(workspace_root)
    promotion_engine = PromotionEngine(policy, audit_service, workspace_root)

    orchestrator = SingleCommandOrchestrator(
        compiler, plan_builder, verification_harness, promotion_engine, workspace_root
    )

    request = SingleCommandRequest(
        request_id=f"req_{uuid.uuid4().hex[:8]}",
        input_text=args.input,
        target_environment=args.env,
        strictness=args.strictness,
        workspace_mode=args.workspace
    )

    print(f"RUNNING SINGLE COMMAND: {args.input}")
    print(f"Environment: {args.env} | Strictness: {args.strictness}")
    print("-" * 40)

    result = orchestrator.run_single_command(request)

    print("\nRUN-ONCE RESULT")
    print(f"Compile: {result.compile_status}")
    print(f"Plan: {result.plan_id}")
    print(f"Execution: {'completed' if result.run_id else 'failed'}")
    print(f"Verification: {result.summary.get('verification_verdict', 'N/A')}")
    print(f"Promotion: {result.summary.get('promotion_decision', 'N/A')}")
    print("-" * 40)
    print(f"FINAL STATUS: {result.final_status.upper()}")

    if result.final_status in ["failed", "blocked", "rejected"]:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
