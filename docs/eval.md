# Evaluation Criteria (Phase-wise)

This document outlines the evaluation strategy for each phase of the **Facts-Only Mutual Fund FAQ Assistant**, as defined in `implementationPlan.md` and `edgecase.md`.

## Phase 1: Environment & Project Setup
**Goal:** Ensure a robust, reproducible development environment.
* **Evaluation Criteria:**
  * All dependencies (`langchain`, `streamlit`, `chromadb`, `groq`, `sentence-transformers`, etc.) install successfully via `requirements.txt` without version conflicts.
  * `.env` file structure exists and correctly loads `GROQ_API_KEY` into the application context.
  * Attempting to run the app without `GROQ_API_KEY` gracefully throws a UI-level validation error (Edge Case 11) rather than crashing the terminal process.

## Phase 2: Data Ingestion Pipeline
**Goal:** Successfully load, chunk, embed, and store context from official AMC URLs/PDFs.
* **Evaluation Criteria:**
  * **Extraction:** Scrapers/Loaders accurately extract text from the 5 selected funds' factsheets/SIDs. Empty PDFs (scanned images) are properly logged/skipped without halting the pipeline (Edge Case 9).
  * **Chunking:** Chunks are verified to fall within the expected character limits (1500 characters max, 200 character overlap) with appropriate overlap. Post-processing successfully removes Groww site navigation boilerplate and fragment chunks (< 50 characters).
  * **Embedding:** `sentence-transformers` (BGE model) correctly converts text to vectors.
  * **Metadata Integrity:** Every single chunk in ChromaDB possesses a valid `URL` and `Fund Name`. Chunks missing URLs are successfully dropped/flagged (Edge Case 12).

## Phase 3: Guardrails & Refusal Module
**Goal:** Block non-factual and prohibited queries before they reach the LLM.
* **Evaluation Criteria:**
  * **Advisory Queries:** Prompts like *"Should I invest in HDFC Mid-Cap?"* are instantly blocked, returning a standard polite refusal + AMFI/SEBI links.
  * **Calculation Queries:** Prompts like *"What was the 5-year return of Bandhan Small Cap?"* trigger a bypass that returns *only* the official factsheet link.
  * **Latency:** The guardrail checks (using regex or a lightweight classifier) add negligible latency (<500ms) to the query flow.

## Phase 4: Retrieval & Generation (RAG Core)
**Goal:** Accurately answer factual queries based *only* on retrieved context.
* **Evaluation Criteria:**
  * **Similarity Thresholds:** Queries unrelated to mutual funds or failing to hit the similarity threshold correctly trigger a "Context Unavailability" refusal *before* the Groq API call (Edge Case 10).
  * **Factuality (No Hallucinations):** The Groq LLM relies strictly on the retrieved context. If a fact is missing from context (e.g., *"Who is the fund manager?"* but it's not in the DB), it refuses to hallucinate (Edge Case 3).
  * **Formatting Constraints:** Every successful answer is exactly 3 sentences or fewer, strictly penalizing bullet points (Edge Case 7).
  * **Citation Requirements:** Every answer ends with exactly one clear source link and the footer `"Last updated from sources: <date>"`.

## Phase 5: User Interface (Minimal)
**Goal:** Provide a clean, compliant interface for users to interact with the assistant.
* **Evaluation Criteria:**
  * **Functionality:** Streamlit (`app.py`) loads successfully and renders the chat interface, welcome message, and 3 example queries.
  * **Compliance:** The disclaimer *"Facts-only. No investment advice."* is highly visible on the main screen.
  * **Input Validation:** The UI successfully restricts excessively long user inputs (e.g., >500 characters) and displays a frontend warning (Edge Case 13).
  * **Graceful Degradation:** Simulating a Groq API failure (e.g., turning off WiFi or using an invalid key) results in a friendly "high traffic/downtime" UI message rather than a stack trace (Edge Case 8).

## Phase 6: Documentation & Verification
**Goal:** Ensure the project is well-documented, secure, and ready for handoff.
* **Evaluation Criteria:**
  * `README.md` is complete, offering clear step-by-step setup instructions and a list of the 5 selected schemes.
  * **Security Audit:** A manual check confirms that PII inputs (e.g., testing with a fake PAN number) are NOT echoed by the LLM and do not appear in console logs (Edge Case 6).
