from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from outcomes_data.utils.http import build_retrying_session


YEAR_PATH_RE = re.compile(r"/rtt-waiting-times/rtt-data-(\d{4})-(\d{2})/?$")
MONTH_ABBR_TO_NUM = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}
MONTH_YEAR_PATTERN = re.compile(r"(?i)(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(\d{2})")


@dataclass(frozen=True)
class PeriodUrl:
    period: str  # YYYY-MM
    url: str


class RttSourceScraper:
    def __init__(self, top_url: str, timeout_s: int = 60) -> None:
        self.top_url = top_url
        self.timeout_s = timeout_s
        self.session = build_retrying_session()

    def find_year_pages(self) -> list[str]:
        resp = self.session.get(self.top_url, timeout=self.timeout_s)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        seen: set[str] = set()
        candidates: list[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href:
                continue
            full = urljoin(self.top_url, href)
            parsed = urlparse(full)
            path = parsed.path.rstrip("/") + "/"
            if YEAR_PATH_RE.search(path):
                normalised = f"{parsed.scheme}://{parsed.netloc}{path}"
                if normalised not in seen:
                    seen.add(normalised)
                    candidates.append(normalised)

        def sort_key(u: str) -> tuple[int, int]:
            m = YEAR_PATH_RE.search(urlparse(u).path)
            if not m:
                return (0, 0)
            start_year = int(m.group(1))
            end_two = int(m.group(2))
            end_year = (start_year // 100) * 100 + end_two
            if end_year < start_year:
                end_year += 100
            return (start_year, end_year)

        return sorted(candidates, key=sort_key, reverse=True)

    def find_csv_zip_links_on_page(self, page_url: str) -> list[str]:
        resp = self.session.get(page_url, timeout=self.timeout_s)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        links: list[str] = []
        for a in soup.select("a[href]"):
            href = a.get("href", "").strip()
            if not href:
                continue
            full = urljoin(page_url, href)
            if full.lower().endswith(".zip"):
                links.append(full)
        # de-duplicate preserving order
        seen = set()
        deduped = []
        for u in links:
            if u in seen:
                continue
            seen.add(u)
            deduped.append(u)
        return deduped

    def _extract_year_month_from_url(self, url: str) -> tuple[int, int] | None:
        m = MONTH_YEAR_PATTERN.search(url)
        if not m:
            return None
        mon_abbr = m.group(1).title()
        yy = int(m.group(2))
        return (2000 + yy, MONTH_ABBR_TO_NUM[mon_abbr])

    @staticmethod
    def _choose_canonical_url(urls: list[str]) -> str:
        revised = [u for u in urls if "revised" in u.lower()]
        return sorted(revised)[-1] if revised else sorted(urls)[-1]

    def build_period_url_list(self) -> list[PeriodUrl]:
        year_pages = self.find_year_pages()
        all_zips: list[str] = []
        for yp in year_pages:
            all_zips.extend(self.find_csv_zip_links_on_page(yp))
        ym_to_urls: dict[tuple[int, int], list[str]] = {}
        for u in all_zips:
            ym = self._extract_year_month_from_url(u)
            if ym is None:
                continue
            ym_to_urls.setdefault(ym, []).append(u)
        period_to_url: dict[str, str] = {}
        for (y, m), urls in ym_to_urls.items():
            if (y > 2015) or (y == 2015 and m >= 10):
                period = f"{y}-{m:02d}"
                period_to_url[period] = self._choose_canonical_url(list(set(urls)))
        return [PeriodUrl(period=k, url=v) for k, v in sorted(period_to_url.items())]
