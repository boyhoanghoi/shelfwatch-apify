"""Strict Shopify Ajax data normalization; public HTML supplies currency evidence."""
from html.parser import HTMLParser
import json
import re
from urllib.parse import urlsplit

from .transport import FetchError


class CurrencyParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_script = False
        self.scripts = []
        self.buffer = []
        self.meta = set()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "script":
            self.in_script = True
            self.buffer = []
        if tag == "meta" and (values.get("property") or values.get("itemprop")) in ("product:price:currency", "priceCurrency", "og:price:currency"):
            self.meta.add(values.get("content", ""))

    def handle_data(self, data):
        if self.in_script:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.in_script:
            self.scripts.append("".join(self.buffer))
            self.in_script = False


def currency_evidence(html):
    parser = CurrencyParser()
    parser.feed(html)
    active = set()
    structured = set(parser.meta)
    for script in parser.scripts:
        active.update(re.findall(r'''Shopify\.currency\s*=\s*\{\s*["']active["']\s*:\s*["']([A-Z]{3})["']''', script))
        active.update(re.findall(r'''Shopify\.currency\.active\s*=\s*["']([A-Z]{3})["']''', script))
        # No execution of scripts; only JSON-LD currency literals are considered.
        if script.lstrip().startswith(("{", "[")):
            try:
                value = json.loads(script)
            except (ValueError, RecursionError):
                continue
            stack, visited = [value], 0
            while stack and visited < 10000:
                item = stack.pop()
                visited += 1
                if isinstance(item, dict):
                    if isinstance(item.get("priceCurrency"), str):
                        structured.add(item["priceCurrency"])
                    stack.extend(item.values())
                elif isinstance(item, list):
                    stack.extend(item)
    active = {code for code in active if re.fullmatch(r"[A-Z]{3}", code)}
    structured = {code for code in structured if re.fullmatch(r"[A-Z]{3}", code)}
    if len(active) == 1:
        return next(iter(active)), "html-shopify-currency-active"
    if not active and len(structured) == 1:
        return next(iter(structured)), "html-currency-markup"
    return None, "unavailable-or-conflicting"


def _id(value):
    if (type(value) is int and value > 0) or (isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,30}", value)):
        return str(value)
    raise ValueError("Invalid product/variant identifier.")


def normalize_product(text: str, product_url: str, html: str) -> dict:
    try:
        data = json.loads(text)
        if not isinstance(data, dict) or not isinstance(data.get("title"), str) or not data["title"].strip():
            raise ValueError("Missing product title.")
        expected = urlsplit(product_url).path.split("/")[-1]
        if data.get("handle") != expected:
            raise ValueError("Product handle does not match the fetched product page.")
        variants = data.get("variants")
        if not isinstance(variants, list) or not 1 <= len(variants) <= 250:
            raise ValueError("Expected 1–250 public variants.")
        items = []
        seen = set()
        for variant in variants:
            if not isinstance(variant, dict):
                raise ValueError("Malformed variant.")
            variant_id = _id(variant.get("id"))
            if variant_id in seen:
                raise ValueError("Duplicate variant identifier.")
            seen.add(variant_id)
            price, compare = variant.get("price"), variant.get("compare_at_price")
            if type(price) is not int or not 0 <= price <= 10**14:
                raise ValueError("Expected a nonnegative integer Shopify Ajax price.")
            if compare is not None and (type(compare) is not int or not 0 <= compare <= 10**14):
                raise ValueError("Invalid compare-at price.")
            if type(variant.get("available")) is not bool:
                raise ValueError("Variant availability is unknown.")
            title, sku = variant.get("title", ""), variant.get("sku")
            if not isinstance(title, str) or (sku is not None and not isinstance(sku, str)):
                raise ValueError("Malformed variant metadata.")
            items.append({"variantId": variant_id, "variantTitle": title[:500], "sku": (sku or "")[:300],
                          "priceRaw": price, "priceAmount": f"{price // 100}.{price % 100:02}",
                          "compareAtPriceRaw": compare, "available": variant["available"]})
        currency, source = currency_evidence(html)
        result = {"productId": _id(data.get("id")), "title": data["title"][:1000],
                  "vendor": data.get("vendor")[:300] if isinstance(data.get("vendor"), str) else "",
                  "currency": currency, "currencySource": source, "currencyEvidenceUrl": product_url,
                  "priceUnitScale": 100, "variants": sorted(items, key=lambda item: item["variantId"]),
                  "variantCount": len(items), "variantWindowMayBeTruncated": len(items) == 250,
                  "inStockVariantCount": sum(item["available"] for item in items),
                  "available": any(item["available"] for item in items),
                  "minPriceAmount": f"{min(item['priceRaw'] for item in items) / 100:.2f}",
                  "maxPriceAmount": f"{max(item['priceRaw'] for item in items) / 100:.2f}"}
        json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return result
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise FetchError("invalid_product", f"Public Shopify product data could not be validated: {exc}") from None
