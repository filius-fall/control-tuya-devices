import os
from dotenv import load_dotenv

from . import api_client

load_dotenv()
def main():

    a = api_client.getDeviceDetails()
    print("Print stat",a)


if __name__ == "__main__":
    main()