# Embedding generation

# : The "Translator". It initializes the embedding model once so we don't load it multiple times.

from langchain_huggingface import HuggingFaceEmbeddings

def get_embedding_model():
    """
    Returns the HuggingFace embedding model.
    Using 'all-MiniLM-L6-v2' for fast, free, local embeddings.
    """
    model_name = "sentence-transformers/all-MiniLM-L6-v2"
    embeddings = HuggingFaceEmbeddings(model_name=model_name)
    return embeddings