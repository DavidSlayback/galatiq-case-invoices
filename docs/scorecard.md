# Eval scorecard

Model: `offline`. 27/27 pass, 0 pending, 0 failing.
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
