# Data loading for ML
import pandas as pd
import sqlite3
import os

def load_data(db_path):
    """
    Connects to the SQLite database and loads booking data.
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"❌ Database not found at: {db_path}")

    conn = sqlite3.connect(db_path)
    
    # We want rows that match our feature needs
    query = """
    SELECT 
        customer_id,
        room_type,
        booking_price,
        total_stays,
        previous_cancellations,
        special_requests,
        status
    FROM bookings
    """
    
    try:
        df = pd.read_sql(query, conn)
        print(f"✅ Loaded {len(df)} rows from database.")
        return df
    except Exception as e:
        print(f"❌ Error loading data: {e}")
        return pd.DataFrame()
    finally:
        conn.close()