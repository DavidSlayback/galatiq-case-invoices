# Human readiness

No human action blocks any ticket.

## Optional action

**H2: install Tesseract.** Enables the local-OCR path in ticket 15; its tests skip without it.
- Run: `sudo apt install tesseract-ocr`
- Done when: `tesseract --version` prints a version.
- Fallback until then: scanned PDFs go straight to the vision model.

## Standing conditions (no action needed)

- `cursor-agent` and `claude` stay logged in. On 2026-11-12 both answered a headless test call.
- If either CLI reports a quota or rate limit, the loop stops and reports what remains (ticket 17's stop condition). The fix is to wait for the quota to reset, or to say "switch the live pass to `cli:claude:haiku`".

## Decisions already taken (2026-11-12)

| Decision | Answer |
|---|---|
| API credits | None bought; use the Cursor Pro and Claude Max subscriptions (D31) |
| Live default | Grok 4.7 via Cursor, with Claude Haiku via Max as the cross-check |
| Unattended live calls | Allowed, about 100–200 calls |
| Default with nothing configured | Auto-detect, with offline replay last (D32) |
| Demo video | Synthetic, made by the agent |

H1 (an xAI key) and H3 (credits) are retired. The xAI API path is still selectable by config for anyone who has a key.
