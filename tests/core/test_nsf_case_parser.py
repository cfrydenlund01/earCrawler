from __future__ import annotations

from pathlib import Path

from api_clients.upstream_status import UpstreamStatus
from earCrawler.core.nsf_case_parser import NSFCaseParser


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_run_parses_case() -> None:
    parser = NSFCaseParser()
    cases = parser.run(FIXTURES, live=False)
    assert len(cases) == 1
    case = cases[0]
    assert case["case_number"] == "NSF-001"
    assert len(case["paragraphs"]) == 2
    for para in case["paragraphs"]:
        assert len(para) >= 30
    assert set(["R01-ABC123", "University of Testing", "John Smith"]) <= set(
        case["entities"]
    )
    expected_hash = NSFCaseParser.hash_text("\n".join(case["paragraphs"]))
    assert case["hash"] == expected_hash


class _StubResult:
    def __init__(self, data: str, status: UpstreamStatus) -> None:
        self.data = data
        self.status = status


def test_run_live_uses_typed_results_and_skips_degraded_case(monkeypatch) -> None:
    class _StubORIClient:
        BASE_URL = "https://ori.hhs.gov"

        def __init__(self) -> None:
            self._snapshot = {
                "get_listing_html": {
                    "source": "ori",
                    "operation": "get_listing_html",
                    "state": "ok",
                    "timestamp": "2026-03-20T00:00:00Z",
                }
            }

        def get_listing_html_result(self):
            html = '<a href="/case/good"></a><a href="/case/bad"></a>'
            return _StubResult(
                html,
                UpstreamStatus(
                    source="ori",
                    operation="get_listing_html",
                    state="ok",
                ),
            )

        def get_case_html_result(self, url: str):
            if url.endswith("/bad"):
                status = UpstreamStatus(
                    source="ori",
                    operation="get_case_html",
                    state="retry_exhausted",
                    message="network down",
                    retry_attempts=3,
                )
                self._snapshot["get_case_html"] = status.as_dict()
                return _StubResult("", status)
            html = (
                "<h1>Case Number NSF-TEST</h1>"
                "<p>This paragraph is intentionally long enough to be captured.</p>"
            )
            status = UpstreamStatus(
                source="ori",
                operation="get_case_html",
                state="ok",
                result_count=1,
            )
            self._snapshot["get_case_html"] = status.as_dict()
            return _StubResult(html, status)

        def get_status_snapshot(self):
            return dict(self._snapshot)

    monkeypatch.setattr("earCrawler.core.nsf_case_parser.ORIClient", _StubORIClient)
    parser = NSFCaseParser()
    cases = parser.run(FIXTURES, live=True)

    assert len(cases) == 1
    assert cases[0]["case_number"] == "NSF-TEST"
    assert parser.last_upstream_status["get_case_html"]["state"] == "retry_exhausted"


def test_run_live_returns_empty_when_listing_is_degraded(monkeypatch) -> None:
    class _StubORIClient:
        BASE_URL = "https://ori.hhs.gov"

        def get_listing_html_result(self):
            return _StubResult(
                "",
                UpstreamStatus(
                    source="ori",
                    operation="get_listing_html",
                    state="upstream_unavailable",
                    status_code=503,
                ),
            )

        def get_status_snapshot(self):
            return {
                "get_listing_html": {
                    "source": "ori",
                    "operation": "get_listing_html",
                    "state": "upstream_unavailable",
                    "status_code": 503,
                    "timestamp": "2026-03-20T00:00:00Z",
                }
            }

    monkeypatch.setattr("earCrawler.core.nsf_case_parser.ORIClient", _StubORIClient)
    parser = NSFCaseParser()
    cases = parser.run(FIXTURES, live=True)

    assert cases == []
    assert parser.last_upstream_status["get_listing_html"]["state"] == "upstream_unavailable"
