from .models import PromotionPolicy, EnvironmentPolicy

DEFAULT_PROMOTION_POLICY = PromotionPolicy(
    policy_id="default_v1",
    environment_rules={
        "dev": EnvironmentPolicy(
            allow_warn=True,
            allow_not_comparable=True,
            required_verdict="pass_with_warnings",
            blocked_drift_categories=[],
            max_failures=0,
            require_exact_match=False
        ),
        "staging": EnvironmentPolicy(
            allow_warn=True,
            allow_not_comparable=False,
            required_verdict="pass_with_warnings",
            blocked_drift_categories=[
                "plan_drift",
                "execution_drift",
                "output_drift"
            ],
            max_failures=0,
            require_exact_match=False
        ),
        "prod": EnvironmentPolicy(
            allow_warn=False,
            allow_not_comparable=False,
            required_verdict="pass",
            blocked_drift_categories=[
                "plan_drift",
                "execution_drift",
                "output_drift",
                "rollback_drift"
            ],
            max_failures=0,
            require_exact_match=False
        )
    }
)
