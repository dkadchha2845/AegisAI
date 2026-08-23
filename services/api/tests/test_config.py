"""
Config is validated, documented, and boots with nothing configured.

Three properties, each of which has cost this project time when absent:

  * **Every setting has a default.** The clean-clone promise is that `git clone
    && pip install && run` works. One required setting breaks it.
  * **`.env.example` documents every setting.** An undocumented knob is one
    nobody finds, and the whole point of explicit degradation is that a person
    can see which capability is off and turn it on.
  * **Old `PRESAGE_*` names still resolve.** A developer's `.env` is untracked,
    so it survived the rename; silently ignoring it switches a configured
    capability off with no signal. `AEGIS_OCR` had exactly that bug — read
    straight from `os.getenv`, bypassing the alias.
"""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from services.api.config import REPO_ROOT, Settings, settings

#: Documented in .env.example but consumed by docker compose, not by the API.
COMPOSE_ONLY = {
    "AEGIS_PG_USER", "AEGIS_PG_PASSWORD", "AEGIS_PG_DB",
    "AEGIS_NEO4J_USER", "AEGIS_NEO4J_PASSWORD",
}


def _accepted_env_names() -> set[str]:
    names: set[str] = set()
    for field_name, f in Settings.model_fields.items():
        alias = f.validation_alias
        if alias is None:
            names.add(f"AEGIS_{field_name.upper()}")
        else:
            names.update(getattr(alias, "choices", []) or [])
    return names


def _documented_env_names() -> set[str]:
    text = (REPO_ROOT / ".env.example").read_text()
    return set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", text, re.M))


def test_every_setting_has_a_default():
    """A clean clone must boot with an empty environment."""
    required = [n for n, f in Settings.model_fields.items() if f.is_required()]
    assert required == [], (
        f"these settings have no default and would block an offline boot: {required}"
    )


def test_env_example_documents_every_setting():
    primary = {n for n in _accepted_env_names() if not n.startswith("PRESAGE_")}
    missing = sorted(primary - _documented_env_names())
    assert missing == [], f".env.example is missing: {missing}"


def test_env_example_has_no_dead_entries():
    """A documented variable nothing reads invites a real credential into a file for nothing."""
    dead = sorted(_documented_env_names() - _accepted_env_names() - COMPOSE_ONLY)
    assert dead == [], f".env.example documents variables no setting reads: {dead}"


def test_renamed_settings_accept_the_old_prefix():
    """Every AEGIS_* alias carries its PRESAGE_* counterpart."""
    for field_name, f in Settings.model_fields.items():
        choices = getattr(f.validation_alias, "choices", []) or []
        aegis = [c for c in choices if c.startswith("AEGIS_")]
        if not aegis:
            continue  # third-party names like DATABASE_URL / GEMINI_API_KEY
        for name in aegis:
            legacy = "PRESAGE_" + name[len("AEGIS_"):]
            assert legacy in choices, f"{field_name}: {name} has no {legacy} fallback"


@pytest.mark.parametrize(
    "env_name,value,field,expected",
    [
        ("PRESAGE_OCR", "none", "ocr_backend", "none"),
        ("PRESAGE_LLM", "ollama", "llm_backend", "ollama"),
        ("PRESAGE_AUTH", "1", "auth_enforced", True),
    ],
)
def test_legacy_prefix_actually_resolves(monkeypatch, env_name, value, field, expected):
    # An un-migrated .env carries ONLY the old name. conftest.py pins some
    # AEGIS_* vars for hermetic tests, and those correctly outrank the legacy
    # spelling, so clear the new name to reproduce the real scenario.
    monkeypatch.delenv("AEGIS_" + env_name[len("PRESAGE_"):], raising=False)
    monkeypatch.setenv(env_name, value)
    assert getattr(Settings(), field) == expected


def test_new_prefix_wins_when_both_are_set(monkeypatch):
    monkeypatch.setenv("PRESAGE_OCR", "easyocr")
    monkeypatch.setenv("AEGIS_OCR", "tesseract")
    assert Settings().ocr_backend == "tesseract"


def test_invalid_value_fails_at_startup(monkeypatch):
    """Bad config must fail loudly, naming the field, not surface later elsewhere."""
    monkeypatch.setenv("AEGIS_PG_PORT", "not-a-number")
    with pytest.raises(ValidationError) as exc:
        Settings()
    assert "PG_PORT" in str(exc.value)


def test_settings_are_immutable():
    """Nothing may reconfigure the app mid-request."""
    with pytest.raises(ValidationError):
        settings.llm_backend = "something-else"  # type: ignore[misc]


def test_blank_string_means_unset(monkeypatch):
    """conftest sets DATABASE_URL="" to force the ephemeral DB."""
    monkeypatch.setenv("DATABASE_URL", "")
    assert Settings().database_url is None
