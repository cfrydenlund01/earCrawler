"""ORI (Office of Research Integrity) client for NSF case summaries.

This client fetches research misconduct case summaries from the ORI
website. It supports listing summaries and retrieving details for
individual cases. Live mode is disabled by default to avoid making
network requests during crawling; enable by passing `live_mode=True`.
"""

from __future__ import annotations

import logging
from typing import Iterable, Dict


class ORIClient:
    """Client for retrieving NSF research misconduct case summaries."""

    def __init__(self, live_mode: bool = False) -> None:
        self.live_mode = live_mode
        self.logger = logging.getLogger(self.__class__.__name__)

    def list_cases(self) -> Iterable[Dict[str, str]]:
        """Return an iterable of available case identifiers.

        When `live_mode` is ``False``, returns an empty list. Override this
        method to provide static case IDs or implement live retrieval.
        """
        if not self.live_mode:
            return []
        # TODO: implement live retrieval from ORI website when enabled
        return []

    def fetch_case(self, case_id: str) -> str:
        """Fetch the full case narrative for the given case identifier.

        Parameters
        ----------
        case_id: str
            Identifier returned from :meth:`list_cases`.

        Returns
        -------
        str
            Raw case narrative text. When `live_mode` is ``False``, returns
            an empty string.
        """
        if not self.live_mode:
            return ""
        # TODO: implement live retrieval of case narrative
        return ""
