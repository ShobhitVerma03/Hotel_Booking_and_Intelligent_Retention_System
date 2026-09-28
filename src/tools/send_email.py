# Tool: Draft/send email
# Simulates sending the final email to the customer.

from langchain_core.tools import tool
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

load_dotenv()

@tool
def send_retention_email(customer_name: str, email_address: str, subject: str, body: str):
    """
    Sends a final retention offer email to the customer using Gmail SMTP.
    Requires EMAIL_ADDRESS and EMAIL_PASSWORD in .env.
    
    WARNING: Do NOT use this tool to "search" or "list" customers. 
    Only use it when you are ready to send an actual email to a specific person.
    """
    sender_email = os.getenv("EMAIL_ADDRESS")
    sender_password = os.getenv("EMAIL_PASSWORD")

    # Fallback to simulation if credentials are missing
    if not sender_email or not sender_password:
        # In a real app, this would use SMTP. For Capstone, we print to console.
        print("\n" + "="*40)
        print(f"📧 [SIMULATION] SENDING EMAIL TO: {customer_name} ({email_address})")
        print(f"📝 SUBJECT: {subject}")
        print("-" * 40)
        print(body)
        print("="*40 + "\n")
        return "Email simulated successfully (add credentials to .env for real sending)."

    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = email_address
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # Connect to Gmail SMTP
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
            
        return f"✅ Email sent successfully to {email_address}"
    except Exception as e:
        return f"❌ Failed to send email: {str(e)}"