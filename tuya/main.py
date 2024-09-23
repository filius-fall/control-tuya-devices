import os
from dotenv import load_dotenv

from . import config
from . import logger

load_dotenv()
def main():

    API_KEY = os.getenv('CLIENTID')
    API_SECRET = os.getenv('CLIENTSECRET')
    logger.logs.info("This is info",API_KEY=config.CLIENTID,API_SECRET=config.CLIENTSECRET)


if __name__ == "__main__":
    main()