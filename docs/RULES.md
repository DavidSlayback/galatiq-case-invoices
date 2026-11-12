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
| `UNSUPPORTED_CURRENCY` | hard | No mock exchange rate for the currency | Can't price-check or tier it | — |
| `PRICE_OVER_CATALOG` | soft | A unit price in USD is more than 5% above catalog | Overbilling (D6) | 1010 (rush line) |
| `NEAR_THRESHOLD` | soft | 9,500 ≤ USD total < 10,000 | Threshold-gaming signal (D27) | 1008, 1012 |
| `DUE_BEFORE_INVOICE` | soft | Due date is on or before the invoice date | Inconsistent terms | 1002 |
| `DUE_TERMS_MISMATCH` | soft | Due date is more than ±1 day from invoice date + Net N | Vendors count terms inclusively; ±1 is tolerated (D26) | 1001, 1002 |
| `PAST_DUE` | soft | Due date is before the processing date (`--as-of`, default 2026-02-01) | Late-payment exposure (D8) | 1008 |
| `DATE_UNPARSEABLE` | soft | The due date is text such as "yesterday" | Never guess a date | 1003 |
| `UNKNOWN_VENDOR` | soft | The vendor is not in the registry | New payees need a look (D27) | 1003, 1005, 1008, 1012 |
| `URGENCY_LANGUAGE` | soft | "urgent", "immediately", "wire transfer", … in notes or terms | Social-engineering pattern | 1003 |
| `UNKNOWN_VENDOR_PRESSURE` | fraud | Unknown vendor **and** urgency language | D10 fraud signal | 1003 |
| `SUSPICIOUS_ADDRESS` | fraud | The address is on the implausible-address list (e.g. 1600 Pennsylvania Ave) | Fake supplier | 1005 |
| `FOREIGN_CURRENCY` | note | Non-USD, converted at the mock rate (EUR 1.08) | Transparency (D5) | 1014 |
| `DISCOUNT_APPLIED` | note | A unit price in USD is below catalog | Discounts are fine (D6) | 1013, 1014 |
