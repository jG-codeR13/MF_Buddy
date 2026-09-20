# Mutual Fund FAQ Assistant: Implementation Plan

This document outlines the detailed, phase-wise implementation plan for the **Facts-Only Mutual Fund FAQ Assistant**, based on the requirements from `problemStatement.md` and the system design in `architecture.md`.

## Phase 1: Environment & Project Setup
Setting up the foundation of the project.
* **Dependencies:** `langchain`, `streamlit`, `chromadb`, `groq`, `sentence-transformers`, `pypdf`, `beautifulsoup4`.
* **Configuration:** `.env` for API keys (e.g., `GROQ_API_KEY`) and `.gitignore` to prevent committing sensitive data and local vector stores.

## Phase 2: Data Ingestion Pipeline
Building the module to load, chunk, and embed the mutual fund documents. This phase is broken into three structured sub-phases to ensure high data quality.

### Phase 2.1: Data Scraping & Markdown Conversion
* **Focus:** Fetch HTML/PDFs for the selected funds and convert them natively to Markdown to preserve tables and structure.
* **Tasks:** 
  - Fetch raw HTML for the 5 selected funds.
  - Rigorously capture metadata (URL, Fund Name, Document Type).
  - Use `markdownify` to convert the HTML body directly into Markdown. This preserves complex structures like tables (e.g., `| Expense Ratio | 0.60% |`) and headers, ensuring no semantic relationships are lost.
  - Save the output to `raw/scraped_markdown.json`.

### Phase 2.2: Two-Pass Markdown Chunking
* **Focus:** Split the Markdown text into manageable semantic blocks while retaining section context.
* **Tasks:** 
  - **Pass 1:** Use LangChain's `MarkdownHeaderTextSplitter` to split the document by headers (`#`, `##`, `###`) and inject those headers into the chunk metadata.
  - **Pass 2:** Use `RecursiveCharacterTextSplitter` (chunk_size=1500, overlap=200) on the resulting documents to break down massive tables (like Holdings) while preserving the header metadata injected in Pass 1.

### Phase 2.3: Embedding & Vector Storage
* **Focus:** Convert text chunks into vector representations and persist them.
* **Tasks:** 
  - Apply **Context Enrichment**: Prepend `fund_name` and markdown headers to each chunk's `page_content` before embedding to ensure context is preserved in the vector space.
  - Initialize the BGE embedding model (`BAAI/bge-small-en-v1.5`) via `sentence-transformers`, using query instruction format.
  - Embed all context-enriched chunks and store them securely in a local `ChromaDB` instance along with their original metadata.

## Phase 3: Guardrails & Refusal Module
Implementing the security and refusal logic to strictly adhere to the "facts-only" constraint.
* **Script:** `src/guardrails.py`
* **PII Detection (Priority 1):** Regex-based detection of PAN, Aadhaar, email, and phone numbers. If detected, refuse without echoing the PII back.
* **Advisory Detection (Priority 2):** Evaluate user queries to detect advisory intent ("Should I buy?", "Which is better?"). If flagged, return a polite refusal and educational links (AMFI/SEBI).
* **Performance Queries (Priority 3):** Detect queries asking for return calculations or performance comparisons. Bypass generation and return a direct link to the official factsheet.

## Phase 4: Retrieval & Generation (RAG Core)
The core logic for searching the database and generating the response. This phase wires together the context-enriched ChromaDB store (Phase 2.3), the guardrail gate (Phase 3), and a Groq-hosted LLM into a single query-to-answer pipeline.
* **Script:** `src/rag_engine.py`

### Phase 4.1: Retriever Setup
* **Focus:** Initialize a retriever that mirrors the exact embedding configuration used during ingestion so that query vectors are comparable to stored document vectors.
* **Tasks:**
  - Load the persisted ChromaDB instance from `./chroma_db` (collection: `langchain`).
  - Initialize `HuggingFaceBgeEmbeddings` with the **same** model and parameters used in `src/embed_and_store.py`:
    - Model: `BAAI/bge-small-en-v1.5` (384 dimensions, normalized cosine similarity).
    - `query_instruction`: `"Represent this sentence for searching relevant passages: "` — this prefix is critical for BGE models to produce accurate query embeddings.
    - `encode_kwargs`: `{'normalize_embeddings': True}` for cosine similarity.
  - Expose a retriever via `vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": 5})` (Top-5 chunks).

