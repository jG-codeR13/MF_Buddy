# Product & Technical Decisions Log

This document records the major architectural, product, and technical decisions made during the development of the **Mutual Fund AI Assistant**. It is designed to explain the *what*, *how*, and *why* behind our choices, highlighting product trade-offs and engineering constraints.

---

## 1. Retrieval-Augmented Generation (RAG) vs. Fine-Tuning
**Decision:** We chose a RAG architecture over fine-tuning a custom model or relying on a base LLM's training data.
**Evaluation:**
- *Base LLM:* Financial data (NAVs, AUMs, Expense Ratios) changes daily. Base LLMs hallucinate numbers and their training cutoff makes them instantly outdated.
- *Fine-Tuning:* Prohibitively expensive and slow to retrain a model every day just to update an Expense Ratio.
- *RAG:* Allows us to scrape live data daily and inject it directly into the prompt context.
**Why:** RAG provided the only cost-effective, scalable way to guarantee 100% factual accuracy (zero hallucinations) for highly volatile financial data, which is non-negotiable in the Fintech space.

---

## 2. Transitioning from Streamlit to Flask + Custom UI
**Decision:** We abandoned our initial Streamlit prototype in favor of a custom Python Flask API backend serving a Vanilla JS/Tailwind CSS frontend.
**Evaluation:**
- *Streamlit:* Incredible for 1-day MVP prototyping, but we quickly hit a wall. Streamlit's aggressive re-rendering loop caused database locking issues with ChromaDB. Furthermore, the UI felt clunky and we couldn't achieve a premium, consumer-facing "Fintech" aesthetic.
- *Flask + Custom UI:* Separated the backend logic (API) from the frontend.
**Why:** To resolve memory leak/locking bugs and to deliver a highly customized, minimalist "glassmorphism" UI. As a product manager, user experience (UX) is paramount; moving to a custom stack gave us total control over the user journey.

---

## 3. "Phase 0" Regex Extraction vs. Standard Chunking
**Decision:** We implemented a custom Regex extraction layer *before* passing documents to the standard Langchain Markdown text splitter.
**Evaluation:**
- When ingesting data from Groww, critical metrics (like Expense Ratio, NAV, and Exit Load) were embedded in headerless tabular formats. Standard text splitters chopped this data up randomly, meaning the LLM couldn't confidently retrieve it.
- We evaluated using complex table-parsing libraries, but they were too heavy and slow.
**Why:** We wrote a lightweight Regex script to hunt for specific financial keywords, extract the numbers, and forcefully inject them at the very top of our Markdown chunks as "Key Facts". This ensured the vector database *always* captured the most important data points, drastically improving RAG accuracy.

---

## 4. GitHub Actions over Native Cloud Cron for Daily Data Ingestion
**Decision:** We chose to use a daily GitHub Actions workflow to run our scraping/embedding pipeline instead of cloud-native Cron jobs (like Render Cron).
**Evaluation:**
- Render and Vercel are fantastic for hosting, but their free tiers utilize *ephemeral* (read-only or temporary) filesystems. If a cloud Cron Job ran our scraper, it would generate the new SQLite `chroma_db`, but the DB would be deleted when the instance spun down or restarted.
- Using a managed cloud vector database (like Pinecone) would solve this, but introduced unnecessary monthly costs for a V1 product.
**Why:** By shifting the daily cron job to **GitHub Actions**, the runner executes the pipeline, updates the local database, and *commits the database directly to the main branch*. This commit instantly triggers a Render redeployment with the fresh data baked in. It was a clever, zero-cost architectural hack to bypass ephemeral storage limitations and avoid paying for a managed database.

---

## 5. Local Storage vs. Backend Database for Multi-Chat
**Decision:** We implemented multi-chat history using browser `localStorage` rather than building a backend user database.
**Evaluation:**
- A backend database (like PostgreSQL) would allow users to access their chat history across devices, but it requires implementing user authentication (Auth0/JWT), managing database schemas, and paying for hosting.
**Why:** To accelerate time-to-market. By pushing state management to the client's browser, we delivered the highly requested "multi-chat" feature instantly without bloating the backend architecture or delaying the launch. It was a classic "MVP" product trade-off: prioritizing immediate user value over perfect cross-device scaling.
