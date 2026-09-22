# Validation DataVision AI v2.49.0

## Scope
v2.49.0 closes the professional Reporting milestone. The Report Studio now supports ordered composable blocks (text, KPI, table, insight, model, code, methodology and visualization), per-block provenance, content integrity hashing, report validation and the existing governed PDF/DOCX/HTML/Markdown exports.

## Acceptance gate
`python scripts/report_acceptance.py --root . --check`

The gate requires 8/8 capabilities from `compliance/REPORT_ACCEPTANCE.json` and executes the v2.49 backend/frontend contract tests.

## Reproducibility
Every generated report locks the dataset version. New report blocks carry provenance with dataset id/version and source kind/reference. A SHA-256 content hash protects the persisted report definition; `/api/v1/datasets/{dataset_id}/reports/{report_id}/validate` verifies the stored artifact.

## Export governance
Report export remains subject to the Data Reliability publication gate. Existing historical reports without per-block provenance remain readable; validation reports a warning rather than silently rewriting them.
