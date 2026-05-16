# ASSEST Knowledge Graph & Relationships Analysis (Layer 17)

## Current Implementation Status

### ✅ Working Components:
1. **Memgraph Integration** - Basic Neo4j driver integration
2. **Document-Entity Relationships** - Simple MENTIONS relationships
3. **Entity Nodes** - Name and type storage
4. **Query-time Graph Context** - 1-hop entity relationship search

### 🔴 Critical Issues Identified:

#### 1. **Oversimplified Relationship Model**
- Only generic "MENTIONS" relationship
- No relationship strength/confidence scoring
- Missing temporal aspects (when relationships were formed)

#### 2. **Limited Entity Representation**
- No entity disambiguation (e.g., multiple "John"s)
- Missing entity attributes (roles, departments, locations)
- No entity lifecycle state (active, inactive, deleted)

#### 3. **Absence of Higher-Order Relationships**
- No document-to-document relationships
- No cross-document entity linking
- Missing organizational hierarchy modeling

#### 4. **Insufficient Graph Traversal**
- Only 1-hop relationships explored
- No path-based queries for indirect relationships
- Missing centrality/importance scoring

## Enhanced Graph Architecture

### Proposed Schema:

#### Entity Types:
```cypher
// Enhanced Entity Node
(:Entity {
  id: String,
  name: String,
  canonical_name: String,
  type: String,  // Person, Org, Product, Concept, Location
  attributes: Map,
  created_at: DateTime,
  updated_at: DateTime,
  confidence: Float,
  source_count: Int
})

// Document Node
(:Document {
  id: String,
  title: String,
  type: String,
  created_at: DateTime,
  updated_at: DateTime,
  content_hash: String
})
```

#### Relationship Types:
```cypher
// Document-Entity Relationships
-[:MENTIONS {
  frequency: Int,
  positions: [Int],
  context_snippets: [String],
  confidence: Float,
  extraction_method: String
}]->

// Entity-Entity Relationships
-[:RELATES_TO {
  type: String,      // WORKS_AT, REPORTS_TO, PART_OF, DEPENDS_ON
  strength: Float,
  bidirectional: Boolean,
  evidence_count: Int,
  last_updated: DateTime
}]->

// Document Hierarchy
-[:REFERENCES {
  type: String,      // DEPENDS_ON, SUPERCEDES, CLARIFIES
  strength: Float
}]->

// Temporal Relationships
-[:TEMPORAL_CONTEXT {
  valid_from: DateTime,
  valid_to: DateTime,
  confidence: Float
}]->
```

### Advanced Graph Features:

#### 1. **Entity Disambiguation System**
```python
class EntityResolver:
    def __init__(self):
        self.entity_vectors = {}
        self.similarity_threshold = 0.85
        
    def resolve_entity(self, mention: str, context: str) -> Entity:
        # Use similarity and context to resolve ambiguous entities
        # Create canonical entities or link to existing ones
```

#### 2. **Relationship Inference Engine**
```cypher
// Infer implicit relationships
MATCH (e1:Entity)-[:MENTIONS]->(d1:Document)
MATCH (e2:Entity)-[:MENTIONS]->(d1:Document)
WHERE e1.type = "Person" AND e2.type = "Person"
MERGE (e1)-[r:COLLABORATES_WITH]->(e2)
SET r.evidence_count = count(d1),
    r.strength = r.evidence_count / 10.0
```

#### 3. **Path-based Query Enhancement**
```python
class GraphTraverser:
    def find_related_entities(self, entity: str, max_depth: int = 3):
        # Multi-hop traversal with path ranking
        paths = self.graph_store.run("""
        MATCH path = (e:Entity {name: $name})-[*1..3]-(related:Entity)
        RETURN path, length(path) as depth, 
               reduce(score = 1.0, rel in relationships(path) | 
                      score * rel.strength) as path_strength
        ORDER BY depth, path_strength DESC
        LIMIT 20
        """, name=entity)
        return self.rank_paths(paths)
```

#### 4. **Temporal Reasoning**
```cypher
// Query with time-aware filtering
MATCH (e:Entity {name: $entity})-[r]->(related)
WHERE r.valid_from <= $query_time 
  AND (r.valid_to IS NULL OR r.valid_to >= $query_time)
RETURN related, r
```

## Implementation Plan:

### Phase 1: Schema Migration
1. Create new node and relationship types
2. Migrate existing data to enhanced schema
3. Add entity disambiguation pipeline

### Phase 2: Relationship Extraction
1. Implement rules-based relationship extraction
2. Add NLP models for relationship detection
3. Create relationship confidence scoring

### Phase 3: Advanced Queries
1. Implement multi-hop traversal
2. Add path ranking algorithms
3. Create temporal reasoning capabilities

### Phase 4: Visualization & Debugging
1. Integrate with Langflow for graph visualization
2. Add graph query debugging tools
3. Create relationship analytics dashboard

## Graph Enhancement Benefits:

1. **Better Context Understanding**: Rich relationships improve query relevance
2. **Indirect Knowledge Discovery**: Multi-hop traversal reveals hidden connections
3. **Temporal Reasoning**: Understanding how relationships change over time
4. **Entity Disambiguation**: Reduces confusion between similarly named entities
5. **Organizational Intelligence**: Models company structure and decision flows

## Priority Matrix:

| Feature | Impact | Effort | Priority |
|---------|---------|--------|----------|
| Entity Disambiguation | High | High | 1 |
| Relationship Types | High | Medium | 2 |
| Multi-hop Traversal | Medium | Medium | 3 |
| Temporal Reasoning | Medium | High | 4 |
| Path Ranking | Low | Low | 5 |

## Next Steps:
1. Design enhanced schema with migration path
2. Implement entity resolution pipeline
3. Add relationship extraction from documents
4. Create graph visualization tools