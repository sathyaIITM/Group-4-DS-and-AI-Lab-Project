"""Phase 1 (domain decision): data conversion, client, calibration and scoring."""

import json
from pathlib import Path

import httpx
import numpy as np
import pytest

from analyst.decisions import phase1
from analyst.decisions.kev_questions import DOMAIN_OPTIONS, QUESTIONS
from analyst.decisions.system_one import ChoiceQuestion, SystemOneClient
from analyst.evaluation import domain_eval

SOURCE = Path(__file__).resolve().parents[1] / "data" / "splits" / "kev" / "dev_synthetic.v1.jsonl"
LABELS = list(DOMAIN_OPTIONS)


def _rows(correct_share: float, confidence: float, n: int = 200) -> list[dict]:
    """Predictions with a chosen accuracy and a fixed stated confidence."""
    rng = np.random.default_rng(1)
    rows = []
    for i in range(n):
        truth = LABELS[i % len(LABELS)]
        wrong = LABELS[(LABELS.index(truth) + 1) % len(LABELS)]
        top = truth if rng.random() < correct_share else wrong
        rest = (1 - confidence) / (len(LABELS) - 1)
        probabilities = {label: (confidence if label == top else rest) for label in LABELS}
        rows.append(
            {
                "id": f"r{i}",
                "label": truth,
                "predicted": top,
                "probabilities": probabilities,
                "latency_s": 0.1,
            }
        )
    return rows


@pytest.mark.skipif(not SOURCE.exists(), reason="routing split not present")
def test_conversion_keeps_state_and_canonical_domain_question() -> None:
    first = next(phase1.read_jsonl(SOURCE))
    converted = phase1.to_domain_record(first)
    assert set(converted["questions"]) == {"domain"}
    assert converted["state"] == first["state"]
    instructions, criteria = QUESTIONS["domain"]
    assert converted["questions"]["domain"]["instructions"] == instructions
    assert converted["questions"]["domain"]["criteria"] == criteria
    assert converted["_meta"]["phase"] == phase1.PHASE


def test_conversion_rejects_changed_question_text() -> None:
    record = {
        "state": {},
        "questions": {"domain": {"instructions": "x", "criteria": {}, "label": "labour"}},
        "_meta": {"id": "t1"},
    }
    with pytest.raises(ValueError, match="canonical"):
        phase1.to_domain_record(record)


def test_subsample_covers_every_label_and_is_reproducible() -> None:
    records = [
        {"questions": {"domain": {"label": LABELS[i % len(LABELS)]}}, "_meta": {"id": str(i)}}
        for i in range(400)
    ]
    first, second = phase1.subsample(records, 40, 0), phase1.subsample(records, 40, 0)
    assert first == second
    assert len(first) == 40
    assert {r["questions"]["domain"]["label"] for r in first} == set(LABELS)


def test_client_parses_a_choice_answer() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["questions"]["domain"]["type"] == "choice"
        probabilities = dict.fromkeys(LABELS, 0.0) | {"labour": 0.9, "rainfall": 0.1}
        answer = {"choice": "labour", "confidence": 0.9, "probabilities": probabilities}
        return httpx.Response(200, json={"answers": {"domain": answer}})

    client = SystemOneClient("http://test", "kev-latest")
    client._client = httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler))
    result = client.ask_choice(
        {"user_message": "x"}, {"domain": ChoiceQuestion.model_validate(phase1.domain_question())}
    )
    assert result.answers["domain"].choice == "labour"
    assert result.latency_s >= 0


def test_temperature_scaling_keeps_the_winner_and_normalises() -> None:
    probabilities = domain_eval.probability_matrix(_rows(0.8, 0.9, 40))
    for temperature in (0.5, 1.0, 3.0):
        scaled = domain_eval.apply_temperature(probabilities, temperature)
        assert np.allclose(scaled.sum(axis=1), 1.0)
        assert (scaled.argmax(axis=1) == probabilities.argmax(axis=1)).all()


def test_fit_temperature_softens_an_overconfident_model() -> None:
    rows = _rows(0.6, 0.95)  # 60% right but 95% sure
    fitted = domain_eval.fit_temperature(
        domain_eval.probability_matrix(rows), domain_eval.label_index(rows)
    )
    assert fitted > 1.0
    raw, calibrated = domain_eval.score(rows, 1.0), domain_eval.score(rows, fitted)
    assert calibrated["ece"] < raw["ece"]
    assert calibrated["nll"] < raw["nll"]
    assert calibrated["accuracy"] == raw["accuracy"]


def test_score_of_a_perfect_prediction() -> None:
    rows = _rows(1.0, 0.99)
    result = domain_eval.score(rows)
    assert result["accuracy"] == 1.0
    assert result["macro_f1"] == pytest.approx(1.0)
    assert result["brier"] < 0.01


def test_paired_bootstrap_detects_a_clear_gain_and_checks_alignment() -> None:
    weak, strong = _rows(0.4, 0.9), _rows(0.95, 0.9)
    for a, b in zip(weak, strong, strict=True):  # same items, same order
        b["id"], b["label"] = a["id"], a["label"]
    result = domain_eval.paired_bootstrap(weak, strong)
    assert result["difference"] > 0.3
    assert result["ci95"][0] > 0
    strong[0]["id"] = "other"
    with pytest.raises(ValueError, match="same items"):
        domain_eval.paired_bootstrap(weak, strong)
