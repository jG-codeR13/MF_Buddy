import re
from typing import Optional, Tuple


# ============================================================
# PII Detection Patterns
# ============================================================
PII_PATTERNS = {
    "PAN": re.compile(r'[A-Z]{5}[0-9]{4}[A-Z]'),
    "Aadhaar": re.compile(r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b'),
    "Email": re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'),
    "Phone": re.compile(r'(?:\+91[\s\-]?)?(?:0)?[6-9]\d{9}\b'),
}

# ============================================================
# Advisory / Opinion Detection
# ============================================================
ADVISORY_KEYWORDS = [
    r'\bshould\s+i\s+(invest|buy|sell|redeem|switch|put|start)',
    r'\bwhich\s+(fund|scheme|one)\s+is\s+(better|best|good|safer)',
    r'\brecommend\b',
    r'\bsuggest\b',
    r'\badvice\b',
    r'\badvise\b',
    r'\bbest\s+fund\b',
    r'\bbest\s+scheme\b',
    r'\bworth\s+(investing|buying)\b',
    r'\bgood\s+time\s+to\s+(buy|invest|redeem)\b',
    r'\bhypothetically\b',
    r'\bif\s+i\s+wanted\s+to\s+retire\b',
    r'\bsafe\s+to\s+invest\b',
    r'\bwill\s+(this|the)\s+fund\s+(go\s+up|grow|perform)\b',
]
ADVISORY_REGEX = re.compile('|'.join(ADVISORY_KEYWORDS), re.IGNORECASE)

# ============================================================
# Performance / Return Calculation Detection
# ============================================================
PERFORMANCE_KEYWORDS = [
    r'\bif\s+i\s+invested\b',
    r'\bwhat\s+(would|will)\s+(my|the)\s+(corpus|returns?|value|amount)\b',
    r'\bcalculat(e|ion)\s+(my\s+)?(returns?|sip|corpus|cagr|xirr)\b',
    r'\bhow\s+much\s+(will|would|did)\s+(i|my)\b.*\b(grow|become|get)\b',
    r'\b(compare|comparison)\s+(of\s+)?(returns?|performance)\b',
    r'\bwhich\s+(fund|scheme)\s+(gave|gives|has)\s+(better|higher|more)\s+returns?\b',
    r'\breturn\s+calculation\b',
    r'\bperformance\s+comparison\b',
    r'\bcagr\b',
    r'\bxirr\b',
]
PERFORMANCE_REGEX = re.compile('|'.join(PERFORMANCE_KEYWORDS), re.IGNORECASE)

# ============================================================
# Refusal Messages
# ============================================================
PII_REFUSAL = (
    "I noticed your query may contain sensitive personal information (such as PAN, Aadhaar, "
    "email, or phone number). For your privacy and security, I cannot process queries containing "
    "personal data. Please rephrase your question without including any personal identifiers."
)

ADVISORY_REFUSAL = (
    "I'm a facts-only assistant and cannot provide investment advice, opinions, or recommendations. "
    "For guidance on investing, please consult a SEBI-registered investment advisor or visit:\n"
    "- AMFI: https://www.amfiindia.com/investor-corner/knowledge-center.html\n"
    "- SEBI Investor Education: https://investor.sebi.gov.in/"
)

PERFORMANCE_REFUSAL = (
    "I cannot perform return calculations or performance comparisons. "
    "For detailed performance data, please visit the official factsheet:\n"
    "- Bandhan Small Cap: https://www.bandhanmutual.com\n"
    "- Parag Parikh Flexi Cap: https://amc.ppfas.com\n"
    "- HDFC Mid-Cap Opportunities: https://www.hdfcfund.com\n"
    "- HDFC Flexi Cap: https://www.hdfcfund.com\n"
    "- Nippon India Large Cap: https://mf.nipponindiaim.com"
)


def check_pii(query: str) -> Tuple[bool, Optional[str]]:
    """
    Check if the user query contains any PII patterns.
    Returns: (is_pii_detected, pii_type_or_none)
    Does NOT echo back the detected PII value.
    """
    for pii_type, pattern in PII_PATTERNS.items():
        if pattern.search(query):
            return True, pii_type
    return False, None


def check_advisory(query: str) -> bool:
    """Check if the query is asking for investment advice or opinions."""
    return bool(ADVISORY_REGEX.search(query))


def check_performance(query: str) -> bool:
    """Check if the query is asking for return calculations or performance comparisons."""
    return bool(PERFORMANCE_REGEX.search(query))


def run_guardrails(query: str) -> Tuple[bool, Optional[str]]:
    """
    Run all guardrail checks on a user query.

    Returns:
        (is_blocked, refusal_message)
        - If is_blocked is True, refusal_message contains the response to show the user.
        - If is_blocked is False, refusal_message is None and the query can proceed to RAG.
    """
    # Priority 1: PII detection (highest priority — security concern)
    is_pii, pii_type = check_pii(query)
    if is_pii:
        return True, PII_REFUSAL

    # Priority 2: Advisory/opinion detection
    if check_advisory(query):
        return True, ADVISORY_REFUSAL

    # Priority 3: Performance calculation detection
    if check_performance(query):
        return True, PERFORMANCE_REFUSAL

    # All clear — query can proceed to RAG pipeline
    return False, None


# ============================================================
# Validation / Self-test
# ============================================================
if __name__ == "__main__":
    test_cases = [
        # PII tests
        ("My PAN is ABCDE1234F, what is the ELSS limit?", True, "PII"),
        ("My Aadhaar is 1234 5678 9012", True, "PII"),
        ("Send details to user@example.com", True, "PII"),
        ("Call me at +91 9876543210", True, "PII"),

        # Advisory tests
        ("Should I invest in HDFC Mid-Cap?", True, "Advisory"),
        ("Which fund is better for long term?", True, "Advisory"),
        ("Recommend a good mutual fund", True, "Advisory"),
        ("Is it a good time to invest?", True, "Advisory"),

        # Performance tests
        ("If I invested 10000 in Bandhan 3 years ago, what is my corpus?", True, "Performance"),
        ("Compare performance of HDFC Flexi Cap and Nippon Large Cap", True, "Performance"),
        ("Calculate my SIP returns", True, "Performance"),

        # Allowed factual queries
        ("What is the expense ratio of Bandhan Small Cap Fund?", False, "Factual"),
        ("What is the exit load for HDFC Mid-Cap?", False, "Factual"),
        ("What is the minimum SIP amount for Parag Parikh?", False, "Factual"),
        ("What is the ELSS lock-in period?", False, "Factual"),
        ("How do I download my CAS statement?", False, "Factual"),
        ("Who is the fund manager of Nippon India Large Cap?", False, "Factual"),
    ]

    print("--- GUARDRAILS VALIDATION ---\n")
    passed = 0
    failed = 0

    for query, expected_blocked, category in test_cases:
        is_blocked, message = run_guardrails(query)
        status = "✅" if is_blocked == expected_blocked else "❌"
        if is_blocked == expected_blocked:
            passed += 1
        else:
            failed += 1
        result = "BLOCKED" if is_blocked else "ALLOWED"
        print(f"  {status} [{category:11s}] {result:7s} | \"{query}\"")
        if is_blocked != expected_blocked:
            print(f"     ⚠️  Expected {'BLOCKED' if expected_blocked else 'ALLOWED'}")

    print(f"\nResults: {passed} passed, {failed} failed out of {len(test_cases)} tests")
