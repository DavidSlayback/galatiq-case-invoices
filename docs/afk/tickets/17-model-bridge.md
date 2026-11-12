# 17 — Model backends: subscription CLI bridge and auto-detect

**Source:** [17-model-bridge.md](../../tickets/17-model-bridge.md)
**Type:** AFK
**Blocked by:** 05 (the extractor agent and its schema); 07 (the VP and critic agents)
**Wave:** 5
**Lane:** models
**Verifier profile:** full (it launches subprocesses on untrusted invoice text)
**What it delivers:** `--model` accepts `cli:cursor:<model>` (Grok via Cursor), `cli:claude:<model>` (Claude via Claude Code on Max), any PydanticAI API model string, or `offline`. With no model set, the backend is picked automatically: an xAI key, then another API key, then a logged-in CLI, then offline replay with a banner.

## Context
- Why: David has no API credits to spend and wants to use the subscriptions he already has: Cursor Pro (which serves Grok) and Claude Max (D31). Graders without those logins still need the system to run (D32).
- Constraining decisions:
  - D31 (David, 2026-11-12): live calls go through `cursor-agent -p` and `claude -p`. Grok 4.7 through Cursor is the default; Claude Haiku through Max is the cross-check. Buying API credits was rejected.
  - D32 (David, 2026-11-12): the auto-detect order above. Defaulting to offline was rejected.
  - The bridge is a PydanticAI `FunctionModel` adapter. It renders the system and user messages plus the output JSON Schema into one prompt, runs the CLI, parses the JSON and returns it as the output-tool call, so the agents, `output_validator` and `ModelRetry` loops are unchanged.
- **Verified 2026-11-12:**
  - `cursor-agent -p --trust --output-format json --model grok-4.7-low-fast` returned a `result` JSON string with token usage, in about 3 s of model time (15 s wall clock).
  - `claude -p --output-format json --model haiku --json-schema <schema>` returned `structured_output` matching the schema, in about 9 s. It loaded the default Claude Code system prompt (about 45K cached tokens), so pass `--system-prompt`.
  - Grok models listed by `cursor-agent models` include `grok-4.7-{low,medium,high,xhigh}[-fast]`.
- Sandbox (required, because invoice text is untrusted and both CLIs are agents):
  - Cursor: run with `--mode ask` (read-only) and `--trust`, with `cwd` set to a fresh empty temp dir per call. Never pass `--force` or `--yolo`.
  - Claude: run with `--system-prompt <ours>`, tools disabled, `--strict-mcp-config` with no MCP config, `--setting-sources ""` and `--no-session-persistence`, also with `cwd` set to an empty temp dir.
  - The exact flag spelling for disabling all Claude tools is unverified: confirm with `claude --help` before use, and if no all-tools-off switch exists, use `--disallowed-tools` listing every built-in tool.
- Vision: for the scan fallback (ticket 15), copy the page PNG into the temp dir and reference it in the prompt. Cursor can read it in ask mode; Claude needs `--allowed-tools Read` scoped to that dir. That this works headlessly is unverified; if it fails, record it as a limitation and keep the API vision path.
- Failure paths: CLI missing or not logged in → auto-detect skips it, and an explicit `--model cli:*` exits with a clear message. Non-JSON or schema-invalid output → raise so PydanticAI retries; after the retry budget → a finding plus escalation, never a crash. A timeout (default 120 s) → the same retry path. Quota or rate-limit messages → stop and report (a stop condition). Concurrency is at most 2 CLI calls at once.
- Plan anchors: D12 (amended), D31, D32, NFR-1, NFR-8.

## Acceptance criteria
- [ ] `invoice_agents/models_backend.py` resolves model strings and runs auto-detect; unit-tested with a monkeypatched environment
- [ ] The CLI bridge is tested offline against fake `cursor-agent` and `claude` scripts on PATH that record their argv and cwd: asserts `--mode ask`, no `--force`/`--yolo`, an empty temp cwd, Claude tools off, and `--system-prompt` passed
- [ ] Fake CLIs returning garbage, invalid JSON or a timeout drive the retry path, then a finding
- [ ] `main.py --invoice_path=data/invoices/invoice_1004.json` with nothing configured prints the backend chosen and why
- [ ] One manual smoke call on each real CLI (1001), with the transcript saved to docs/live/smoke.md. This uses the subscription quota, as D31 allows.
- [ ] README model section: the four backends and how each is selected

## Verification
- `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest -q` — exit 0
- `uv run python main.py --model cli:cursor:grok-4.7-low-fast --invoice_path=data/invoices/invoice_1001.txt` — exit 0, Grok extraction, decision shown

## Change surface
- invoice_agents/models_backend.py, invoice_agents/agents/*.py (model construction only), invoice_agents/settings.py, tests/test_models_backend.py, tests/fake_bin/
- Conflict risk: low. The agents take a model object, so only the factory changes.

## Out of scope
- Buying API credits; the xAI API path is supported by config but untested until someone has a key

## Completion evidence
- Fake-CLI test output showing the sandbox flags
- docs/live/smoke.md
