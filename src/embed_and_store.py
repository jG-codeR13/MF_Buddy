import json
import os
import shutil
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from dotenv import load_dotenv

load_dotenv()

def embed_and_store():
    print("Starting Phase 2.3: Embedding & Vector Storage...")
    
    # 1. Load the chunked data
    try:
        with open('processed/chunked_data.json', 'r', encoding='utf-8') as f:
            chunk_data = json.load(f)
    except FileNotFoundError:
        print("Error: processed/chunked_data.json not found. Please run src/chunking.py first.")
        return

    documents = []
    
    # 2. Context Enrichment
    for item in chunk_data:
        metadata = item['metadata']
        original_content = item['content']
        
        # Build enriched content
        enriched_content = f"Fund Name: {metadata.get('fund_name', 'Unknown')}\n"
        
        # Inject header context if present
        if "Header 1" in metadata:
            enriched_content += f"Section 1: {metadata['Header 1']}\n"
        if "Header 2" in metadata:
            enriched_content += f"Section 2: {metadata['Header 2']}\n"
        if "Header 3" in metadata:
            enriched_content += f"Section 3: {metadata['Header 3']}\n"
        if "Header 4" in metadata:
            enriched_content += f"Section 4: {metadata['Header 4']}\n"
            
        enriched_content += f"\n{original_content}"
        
        # Create a new Document object
        doc = Document(page_content=enriched_content, metadata=metadata)
        documents.append(doc)
        
    print(f"Context enrichment complete for {len(documents)} chunks.")
    
    # 3. Initialize the FastEmbed API embedding model
    print("Initializing FastEmbed embedding model (BAAI/bge-small-en-v1.5)...")
        
    embeddings = FastEmbedEmbeddings(
        model_name="BAAI/bge-small-en-v1.5"
    )
    
    # 4. Create and persist the Chroma vector store
    persist_directory = './chroma_db'
    
    # Clear existing vector store if it exists to avoid duplication during re-runs
    if os.path.exists(persist_directory):
        print(f"Clearing existing vector store at {persist_directory}...")
        shutil.rmtree(persist_directory)
        
    print("Embedding chunks and storing in ChromaDB. This may take a few minutes...")
    vectorstore = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=persist_directory
    )
    
    # In newer versions of langchain-chroma, persistence is automatic.
    # We call persist() for backward compatibility if it exists.
    if hasattr(vectorstore, 'persist'):
        vectorstore.persist()
        
    print(f"Success! {len(documents)} chunks have been embedded and stored in {persist_directory}.")
    
    # Validation
    print("\n--- PHASE 2.3 VALIDATION ---")
    query = "What is the expense ratio?"
    docs = vectorstore.similarity_search(query, k=1)
    if docs:
        print(f"Sample Query: '{query}'")
        print("Top result metadata:", docs[0].metadata)
        print("Top result enriched content snippet:")
        print("-" * 40)
        print(docs[0].page_content[:300] + "...")
        print("-" * 40)
    
if __name__ == "__main__":
    embed_and_store()
