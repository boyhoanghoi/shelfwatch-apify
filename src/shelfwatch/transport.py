"""Bounded public-web crawler. No browser, private-network access, or bypasses."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
import ipaddress
import socket
import time
from urllib.parse import urljoin, urlsplit, urlunsplit


import aiohttp
from aiohttp.abc import AbstractResolver

from .config import RunConfig
from protego import Protego

USER_AGENT = "ShelfWatchBot/0.1 (+https://github.com/boyhoanghoi/shelfwatch-apify)"
ROBOTS_AGENT = "ShelfWatchBot"
MAX_BYTES = 2 * 1024 * 1024


class FetchError(Exception):
    def __init__(self, status: str, message: str, http_status: int | None = None):
        super().__init__(message)
        self.status = status
        self.http_status = http_status


def public_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%")[0])
        mapped = getattr(ip, "ipv4_mapped", None)
        return bool(ip.is_global and (mapped is None or mapped.is_global))
    except ValueError:
        return False


def validate_url(value: str) -> str:
    """Validate literal targets; PublicResolver also checks the actual DNS answer."""
    try:
        if not isinstance(value, str) or len(value) > 4096:
            raise ValueError("Invalid or excessively long URL.")
        p = urlsplit(value)
        if p.scheme not in {"http", "https"} or not p.hostname:
            raise ValueError("Only HTTP(S) URLs are supported.")
        if p.username is not None or p.password is not None:
            raise ValueError("URL credentials are not supported.")
        if any(c.isspace() or ord(c) < 32 for c in value):
            raise ValueError("URL contains whitespace or control characters.")
        host = p.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        if p.port not in {None, 80, 443}:
            raise ValueError("Only standard web ports 80 and 443 are allowed.")
        if "%" in host or host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".lan")):
            raise ValueError("Local network destinations are not allowed.")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            # aiohttp treats any all-digit/dot hostname as an IP literal and
            # bypasses its resolver. Reject legacy octal/shortened spellings.
            if host.replace(".", "").isdigit():
                raise ValueError("IP addresses must use canonical public IP syntax.")
            if "." not in host or any(not label for label in host.split(".")):
                raise ValueError("A public fully qualified hostname is required.")
        else:
            if not public_ip(host):
                raise ValueError("Private or reserved network destinations are not allowed.")
        authority = f"[{host}]" if ":" in host else host
        if p.port is not None:
            authority += f":{p.port}"
        return urlunsplit((p.scheme, authority, p.path or "/", p.query, ""))
    except (ValueError, UnicodeError) as exc:
        raise FetchError("invalid_url", str(exc)) from None


def domain_key(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def same_site(a: str, b: str) -> bool:
    return domain_key(a) == domain_key(b)


class PublicResolver(AbstractResolver):
    """Resolve once and connect only to the checked addresses (no DNS TOCTOU)."""
    def __init__(self):
        self._resolver = aiohttp.ThreadedResolver()

    async def resolve(self, host: str, port: int = 0, family: int = socket.AF_INET):
        answers = await self._resolver.resolve(host, port, family)
        if not answers or any(not public_ip(a["host"]) for a in answers):
            raise OSError("DNS returned a private or reserved address; request blocked.")
        return answers

    async def close(self):
        await self._resolver.close()


@dataclass
class Page:
    url: str
    text: str
    status: int
    content_type: str


class SafeHttpClient:
    def __init__(self, config: RunConfig):
        self.config = config
        self.session: aiohttp.ClientSession | None = None
        self._last_request: dict[str, float] = {}
        self._host_locks = defaultdict(asyncio.Lock)
        self._robots_locks = defaultdict(asyncio.Lock)
        self._robots: dict[str, Protego] = {}
        self._crawl_delays: dict[str, float] = {}
        self.requests = 0

    async def __aenter__(self):
        self._resolver = PublicResolver()
        connector = aiohttp.TCPConnector(
            resolver=self._resolver, use_dns_cache=False,
            limit=self.config.concurrency + 2, family=socket.AF_UNSPEC,
        )
        self.session = aiohttp.ClientSession(
            connector=connector, timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds),
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/json;q=0.8,text/plain;q=0.7"},
            cookie_jar=aiohttp.DummyCookieJar(), trust_env=False,
        )
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
        await self._resolver.close()

    async def _pace(self, url: str):
        host = urlsplit(url).netloc
        async with self._host_locks[host]:
            delay = max(self.config.min_delay_seconds, self._crawl_delays.get(host, 0))
            await asyncio.sleep(max(0, self._last_request.get(host, 0) + delay - time.monotonic()))
            self._last_request[host] = time.monotonic()

    async def allowed(self, url: str) -> bool:
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        async with self._robots_locks[origin]:
            if origin not in self._robots:
                rules = ""
                try:
                    page = await self.fetch(origin + "/robots.txt", check_robots=False)
                except FetchError as exc:
                    if exc.http_status in {404, 410}:
                        rules = ""
                    elif exc.http_status in {401, 403}:
                        rules = "User-agent: *\nDisallow: /"
                    else:
                        # Do not silently crawl when the site's rules cannot be read.
                        raise FetchError("robots_unavailable", f"Could not read robots.txt ({exc.status}); skipped conservatively.", exc.http_status) from None
                else:
                    # Robots rules are authoritative regardless of a site's
                    # mistaken MIME type. HTML-only branded 404 lines are ignored
                    # by the robots parser without discarding valid directives.
                    rules = page.text
                parser = Protego.parse(rules)
                delay = parser.crawl_delay(ROBOTS_AGENT) or 0
                if delay > 30:
                    raise FetchError("robots_disallowed", "Published crawl delay exceeds this tool's bounded runtime.")
                self._crawl_delays[p.netloc] = float(delay)
                self._robots[origin] = parser
            return self._robots[origin].can_fetch(url, ROBOTS_AGENT)

    async def fetch(self, url: str, *, check_robots: bool = True, scope_url: str | None = None) -> Page:
        assert self.session is not None
        for redirect in range(6):
            url = validate_url(url)
            if scope_url is not None and not same_site(scope_url, url):
                raise FetchError("offsite_redirect", "Contact-page redirect leaves the selected website.")
            if check_robots and self.config.respect_robots and not await self.allowed(url):
                raise FetchError("robots_disallowed", "The website's robots.txt disallows this page.")
            await self._pace(url)
            try:
                self.requests += 1
                async with self.session.get(url, allow_redirects=False) as response:
                    status = response.status
                    if status in {301, 302, 303, 307, 308}:
                        location = response.headers.get("Location")
                        if not location:
                            raise FetchError("http_error", "Redirect has no Location header.", status)
                        if not check_robots and not same_site(url, urljoin(url, location)):
                            raise FetchError("robots_unavailable", "robots.txt redirected to another website.")
                        url = urljoin(url, location)
                        continue
                    if status in {401, 403, 429}:
                        raise FetchError("blocked", "Website denied access or requested a lower request rate.", status)
                    if status >= 400:
                        raise FetchError("http_error", f"Website returned HTTP {status}.", status)
                    content_type = response.headers.get("Content-Type", "").lower()
                    if content_type and not any(t in content_type for t in ("text/", "application/json", "application/ld+json", "application/xhtml+xml", "application/xml")):
                        raise FetchError("unsupported_content", "Response is not a supported text/HTML page.", status)
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.content.iter_chunked(65536):
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise FetchError("response_too_large", "Page exceeds the 2 MiB decoded response limit.")
                        chunks.append(chunk)
                    charset = response.charset or "utf-8"
                    try:
                        text = b"".join(chunks).decode(charset, errors="replace")
                    except LookupError:
                        text = b"".join(chunks).decode("utf-8", errors="replace")
                    if any(marker in text[:200000].lower() for marker in ("<title>just a moment", "<title>access denied", "<title>verify you are human", "<title>attention required!")):
                        raise FetchError("blocked", "A browser challenge was returned; skipped without a bypass.", status)
                    return Page(str(response.url), text, status, content_type)
            except asyncio.TimeoutError:
                raise FetchError("timeout", "Website request timed out.") from None
            except (aiohttp.ClientError, OSError) as exc:
                raise FetchError("network_error", f"Public website connection failed ({type(exc).__name__}).") from None
        raise FetchError("redirect_limit", "Website exceeded five redirects.")
