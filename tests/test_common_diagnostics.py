"""#111 Phase-1 common/ sweep — DB-free diagnostics tests (#326, #328 + review deepening).

Lives outside test_acquisition_stages.py on purpose: that module is pytestmark'd
integration and deselected from the CI DB-free job; these are pure unit tests.
"""
import pytest

from infrastructure.acquisition.common import discover as DISC


class TestSecretPreflight:
    """#328 (review-deepened): a missing/malformed secrets setup halts BEFORE any network
    call, with its own precise message — the openrouter has_key() pre-flight shape, not a
    reactive message patch at the 401 site (which wasted a round-trip and could mask the
    original billing/auth status mid-f-string)."""

    def test_missing_key_halts_before_any_http(self, monkeypatch, tmp_path):
        import requests
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        monkeypatch.setattr(DISC, "SECRETS_FILE", tmp_path / "absent.json")
        monkeypatch.setattr(requests, "post",
                            lambda *a, **k: pytest.fail("pre-flight must halt before any HTTP call"))
        with pytest.raises(SystemExit, match="SERPER_API_KEY not set.*no request was sent"):
            DISC.serper_search("q", "example.org", _sleep=lambda s: None)

    def test_brightdata_names_every_missing_secret(self, monkeypatch, tmp_path):
        import requests
        monkeypatch.delenv("BRIGHTDATA_API_KEY", raising=False)
        monkeypatch.delenv("BRIGHTDATA_SERP_ZONE", raising=False)
        monkeypatch.setattr(DISC, "SECRETS_FILE", tmp_path / "absent.json")
        monkeypatch.setattr(requests, "post",
                            lambda *a, **k: pytest.fail("pre-flight must halt before any HTTP call"))
        with pytest.raises(SystemExit, match="BRIGHTDATA_API_KEY, BRIGHTDATA_SERP_ZONE not set"):
            DISC.brightdata_search("q", "example.org")

    def test_malformed_secrets_file_halts_with_its_own_message(self, monkeypatch, tmp_path):
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        bad = tmp_path / "secrets.local.json"
        bad.write_text("{not json")
        monkeypatch.setattr(DISC, "SECRETS_FILE", bad)
        with pytest.raises(SystemExit, match="malformed secrets file"):
            DISC._secret("SERPER_API_KEY")

    def test_key_present_401_is_pure_billing_auth(self, monkeypatch):
        """With the key present, a 401 passes pre-flight and halts with the REAL status+body —
        no hint machinery left to mask it (the review's f-string-masking scenario is gone)."""
        import requests

        class R:
            status_code = 401
            text = "unauthorized"

        monkeypatch.setenv("SERPER_API_KEY", "k")
        monkeypatch.setattr(requests, "post", lambda *a, **k: R())
        with pytest.raises(SystemExit, match=r"Serper HTTP 401 \(billing/auth\).*unauthorized"):
            DISC.serper_search("q", "example.org", _sleep=lambda s: None)


class TestLoadCandidatesWarn:
    """#326 — a MALFORMED candidates.json still ingests as empty, but says so."""

    def test_malformed_file_warns_instead_of_silent_empty(self, tmp_path, capsys):
        from infrastructure.acquisition.common import cache_ingest as CI
        (tmp_path / "candidates.json").write_text("{truncated")
        assert CI.load_candidates(tmp_path) == {}
        assert "unreadable candidates.json" in capsys.readouterr().out

    def test_absent_file_stays_silent(self, tmp_path, capsys):
        from infrastructure.acquisition.common import cache_ingest as CI
        assert CI.load_candidates(tmp_path) == {}
        assert capsys.readouterr().out == ""
