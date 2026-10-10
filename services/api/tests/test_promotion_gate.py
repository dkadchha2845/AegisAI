"""
A checkpoint is never promoted on data it was trained on — task T-05, audit B-01.

The stage classifier was served for weeks on a macro-F1 of 0.767 that was a
train/test leak: the split was rebuilt after training, the old weights were
scored on the new test set, and 311 of its 423 turns were the weights' own
training data. Nothing checked, because nothing recorded what the weights had
seen. Two halves had to change, and both are tested here:

  * **The gate** (`ml/evaluation/provenance.py`, used by `eval_backends.py`)
    refuses to score a checkpoint whose training data overlaps the test split,
    or which has no record of its training data at all.
  * **Serving** (`engine/classifier.py`) promotes a checkpoint only on a
    comparison that says the leak check passed. A missing, unreadable, refused
    or older-format comparison leaves the lexical model serving, and says why.

Everything here runs without torch and without a checkpoint, so it runs on CI —
which is the point: the last gate could only be exercised on one laptop.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from ml.evaluation import manifest, provenance
from services.api.engine import classifier as classifier_mod
from services.api.main import app

ROOT = Path(__file__).resolve().parents[3]


def _rows(archetype: str, call: str, texts: List[str]) -> List[Dict[str, Any]]:
    return [
        {"text": t, "archetype": archetype, "call_id": call, "turn_index": i}
        for i, t in enumerate(texts)
    ]


TRAIN = _rows("courier_parcel", "c1", ["Aapka parcel customs mein hai.", "Fine bharna hoga."])
VAL = _rows("kyc_expiry", "k1", ["Aapka KYC expire ho gaya hai."])
SEEN_TEST = _rows("courier_parcel", "c1", ["Aapka parcel customs mein hai.", "Fine bharna hoga."])
UNSEEN_TEST = _rows("income_tax_refund", "t1", ["Aapka refund approve hua hai.", "Link par click karein."])


@pytest.fixture()
def trained_on() -> Dict[str, Any]:
    return provenance.build({"train": TRAIN, "val": VAL}, source="test fixture")


# --- the record --------------------------------------------------------------


def test_a_text_is_the_same_text_whatever_its_whitespace() -> None:
    assert provenance.text_key("Fine  bharna\thoga. ") == provenance.text_key("Fine bharna hoga.")


def test_case_and_punctuation_are_part_of_what_the_model_saw() -> None:
    """Folding them would call two different training examples one example,
    and report a leak that is not there."""
    assert provenance.text_key("Fine bharna hoga.") != provenance.text_key("fine bharna hoga")


def test_validation_counts_as_seen(trained_on: Dict[str, Any]) -> None:
    """A model early-stopped on a split has been selected on it."""
    assert provenance.overlap(trained_on, VAL)["overlap_turns"] == len(VAL)


def test_the_record_survives_a_round_trip(tmp_path: Path, trained_on: Dict[str, Any]) -> None:
    provenance.write(trained_on, tmp_path)
    assert provenance.load(tmp_path) == trained_on


def test_a_record_edited_by_hand_is_not_a_record(tmp_path: Path, trained_on: Dict[str, Any]) -> None:
    """Dropping the inconvenient keys is the obvious way to make a leak pass.
    The digest is what makes that the same as having no record."""
    doctored = dict(trained_on, text_keys=trained_on["text_keys"][1:])
    provenance.write(doctored, tmp_path)
    assert provenance.load(tmp_path) is None


@pytest.mark.parametrize("content", ["", "not json", "[]", '{"schema": 99, "text_keys": ["a"]}'])
def test_an_unusable_record_is_no_record(tmp_path: Path, content: str) -> None:
    (tmp_path / provenance.PROVENANCE_NAME).write_text(content)
    assert provenance.load(tmp_path) is None


def test_the_summary_carries_no_keys(trained_on: Dict[str, Any]) -> None:
    assert "text_keys" not in provenance.summary(trained_on)
    assert provenance.summary(trained_on)["n_texts"] == 3


# --- the verdict -------------------------------------------------------------


def test_a_checkpoint_trained_on_the_test_split_is_refused(trained_on: Dict[str, Any]) -> None:
    """B-01, in miniature: two of four test turns were training data."""
    ok, reason, check = provenance.leak_verdict(trained_on, SEEN_TEST + UNSEEN_TEST)
    assert ok is False
    assert "2 of the 4 test turns" in reason
    assert check is not None
    assert check["overlap_turns"] == 2 and check["overlap_calls"] == 1
    assert check["by_archetype"] == {
        "courier_parcel": {"overlap": 2, "turns": 2},
        "income_tax_refund": {"overlap": 0, "turns": 2},
    }


def test_one_leaked_turn_is_enough(trained_on: Dict[str, Any]) -> None:
    """Zero tolerance. A gate that forgives a little overlap has to be told how
    much, and nobody can say."""
    ok, _reason, check = provenance.leak_verdict(trained_on, UNSEEN_TEST + SEEN_TEST[:1])
    assert ok is False and check is not None and check["overlap_turns"] == 1


def test_a_checkpoint_with_no_record_is_refused() -> None:
    """It cannot show what it was trained on, so it cannot show it was held out.
    This is the state of every checkpoint trained before the record existed."""
    ok, reason, check = provenance.leak_verdict(None, UNSEEN_TEST)
    assert ok is False and check is None
    assert provenance.PROVENANCE_NAME in reason


def test_a_checkpoint_held_out_from_the_test_split_may_be_scored(trained_on: Dict[str, Any]) -> None:
    ok, reason, check = provenance.leak_verdict(trained_on, UNSEEN_TEST)
    assert ok is True
    assert check is not None and check["overlap_turns"] == 0
    assert "none of the 2 test turns" in reason


def test_the_real_split_is_judged_against_the_split_the_weights_came_from() -> None:
    """The actual incident, from git history rather than from a fixture.

    The served weights were trained at 85a2aee. Scored against the test split
    as it is now, 311 of 423 turns are theirs. Skipped where history is shallow
    (a CI checkout), because the claim is about this repository's past.
    """
    try:
        trained = provenance.build(
            {s: provenance.rows_at_rev("85a2aee", s) for s in ("train", "val")},
            source="git 85a2aee",
        )
    except Exception:  # shallow clone, or no git at all
        pytest.skip("commit 85a2aee is not reachable in this checkout")
    test_rows = [
        json.loads(line)
        for line in (ROOT / "ml/data/processed/test.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ok, reason, check = provenance.leak_verdict(trained, test_rows)
    assert ok is False
    assert check is not None
    assert (check["overlap_turns"], check["n_test"]) == (311, 423)
    assert "311 of the 423 test turns" in reason
    leaked = {a for a, n in check["by_archetype"].items() if n["overlap"]}
    assert leaked == {"courier_parcel", "loan_app_harassment", "refund_overpayment"}


# --- the comparison file -----------------------------------------------------


def test_both_sides_agree_on_the_shape_of_the_comparison() -> None:
    """`ml/` writes it and `services/` reads it; neither imports the other."""
    assert provenance.COMPARISON_SCHEMA == classifier_mod.COMPARISON_SCHEMA


def test_a_comparison_cannot_be_given_an_invented_status() -> None:
    with pytest.raises(ValueError):
        provenance.comparison_record(status="probably fine", reason="", n_test=1, results={})


SCORES = {"macro_f1": 0.4, "weighted_f1": 0.4}


def _comparison(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: Any) -> None:
    path = tmp_path / "backend_comparison.json"
    if content is not None:
        path.write_text(content if isinstance(content, str) else json.dumps(content))
    monkeypatch.setattr(classifier_mod, "COMPARISON_PATH", path)
    monkeypatch.delenv("AEGIS_CLASSIFIER", raising=False)
    monkeypatch.delenv("PRESAGE_CLASSIFIER", raising=False)


def _valid(fused: float, lexical: float, overlap: int = 0) -> Dict[str, Any]:
    return provenance.comparison_record(
        status="valid",
        reason="none of the 100 test turns is in the checkpoint's training data",
        n_test=100,
        results={
            "lexical": {"macro_f1": lexical, "weighted_f1": lexical},
            "muril": {"macro_f1": 0.99, "weighted_f1": 0.99},
            "fused": {"macro_f1": fused, "weighted_f1": fused},
        },
        leak_check={"n_test": 100, "overlap_turns": overlap},
    )


REFUSED = provenance.comparison_record(
    status="refused",
    reason="311 of the 423 test turns are in the checkpoint's own training data",
    n_test=423,
    results={"lexical": SCORES},
    leak_check={"n_test": 423, "overlap_turns": 311},
)

#: The file committed to this repository until T-05: schema 1, the leak itself.
THE_LEAKED_FILE = {
    "lexical": {"macro_f1": 0.3748, "weighted_f1": 0.3812},
    "muril": {"macro_f1": 0.7672, "weighted_f1": 0.8067},
}


# --- serving: what is promoted -----------------------------------------------


def test_a_clean_comparison_the_fusion_wins_is_promoted(tmp_path, monkeypatch) -> None:
    _comparison(tmp_path, monkeypatch, _valid(fused=0.61, lexical=0.43))
    promote, reason = classifier_mod._checkpoint_is_better()
    assert promote is True
    assert reason == "measured better (fused 0.610 vs lexical 0.430)"


def test_promotion_is_decided_on_the_model_that_would_serve(tmp_path, monkeypatch) -> None:
    """MuRIL alone scores 0.99 in this record and the fusion loses. The API
    serves the fusion, so the fusion is what has to win."""
    _comparison(tmp_path, monkeypatch, _valid(fused=0.30, lexical=0.43))
    promote, reason = classifier_mod._checkpoint_is_better()
    assert promote is False
    assert reason == "measured worse (fused 0.300 vs lexical 0.430)"


def test_the_leaked_comparison_no_longer_promotes_anything(tmp_path, monkeypatch) -> None:
    """The regression test for B-01: this exact file promoted the checkpoint."""
    _comparison(tmp_path, monkeypatch, THE_LEAKED_FILE)
    promote, reason = classifier_mod._checkpoint_is_better()
    assert promote is False
    assert "predates the leak check" in reason


def test_a_refused_comparison_does_not_promote_and_says_why(tmp_path, monkeypatch) -> None:
    _comparison(tmp_path, monkeypatch, REFUSED)
    promote, reason = classifier_mod._checkpoint_is_better()
    assert promote is False
    assert reason == "not promoted: 311 of the 423 test turns are in the checkpoint's own training data"


def test_no_comparison_no_longer_means_trust_the_checkpoint(tmp_path, monkeypatch) -> None:
    """It used to. An unmeasured model is the one case where nothing at all
    supports loading it."""
    _comparison(tmp_path, monkeypatch, None)
    promote, reason = classifier_mod._checkpoint_is_better()
    assert promote is False and "no comparison on file" in reason


@pytest.mark.parametrize("content", ["", "{not json", "[]", '{"schema": 2}'])
def test_an_unreadable_comparison_does_not_promote(tmp_path, monkeypatch, content: str) -> None:
    _comparison(tmp_path, monkeypatch, content)
    assert classifier_mod._checkpoint_is_better()[0] is False


def test_a_record_that_calls_itself_valid_while_carrying_a_leak_is_not_believed(
    tmp_path, monkeypatch
) -> None:
    _comparison(tmp_path, monkeypatch, _valid(fused=0.9, lexical=0.4, overlap=7))
    promote, reason = classifier_mod._checkpoint_is_better()
    assert promote is False and "clean leak check" in reason


def test_a_valid_record_with_no_leak_check_is_not_believed(tmp_path, monkeypatch) -> None:
    record = _valid(fused=0.9, lexical=0.4)
    record["leak_check"] = None
    _comparison(tmp_path, monkeypatch, record)
    assert classifier_mod._checkpoint_is_better()[0] is False


def test_an_operator_can_still_force_either_backend(tmp_path, monkeypatch) -> None:
    _comparison(tmp_path, monkeypatch, REFUSED)
    monkeypatch.setenv("AEGIS_CLASSIFIER", "muril")
    assert classifier_mod._checkpoint_is_better() == (True, "forced by AEGIS_CLASSIFIER")
    monkeypatch.setenv("AEGIS_CLASSIFIER", "lexical")
    assert classifier_mod._checkpoint_is_better() == (False, "forced by AEGIS_CLASSIFIER")


# --- serving: what is shown --------------------------------------------------


def test_an_unchecked_figure_is_not_shown_beside_the_model(tmp_path, monkeypatch) -> None:
    """The leaked file's numbers must not reach the model card."""
    _comparison(tmp_path, monkeypatch, THE_LEAKED_FILE)
    assert classifier_mod.comparison_scores() == {}
    assert "predates the leak check" in classifier_mod.evaluation_protocol()


