# Assest — Complete Product Blueprint
### From Zero to Production-Ready Company Brain for Indian Startups
**Solo Founder. AI-First Operations. India-Compliant.**

---

> **How to use this document**
> This file is your single source of truth. Every section is written so your AI IDE (Antigravity) can understand the context, generate the correct code, and build the right thing. Before starting any coding task, paste the relevant section into Antigravity along with your request. The more context you give it, the better the output.
> 
> **Working name:** Assest  
> **Founder:** Solo  
> **Target market:** Funded Indian startups, 50–500 employees  
> **Core promise:** New employees get instant, accurate answers from your company's own knowledge. Senior people stop getting interrupted. AI agents get the context they need to work reliably.

---

## Table of Contents

1. [Vision and Strategy](#1-vision-and-strategy)
2. [Technical Architecture Overview](#2-technical-architecture-overview)
3. [Project Structure](#3-project-structure)
4. [Environment and Infrastructure Setup](#4-environment-and-infrastructure-setup)
5. [Phase 1 — MVP Build (Weeks 1–8)](#5-phase-1--mvp-build-weeks-18)
6. [Phase 2 — Full Knowledge Platform (Months 3–6)](#6-phase-2--full-knowledge-platform-months-36)
7. [Phase 3 — Skills File Engine (Months 6–12)](#7-phase-3--skills-file-engine-months-612)
8. [Phase 4 — Full Company Brain Platform (Month 12+)](#8-phase-4--full-company-brain-platform-month-12)
9. [Compliance and Security](#9-compliance-and-security)
10. [Testing Strategy](#10-testing-strategy)
11. [Deployment and DevOps](#11-deployment-and-devops)
12. [Assest as Its Own First Customer](#12-assest-as-its-own-first-customer)
13. [Go-to-Market Plan](#13-go-to-market-plan)
14. [Antigravity AI IDE — Prompting Guide](#14-antigravity-ai-ide--prompting-guide)

---

## 1. Vision and Strategy

### What Assest Is

Assest is a company brain platform. It ingests knowledge from wherever a company stores it — Notion, Google Drive, Slack, GitHub, Jira — structures that knowledge, keeps it current, and makes it available to both humans (via chat) and AI agents (via a skills API).

The product solves one immediate, urgent problem for its first customers: **new employees waste weeks asking questions that already have answers somewhere in the company's tools. Senior people lose hours answering them. Assest eliminates this entirely.**

As the product matures, it becomes the missing context layer between a company's raw data and reliable AI automation.

### Why India First

- No serious local competitor exists in this space
- Indian funded startups (50–500 people) feel knowledge chaos acutely due to 25%+ annual attrition
- WhatsApp is the primary knowledge channel — ignored by all US competitors
- Data localisation requirements (DPDP Act 2023) give a locally-built product a compliance advantage
- 63 million MSMEs, thousands of funded startups — massive TAM

### The Solo Founder + AI Agents Philosophy

Assest is built by one person using AI agents. This means:
- Assest uses its own product internally (you are customer zero)
- Every manual operation is a candidate for automation
- The codebase must be clean enough for AI to navigate and extend
- Documentation is written for AI consumption, not just humans
- Agents handle: customer onboarding emails, support ticket triage, ingestion monitoring, error alerts

### Revenue Model

| Plan | Price | Includes |
|---|---|---|
| Starter | ₹15,000/month | Up to 3 connectors, 1 workspace, web chat + Slack bot |
| Growth | ₹35,000/month | Up to 8 connectors, 3 workspaces, skills API access |
| Scale | ₹75,000/month | Unlimited connectors, custom integrations, SLA |

Pilot pricing: Free for 60 days, then Starter plan. No credit card required for pilots.

---

## 2. Technical Architecture Overview

### Technology Decisions

| Layer | Technology | Reason |
|---|---|---|
| **Backend language** | Python 3.11+ | Best ecosystem for AI/ML, LlamaIndex, LangChain |
| **Web framework** | FastAPI | Async, fast, auto-generates API docs |
| **Vector database** | Qdrant (self-hosted) | Open source, India-deployable, excellent performance |
| **Relational database** | PostgreSQL via Supabase (self-hosted) | Auth + DB + storage in one, open source |
| **Document parsing** | Unstructured.io | Handles PDFs, DOCX, HTML, images |
| **Chunking + indexing** | LlamaIndex | Purpose-built for knowledge base construction |
| **LLM** | Anthropic Claude API (claude-sonnet-4-6) | Best grounded answers, citation support |
| **Embeddings** | text-embedding-3-small (OpenAI) or Cohere | Cost-effective, high quality |
| **PII scrubbing** | Microsoft Presidio | Open source, supports Indian PII patterns |
| **Task queue** | Celery + Redis | Async ingestion jobs |
| **Slack bot** | Slack Bolt for Python | Official SDK, well maintained |
| **Web chat frontend** | Next.js 14 (React) | Modern, fast, easy to deploy |
| **Hosting** | AWS Mumbai (ap-south-1) | Data stays in India, DPDP compliant |
| **Containerisation** | Docker + Docker Compose | Consistent environments |
| **CI/CD** | GitHub Actions | Free, integrates with everything |
| **Monitoring** | Grafana + Prometheus | Open source, self-hosted |
| **Logging** | ELK Stack (Elasticsearch, Logstash, Kibana) | 180-day retention for CERT-In compliance |

### System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                             │
│              Slack Bot          Web Chat (Next.js)              │
└──────────────────────┬──────────────────────────────────────────┘
                       │ HTTPS
┌──────────────────────▼──────────────────────────────────────────┐
│                      API LAYER (FastAPI)                        │
│   /query   /ingest   /connectors   /health   /admin   /skills   │
└──────┬──────────────────────┬───────────────────────────────────┘
       │                      │
┌──────▼──────┐    ┌──────────▼──────────────────────────────────┐
│  QUERY      │    │           INGESTION PIPELINE                 │
│  ENGINE     │    │  Connectors → Parse → Chunk → PII Scrub     │
│             │    │  → Embed → Store → Index                    │
│  Embed Q    │    └──────────────────────────────────────────────┘
│  → Qdrant   │                      │
│  → Rerank   │    ┌──────────────────▼──────────────────────────┐
│  → Claude   │    │              STORAGE LAYER                  │
│  → Answer   │    │   Qdrant (vectors)   PostgreSQL (metadata)  │
└─────────────┘    │   S3 Mumbai (raw files)   Redis (jobs)      │
                   └─────────────────────────────────────────────┘
```

### Data Flow — Query Path

```
User asks question
    → FastAPI receives request
    → Question embedded to vector
    → Qdrant similarity search (top 5 chunks)
    → Chunks + question sent to Claude API
    → Claude generates grounded answer with citations
    → Answer returned to Slack or Web Chat
    → Interaction logged to PostgreSQL
```

### Data Flow — Ingestion Path

```
Connector triggered (scheduled or manual)
    → Raw content fetched (Notion API / Google Drive API)
    → Unstructured.io parses to clean text
    → LlamaIndex splits into 500-token chunks with overlap
    → Presidio scrubs PII (Aadhaar, PAN, phone, email)
    → Chunks embedded to vectors
    → Vectors stored in Qdrant with metadata
    → Metadata (source, timestamp, hash) stored in PostgreSQL
    → Celery marks job complete
    → Staleness timer set for next re-sync
```

---

## 3. Project Structure

```
assest/
├── README.md
├── .env.example                    # All required env vars listed here
├── .gitignore
├── docker-compose.yml              # Local dev: all services
├── docker-compose.prod.yml         # Production overrides
├── Makefile                        # Common commands (make dev, make test, etc.)
│
├── backend/                        # FastAPI application
│   ├── main.py                     # App entry point
│   ├── requirements.txt
│   ├── Dockerfile
│   │
│   ├── api/                        # Route handlers
│   │   ├── __init__.py
│   │   ├── query.py                # POST /query — main Q&A endpoint
│   │   ├── ingest.py               # POST /ingest — trigger ingestion
│   │   ├── connectors.py           # CRUD for connector configs
│   │   ├── health.py               # GET /health
│   │   ├── admin.py                # Admin routes (protected)
│   │   └── skills.py               # GET /skills — skills files API
│   │
│   ├── core/                       # Business logic
│   │   ├── __init__.py
│   │   ├── config.py               # Settings from env vars
│   │   ├── security.py             # Auth, API keys, JWT
│   │   └── database.py             # DB connection, session management
│   │
│   ├── ingestion/                  # Ingestion pipeline
│   │   ├── __init__.py
│   │   ├── pipeline.py             # Main orchestrator
│   │   ├── chunker.py              # LlamaIndex chunking logic
│   │   ├── embedder.py             # Embedding generation
│   │   ├── pii_scrubber.py         # Presidio PII detection + removal
│   │   ├── deduplicator.py         # Hash-based deduplication
│   │   └── freshness.py            # Staleness detection logic
│   │
│   ├── connectors/                 # Data source connectors
│   │   ├── __init__.py
│   │   ├── base.py                 # Abstract base connector class
│   │   ├── notion.py               # Notion API connector
│   │   ├── google_drive.py         # Google Drive connector
│   │   ├── slack.py                # Slack connector (Phase 2)
│   │   ├── github.py               # GitHub connector (Phase 2)
│   │   ├── jira.py                 # Jira connector (Phase 2)
│   │   └── whatsapp.py             # WhatsApp connector (Phase 3)
│   │
│   ├── query/                      # Query and retrieval engine
│   │   ├── __init__.py
│   │   ├── retriever.py            # Qdrant similarity search
│   │   ├── reranker.py             # Result reranking
│   │   ├── generator.py            # Claude API answer generation
│   │   └── citation.py             # Source citation formatting
│   │
│   ├── models/                     # SQLAlchemy database models
│   │   ├── __init__.py
│   │   ├── workspace.py            # Customer workspace
│   │   ├── connector.py            # Connector configurations
│   │   ├── document.py             # Ingested document metadata
│   │   ├── query_log.py            # Query history and feedback
│   │   └── user.py                 # User accounts
│   │
│   ├── tasks/                      # Celery background tasks
│   │   ├── __init__.py
│   │   ├── celery_app.py           # Celery configuration
│   │   ├── ingestion_tasks.py      # Async ingestion jobs
│   │   └── freshness_tasks.py      # Scheduled re-sync jobs
│   │
│   └── tests/                      # Backend tests
│       ├── test_connectors.py
│       ├── test_ingestion.py
│       ├── test_query.py
│       └── test_api.py
│
├── slack_bot/                      # Slack Bolt application
│   ├── app.py                      # Bot entry point
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── handlers/
│   │   ├── ask.py                  # /ask slash command handler
│   │   ├── feedback.py             # Thumbs up/down feedback
│   │   └── onboard.py              # /assest-setup command
│   └── utils/
│       └── formatter.py            # Format answers for Slack
│
├── web/                            # Next.js web chat frontend
│   ├── package.json
│   ├── Dockerfile
│   ├── next.config.js
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx                # Landing / login
│   │   ├── chat/
│   │   │   └── page.tsx            # Main chat interface
│   │   └── admin/
│   │       └── page.tsx            # Admin dashboard
│   ├── components/
│   │   ├── ChatWindow.tsx          # Main chat UI
│   │   ├── MessageBubble.tsx       # Individual message
│   │   ├── SourceCard.tsx          # Citation source card
│   │   └── ConnectorStatus.tsx     # Connector health display
│   └── lib/
│       ├── api.ts                  # API client
│       └── auth.ts                 # Auth helpers
│
├── infrastructure/                 # Infrastructure as code
│   ├── docker/
│   │   ├── qdrant/
│   │   │   └── config.yaml
│   │   └── redis/
│   │       └── redis.conf
│   ├── nginx/
│   │   └── nginx.conf              # Reverse proxy config
│   └── scripts/
│       ├── setup_aws.sh            # AWS initial setup
│       ├── deploy.sh               # Deployment script
│       └── backup.sh               # Database backup
│
└── docs/                           # Internal documentation
    ├── api.md                      # API reference
    ├── connector_guide.md          # How to add new connectors
    └── compliance.md               # DPDP + IT Act compliance notes
```

---

## 4. Environment and Infrastructure Setup

### Step 1 — AWS Account Setup (Starting Fresh)

**Do this before writing any code.**

```bash
# 1. Create AWS account at aws.amazon.com
# 2. Enable MFA on root account immediately
# 3. Create an IAM user for programmatic access (never use root)
# 4. Attach these policies to IAM user:
#    - AmazonEC2FullAccess
#    - AmazonS3FullAccess
#    - AmazonRDSFullAccess (if using RDS later)

# 4. Install AWS CLI
pip install awscli

# 5. Configure
aws configure
# AWS Access Key ID: [your key]
# AWS Secret Access Key: [your secret]
# Default region name: ap-south-1
# Default output format: json
```

**EC2 Instance to create (AWS Mumbai):**
- Instance type: `t3.medium` for MVP (2 vCPU, 4GB RAM) — ~₹3,500/month
- OS: Ubuntu 22.04 LTS
- Storage: 50GB SSD (gp3)
- Security group: open ports 22 (SSH), 80 (HTTP), 443 (HTTPS), 8000 (FastAPI dev)
- Elastic IP: yes — attach a static IP immediately

**S3 Bucket (for raw file storage):**
```bash
aws s3 mb s3://assest-raw-documents --region ap-south-1
# Block all public access — this bucket is private
aws s3api put-public-access-block \
  --bucket assest-raw-documents \
  --public-access-block-configuration \
  "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
```

### Step 2 — Server Initial Setup

```bash
# SSH into your EC2 instance
ssh -i your-key.pem ubuntu@your-elastic-ip

# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Install Git
sudo apt install git -y

# Install Nginx
sudo apt install nginx -y

# Clone your repo
git clone https://github.com/yourusername/assest.git
cd assest
```

### Step 3 — Environment Variables

Create `.env` file on server. **Never commit this file to Git.**

```env
# ============================================
# ASSEST — ENVIRONMENT VARIABLES
# ============================================

# App
APP_ENV=production
APP_SECRET_KEY=generate-a-random-64-char-string-here
APP_HOST=0.0.0.0
APP_PORT=8000
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com

# Database (Supabase / PostgreSQL)
DATABASE_URL=postgresql://assest_user:password@localhost:5432/assest_db
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-supabase-anon-key
SUPABASE_SERVICE_KEY=your-supabase-service-key

# Vector Database (Qdrant)
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION_NAME=assest_knowledge

# Redis (Celery broker)
REDIS_URL=redis://localhost:6379/0

# AWS
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=ap-south-1
AWS_S3_BUCKET=assest-raw-documents

# LLM APIs
ANTHROPIC_API_KEY=your-anthropic-api-key
OPENAI_API_KEY=your-openai-api-key  # for embeddings

# Slack Bot
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_SIGNING_SECRET=your-signing-secret

# Notion
NOTION_CLIENT_ID=your-notion-client-id
NOTION_CLIENT_SECRET=your-notion-client-secret
NOTION_REDIRECT_URI=https://yourdomain.com/connectors/notion/callback

# Google
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=https://yourdomain.com/connectors/google/callback

# PII Scrubbing
PRESIDIO_ANALYZER_URL=http://localhost:5002
PRESIDIO_ANONYMIZER_URL=http://localhost:5001

# Monitoring
GRAFANA_ADMIN_PASSWORD=your-grafana-password
```

### Step 4 — Docker Compose (Local Development)

```yaml
# docker-compose.yml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    env_file: .env
    volumes:
      - ./backend:/app
    depends_on:
      - postgres
      - qdrant
      - redis
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload

  slack_bot:
    build: ./slack_bot
    env_file: .env
    depends_on:
      - backend
    command: python app.py

  web:
    build: ./web
    ports:
      - "3000:3000"
    env_file: .env
    command: npm run dev

  celery_worker:
    build: ./backend
    env_file: .env
    depends_on:
      - redis
      - postgres
    command: celery -A tasks.celery_app worker --loglevel=info

  celery_beat:
    build: ./backend
    env_file: .env
    depends_on:
      - redis
    command: celery -A tasks.celery_app beat --loglevel=info

  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: assest_user
      POSTGRES_PASSWORD: your-local-password
      POSTGRES_DB: assest_db
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  presidio_analyzer:
    image: mcr.microsoft.com/presidio-analyzer:latest
    ports:
      - "5002:3000"

  presidio_anonymizer:
    image: mcr.microsoft.com/presidio-anonymizer:latest
    ports:
      - "5001:3000"

volumes:
  postgres_data:
  qdrant_data:
  redis_data:
```

---

## 5. Phase 1 — MVP Build (Weeks 1–8)

### Overview

**Goal:** A working onboarding assistant. New employees ask questions. Assest answers from Notion + Google Drive. Available via Slack bot AND web chat.

**Definition of done for Phase 1:**
- [ ] Notion connector ingests all pages from a workspace
- [ ] Google Drive connector ingests all Google Docs and PDFs from specified folders
- [ ] PII is scrubbed before storage
- [ ] Questions answered accurately with source citations
- [ ] Slack bot responds to `/ask` command
- [ ] Web chat interface works in browser
- [ ] 3 pilot customers onboarded
- [ ] All data stored in AWS Mumbai
- [ ] Basic audit logging active

---

### Week 1-2 — Backend Foundation + Notion Connector

#### Task 1.1 — FastAPI App Skeleton

**Antigravity prompt:**
> "Create a FastAPI application in Python 3.11. The app is called Assest — a company knowledge base product. Create the main.py entry point with: CORS middleware configured for the origins in the CORS_ORIGINS env var, a /health endpoint that returns app status and version, router imports for api/query.py, api/ingest.py, api/connectors.py, api/admin.py. Include lifespan context manager for startup/shutdown events. Use pydantic-settings for configuration management loaded from a .env file."

**File:** `backend/main.py`

```python
# CONTEXT FOR ANTIGRAVITY:
# This is the entry point for the Assest FastAPI backend.
# It must:
# 1. Load all environment variables via pydantic-settings
# 2. Configure CORS for the web chat frontend and Slack bot
# 3. Include all route modules
# 4. Connect to PostgreSQL on startup, disconnect on shutdown
# 5. Initialize Qdrant client on startup
# 6. Health check must return: status, version, db_connected, qdrant_connected
```

#### Task 1.2 — Database Models

**Antigravity prompt:**
> "Create SQLAlchemy 2.0 models for the Assest application using async sessions. Create these models: Workspace (id, name, slug, created_at, settings JSONB), Connector (id, workspace_id FK, type enum[notion/google_drive/slack/github/jira], config JSONB encrypted, status enum[active/paused/error], last_synced_at), Document (id, workspace_id FK, connector_id FK, source_url, title, content_hash, chunk_count, last_ingested_at, is_stale), QueryLog (id, workspace_id FK, question, answer, sources JSONB, feedback enum[positive/negative/null], response_time_ms, created_at). Include Alembic migration setup."

**File:** `backend/models/`

#### Task 1.3 — Notion Connector

**Context for Antigravity — paste this before asking it to build:**

> The Notion connector must:
> - Use the official Notion API (api.notion.com) with an integration token
> - Fetch all pages from a workspace that the integration has access to
> - Handle pagination (Notion API returns max 100 results per call)
> - Extract: page title, page content (all block types: paragraph, heading, bulleted list, numbered list, toggle, code, table), last edited time, page URL
> - Convert Notion blocks to clean plain text (strip formatting marks)
> - Skip: databases (fetch separately), archived pages, pages the integration cannot access
> - Store raw content to S3 before processing
> - Return a list of Document objects ready for the ingestion pipeline
> - Handle rate limits: Notion allows 3 requests/second — implement exponential backoff
> - Log all API calls to the audit log

**Antigravity prompt:**
> "Build a Notion connector class for the Assest knowledge base application in Python. It should inherit from a base connector class (base.py) that has abstract methods: connect(), fetch_documents(), validate_config(). The Notion connector uses the notion-client Python library. Implement all methods described in the context above. Include comprehensive error handling for: invalid tokens, rate limits (429), network timeouts, malformed page content. All connector config (token, workspace_id) is stored encrypted in the database and decrypted at runtime."

**File:** `backend/connectors/notion.py`

**Notion API setup steps (do these manually):**
1. Go to https://www.notion.so/my-integrations
2. Click "New integration"
3. Name it "Assest"
4. Select the customer's workspace
5. Enable: Read content, Read user information (no write permissions needed)
6. Copy the Internal Integration Token
7. Customer must share their pages with the integration (Notion requires this)

#### Task 1.4 — Google Drive Connector

**Context for Antigravity:**

> The Google Drive connector must:
> - Use Google Drive API v3 with OAuth 2.0 (not service account — customers authenticate with their own Google account)
> - Fetch all Google Docs and PDF files from specified folder IDs
> - For Google Docs: export to plain text using the export endpoint
> - For PDFs: download the file binary, pass to Unstructured.io for text extraction
> - Recurse into subfolders up to 3 levels deep
> - Extract: file name, file URL (drive.google.com link), last modified time, owner email
> - Skip: Google Sheets, Google Slides, Google Forms, binary files (images, videos)
> - Handle OAuth token refresh automatically
> - Respect folder-level exclusions (customer can mark folders as excluded)
> - Rate limit: 1000 requests per 100 seconds — implement queue

**Antigravity prompt:**
> "Build a Google Drive connector class for Assest. Use the google-api-python-client library. Implement OAuth 2.0 flow: generate auth URL, handle callback, store refresh token encrypted in database, auto-refresh access tokens. Implement folder traversal that respects exclusion lists. For PDF extraction, call a local Unstructured.io instance at the URL in UNSTRUCTURED_URL env var. Return standardised Document objects."

**File:** `backend/connectors/google_drive.py`

**Google Cloud Console setup steps (do these manually):**
1. Go to console.cloud.google.com
2. Create new project: "Assest"
3. Enable Google Drive API
4. Create OAuth 2.0 credentials (Web application type)
5. Add authorised redirect URI: `https://yourdomain.com/connectors/google/callback`
6. Download credentials JSON
7. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env

---

### Week 3-4 — Ingestion Pipeline

#### Task 2.1 — PII Scrubber

**Context for Antigravity:**

> The PII scrubber must detect and remove these entities before any content is stored in the vector database:
> - Indian-specific: Aadhaar numbers (12-digit format), PAN numbers (ABCDE1234F format), Indian mobile numbers (+91 or 10-digit starting with 6-9), GSTIN (15-character alphanumeric), UPI IDs (format@bank)
> - Standard: email addresses, credit card numbers, bank account numbers, passport numbers, dates of birth
> - Names: replace detected person names with [PERSON]
> - Replace all PII with type labels: [AADHAAR_NUMBER], [PAN_NUMBER], [PHONE_NUMBER], [EMAIL], [PERSON]
> - Log what was scrubbed (not the actual values) for audit purposes
> - Return both the scrubbed text and a scrub report

**Antigravity prompt:**
> "Build a PII scrubber module for Assest using Microsoft Presidio. Set up a custom RecognizerRegistry that includes all standard Presidio recognizers plus custom pattern recognizers for: Aadhaar numbers (regex: \b[2-9]{1}[0-9]{11}\b), PAN numbers (regex: [A-Z]{5}[0-9]{4}[A-Z]{1}), Indian mobile numbers (regex: (\+91|0)?[6-9]\d{9}), GSTIN (regex: \d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}), UPI IDs (regex: [a-zA-Z0-9._-]+@[a-zA-Z]+). The scrub_text() function takes raw text and returns a ScrubResult object with: scrubbed_text, entities_found (list of entity types only, not values), scrub_timestamp."

**File:** `backend/ingestion/pii_scrubber.py`

#### Task 2.2 — Document Chunker

**Context for Antigravity:**

> Chunking splits long documents into smaller pieces that fit in the LLM context window and produce accurate vector search results.
> 
> Rules:
> - Target chunk size: 512 tokens (not characters — use tiktoken to count)
> - Overlap between chunks: 50 tokens (so context is preserved at boundaries)
> - Never split in the middle of a sentence
> - Never split in the middle of a code block
> - Preserve metadata per chunk: source_url, document_title, chunk_index, total_chunks, section_heading (the nearest heading above this chunk)
> - For Notion pages: respect page structure — keep a heading with its following paragraphs together when possible
> - For PDFs: use Unstructured.io's element detection to keep tables together

**Antigravity prompt:**
> "Build a document chunker for Assest using LlamaIndex. Use the SentenceSplitter with chunk_size=512, chunk_overlap=50, tokenizer from tiktoken with cl100k_base encoding. Create a chunk_document() function that takes a Document object (with content, title, source_url, metadata) and returns a list of Chunk objects. Each Chunk has: chunk_id (uuid), document_id, content (scrubbed text), embedding (None at this stage), metadata dict containing source_url, title, chunk_index, total_chunks, section_heading, ingested_at timestamp."

**File:** `backend/ingestion/chunker.py`

#### Task 2.3 — Embedder

**Context for Antigravity:**

> Embeddings convert text into numerical vectors so semantically similar content can be found via vector search.
> 
> Rules:
> - Use OpenAI text-embedding-3-small model (1536 dimensions, cheapest, good quality)
> - Batch embed: send up to 100 chunks per API call to reduce costs
> - Cache embeddings: if the content hash hasn't changed, don't re-embed
> - Store embeddings in Qdrant with the chunk metadata as payload
> - Qdrant collection name comes from QDRANT_COLLECTION_NAME env var
> - Each vector in Qdrant must have payload: workspace_id, document_id, chunk_id, source_url, title, content (the actual text for retrieval), section_heading, ingested_at

**Antigravity prompt:**
> "Build an embedder module for Assest. It must: batch embed text chunks using the OpenAI embeddings API (model: text-embedding-3-small), upsert vectors into Qdrant using the qdrant-client Python library, filter by workspace_id in all queries (multi-tenant isolation), handle Qdrant collection creation if it doesn't exist (create with vectors config: size=1536, distance=Cosine). Create a Qdrant collection per environment (assest_knowledge_dev, assest_knowledge_prod). Implement embed_and_store(chunks, workspace_id) and delete_document(document_id, workspace_id) functions."

**File:** `backend/ingestion/embedder.py`

#### Task 2.4 — Ingestion Pipeline Orchestrator

**Antigravity prompt:**
> "Build the main ingestion pipeline orchestrator for Assest. The run_ingestion(connector_id, workspace_id) function must: 1) Load connector config from database, 2) Instantiate the correct connector class based on connector type, 3) Fetch all documents from the connector, 4) For each document: check content hash against database (skip if unchanged), store raw file to S3, run PII scrubber, chunk the document, embed and store chunks, update document record in database. 5) Mark any previously-ingested documents not seen in this run as potentially stale. 6) Update connector last_synced_at. Wrap the whole thing in a Celery task so it runs asynchronously. Emit progress events to a Redis pub/sub channel so the frontend can show live progress."

**File:** `backend/ingestion/pipeline.py` and `backend/tasks/ingestion_tasks.py`

---

### Week 4-5 — Query Engine

#### Task 3.1 — Retriever

**Context for Antigravity:**

> The retriever finds the most relevant knowledge chunks for a given question.
> 
> Rules:
> - Embed the user's question using the same model as the chunks (text-embedding-3-small)
> - Search Qdrant for top 8 most similar chunks
> - ALWAYS filter by workspace_id — never return chunks from another workspace
> - Also filter by any connector exclusions the workspace has configured
> - Return chunks with their similarity scores
> - Minimum similarity threshold: 0.7 (below this, the chunk is not relevant)
> - If fewer than 2 chunks are above threshold, return a "knowledge not found" signal

**Antigravity prompt:**
> "Build the retriever module for Assest. Implement search(question, workspace_id, top_k=8) that: embeds the question, queries Qdrant with a must filter on workspace_id, applies score threshold of 0.7, returns a list of RetrievalResult objects with fields: chunk_id, content, source_url, title, score, section_heading. If no results above threshold, raise KnowledgeNotFoundError. Handle Qdrant connection errors gracefully."

**File:** `backend/query/retriever.py`

#### Task 3.2 — Answer Generator

**Context for Antigravity:**

> The generator takes retrieved chunks and a question, sends them to Claude, and gets back a grounded answer.
> 
> Rules:
> - Model: claude-sonnet-4-6 (claude-sonnet-4-20250514)
> - System prompt must instruct Claude to:
>   - Answer ONLY based on the provided knowledge chunks
>   - If the answer is not in the chunks, say "I couldn't find this in your company's knowledge base" — never hallucinate
>   - Always cite the source document for each claim (use the source_url)
>   - Keep answers concise and direct — this is a work tool, not a chatbot
>   - Format for Slack: use Slack mrkdwn formatting (*bold*, _italic_, bullet points with •)
>   - Format for web: use Markdown
> - Max tokens: 800
> - Temperature: 0 (deterministic, factual answers only)
> - Include the question and all retrieved chunks in the user message

**Antigravity prompt:**
> "Build the answer generator for Assest using the Anthropic Python SDK (anthropic library). Implement generate_answer(question, chunks, response_format='slack'|'markdown') that constructs a prompt with the system instructions above, sends to Claude claude-sonnet-4-20250514, parses the response, and returns an Answer object with: answer_text (formatted), sources (list of unique source_urls with titles), model_used, tokens_used, response_time_ms. Log all queries and responses to the QueryLog database table."

**File:** `backend/query/generator.py`

#### Task 3.3 — Query API Endpoint

**Antigravity prompt:**
> "Build the POST /query FastAPI endpoint for Assest. Request body: QueryRequest(question: str, workspace_id: str, response_format: str = 'markdown'). The endpoint must: validate workspace_id exists in database, call retriever.search(), handle KnowledgeNotFoundError with a friendly response, call generator.generate_answer(), return QueryResponse(answer: str, sources: list[Source], query_id: str for feedback). Rate limit: 20 requests per minute per workspace using slowapi. Require API key authentication via X-API-Key header."

**File:** `backend/api/query.py`

---

### Week 5-6 — Interfaces

#### Task 4.1 — Slack Bot

**Context for Antigravity:**

> The Slack bot is the primary interface for MVP. It uses Socket Mode (no public webhook URL needed — works behind a firewall).
> 
> Commands to implement:
> - `/ask [question]` — main command, queries Assest and returns answer
> - `/assest-setup` — shows connector status (admin only)
> - `/assest-feedback [good/bad] [query_id]` — submit feedback on an answer
> 
> Bot behaviour:
> - When /ask is called, immediately post "Searching your knowledge base..." (Slack requires response within 3s)
> - Then post the actual answer as a follow-up message in the same thread
> - Format: answer text, then a divider, then "Sources:" with clickable links
> - Add 👍 and 👎 reaction buttons below each answer for feedback
> - If knowledge not found: "I couldn't find this in your company's knowledge base. Try rephrasing, or ask your team to add this to Notion."
> - Log every interaction with workspace_id, user_id (anonymised), question, answer

**Antigravity prompt:**
> "Build a Slack bot for Assest using Slack Bolt for Python in Socket Mode. Implement the three slash commands above. For /ask: use respond() for the immediate acknowledgment, then use client.chat_postMessage() for the full answer. Format answers with Slack Block Kit: a section block for the answer, a divider, a context block for sources. Add action buttons (value=query_id) for thumbs up/down feedback. Handle the action callbacks to update QueryLog.feedback in the database. The bot must identify the workspace from the Slack workspace ID — look up workspace_id in the database."

**File:** `slack_bot/app.py` and `slack_bot/handlers/`

**Slack App setup steps (do these manually):**
1. Go to api.slack.com/apps
2. Create new app → From scratch
3. Name: "Assest" 
4. Enable Socket Mode (Settings → Socket Mode)
5. Generate App-Level Token with connections:write scope → save as SLACK_APP_TOKEN
6. Add slash commands: /ask, /assest-setup, /assest-feedback
7. Add OAuth scopes (Bot Token Scopes): commands, chat:write, reactions:read
8. Install to workspace → save Bot User OAuth Token as SLACK_BOT_TOKEN
9. Save Signing Secret as SLACK_SIGNING_SECRET

#### Task 4.2 — Web Chat Frontend

**Context for Antigravity:**

> The web chat is a simple, clean interface for employees who prefer browser over Slack.
> 
> Requirements:
> - Built with Next.js 14 (App Router), TypeScript, Tailwind CSS
> - Login with Google OAuth (employees use their company Google account)
> - Main screen: chat input at bottom, messages above, source cards on the right side
> - Each answer shows: answer text, source list with clickable links, feedback buttons
> - No conversation history needed in MVP (each question is independent)
> - Loading state: animated dots while waiting for answer
> - Error state: friendly message if API call fails
> - Mobile responsive
> - No dark mode needed for MVP

**Antigravity prompt:**
> "Build the web chat interface for Assest using Next.js 14 with App Router, TypeScript, and Tailwind CSS. Create: app/chat/page.tsx (main chat page, requires auth), components/ChatWindow.tsx (message list + input), components/MessageBubble.tsx (renders assistant answer with markdown using react-markdown), components/SourceCard.tsx (shows source title, URL, and icon based on source type). The chat page calls POST /query on the Assest backend with the user's question and workspace_id (stored in session). Show a skeleton loader while waiting. Use Next.js API routes as a proxy to avoid exposing the backend API key to the browser."

**Files:** `web/app/chat/page.tsx`, `web/components/`

---

### Week 7-8 — Compliance, Testing, and Pilot Setup

#### Task 5.1 — Audit Logging

**Antigravity prompt:**
> "Build an audit logging system for Assest that complies with CERT-In requirements (180-day retention). Create a AuditLog database model with fields: id, workspace_id, event_type (enum: document_ingested, document_deleted, query_made, connector_added, connector_removed, user_login, pii_detected, data_exported), actor_id, resource_id, metadata JSONB, ip_address, timestamp. Create an audit_log() helper function used throughout the codebase. Logs must be immutable (no update/delete operations). Set up a PostgreSQL retention policy to archive logs older than 180 days to S3 instead of deleting them."

**File:** `backend/core/audit.py`

#### Task 5.2 — API Authentication

**Antigravity prompt:**
> "Build API key authentication for Assest. Each workspace gets a unique API key generated on creation (format: ast_live_[32 random chars] for production, ast_test_[32 chars] for test). Store API keys as bcrypt hashes in the database. Build a FastAPI dependency get_workspace_from_api_key() that: extracts X-API-Key header, validates it, returns the workspace object, raises 401 if invalid. Also build a simple admin token system for internal routes using a static ADMIN_TOKEN env var."

**File:** `backend/core/security.py`

#### Task 5.3 — Pilot Customer Onboarding Script

**Antigravity prompt:**
> "Build a CLI onboarding script for Assest pilots. The script (scripts/onboard_pilot.py) should: 1) Prompt for company name, admin email, Slack workspace ID, 2) Create workspace record in database, 3) Generate API key and display it, 4) Output a setup checklist in the terminal: Notion steps, Google Drive steps, Slack bot installation link. Use the click library for the CLI. Also create a POST /admin/workspaces endpoint that does the same thing via API."

---

## 6. Phase 2 — Full Knowledge Platform (Months 3–6)

**Unlock criteria:** 3 paying pilots, consistent positive feedback, clear demand for more sources.

### New Connectors

#### Task — Slack Connector (ingestion, not bot)

**Context for Antigravity:**

> Unlike the Slack bot (which answers questions), the Slack connector ingests valuable knowledge from Slack channels.
> 
> What to ingest:
> - Only specific channels that the workspace admin approves (never all channels)
> - Only messages that contain decisions, answers, or documentation signals
> - A message is worth ingesting if: it's longer than 50 words, or it's a reply to a question that got 2+ reactions, or it's pinned, or it's in a designated #decisions or #incidents channel
> - Thread context: always ingest full thread, not just the top message
> - Format: "In #channel-name on [date], [anonymised user] said: [message content]"
> - Strip: emoji, GIFs, file attachments (unless PDF), mentions
> - Never ingest: DMs, private channels unless explicitly added

**Antigravity prompt:**
> "Build a Slack ingestion connector for Assest (separate from the Slack bot). Use the Slack Web API via slack_sdk. Implement channel filtering using an approved_channels list stored in connector config. Implement message quality scoring: score > 0.6 = ingest. Score based on: message length (0-0.4), reaction count (0-0.3), is_pinned (0.3), is_thread_reply_with_engagement (0.2). Fetch in batches of 200 messages, handle pagination. Anonymise user IDs — map to stable pseudonyms (User_A, User_B) stored in workspace config."

**File:** `backend/connectors/slack.py`

#### Task — GitHub Connector

**What to ingest from GitHub:**
- README files from all repositories
- Pull request descriptions that are longer than 100 words (engineering decisions live here)
- Wiki pages
- Issues that are closed and labeled "documentation" or "decision"
- Skip: code files, comments, automated bot messages

**Antigravity prompt:**
> "Build a GitHub connector for Assest using the PyGithub library. OAuth with GitHub Apps (not personal access tokens — more secure for multi-tenant). Ingest: README.md from each repo (all branches if different), PR descriptions where body length > 100 chars and PR is merged, Wiki pages, closed issues with labels containing 'doc' or 'decision' or 'adr'. Format ingested content with repo context: '[Repo: repo-name] [Type: README/PR/Wiki/Issue] [Date: date]'."

**File:** `backend/connectors/github.py`

### Staleness Detection System

**Antigravity prompt:**
> "Build a staleness detection system for Assest. A document is stale if: it hasn't been re-synced in more than 7 days (configurable per connector), OR its source has been modified (check last_modified_at from connector against stored ingested_at), OR a newer document contradicts it (detected by embedding similarity + LLM check). Create a Celery beat task that runs daily, checks all documents, marks stale ones, and sends a weekly digest email to workspace admins listing stale documents. Also expose GET /admin/staleness/{workspace_id} endpoint."

**File:** `backend/ingestion/freshness.py`

### Analytics Dashboard

**Antigravity prompt:**
> "Build a simple analytics dashboard page in the Assest web app (app/admin/page.tsx). Show: total documents ingested (by connector), total queries this month, most asked questions (top 10), answer quality score (% positive feedback), knowledge gaps (questions where answer was not found — these show what's missing from the knowledge base), connector health status. Fetch data from GET /admin/analytics/{workspace_id}. Use recharts for the charts. Keep it simple — this is for the workspace admin."

---

## 7. Phase 3 — Skills File Engine (Months 6–12)

**Unlock criteria:** 8+ customers, clear request for agent integration, stable ingestion layer.

### What Skills Files Are

A skills file is a structured, executable representation of a company process. Instead of a paragraph describing how refunds work, a skills file is a decision tree an AI agent can follow:

```json
{
  "skill_id": "handle_customer_refund",
  "skill_name": "Customer Refund Handling",
  "version": "1.2",
  "last_updated": "2024-01-15",
  "source_documents": ["notion://page/xyz", "drive://doc/abc"],
  "trigger_conditions": ["customer requests refund", "order cancellation"],
  "steps": [
    {
      "step": 1,
      "action": "check_order_age",
      "condition": "order_date < 30 days ago",
      "if_true": "proceed_to_step_2",
      "if_false": "escalate_to_manager"
    },
    {
      "step": 2,
      "action": "check_refund_reason",
      "valid_reasons": ["defective", "wrong_item", "not_delivered"],
      "if_valid": "approve_refund",
      "if_invalid": "request_evidence"
    }
  ],
  "output": "refund_decision",
  "confidence_score": 0.87
}
```

### Task — Skills Extractor

**Antigravity prompt:**
> "Build a skills extraction system for Assest. The extract_skills(workspace_id) function: 1) Retrieves all ingested documents for the workspace, 2) Groups documents by topic using clustering (use sklearn KMeans on embeddings), 3) For each cluster, sends representative chunks to Claude with this prompt: 'These documents describe a business process. Extract the decision tree as a structured JSON skills file following this schema: [schema above]. If multiple processes are described, create multiple skills files. Focus on: trigger conditions, decision points, actions, escalation paths.' 4) Validates the JSON against a Pydantic schema, 5) Stores skills files in PostgreSQL and as JSON files in S3, 6) Versions each skills file when updated."

**File:** `backend/skills/extractor.py`

### Task — Skills API

**Antigravity prompt:**
> "Build the Skills API for Assest. Endpoints: GET /skills/{workspace_id} — list all skills with metadata, GET /skills/{workspace_id}/{skill_id} — get a specific skills file, GET /skills/{workspace_id}/search?q=refund — semantic search over skills, POST /skills/{workspace_id}/{skill_id}/feedback — flag a skills file as incorrect. Authentication: API key. Rate limit: 100 requests/minute. This API is what external AI agents call to get context before performing actions."

**File:** `backend/api/skills.py`

---

## 8. Phase 4 — Full Company Brain Platform (Month 12+)

**Unlock criteria:** ₹10L+ MRR, Series A funding or YC backing, dedicated engineering help (even if AI agents).

### WhatsApp Connector

**Implementation approach:**
- Use Meta's WhatsApp Business API via a BSP (Gupshup or Kaleyra — both India-based)
- Customer connects their WhatsApp Business account
- Assest reads business conversation history (customer has consent by their terms)
- Focus: support ticket resolutions (how issues were solved), FAQs (repeated questions + answers), product instructions sent to customers

### Multilingual Support (Hindi First)

**Approach:**
- Language detection on all ingested content using langdetect library
- Hindi content: use IndicTrans2 for Hindi-to-English translation before embedding (embedding models work better in English)
- Store both original (Hindi) and translated (English) versions
- Query detection: if question is in Hindi, translate to English for retrieval, translate answer back to Hindi
- Transliteration: handle Hinglish (Hindi in Roman script) using IndicXlit

### Multi-Tenant Architecture Hardening

When you reach 20+ customers, these become critical:
- Separate Qdrant collections per workspace (already designed for this)
- Row-level security in PostgreSQL for all workspace data
- Workspace-level rate limiting on all endpoints
- Isolated Celery queues per workspace (no one customer's ingestion blocks another)
- Data export API: customers can download all their data as JSON at any time

---

## 9. Compliance and Security

### DPDP Act 2023 — Implementation Checklist

```python
# Every ingestion run must produce a ConsentRecord:
# {
#   workspace_id: str,
#   connector_type: str,
#   data_fiduciary: str,  # the customer company
#   data_processor: "Assest",
#   purpose: "Knowledge base construction for internal AI tools",
#   consent_given_at: datetime,
#   consent_given_by: str,  # admin email
#   data_categories: list[str],  # ["company documents", "internal communications"]
#   retention_days: int,
#   deletion_method: "hard_delete"
# }
```

**DPDP Checklist:**
- [ ] Consent recorded before any data is ingested
- [ ] Data subjects (employees) can request their data be excluded
- [ ] Full workspace deletion works in under 24 hours (test this)
- [ ] No customer data used for Assest model training (explicit in ToS)
- [ ] Data stays in AWS Mumbai (ap-south-1) — verify with AWS Config
- [ ] Retention policy: delete ingested content 30 days after customer churns
- [ ] Breach notification: process documented, can notify within 72 hours
- [ ] DPA (Data Processing Agreement) signed before any customer onboarding

### IT Act 2000 / CERT-In Compliance

- [ ] Audit logs retained 180 days minimum (in India)
- [ ] CERT-In incident reporting procedure documented
- [ ] NTP synchronization: all servers sync to time.google.com
- [ ] Penetration test before first enterprise customer
- [ ] Vulnerability disclosure policy published

### Security Hardening Checklist

```bash
# Run these on the EC2 instance

# Firewall
sudo ufw enable
sudo ufw allow 22/tcp   # SSH (restrict to your IP only in production)
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw deny all       # Block everything else

# Fail2ban (blocks brute force)
sudo apt install fail2ban -y

# SSL Certificate (free via Let's Encrypt)
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d yourdomain.com -d app.yourdomain.com

# Disable root SSH login
sudo sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart sshd
```

**Application security:**
- All API endpoints require authentication (no public endpoints except /health)
- API keys hashed with bcrypt before storage
- All database queries use parameterised statements (SQLAlchemy handles this)
- Connector OAuth tokens encrypted at rest using Fernet encryption
- No secrets in code or Git history — all via environment variables
- Dependency scanning: run `pip audit` weekly

---

## 10. Testing Strategy

### Testing Philosophy for Solo AI-Assisted Development

Since Antigravity writes the code, your job is to write tests that verify the code does what it should. Tests are also the clearest way to describe requirements to Antigravity.

### Unit Tests

**Antigravity prompt template for tests:**
> "Write pytest unit tests for the [module name] in Assest. Test these specific behaviours: [list behaviours]. Use pytest fixtures for database and Qdrant mocking. Mock all external API calls (Notion API, Google API, Anthropic API) using unittest.mock. Each test should be independent and not require a running database. Test file: backend/tests/test_[module].py"

**Critical tests to write:**

```python
# test_pii_scrubber.py — test these cases:
# 1. Aadhaar number is detected and replaced with [AADHAAR_NUMBER]
# 2. PAN number ABCDE1234F is detected
# 3. Indian mobile number +91 9876543210 is detected
# 4. Regular text with no PII passes through unchanged
# 5. Multiple PII types in one document are all caught
# 6. PII inside a code block is NOT scrubbed (code context)

# test_chunker.py — test these cases:
# 1. Document shorter than chunk_size returns single chunk
# 2. Long document returns multiple chunks with correct overlap
# 3. Chunk never splits mid-sentence
# 4. Each chunk has correct metadata (source_url, chunk_index, total_chunks)
# 5. Code blocks are not split

# test_retriever.py — test these cases:
# 1. Query returns only chunks from the correct workspace_id
# 2. Chunks below similarity threshold are excluded
# 3. KnowledgeNotFoundError raised when no relevant chunks
# 4. Results sorted by similarity score descending

# test_ingestion_pipeline.py — test these cases:
# 1. Unchanged document (same content hash) is not re-embedded
# 2. Modified document is re-embedded and old chunks deleted
# 3. PII scrubbing is called before embedding
# 4. S3 raw file upload happens before processing
# 5. Connector last_synced_at is updated after successful run
```

### Integration Tests

**Antigravity prompt:**
> "Write integration tests for Assest that test the full query path. Use a test Qdrant instance and test PostgreSQL database (use pytest-asyncio and test fixtures). Test: given 3 pre-loaded knowledge chunks, a question about their content returns an accurate answer with correct source citations. Test the failure case: a question about unknown topics returns the knowledge-not-found response."

### Load Testing

```bash
# Install locust
pip install locust

# Run load test (after MVP is live)
# Target: 50 concurrent users, 20 req/sec, for 5 minutes
locust -f tests/load/locustfile.py --host=https://yourdomain.com \
  --users 50 --spawn-rate 10 --run-time 5m
```

---

## 11. Deployment and DevOps

### Production Deployment Flow

```bash
# Every deployment follows this sequence
# 1. Push to main branch
# 2. GitHub Actions runs tests
# 3. If tests pass, build Docker images
# 4. Push images to AWS ECR (Elastic Container Registry)
# 5. SSH to EC2, pull new images, restart containers

# GitHub Actions workflow (create .github/workflows/deploy.yml):
# Trigger: push to main
# Steps:
#   - Run pytest
#   - Build Docker images
#   - Push to ECR
#   - Deploy to EC2 via SSH
```

**Antigravity prompt for CI/CD:**
> "Create a GitHub Actions workflow file for Assest (.github/workflows/deploy.yml). The workflow triggers on push to main branch. Steps: 1) Checkout code, 2) Set up Python 3.11, 3) Install dependencies and run pytest (fail if any test fails), 4) Configure AWS credentials from GitHub secrets, 5) Build Docker images for backend, slack_bot, and web, 6) Push to AWS ECR repository in ap-south-1, 7) SSH to EC2 (use SSH key from GitHub secrets), 8) Pull new images and run docker compose up -d with docker-compose.prod.yml, 9) Run database migrations (alembic upgrade head), 10) Health check: curl /health and fail if not 200."

### Nginx Configuration

**Antigravity prompt:**
> "Write an Nginx configuration for Assest that: serves the Next.js web app at yourdomain.com, proxies API requests from app.yourdomain.com/api to FastAPI on port 8000, proxies the web app from app.yourdomain.com to Next.js on port 3000, includes SSL termination (certificates managed by certbot), sets security headers (X-Frame-Options, X-Content-Type-Options, HSTS), rate limiting: 20 req/s per IP on /api/query, gzip compression for all text responses, logs to /var/log/nginx/assest_access.log and assest_error.log."

### Backup Strategy

```bash
# Create scripts/backup.sh

#!/bin/bash
# Run daily via cron: 0 2 * * * /home/ubuntu/assest/scripts/backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BUCKET="assest-backups"

# PostgreSQL backup
docker exec assest_postgres pg_dump -U assest_user assest_db | \
  gzip | aws s3 cp - s3://$BUCKET/postgres/assest_$DATE.sql.gz

# Qdrant backup (snapshot)
curl -X POST "http://localhost:6333/collections/assest_knowledge/snapshots"
SNAPSHOT=$(curl "http://localhost:6333/collections/assest_knowledge/snapshots" | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['result'][-1]['name'])")
aws s3 cp /qdrant/snapshots/$SNAPSHOT s3://$BUCKET/qdrant/$SNAPSHOT

echo "Backup completed: $DATE"
```

### Monitoring Setup

**Key metrics to alert on:**
- API response time > 10 seconds → alert
- Ingestion job failed → alert immediately
- Qdrant disk usage > 80% → alert
- Query volume drop > 50% in 1 hour → alert (might indicate bot is down)
- Error rate > 5% → alert

**Antigravity prompt:**
> "Set up Prometheus metrics collection for the Assest FastAPI backend using prometheus-fastapi-instrumentator. Track these custom metrics: assest_queries_total (counter, labels: workspace_id, status), assest_query_duration_seconds (histogram), assest_ingestion_jobs_total (counter, labels: connector_type, status), assest_chunks_stored_total (gauge, labels: workspace_id), assest_knowledge_not_found_total (counter, labels: workspace_id). Expose metrics at GET /metrics (internal only, not proxied by Nginx)."

---

## 12. Assest as Its Own First Customer

This is non-negotiable. You are a one-person company. Assest must run on Assest.

### Your Company Brain Setup

**Sources to ingest into your own Assest workspace:**
- This document (the product blueprint)
- Your customer conversation notes (Notion)
- Your competitive research notes
- Your compliance checklist
- Your pilot customer SOPs (how to onboard a new pilot)
- Your incident runbooks (what to do when the ingestion pipeline breaks)

### AI Agents That Run Your Company

**Agent 1 — Customer Support Triage**
Watches your support email/Slack. When a customer reports an issue, it:
1. Queries Assest for relevant runbook
2. Attempts automated fix if the runbook has one
3. Drafts a response to the customer
4. Escalates to you (human) only if it can't resolve

**Agent 2 — Ingestion Monitor**
Runs every hour. Checks all active connector sync statuses. If a sync has failed or is overdue, it:
1. Queries error logs
2. Attempts to restart the failed job
3. If restart fails twice, sends you a Slack DM with full context

**Agent 3 — Onboarding Agent**
When a new pilot signs up, it:
1. Creates workspace in database
2. Generates API key
3. Sends welcome email with setup instructions
4. Schedules a Calendly link for the setup call
5. Creates a Notion page in your internal workspace with the customer's details

**Antigravity prompt for Agent 1:**
> "Build a customer support triage agent for Assest using LangGraph. The agent monitors a Gmail inbox (label: 'assest-support'). When a new email arrives: 1) Extract the customer's workspace_id from their email address (look up in database), 2) Classify the issue type using Claude (enum: ingestion_error, answer_quality, connector_auth, billing, other), 3) Query the Assest knowledge base for the relevant runbook, 4) If issue type is ingestion_error and runbook has automated fix steps, attempt the fix via the admin API, 5) Draft a customer response email using Claude (professional, concise, solution-focused), 6) If confidence > 0.85, send automatically; if not, draft to Gmail drafts folder for your review."

---

## 13. Go-to-Market Plan

### Finding Your First 3 Pilots

**Week 1-2: Build target list**
- Sources: Tracxn (tracxn.com), Inc42, YourStory, LinkedIn
- Filter: Indian startup, Seed to Series B, 50-300 employees, tech product company, founded 2019-2023
- Target role: CTO, VP Engineering, Head of Operations, Co-founder
- Build list of 50 companies in a Notion database

**Week 3-4: Outreach**

Message template (LinkedIn or email):

> Subject: Quick question about knowledge management at [Company]
>
> Hi [Name],
>
> I've been researching how fast-growing Indian startups manage institutional knowledge — specifically what happens when senior people leave or new hires join.
>
> I'm building a tool to solve this and would love 20 minutes to understand how [Company] handles it today — not to pitch, just to learn.
>
> Would you be open to a quick call this week?
>
> [Your name]

**Week 5-6: Identify pilots**

In the conversation, listen for:
- "Oh god, this is a real problem" → pilot candidate
- Polite interest → not yet
- "We already use [tool]" → ask what's missing from it

Pilot offer:
> "I'd love to set this up for [Company] completely free for 60 days. I need 2 hours of your time to connect your Notion and Google Drive, and then your team can start using it immediately. No contract, cancel anytime."

### Pricing Conversations (Month 3+)

After 60 days of free pilot, the conversion conversation:

> "Over the last 60 days, Assest answered [X] questions from your team. How much time do you think that saved your senior engineers? At ₹15,000/month, that's probably less than 2 hours of an engineer's time. Want to continue?"

### Metrics to Track From Day One

| Metric | Target (Month 3) | Target (Month 6) |
|---|---|---|
| Pilot customers | 3 | 8 |
| Paying customers | 0 | 4 |
| MRR | ₹0 | ₹60,000 |
| Queries per month (total) | 500 | 3,000 |
| Answer quality score | >75% positive | >85% positive |
| Knowledge not found rate | <30% | <15% |

---

## 14. Antigravity AI IDE — Prompting Guide

### How to Use This Document With Antigravity

This section is a guide for getting the best results from your AI IDE when building Assest.

**Rule 1: Always provide context before a task**

Bad prompt:
> "Build the Notion connector"

Good prompt:
> "I'm building Assest — a company knowledge base product in Python. We use FastAPI, LlamaIndex, Qdrant, and Anthropic's Claude API. I need you to build the Notion connector class as described in the blueprint. Here is the context: [paste the Task 1.3 section]. Follow the data flow described and return Document objects with these fields: [list fields]."

**Rule 2: Paste the relevant architecture section**

Before any task, paste the architecture diagram and the specific task context block. Antigravity will produce code that fits the existing system rather than creating something incompatible.

**Rule 3: Ask for one file at a time**

Never ask for multiple files in one prompt. Ask for one file, review it, then move to the next.

**Rule 4: Use the error-fix pattern**

When Antigravity produces code that fails:
> "This code produced the following error: [paste full error traceback]. Here is the code that failed: [paste code]. The expected behaviour is: [describe what should happen]. Fix the error and explain what was wrong."

**Rule 5: Ask for tests alongside implementation**

> "Now write pytest unit tests for the file you just created. Test the following specific cases: [list from the testing section above]."

### Standard Antigravity Context Block

Paste this at the start of every new Antigravity session about Assest:

```
PROJECT: Assest — Company knowledge base for Indian startups
LANGUAGE: Python 3.11
FRAMEWORK: FastAPI (backend), Next.js 14 (frontend)
DATABASE: PostgreSQL (SQLAlchemy 2.0 async), Qdrant (vector DB)
LLM: Anthropic Claude API (claude-sonnet-4-20250514)
EMBEDDINGS: OpenAI text-embedding-3-small (1536 dimensions)
TASK QUEUE: Celery + Redis
DEPLOYMENT: AWS Mumbai (ap-south-1), Docker
COMPLIANCE: DPDP Act 2023, IT Act 2000, data must stay in India
ARCHITECTURE: Multi-tenant SaaS. workspace_id isolates all data.
CURRENT PHASE: [Phase 1 / Phase 2 / Phase 3 — update as you progress]
CURRENT TASK: [describe what you're building right now]
```

### Common Antigravity Prompts You'll Use Repeatedly

**Adding a new connector:**
> "Using the existing base.py connector class in assest/backend/connectors/base.py, create a new [SOURCE_NAME] connector. It must implement connect(), fetch_documents(), and validate_config(). Documents must be returned as Document objects with: content (scrubbed), source_url, title, last_modified_at, connector_id, workspace_id. Handle these specific error cases: [list error cases for this source's API]."

**Adding a new API endpoint:**
> "Add a new FastAPI endpoint to assest/backend/api/[file].py. Method: [GET/POST/DELETE]. Path: /[path]. Request body: [describe or paste Pydantic schema]. Response: [describe response]. It must: require API key auth via the existing get_workspace_from_api_key dependency, log to audit log, return appropriate HTTP status codes for error cases."

**Debugging an ingestion issue:**
> "The Assest ingestion pipeline is failing for the [connector type] connector. Here is the error: [paste error]. Here is the relevant code: [paste pipeline.py and the connector file]. The connector config stored in the database is: [paste config structure, no actual credentials]. Diagnose the issue and fix it."

---

## Appendix A — API Reference (MVP)

### POST /query
```json
// Request
{
  "question": "How do we handle customer refunds?",
  "workspace_id": "ws_abc123",
  "response_format": "markdown"
}

// Response
{
  "answer": "## Refund Policy\n\nRefunds are processed within...",
  "sources": [
    {
      "title": "Customer Support Handbook",
      "url": "https://notion.so/page/xyz",
      "connector_type": "notion"
    }
  ],
  "query_id": "q_def456",
  "knowledge_found": true,
  "response_time_ms": 1240
}
```

### POST /ingest
```json
// Request
{
  "connector_id": "conn_ghi789",
  "workspace_id": "ws_abc123",
  "force_full_sync": false
}

// Response
{
  "job_id": "job_jkl012",
  "status": "queued",
  "estimated_duration_minutes": 5
}
```

### GET /connectors/{workspace_id}
```json
// Response
{
  "connectors": [
    {
      "id": "conn_ghi789",
      "type": "notion",
      "status": "active",
      "last_synced_at": "2024-01-15T10:30:00Z",
      "document_count": 142,
      "is_stale": false
    }
  ]
}
```

---

## Appendix B — Cost Estimate (MVP Stage)

| Service | Specification | Monthly Cost (INR) |
|---|---|---|
| AWS EC2 t3.medium | Mumbai region | ₹3,500 |
| AWS S3 | 10GB storage | ₹200 |
| AWS Data Transfer | 50GB outbound | ₹350 |
| Elastic IP | 1 IP | ₹300 |
| Anthropic Claude API | ~50,000 tokens/day at pilot scale | ₹3,000 |
| OpenAI Embeddings | ~1M tokens/month | ₹700 |
| Domain + SSL | yourdomain.com | ₹800/year = ₹70/month |
| **Total** | | **~₹8,120/month** |

At ₹15,000/month per customer, you break even with 1 paying customer. Every customer after that is profit.

---

*Document version: 1.0 — Built for Antigravity AI IDE*  
*Last updated: May 2026*  
*This document is designed for AI-assisted development. Paste relevant sections into Antigravity before each coding task.*
