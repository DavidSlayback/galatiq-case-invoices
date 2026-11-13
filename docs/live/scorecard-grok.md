# Eval scorecard

Model: `cli:cursor:grok-4.7-medium-fast`. 27/27 pass, 0 pending, 0 failing.
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
| invoice_1009.json | PASS | rejected | rejected | rules | ARITHMETIC_MISMATCH, MISSING_DUE_DATE, MISSING_VENDOR, NEGATIVE_QUANTITY, NON_POSITIVE_TOTAL |
| invoice_1010.txt | PASS | paid | paid | vp_agent | PRICE_OVER_CATALOG |
| invoice_1011.pdf | PASS | paid | paid | rules | - |
| invoice_1011.txt | PASS | duplicate_skipped | duplicate_skipped | ledger | - |
| invoice_1012.pdf | PASS | escalated | escalated | approval | NEAR_THRESHOLD, VENDOR_RENAMED, VENDOR_RISK |
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

Total: 42 model calls, 593,856 tokens, 10.6 minutes.

| File | Calls | Tokens | Seconds | Extraction differences |
|---|---|---|---|---|
| invoice_1001.txt | 3 | 41,281 | 47 | none |
| invoice_1002.txt | 1 | 12,032 | 15 | none |
| invoice_1003.txt | 1 | 11,992 | 9 | none |
| invoice_1004.json | 1 | 13,307 | 19 | none |
| invoice_1004_revised.json | 1 | 12,573 | 16 | none |
| invoice_1005.json | 1 | 13,077 | 14 | none |
| invoice_1006.csv | 1 | 16,632 | 9 | none |
| invoice_1007.csv | 3 | 44,338 | 48 | none |
| invoice_1008.txt | 2 | 35,070 | 80 | none |
| invoice_1009.json | 3 | 45,911 | 52 | none |
| invoice_1010.txt | 5 | 71,967 | 82 | none |
| invoice_1011.pdf | 1 | 11,205 | 7 | none |
| invoice_1011.txt | 1 | 16,328 | 8 | none |
| invoice_1012.pdf | 1 | 12,385 | 16 | none |
| invoice_1012.txt | 1 | 18,544 | 16 | none |
| invoice_1013.json | 3 | 43,174 | 47 | none |
| invoice_1013.pdf | 3 | 39,796 | 42 | none |
| invoice_1014.xml | 1 | 12,392 | 12 | none |
| invoice_1015.csv | 1 | 11,989 | 9 | none |
| invoice_1016.json | 1 | 12,638 | 15 | none |
| invoice_1011_scan.pdf | 1 | 12,332 | 13 | none |
| invoice_2001_injection.txt | 1 | 11,302 | 15 | none |
| invoice_2002_split_a.txt | 1 | 17,293 | 9 | none |
| invoice_2003_split_b.txt | 1 | 16,211 | 8 | none |
| invoice_2004_lookalike.txt | 1 | 11,244 | 8 | none |
| invoice_2005_bank_change.txt | 1 | 17,473 | 9 | none |
| invoice_2006_control.txt | 1 | 11,370 | 8 | none |
