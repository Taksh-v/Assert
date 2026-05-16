# ASSEST Query Engine & Agent Orchestration Analysis (Layer 16)

## Current Implementation Status

### ✅ Working Components:
1. **Hybrid Search** - Vector + BM25 hybrid retrieval
2. **HyDE Query Expansion** - Hypothetical document embedding
3. **Graph Context Integration** - Basic entity relationship search
4. **Reranking** - Cross-encoder reranking for better relevance
5. **Knowledge Gap Tracking** - Automatic identification of missing knowledge

### 🔴 Critical Issues Identified:

#### 1. **Monolithic Query Pipeline**
- Single linear flow (Query -> Retrieve -> Generate)
- No multi-step reasoning or verification
- No feedback loops for self-correction

#### 2. **Limited Agent Coordination**
- No collaboration between specialized agents (researcher, verifier, critic)
- Missing statefull conversation context management
- No parallel processing strategies

#### 3. **Insufficient Verification Layer**
- Only basic truth checks via graph store
- No hallucination detection mechanisms
- Missing conflict resolution between sources

#### 4. **Context Window Management**
- No intelligent context compression for long conversations
- Missing context prioritization based on relevance
- No episodic memory for user preferences

## LangGraph Integration Architecture

### Proposed Multi-Agent System:
```python
from langgraph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

class AssestQueryState:
    question: str
    workspace_id: str
    conversation_id: str
    
    # Agent outputs
    retrieved_chunks: List[Chunk]
    graph_context: Dict[str, Any]
    verification_results: List[Dict]
    critique: str
    
    # Control flow
    needs_verification: bool
    needs_more_context: bool
    iteration_count: int
```

### Agent Nodes:

#### 1. **Search Agent** 
- Performs hybrid search with graph context
- Implements HyDE expansion
- Manages retrieval parameters dynamically

#### 2. **Verification Agent**
- Cross-references chunks with graph relationships
- Detects contradictions between sources
- Validates factual claims against stored knowledge

#### 3. **Critic Agent**
- Evaluates answer for groundedness
- Identifies potential hallucinations
- Triggers additional context retrieval when needed

#### 4. **Synthesis Agent**
- Merges verified information into coherent response
- Maintains conversation context
- Handles multi-turn dialogues with memory

### Control Flow:
```
START -> Search -> Verification -> Critic
          |          ^            |
          |          |            v
          |<---------+------> More Context?
          |                     |
          v                     |
        Synthesis <-------------+
          |
        END
```

## Implementation Plan:

### Phase 1: Core LangGraph Setup
1. Install dependencies: `langgraph`, `langchain-anthropic`
2. Create state schema and checkpointing
3. Migrate existing retriever to Search Agent

### Phase 2: Agent Implementation
1. Implement Verification Agent with graph integration
2. Create Critic Agent using Groq LLM
3. Add Synthesis Agent for final response generation

### Phase 3: Advanced Features
1. Add parallel retrieval strategies
2. Implement context compression for long conversations
3. Add preference learning from user feedback

## Benefits of LangGraph Integration:

1. **Self-Correction**: Automatically detects and fixes retrieval gaps
2. **Stateful Memory**: Persistent conversation and episodic memory
3. **HITL Support**: Can pause for human approval on sensitive queries
4. **Observability**: Built-in tracing for debugging complex queries
5. **Scalability**: Easy to add new specialized agents

## Migration Strategy:

1. **Backwards Compatibility**: Keep existing API endpoints
2. **Gradual rollout**: Feature flag for LangGraph vs legacy
3. **Parallel Testing**: A/B testing both approaches
4. **Performance Monitoring**: Track latency and accuracy improvements

## Priority Matrix:

| Component | Impact | Effort | Priority |
|-----------|---------|--------|----------|
| State Graph Setup | High | Low | 1 |
| Search Agent | High | Medium | 2 |
| Verification Agent | High | High | 3 |
| Critic Agent | Medium | High | 4 |
| Synthesis Agent | Medium | Medium | 5 |

## Next Steps:
1. Set up LangGraph infrastructure
2. Migrate retriever to Search Agent
3. Implement verification and critic agents
4. Add observability and debugging tools