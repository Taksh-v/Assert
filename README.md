# 🧠 Assest: The Company Brain

**Assest** is a high-precision, 16-layer agentic knowledge ingestion and retrieval engine. It transforms fragmented organizational data into a unified, version-aware "Company Brain" capable of self-learning and expert-level reasoning.

---

## 🚀 Core Value Proposition
Unlike standard RAG pipelines, Assest implements a **Deep Ingestion Architecture** that preserves organizational context, relationships, and temporal intelligence. It doesn't just store text; it understands your company's evolution.

---

## 🏗️ The 16-Layer Ingestion Architecture
Assest operates on a meticulously engineered pipeline designed for elite performance:

1.  **Normalization**: Standardizing multimodal data (Slack, Notion, Drive, etc.).
2.  **Structural Hierarchy**: Preserving document headers and semantic nesting.
3.  **Privacy-First (PII)**: Automatic scrubbing of sensitive data before indexing.
4.  **Semantic Enrichment**: AI-driven summary and entity extraction.
5.  **Adaptive Chunking**: Context-aware segmentation (not just fixed-length).
6.  **Multi-Vector Intelligence**: Simultaneous indexing of titles, summaries, and content.
7.  **Hybrid Storage**: Unified Postgres (Metadata) + Qdrant (Vectors) + Memgraph (Graphs).
8.  **Knowledge Graphing**: Real-time relationship mapping across people and projects.
9.  **Security ACLs**: Pre-retrieval security gates for multi-tenant isolation.
10. **Elite Retrieval**: Reciprocal Rank Fusion (RRF) combining dense and sparse search.
11. **Agentic Memory**: Cross-session recall of user preferences and past context.
12. **Temporal Knowledge**: Full versioning and "Active Knowledge" tracking.

---

## 🛠️ Tech Stack
- **Backend**: Python / FastAPI
- **Vector Store**: [Qdrant](https://qdrant.tech/)
- **Graph Database**: [Memgraph](https://memgraph.com/)
- **Primary DB**: PostgreSQL (with pgvector)
- **Frontend**: Next.js / TailwindCSS
- **AI Models**: Gemini 1.5 Pro, Claude 3.5 Sonnet, Groq (Llama 3)

---

## 🏁 Getting Started

### 1. Prerequisites
- Python 3.10+
- Docker (for Qdrant & Memgraph)

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/Taksh-v/Assert.git
cd Assert

# Set up backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set up frontend
cd ../web
npm install
```

### 3. Environment Setup
Copy the example environment file and add your keys:
```bash
cp .env.example .env
```
*(Note: Never commit your real `.env` file to version control!)*

### 4. Run the System
```bash
# Start the backend
./run_backend.sh

# Start the frontend
cd web
npm run dev
```

---

## 🛡️ Security & Privacy
Assest is designed with enterprise-grade security in mind:
- **PII Scrubbing**: Built-in layer to ensure data privacy.
- **Access Control**: Strict authorization checks at the retrieval layer.
- **Data Sovereignty**: Designed for local or VPC-only deployment.

---

## 📈 Roadmap
- [x] 16-Layer Ingestion Engine
- [x] Multi-Hop Knowledge Graph Reasoning
- [x] Agentic Memory Layer
- [ ] Self-Healing Knowledge Gaps
- [ ] Automated Enterprise Connectors (Linear, Jira, Zendesk)
- [ ] Multi-Agent Collaboration Hub

---

## 📄 License
This project is licensed under the MIT License.
