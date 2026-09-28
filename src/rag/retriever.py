# Retrieval logic

import os
from langchain_community.vectorstores import Chroma
from src.rag.embedder import get_embedding_model

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, "vectorstore", "chroma_db")

def get_retriever(k=2):
    """
    Loads the vectorstore and returns a retriever object.
    k: Number of chunks to retrieve.
    """
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"❌ Vectorstore not found at {DB_PATH}. Run src/rag/store.py first.")

    embedding_fn = get_embedding_model()
    
    vectorstore = Chroma(
        persist_directory=DB_PATH,
        embedding_function=embedding_fn
    )
    
    return vectorstore.as_retriever(search_kwargs={"k": k})