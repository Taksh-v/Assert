import logging
from typing import List, Dict, Any
from backend.graph.graph_store import GraphStore

logger = logging.getLogger(__name__)

class GraphExpansionEngine:
    """
    Layer 10: Graph Expansion Engine.
    Traverses the knowledge graph to find structurally related context.
    """

    def __init__(self):
        self.graph_store = GraphStore()

    async def expand(self, entities: List[str], max_hops: int = 1) -> List[Dict[str, Any]]:
        """
        Traverse the graph starting from query entities to find related facts.
        """
        if not entities:
            return []
            
        results = []
        for entity in entities:
            try:
                # Fetch cluster from graph store
                cluster = self.graph_store.get_knowledge_cluster(entity)
                if cluster and cluster.get("relationships"):
                    # Format into factual blocks
                    fact_str = f"Knowledge about {entity}:\n"
                    for rel in cluster["relationships"]:
                        fact_str += f"- {entity} {rel['rel']} {rel['name']} ({rel['type']})\n"
                    
                    results.append({
                        "id": f"graph_{entity}",
                        "text": fact_str,
                        "source": "knowledge_graph",
                        "score": 0.85
                    })
            except Exception as e:
                logger.error(f"Graph expansion failed for {entity}: {e}")
                
        return results
