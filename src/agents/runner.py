# src/runner.py  (or wherever you keep it)
import uuid
from langchain_core.messages import HumanMessage
from src.agents.graph import app

def run_interactive_session(customer_id: int):
    print(f"\n🚀 Starting interactive retention session for Customer ID: {customer_id}")
    print("Type your message or 'exit' to quit.")
    print("=" * 70)

    thread_id = f"retention_{customer_id}_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}

    # Initial trigger message
    initial_input = f"Please process retention for customer_id {customer_id}. Start now."

    # Send the initial message
    print("\nSending initial request to agent...")
    events = app.stream(
        {"messages": [HumanMessage(content=initial_input)]},
        config,
        stream_mode="values"
    )

    for event in events:
        _print_event(event)

    # Now enter interactive loop
    while True:
        user_input = input("\n👤 You (reply or 'exit'): ").strip()
        if user_input.lower() in ["exit", "quit", "q"]:
            print("👋 Session ended.")
            break

        if not user_input:
            continue

        # Resume / continue the stream with new human message
        events = app.stream(
            {"messages": [HumanMessage(content=user_input)]},
            config,
            stream_mode="values"
        )

        for event in events:
            _print_event(event)

def _print_event(event):
    """Helper to nicely display agent thoughts, tool calls, results"""
    if "messages" not in event:
        return

    msg = event["messages"][-1]

    if msg.type == "ai":
        if msg.tool_calls:
            print("\n🤖 AGENT is calling tools:")
            for tc in msg.tool_calls:
                print(f"  → {tc['name']} (args: {tc['args']})")
        else:
            print(f"\n🤖 AGENT: {msg.content}")

    elif msg.type == "tool":
        name = msg.name or "unknown"
        content = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
        print(f"\n🛠️ TOOL ({name}): {content}")

if __name__ == "__main__":
    run_interactive_session(101)  # John Doe example