"""
Phase 4: Retrieval & Generation (RAG Core)
==========================================
Main RAG pipeline that wires together:
- Phase 2.3's context-enriched ChromaDB store
- Phase 3's regex guardrails
- A two-layer query classification gate (regex + LLM)
- Groq LLM generation with rate-limit awareness
- Post-processing with citation and footer assembly

Script: src/rag_engine.py
"""

import os
import sys
import json
import time
from datetime import datetime
from typing import Optional, Tuple

from dotenv import load_dotenv
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

# Import guardrails from the same src/ directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from guardrails import run_guardrails

# Load environment variables from project root
load_dotenv()


# ============================================================
# Constants & Configuration
# ============================================================
CHROMA_PERSIST_DIR = "./chroma_db"

# Model configuration
PRIMARY_MODEL = "llama-3.3-70b-versatile"
FALLBACK_MODEL = "llama-3.1-8b-instant"
# Layer 2 classifier: use 8b-instant as primary (proper chat model for intent classification)
# with prompt-guard as fallback (designed for injection detection, less reliable for advisory)
CLASSIFIER_MODEL = "llama-3.1-8b-instant"
CLASSIFIER_FALLBACK_MODEL = "meta-llama/llama-prompt-guard-2-86m"

# Groq free-tier limits for the primary model
DAILY_TOKEN_LIMIT = 100_000
DAILY_REQUEST_LIMIT = 1_000
TOKEN_BUDGET_WARNING_THRESHOLD = 0.70  # Reduce to Top-3 chunks above 70%

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]  # Exponential backoff in seconds

# Usage tracking
USAGE_FILE = "./usage_tracker.json"


# ============================================================
# Phase 4.1: Retriever Setup
# ============================================================

def init_embeddings():
    """
    Initialize the FastEmbed API embedding model with the EXACT same configuration
    used during ingestion in src/embed_and_store.py.
    """
    return FastEmbedEmbeddings(
        model_name="BAAI/bge-small-en-v1.5"
    )


def init_vectorstore(embeddings):
    """Load the persisted ChromaDB instance from ./chroma_db (collection: 'langchain')."""
    return Chroma(
        persist_directory=CHROMA_PERSIST_DIR,
        embedding_function=embeddings
    )


def get_retriever(vectorstore, k: int = 5):
    """Expose a LangChain retriever for similarity search with Top-K chunks."""
    return vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={"k": k}
    )


# ============================================================
# Phase 4.2: Query Classification (Two-Layer Guardrail)
# ============================================================

CLASSIFICATION_PROMPT = (
    "You are a strict query classifier for a facts-only mutual fund FAQ system.\n"
    "Determine if the user query below asks for ANY of the following:\n"
    "- Investment advice or recommendations\n"
    "- Opinions on which fund is better or worse\n"
    "- Predictions about future fund performance\n"
    "- Performance comparisons between funds\n"
    "- Return calculations (SIP returns, CAGR, XIRR, corpus growth)\n\n"
    "If the query asks for ANY of the above, respond with exactly: YES\n"
    "If the query is purely factual (expense ratio, exit load, fund manager, holdings, "
    "minimum SIP, lock-in period, how to download statements, etc.), respond with exactly: NO\n\n"
    'User Query: "{query}"\n\n'
    "Answer (YES or NO):"
)

ADVISORY_REFUSAL_LLM = (
    "I'm a facts-only assistant and cannot provide investment advice, opinions, or recommendations. "
    "For guidance on investing, please consult a SEBI-registered investment advisor or visit:\n"
    "- AMFI: https://www.amfiindia.com/investor-corner/knowledge-center.html\n"
    "- SEBI Investor Education: https://investor.sebi.gov.in/"
)


def classify_query_with_llm(query: str, groq_api_key: str) -> bool:
    """
    Layer 2 — LLM-based Intent Classifier (safety net).

    Attempts to use the purpose-built prompt-guard model first.
    Falls back to llama-3.1-8b-instant if the primary classifier fails.

    Returns True if the query should be BLOCKED as advisory/non-factual.
    Returns False if the query should be ALLOWED through to RAG.
    """
    prompt_text = CLASSIFICATION_PROMPT.format(query=query)

    # Try the primary classifier model
    try:
        llm = ChatGroq(
            api_key=groq_api_key,
            model_name=CLASSIFIER_MODEL,
            temperature=0,
            max_tokens=10,
        )
        response = llm.invoke([HumanMessage(content=prompt_text)])
        answer = response.content.strip().upper()
        return "YES" in answer

    except Exception as e:
        print(f"  ⚠ Prompt guard model failed ({type(e).__name__}). Falling back to {CLASSIFIER_FALLBACK_MODEL}...")

    # Fallback classifier
    try:
        llm_fallback = ChatGroq(
            api_key=groq_api_key,
            model_name=CLASSIFIER_FALLBACK_MODEL,
            temperature=0,
            max_tokens=10,
        )
        response = llm_fallback.invoke([HumanMessage(content=prompt_text)])
        answer = response.content.strip().upper()
        return "YES" in answer

    except Exception as e2:
        # Both classifiers failed — fail open (let the query through).
        # The system prompt still instructs the LLM to refuse advisory queries.
        print(f"  ⚠ Classifier fallback also failed ({type(e2).__name__}). Allowing query to proceed to RAG.")
        return False


