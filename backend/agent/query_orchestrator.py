"""
Assest Multi-Agent Query Orchestration using LangGraph
Implements Layer 16: Agent Orchestration for intelligent, self-correcting responses
"""

from typing import List, Dict, Any, Optional, TypedDict
from dataclasses import dataclass
import asyncio
import logging
from datetime import datetime
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

try:
    from langgraph.graph import StateGraph, END
    from langgraph.checkpoint.sqlite import SqliteSaver
    HAS_LANGGRAPH = True
except ImportError:
    logger.warning("langgraph not found. Multi-agent queries will be disabled.")
    HAS_LANGGRAPH = False
    StateGraph = Any
    END = "end"
    SqliteSaver = Any

try:
    from langchain_core.messages import HumanMessage, AIMessage
    from langchain_core.runnables import RunnableConfig
except ImportError:
    logger.warning("langchain_core not found. Some agent features will be limited.")
    HumanMessage = Any
    AIMessage = Any
    RunnableConfig = Any

from backend.query.retriever import Retriever, RetrievalResult
from backend.query.generator import Generator
from backend.graph.graph_store import GraphStore
from backend.models.chunk import Chunk
from backend.core.ranker import Ranker


class QueryState(TypedDict):
    """State object for the multi-agent query workflow"""
    # Input
    question: str
    workspace_id: str
    conversation_id: Optional[str]
    
    # Agent outputs
    retrieved_chunks: List[Dict[str, Any]]
    graph_context: Dict[str, Any]
    verification_results: List[Dict[str, str]]
    critique: Optional[str]
    
    # Control flow
    needs_verification: bool
    needs_more_context: bool
    iteration_count: int
    max_iterations: int
    
    # Response
    final_answer: Optional[str]
    sources: List[Dict[str, str]]
    confidence: float


class SearchAgent:
    """Agent responsible for retrieving relevant knowledge"""
    
    def __init__(self):
        self.retriever = Retriever()
        self.graph_store = GraphStore()
        
    async def search(self, state: QueryState) -> QueryState:
        """Perform hybrid search with graph context"""
        logger.info(f"Search Agent: Retrieving for '{state['question']}'")
        
        # Standard retrieval
        chunks = await self.retriever.search(
            state["question"], 
            state["workspace_id"],
            top_k=10
        )
        
        # Convert chunks to state format
        state["retrieved_chunks"] = [
            {
                "content": c.content,
                "source_url": c.source_url,
                "title": c.title,
                "score": c.score,
                "chunk_id": c.chunk_id,
                "heading_path": c.metadata.get("heading_path", [])
            }
            for c in chunks
        ]
        
        # Enhanced graph context
        try:
            # Extract entities from the question
            entities = await self._extract_entities(state["question"])
            graph_context = {}
            
            for entity in entities:
                # Get related entities (2-hop for richer context)
                related = self.graph_store.get_context(entity).get("relationships", [])
                if related:
                    graph_context[entity] = related
            
            # Add document relationships
            if state["retrieved_chunks"]:
                doc_ids = [c.get("source_url", "") for c in state["retrieved_chunks"]]
                doc_relationships = await self._get_document_relationships(doc_ids)
                graph_context["documents"] = doc_relationships
                
            state["graph_context"] = graph_context
            
        except Exception as e:
            logger.warning(f"Graph context extraction failed: {e}")
            state["graph_context"] = {}
        
        state["needs_verification"] = bool(chunks)
        state["iteration_count"] = 1
        
        return state
    
    async def _extract_entities(self, question: str) -> List[str]:
        """Simple entity extraction - can be enhanced with NLP"""
        # For now, use capitalized words as entities
        return [word for word in question.split() if word[0].isupper() and len(word) > 2]
    
    async def _get_document_relationships(self, doc_ids: List[str]) -> List[Dict[str, str]]:
        """Get relationships between documents"""
        # Placeholder for document relationship detection
        # This would check if documents reference each other
        return []


