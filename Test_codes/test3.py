import requests

ACCESS_TOKEN = "1000.c400a79b41e7a462453d411fbb8838ac.07fdf3b09121f6e4f25fce880c57dbd3"
FILE_ID = "bc7yn59bad057ea0f409891985ff89527e180"  # Passport.pdf
OUTPUT_FILE = "Passport1.pdf"



# url = f"https://www.zohoapis.in/workdrive/api/v1/files/{FILE_ID}/export?format=pdf"

# headers = {
#     "Authorization": f"Zoho-oauthtoken {ACCESS_TOKEN}"
# }

# r = requests.get(url, headers=headers, stream=True)
# r.raise_for_status()

# with open(OUTPUT_FILE, "wb") as f:
#     for chunk in r.iter_content(8192):
#         if chunk:
#             f.write(chunk)

# print("✅ Exported:", OUTPUT_FILE)




import requests

FILE_ID = "bc7yn59bad057ea0f409891985ff89527e180"

url = "https://www.zohoapis.in/workdrive/api/v1/links"

payload = {
    "data": {
        "type": "links",
        "attributes": {
            "resource_id": FILE_ID,
            "link_type": "download",
            "allow_download": True
        }
    }
}

headers = {
    "Authorization": f"Zoho-oauthtoken {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

r = requests.post(url, headers=headers, json=payload)

print("STATUS:", r.status_code)
print(r.text)


