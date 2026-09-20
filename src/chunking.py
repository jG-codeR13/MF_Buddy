import json
import os
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_core.documents import Document

# Blocklist patterns for detecting Groww site-wide boilerplate/navigation noise.
# If a chunk's content contains 3+ of these patterns, it's classified as noise.
NOISE_PATTERNS = [
    "/options/",
    "/futures/",
    "/calculators/",
    "/commodities",
    "/stocks/mtf",
    "/trade-api",
    "Top Gainers",
    "Top Losers",
    "Groww Digest",
    "PRODUCTS",
    "Terms and Conditions",
    "Policies and Procedures",
    "Bug Bounty",
    "Investor Charter",
    "SMART ODR",
    "Download Forms",
    "NSE",
    "MCX",
    "Stocks:",
    "Mutual Funds:",
    "Groww. All rights reserved",
    "Groww Arbitrage Fund",
    "Groww Liquid Fund",
    "NFO",
    "Pricing",
    "Trust & Safety",
    "915 Terminal",
    "Algo Trading",
    "Demat Account",
    "Groww AMC",
]

# Patterns that indicate leading navigation/header menu chunks
NAV_HEADER_PATTERNS = [
    "Invest in stocks, ETFs, IPOs",
    "Trade in Crude Oil, Gold, Silver",
    "Invest in direct mutual funds at zero charges",
    "Track upcoming and ongoing IPOs",
    "Monitor top intraday performers",
]

# Minimum chunk size in characters — anything smaller is likely a fragment
MIN_CHUNK_SIZE = 50


def _is_noise_chunk(content: str) -> bool:
    """Detect if a chunk is Groww site-wide boilerplate/navigation noise."""
    hits = sum(1 for pattern in NOISE_PATTERNS if pattern in content)
    return hits >= 3


def _is_nav_header_chunk(content: str) -> bool:
    """Detect if a chunk is from the Groww page header/navigation menu."""
    return any(pattern in content for pattern in NAV_HEADER_PATTERNS)


def _is_fragment_chunk(content: str) -> bool:
    """Detect chunks that are too small to carry useful information."""
    return len(content.strip()) < MIN_CHUNK_SIZE


def filter_chunks(chunks: list[Document]) -> tuple[list[Document], dict]:
    """
    Post-processing filter that removes noise, navigation, and fragment chunks.
    Returns: (clean_chunks, stats_dict)
    """
    clean = []
    stats = {"noise": 0, "nav_header": 0, "fragment": 0, "kept": 0}

    for chunk in chunks:
        content = chunk.page_content

        if _is_nav_header_chunk(content):
            stats["nav_header"] += 1
        elif _is_noise_chunk(content):
            stats["noise"] += 1
        elif _is_fragment_chunk(content):
            stats["fragment"] += 1
        else:
            clean.append(chunk)
            stats["kept"] += 1

    return clean, stats


def load_all_source_data() -> list[dict]:
    """Load scraped markdown data and any curated knowledge documents."""
    all_data = []

    # Load scraped markdown
    scraped_path = 'raw/scraped_markdown.json'
    if os.path.exists(scraped_path):
        with open(scraped_path, 'r', encoding='utf-8') as f:
            all_data.extend(json.load(f))
        print(f"Loaded {len(all_data)} documents from {scraped_path}")

    # Load curated knowledge (ELSS, statement downloads, etc.)
    curated_path = 'raw/curated_knowledge.json'
    if os.path.exists(curated_path):
        with open(curated_path, 'r', encoding='utf-8') as f:
            curated = json.load(f)
            all_data.extend(curated)
        print(f"Loaded {len(curated)} curated knowledge documents from {curated_path}")

    return all_data