class VerificationAgent:
    """Agent that verifies retrieved information for consistency and correctness"""
    
    def __init__(self):
        self.graph_store = GraphStore()
        
    async def verify(self, state: QueryState) -> QueryState:
        """Verify claims against graph knowledge and check for contradictions"""
        logger.info(f"Verification Agent: Checking {len(state['retrieved_chunks'])} chunks")
        
        verification_results = []
        
        for chunk in state["retrieved_chunks"]:
            verification = {
                "chunk_id": chunk["chunk_id"],
                "status": "verified",
                "issues": [],
                "confidence": chunk["score"]
            }
            
            # Check for contradictions with graph knowledge
            if "graph_context" in state:
                contradictions = await self._check_contradictions(
                    chunk["content"], 
                    state["graph_context"]
                )
                if contradictions:
                    verification["issues"].extend(contradictions)
                    verification["status"] = "warning"
            
            # Check for factual consistency across chunks
            similar_claims = await self._find_similar_claims(
                chunk["content"],
                [
                    c["content"] for c in state["retrieved_chunks"]
                    if c["chunk_id"] != chunk["chunk_id"]
                ]
            )
            
            if similar_claims:
                verification["similar_claims"] = similar_claims
            
            verification_results.append(verification)
        
        state["verification_results"] = verification_results
        
        # Determine if more context is needed
        warning_count = sum(1 for v in verification_results if v["status"] == "warning")
        if warning_count > len(verification_results) * 0.3:
            state["needs_more_context"] = True
        
        return state
    
    async def _check_contradictions(
        self, 
        content: str, 
        graph_context: Dict[str, Any]
    ) -> List[str]:
        """Check if content contradicts known graph relationships"""
        contradictions = []
        
        # Simple contradiction detection
        # In production, this would use semantic similarity
        for entity, relations in graph_context.items():
            if entity.lower() in content.lower():
                for relation in relations:
                    # Check if the relation type contradicts the statement
                    if relation.get("relationship") == "OPPOSES":
                        contradictions.append(
                            f"Content contradicts known opposition between {entity} and {relation.get('name')}"
                        )
        
        return contradictions
    
    async def _find_similar_claims(
        self, 
        content: str, 
        other_chunks: List[str]
    ) -> List[str]:
        """Find similar claims in other chunks for consistency check"""
        # Simple similarity - in production, use embeddings
        similar = []
        content_words = set(content.lower().split())
        
        for chunk in other_chunks:
            chunk_words = set(chunk.lower().split())
            overlap = len(content_words & chunk_words) / len(content_words | chunk_words)
            if overlap > 0.5:
                similar.append(chunk[:100] + "...")
        
        return similar


class CriticAgent:
    """Agent that evaluates the quality and completeness of the retrieved information"""
    
    def __init__(self):
        self.critique_prompt = """
        Analyze the following question and retrieved context. Provide a critique that answers:
        1. Is there enough information to answer the question fully?
        2. Are there obvious gaps or missing context?
        3. Is the information potentially outdated or conflicting?
        4. Should we search for more specific information?
        
        Question: {question}
        
        Retrieved Context:
        {context}
        
        Verification Results:
        {verification}
        
        Provide your critique as a JSON with this structure:
        {{
            "adequate": true/false,
            "gaps": ["gap1", "gap2"],
            "needs_more_context": true/false,
            "suggested_search_terms": ["term1", "term2"]
        }}
        """
        
    async def critique(self, state: QueryState) -> QueryState:
        """Evaluate whether retrieved information is adequate"""
        logger.info(f"Critic Agent: Evaluating {len(state['retrieved_chunks'])} chunks")
        
        from groq import Groq
        if not settings.groq_api_key:
            state["critique"] = '{"adequate": true}'
            return state
        
        try:
            client = Groq(api_key=settings.groq_api_key)
            
            # Prepare context
            context_str = "\n\n".join([
                f"Chunk {i+1}: {c['content'][:200]}..."
                for i, c in enumerate(state["retrieved_chunks"])
            ])
            
            verification_str = "\n".join([
                f"Chunk {v['chunk_id']}: {v['status']} - {', '.join(v['issues'])}"
                for v in state["verification_results"]
            ])
            
            response = client.chat.completions.create(
                messages=[{
                    "role": "user",
                    "content": self.critique_prompt.format(
                        question=state["question"],
                        context=context_str,
                        verification=verification_str
                    )
                }],
                model="llama3-8b-8192",
                temperature=0.1
            )
            
            state["critique"] = response.choices[0].message.content
            
            # Parse critique to determine if more context is needed
            if "needs_more_context\": true" in state["critique"]:
                state["needs_more_context"] = True
                
        except Exception as e:
            logger.warning(f"Critique agent failed: {e}")
            state["critique"] = '{"adequate": true}'
        
        return state


