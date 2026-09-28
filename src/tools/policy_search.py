# Tool: RAG policy search

# Allows the agent to check if a customer is "High Risk".

from langchain_core.tools import tool
from src.rag.retriever import get_retriever

@tool
def search_retention_policy(query: str):
    """
    Searches the Company Retention Policy for rules, limits, and allowed offers.
    Use this BEFORE making any offer to a customer.
    """
    try:
        # Get the retriever (The Librarian)
        retriever = get_retriever(k=2)
        
        # Ask the question
        docs = retriever.invoke(query)
        
        # Combine the answers found
        return "\n\n".join([doc.page_content for doc in docs])
    except Exception as e:
        return f"Error searching policy: {e}"