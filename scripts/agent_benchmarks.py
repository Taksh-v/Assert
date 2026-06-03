"""
Synthetic Agent Benchmarks — Task P5-3

Simulates end-to-end agentic flows and measures:
- Execution Latency
- Plan Accuracy (Decomposition)
- Skill Success Rate
"""

import asyncio
import time
import logging
import json
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from backend.orchestrator.orchestrator import Orchestrator
from backend.core.config import get_settings

settings = get_settings()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("benchmarks")

BENCHMARK_QUERIES = [
    {
        "name": "Invoice Lookup",
        "query": "What is the status of invoice INV-999?",
        "expected_skills": ["invoice_lookup"]
    },
    {
        "name": "FAQ / Knowledge",
        "query": "How do I reset my company password?",
        "expected_skills": ["internal_knowledge_search"]
    },
    {
        "name": "Complex Ticket Flow",
        "query": "My laptop screen is broken, please create a ticket for Acme Corp.",
        "expected_skills": ["customer_lookup", "ticket_creation"]
    }
]

async def run_benchmarks():
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    results = []
    
    async with async_session() as db:
        orch = Orchestrator(db)
        
        for case in BENCHMARK_QUERIES:
            logger.info(f"Running Benchmark: {case['name']}...")
            start_time = time.time()
            
            try:
                res = await orch.run(case['query'], workspace_id="benchmark_ws")
                latency = time.time() - start_time
                
                # Verify plan accuracy
                actual_skills = [s['skill'] for s in res.get('results', [])]
                # Normalize actual skills for comparison (faq_matching is a variant of internal_search)
                normalized_actual = ["internal_knowledge_search" if s == "faq_matching" else s for s in actual_skills]
                skills_match = all(s in normalized_actual for s in case['expected_skills'])
                
                results.append({
                    "name": case['name'],
                    "status": res['status'],
                    "latency_sec": round(latency, 2),
                    "skills_match": skills_match,
                    "actual_skills": actual_skills
                })
            except Exception as e:
                logger.error(f"Benchmark {case['name']} failed: {e}")
                results.append({
                    "name": case['name'],
                    "status": "exception",
                    "error": str(e)
                })

    # Summary
    print("\n" + "="*50)
    print("      AGENT BENCHMARK RESULTS")
    print("="*50)
    for r in results:
        indicator = "✅" if r['status'] == 'completed' and r.get('skills_match') else "❌"
        print(f"{indicator} {r['name']:25} | Latency: {r.get('latency_sec', 'N/A')}s | Skills: {r.get('actual_skills')}")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(run_benchmarks())
