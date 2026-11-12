# Eval scorecard

Model: `cli:cursor:grok-4.7-medium-fast`. 26/27 pass, 0 pending, 1 failing.
Expectations: [eval/expected_outcomes.yaml](../eval/expected_outcomes.yaml).

| File | Result | Expected | Actual | Decided by | Rules fired |
|---|---|---|---|---|---|
| invoice_1001.txt | PASS | paid | paid | vp_agent | DUE_TERMS_MISMATCH |
| invoice_1002.txt | PASS | rejected | rejected | rules | DUE_BEFORE_INVOICE, DUE_TERMS_MISMATCH, PAST_DUE, STOCK_EXCEEDED |
| invoice_1003.txt | PASS | rejected | rejected | rules | DATE_UNPARSEABLE, HIGH_VENDOR_RISK, UNKNOWN_VENDOR, UNKNOWN_VENDOR_PRESSURE, URGENCY_LANGUAGE, VENDOR_RISK, ZERO_STOCK_ITEM |
| invoice_1004.json | PASS | paid | paid | rules | - |
| invoice_1004_revised.json | PASS | escalated | escalated | approval | - |
| invoice_1005.json | PASS | rejected | rejected | rules | HIGH_VENDOR_RISK, STOCK_EXCEEDED, SUSPICIOUS_ADDRESS, UNKNOWN_VENDOR, VENDOR_RISK |
| invoice_1006.csv | PASS | paid | paid | rules | - |
| invoice_1007.csv | PASS | rejected | rejected | rules | ARITHMETIC_MISMATCH, STOCK_EXCEEDED |
| invoice_1008.txt | PASS | rejected | rejected | rules | NEAR_THRESHOLD, PAST_DUE, UNKNOWN_ITEM, UNKNOWN_VENDOR, VENDOR_RISK |
| invoice_1009.json | PASS | rejected | rejected | rules | ARITHMETIC_MISMATCH, MISSING_DUE_DATE, MISSING_VENDOR, NEGATIVE_QUANTITY |
| invoice_1010.txt | PASS | paid | paid | vp_agent | PRICE_OVER_CATALOG |
| invoice_1011.pdf | PASS | paid | paid | rules | - |
| invoice_1011.txt | PASS | duplicate_skipped | duplicate_skipped | ledger | - |
| invoice_1012.pdf | FAIL | escalated | paid | vp_agent | NEAR_THRESHOLD, VENDOR_RENAMED, VENDOR_RISK |
| invoice_1012.txt | PASS | duplicate_skipped | duplicate_skipped | ledger | - |
| invoice_1013.json | PASS | rejected | rejected | rules | ARITHMETIC_MISMATCH, DISCOUNT_APPLIED, STOCK_EXCEEDED |
| invoice_1013.pdf | PASS | duplicate_skipped | duplicate_skipped | ledger | ARITHMETIC_MISMATCH |
| invoice_1014.xml | PASS | paid | paid | rules | DISCOUNT_APPLIED, FOREIGN_CURRENCY |
| invoice_1015.csv | PASS | paid | paid | rules | - |
| invoice_1016.json | PASS | rejected | rejected | rules | UNKNOWN_ITEM |
| invoice_1011_scan.pdf | PASS | duplicate_skipped | duplicate_skipped | ledger | - |
| invoice_2001_injection.txt | PASS | escalated | escalated | approval | PROMPT_INJECTION |
| invoice_2002_split_a.txt | PASS | paid | paid | rules | - |
| invoice_2003_split_b.txt | PASS | escalated | escalated | approval | SPLIT_INVOICE_SUSPECTED |
| invoice_2004_lookalike.txt | PASS | escalated | escalated | approval | HIGH_VENDOR_RISK, LOOKALIKE_VENDOR, VENDOR_RISK |
| invoice_2005_bank_change.txt | PASS | escalated | escalated | approval | BANK_DETAILS_CHANGED |
| invoice_2006_control.txt | PASS | paid | paid | rules | - |

## Live model usage and extraction differences from the goldens

Total: 42 model calls, 573,905 tokens, 11.7 minutes.

| File | Calls | Tokens | Seconds | Extraction differences |
|---|---|---|---|---|
| invoice_1001.txt | 3 | 40,267 | 33 | none |
| invoice_1002.txt | 1 | 11,671 | 11 | none |
| invoice_1003.txt | 1 | 11,270 | 9 | none |
| invoice_1004.json | 1 | 12,808 | 19 | none |
| invoice_1004_revised.json | 1 | 12,689 | 17 | none |
| invoice_1005.json | 1 | 13,095 | 21 | none |
| invoice_1006.csv | 1 | 11,824 | 11 | none |
| invoice_1007.csv | 3 | 44,730 | 62 | none |
| invoice_1008.txt | 2 | 27,516 | 70 | none |
| invoice_1009.json | 3 | 39,829 | 58 | none |
| invoice_1010.txt | 3 | 47,296 | 72 | none |
| invoice_1011.pdf | 1 | 11,267 | 9 | none |
| invoice_1011.txt | 1 | 11,455 | 10 | none |
| invoice_1012.pdf | 3 | 36,375 | 52 | none |
| invoice_1012.txt | 1 | 11,948 | 11 | none |
| invoice_1013.json | 3 | 44,034 | 69 | none |
| invoice_1013.pdf | 3 | 46,940 | 57 | none |
| invoice_1014.xml | 1 | 12,370 | 16 | none |
| invoice_1015.csv | 1 | 11,833 | 10 | none |
| invoice_1016.json | 1 | 18,832 | 14 | none |
| invoice_1011_scan.pdf | 1 | 27,850 | 9 | none |
| invoice_2001_injection.txt | 1 | 11,382 | 9 | none |
| invoice_2002_split_a.txt | 1 | 11,276 | 9 | none |
| invoice_2003_split_b.txt | 1 | 11,251 | 9 | none |
| invoice_2004_lookalike.txt | 1 | 11,266 | 9 | none |
| invoice_2005_bank_change.txt | 1 | 11,649 | 13 | none |
| invoice_2006_control.txt | 1 | 11,182 | 11 | none |
