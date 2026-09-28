# Streamlit UI
import streamlit as st
import uuid
import requests
from langchain_core.messages import HumanMessage, AIMessage

# ───────────────────────────────────────────────
# 1. Page Configuration & Styling 🎨
# ───────────────────────────────────────────────
st.set_page_config(
    page_title="Hotel Retention AI",
    page_icon="🏨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for "Dark & Aesthetic" Look
st.markdown("""
<style>
    /* Main Background */
    .stApp {
        background-color: #0e1117;
        color: #ffffff;
    }
    
    /* Chat Input Area */
    .stChatInputContainer {
        padding-bottom: 20px;
    }
    
    /* User Message Bubble */
    .stChatMessage[data-testid="stChatMessageUser"] {
        background-color: #2b313e;
        border-right: 4px solid #70a1ff;
        color: #ffffff;
        border-radius: 12px;
    }
    
    /* Agent Message Bubble */
    .stChatMessage[data-testid="stChatMessageAssistant"] {
        background-color: #1c2128;
        border-left: 4px solid #2ed573;
        color: #e0e0e0;
        border-radius: 12px;
    }

    /* Buttons */
    .stButton > button {
        background-color: #2ed573;
        color: black;
        border-radius: 8px;
        font-weight: bold;
        border: none;
    }
    .stButton > button:hover {
        background-color: #7bed9f;
        transform: scale(1.02);
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #1e272e;
    }
    .sidebar-text {
        color: #d2dae2;
    }
</style>
""", unsafe_allow_html=True)

# ───────────────────────────────────────────────
# 2. Session State Initialization 💾
# ───────────────────────────────────────────────
if "messages" not in st.session_state:
    # Add a welcoming starting message
    st.session_state.messages = [
        AIMessage(content="👋 Hello! I'm your Hotel Retention AI.\n\nI can check booking details and propose retention offers.\n\n**Try asking:**\n*\"Check retention for Customer 101\"*")
    ]

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

if "agent_state" not in st.session_state:
    # "ready", "waiting_approval"
    st.session_state.agent_state = "ready"
    st.session_state.pending_tool_call = None

API_URL = "http://localhost:5000/chat"

# API_URL = "http://172.19.20.187:5000/chat"

# ───────────────────────────────────────────────
# 3. Helper Functions 🛠️
# ───────────────────────────────────────────────
def run_agent(user_input=None, resume_input=None):
    """
    Client-side logic to call the Flask API.
    """
    payload = {
        "thread_id": st.session_state.thread_id
    }
    
    if user_input:
        payload["message"] = user_input
        # Clear approval state
        st.session_state.agent_state = "ready"
        st.session_state.pending_tool_call = None
    
    elif resume_input:
        payload["action"] = resume_input # "APPROVE" or "REJECT"
    
    try:
        with st.spinner("🤖 AI is processing..."):
            response = requests.post(API_URL, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                
                # Case 1: Completed successfully
                if data["status"] == "completed":
                    response_text = data["response"]
                    st.session_state.messages.append(AIMessage(content=response_text))
                    st.session_state.agent_state = "ready"
                    st.session_state.pending_tool_call = None
                    st.rerun()
                
                # Case 2: Requires Action (Interrupt)
                elif data["status"] == "requires_action":
                    st.session_state.agent_state = "waiting_approval"
                    st.session_state.pending_tool_call = {
                        "name": data["tool"],
                        "args": data["args"],
                        "message": data["message"]
                    }
                    st.rerun()
                
                # Case 3: Stopped (e.g. Rejected)
                elif data["status"] == "stopped":
                    st.error(f"Workflow Stopped: {data.get('reason')}")
                    st.session_state.agent_state = "ready"
            
            else:
                 st.error(f"API Error: {response.text}")
                 
    except requests.exceptions.ConnectionError:
        st.error("❌ Could not connect to Backend. Is `main.py` running on Port 5000?")
    except Exception as e:
        st.error(f"Client Error: {e}")

# ───────────────────────────────────────────────
# 4. Sidebar Controls ⚙️
# ───────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/color/96/five-star-hotel.png", width=80) 
    st.title("Admin Console")
    st.markdown('<p class="sidebar-text">Manage Retention Requests</p>', unsafe_allow_html=True)
    
    st.divider()
    
    st.caption(f"Session ID: {st.session_state.thread_id[:8]}...")
    st.caption("Backend: Connected ✅") 
    
    if st.button("🗑️ Clear History", use_container_width=True):
        st.session_state.messages = []
        st.session_state.thread_id = str(uuid.uuid4())
        st.rerun()

    st.divider()
    st.info("""
    **Tools Available:**
    - 🏨 Fetch Booking
    - 📊 Risk Analysis
    - 📜 Policy Search
    - 👔 Manager Approval (Sensitive)
    - 📧 Send Email (Sensitive)
    """)

# ───────────────────────────────────────────────
# 5. Main Chat Interface 💬
# ───────────────────────────────────────────────
st.title("🏨 Intelligent Hotel Retention Agent (Client)")
st.caption("AI-Powered Customer Retention & Churn Prevention")

# Display History
for msg in st.session_state.messages:
    if isinstance(msg, HumanMessage):
        with st.chat_message("user"):
            st.markdown(msg.content)
    elif isinstance(msg, AIMessage):
        with st.chat_message("assistant"):
            st.markdown(msg.content)

# ───────────────────────────────────────────────
# 6. Interaction Area (Input or Approval) 🎮
# ───────────────────────────────────────────────

# CASE A: Waiting for Approval
if st.session_state.agent_state == "waiting_approval":
    tool_data = st.session_state.pending_tool_call
    tool_name = tool_data["name"]
    tool_args = tool_data["args"]
    tool_msg = tool_data.get("message", "Approval Required")
    
    st.warning(f"✋ **{tool_msg}**")
    st.json(tool_args)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Approve", type="primary", use_container_width=True):
            run_agent(resume_input="APPROVE")
    with col2:
        if st.button("🚫 Reject", type="secondary", use_container_width=True):
            run_agent(resume_input="REJECT")

# CASE B: Standard Chat Input
else:
    if prompt := st.chat_input("Enter customer request (e.g., 'Check status for John Doe'):"):
        # Add user message to history immediately for better UX
        st.session_state.messages.append(HumanMessage(content=prompt))
        with st.chat_message("user"):
            st.markdown(prompt)
            
        # Trigger Run
        run_agent(user_input=prompt)