# ============================================================
# Phase 4.2: System Prompt Construction
# ============================================================

SYSTEM_PROMPT_TEMPLATE = (
    "You are a facts-only mutual fund FAQ assistant. You answer questions using "
    "ONLY the context provided below. Follow these rules strictly:\n\n"
    "1. Answer in 3 sentences MAXIMUM. Be concise and factual.\n"
    "2. Use ONLY the information present in the provided context. "
    "Do not use any external knowledge.\n"
    "3. If the answer is NOT present in the context, respond with exactly: "
    '"I don\'t have this information in my current data sources."\n'
    "4. NEVER provide investment advice, opinions, predictions, or recommendations.\n"
    "5. Do NOT say \"based on the context\" or reference the context directly. "
    "Just state the facts.\n\n"
    "CONTEXT:\n{context}"
)


def build_prompt(query: str, retrieved_docs: list) -> Tuple[SystemMessage, HumanMessage]:
    """
    Assemble the system and user messages for the LLM.

    Each context block is numbered and labelled with the fund name,
    since chunks already contain enriched content (fund_name + headers
    prepended during Phase 2.3).
    """
    context_blocks = []
    for i, doc in enumerate(retrieved_docs, 1):
        fund_name = doc.metadata.get("fund_name", "Unknown Fund")
        source_url = doc.metadata.get("source_url", "")
        context_blocks.append(
            f"[Chunk {i} — {fund_name}]\n"
            f"Source: {source_url}\n"
            f"{doc.page_content}"
        )

    context_text = "\n\n---\n\n".join(context_blocks)
    system_msg = SystemMessage(content=SYSTEM_PROMPT_TEMPLATE.format(context=context_text))
    user_msg = HumanMessage(content=query)

    return system_msg, user_msg


# ============================================================
# Phase 4.3: Rate-Limit Tracking
# ============================================================

def _load_usage() -> dict:
    """Load daily usage counters. Resets automatically on a new day."""
    today = datetime.now().strftime("%Y-%m-%d")

    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE, 'r') as f:
                usage = json.load(f)
            if usage.get("date") != today:
                usage = {"date": today, "requests": 0, "tokens": 0}
        except (json.JSONDecodeError, KeyError):
            usage = {"date": today, "requests": 0, "tokens": 0}
    else:
        usage = {"date": today, "requests": 0, "tokens": 0}

    return usage


def _save_usage(usage: dict):
    """Persist daily usage counters to disk."""
    with open(USAGE_FILE, 'w') as f:
        json.dump(usage, f)


def _update_usage(tokens_used: int) -> dict:
    """Increment counters after a successful LLM call and return updated usage."""
    usage = _load_usage()
    usage["requests"] += 1
    usage["tokens"] += tokens_used
    _save_usage(usage)
    return usage


def _check_quota() -> Tuple[bool, bool, Optional[str]]:
    """
    Check daily quota status.

    Returns:
        (is_ok, should_reduce_chunks, warning_message)
        - is_ok = False means primary model quota is exhausted → use fallback.
        - should_reduce_chunks = True means switch from Top-5 to Top-3 chunks.
    """
    usage = _load_usage()
    token_pct = usage["tokens"] / DAILY_TOKEN_LIMIT if DAILY_TOKEN_LIMIT else 0
    request_pct = usage["requests"] / DAILY_REQUEST_LIMIT if DAILY_REQUEST_LIMIT else 0

    if token_pct >= 0.95 or request_pct >= 0.95:
        return False, False, (
            f"⚠️ Daily Groq quota nearly exhausted "
            f"({usage['requests']}/{DAILY_REQUEST_LIMIT} requests, "
            f"{usage['tokens']}/{DAILY_TOKEN_LIMIT} tokens). "
            f"Switching to fallback model."
        )
    elif token_pct >= TOKEN_BUDGET_WARNING_THRESHOLD:
        return True, True, (
            f"⚠️ Daily token usage at {token_pct:.0%}. "
            f"Reducing context to Top-3 chunks to conserve quota."
        )

    return True, False, None


