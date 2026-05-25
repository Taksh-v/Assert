import pytest

from backend.retrieval.fusion import reciprocal_rank_fusion
from backend.retrieval.security import apply_security_filter


def make_res(cid, score=1.0, metadata=None):
    return {"chunk_id": cid, "text": f"doc {cid}", "score": score, "metadata": metadata or {}}


def test_rrf_combines_and_orders():
    vec = [make_res("a", 0.9), make_res("b", 0.8), make_res("c", 0.7)]
    kw = [make_res("b", 1.0), make_res("d", 0.5)]

    fused = reciprocal_rank_fusion(vector_results=vec, keyword_results=kw, k=60)

    # Expect fused contains all unique ids
    ids = [r["chunk_id"] for r in fused]
    assert set(ids) == {"a", "b", "c", "d"}

    # b should appear relatively high due to presence in both
    assert ids.index("b") <= ids.index("a")


def test_apply_security_filter_filters_out_docs_without_access():
    # Simulate two docs, one allowed and one denied
    results = [
        {"chunk_id": "allowed", "metadata": {"workspace_id": "ws1", "is_public": True}},
        {"chunk_id": "denied", "metadata": {"workspace_id": "ws1", "allowed_users": ["other_user"]}},
    ]

    # User 'alice' should only see 'allowed' (simulate production mode)
    filtered = apply_security_filter(results, user_id="alice", is_development=False)
    ids = [r["chunk_id"] for r in filtered]
    assert "allowed" in ids
    assert "denied" not in ids
