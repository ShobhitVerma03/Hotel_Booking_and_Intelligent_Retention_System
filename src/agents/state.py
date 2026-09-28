# Graph state definition
# it holds the entire thought process (Thought -> Action -> Observation).


from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    # The 'messages' key is all we need for a ReAct agent.
    # It stores the conversation history: [User, AI, Tool, AI, ...]
    messages: Annotated[list, add_messages]