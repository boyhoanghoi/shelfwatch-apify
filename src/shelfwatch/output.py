import csv
import io
import json
from pathlib import Path


def safe_cell(value):
    text = "" if value is None else str(value)
    if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        text = "'" + text
    return text


def csv_text(rows, fields):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: safe_cell(row.get(field)) for field in fields})
    return stream.getvalue()


def checks_csv(rows):
    return csv_text(rows, ["productUrl", "title", "vendor", "currency", "currencySource", "minPriceAmount", "maxPriceAmount", "available", "variantCount", "inStockVariantCount", "checkStatus", "changeCount", "priceComparisonStatus", "previousObservedAt", "observedAt", "sourceUrl"])


def alerts_csv(alerts):
    return csv_text(alerts, ["eventId", "type", "productUrl", "title", "variantId", "currency", "previousPriceAmount", "currentPriceAmount", "percentChange", "previousObservedAt", "observedAt"])


def alerts_ndjson(alerts):
    return "".join(json.dumps(alert, ensure_ascii=False, allow_nan=False) + "\n" for alert in alerts)


def digest_markdown(report):
    summary = report["summary"]
    lines = ["# ShelfWatch — watchlist check", "", f"{summary['savedChecks']} saved product checks; {summary['alertCount']} change observations; {summary['failedProducts']} failed products.", "", "Counts describe this saved watchlist sample. FIRST_OBSERVATION is a baseline, not a newly launched product. Availability means purchasable in the fetched storefront, not units in stock.", "", "## Observed changes", ""]
    for alert in report["alerts"]:
        # Public text is rendered as literal text, not injected Markdown/HTML.
        title = alert["title"].replace("\n", " ").replace("\r", " ")
        title = "".join(char for char in title if char not in "<>[]`*_\\")
        lines.append(f"- {alert['type']}: {title[:160]} — variant {alert.get('variantId') or 'product'}")
    if not report["alerts"]:
        lines.append("No matching change observations in saved checks.")
    lines.extend(["", "See dataset rows for source URLs, raw prices, variants and embedded change events. Every saved successful check is billable, including unchanged checks.", ""])
    return "\n".join(lines)


def export_results(report, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, value in [("results.json", report["results"]), ("alerts.json", report["alerts"]), ("summary.json", report["summary"]), ("diagnostics.json", report["diagnostics"])]:
        (directory / name).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    for name, text in [("checks.csv", checks_csv(report["results"])), ("alerts.csv", alerts_csv(report["alerts"])), ("alerts.ndjson", alerts_ndjson(report["alerts"])), ("digest.md", digest_markdown(report))]:
        (directory / name).write_text(text, encoding="utf-8")