def test_a_refusal_shows_the_lexical_figure_alone_and_explains_itself(tmp_path, monkeypatch) -> None:
    _comparison(tmp_path, monkeypatch, REFUSED)
    assert classifier_mod.comparison_scores() == {"lexical": SCORES}
    protocol = classifier_mod.evaluation_protocol()
    assert "refused to score" in protocol
    assert "311 of the 423 test turns" in protocol


def test_a_valid_comparison_says_the_leak_check_passed(tmp_path, monkeypatch) -> None:
    _comparison(tmp_path, monkeypatch, _valid(fused=0.6, lexical=0.4))
    assert set(classifier_mod.comparison_scores()) == {"lexical", "muril", "fused"}
    assert "Leak check passed" in classifier_mod.evaluation_protocol()


def test_nothing_on_file_says_so(tmp_path, monkeypatch) -> None:
    _comparison(tmp_path, monkeypatch, None)
    assert classifier_mod.comparison_scores() == {}
    assert "No comparison on file" in classifier_mod.evaluation_protocol()


# --- the running service -----------------------------------------------------


def test_a_checkpoint_the_gate_refused_is_not_loaded_and_the_service_says_why(
    tmp_path, monkeypatch
) -> None:
    """End to end, on the served endpoints, with a checkpoint present.

    The directory below is what a full checkout has — a `config.json` beside
    weights — and the comparison beside it is a refusal. The lexical model must
    serve; that must not be reported as a fault, because it is what every
    machine now serves; and both the health check and the model card must give
    the reason.
    """
    model_dir = tmp_path / "stage-classifier"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}")
    _comparison(tmp_path, monkeypatch, REFUSED)
    monkeypatch.setattr(classifier_mod, "settings", SimpleNamespace(classifier_dir=model_dir))
    monkeypatch.setattr(classifier_mod, "_cached", None)
    monkeypatch.setattr(classifier_mod, "selection_reason", "not yet loaded")
    monkeypatch.setattr(classifier_mod, "serving_is_fallback", False)

    client = TestClient(app)
    health = client.get("/api/health").json()
    clf = health["classifier"]
    assert clf["backend"] == "lexical"
    assert clf["loaded"] is False
    assert "311 of the 423 test turns" in clf["reason"]
    assert clf["comparison"] == {"lexical": SCORES}
    # Not a fallback: the gate did its job. `serving_best` stays true and the
    # degraded tag stays off, exactly as when lexical wins a valid comparison.
    assert clf["serving_best"] is True
    assert "clf:lexical_fallback" not in health["degraded"]

    card = client.get("/api/model/card").json()
    assert card["active_backend"] == "lexical"
    assert card["evaluation"]["scores"] == {"lexical": SCORES}
    assert "refused to score" in card["evaluation"]["protocol"]
    assert "311 of the 423 test turns" in card["evaluation"]["selection"]


