# 13 · Vendor registry and risk score

- **Blocked by:** 09
- **Source:** D9, D10, FR-2.12
- **Status:** todo

## What
A risk score from 0 to 100 from weighted signals (unknown vendor, alias or rename, suspicious address, urgency or wire language, bank-detail change compared with the registry). Shown in the CLI and UI, passed to the VP agent, and above a threshold it adds a fraud finding.

## Surfaces
invoice_agents/vendors.py, tests/test_vendors.py

## Acceptance
- [ ] 1003 and 1005 score high; 1001 scores low
- [ ] 1012 matches FastShip through the alias and gets VENDOR_RENAMED

## Verify
```bash
uv run ruff check . && uv run pyright && uv run pytest -q
```

## Docs
docs/RULES.md risk section

> The enriched tickets in [../afk/tickets/](../afk/tickets/) supersede these where they differ.
