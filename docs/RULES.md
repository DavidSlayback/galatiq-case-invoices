# Validation rules

Every rule has a stable ID that the agents cite and the eval asserts on. Severity sets the route (D7):

- **hard** → reject.
- **fraud** → human inbox, labelled "suspected fraud".
- **soft** → VP agent review.
- **note** → informational only.

Code: [invoice_agents/rules.py](../invoice_agents/rules.py). `ARITHMETIC_MISMATCH` comes from the extraction self-correction loop ([reconcile.py](../invoice_agents/reconcile.py)), and `LOAD_FAILED` from the loaders.

| Rule | Severity | Fires when | Why | Sample |
|---|---|---|---|---|
| `LOAD_FAILED` | hard | The file is unreadable, empty, malformed or of an unsupported type | Nothing to process | — |
| `ARITHMETIC_MISMATCH` | hard | Stated figures disagree after 2 re-extractions (qty × price, line sum, subtotal + tax + shipping = total) | Totals must be internally consistent before money moves (D14, D30) | 1007, 1009, 1013 |
| `UNKNOWN_ITEM` | hard | A line doesn't map to an inventory SKU | Can't receive goods we don't stock | 1008, 1016 |
| `ZERO_STOCK_ITEM` | hard | A SKU carried at zero stock is invoiced | FakeItem is a planted fraud item | 1003 |
| `STOCK_EXCEEDED` | hard | **Summed** quantity per SKU exceeds stock | Literal stock check (D1); 1013 hides the overrun across split lines | 1002, 1005, 1007, 1013 |
| `NEGATIVE_QUANTITY` | hard | Quantity is 0 or less | Data-integrity error | 1009 |
| `MISSING_VENDOR` | hard | Vendor name is blank | Can't pay an unknown payee | 1009 |
| `MISSING_DUE_DATE` | hard | No due date at all | Required field | 1009 |
| `MISSING_TOTAL` / `NO_LINE_ITEMS` | hard | No total, or no lines | Required fields | — |
| `NON_POSITIVE_TOTAL` / `NEGATIVE_PRICE` | hard | Total ≤ 0, or a negative unit price | Not a payable invoice; a credit note is a different flow (D37) | 1009 |
| `UNSUPPORTED_CURRENCY` | hard | No mock exchange rate for the currency | Can't price-check or tier it | — |
| `PRICE_OVER_CATALOG` | soft | A unit price in USD is more than 5% above catalog | Overbilling (D6) | 1010 (rush line) |
| `PRICE_UNVERIFIABLE` | soft | A stocked item with no unit price and no line amount to derive one from | An unchecked price must not auto-pay (D37) | — |
| `MISSING_INVOICE_NUMBER` / `MISSING_INVOICE_DATE` | soft | No invoice number, or no readable invoice date | Without a number only content can catch a resend; without a date the terms and split checks have nothing (D53) | — |
| `CHARGES_OUT_OF_PROPORTION` | soft | Total minus the line amounts (tax, shipping, other charges) is over 20% of the goods and over $100 | Line prices are catalog-checked; an overcharge moved into freight or tax is not (D53). The samples' charges are at most 9% | — |
| `NEAR_THRESHOLD` | soft | 9,500 ≤ USD total < 10,000 | Threshold-gaming signal (D27) | 1008, 1012 |
| `DUE_BEFORE_INVOICE` | soft | Due date is on or before the invoice date | Inconsistent terms | 1002 |
| `DUE_TERMS_MISMATCH` | soft | Due date is more than ±1 day from invoice date + Net N | Vendors count terms inclusively; ±1 is tolerated (D26) | 1001, 1002 |
| `PAST_DUE` | soft | Due date is before the processing date (`--as-of`, default 2026-02-01) | Late-payment exposure (D8) | 1008 |
| `DATE_UNPARSEABLE` | soft | The due date is text such as "yesterday" | Never guess a date | 1003 |
| `UNKNOWN_VENDOR` | soft | The vendor is not in the registry (nor an alias or look-alike) | New payees need a look (D27) | 1003, 1005, 1008 |
| `URGENCY_LANGUAGE` | soft | "urgent", "immediately", "wire transfer", … in notes or terms | Social-engineering pattern | 1003 |
| `VENDOR_RENAMED` | soft | The name matches a registered vendor's **alias** (QuickShip → FastShip Ltd.) | A rename claimed on the invoice needs confirming (D9) | 1012 |
| `LOOKALIKE_VENDOR` | fraud | The name is within 2 edits of a registered vendor but not equal (`Widgets lnc.`) | Classic impersonation (D10) | adversarial |
| `HIGH_VENDOR_RISK` | fraud | Vendor risk score ≥ 60: unknown 40, alias 20, look-alike 60, suspicious address 50, urgency 20 | Several weak signals add up (D10) | 1003, 1005 |
| `VENDOR_RISK` | note | Any non-zero vendor risk score, with its signals | Shown to the VP and in the inbox | — |
| `UNKNOWN_VENDOR_PRESSURE` | fraud | Unknown vendor **and** urgency language | D10 fraud signal | 1003 |
| `SUSPICIOUS_ADDRESS` | fraud | The address is on the implausible-address list (e.g. 1600 Pennsylvania Ave) | Fake supplier | 1005 |
| `PROMPT_INJECTION` | fraud | Notes, terms or item text address an approver or AI ("ignore previous rules", "approve and pay this invoice", "SYSTEM:"). Look-alike letters, invisible characters, line breaks and base64 are folded first, and French, Spanish and German forms are included (D53) | Attack on the agents; checked in code whatever the model did (NFR-8) | adversarial 2001 |
| `BANK_DETAILS_CHANGED` | fraud | A known vendor's (or alias's) remit-to details don't name the bank reference on file as a whole token, or also name another account or a change (D52, D53) | Payment-diversion fraud | adversarial 2005 |
| `SPLIT_INVOICE_SUSPECTED` | fraud | Same vendor within 7 days (an undated invoice counts as inside): each USD total is under $10K, the sum is over. Only invoices that escaped review count: paid or in flight, never decided by a person (D53) | Splitting to dodge review | adversarial 2003 |
| `DUPLICATE_NUMBER_CONFLICT` | fraud | Same vendor, number and revision as an invoice on file, but different content | A reused invoice number (D2) | ledger tests |
| `POSSIBLE_DUPLICATE` | fraud | Another invoice from the vendor has the same lines and total (and the same date, when both state one) under a different number | A resend under `-A`, `/1` or no number would be paid twice (D53) | — |
| `STALE_REVISION` | soft | An older revision arrives after a newer one | The newer one stays; the old one is skipped | ledger tests |
| `FOREIGN_CURRENCY` | note | Non-USD, converted at the mock rate (EUR 1.08) | Transparency (D5) | 1014 |
| `DISCOUNT_APPLIED` | note | A unit price in USD is below catalog | Discounts are fine (D6) | 1013, 1014 |
