import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./governance_agent.db")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")