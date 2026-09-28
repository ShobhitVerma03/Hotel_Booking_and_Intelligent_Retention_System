# Text splitting logic


# It cuts the PDF into bite-sized pieces for the AI.

from langchain_text_splitters import RecursiveCharacterTextSplitter

def split_documents(docs, chunk_size=500, chunk_overlap=50):
    """
    Splits a list of documents into smaller chunks.
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ".", " ", ""]
    )
    return text_splitter.split_documents(docs)