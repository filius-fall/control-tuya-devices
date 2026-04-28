from dotenv import load_dotenv
import os

load_dotenv()

CLIENT_KEY = os.getenv("CLIENTKEY")
CLIENT_SECRET = os.getenv("CLIENTSECRET")
API_REGION = os.getenv("APIREGION")
