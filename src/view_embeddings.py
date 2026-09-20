"""
Quick utility to inspect embeddings stored in ChromaDB.
Shows chunk metadata, content snippets, and embedding vectors.
"""
import chromadb
import json

def view_embeddings():
    # Connect to the persisted ChromaDB
    client = chromadb.PersistentClient(path="./chroma_db")
    
    # Get the collection (LangChain uses 'langchain' as default collection name)
    collection = client.get_collection("langchain")
    
    # Fetch all data including embeddings
    results = collection.get(include=["embeddings", "documents", "metadatas"])
    
    total = len(results["ids"])
    print(f"Total chunks in ChromaDB: {total}")
    print(f"Embedding dimensions: {len(results['embeddings'][0])}")
    print("=" * 80)
    
    # Show first 5 chunks with their embeddings
    for i in range(min(5, total)):
        print(f"\n--- Chunk {i+1} / {total} ---")
        print(f"ID:       {results['ids'][i]}")
        print(f"Metadata: {json.dumps(results['metadatas'][i], indent=2)}")
        print(f"Content:  {results['documents'][i][:200]}...")
        
        # Show first 10 dimensions of the embedding vector
        embedding = results["embeddings"][i]
        print(f"Embedding (first 10 of {len(embedding)} dims):")
        print(f"  {embedding[:10]}")
        print(f"  Min: {min(embedding):.6f}  Max: {max(embedding):.6f}  Avg: {sum(embedding)/len(embedding):.6f}")

    # Summary stats across all embeddings
    print("\n" + "=" * 80)
    print("SUMMARY STATS ACROSS ALL EMBEDDINGS")
    print("=" * 80)
    all_dims = [len(e) for e in results["embeddings"]]
    print(f"Chunks: {total}")
    print(f"Dimensions per vector: {all_dims[0]}")
    
    # Show fund distribution
    funds = {}
    for meta in results["metadatas"]:
        fund = meta.get("fund_name", "Unknown")
        funds[fund] = funds.get(fund, 0) + 1
    print(f"\nChunks per fund:")
    for fund, count in sorted(funds.items(), key=lambda x: -x[1]):
        print(f"  {fund}: {count}")


if __name__ == "__main__":
    view_embeddings()
