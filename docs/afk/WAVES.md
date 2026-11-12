# Waves, lanes, integration order

| Wave | Tickets (lane) | Conflict notes |
|---|---|---|
| 0 | 01 (serial-required) | greenfield |
| 1 | 02 (serial-required) | freezes models and schema; everything imports them |
| 2 | 03 (serial-required) | creates graph.py, the hub |
| 3 | 04 (loaders) · 06 (rules) · 07 (approval) · 08 (payment) | Only 07 may edit graph.py (the VP branch). 04, 06 and 08 own separate modules behind the 03 seams. Parallel-safe. |
| 4 | 05 (serial-required) | the goldens become the eval truth |
| 5 | 09 (serial-required) · 15 (ocr) · 17 (models) | 15 touches only pdf_loader.py and new files; 17 touches only the model factory and settings; all parallel-safe with 09 |
| 6 | 10 (ledger) · 13 (vendors) | Both edit `eval/expected_outcomes.yaml`; 10 also edits graph.py and 13 registers in rules.py. Behaviour is independent, so they run in parallel and merge 10 first. |
| 7 | 11 (inbox) · 14 (adversarial) | 14 edits rules.py and the yaml after 13; 11 touches inbox and cli |
| 8 | 12 (serial-required) · 18 (serial-required) | 18 uses subscription quota (D31); stops on a rate limit |
| 9 | 16 (serial-required) | |
| 10 | 19 (serial-required) | the README and presentation consume everything |

**Integration order (stacked PRs):** 01, 02, 03, 04, 06, 08, 07, 05, 09, 15, 17, 10, 13, 11, 14, 12, 18, 16, 19. Wave 3 merges 07 last because it is the only one touching graph.py. Wave 6 merges 10 before 13 because of the yaml.

**Critical path:** 01→02→03→04→05→09→10→11→12→16→19 (11 tickets). Fillers off the critical path: 06, 07, 08 (wave 3), 15 and 17 (wave 5), 13 and 14 (waves 6–7), 18 (wave 8).
