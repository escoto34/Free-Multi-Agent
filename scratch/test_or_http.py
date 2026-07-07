import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ.get("OPENROUTER_API_KEY")
print(f"Loaded OPENROUTER_API_KEY: {api_key[:5]}... (length={len(api_key)})")

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

data = {
    "model": "tencent/hy3:free",
    "messages": [{"role": "user", "content": "Hi"}],
}

print("Sending POST request to OpenRouter...")
resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
print("Status Code:", resp.status_code)
print("Response JSON:", resp.json())
