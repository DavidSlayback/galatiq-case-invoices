# 17 — README, Artifact presentation and synthetic demo video

**Source:** [17-presentation.md](../../tickets/17-presentation.md)
**Type:** AFK
**Blocked by:** 12 (screenshots); 13 (risk content); 14 (adversarial results); 15 (OCR story); 16 (ROI)
**Wave:** 10
**Lane:** serial-required
**Verifier profile:** self-check
**What it delivers:** A README that gets a fresh clone to the scorecard, a Claude Artifact presentation, and a 2–3 minute synthetic narrated demo video.

## Context
- Why: D24; the brief's presentation criterion.
- Constraining decisions: D24: README plus Artifact (in place of slides) plus video. The video is synthetic (David, 2026-11-12): use the record-demo-video skill's synthetic mode with a local Kokoro voice, recording real offline CLI and Streamlit runs. The README states that live-model results are pending until ticket 19 if it hasn't run. No AI-disclosure boilerplate.
- Failure paths: A fresh clone without an API key must still reach the scorecard through --offline.
- Plan anchors: PRD §1; D24

## Acceptance criteria
- [ ] README: problem, quickstart (offline and live), the generated graph, decision summary, rules link, scorecard, ROI, limitations and roadmap (PO three-way match, stock reservation)
- [ ] A fresh `git clone` into a temp dir plus the README quickstart reproduces the offline scorecard
- [ ] Artifact URL recorded in docs/STATUS.md
- [ ] Video file at docs/demo/demo.mp4 (or the link if over 50 MB) recorded in STATUS

## Verification
- `git clone <repo> /tmp/x && cd /tmp/x && uv sync && uv run python main.py eval --offline` — exit 0

## Change surface
- README.md, docs/*, docs/demo/
- Conflict risk: low

## Out of scope
- Live numbers if ticket 19 hasn't run

## Completion evidence
- Fresh-clone transcript
- Artifact URL
- Video path