def chunk_markdown_data():
    print("Starting Phase 2.2: Two-Pass Markdown Chunking...")

    data = load_all_source_data()

    # ── Pass 0: Extract key fund metadata from headerless sections ──
    # On Groww pages, critical facts like NAV, expense ratio, AUM, and min SIP
    # appear as free-form text without any markdown header. The header-based
    # splitter misses them and they get absorbed into nav noise chunks.
    # This pass extracts them via regex and creates a dedicated chunk per fund.
    import re

    metadata_chunks = []
    METADATA_PATTERNS = {
        "NAV": re.compile(r'NAV:.*?\n\n(₹[\d,]+\.?\d*)'),
        "Min SIP": re.compile(r'Min\. for SIP\s*\n\n(₹[\d,]+)'),
        "Fund Size (AUM)": re.compile(r'Fund size \(AUM\)\s*\n\n(₹[\d,]+\.?\d*\s*Cr)'),
        "Expense Ratio": re.compile(r'Expense ratio\s*\n\n([\d.]+%)'),
        "Rating": re.compile(r'Rating\s*\n\n(\d)'),
    }

    for item in data:
        content = item['content']
        base_metadata = item['metadata']
        fund_name = base_metadata.get('fund_name', 'Unknown')

        # Only extract from Groww fund pages (not curated knowledge docs)
        if base_metadata.get('document_type') != 'Groww Overview':
            continue

        extracted = {}
        for field, pattern in METADATA_PATTERNS.items():
            match = pattern.search(content)
            if match:
                extracted[field] = match.group(1)

        if extracted:
            # Build a synthetic structured chunk with all key facts
            lines = [f"## {fund_name} — Key Facts"]
            for field, value in extracted.items():
                lines.append(f"- **{field}**: {value}")

            # Also extract exit load if present
            exit_load_match = re.search(
                r'(?:Exit [Ll]oad|Exit load)\s*\n\n(.*?)(?:\n\n|$)', content
            )
            if exit_load_match:
                lines.append(f"- **Exit Load**: {exit_load_match.group(1).strip()}")

            # Extract tax implication if present
            tax_match = re.search(
                r'Tax implication\s*\n\n(.*?)(?:\n\n|$)', content
            )
            if tax_match:
                lines.append(f"- **Tax Implication**: {tax_match.group(1).strip()}")

            synthetic_content = "\n".join(lines)

            doc = Document(
                page_content=synthetic_content,
                metadata={
                    **base_metadata,
                    "Header 2": f"{fund_name} — Key Facts",
                    "chunk_type": "extracted_metadata",
                }
            )
            metadata_chunks.append(doc)
            print(f"  ✅ Extracted key facts for {fund_name}: {list(extracted.keys())}")

    print(f"  Metadata extraction: {len(metadata_chunks)} synthetic chunks created.\n")

    # Pass 1: Split by Markdown Headers to retain section metadata
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
        ("####", "Header 4"),
    ]
    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on, strip_headers=False)

    # Pass 2: Recursive character splitter for large tables/sections
    recursive_splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=200)

    all_chunks = []

    for item in data:
        content = item['content']
        base_metadata = item['metadata']

        # Pass 1: Split into sections and get header metadata
        md_docs = markdown_splitter.split_text(content)

        # Inject our base metadata (url, fund_name, etc.) into every section document
        for doc in md_docs:
            doc.metadata.update(base_metadata)

        # Pass 2: Further chunk any sections that exceed our chunk_size limit
        final_chunks = recursive_splitter.split_documents(md_docs)

        all_chunks.extend(final_chunks)
        print(f"  Raw chunks for {base_metadata.get('fund_name', base_metadata.get('document_type', 'Unknown'))}: {len(final_chunks)}")

    # Pass 3: Post-processing filter — remove noise, navigation, and fragment chunks
    # But first, inject the synthetic metadata chunks (Pass 0) — these are clean
    # and must NOT be filtered out.
    print(f"\nTotal raw chunks before filtering: {len(all_chunks)}")
    all_chunks.extend(metadata_chunks)
    print(f"After adding {len(metadata_chunks)} metadata chunks: {len(all_chunks)}")
    clean_chunks, filter_stats = filter_chunks(all_chunks)
    print(f"Filtering results:")
    print(f"  Noise chunks removed:      {filter_stats['noise']}")
    print(f"  Nav header chunks removed:  {filter_stats['nav_header']}")
    print(f"  Fragment chunks removed:    {filter_stats['fragment']}")
    print(f"  Clean chunks kept:          {filter_stats['kept']}")

    os.makedirs('processed', exist_ok=True)

    # Save chunks for transparency/validation
    chunk_data = []
    for c in clean_chunks:
        chunk_data.append({
            "metadata": c.metadata,
            "content": c.page_content
        })

    with open('processed/chunked_data.json', 'w', encoding='utf-8') as f:
        json.dump(chunk_data, f, indent=4, ensure_ascii=False)

    print(f"\n--- PHASE 2.2 VALIDATION ---")
    print(f"Total clean chunks saved: {len(clean_chunks)}")
    if len(clean_chunks) > 0:
        # Pick a sample that likely contains injected header metadata
        for sample in clean_chunks:
            if "Header 2" in sample.metadata or "Header 3" in sample.metadata:
                print(f"\nSample Chunk Content:\n{'-'*40}\n{sample.page_content[:500]}...\n{'-'*40}")
                print(f"Metadata: {sample.metadata}")
                break


if __name__ == "__main__":
    chunk_markdown_data()
