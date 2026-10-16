from dataclasses import dataclass
import re
from urllib.parse import urlsplit, urlunsplit

from .transport_errors import ConfigError


def product_url(value: str) -> str:
    # Transport performs public-address and DNS checks as well.
    from .transport import validate_url
    from .transport import FetchError
    try:
        clean = validate_url(value)
    except FetchError as exc:
        raise ConfigError(str(exc)) from None
    p = urlsplit(clean)
    if p.scheme != "https" or p.port is not None or p.query:
        raise ConfigError("Use an HTTPS product page URL without a port or query string; remove tracking and variant parameters.")
    path = p.path.rstrip("/")
    if not re.fullmatch(r"(?:/[a-zA-Z]{2}(?:-[a-zA-Z]{2})?)?/products/[a-zA-Z0-9][a-zA-Z0-9_-]{0,240}", path):
        raise ConfigError("Use a Shopify /products/handle page, optionally prefixed by a locale such as /en-gb. Store roots and collection URLs are not supported.")
    return urlunsplit(("https", p.netloc, path, "", ""))


@dataclass(frozen=True)
class RunConfig:
    product_urls: tuple[str, ...]
    monitor_name: str = "my-watchlist"
    max_products: int = 20
    min_price_change_percent: float = 0
    timeout_seconds: int = 15
    concurrency: int = 1
    min_delay_seconds: float = 1.0
    respect_robots: bool = True

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ConfigError("Input must be a JSON object.")
        allowed = {"productUrls", "monitorName", "maxProducts", "minPriceChangePercent", "timeoutSeconds"}
        if any(key not in allowed and not key.startswith("__") for key in data):
            raise ConfigError("Unknown input field. See the input schema for supported fields.")
        urls = data.get("productUrls", [])
        if not isinstance(urls, list) or not 1 <= len(urls) <= 100 or any(not isinstance(url, str) for url in urls):
            raise ConfigError("productUrls must contain 1–100 HTTPS Shopify product page URLs.")
        urls = tuple(dict.fromkeys(product_url(url.strip()) for url in urls))
        name = data.get("monitorName", "my-watchlist")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", name):
            raise ConfigError("monitorName must contain 1–32 lowercase letters, digits or hyphens, starting with a letter/digit.")
        limit, timeout = data.get("maxProducts", 20), data.get("timeoutSeconds", 15)
        for field, value, lo, hi in [("maxProducts", limit, 1, 100), ("timeoutSeconds", timeout, 5, 30)]:
            if type(value) is not int or not lo <= value <= hi:
                raise ConfigError(f"{field} must be an integer between {lo} and {hi}.")
        percent = data.get("minPriceChangePercent", 0)
        if isinstance(percent, bool) or not isinstance(percent, (int, float)) or not 0 <= percent <= 100:
            raise ConfigError("minPriceChangePercent must be a finite number between 0 and 100.")
        return cls(urls, name, limit, float(percent), timeout)
