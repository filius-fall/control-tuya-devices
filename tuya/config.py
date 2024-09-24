from dotenv import load_dotenv
import os
from . import logger

load_dotenv()

CLIENTKEY=os.getenv('CLIENTKEY')
CLIENTSECRET=os.getenv('CLIENTSECRET')
APIREGION=os.getenv('APIREGION')

