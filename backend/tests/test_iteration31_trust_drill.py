"""Iteration 31 — /api/trust/timeseries/details drill-through endpoint tests."""
import os
import pytest
import requests

def _load_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        v = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    return (v or "").rstrip("/")

BASE_URL = _load_url()


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _get(client, series):
    return client.get(f"{BASE_URL}/api/trust/timeseries/details", params={"series": series}, timeout=30)


def _validate_initials(primary: str):
    """Primary must contain initials (with '.') and be short."""
    assert primary, "primary is empty"
    # For engagements the format is 'X.X. · Industry' — split on '·'
    head = primary.split("·")[0].strip()
    assert "." in head, f"'{head}' does not look like initials"
    assert len(head) < 12, f"initials segment too long: '{head}'"


class TestTrustDrill:
    def test_refs_series(self, client):
        r = _get(client, "refs")
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("series", "items", "count", "window_start", "as_of"):
            assert k in j, f"missing key {k}"
        assert j["series"] == "refs"
        assert isinstance(j["items"], list)
        assert j["count"] == len(j["items"])
        for it in j["items"]:
            assert set(["date", "primary", "secondary", "chip", "kind"]).issubset(it.keys())
            assert it["kind"] == "reference"
            assert it["chip"] in {"yes", "no", "partial", "answered"}
            _validate_initials(it["primary"])
            # yyyy-mm-dd
            assert len(it["date"]) == 10 and it["date"][4] == "-"

    def test_engagements_series(self, client):
        r = _get(client, "engagements")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["series"] == "engagements"
        assert j["count"] == len(j["items"])
        # Per problem statement: ~20 signed engagements dated 2026-08-09
        for it in j["items"]:
            assert it["kind"] == "engagement"
            assert it["chip"] in {"contract_signed", "active", "completed", "signed"}
            _validate_initials(it["primary"])
            assert "·" in it["primary"], "engagements primary must be '<initials> · <industry>'"

    def test_verified_talents_series(self, client):
        r = _get(client, "verified_talents")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["series"] == "verified_talents"
        for it in j["items"]:
            assert it["kind"] == "talent"
            assert it["chip"] == "verified"
            _validate_initials(it["primary"])

    def test_verified_companies_series(self, client):
        r = _get(client, "verified_companies")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["series"] == "verified_companies"
        for it in j["items"]:
            assert it["kind"] == "employer"
            assert it["chip"] == "verified"
            _validate_initials(it["primary"])

    def test_bogus_series_returns_400(self, client):
        r = _get(client, "bogus")
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"

    def test_timeseries_regression_30_buckets(self, client):
        r = client.get(f"{BASE_URL}/api/trust/timeseries", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "series" in j
        assert len(j["series"]) == 30, f"expected 30 buckets, got {len(j['series'])}"
