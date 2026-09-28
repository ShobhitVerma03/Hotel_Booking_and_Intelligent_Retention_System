import sqlite3
import pandas as pd
import os

# Consolidated Database Path
# Dynamic Path Resolution (Robust for Notebooks)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, "data", "hotel_retention.db")

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Database not found at {DB_PATH}. Please run setup_db.py first.")
    return sqlite3.connect(DB_PATH)

def fetch_booking_by_id(customer_id: int):
    """
    Fetches booking details for a given customer ID.
    Returns: Dictionary with customer details or error message.
    """
    try:
        conn = get_db_connection()
        query = "SELECT * FROM bookings WHERE customer_id = ?"
        df = pd.read_sql(query, conn, params=(customer_id,))
        conn.close()

        if df.empty:
            return {"error": f"Customer ID {customer_id} not found."}
        
        return df.iloc[0].to_dict()
    except Exception as e:
        return {"error": str(e)}

def search_customers_by_name(name_query: str):
    """
    Searches for customers by partial name match.
    Returns: List of matching customer dictionaries.
    """
    try:
        conn = get_db_connection()
        # Case-insensitive partial match
        query = "SELECT * FROM bookings WHERE name LIKE ?"
        # Add wildcards for partial match
        search_term = f"%{name_query}%"
        
        df = pd.read_sql(query, conn, params=(search_term,))
        conn.close()

        if df.empty:
            return []
        
        return df.to_dict(orient="records")
    except Exception as e:
        return [{"error": str(e)}]

def fetch_recent_bookings(limit=5):
    """
    Fetches the most recent bookings for dashboard/bulk analysis.
    """
    try:
        conn = get_db_connection()
        query = "SELECT * FROM bookings ORDER BY check_out_date DESC LIMIT ?"
        df = pd.read_sql(query, conn, params=(limit,))
        conn.close()

        return df.to_dict(orient="records")
    except Exception as e:
        return [{"error": str(e)}]
