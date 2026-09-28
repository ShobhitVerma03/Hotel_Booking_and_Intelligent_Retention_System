# src/agents/graph.py
"""
This file builds the ReAct-style agentic loop using LangGraph.
The agent can reason, call tools in any order it decides, and loop until it has a final answer.
Memory (checkpointer) is enabled so sessions can be resumed.
"""

import os
import sqlite3
from typing import List
from dotenv import load_dotenv

# Load env before importing ChatGroq
load_dotenv()

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langgraph.prebuilt import create_react_agent

from langgraph.checkpoint.sqlite import SqliteSaver

# Import the prompt template (must be ChatPromptTemplate)
from src.agents.prompts import AGENT_SYSTEM_PROMPT  # ← should be ChatPromptTemplate

# Import all tools
from src.tools.fetch_bookings import fetch_customer_booking
from src.tools.get_risk import get_customer_risk_score
from src.tools.policy_search import search_retention_policy
from src.tools.send_email import send_retention_email
from src.tools.human_approval import request_manager_approval

# ───────────────────────────────────────────────
# 1. LLM Setup
# ───────────────────────────────────────────────
llm = ChatGroq(
    model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
    temperature=0,              # deterministic = better for tool calling
    max_retries=3,
)

# ───────────────────────────────────────────────
# 2. Tools
# ───────────────────────────────────────────────
tools: List = [
    fetch_customer_booking,
    get_customer_risk_score,
    search_retention_policy,
    send_retention_email,
    request_manager_approval,
]

# ───────────────────────────────────────────────
# 3. Memory / Checkpointer (SQLite-based persistence)
# ───────────────────────────────────────────────
# Creates agent_memory.db in project root
conn = sqlite3.connect("agent_memory.db", check_same_thread=False)
memory = SqliteSaver(conn)

# ───────────────────────────────────────────────
# 4. Build the ReAct Agent (agent ↔ tools loop)
# ───────────────────────────────────────────────
app = create_react_agent(
    model=llm,
    tools=tools,
    prompt=AGENT_SYSTEM_PROMPT,                        # ← must be ChatPromptTemplate
    checkpointer=memory,
    interrupt_before=["tools"],                        # PAUSE before EVERY tool call (safety!)
    # interrupt_before=["send_retention_email", "request_manager_approval"]  # alternative
)

# Optional: Export for notebooks / app.py
# from src.agents.graph import app