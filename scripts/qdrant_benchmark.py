#!/usr/bin/env python3
"""Qdrant benchmarking harness

Generates synthetic vectors and payloads and benchmarks `VectorStore.upsert_batch`
for various batch sizes and concurrency settings. Prints throughput and latency.

Usage:
    python3 scripts/qdrant_benchmark.py --points 10000 --dim 1536

This is best run against a local Qdrant instance (or memory mode) created via
`infrastructure/docker-compose.yml`.
"""
import time
import argparse
import random
import string
import json
from typing import List, Dict

from backend.core.vector_store import VectorStore
from backend.core.config import get_settings


def random_vector(dim: int) -> List[float]:
    return [random.random() for _ in range(dim)]


def random_payload(i: int) -> Dict:
    return {
        "text": "sample chunk " + str(i),
        "source_url": f"https://example.com/doc/{i}",
        "content_tier": 1,
    }


def run_benchmark(total_points: int, dim: int, batch_size: int = None, concurrency: int = None):
    settings = get_settings()
    if batch_size is None:
        batch_size = settings.qdrant_upsert_batch_size
    if concurrency is None:
        concurrency = settings.qdrant_write_concurrency

    store = VectorStore()
    # Ensure collection exists
    try:
        store.create_collection(vector_size=dim)
    except Exception as e:
        print("Warning: create_collection failed:", e)

    vectors = []
    payloads = []
    for i in range(total_points):
        vectors.append(random_vector(dim))
        payloads.append(random_payload(i))

    print(f"Starting upsert benchmark: points={total_points} dim={dim} batch_size={batch_size} concurrency={concurrency}")
    start = time.time()
    store.upsert_batch(workspace_id="benchmark", vectors=vectors, payloads=payloads)
    elapsed = time.time() - start
    print(f"Completed upsert: total_points={total_points} elapsed={elapsed:.2f}s throughput={total_points/elapsed:.2f} pts/s")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--points", type=int, default=1000)
    p.add_argument("--dim", type=int, default=1536)
    p.add_argument("--batch-size", type=int, default=None)
    p.add_argument("--concurrency", type=int, default=None)
    return p.parse_args()


def main():
    args = parse_args()
    run_benchmark(args.points, args.dim, args.batch_size, args.concurrency)


if __name__ == "__main__":
    main()
