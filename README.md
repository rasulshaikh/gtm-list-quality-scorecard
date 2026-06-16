# GTM List Quality Scorecard

Pre-send quality grading for any lead list. Catches bad lists before they burn inboxes — duplicate rate, title drift, catch-all density, ICP fit, and verification coverage.

## Why this exists

Three campaign failure modes this catches in 5 minutes:

1. **Bad list** — wrong people, wrong titles
2. **Unverified emails** — bounces kill domain reputation
3. **ICP drift** — you think you're targeting VPs, list is mostly Managers

## Setup

```bash
# No dependencies beyond Python 3.10+
python scorecard.py --list example_leads.csv --out scorecard.md
```

## Usage

```bash
python scorecard.py --list leads.csv --out scorecard.md

# With ICP filters from onboarding
python scorecard.py \
  --list leads.csv \
  --icp-file example_icp.yaml \
  --out scorecard.md \
  --json scorecard.json
```

## Input CSV

Required columns (case-insensitive):

| Column | Aliases |
|--------|---------|
| `email` | — |
| `first_name` | — |
| `last_name` | — |
| `job_title` | `title` |
| `company_name` | `company` |
| `company_domain` | derived from email if missing |
| `company_industry` | optional, for ICP fit |
| `company_headcount` | optional, for ICP fit |
| `email_status` | `verification_status`, `mv_status` |

## The 8 dimensions

| # | Dimension | Rule |
|---|-----------|------|
| 1 | Email verification | 100% must be verified before sending |
| 2 | Duplicate emails | <1% acceptable, >5% is a problem |
| 3 | Duplicate domains | 1-2 leads per domain ideal |
| 4 | Title relevance | ≥80% match ICP title list |
| 5 | Bad-title detection | <2% intern/assistant/coordinator |
| 6 | Catch-all density | <5% info@/contact@/hello@ |
| 7 | ICP fit | ≥80% match industry + headcount |
| 8 | Name quality | ≥95% real first + last names |

## Letter grades

| Score | Grade | Action |
|-------|-------|--------|
| 90-100 | A+/A | Ship it |
| 80-89 | B | Minor fixes, then ship |
| 70-79 | C | Fix top 3 issues first |
| 60-69 | D | Serious cleanup required |
| <60 | F | Don't send. Rebuild the list. |

## PDF guide

Download: [docs/play-guide.pdf](docs/play-guide.pdf) — 8 dimensions, grade mapping, pre-send checklist.

## n8n workflow

Import `n8n/pre-send-list-gate.json` into n8n.

Webhook `POST /gtm-list-gate` receives Clay export `{ leads: [...] }`. Scores in-code. Grade B+ forwards to Omnibound push pipeline. Below B blocks send + Slack alert.

**Env vars:** `N8N_OMNIBOUND_WEBHOOK_URL`, `SLACK_GTM_CHANNEL`

## Pair with

- [gtm-deliverability-audit](https://github.com/rasulshaikh/gtm-deliverability-audit) — post-send health check
- [gtm-ai-lead-scorer](https://github.com/rasulshaikh/gtm-ai-lead-scorer) — per-lead 0-100 scoring
- [gtm-email-cadences](https://github.com/rasulshaikh/gtm-email-cadences) — copy after list passes