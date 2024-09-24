from dotenv import load_dotenv
import os
from . import logger

load_dotenv()

CLIENTKEY=os.getenv('CLIENTID')
CLIENTSECRET=os.getenv('CLIENTSECRET')
APIREGION=os.getenv('CLIENTREGION')

