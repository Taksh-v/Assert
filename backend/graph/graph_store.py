import logging
from typing import List, Dict, Any, Optional
from backend.core.config import get_settings
from backend.core.async_utils import run_blocking
from backend.core.retry import retry_sync

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
                from neo4j import GraphDatabase  # lazy import
                self.driver = GraphDatabase.driver(
                    self.uri, 
                    auth=(self.user, self.password)
                )
                # Verify connection
                self.driver.verify_connectivity()
                logger.info(f"Connected to Memgraph at {self.uri}")
            except ImportError:
                logger.warning("neo4j driver not available — graph features disabled")
            except Exception as e:
                logger.error(f"Failed to connect to Memgraph: {e}")
                self.driver = None

    def add_event_node(self, document_id: str, event_data: Dict[str, Any]):
        """
        Layer 13: Temporal Intelligence.
        Adds an Event node and links it to the document and related entities.
        """
        # Offload the graph write to a threadpool to avoid blocking the event loop.
        return run_blocking(self._add_event_node_blocking, document_id, event_data)


    def _add_event_node_blocking(self, document_id: str, event_data: Dict[str, Any]):
        """Blocking implementation of add_event_node. Intended to be run via `run_blocking`."""
        if not self.driver:
            self.connect()
        if not self.driver:
            return

        with self.driver.session() as session:
            title = event_data.get("title", "Unknown Event")
            e_type = event_data.get("type", "milestone").upper()
            ts = event_data.get("timestamp")
            related = event_data.get("related_entities", [])

            # 1. Create Event node
            query = f"""
            MATCH (d:Document {{id: $doc_id}})
            MERGE (ev:Event {{title: $title, timestamp: $ts}})
            SET ev.type = $type, ev.updated_at = timestamp()
            MERGE (d)-[:REPORTED]->(ev)
            """
            session.run(query, doc_id=document_id, title=title, ts=str(ts), type=e_type)

            # 2. Link to related entities
            for ent_name in related:
                link_query = f"""
                MATCH (ev:Event {{title: $title, timestamp: $ts}})
                MATCH (e {{name: $ent_name}})
                WHERE e:Employee OR e:Project OR e:Team OR e:API OR e:Service OR e:Entity
                MERGE (ev)-[:INVOLVES]->(e)
                """
                session.run(link_query, title=title, ts=str(ts), ent_name=ent_name)

    # Add retries to blocking graph operations to improve resilience to transient errors
    _add_event_node_blocking = retry_sync(max_attempts=3, initial_delay=0.1)(_add_event_node_blocking)

    def close(self):
        """Close connection."""
        # Close driver in threadpool to avoid blocking
        return run_blocking(self._close_blocking)


    def _close_blocking(self):
        if self.driver:
            try:
                self.driver.close()
            finally:
                self.driver = None
    _close_blocking = retry_sync(max_attempts=2, initial_delay=0.05)(_close_blocking)

    def add_document_node(self, workspace_id: str, document_id: str, title: str, source_url: str, is_active: bool = True):
        """Create a Version-Aware Document node in the graph."""
        return run_blocking(self._add_document_node_blocking, workspace_id, document_id, title, source_url, is_active)


    def _add_document_node_blocking(self, workspace_id: str, document_id: str, title: str, source_url: str, is_active: bool = True):
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

    _add_document_node_blocking = retry_sync(max_attempts=3, initial_delay=0.1)(_add_document_node_blocking)

    def add_entities_and_relationships(self, document_id: str, entities: List[Dict[str, Any]]):
        """
        Layer 10: Advanced Entity Resolution.
        Categorizes entities into specialized nodes (Employee, Project, API, SOP, etc.) 
        and links them with weighted relationships.
        """
        return run_blocking(self._add_entities_and_relationships_blocking, document_id, entities)


    def _add_entities_and_relationships_blocking(self, document_id: str, entities: List[Dict[str, Any]]):
        if not self.driver:
            self.connect()
        if not self.driver:
            return

        with self.driver.session() as session:
            for entity in entities:
                name = entity["name"]
                category = entity.get("category", "GENERAL").upper()
                e_type = entity.get("type", "concept")
                relationship = entity.get("relationship", "MENTIONS").upper()
                confidence = entity.get("confidence", 0.5)

                # Determine Label based on category and type
                label = "Entity"
                if category == "ORGANIZATIONAL":
                    if "person" in e_type.lower() or "employee" in e_type.lower():
                        label = "Employee"
                    elif "team" in e_type.lower() or "dept" in e_type.lower():
                        label = "Team"
                    else:
                        label = "OrgUnit"
                elif category == "TECHNICAL":
                    if "api" in e_type.lower():
                        label = "API"
                    elif "repo" in e_type.lower():
                        label = "Repository"
                    elif "db" in e_type.lower() or "database" in e_type.lower():
                        label = "Database"
                    else:
                        label = "Service"
                elif category == "BUSINESS":
                    if "customer" in e_type.lower():
                        label = "Customer"
                    elif "product" in e_type.lower():
                        label = "Product"
                    else:
                        label = "BizEntity"
                elif category == "OPERATIONAL":
                    if "incident" in e_type.lower():
                        label = "Incident"
                    elif "sop" in e_type.lower() or "workflow" in e_type.lower():
                        label = "SOP"
                    elif "meeting" in e_type.lower():
                        label = "Meeting"
                    else:
                        label = "Process"

                # 1. Create/Merge specialized node
                # 2. Link Document to Entity
                # 3. Store confidence and weight
                query = f"""
                MATCH (d:Document {{id: $doc_id}})
                MERGE (e:{label} {{name: $name}})
                SET e.type = $type, 
                    e.category = $category,
                    e.updated_at = timestamp()
                MERGE (d)-[r:{relationship}]->(e)
                SET r.weight = COALESCE(r.weight, 0) + 1,
                    r.confidence = $confidence,
                    r.updated_at = timestamp()
                """
                session.run(query, doc_id=document_id, name=name, type=e_type, category=category, confidence=confidence)
        
    _add_entities_and_relationships_blocking = retry_sync(max_attempts=3, initial_delay=0.1)(_add_entities_and_relationships_blocking)

    def get_context(self, entity_name: str) -> Dict[str, Any]:
        """Alias for get_knowledge_cluster for unified retrieval API."""
        if not self.driver:
            return {"relationships": []}
        return self.get_knowledge_cluster(entity_name)

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
