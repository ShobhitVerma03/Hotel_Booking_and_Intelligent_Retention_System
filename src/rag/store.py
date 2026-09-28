import os
import shutil
from langchain_community.vectorstores import Chroma
from src.rag.loader import load_policy_docs
from src.rag.chunker import split_documents
from src.rag.embedder import get_embedding_model

# Paths
PDF_PATH = "data/policy/Company_Retention_Policy_2026.pdf"
DB_PATH = "vectorstore/chroma_db"

def build_vectorstore():
    """
    Orchestrates the indexing pipeline: Load -> Split -> Embed -> Store.
    """
    print("🏗️  Building Vector Store...")

    # 1. Clear old DB to avoid duplicates
    if os.path.exists(DB_PATH):
        shutil.rmtree(DB_PATH)

    # 2. Load
    docs = load_policy_docs(PDF_PATH)
    if not docs:
        print("❌ No documents found.")
        return

    # 3. Split
    splits = split_documents(docs)
    print(f"🧩 Split into {len(splits)} chunks.")

    # 4. Embed & Store
    embedding_fn = get_embedding_model()
    
    vectorstore = Chroma.from_documents(
        documents=splits,
        embedding=embedding_fn,
        persist_directory=DB_PATH
    )
    print(f"💾 Vectorstore saved successfully to {DB_PATH}")

if __name__ == "__main__":
    build_vectorstore()