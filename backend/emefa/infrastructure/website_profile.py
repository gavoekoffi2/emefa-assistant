"""Bounded, SSRF-safe import of public business website information."""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

MAX_PAGE_BYTES = 750_000
MAX_PAGES = 5
MAX_SUMMARY_CHARS = 6_000
PREFERRED_PATHS = ("about", "a-propos", "qui-sommes", "services", "solutions", "contact")


@dataclass(frozen=True, slots=True)
class WebsiteImport:
    url: str
    company_name: str
    description: str
    summary: str
    pages_imported: int


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.site_name = ""
        self.links: list[str] = []
        self.text: list[str] = []
        self._ignored = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        values = {str(key).lower(): str(value or "") for key, value in attrs}
        if tag in {"script", "style", "svg", "noscript"}:
            self._ignored += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            content = values.get("content", "").strip()
            if key in {"description", "og:description"} and content and not self.description:
                self.description = content
            if key == "og:site_name" and content:
                self.site_name = content
        elif tag == "a" and values.get("href"):
            self.links.append(values["href"])

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "svg", "noscript"} and self._ignored:
            self._ignored -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        value = re.sub(r"\s+", " ", data).strip()
        if not value or self._ignored:
            return
        if self._in_title:
            self.title = f"{self.title} {value}".strip()
        elif len(value) >= 3:
            self.text.append(value)


Resolver = Callable[[str, int], Awaitable[list[str]]]


async def _resolve_public(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    records = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({str(record[4][0]).split("%", 1)[0] for record in records})


def _is_forbidden_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


class WebsiteProfileImporter:
    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Resolver = _resolve_public,
    ) -> None:
        self.transport = transport
        self.resolver = resolver

    async def _validate(self, url: str) -> tuple[str, str]:
        try:
            parsed = urlsplit(url.strip())
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as exc:
            raise ValueError("L’adresse du site est invalide.") from exc
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Saisissez une adresse publique commençant par http:// ou https://.")
        if parsed.username or parsed.password:
            raise ValueError("Les adresses contenant des identifiants ne sont pas acceptées.")
        try:
            addresses = await self.resolver(parsed.hostname, port)
        except (OSError, socket.gaierror) as exc:
            raise ValueError("Le nom de domaine du site est introuvable.") from exc
        if not addresses or any(_is_forbidden_ip(address) for address in addresses):
            raise ValueError("Cette adresse réseau n’est pas un site public autorisé.")
        normalized = urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, "")
        )
        origin = f"{parsed.scheme}://{parsed.netloc.lower()}"
        return normalized, origin

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> tuple[str, bytes]:
        current = url
        for _ in range(4):
            current, _origin = await self._validate(current)
            async with client.stream("GET", current) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise RuntimeError("Le site a renvoyé une redirection invalide.")
                    current = urljoin(current, location)
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if "text/html" not in content_type:
                    raise RuntimeError("L’adresse ne renvoie pas une page web HTML.")
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_PAGE_BYTES:
                        raise RuntimeError("La page est trop volumineuse pour être importée.")
                    chunks.append(chunk)
                return str(response.url), b"".join(chunks)
        raise RuntimeError("Le site effectue trop de redirections.")

    async def import_site(self, url: str) -> WebsiteImport:
        start_url, origin = await self._validate(url)
        queue = [start_url]
        visited: set[str] = set()
        pages: list[tuple[str, _PageParser]] = []
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(12.0, connect=5.0),
            headers={"User-Agent": "EMEFA-Profile-Importer/1.0"},
            follow_redirects=False,
            transport=self.transport,
        ) as client:
            while queue and len(pages) < MAX_PAGES:
                candidate = queue.pop(0)
                if candidate in visited:
                    continue
                visited.add(candidate)
                try:
                    final_url, body = await self._fetch(client, candidate)
                except (httpx.HTTPError, RuntimeError, ValueError):
                    if not pages:
                        raise RuntimeError("EMEFA n’a pas pu lire ce site public.")
                    continue
                parser = _PageParser()
                parser.feed(body.decode("utf-8", errors="ignore"))
                pages.append((final_url, parser))
                links: list[tuple[int, str]] = []
                for href in parser.links:
                    absolute = urljoin(final_url, href)
                    parsed = urlsplit(absolute)
                    if f"{parsed.scheme}://{parsed.netloc.lower()}" != origin:
                        continue
                    clean = urlunsplit(
                        (parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, "")
                    )
                    score = 0 if any(
                        word in parsed.path.lower() for word in PREFERRED_PATHS
                    ) else 1
                    links.append((score, clean))
                for _score, link in sorted(links)[:12]:
                    if link not in visited and link not in queue:
                        queue.append(link)

        if not pages:
            raise RuntimeError("Aucune information publique exploitable n’a été trouvée.")
        first = pages[0][1]
        company = (
            first.site_name or first.title.split("|")[0].split("—")[0]
        ).strip()[:200]
        description = first.description.strip()[:2_000]
        sections: list[str] = []
        for page_url, parser in pages:
            text = re.sub(r"\s+", " ", " ".join(parser.text)).strip()
            if text:
                sections.append(f"Page {page_url}: {text[:1_600]}")
        summary = "\n".join(sections)[:MAX_SUMMARY_CHARS]
        return WebsiteImport(
            url=pages[0][0],
            company_name=company,
            description=description,
            summary=summary,
            pages_imported=len(pages),
        )
