# Intelligent Hotel Retention Agent 🏨

**Intelligent Hotel Retention Agent** is an AI-powered customer retention and churn prevention system tailored for hotel administrators. The project leverages a ReAct-style agentic workflow to interact with various internal tools to identify customer churn risk, look up hotel retention policies, interact with booking databases via natural language, and securely propose or email retention offers requiring human-in-the-loop approval.

---

## 🚀 How it Works (High-Level Architecture)

The system is designed with a detached Frontend and Backend architecture, utilizing LangGraph for intelligent tool orchestration.

1. **Frontend (Streamlit)**: Provides a "Dark & Aesthetic" Administrator Console where users (hotel managers) can query customer data (e.g., *"Check retention for Customer 101"*).
2. **Backend (Flask)**: Exposes a `/chat` API endpoint that receives the user's instructions and streams the response back. It also acts as the middleware handling execution pausing and resuming.
3. **Agent Loop (LangGraph)**: The core brain. It routes user requests to the appropriate tools, analyzes the results, and decides on the next sequence of actions. It has SQLite-based memory allowing conversational persistence.
4. **Tool Execution**: Depending on the user's intent, the agent invokes:
   - **Database queries** via Natural Language to SQL generation.
   - **Machine Learning Inference** to assess customer risk.
   - **RAG Data Retrieval** to find current company policies.
   - **Sensitive Actions** like requesting manager approval or sending emails, which explicitly pause the Agent Loop using LangGraph's interruption mechanics, awaiting manual approval from the admin interface.

### Deployment Architecture (CI/CD)

```text
                 ┌────────────────────┐
                 │     Developer      │
                 │   VS Code + Git    │
                 └─────────┬──────────┘
                           │
                           ▼
                 ┌────────────────────┐
                 │      GitHub        │
                 │   (Source Code)    │
                 └─────────┬──────────┘
                           │
                    Webhook (HTTP POST)
                           │
                           ▼
                 ┌────────────────────┐
                 │     ngrok Tunnel   │
                 │  https://abc.ngrok │
                 └─────────┬──────────┘
                           │
                           ▼
                 ┌────────────────────┐
                 │  Jenkins (Local)   │
                 │   localhost:8080   │
                 │   (CI/CD Brain)    │
                 └─────────┬──────────┘
                           │
        ┌──────────────────┼───────────────────┐
        │                  │                   │
        ▼                  ▼                   ▼
  Docker Build        Push Image          SSH Deploy
   (Create Image)        to ECR              to EC2
                         │                    │
                         ▼                    ▼
               ┌────────────────┐     ┌───────────────┐
               │   AWS ECR      │     │   EC2 Server  │
               │ (Image Store)  │     │ (Runs App)    │
               └────────────────┘     └───────────────┘
```

---

## 🧰 Tech Stack & Tools

- **Core Agent Framework**: `langgraph`, `langchain`, `langchain-groq` (LLMs: `llama-3.1-8b-instant`, `llama-3.3-70b-versatile`)
- **Backend**: `Flask` (REST API server)
- **Frontend**: `Streamlit` (Interactive UI)
- **Machine Learning**: `scikit-learn`, `pandas`, `joblib` (Random Forest Classifier for Churn Prediction)
- **RAG (Retrieval-Augmented Generation)**: `chromadb`, `pypdf`, `sentence-transformers`, `langchain-huggingface`
- **Database**: `SQLite3`, `sqlalchemy` (Agent memory & Hotel context data)

---

## ⚙️ Detailed Pipeline Breakdowns

### 1. The RAG Pipeline (`src/rag/`)
Responsible for answering policy-related queries from unstructured documents.
- **Loader**: Ingests the PDF (`Company_Retention_Policy_2026.pdf`).
- **Chunker**: Splits the document into semantic chunks using Langchain's TextSplitter.
- **Embedder**: Converts text into vector embeddings using HuggingFace Models.
- **Store & Retriever**: Stores embeddings in a local ChromaDB instance (`vectorstore/chroma_db`) and retrieves the top-k most relevant policy rules whenever the Agent uses the `search_retention_policy` tool.

### 2. The Machine Learning Pipeline (`src/ml/`)
Responsible for establishing whether a customer is a flight risk.
- **Data Loading**: Fetches tabular data of past bookings from SQLite.
- **Preprocessing & Feature Engineering**: Cleans data and formats features (e.g., total spend, past cancellations).
- **Training**: Fits a `RandomForestClassifier` on historical retention data.
- **Inference**: The model is saved as a `.joblib` file. When the `get_customer_risk_score` tool is invoked, it loads the model, processes the single user data point, and predicts a churn probability score (0.0 to 1.0).

### 3. The Agent Pipeline & Tools (`src/agents/` & `src/tools/`)
The agent loop utilizes **LangGraph** to process intermediate steps:
- **Natural Language to SQL Tool**: (`fetch_bookings.py`) Reads the booking database schema dynamically, generates a valid SQLite query using a LLaMa LLM, runs the query, and parses results—all securely.
- **Conditional Human-in-the-loop**: Tools are split into "Safe" and "Sensitive". The execution securely pauses (`interrupt_before`) prior to executing sensitive tools like `send_retention_email` or `request_manager_approval`. The state pauses and waits for Human Approval before resuming.

---

## 💻 Setup & Execution

### 1. Install Dependencies
Ensure you have `uv` or `pip` installed. Check the `requirements.txt`.
```bash
pip install -r requirements.txt
```

### 2. Environment Variables
Create a `.env` file referencing `.env.example`. Make sure you define your API keys:
```env
GROQ_API_KEY=your_groq_api_key_here
```

### 3. Initialize Pipelines
Before starting the servers, you must train the ML model and build the Vector Store.
```bash
# Train the Random Forest Model for churn prediction
uv run python -m src.ml.train_model

# Build the ChromaDB Vector Store for Policy RAG
uv run python -m src.rag.store
```

### 4. Run the Application
You need two terminals to run the detached front and back ends.

**Terminal 1: Start the Backend (Flask & LangGraph Agent)**
```bash
uv run python main.py
```
*(Runs on `http://localhost:5000`)*

**Terminal 2: Start the Frontend (Streamlit)**
```bash
uv run streamlit run app.py
```
*(Runs on `http://localhost:8501`)*