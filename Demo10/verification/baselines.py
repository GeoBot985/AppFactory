from __future__ import annotations
import json
from typing import Any, Dict, List

class BaselineComparator:
    def compare(self, actual: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, Any]:
        # Stable fields to compare
        fields_to_compare = ["final_status", "verification", "regression"]

        mismatches = []
        for field in fields_to_compare:
            if field in actual and field in expected:
                if actual[field] != expected[field]:
                    mismatches.append({
                        "field": field,
                        "expected": expected[field],
                        "actual": actual[field]
                    })
            elif field in expected:
                 mismatches.append({
                     "field": field,
                     "expected": expected[field],
                     "actual": "missing"
                 })

        # Compare specific counts in verification
        if "verification" in actual and "verification" in expected:
             actual_v = actual["verification"]
             expected_v = expected["verification"]
             for key in ["passed", "failed", "warned"]:
                  if actual_v.get(key) != expected_v.get(key):
                       mismatches.append({
                           "field": f"verification.{key}",
                           "expected": expected_v.get(key),
                           "actual": actual_v.get(key)
                       })

        return {
            "status": "pass" if not mismatches else "fail",
            "mismatches": mismatches
        }
