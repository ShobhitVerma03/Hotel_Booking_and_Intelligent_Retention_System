import os
from pathlib import Path

# The project root is the current directory
project_root = Path(".")

# 1. Define the Folder Structure
folders = [
    "config",
    "data/raw",
    "data/processed",
    "data/policy",
    "models",
    "vectorstore/chroma_db",
    "notebooks",
    "tests",
    "src",
    "src/rag",
    "src/ml",
    "src/tools",
    "src/agents",
    "src/llmops",
    "src/utils",
]

# 2. Define the Files to Create (path, content)
# We use empty strings or comments as placeholder content
files = [
    # Config
    ("config/settings.py", "# Project configuration settings"),
    (".env.example", "GROQ_API_KEY=\nTAVILY_API_KEY=\nLANGCHAIN_API_KEY="),
    (".gitignore", ".env\n.venv/\n__pycache__/\n*.db\n*.joblib\nvectorstore/"),
    ("README.md", "# Intelligent Hotel Retention Agent"),

    # Data placeholders (so you know where to put files later)
    ("data/raw/.gitkeep", ""), 
    ("data/policy/.gitkeep", ""), 

    # Src - Init files to make them Python packages
    ("src/__init__.py", ""),
    ("src/rag/__init__.py", ""),
    ("src/ml/__init__.py", ""),
    ("src/tools/__init__.py", ""),
    ("src/agents/__init__.py", ""),
    ("src/llmops/__init__.py", ""),
    ("src/utils/__init__.py", ""),

    # RAG Layer
    ("src/rag/loader.py", "# Document loading logic"),
    ("src/rag/chunker.py", "# Text splitting logic"),
    ("src/rag/embedder.py", "# Embedding generation"),
    ("src/rag/store.py", "# Vector database interaction"),
    ("src/rag/retriever.py", "# Retrieval logic"),

    # ML Layer
    ("src/ml/loader.py", "# Data loading for ML"),
    ("src/ml/preprocessor.py", "# Feature engineering"),
    ("src/ml/predictor.py", "# Inference logic"),

    # Tools
    ("src/tools/fetch_bookings.py", "# Tool: Get booking details"),
    ("src/tools/get_risk.py", "# Tool: Get churn risk"),
    ("src/tools/policy_search.py", "# Tool: RAG policy search"),
    ("src/tools/send_email.py", "# Tool: Draft/send email"),
    ("src/tools/human_approval.py", "# Tool: Human-in-the-loop"),

    # Agents
    ("src/agents/prompts.py", "# System prompts"),
    ("src/agents/state.py", "# Graph state definition"),
    ("src/agents/graph.py", "# LangGraph construction"),
    ("src/agents/runner.py", "# Graph execution entry point"),

    # LLMOps
    ("src/agents/tracing.py", "# LangSmith tracing setup"),
    ("src/agents/evaluation.py", "# Eval metrics"),

    # Utils
    ("src/utils/logger.py", "# Logging config"),
    ("src/utils/dates.py", "# Date handling helpers"),

    # App & Main
    ("app.py", "# Streamlit UI"),
    ("main.py", "# CLI / Backend entry point"),

    # Notebooks
    ("notebooks/01_data_eda.ipynb", '{"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}'),
    ("notebooks/02_model_training.ipynb", '{"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}'),
    ("notebooks/03_rag_indexing.ipynb", '{"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}'),
    ("notebooks/04_agent_testing.ipynb", '{"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}'),

    # Tests
    ("tests/test_rag.py", ""),
    ("tests/test_ml.py", ""),
    ("tests/test_tools.py", ""),
]

def create_structure():
    print("🚀 Starting project setup...")

    # Create Folders
    for folder in folders:
        path = project_root / folder
        try:
            path.mkdir(parents=True, exist_ok=True)
            print(f"✅ Created folder: {folder}")
        except Exception as e:
            print(f"❌ Error creating {folder}: {e}")

    # Create Files
    for file_path, content in files:
        path = project_root / file_path
        try:
            if not path.exists():
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"📄 Created file: {file_path}")
            else:
                print(f"⏩ Skipped (exists): {file_path}")
        except Exception as e:
            print(f"❌ Error creating {file_path}: {e}")

    print("\n🎉 Project structure created successfully!")

if __name__ == "__main__":
    create_structure()