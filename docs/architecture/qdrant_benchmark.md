# Qdrant Benchmarking Guide

This document describes how to run the Qdrant benchmarking harness included in `scripts/qdrant_benchmark.py`.

Prerequisites
- Local Qdrant running via `docker-compose` (see `infrastructure/docker-compose.yml`) or configure `QDRANT_MODE=memory`.
- Python dependencies installed (see `requirements.txt` which includes `qdrant-client`).

Quick run

```bash
python3 scripts/qdrant_benchmark.py --points 5000 --dim 1536
```

Notes
- Tune `QDRANT_UPSERT_BATCH_SIZE` and `QDRANT_WRITE_CONCURRENCY` in environment or `backend/core/config.py`.
- The harness uses the existing `VectorStore` upsert path to measure real-world behavior (including chunking and concurrency).

Next steps
- Add a small CSV output option for results to plot latency vs batch size.
- Integrate a simple load generator to measure ingestion under concurrent producers.
