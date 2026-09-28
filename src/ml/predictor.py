# Inference logic


import joblib
import os
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from src.ml.loader import load_data
from src.ml.preprocessor import feature_engineering

# Paths
from src.utils.db_ops import DB_PATH

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_PATH = os.path.join(BASE_DIR, "models", "churn_model.joblib")

def train_model():
    """Trains a Random Forest model and saves it."""
    print("🔄 Starting Model Training...")
    
    # 1. Load Data
    df = load_data(DB_PATH)
    if df.empty:
        print("❌ No data to train on!")
        return

    # 2. Preprocess
    X, y = feature_engineering(df, is_training=True)

    # 3. Train (Random Forest)
    model = RandomForestClassifier(n_estimators=50, random_state=42)
    model.fit(X, y)

    # 4. Save Model
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"✅ Model saved to {MODEL_PATH}")
    print(f"🎯 Training Accuracy: {model.score(X, y):.2f}")

def get_churn_risk(customer_data):
    """
    Predicts risk for a single customer dictionary.
    Returns: probability of churn (0.0 to 1.0)
    """
    if not os.path.exists(MODEL_PATH):
        print("⚠️ Model not found. Please train first.")
        return 0.5  # Default uncertainty

    model = joblib.load(MODEL_PATH)
    
    # Convert single dict to DataFrame
    df = pd.DataFrame([customer_data])
    
    # Preprocess
    X = feature_engineering(df, is_training=False)
    
    # Predict Probability
    risk_score = model.predict_proba(X)[0][1] # Probability of class 1 (Churn)
    return risk_score

if __name__ == "__main__":
    train_model()