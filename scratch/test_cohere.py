import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import cohere

load_dotenv()
api_key = os.environ.get("COHERE_API_KEY")
print(f"Loaded COHERE_API_KEY: {api_key[:5]}... (length={len(api_key)})")

try:
    client = cohere.ClientV2(api_key=api_key)
    print("Sending request to cohere command-a-plus-05-2026...")
    resp = client.chat(
        model="command-a-plus-05-2026",
        messages=[{"role": "user", "content": "Hi"}],
    )
    print("Success:", resp.message.content[0].text)
except Exception as e:
    print("Error class:", e.__class__.__name__)
    print("Error:", str(e))
