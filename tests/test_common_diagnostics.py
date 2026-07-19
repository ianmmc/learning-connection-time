"""#111 Phase-1 common/ sweep — DB-free diagnostics tests (#326, #328).

Lives outside test_acquisition_stages.py on purpose: that module is pytestmark'd
integration and deselected from the CI DB-free job; these are pure unit tests.
"""
import pytest

from infrastructure.acquisition.common import discover as DISC


def _fake_response(status, payload=None, text=""):
    class R:
        status_code = status

        def json(self):
            return payload

        @property
        def text(self):
            return text

        def raise_for_status(self):
            import requests
            if status >= 400:
                raise requests.HTTPError(f"HTTP {status}")
    return R()


class TestSecretDiagnostics:
    """#328 — a missing/malformed secrets setup must diagnose as itself, not as billing/auth."""

    def test_auth_hint_names_the_missing_secret(self, monkeypatch, tmp_path):
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        monkeypatch.setattr(DISC, "SECRETS_FILE", tmp_path / "absent.json")
        hint = DISC._auth_hint("SERPER_API_KEY")
        assert "SERPER_API_KEY not set" in hint and "not a billing problem" in hint

    def test_auth_hint_empty_when_secret_present(self, monkeypatch):
        monkeypatch.setenv("SERPER_API_KEY", "k")
        assert DISC._auth_hint("SERPER_API_KEY") == ""

    def test_malformed_secrets_file_halts_with_its_own_message(self, monkeypatch, tmp_path):
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        bad = tmp_path / "secrets.local.json"
        bad.write_text("{not json")
        monkeypatch.setattr(DISC, "SECRETS_FILE", bad)
        with pytest.raises(SystemExit, match="malformed secrets file"):
            DISC._secret("SERPER_API_KEY")

    def test_401_message_carries_the_hint_when_key_missing(self, monkeypatch, tmp_path):
        import requests
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        monkeypatch.setattr(DISC, "SECRETS_FILE", tmp_path / "absent.json")
        monkeypatch.setattr(requests, "post", lambda *a, **k: _fake_response(401, text="unauthorized"))
        with pytest.raises(SystemExit, match="SERPER_API_KEY not set"):
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
