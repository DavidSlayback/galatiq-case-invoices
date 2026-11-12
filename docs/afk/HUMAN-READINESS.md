# Human readiness

These are every foreseeable human action or decision. None of them block the AFK queue (01–17).

## Action items

**H1: get an xAI API key.** Unblocks ticket 18.
- Steps: create a key in the xAI console, then add `export XAI_API_KEY=...` to `~/user-env.sh`.
- Done when: `grep -c XAI_API_KEY ~/user-env.sh` prints 1.
- Fallback until then: Claude Haiku stays the default and the README says Grok is a config switch.

**H2: install Tesseract** (optional). Unblocks the Tesseract path in ticket 15; its tests skip without it.
- Run: `sudo apt install tesseract-ocr`
- Done when: `tesseract --version` prints a version.
- Fallback until then: scanned PDFs go straight to the vision model.

**H3: sort out API credits and a live-spend cap.** Unblocks ticket 19, then 18.
- Confirm which Anthropic account and key hold the credits, and put that key in `ANTHROPIC_API_KEY`.
- Give a cap, for example "$5 per run, $30 total". On 2026-11-12 the current key answered a free models-list call with HTTP 200, but whether it has credit was not checked, by David's choice.
- Done when: David says "live pass approved, cap $X".
- Fallback until then: everything is verified offline against the goldens, and the README marks live results as pending.

## Decisions already taken (2026-11-12)

| Decision | Answer |
|---|---|
| Stand-in model | Claude Haiku |
| Live calls unattended | No; collected into HITL ticket 19 |
| Demo video | Synthetic, made by the agent |
