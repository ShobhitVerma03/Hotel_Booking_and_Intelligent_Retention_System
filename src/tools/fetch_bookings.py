import os
import sqlite3
import logging
from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load API keys from .env
load_dotenv()

# --- 1. SETUP DATABASE CONNECTION ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, "data", "hotel_retention.db")

# --- 2. SETUP THE LLM ---
llm = ChatGroq(
    model=os.getenv("GROQ_SQL_MODEL", os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")), 
    temperature=0
)

# --- 3. GET DATABASE SCHEMA ---
def get_database_schema():
    """Fetch the schema of the bookings table"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(bookings)")
        columns = cursor.fetchall()
        conn.close()
        
        if not columns:
             return "Error: Table 'bookings' not found or empty."

        schema = "Table: bookings\nColumns:\n"
        for col in columns:
            schema += f"  - {col[1]} ({col[2]})\n"
        return schema
    except Exception as e:
        logger.error(f"Error fetching schema: {e}")
        return f"Error fetching schema: {str(e)}"

# --- 4. SQL GENERATION PROMPT ---
sql_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a SQL expert. Generate ONLY valid SQLite queries based on the user's question.

Database Schema:
{schema}

Rules:
1. Return ONLY the SQL query, nothing else
2. Do NOT include ```sql or any markdown formatting
3. Use proper SQLite syntax
4. Always use SELECT statements unless explicitly asked to modify data
5. Limit results to 10 rows unless specified otherwise
6. Table name is 'bookings'
7. When searching by name, use LIKE with wildcards for partial matches (e.g., WHERE name LIKE '%searchterm%')
8. Use case-insensitive searches when appropriate"""),
    ("human", "{question}")
])

sql_chain = sql_prompt | llm

@tool
def fetch_customer_booking(query: str):
    """
    Useful for getting ANY data from the database using natural language.
    You can search by Name, ID, Price, Date, or any other column.
    
    Args:
        query (str): The natural language question.
        Examples: 
        - "Get details for customer named Alice"
        - "What is the booking price for customer ID 101?"
        - "Show me the top 5 most expensive bookings"
    """
    try:
        # Step 1: Get database schema
        schema = get_database_schema()
        logger.info(f"Database Schema: {schema}")
        
        if "Error" in schema:
            return schema

        # Step 2: Generate SQL query using LLM
        logger.info(f"Generating SQL for query: {query}")
        try:
            response = sql_chain.invoke({
                "schema": schema,
                "question": query
            })
            # Log the raw response for debugging
            logger.info(f"LLM Response: {response.content}")
        except Exception as llm_error:
            logger.error(f"LLM Invocation Failed: {llm_error}")
            return f"Error generating SQL: {str(llm_error)}"
        
        # Extract the SQL query from the response
        generated_sql = response.content.strip()
        
        # Clean up any potential markdown formatting
        generated_sql = generated_sql.replace("```sql", "").replace("```", "").strip()
        logger.info(f"Executed SQL: {generated_sql}")
        
        # Step 3: Execute the query
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(generated_sql)
        
        # Fetch results
        results = cursor.fetchall()
        column_names = [description[0] for description in cursor.description]
        conn.close()
        
        # Step 4: Format results
        if not results:
            return "No records found matching that query."
        
        # Convert to readable format
        formatted_results = []
        for row in results:
            row_dict = dict(zip(column_names, row))
            formatted_results.append(row_dict)
        
        return str(formatted_results)

    except sqlite3.Error as e:
        logger.error(f"Database Error: {e}")
        return f"Database error: {str(e)}\nGenerated SQL: {generated_sql}"
    except Exception as e:
        logger.error(f"General Error: {e}")
        return f"Error querying database: {str(e)}"

if __name__ == "__main__":
    # Test run
    test_query = "give the details of customer named Lav Soni"
    print(f"Running test query: {test_query}")
    result = fetch_customer_booking.invoke(test_query)
    print("Final Result:", result)