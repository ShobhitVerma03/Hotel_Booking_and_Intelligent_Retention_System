# Feature engineering


import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder

# Global encoders (in a real app, these would be saved/loaded too)
room_encoder = LabelEncoder()

def feature_engineering(df, is_training=True):
    """
    Prepares raw data for the model.
    """
    df_clean = df.copy()

    # 1. Handle Room Type (Text -> Number)
    # Mocking fit_transform for simplicity in this capstone
    room_map = {"Standard": 0, "Deluxe Suite": 1, "Presidential": 2}
    df_clean['room_type_enc'] = df_clean['room_type'].map(room_map).fillna(0)

    # 2. Handle Special Requests (Yes/No -> 1/0)
    df_clean['has_requests'] = df_clean['special_requests'].notna().astype(int)

    # 3. Select Features for Model
    features = ['room_type_enc', 'booking_price', 'total_stays', 'previous_cancellations', 'has_requests']
    
    if is_training:
        # Create a mock target variable 'churned' based on logic 
        # (Since our DB doesn't have a 'cancelled' column for history yet)
        # LOGIC: High cancellations OR High price (>500) = Likely Churn
        df_clean['churned'] = np.where(
            (df_clean['previous_cancellations'] > 0) | (df_clean['booking_price'] > 600), 
            1, 
            0
        )
        return df_clean[features], df_clean['churned']
    
    return df_clean[features]