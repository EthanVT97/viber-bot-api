import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    CUSTOMER_API_KEY = os.getenv("CUSTOMER_API_KEY")
    BILLING_API_KEY = os.getenv("BILLING_API_KEY")
    CHATLOG_API_KEY = os.getenv("CHATLOG_API_KEY")
    WHITELISTED_IP = os.getenv("WHITELISTED_IP")
    ADMIN_SECRET = os.getenv("ADMIN_SECRET")

config = Config()