# --- the two scripts ---------------------------------------------------------


def _source(relative: str) -> ast.Module:
    return ast.parse((ROOT / relative).read_text(encoding="utf-8"))


def _calls(tree: ast.Module) -> set[str]:
    return {
        f"{node.func.value.id}.{node.func.attr}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
    }


def test_training_leaves_the_record_beside_the_weights() -> None:
    """`train.py` needs torch and two CPU-hours, so it cannot run here. What can
    be checked is that it still writes the record — the thing whose absence
    made B-01 undetectable."""
    calls = _calls(_source("ml/training/train.py"))
    assert {"provenance.build", "provenance.write"} <= calls


def test_the_gate_asks_before_it_scores() -> None:
    """Same limit: `eval_backends.py` loads the checkpoint. It must consult the
    verdict, and must not be able to write a comparison any other way."""
    tree = _source("ml/evaluation/eval_backends.py")
    calls = _calls(tree)
    assert {"provenance.load", "provenance.leak_verdict", "provenance.comparison_record"} <= calls
    assert "json.dumps" in calls  # written once, in `_write_comparison`
    writers = [
        fn.name
        for fn in ast.walk(tree)
        if isinstance(fn, ast.FunctionDef)
        and any(
            isinstance(n, ast.Attribute) and n.attr == "write_text" for n in ast.walk(fn)
        )
    ]
    assert writers == ["_write_comparison"]


# --- the manifest ------------------------------------------------------------


def test_a_refused_manifest_still_names_the_weights_it_is_about(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text("{}")
    built = manifest.build(
        tmp_path,
        results={"lexical": SCORES},
        split="test",
        n_examples=423,
        status="refused",
        reason=REFUSED["reason"],
        leak_check=REFUSED["leak_check"],
    )
    assert built["schema"] == manifest.MANIFEST_SCHEMA == 2
    assert built["fingerprint"]["files"]["config.json"]["sha256"]
    assert built["evaluation"]["status"] == "refused"
    assert "muril" not in built["evaluation"]["results"]
