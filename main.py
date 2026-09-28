import os
import uuid
import logging
from flask import Flask, request, jsonify
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command
from src.agents.graph import app as agent_app

# ───────────────────────────────────────────────
# 1. Setup & Config
# ───────────────────────────────────────────────
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Safe tools to auto-approve
SAFE_TOOLS = [
    "fetch_customer_booking", 
    "get_customer_risk_score", 
    "search_retention_policy",
]
SENSITIVE_TOOLS = ["request_manager_approval", "send_retention_email"]

@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "service": "Hotel Retention Agent API"})

@app.route("/chat", methods=["POST"])
def chat():
    """
    Main/Chat Endpoint.
    Input JSON:
    {
        "message": "User message here",       (Optional if resuming)
        "thread_id": "unique-session-id",     (Optional, generated if missing)
        "action": "APPROVE" | "REJECT"        (Optional, for resuming interrupts)
    }
    """
    data = request.json
    thread_id = data.get("thread_id", str(uuid.uuid4()))
    user_message = data.get("message")
    action = data.get("action") # "APPROVE" or "REJECT"

    config = {"configurable": {"thread_id": thread_id}}

    try:
        # ───────────────────────────────────────────────
        # 2. Determine Execution Mode (Start vs Resume)
        # ───────────────────────────────────────────────
        iterator = None
        
        if action:
            # RESUME MODE
            logger.info(f"Resuming thread {thread_id} with action: {action}")
            if action == "APPROVE":
                # Resume with None -> Runs the tool
                # cmd = Command(resume=None)  <-- Old way causing error
                # For interrupt_before, we just call stream with None/Input?
                # Actually, for create_react_agent, we just continue.
                iterator = agent_app.stream(None, config, stream_mode="values")
            elif action == "REJECT":
                # For now, we just stop. Real-world: Insert "Tool Rejected" message.
                return jsonify({
                    "status": "stopped",
                    "reason": "User rejected action.",
                    "thread_id": thread_id
                })
        elif user_message:
            # NEW MESSAGE MODE
            logger.info(f"New message on thread {thread_id}: {user_message}")
            inputs = {"messages": [HumanMessage(content=user_message)]}
            iterator = agent_app.stream(inputs, config, stream_mode="values")
        else:
            return jsonify({"error": "Either 'message' or 'action' is required."}), 400

        # ───────────────────────────────────────────────
        # 3. Process Stream & Handle Interrupts
        # ───────────────────────────────────────────────
        final_response = ""
        
        # We need to loop manually to handle the "Safe Tool" auto-resume recursion
        # But `agent_app.stream` yields events. If it hits an interrupt, it stops yielding.
        
        # NOTE: To handle "Auto-Resume" correctly in a sync API loop, we might need a while loop?
        # Or simply: run stream -> check state -> if interrupt & safe -> resume -> repeat.
        
        # Let's use a helper to drain the stream until a REAL stop
        
        current_iterator = iterator
        
        while True:
            # Consume the iterator
            last_event = None
            for event in current_iterator:
                last_event = event
                # Capture the AI's final text response if present
                if "messages" in event:
                    last_msg = event["messages"][-1]
                    if isinstance(last_msg, AIMessage) and last_msg.content:
                        final_response = last_msg.content
            
            # CHECK STATE
            snapshot = agent_app.get_state(config)
            
            if not snapshot.next:
                # Execution Finished
                return jsonify({
                    "status": "completed",
                    "response": final_response,
                    "thread_id": thread_id
                })
            
            # We are PAUSED. Why?
            last_msg = snapshot.values["messages"][-1]
            if not isinstance(last_msg, AIMessage) or not last_msg.tool_calls:
                 return jsonify({"status": "error", "message": "Unknown interrupt state"}), 500
            
            tool_calls = last_msg.tool_calls
            is_sensitive = any(tc["name"] in SENSITIVE_TOOLS for tc in tool_calls)
            
            if is_sensitive:
                # REAL INTERRUPT -> Return to Client
                sensitive_tool_call = next(tc for tc in tool_calls if tc["name"] in SENSITIVE_TOOLS)
                return jsonify({
                    "status": "requires_action",
                    "tool": sensitive_tool_call["name"],
                    "args": sensitive_tool_call["args"],
                    "thread_id": thread_id,
                    "message": f"Approval required for {sensitive_tool_call['name']}"
                })
            else:
                # SAFE INTERRUPT -> Auto-Resume
                logger.info("Auto-approving safe tool...")
                # cmd = Command(resume=None) <-- Old way causing error
                current_iterator = agent_app.stream(None, config, stream_mode="values")
                # Loop continues...

    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Run on port 5000
    print("🚀 Starting Flask Server on http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
