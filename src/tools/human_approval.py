# Tool: Human-in-the-loop

# A safety brake. If the agent wants to do something crazy (like a 50% discount), it calls this.


from langchain_core.tools import tool
from pydantic import BaseModel, Field

class ApprovalInput(BaseModel):
    reason: str = Field(description="The reason for requiring approval, e.g., 'High Risk' or 'Discount > 20%'")
    proposed_offer: str = Field(description="The specific offer being proposed, e.g., '20% discount'")

@tool("request_manager_approval", args_schema=ApprovalInput)
def request_manager_approval(reason: str, proposed_offer: str):
    """
    Requests human manager approval for high-risk or high-value offers.
    Use this if the offer exceeds standard policy limits.
    """
    print(f"\n✋ REQUESTING APPROVAL: {reason}")
    print(f"Proposed Offer: {proposed_offer}")
    
    # For the automated agent flow, we simulate "Pending"
    return "Approval Request Submitted. Waiting for manager decision."