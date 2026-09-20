import os
import bs4
from langchain_community.document_loaders import WebBaseLoader, PyPDFLoader

# Core 5 Mutual Funds
FUNDS = [
    {"name": "Bandhan Small Cap Fund", "url": "https://groww.in/mutual-funds/bandhan-small-cap-fund-direct-growth"},
    {"name": "Parag Parikh Long Term Value Fund", "url": "https://groww.in/mutual-funds/parag-parikh-long-term-value-fund-direct-growth"},
    {"name": "HDFC Mid-Cap Opportunities Fund", "url": "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"},
    {"name": "HDFC Flexi Cap Fund", "url": "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth"},
    {"name": "Nippon India Large Cap Fund", "url": "https://groww.in/mutual-funds/nippon-india-large-cap-fund-direct-growth"}
]

def load_and_parse_funds():
    """Phase 2.1: Data Scraping & Parsing"""
    print("Starting Phase 2.1: Scraping and Parsing Data...")
    all_documents = []
    
    for fund in FUNDS:
        print(f"Fetching data for: {fund['name']}...")
        
        # Check if the URL is a PDF or standard HTML
        if fund["url"].lower().endswith(".pdf"):
            loader = PyPDFLoader(fund["url"])
            docs = loader.load()
        else:
            import requests
            from langchain_core.documents import Document
            
            # Fetch HTML manually to enforce strict structural normalization
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(fund["url"], headers=headers)
            soup = bs4.BeautifulSoup(response.content, "html.parser")
            
            # Strip out irrelevant navigation, footers, and scripts (Phase 2.1 requirement)
            for element in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                element.extract()
                
            # Convert the clean HTML directly to Markdown to preserve tables/structure
            import markdownify
            markdown_text = markdownify.markdownify(str(soup), heading_style="ATX")
            
            # Clean up excessive multiple newlines
            import re
            cleaned_text = re.sub(r'\n{3,}', '\n\n', markdown_text).strip()
            
            docs = [Document(page_content=cleaned_text)]
        
        for doc in docs:
            # Rigorously capture metadata as specified in the plan
            doc.metadata = {
                "source_url": fund["url"],
                "fund_name": fund["name"],
                "document_type": "Groww Overview"
            }
            all_documents.append(doc)
            
    # Save raw data to JSON for transparency
    import json
    os.makedirs("raw", exist_ok=True)
    
    json_data = []
    for d in all_documents:
        json_data.append({
            "metadata": d.metadata,
            "content": d.page_content
        })
        
    with open("raw/scraped_markdown.json", "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=4, ensure_ascii=False)
    print("Saved raw scraped markdown to raw/scraped_markdown.json")
    
    return all_documents

if __name__ == "__main__":
    # Validate Phase 2.1 by printing what has been consumed
    docs = load_and_parse_funds()
    
    print("\n--- PHASE 2.1 VALIDATION ---")
    print(f"Total pages successfully parsed: {len(docs)}")
    
    if len(docs) > 0:
        sample = docs[0]
        print(f"\nMetadata for the first document:\n{sample.metadata}")
        print(f"\nContent Snippet (first 500 characters):\n{sample.page_content[:500]}...\n")
        print("Note: The text above is the raw, cleaned text that will be fed to the chunker in Phase 2.2.")
