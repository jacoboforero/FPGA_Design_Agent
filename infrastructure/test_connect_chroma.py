# test_connect.py
import chromadb
from chromadb.utils import embedding_functions

def main():
    client = chromadb.HttpClient(host="localhost", port=8000)
    print("Heartbeat (ms):", client.heartbeat())

    embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )

    # Use a fresh name to avoid conflicts with an existing "demo"
    coll = client.get_or_create_collection(
        name="demo_sbert",
        embedding_function=embedder
    )

    doc = "Chroma is a simple, local, file-based vector DB for rapid prototyping."
    coll.upsert(
        ids=["id-1"],
        documents=[doc],
        metadatas=[{"source": "readme"}],
    )

    res = coll.query(query_texts=["What is Chroma used for?"], n_results=1)
    print("Query result:", res)
    print("Connected and queried successfully.")

if __name__ == "__main__":
    main()
