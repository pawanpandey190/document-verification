import requests
import os

ACCESS_TOKEN = "1000.a8de813a4d57138ea2ca5b355dd0bec8.bf62dd3f44d4e932834966130d4b28f1"
   # must match token region





ROOT_FOLDER_ID = "bc7yn0af400fe99624e5d814ce1d35d797d01"
folder_id = "bc7yn1947a2084da745828e2a7eee059e275e"






import requests
import json

TOKEN = "YOUR_ACCESS_TOKEN"
FOLDER_ID = "bc7yn1947a2084da745828e2a7eee059e275e"

url = f"https://www.zohoapis.in/workdrive/api/v1/files/{folder_id}/files"

headers = {
    "Authorization": f"Zoho-oauthtoken {ACCESS_TOKEN}",
    "Accept": "application/vnd.api+json"
}

r = requests.get(url, headers=headers)
r.raise_for_status()

for item in r.json()["data"]:
    print(
        item["attributes"]["name"],
        "| type:", item["attributes"]["type"],
        "| id:", item["id"]
    )
