from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from outcomes_data.utils.http import build_retrying_session


YEAR_PATH_RE = re.compile(r"/(\d{4})-(\d{2})-monthly-cancer-waiting-times-statistics/?$")
PERIOD_PAGE_RE = re.compile(r"cancer-waiting-times-for-([a-z]+)-(\d{4}-\d{2})-(provisional|final)/?$")
METRIC_FILENAME_RE = re.compile(r"([358])\..*\.csv$")

MONTH_NAME_TO_NUM = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

@dataclass(frozen=True)
class CancerMetricUrl:
    period: str  # YYYY-MM
    metric: int # 3, 5, or 8
    url: str
    is_final: bool

class CancerSourceScraper:
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

            if "monthly-cancer-waiting-times-statistics" in href and any(char.isdigit() for char in href):
                full = urljoin(self.top_url, href)
                parsed = urlparse(full)
                path = parsed.path.rstrip("/") + "/"
                normalised = f"{parsed.scheme}://{parsed.netloc}{path}"
                if normalised not in seen:
                    seen.add(normalised)
                    candidates.append(normalised)
        return sorted(list(set(candidates)), reverse=True)

    def find_period_pages_on_year_page(self, year_page_url: str) -> list[str]:
        resp = self.session.get(year_page_url, timeout=self.timeout_s)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if "cancer-waiting-times-for-" in href:
                full_url = urljoin(year_page_url, href)
                links.append(full_url)
        return sorted(list(set(links)), reverse=True)

    def find_csv_links_on_period_page(self, period_page_url: str) -> list[CancerMetricUrl]:
        path_match = PERIOD_PAGE_RE.search(period_page_url)
        if not path_match:
            return []

        month_name, year_span, type_str = path_match.groups()
        month_num = MONTH_NAME_TO_NUM.get(month_name.lower())
        if not month_num:
            return []

        start_year = int(year_span.split('-')[0])
        year = start_year if month_num >= 4 else start_year + 1
        period = f"{year}-{month_num:02d}"
        is_final = type_str == 'final'

        resp = self.session.get(period_page_url, timeout=self.timeout_s)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        found_metrics = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href.lower().endswith(".csv"):
                continue

            filename_match = METRIC_FILENAME_RE.search(href)
            if filename_match:
                metric = int(filename_match.group(1))
                full_url = urljoin(period_page_url, href)
                found_metrics.append(
                    CancerMetricUrl(period=period, metric=metric, url=full_url, is_final=is_final)
                )
        return found_metrics

    def build_period_url_list(self) -> list[CancerMetricUrl]:
        year_pages = self.find_year_pages()
        all_period_pages = []
        for yp in year_pages:
            all_period_pages.extend(self.find_period_pages_on_year_page(yp))

        all_metrics: list[CancerMetricUrl] = []
        for pp in all_period_pages:
            all_metrics.extend(self.find_csv_links_on_period_page(pp))

        # Prioritise final over provisional
        final_urls: dict[tuple[str, int], CancerMetricUrl] = {}
        for metric_url in all_metrics:
            key = (metric_url.period, metric_url.metric)

            existing = final_urls.get(key)

            # If we already have a final version, skip
            if existing and existing.is_final:
                continue

            # If the new one is final, it replaces any provisional one
            if metric_url.is_final:
                final_urls[key] = metric_url
            # Otherwise, only add if nothing exists for this key
            elif key not in final_urls:
                 final_urls[key] = metric_url

        return sorted(final_urls.values(), key=lambda x: (x.period, x.metric), reverse=True)
