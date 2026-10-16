import hashlib
import json
import os
from pathlib import Path
import tempfile

MAX_STATE_BYTES = 8 * 1024 * 1024


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def product_key(url):
    return "P-" + hashlib.sha256(url.encode("utf-8")).hexdigest()


def compact_state(row):
    return {"version": 1, "productKey": row["productKey"], "productUrl": row["productUrl"],
            "productId": row["productId"], "currency": row["currency"],
            "variants": {v["variantId"]: {"p": v["priceRaw"], "c": v["compareAtPriceRaw"], "a": v["available"]} for v in row["variants"]},
            "lastSavedAt": row["observedAt"]}


def validate_state(value, url):
    if value is None:
        return None
    try:
        if not isinstance(value, dict) or type(value.get("version")) is not int or value["version"] != 1:
            raise ValueError()
        if value["productKey"] != product_key(url) or value["productUrl"] != url:
            raise ValueError()
        if not isinstance(value["productId"], str) or not value["productId"].isdigit():
            raise ValueError()
        currency = value["currency"]
        if currency is not None and (not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha() or not currency.isupper()):
            raise ValueError()
        variants = value["variants"]
        if not isinstance(variants, dict) or not 1 <= len(variants) <= 250:
            raise ValueError()
        if not isinstance(value["lastSavedAt"], str) or len(value["lastSavedAt"]) > 60:
            raise ValueError()
        for key, variant in variants.items():
            if not isinstance(key, str) or not key.isdigit() or not isinstance(variant, dict) or set(variant) != {"p", "c", "a"}:
                raise ValueError()
            if type(variant["p"]) is not int or not 0 <= variant["p"] <= 10**14 or type(variant["a"]) is not bool:
                raise ValueError()
            if variant["c"] is not None and (type(variant["c"]) is not int or not 0 <= variant["c"] <= 10**14):
                raise ValueError()
        canonical(value).encode("utf-8")
        return value
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise ValueError("Saved baseline is malformed or incompatible. Use a new monitorName to start a separate baseline; existing state was not overwritten.") from None


def compare(row, previous, min_percent=0):
    current = compact_state(row)
    changes = []
    before = {k: v for k, v in (previous or {}).items() if k != "lastSavedAt"}
    after = {k: v for k, v in current.items() if k != "lastSavedAt"}
    transition = digest({"before": before, "after": after})

    def add(kind, variant=None, **details):
        changes.append({"eventId": digest([row["productKey"], transition, kind, variant]),
                        "type": kind, "variantId": variant, "productKey": row["productKey"],
                        "productUrl": row["productUrl"], "title": row["title"], "currency": row["currency"],
                        "previousObservedAt": previous.get("lastSavedAt") if previous else None,
                        "observedAt": row["observedAt"], **details})

    if previous is None:
        add("FIRST_OBSERVATION")
    elif previous["productId"] != row["productId"]:
        add("PRODUCT_REPLACED")
    else:
        same_currency = row["currency"] is not None and row["currency"] == previous["currency"]
        if row["currency"] != previous["currency"]:
            add("CURRENCY_CONTEXT_CHANGED", previousCurrency=previous["currency"])
        for variant_id, value in current["variants"].items():
            old = previous["variants"].get(variant_id)
            if old is None:
                add("VARIANT_FIRST_OBSERVATION", variant_id)
                continue
            if value["a"] != old["a"]:
                add("BACK_IN_STOCK" if value["a"] else "OUT_OF_STOCK", variant_id)
            if same_currency:
                if value["p"] != old["p"]:
                    percent = abs(value["p"] - old["p"]) / old["p"] * 100 if old["p"] else None
                    if percent is None or percent >= min_percent:
                        add("PRICE_DROP" if value["p"] < old["p"] else "PRICE_RISE", variant_id,
                            previousPriceRaw=old["p"], currentPriceRaw=value["p"], percentChange=round(percent, 4) if percent is not None else None,
                            previousPriceAmount=f"{old['p'] // 100}.{old['p'] % 100:02}", currentPriceAmount=f"{value['p'] // 100}.{value['p'] % 100:02}")
                if value["c"] != old["c"]:
                    add("COMPARE_AT_PRICE_CHANGED", variant_id, previousCompareAtPriceRaw=old["c"], currentCompareAtPriceRaw=value["c"])
        # Missing variants might reflect the 250-variant source window. Never infer removal.
    row.update({"changes": changes, "changeCount": len(changes), "isChanged": bool(changes),
                "checkStatus": "FIRST_OBSERVATION" if previous is None else "CHANGED" if changes else "NO_ALERT",
                "priceComparisonStatus": "first_observation" if previous is None else "comparable" if row["currency"] is not None and row["currency"] == previous["currency"] else "currency_unknown_or_changed",
                "previousObservedAt": previous.get("lastSavedAt") if previous else None})
    return row, current


def write_atomic(path, data):
    encoded = canonical(data).encode("utf-8")
    if len(encoded) > MAX_STATE_BYTES:
        raise ValueError("Local state exceeds the 8 MiB checkpoint limit.")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", delete=False) as handle:
            temp = handle.name
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)
