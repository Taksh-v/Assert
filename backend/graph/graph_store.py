import logging
from typing import List, Dict, Any, Optional
from neo4j import GraphDatabase
from backend.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class GraphStore:
    """
    Interface for Memgraph (Graph Database).
    Stores entities and relationships extracted from ingested documents.
    """

    def __init__(self):
        self.uri = settings.memgraph_url
        self.user = settings.memgraph_user
        self.password = settings.memgraph_password
        self.driver = None

    def connect(self):
        """Establish connection to Memgraph."""
        if not self.driver:
            try:
                self.driver = GraphDatabase.driver(
                    self.uri, 
                    auth=(self.user, self.password)
                )
                # Verify connection
                self.driver.verify_connectivity()
                logger.info(f"Connected to Memgraph at {self.uri}")
            except Exception as e:
                logger.error(f"Failed to connect to Memgraph: {e}")
                self.driver = None

    def close(self):
        """Close connection."""
        if self.driver:
            self.driver.close()
            self.driver = None

    def add_document_node(self, workspace_id: str, document_id: str, title: str, source_url: str, is_active: bool = True):
        """Create a Version-Aware Document node in the graph."""
        if not self.driver:
            self.connect()
        if not self.driver:
            return

        query = """
        MERGE (d:Document {id: $doc_id})
        SET d.title = $title, 
            d.source_url = $url, 
            d.workspace_id = $ws_id,
            d.is_active = $active,
            d.updated_at = timestamp()
        RETURN d
        """
        with self.driver.session() as session:
            session.run(query, doc_id=document_id, title=title, url=source_url, ws_id=workspace_id, active=is_active)

    def add_entities_and_relationships(self, document_id: str, entities: List[Dict[str, Any]]):
        """
        Layer 10: Advanced Entity Resolution.
        Categorizes entities into specialized nodes (Employee, Project, Tech) and links them.
        """
        if not self.driver:
            self.connect()
        if not self.driver:
            return

        with self.driver.session() as session:
            for entity in entities:
                name = entity["name"]
                e_type = entity.get("type", "General")
                relationship = entity.get("relationship", "MENTIONS")
                
                # Determine Label based on type (Layer 10 specialized nodes)
                label = "Entity"
                if e_type.lower() in ["person", "employee", "user"]:
                    label = "Employee"
                elif e_type.lower() in ["project", "product"]:
                    label = "Project"
                elif e_type.lower() in ["dept", "department", "team"]:
                    label = "Team"
                
                # 1. Create/Merge specialized node
                # 2. Link Document to Entity
                query = f"""
                MATCH (d:Document {{id: $doc_id}})
                MERGE (e:{label} {{name: $name}})
                SET e.type = $type, e.updated_at = timestamp()
                MERGE (d)-[r:{relationship}]->(e)
                SET r.weight = COALESCE(r.weight, 0) + 1
                """
                session.run(query, doc_id=document_id, name=name, type=e_type)

    def get_knowledge_cluster(self, entity_name: str) -> Dict[str, Any]:
        """
        Layer 10: Multi-hop Context Expansion.
        Only traverses relationships linked to ACTIVE documents.
        """
        if not self.driver:
            self.connect()
        if not self.driver:
            return {}

        query = """
        MATCH (center {name: $name})
        OPTIONAL MATCH (center)-[r]-(neighbor)
        // Ensure neighbor or source document is ACTIVE
        WHERE (NOT (neighbor:Document) OR neighbor.is_active = True)
        RETURN labels(center) as center_labels,
               neighbor.name as name, 
               labels(neighbor) as type, 
               type(r) as relationship
        LIMIT 20
        """
        with self.driver.session() as session:
            result = session.run(query, name=entity_name)
            data = result.data()
            if not data:
                return {}
            
            return {
                "concept": entity_name,
                "labels": data[0]["center_labels"],
                "relationships": [
                    {"name": r["name"], "type": r["type"], "rel": r["relationship"]}
                    for r in data if r["name"]
                ]
            }

    def search_expert(self, project_name: str) -> List[Dict[str, Any]]:
        """
        Layer 10: Expertise Discovery.
        Finds experts via ACTIVE documents only.
        """
        query = """
        MATCH (p:Project {name: $project})<-[:MENTIONS|WORKS_ON]-(d:Document {is_active: True})-[:MENTIONS|OWNED_BY]->(e:Employee)
        RETURN e.name as expert, count(d) as document_count
        ORDER BY document_count DESC
        LIMIT 5
        """
        if not self.driver: self.connect()
        with self.driver.session() as session:
            result = session.run(query, project=project_name)
            return [record.data() for record in result]
