"""RAG proof of concept: retrieval maths and the graph's paths, with a scripted LLM.

The embedder is replaced by a hashed bag of words and the LLM by fixed replies, so these
tests need no network, model download or database.
"""

import hashlib
from typing import Any

import numpy as np
import pytest

from analyst.inference.llm import LlmCall, parse_json
from analyst.pipelines import rag_poc
from analyst.retrieval.hybrid import BM25, HybridIndex, rrf, tokenize
from analyst.retrieval.knowledge import build_entries

pytestmark = pytest.mark.skipif(
    not rag_poc.obs_path("plfs_state_ur_usual_status").exists(),
    reason="processed obs tables not present",
)


def fake_embed(self: HybridIndex, texts: Any, query: bool = False) -> np.ndarray:
    vectors = np.zeros((len(texts), 256))
    for row, text in enumerate(texts):
        for token in tokenize(text):
            vectors[row, int(hashlib.sha256(token.encode()).hexdigest(), 16) % 256] += 1.0
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)


class ScriptedLlm:
    model = "scripted"

    def __init__(self, replies: dict[str, dict[str, Any]]) -> None:
        self.replies = replies
        self.purposes: list[str] = []

    def json_call(self, purpose: str, system: str, user: str) -> tuple[dict[str, Any], LlmCall]:
        self.purposes.append(purpose)
        return self.replies[purpose], LlmCall(purpose, 0.0, 10, 5)


@pytest.fixture(scope="module")
def index() -> HybridIndex:
    mp = pytest.MonkeyPatch()
    mp.setattr(HybridIndex, "embed", fake_embed)
    idx = HybridIndex(build_entries(), database_url=None)
    idx.build()
    yield idx
    mp.undo()


TA_QUESTION = "Which state had the highest unemployment rate in 2019-20?"
TA_INTENT = {
    "action": "answer",
    "dataset_id": "plfs_state_ur_usual_status",
    "indicator_ids": ["ur_usual_ps_ss"],
    "analysis_type": "ranking",
    "periods": ["2019-20"],
    "places": [],
    "other_filters": {},
}
TA_SQL = (
    "SELECT geo_name, period_label, value, unit FROM obs_plfs_state_ur_usual_status "
    "WHERE indicator_id = 'ur_usual_ps_ss' AND geo_level = 'state' "
    "AND period_label = '2019-20' ORDER BY value DESC LIMIT 1"
)


def test_bm25_and_rrf() -> None:
    bm25 = BM25(["unemployment rate by state", "monsoon rainfall in mm"])
    scores = bm25.scores("state unemployment")
    assert scores[0] > 0 and scores[1] == 0
    fused = rrf([["a", "b"], ["b", "c"]])
    assert max(fused, key=fused.get) == "b"


def test_parse_json_accepts_fenced_reply() -> None:
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_ta_question_is_answered_with_supported_narration(index: HybridIndex) -> None:
    llm = ScriptedLlm(
        {
            "intent": TA_INTENT,
            "sql": {"sql": TA_SQL},
            "narration": {"answer": "Nagaland had the highest rate in 2019-20, at 25.7 per cent."},
        }
    )
    state = rag_poc.RagPipeline(index, llm).run(TA_QUESTION)
    assert state["tables"][0]["dataset_id"] == "plfs_state_ur_usual_status"
    assert any(c["id"] == "plfs_geography" for c in state["cards"])
    assert state["outcome"] == "answered"
    assert state["rows"][0][0] == "Nagaland"
    assert state["chart"].startswith("none")
    assert llm.purposes == ["intent", "sql", "narration"]
    case = {
        "expected_action": "answer",
        "expected_values": [25.7],
        "expected_entities": ["Nagaland"],
    }
    assert rag_poc.score(case, state)["success"]


def test_invented_figure_is_withheld(index: HybridIndex) -> None:
    llm = ScriptedLlm(
        {
            "intent": TA_INTENT,
            "sql": {"sql": TA_SQL},
            "narration": {"answer": "Nagaland had 25.7 per cent, up from 19.4 per cent."},
        }
    )
    state = rag_poc.RagPipeline(index, llm).run(TA_QUESTION)
    assert state["outcome"] == "answered_template"
    assert state["claims"]["unsupported"] == [19.4]


def test_period_outside_coverage_is_declined_by_code(index: HybridIndex) -> None:
    intent = TA_INTENT | {"analysis_type": "lookup", "periods": ["2022-23"], "places": ["Kerala"]}
    llm = ScriptedLlm({"intent": intent})
    state = rag_poc.RagPipeline(index, llm).run("Kerala unemployment rate in 2022-23?")
    assert state["outcome"] == "decline"
    assert state["coverage"]["by"] == "code"
    assert llm.purposes == ["intent"]


def test_write_attempt_is_rejected_then_repaired_once(index: HybridIndex) -> None:
    class Repairing(ScriptedLlm):
        def json_call(self, purpose: str, system: str, user: str) -> Any:
            if purpose == "sql":
                self.purposes.append(purpose)
                return {"sql": "DROP TABLE obs_plfs_state_ur_usual_status"}, LlmCall(
                    purpose, 0.0, 1, 1
                )
            return super().json_call(purpose, system, user)

    llm = Repairing(
        {
            "intent": TA_INTENT,
            "sql_repair": {"sql": TA_SQL},
            "narration": {"answer": "Nagaland, 25.7 per cent in 2019-20."},
        }
    )
    state = rag_poc.RagPipeline(index, llm).run(TA_QUESTION)
    assert state["sql_attempts"][0]["error"].startswith("SqlRejectedError")
    assert state["outcome"] == "answered"
    assert llm.purposes == ["intent", "sql", "sql_repair", "narration"]


def test_every_candidate_table_sends_indicators(index: HybridIndex) -> None:
    """Regression: a shared top-k let NFHS-5's 104 indicators crowd out the IMD indicator."""
    pipeline = rag_poc.RagPipeline(index, ScriptedLlm({}))
    q = "How much rain did Kerala get during the 2017 southwest monsoon, in millimetres?"
    state = pipeline.retrieve_tables({"question": q})
    context = pipeline.retrieve_context({"question": q, **state})
    sent = {(i["dataset_id"], i["indicator_id"]) for i in context["indicators"]}
    assert ("imd_subdivision_monthly_rainfall", "rainfall_mm") in sent
    nfhs = [d for d, _ in sent if d == "nfhs5_district_indicators"]
    assert len(nfhs) <= rag_poc.INDICATORS_PER_TABLE
