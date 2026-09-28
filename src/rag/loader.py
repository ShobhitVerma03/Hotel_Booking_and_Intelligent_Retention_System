# Document loading logic
from langchain_community.document_loaders import PyPDFLoader
import os

def load_policy_docs(pdf_path):
    """
    Loads the PDF policy document.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"❌ Policy file not found: {pdf_path}")
        
    loader = PyPDFLoader(pdf_path)
    docs = loader.load()
    print(f"✅ Loaded {len(docs)} pages from {pdf_path}")
    return docs