class SynthesisAgent:
    """Agent that synthesizes verified information into a coherent response"""
    
    def __init__(self):
        self.generator = Generator()
        
    async def synthesize(self, state: QueryState) -> QueryState:
        """Generate the final response using verified information"""
        logger.info("Synthesis Agent: Generating final response")
        
        if not state["retrieved_chunks"]:
            state["final_answer"] = "I couldn't find relevant information in your knowledge base."
            state["sources"] = []
            state["confidence"] = 0.0
            return state
        
        # Use the existing generator with verified chunks
        # Convert back to RetrievalResult format
        verified_chunks = []
        for chunk, verification in zip(
            state["retrieved_chunks"], 
            state["verification_results"]
        ):
            if verification["status"] != "rejected":
                # Inject structural context into content for synthesis
                # Phase 2/3: Structural Injection
                heading_path = chunk.get("heading_path", [])
                breadcrumb = " > ".join(heading_path) if heading_path else "General"
                
                context_with_structure = f"[Context: {breadcrumb}]\n{chunk['content']}"
                
                verified_chunks.append(RetrievalResult(
                    chunk_id=chunk["chunk_id"],
                    content=context_with_structure,
                    source_url=chunk["source_url"],
                    title=chunk["title"],
                    score=chunk["score"],
                    metadata={**chunk.get("metadata", {}), **verification}
                ))
        
        # Generate answer
        try:
            answer = await self.generator.generate_answer(
                state["question"], 
                verified_chunks
            )
            
            state["final_answer"] = answer.answer_text
            state["sources"] = answer.sources
            state["confidence"] = answer.confidence if hasattr(answer, 'confidence') else 0.8
            
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            state["final_answer"] = "I encountered an error while generating the response."
            state["sources"] = []
            state["confidence"] = 0.0
        
        return state


class MoreContextAgent:
    """Agent that searches for additional context when needed"""
    
    def __init__(self):
        self.retriever = Retriever()
        
    async def search_more(self, state: QueryState) -> QueryState:
        """Search for additional context based on critique"""
        logger.info(f"MoreContext Agent: Iteration {state['iteration_count']}")
        
        # Extract suggested search terms from critique
        search_terms = []
        if state.get("critique"):
            try:
                import json
                critique_data = json.loads(state["critique"])
                search_terms = critique_data.get("suggested_search_terms", [])
            except:
                pass
        
        # Default to question keywords if no terms suggested
        if not search_terms:
            search_terms = state["question"].split()[:3]
        
        # Search with expanded terms
        expanded_query = " ".join([state["question"]] + search_terms)
        
        additional_chunks = await self.retriever.search(
            expanded_query,
            state["workspace_id"],
            top_k=5
        )
        
        # Add new chunks (deduplicate by chunk_id)
        existing_ids = {c["chunk_id"] for c in state["retrieved_chunks"]}
        
        for chunk in additional_chunks:
            if chunk.chunk_id not in existing_ids:
                state["retrieved_chunks"].append({
                    "content": chunk.content,
                    "source_url": chunk.source_url,
                    "title": chunk.title,
                    "score": chunk.score,
                    "chunk_id": chunk.chunk_id
                })
        
        state["iteration_count"] += 1
        state["needs_more_context"] = False
        
        return state


