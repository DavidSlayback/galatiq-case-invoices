# Coverage

## Plan element → tickets

| Element | Tickets |
|---|---|
| FR-1.1 schema | 02, 05 |
| FR-1.2 formats (PDF, TXT, JSON, CSV×2, XML, email) | 03 (JSON), 04, 15 (scans) |
| FR-1.3 typos and OCR noise | 05 |
| FR-1.4 dates | 05, 06 (DATE_UNPARSEABLE) |
| FR-1.5 missing fields | 05, 06 |
| FR-1.6 SKU canonicalisation | 05 |
| FR-1.7 provenance | 02 (model), 05 |
| FR-1.8 extraction self-correction | 05 |
| FR-2.1 seeded inventory | 02 |
| FR-2.2–2.5, 2.7, 2.13 stock, unknown, integrity, arithmetic, extra overruns | 06 |
| FR-2.6 per-SKU summing | 06 |
| FR-2.8 price, FR-2.9 currency | 06 |
| FR-2.10 duplicates and revisions | 10 |
| FR-2.11 dates | 06 |
| FR-2.12 vendor risk | 06 (address, urgency), 13 |
| FR-3.1–3.6 approval, critique, guardrail, escalate, near-threshold | 06 (NEAR_THRESHOLD), 07 |
| FR-4.1–4.2 pay or log | 03, 08 |
| FR-4.3 idempotent payment | 08 |
| FR-4.4 payment failures | 08 |
| FR-5.1–5.2 multi-agent, tools, structured output | 03, 05, 07 |
| FR-5.3–5.4 CLI and structured logs | 01, 03 |
| FR-5.5 batch | 10 |
| FR-5.6 UI | 12, 16 |
| FR-5.7 Grok | 17, 18 |
| NFR-1 offline | 03 (`--offline`), 05 |
| NFR-2/3 Python, local | 01 |
| NFR-4 testable, quality | 01 (gate), all |
| NFR-5 deterministic, rules in code | 06, 07 (guardrail) |
| NFR-6 tests without network | 03, 05, 09 |
| NFR-7 safe by default | 07, 08 |
| NFR-8 untrusted input | 05 (prompt), 14 |
| NFR-9 tracing | 03 (JSONL), 16 |
| NFR-10 one-command setup | 01, 19 |
| NFR-11 cost and time | 16, 18 |
| NFR-12 GitHub repository | done (repo exists) |
| D1 literal stock with caveat | 06, 19 (README) |
| D2 and D25 ledger and events | 02, 10 |
| D3 no stock consumption | 06 |
| D4 no partial payment | 08 |
| D5 FX | 02 (rate), 06 |
| D6 price tolerance | 06 |
| D7 tiers | 07 |
| D8 as-of date | 01, 06 |
| D9 vendor seed | 02, 13 |
| D10 fraud escalates | 07, 13, 14 |
| D11 PydanticAI + pydantic-graph | 03 |
| D12 model config (amended) | 01, 17 |
| D13 parsers then LLM | 04, 05 |
| D14 2 retries then finding | 05 |
| D15 VP + critic | 07 |
| D16 OCR chain | 15 |
| D17 SQLite + JSONL | 02, 03 |
| D18 Rich + Streamlit | 03, 12 |
| D19 inbox CLI + UI | 11, 12 |
| D20 eval, adversarial, vendor risk, ROI | 09, 14, 13, 16 |
| D21 editable ROI assumptions | 16 |
| D22 build order | WAVES.md |
| D23 tooling | 01 |
| D24 presentation | 19 |
| D25a extended event types | 02 |
| D26 terms tolerance | 06 |
| D27 boundaries, UNKNOWN_VENDOR severity | 06, 07 |
| D28 fixed VP outcomes | 07, 09 |
| D29 payment currency | 08 |
| D30 1007 arithmetic | 05, 06, 09 |
| A2 Haiku | 01 |
| A3 resume from SQLite | 11 |
| A4 goldens offline, live recording later | 03, 05, 18 |
| A5 rule IDs and severities | 02, 06 |
| A6 FX rate | 02 |
| A7 payment hook | 08 |
| A8 1004 R1 delta | 09 (pending), 10 |
| Live model parity | 18 |
| D31 subscription CLI backends | 17, 18 |
| D32 backend auto-detect | 17, 19 (README) |

## Ticket → plan anchor

| Ticket | Anchors |
|---|---|
| 01 | D23, A1, A2, NFR-2/3/10 |
| 02 | D2, D5, D9, D17, D25, A5, A6, FR-2.1 |
| 03 | D11, D12, A3, A4, FR-4.1, FR-5.3/5.4, NFR-9 |
| 04 | FR-1.2, D13 |
| 05 | FR-1.*, D13, D14, NFR-8 |
| 06 | FR-2.*, D1, D3, D5, D6, D7, D8, D10 |
| 07 | FR-3.*, D7, D10, D15 |
| 08 | FR-4.*, D4, A7 |
| 09 | D20, A8 |
| 10 | FR-2.10, FR-5.5, D2, D25, A8 |
| 11 | D19, A3 |
| 12 | FR-5.6, D18, D19 |
| 13 | FR-2.12, D9, D10 |
| 14 | NFR-8, D10, D20 |
| 15 | D16 |
| 16 | NFR-11, D21 |
| 17 | D12, D31, D32, NFR-8 |
| 18 | A4, D31, live parity, NFR-11, FR-5.7 |
| 19 | D24, D1 caveat, D32 |

**Unmapped:** none in either direction.