### Phase 4.2: Query Classification, Prompt Engineering & Guardrail Integration
* **Focus:** Enforce a two-layer classification gate before RAG generation, then construct a strict, facts-only prompt using the context-enriched chunk format.
* **Tasks:**
  - **Layer 1 — Regex Guardrail (fast, free):** Before any LLM call, run `guardrails.run_guardrails(query)` from Phase 3. This catches obvious PII (PAN, Aadhaar, email, phone), advisory intent ("Should I buy?"), and performance calculation requests instantly. If `is_blocked` is `True`, return the `refusal_message` directly and skip the entire RAG pipeline.
  - **Layer 2 — LLM-based Intent Classifier (safety net):** For queries that pass the regex layer, make a lightweight call using Groq's **`meta-llama/llama-prompt-guard-2-86m`** model — this is a purpose-built prompt safety classifier with generous rate limits (14.4K RPD, 500K TPD vs. the main model's 1K RPD, 100K TPD). Send a classification prompt: _"Does the following user query ask for investment advice, opinions, predictions, performance comparisons, or return calculations? Answer only YES or NO."_ (`max_tokens` ~10). If the response is `YES`, return a polite refusal that reinforces the facts-only limitation and includes an educational link (AMFI/SEBI). This catches cleverly phrased advisory queries that dodge regex patterns (e.g., _"Tell me which of these five funds will make me the most money"_).
  - **Refusal Response Formatting:** All refused responses (from either layer) must: (1) be polite and clearly worded, (2) reinforce the facts-only limitation, and (3) include a relevant educational link (AMFI: `amfiindia.com` or SEBI: `investor.sebi.gov.in`), as required by the problem statement §3.
  - **Context Assembly:** For queries that pass both layers, retrieve Top-K chunks. Each chunk's `page_content` already contains enriched context (e.g., `Fund Name: Bandhan Small Cap Fund\nSection 2: Holdings (258)\n...`) — use this directly as context.
  - **System Prompt Construction:** Build a system prompt enforcing these hard constraints:
    1. Answer in **3 sentences maximum** — no elaboration beyond the retrieved context.
    2. Use **only** the provided context chunks. If the answer is not present in the context, respond with: _"I don't have this information in my current data sources."_
    3. Include **exactly one source citation** as a clickable URL (extracted from the chunk's `source_url` metadata).
    4. Never provide investment advice, opinions, predictions, or recommendations.
  - **User Prompt:** Combine the system instructions, the formatted context blocks (numbered, with fund name labels), and the user's original query.

### Phase 4.3: LLM Generation via Groq (Rate-Limit Aware)
* **Focus:** Call the Groq API for fast inference while respecting the free-tier rate limits.
* **Groq Free-Tier Limits for `llama-3.3-70b-versatile`:**
  | Constraint | Limit |
  |---|---|
  | Requests per minute | 30 |
  | Requests per day | 1,000 |
  | Tokens per minute | 12,000 |
  | Tokens per day | 100,000 |
* **Token Budget per Query:** System prompt (~200 tokens) + 5 context chunks (~1,500 tokens each × 5 = ~7,500 tokens) + user query (~50 tokens) + response (`max_tokens` = 300) ≈ **~8,050 tokens/query**. At 100K TPD, this allows roughly **~12 full queries/day** with the 70b model. To stretch the budget: limit to Top-3 chunks instead of Top-5 when daily usage exceeds 70% of the token quota.
* **Tasks:**
  - Load `GROQ_API_KEY` from `.env` using `python-dotenv`.
  - Initialize `ChatGroq` from `langchain_groq` with:
    - `model_name`: `"llama-3.3-70b-versatile"` (primary — high-quality reasoning).
    - `temperature`: `0` (deterministic, factual responses — no creative sampling).
    - `max_tokens`: `300` (hard cap to enforce brevity).
  - **Rate Limit Handling:**
    - Wrap LLM calls with retry logic using exponential backoff (e.g., `tenacity` or manual retry with 2s/4s/8s delays) to handle HTTP 429 (rate limit exceeded) responses gracefully.
    - Track daily request/token counters locally (in-memory or a simple JSON file) to proactively warn the user when approaching daily limits.
  - **Fallback Model:** If the primary model's daily quota is exhausted, automatically fall back to `llama-3.1-8b-instant` which has 14.4K RPD and 500K TPD — lower quality but 14× more daily requests and 5× more daily tokens.
  - Invoke the chain: `system_prompt + context + user_query → LLM → raw_response`.

### Phase 4.4: Post-processing & Citation Assembly
* **Focus:** Format the raw LLM output to meet the exact output spec from the problem statement.
* **Tasks:**
  - **Citation Extraction:** Extract the `source_url` from the top-ranked retrieved chunk's metadata and append it as a clickable source link.
  - **Footer:** Append the mandatory footer: `Last updated from sources: <date>` (use the current date or a stored ingestion timestamp).
  - **Fallback Handling:** If the retriever returns 0 results (e.g., completely off-topic query that passed guardrails), return a graceful: _"I couldn't find relevant information in my data sources for this query."_
  - **Response Object:** Return a structured dict containing `{"answer": str, "source_url": str, "is_refused": bool}` to allow the UI layer (Phase 5) to render responses consistently.

## Phase 5: User Interface (Custom HTML/JS + Flask API)
Creating the premium, minimalist frontend.
* **Backend (`app.py`):** Flask API serving the frontend on `/` and handling chat requests on `/api/chat`.
* **Frontend (`templates/index.html`):** Custom HTML, Tailwind CSS, and Vanilla JavaScript.
* **Features:** 
  - Welcome message and clickable example queries.
  - Multi-chat UI layout (sidebar).
  - Floating chat input with auto-expanding textarea.
  - Asynchronous `fetch` calls to the Flask backend.
  - Markdown rendering (using `marked.js`) for complex AI responses (tables, lists).
  - Dynamic pill badges for source citations and timestamps.

## Phase 6: Automated Data Scheduler (GitHub Actions)
Deploying a background RAG ingestion trigger compatible with Render's ephemeral filesystem.
* **Component:** `.github/workflows/daily_ingestion.yml`
* **Features:**
  - Automated cron job to run the pipeline at 10:30 IST (05:00 UTC) daily.
  - Manual `workflow_dispatch` trigger for on-demand database updates.
  - Sequentially runs `ingestion.py`, `chunking.py`, and `embed_and_store.py`.
  - Commits the updated `./chroma_db`, `./raw`, and `./processed` directories back to the `main` branch.
  - Integrates perfectly with Render, triggering a fast redeployment containing the fresh database.

## Phase 7: Documentation & Verification
Finalizing the project deliverables.
* **Documentation:** `README.md` containing setup instructions, architecture overview, selected schemes, and known limitations.
* **Verification:** 
  - Automated/manual tests for guardrails (ensuring advisory/performance queries are refused).
  - Validation of output formatting (3 sentences max, citations, footer).
  - Security check to ensure no PII (PAN, Aadhaar, account numbers, OTPs, emails, phone numbers) is processed or logged.
