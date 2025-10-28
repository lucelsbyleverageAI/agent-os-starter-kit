from __future__ import annotations

import logging
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


logger = logging.getLogger(__name__)


def build_retrying_session(
    total: int = 3,
    backoff_factor: float = 0.5,
    status_forcelist: tuple[int, ...] = (429, 500, 502, 503, 504),
    user_agent: Optional[str] = "Mozilla/5.0 (compatible; e18-agent/1.0)",
) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=total,
        read=total,
        connect=total,
        status=total,
        status_forcelist=status_forcelist,
        allowed_methods=("GET", "HEAD"),
        backoff_factor=backoff_factor,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    if user_agent:
        session.headers.update({"User-Agent": user_agent})
    return session
