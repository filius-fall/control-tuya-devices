import os
import json
from dotenv import load_dotenv

from . import logger
from . import api_client

load_dotenv()
def main():

    a = api_client.getDeviceDetails()

    os.makedirs('data',exist_ok=True)
    file_path = os.path.join('data','api_response.json')

    with open(file_path, 'a+') as f:
        
        f.seek(0)

        try:
            data = json.load(f)

        except json.JSONDecodeError:
            logger.logs.info("Exception is created and a new json will be created")
            data = []
        
        logger.logs.info("Before Data append",data=data)
        data.append(a)
        json.dump(data,f)
        logger.logs.info("After data Append",data=data)


        
    

        
    


if __name__ == "__main__":
    main()