# ============================================================
# Phase 4.3: LLM Generation with Retry & Fallback
# ============================================================

def _estimate_tokens(messages: list, response_content: str = "") -> int:
    """Rough token estimate: ~4 characters per token."""
    input_chars = sum(len(m.content) for m in messages)
    output_chars = len(response_content)
    return (input_chars + output_chars) // 4


def call_llm_with_retry(
    messages: list,
    groq_api_key: str,
    model: str = None
) -> Tuple[str, int, str]:
    """
    Call the Groq LLM with exponential backoff retry logic.

    If the primary model is rate-limited after all retries,
    automatically falls back to the fallback model.

    Returns: (response_content, estimated_tokens_used, model_used)
    """
    if model is None:
        model = PRIMARY_MODEL

    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            llm = ChatGroq(
                api_key=groq_api_key,
                model_name=model,
                temperature=0,
                max_tokens=300,
            )
            response = llm.invoke(messages)
            tokens_used = _estimate_tokens(messages, response.content)

            return response.content, tokens_used, model

        except Exception as e:
            last_error = e
            error_str = str(e).lower()

            if "429" in str(e) or "rate_limit" in error_str or "rate limit" in error_str:
                delay = RETRY_DELAYS[attempt] if attempt < len(RETRY_DELAYS) else RETRY_DELAYS[-1]
                if attempt < MAX_RETRIES - 1:
                    print(f"  ⏳ Rate limited (attempt {attempt + 1}/{MAX_RETRIES}). Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    # All retries exhausted on this model — try fallback
                    if model == PRIMARY_MODEL:
                        print(f"  🔄 Primary model rate limited after {MAX_RETRIES} retries. Switching to fallback: {FALLBACK_MODEL}")
                        return call_llm_with_retry(messages, groq_api_key, model=FALLBACK_MODEL)
                    else:
                        raise RuntimeError(
                            f"Both primary ({PRIMARY_MODEL}) and fallback ({FALLBACK_MODEL}) models "
                            f"are rate limited. Please try again later."
                        ) from last_error
            else:
                # Non-rate-limit error — raise immediately
                raise

    raise last_error


# ============================================================
# Phase 4.4: Post-processing & Citation Assembly
# ============================================================

def format_response(
    raw_answer: str,
    retrieved_docs: list,
    is_refused: bool = False,
    refusal_message: Optional[str] = None,
    model_used: Optional[str] = None,
    quota_warning: Optional[str] = None,
) -> dict:
    """
    Format the final response for the UI layer (Phase 5).

    Returns a structured dict:
    {
        "answer": str,        # The full formatted answer text
        "source_url": str,    # Citation URL from the top-ranked chunk
        "is_refused": bool,   # True if the query was blocked by guardrails
        "footer": str,        # The "Last updated from sources" footer
        "model_used": str,    # Which Groq model generated this response
        "quota_warning": str, # Rate limit warning, if any
    }
    """
    today = datetime.now().strftime("%Y-%m-%d")

    if is_refused:
        return {
            "answer": refusal_message,
            "source_url": None,
            "is_refused": True,
            "footer": None,
            "model_used": None,
            "quota_warning": quota_warning,
        }

    # Extract source_url from the top-ranked chunk's metadata
    source_url = None
    if retrieved_docs:
        source_url = retrieved_docs[0].metadata.get("source_url", None)

    # Build the formatted answer
    formatted_answer = raw_answer.strip()
    
    # Check if the LLM rejected the chunks (couldn't find the answer)
    # Our system prompt forces it to say exactly this phrase:
    if "I don't have this information" in formatted_answer:
        # Do not append irrelevant source URLs if the data wasn't found
        source_url = None
        footer = None
    else:
        # Append citation link
        if source_url:
            formatted_answer += f"\n\nSource: {source_url}"

        # Append mandatory footer
        footer = f"Last updated from sources: {today}"
        formatted_answer += f"\n\n_{footer}_"

    return {
        "answer": formatted_answer,
        "source_url": source_url,
        "is_refused": False,
        "footer": footer,
        "model_used": model_used,
        "quota_warning": quota_warning,
    }


# ============================================================
# Main RAG Pipeline — Entry Point
# ============================================================

def query_rag(user_query: str) -> dict:
    """
    Main entry point for the RAG engine.

    Takes a user query string and returns a structured response dict.
    Runs the full Phase 4 pipeline:
        Layer 1 Guardrail → Layer 2 Classifier → Retrieval → Generation → Formatting
    """
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        return format_response(
            "", [], is_refused=True,
            refusal_message="⚠️ GROQ_API_KEY not found. Please add it to your environment variables."
        )

    print(f"\n  Processing query: \"{user_query}\"")

    # ── Layer 1: Regex Guardrail (Phase 3 — fast, free) ──────
    is_blocked, refusal_msg = run_guardrails(user_query)
    if is_blocked:
        print(f"  🚫 [Layer 1 — Regex] Query BLOCKED.")
        return format_response("", [], is_refused=True, refusal_message=refusal_msg)
    print(f"  ✅ [Layer 1 — Regex] Passed.")

    # ── Layer 2: LLM-based Intent Classifier (safety net) ────
    is_advisory = classify_query_with_llm(user_query, groq_api_key)
    if is_advisory:
        print(f"  🚫 [Layer 2 — LLM Classifier] Query BLOCKED as advisory/non-factual.")
        return format_response("", [], is_refused=True, refusal_message=ADVISORY_REFUSAL_LLM)
    print(f"  ✅ [Layer 2 — LLM Classifier] Passed.")

    # ── Phase 4.1: Initialize retriever ──────────────────────
    print(f"  🔍 Initializing retriever...")
    embeddings = init_embeddings()
    vectorstore = init_vectorstore(embeddings)

    # Check quota and decide chunk count
    quota_ok, reduce_chunks, warning_msg = _check_quota()
    k = 3 if reduce_chunks else 5

    if warning_msg:
        print(f"  {warning_msg}")

    # Determine which model to use
    model = PRIMARY_MODEL
    if not quota_ok:
        model = FALLBACK_MODEL
        print(f"  🔄 Quota exhausted — using fallback model: {FALLBACK_MODEL}")

    # ── Retrieval ────────────────────────────────────────────
    retriever = get_retriever(vectorstore, k=k)
    retrieved_docs = retriever.invoke(user_query)
    print(f"  📄 Retrieved {len(retrieved_docs)} chunks (k={k}).")

    # Fallback: no results found
    if not retrieved_docs:
        return format_response(
            "I couldn't find relevant information in my data sources for this query.",
            [], model_used=model, quota_warning=warning_msg
        )

    # ── Phase 4.2: Prompt Construction ───────────────────────
    system_msg, user_msg = build_prompt(user_query, retrieved_docs)

    # ── Phase 4.3: LLM Generation ───────────────────────────
    print(f"  🤖 Generating response with {model}...")
    raw_answer, tokens_used, model_used = call_llm_with_retry(
        [system_msg, user_msg], groq_api_key, model=model
    )

    # Update usage tracking
    usage = _update_usage(tokens_used)
    print(
        f"  📊 Tokens: ~{tokens_used} | Daily usage: "
        f"{usage['requests']}/{DAILY_REQUEST_LIMIT} requests, "
        f"{usage['tokens']}/{DAILY_TOKEN_LIMIT} tokens"
    )

    # ── Phase 4.4: Post-processing ──────────────────────────
    return format_response(
        raw_answer, retrieved_docs,
        model_used=model_used, quota_warning=warning_msg
    )


# ============================================================
# Validation / Self-test
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("  PHASE 4 VALIDATION — RAG Engine (src/rag_engine.py)")
    print("=" * 70)

    test_queries = [
        # Should be blocked by Layer 1 (regex guardrails)
        ("Should I invest in HDFC Mid-Cap?", True, "Layer 1 Advisory"),
        ("My PAN is ABCDE1234F", True, "Layer 1 PII"),
        ("Calculate my SIP returns", True, "Layer 1 Performance"),

        # Should be blocked by Layer 2 (LLM classifier)
        ("Tell me which of these five funds will make me the most money", True, "Layer 2 Advisory"),

        # Should pass through and get a RAG answer
        ("What is the expense ratio of Bandhan Small Cap Fund?", False, "Factual"),
        ("Who is the fund manager of HDFC Flexi Cap Fund?", False, "Factual"),
    ]

    passed = 0
    failed = 0

    for query, expect_refused, category in test_queries:
        print(f"\n{'─' * 70}")
        print(f"  [{category}] \"{query}\"")
        print(f"  Expected: {'REFUSED' if expect_refused else 'ANSWERED'}")

        result = query_rag(query)
        actual_refused = result["is_refused"]
        status = "✅" if actual_refused == expect_refused else "❌"

        if actual_refused == expect_refused:
            passed += 1
        else:
            failed += 1

        print(f"  {status} Got: {'REFUSED' if actual_refused else 'ANSWERED'}")
        if result.get("model_used"):
            print(f"  Model: {result['model_used']}")
        print(f"  Response preview: {result['answer'][:250]}...")

    print(f"\n{'=' * 70}")
    print(f"  Results: {passed} passed, {failed} failed out of {len(test_queries)} tests")
    print(f"{'=' * 70}")
