import asyncio
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, AsyncMock

from shelfwatch.config import RunConfig, product_url
from shelfwatch.lease import MonitorBusy, MonitorLease
from shelfwatch.output import alerts_csv, checks_csv
from shelfwatch.product import currency_evidence, normalize_product
from shelfwatch.runner import run_pipeline
from shelfwatch.state import compare, compact_state, digest, product_key, validate_state, write_atomic
from shelfwatch.transport import FetchError, Page, PublicResolver, SafeHttpClient, public_ip, validate_url

URL = "https://shop.example.com/products/red-coat"
HTML = '<script>Shopify.currency = {"active":"USD","rate":"1.0"};</script>'


def source(price=1000, available=True, **changes):
    return {"id": 12, "title": "Red coat", "handle": "red-coat", "vendor": "Demo", "variants": [{"id": 31, "title": "Small", "sku": "RED-S", "price": price, "compare_at_price": None, "available": available}], **changes}


def row(price=1000, available=True, **changes):
    data = normalize_product(json.dumps(source(price, available)), URL, HTML)
    data.update({"productKey": product_key(URL), "productUrl": URL, "observedAt": "2026-10-16T00:00:00Z", **changes})
    return data


class InputTests(unittest.TestCase):
    def test_normalizes_deduplicates_and_supports_locale(self):
        config = RunConfig.from_dict({"productUrls": [URL + "/", URL]})
        self.assertEqual(config.product_urls, (URL,))
        self.assertEqual(product_url("https://shop.example.com/en-gb/products/red-coat/"), "https://shop.example.com/en-gb/products/red-coat")

    def test_rejects_unsupported_and_private_targets(self):
        for url in ["http://shop.example.com/products/x", URL + "?variant=3", "https://shop.example.com/collections/sale/products/x", "https://localhost/products/x", "https://127.0.0.1/products/x", "https://2130706433/products/x", "https://user:pass@shop.example.com/products/x", "https://shop.example.com:443/products/x", "https://shop.example.com/products/x.js", "https://shop.example.com/"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                RunConfig.from_dict({"productUrls": [url]})

    def test_rejects_typos_booleans_nan_and_malformed_fields(self):
        for extra in [{"maxProducts": True}, {"timeoutSeconds": 1}, {"minPriceChangePercent": float("nan")}, {"minPriceChangePercent": True}, {"monitorName": "Other Account"}, {"max_products": 2}, {"productUrls": "not-list"}]:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                RunConfig.from_dict({"productUrls": [URL], **extra})


class ProductTests(unittest.TestCase):
    def test_strict_units_and_250_variant_coverage_warning(self):
        data = source(12345)
        data["variants"] = [{**data["variants"][0], "id": i + 1} for i in range(250)]
        product = normalize_product(json.dumps(data), URL, HTML)
        self.assertEqual(product["variants"][0]["priceAmount"], "123.45")
        self.assertTrue(product["variantWindowMayBeTruncated"])
        self.assertEqual(product["currency"], "USD")
        self.assertEqual(product["inStockVariantCount"], 250)

    def test_refuses_partial_invalid_or_duplicate_variants(self):
        bad = source()
        for change in [{"price": True}, {"price": 1.5}, {"available": None}, {"compare_at_price": -1}, {"id": "bad"}, {"title": []}]:
            data = copy.deepcopy(bad)
            data["variants"].append({**data["variants"][0], "id": 32, **change})
            with self.subTest(change=change), self.assertRaises(FetchError):
                normalize_product(json.dumps(data), URL, HTML)
        with self.assertRaises(FetchError):
            normalize_product(json.dumps({**bad, "variants": bad["variants"] * 2}), URL, HTML)

    def test_refuses_handle_mismatch_html_response_and_lone_surrogate(self):
        for text in ["<h1>Challenge</h1>", json.dumps(source(handle="other")), json.dumps(source(title="bad\ud800title"))]:
            with self.assertRaises(FetchError):
                normalize_product(text, URL, HTML)

    def test_currency_evidence_unknown_and_conflicts(self):
        self.assertEqual(currency_evidence(HTML), ("USD", "html-shopify-currency-active"))
        self.assertEqual(currency_evidence('<script type="application/ld+json">{"offers":{"priceCurrency":"JPY"}}</script>'), ("JPY", "html-currency-markup"))
        self.assertEqual(currency_evidence('<meta itemprop="priceCurrency" content="EUR">')[0], "EUR")
        self.assertIsNone(currency_evidence(HTML + HTML.replace("USD", "EUR"))[0])
        self.assertIsNone(currency_evidence("<p>USD appears in ordinary text</p>")[0])


class ChangeTests(unittest.TestCase):
    def test_initial_not_a_launch_then_repeat_has_no_alert(self):
        first, state = compare(row(), None)
        self.assertEqual([c["type"] for c in first["changes"]], ["FIRST_OBSERVATION"])
        repeated, _ = compare(row(observedAt="later"), state)
        self.assertEqual(repeated["changes"], [])
        self.assertEqual(repeated["checkStatus"], "NO_ALERT")

    def test_variant_price_and_restock_transitions_have_stable_ids(self):
        before = compact_state(row(1000, False))
        after, state = compare(row(800, True), before)
        self.assertEqual({a["type"] for a in after["changes"]}, {"PRICE_DROP", "BACK_IN_STOCK"})
        again, _ = compare(row(800, True, observedAt="another check"), before)
        self.assertEqual([a["eventId"] for a in after["changes"]], [a["eventId"] for a in again["changes"]])
        self.assertEqual(next(c for c in after["changes"] if c["type"] == "PRICE_DROP")["percentChange"], 20)
        out, _ = compare(row(900, False), state)
        self.assertEqual({a["type"] for a in out["changes"]}, {"PRICE_RISE", "OUT_OF_STOCK"})

    def test_price_threshold_does_not_hide_stock_or_compare_at_change(self):
        before = compact_state(row(1000, False))
        current = row(990, True)
        current["variants"][0]["compareAtPriceRaw"] = 1100
        changed, _ = compare(current, before, 5)
        self.assertEqual({c["type"] for c in changed["changes"]}, {"BACK_IN_STOCK", "COMPARE_AT_PRICE_CHANGED"})

    def test_unknown_or_different_currency_never_emits_price_drop(self):
        for currency in [None, "EUR"]:
            changed, _ = compare(row(100, currency=currency), compact_state(row(1000)))
            self.assertNotIn("PRICE_DROP", {c["type"] for c in changed["changes"]})
        changed, _ = compare(row(100, currency=None), compact_state(row(1000, currency=None)))
        self.assertEqual(changed["changes"], [])

    def test_replacement_and_missing_variants_do_not_imply_removal(self):
        before = compact_state(row())
        before["variants"]["999"] = {"p": 100, "c": None, "a": True}
        changed, _ = compare(row(), before)
        self.assertEqual(changed["changes"], [])
        replacement, _ = compare(row(productId="99"), before)
        self.assertEqual([c["type"] for c in replacement["changes"]], ["PRODUCT_REPLACED"])

    def test_zero_price_does_not_divide_by_zero(self):
        changed, _ = compare(row(100), compact_state(row(0)), 99)
        self.assertIsNone(changed["changes"][0]["percentChange"])

    def test_state_rejects_wrong_url_version_and_bad_availability(self):
        good = compact_state(row())
        self.assertEqual(validate_state(good, URL), good)
        for bad in [{**good, "version": True}, {**good, "productUrl": "https://other.example/products/x"}, {**good, "variants": {"31": {"p": 10, "c": None, "a": "yes"}}}]:
            with self.assertRaises(ValueError):
                validate_state(bad, URL)


class ExportTests(unittest.TestCase):
    def test_csv_neutralizes_formula_payload(self):
        value = row(title="=HYPERLINK('evil')")
        self.assertIn("'=HYPERLINK", checks_csv([value]))
        value, _ = compare(value, None)
        self.assertIn("'=HYPERLINK", alerts_csv(value["changes"]))

    def test_atomic_write_failure_preserves_old_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            write_atomic(path, {"old": True})
            with patch("shelfwatch.state.os.replace", side_effect=OSError("disk error")), self.assertRaises(OSError):
                write_atomic(path, {"new": True})
            self.assertEqual(json.loads(path.read_text()), {"old": True})
            self.assertEqual(len(list(Path(directory).iterdir())), 1)


class FakeClient:
    def __init__(self, config):
        self.requests = 0
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass
    async def fetch(self, url, **kwargs):
        self.requests += 1
        return Page(url, json.dumps(source()) if url.endswith(".js") else HTML, 200, "application/json" if url.endswith(".js") else "text/html")


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_saved_only_state_and_unchanged_checks_are_still_results(self):
        state = {}
        async def load(key): return state.get(key)
        async def save(value, current):
            state[value["productKey"]] = current
            return True
        config = RunConfig.from_dict({"productUrls": [URL]})
        first = await run_pipeline(config, load, save, client_factory=FakeClient)
        second = await run_pipeline(config, load, save, client_factory=FakeClient)
        self.assertEqual(first["summary"]["alertCount"], 1)
        self.assertEqual(second["summary"]["savedChecks"], 1)
        self.assertEqual(second["summary"]["alertCount"], 0)
        self.assertEqual(second["results"][0]["checkStatus"], "NO_ALERT")

    async def test_rejected_save_failure_deadline_and_bad_state_do_not_advance(self):
        async def load(key): return None
        async def refuse(value, current): return False
        config = RunConfig.from_dict({"productUrls": [URL]})
        rejected = await run_pipeline(config, load, refuse, client_factory=FakeClient)
        self.assertEqual(rejected["results"], [])
        self.assertEqual(rejected["summary"]["stoppedReason"], "spending_limit")
        class Failed(FakeClient):
            async def fetch(self, *args, **kwargs): raise FetchError("blocked", "Denied", 403)
        failed = await run_pipeline(config, load, refuse, client_factory=Failed)
        self.assertEqual(failed["results"], [])
        self.assertEqual(failed["diagnostics"][0]["status"], "blocked")
        deadline = await run_pipeline(config, load, refuse, client_factory=FakeClient, deadline_seconds=0)
        self.assertEqual(deadline["summary"]["requests"], 0)
        async def invalid(key): return {"version": True}
        bad = await run_pipeline(config, invalid, refuse, client_factory=FakeClient)
        self.assertEqual(bad["summary"]["requests"], 0)

    async def test_robots_wildcards_and_deny_status(self):
        config = RunConfig.from_dict({"productUrls": [URL]})
        client = SafeHttpClient(config)
        async def robots(*args, **kwargs):
            return Page("https://shop.example.com/robots.txt", "User-agent: *\nDisallow: /products/*coat.js$\n", 200, "text/plain")
        client.fetch = robots
        self.assertFalse(await client.allowed(URL + ".js"))
        self.assertTrue(await client.allowed(URL))
        self.assertFalse(public_ip("127.0.0.1"))
        self.assertFalse(public_ip("::ffff:127.0.0.1"))

    async def test_product_page_json_content_negotiation_is_not_billed(self):
        class JsonPage(FakeClient):
            async def fetch(self, url, **kwargs):
                self.requests += 1
                return Page(url, json.dumps(source()), 200, "application/json")
        async def load(key): return None
        async def save(value, current): raise AssertionError("Non-HTML page must not be saved")
        result = await run_pipeline(RunConfig.from_dict({"productUrls": [URL]}), load, save, client_factory=JsonPage)
        self.assertEqual(result["results"], [])
        self.assertEqual(result["diagnostics"][0]["status"], "unsupported_storefront")

    async def test_private_dns_answer_is_rejected_even_when_other_answers_are_public(self):
        resolver = PublicResolver()
        resolver._resolver.resolve = AsyncMock(return_value=[{"host": "1.1.1.1"}, {"host": "127.0.0.1"}])
        with self.assertRaises(OSError):
            await resolver.resolve("shop.example.com")
        await resolver.close()

    async def test_robots_failures_preserve_cause_and_deny_access(self):
        config = RunConfig.from_dict({"productUrls": [URL]})
        for status, http_status in [("timeout", None), ("http_error", 503)]:
            client = SafeHttpClient(config)
            async def fail(*args, **kwargs):
                raise FetchError(status, "Failed", http_status)
            client.fetch = fail
            with self.assertRaises(FetchError) as caught:
                await client.allowed(URL)
            self.assertIn(status, str(caught.exception))
            self.assertEqual(caught.exception.http_status, http_status)
        client = SafeHttpClient(config)
        async def denied(*args, **kwargs): raise FetchError("blocked", "Denied", 403)
        client.fetch = denied
        self.assertFalse(await client.allowed(URL))


class LockTests(unittest.IsolatedAsyncioTestCase):
    async def test_busy_lock_is_not_released_or_used(self):
        class Busy:
            async def add_request(self, request): return {"requestId": "singleton"}
            async def list_and_lock_head(self, **kwargs): return {"items": []}
            async def delete_request_lock(self, request_id): raise AssertionError("Not our lock")
        lease = MonitorLease(Busy())
        with self.assertRaises(MonitorBusy): await lease.acquire()
        await lease.release()

    async def test_owned_lock_renew_and_release(self):
        calls = []
        class Available:
            async def add_request(self, request): return {"requestId": "singleton"}
            async def list_and_lock_head(self, **kwargs): return {"items": [{"id": "singleton"}]}
            async def prolong_request_lock(self, request_id, **kwargs): calls.append(("renew", request_id))
            async def delete_request_lock(self, request_id): calls.append(("release", request_id))
        lease = MonitorLease(Available())
        await lease.acquire()
        await lease.renew()
        await lease.release()
        self.assertEqual(calls, [("renew", "singleton"), ("release", "singleton")])
