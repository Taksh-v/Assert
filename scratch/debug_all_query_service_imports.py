import os
import sys
import time

sys.path.insert(0, os.path.abspath("."))

def try_import(name):
    t0 = time.time()
    print(f"Importing {name}...")
    try:
        mod = __import__(name, fromlist=["*"])
        print(f"  Loaded {name} in {time.time()-t0:.4f}s")
    except Exception as e:
        print(f"  Failed to load {name}: {e}")

try_import("backend.query.adaptive_router")
try_import("backend.query.crag_verifier")
try_import("backend.query.generator")
try_import("backend.query.retriever")
try_import("backend.query.resolution")
try_import("backend.generation.stream_generator")
try_import("backend.reasoning.orchestrator")
try_import("backend.reasoning.supervisor")
try_import("backend.models.query_log")
try_import("backend.models.conversation")
try_import("backend.models.user")
try_import("backend.query.semantic_cache")

print("Now attempting to import query_service...")
t0 = time.time()
from backend.query.query_service import QueryService
print(f"Imported QueryService in {time.time()-t0:.4f}s")
