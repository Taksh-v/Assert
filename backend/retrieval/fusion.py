"""Ranking/fusion utilities for combining multiple retrieval signals.

This module centralizes fusion algorithms (RRF, reciprocal rank fusion) so
they live in the retrieval layer rather than inside the DB client wrapper.
"""
from typing import List, Dict, Any


def reciprocal_rank_fusion(
    vector_results: List[Dict[str, Any]],
    keyword_results: List[Dict[str, Any]],
    k: int = 60,
) -> List[Dict[str, Any]]:
    """Combine vector and keyword results using Reciprocal Rank Fusion.

    Returns combined list ordered by fused score. Preserves item metadata
    favoring vector result metadata when both sources include the same id.
    """
    scores = {}

    for rank, res in enumerate(vector_results):
        chunk_id = res["chunk_id"]
        scores[chunk_id] = scores.get(chunk_id, 0) + 1.0 / (rank + k)

    for rank, res in enumerate(keyword_results):
        chunk_id = res["chunk_id"]
        scores[chunk_id] = scores.get(chunk_id, 0) + 1.0 / (rank + k)

    all_items = {res["chunk_id"]: res for res in keyword_results + vector_results}

    sorted_ids = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    final_results = []
    for chunk_id, combined_score in sorted_ids:
        item = all_items[chunk_id]
        item["rrf_score"] = combined_score
        final_results.append(item)

    return final_results
