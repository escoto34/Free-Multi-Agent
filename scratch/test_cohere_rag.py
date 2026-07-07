import os
from dotenv import load_dotenv
import cohere

load_dotenv()
api_key = os.environ.get("COHERE_API_KEY")

client = cohere.ClientV2(api_key=api_key)

try:
    print("Testing command-a-plus-05-2026 with documents...")
    resp = client.chat(
        model="command-a-plus-05-2026",
        messages=[{"role": "user", "content": "Tell me about quantum computing based on the documents."}],
        documents=[{"data": {"text": "IBM plans to release modular quantum computers by 2026."}}],
    )
    print("Success command-a-plus-05-2026:", resp.message.content[0].text)
except Exception as e:
    print("Error with command-a-plus-05-2026:", str(e))

try:
    print("Testing command-r-plus-08-2024 with documents...")
    resp = client.chat(
        model="command-r-plus-08-2024",
        messages=[{"role": "user", "content": "Tell me about quantum computing based on the documents."}],
        documents=[{"data": {"text": "IBM plans to release modular quantum computers by 2026."}}],
    )
    print("Success command-r-plus-08-2024:", resp.message.content[0].text)
except Exception as e:
    print("Error with command-r-plus-08-2024:", str(e))
