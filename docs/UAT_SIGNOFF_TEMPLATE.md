# DataVision AI — UAT production sign-off template

Use this template only after the target technical acceptance has passed.

## Session

- Version tested:
- Environment:
- Date/time:
- Business owner:
- Technical facilitator:
- Dataset(s) used:

## Priority workflows

- [ ] Import a supported dataset and inspect profile/quality.
- [ ] Apply a preparation step and verify a new dataset version.
- [ ] Produce a statistical/visual analysis.
- [ ] Ask DataVision AI a contextual question and verify the displayed context.
- [ ] Build/export a report.
- [ ] Verify a governance/security workflow relevant to the organization.

## Decision

- [ ] PASS — accepted for the stated production scope.
- [ ] FAIL — blocking issues remain.
- [ ] WAIVED — formally accepted with documented limitations.

Blocking issues / limitations:

Signatory:

## Record the evidence

```bash
python scripts/production_signoff.py record \
  --kind uat \
  --status pass \
  --source "uat:<session-id>" \
  --actor "<business-owner>" \
  --details "Priority workflows accepted"
```

Then run:

```bash
python scripts/production_signoff.py verify --evidence-dir production-evidence --require-all
```
