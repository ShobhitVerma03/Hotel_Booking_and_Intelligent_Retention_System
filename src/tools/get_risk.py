# Tool: Get churn risk

# Allows the agent to check if a customer is "High Risk".


import json
from langchain_core.tools import tool
from src.ml.predictor import get_churn_risk
from src.utils.db_ops import fetch_booking_by_id

@tool
def get_customer_risk_score(customer_id: int):
    """
    Calculates the churn risk score (0 to 1) for a specific customer.
    Uses the ML model to predict probability of cancellation.
    Returns: JSON string with risk_score and risk_level.
    """
    # 1. Fetch data first (Use utility, not the tool wrapper)
    customer_data = fetch_booking_by_id(customer_id)
    
    if "error" in customer_data:
        return json.dumps(customer_data)

    # 2. Get Prediction
    try:
        risk_score = get_churn_risk(customer_data)
        
        return json.dumps({
            "customer_id": customer_id,
            "risk_score": risk_score,
            "risk_level": "HIGH" if risk_score >= 0.7 else "LOW"
        })
    except Exception as e:
        return json.dumps({"error": f"Risk calculation failed: {str(e)}"})