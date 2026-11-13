# Tool calls in the 2026-11-13 live runs

Every VP and critic turn from the final live runs, with the tools it called (from `runs/eval/*.jsonl`, which are not committed). See [README.md](README.md).

## Claude Haiku

| Invoice | Turn | Round | Tools called |
|---|---|---|---|
| invoice_1001.txt | VP | 0 | none |
| invoice_1001.txt | critic | 0 | `vendor_history()` |
| invoice_1010.txt | VP | 0 | `vendor_history()` |
| invoice_1010.txt | VP | 1 | none |
| invoice_1010.txt | critic | 0 | `vendor_history()`, `catalog_item(sku=WidgetA)` |
| invoice_1010.txt | critic | 1 | `vendor_history()`, `catalog_item(sku=WidgetA)`, `catalog_item(sku=WidgetB)` |

## Grok 4.7 via Cursor

| Invoice | Turn | Round | Tools called |
|---|---|---|---|
| invoice_1001.txt | VP | 0 | none |
| invoice_1001.txt | critic | 0 | none |
| invoice_1010.txt | VP | 0 | `catalog_item(sku=WidgetA)` |
| invoice_1010.txt | critic | 0 | `catalog_item(sku=WidgetA)` |
