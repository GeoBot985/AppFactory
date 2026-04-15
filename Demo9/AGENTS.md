## Project Purpose
`Demo9` imports diagram images, reconstructs structural graph topology, routes connectors, and exports deterministic output artifacts for validation.

## Required Workflow
After every code change:
1. Run: `python Demo9/app.py`
2. Run: `pytest -q Demo9/tests`
3. Do not stop while any required acceptance test fails.
4. Do not declare success based only on image appearance.
5. Use `diagram.json` and `summary.txt` as the source of truth.

## Do Not Declare Success Unless
- The pipeline run completes.
- The acceptance test suite passes.
- Required output files were regenerated for the target diagrams.
- Reported metrics satisfy the encoded acceptance checks.

## Primary Acceptance Targets
`Diagram1`
- `route_count >= 3`
- `graph_vertices < 55`
- `degree2_endpoints_reclassified > 0`
- `gate_stubs_absorbed > 0`
- `intersections_accepted > 0` once Spec 009 is implemented
- restore visible connectivity consistent with expected diagram structure
- verification should not be `fail`

`Diagram2`
- `route_count >= 3`
- verification not `fail`

## Debug Workflow When Failing
- Re-run `python Demo9/app.py` to refresh outputs.
- Read `outputs/Diagram1/diagram.json` and `outputs/Diagram1/summary.txt` first.
- Compare graph metrics, routing metrics, and verification status before inspecting images.
- Use `pytest -q Demo9/tests -k <pattern>` for focused iteration after identifying the failing metric.

## Files To Inspect After Run
- `outputs/Diagram1/diagram.json`
- `outputs/Diagram1/summary.txt`
- `outputs/Diagram1/07e_connector_graph.png`
- `outputs/Diagram1/07g_routed_connectors.png`
