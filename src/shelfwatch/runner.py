import asyncio
from collections import Counter
from datetime import datetime, timezone
import time

from .config import product_url
from .product import normalize_product
from .state import compare, product_key, validate_state
from .transport import FetchError, SafeHttpClient


async def run_pipeline(config, load, save, *, client_factory=SafeHttpClient, deadline_seconds=240):
    """save must persist the paid row before promoting its baseline; failures stop the run."""
    started = time.monotonic()
    rows, diagnostics = [], []
    stopped = None
    selected = config.product_urls[:config.max_products]
    async with client_factory(config) as client:
        for url in selected:
            if time.monotonic() - started >= deadline_seconds:
                stopped = "run_deadline"
                break
            try:
                old = validate_state(await load(product_key(url)), url)
            except ValueError as exc:
                diagnostics.append({"productUrl": url, "status": "invalid_baseline", "message": str(exc)})
                continue
            try:
                async def fetch_product():
                    page = await client.fetch(url, scope_url=url)
                    if page.content_type and not any(kind in page.content_type for kind in ("text/html", "application/xhtml+xml")):
                        raise FetchError("unsupported_storefront", "Product page did not return HTML; currency context cannot be observed reliably.", page.status)
                    final_url = product_url(page.url)
                    source_url = final_url + ".js"
                    source = await client.fetch(source_url, scope_url=final_url)
                    data = normalize_product(source.text, final_url, page.text)
                    # State identity is the original normalized watch URL. Redirect evidence is retained.
                    data.update({"productKey": product_key(url), "productUrl": url,
                                 "finalProductUrl": final_url, "sourceUrl": source.url,
                                 "observedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")})
                    return data
                remaining = max(0.01, deadline_seconds - (time.monotonic() - started))
                row = await asyncio.wait_for(fetch_product(), timeout=remaining)
            except (FetchError, ValueError) as exc:
                diagnostics.append({"productUrl": url, "status": getattr(exc, "status", "unsupported_redirect"),
                                    "httpStatus": getattr(exc, "http_status", None), "message": str(exc)})
                continue
            except asyncio.TimeoutError:
                stopped = "run_deadline"
                diagnostics.append({"productUrl": url, "status": "run_deadline", "message": "Bounded run deadline reached; prior baseline preserved."})
                break
            row, state = compare(row, old, config.min_price_change_percent)
            if not await save(row, state):
                stopped = "spending_limit"
                break
            rows.append(row)
        requests = client.requests
    return report_for(rows, diagnostics, config, requests, started, stopped)


def report_for(rows, diagnostics, config, requests, started, stopped=None):
    alerts = [change for row in rows for change in row["changes"]]
    product_failures = sum("productUrl" in diagnostic for diagnostic in diagnostics)
    summary = {"inputProducts": len(config.product_urls), "selectedProducts": min(config.max_products, len(config.product_urls)),
               "savedChecks": len(rows), "failedProducts": product_failures,
               "unprocessedProducts": max(0, len(config.product_urls) - len(rows) - product_failures),
               "productsWithAlerts": sum(row["isChanged"] for row in rows), "alertCount": len(alerts),
               "alertsByType": dict(Counter(change["type"] for change in alerts)), "requests": requests,
               "monitorName": config.monitor_name, "stoppedReason": stopped, "durationSeconds": round(time.monotonic() - started, 3),
               "note": "Every saved successful check is billable, including NO_ALERT. Failures have no check event. Availability is storefront buyability, not an inventory count; no removal is inferred."}
    return {"results": rows, "alerts": alerts, "diagnostics": diagnostics, "summary": summary}
