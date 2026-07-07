import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.clients import get_client

try:
    client = get_client("openrouter")
    print("Sending completions request to openrouter tencent/hy3:free...")
    resp = client.chat.completions.create(
        model="tencent/hy3:free",
        messages=[{"role": "user", "content": "Hi"}],
    )
    print("Success:", resp.choices[0].message.content)
except Exception as e:
    print("Error class:", e.__class__.__name__)
    print("Error:", str(e))