def create_query_graph() -> StateGraph:
    """Create the LangGraph workflow for query processing"""
    
    # Initialize agents
    search_agent = SearchAgent()
    verification_agent = VerificationAgent()
    critic_agent = CriticAgent()
    synthesis_agent = SynthesisAgent()
    more_context_agent = MoreContextAgent()
    
    # Create the graph
    workflow = StateGraph(QueryState)
    
    # Add nodes
    workflow.add_node("search", search_agent.search)
    workflow.add_node("verify", verification_agent.verify)
    workflow.add_node("critic", critic_agent.critique)
    workflow.add_node("synthesize", synthesis_agent.synthesize)
    workflow.add_node("more_context", more_context_agent.search_more)
    
    # Set entry point
    workflow.set_entry_point("search")
    
    # Add edges
    workflow.add_edge("search", "verify")
    workflow.add_edge("verify", "critic")
    
    # Conditional edge after critic
    def decide_next(state: QueryState) -> str:
        """Decide next step based on critic evaluation"""
        
        # Check if we've exceeded max iterations
        if state["iteration_count"] >= state["max_iterations"]:
            return "synthesize"
        
        # Check if critique indicates need for more context
        if state.get("needs_more_context", False):
            return "more_context"
        
        # Otherwise, proceed to synthesis
        return "synthesize"
    
    workflow.add_conditional_edges(
        "critic",
        decide_next,
        {
            "more_context": "more_context",
            "synthesize": "synthesize"
        }
    )
    
    # More context flows back to verification
    workflow.add_edge("more_context", "verify")
    
    # End at synthesis
    workflow.add_edge("synthesize", END)
    
    # Add memory for conversation state
    memory = SqliteSaver.from_conn_string(":memory:")
    
    # Compile the graph
    app = workflow.compile(checkpointer=memory)
    
    return app


# Singleton instance
_query_graph = None


def get_query_graph() -> StateGraph:
    """Get the singleton query graph instance"""
    global _query_graph
    if _query_graph is None:
        _query_graph = create_query_graph()
    return _query_graph


async def run_multi_agent_query(
    question: str,
    workspace_id: str,
    conversation_id: Optional[str] = None,
    max_iterations: int = 2
) -> Dict[str, Any]:
    """
    Run a query through the multi-agent orchestration system
    
    Returns:
        Dict containing:
        - answer: The final answer
        - sources: List of sources
        - confidence: Confidence score
        - iterations: Number of iterations run
        - verification_results: Detailed verification info
        - critique: Critique agent feedback
    """
    
    if not HAS_LANGGRAPH:
        logger.info("LangGraph missing, using fallback retrieval mode.")
        retriever = Retriever()
        generator = Generator()
        chunks = await retriever.search(question, workspace_id)
        if chunks:
            answer = await generator.generate_answer(question, chunks)
            return {
                "answer": answer.answer_text,
                "sources": answer.sources,
                "confidence": 0.7,
                "iterations": 1,
                "verification_results": [],
                "critique": "LangGraph missing, used standard retrieval"
            }
        return {
            "answer": "I couldn't find information in your knowledge base.",
            "sources": [],
            "confidence": 0.0,
            "iterations": 0,
            "verification_results": [],
            "critique": "No information found"
        }

    graph = get_query_graph()
    
    # Initial state
    initial_state = {
        "question": question,
        "workspace_id": workspace_id,
        "conversation_id": conversation_id,
        "retrieved_chunks": [],
        "graph_context": {},
        "verification_results": [],
        "critique": None,
        "needs_verification": False,
        "needs_more_context": False,
        "iteration_count": 0,
        "max_iterations": max_iterations,
        "final_answer": None,
        "sources": [],
        "confidence": 0.0
    }
    
    # Run the graph
    config = RunnableConfig(
        recursion_limit=max_iterations + 5,
        configurable={"thread_id": conversation_id or "default"}
    )
    
    try:
        result = await graph.ainvoke(initial_state, config=config)
        
        return {
            "answer": result["final_answer"],
            "sources": result["sources"],
            "confidence": result["confidence"],
            "iterations": result["iteration_count"],
            "verification_results": result["verification_results"],
            "critique": result["critique"]
        }
        
    except Exception as e:
        logger.error(f"Multi-agent query failed: {e}")
        # Fallback to simple retrieval
        retriever = Retriever()
        generator = Generator()
        
        chunks = await retriever.search(question, workspace_id)
        if chunks:
            answer = await generator.generate_answer(question, chunks)
            return {
                "answer": answer.answer_text,
                "sources": answer.sources,
                "confidence": 0.7,
                "iterations": 1,
                "verification_results": [],
                "critique": "Multi-agent failed, used fallback"
            }
        
        return {
            "answer": "I couldn't find information in your knowledge base.",
            "sources": [],
            "confidence": 0.0,
            "iterations": 0,
            "verification_results": [],
            "critique": "No information found"
        }