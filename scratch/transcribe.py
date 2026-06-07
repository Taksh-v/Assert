import os
import requests
from dotenv import load_dotenv

# Load env variables
load_dotenv()

api_key = os.getenv("groq_api_key", "").strip()
if not api_key:
    print("Error: groq_api_key not found in .env")
    exit(1)

url = "https://api.groq.com/openai/v1/audio/transcriptions"
headers = {
    "Authorization": f"Bearer {api_key}"
}

audio_path = "/Users/takshvadaliya/.gemini/antigravity-ide/brain/62d9333a-d473-448a-a959-4cc4c526df0d/uploaded_media_1780512649577.img"

try:
    with open(audio_path, "rb") as f:
        files = {
            "file": ("audio.webm", f, "audio/webm")
        }
        data = {
            "model": "whisper-large-v3",
            "response_format": "json"
        }
        response = requests.post(url, headers=headers, files=files, data=data)
        
    res_json = response.json()
    if "text" in res_json:
        print("TRANSCRIPT:")
        print(res_json["text"])
    else:
        print(f"Error: {res_json}")
except Exception as e:
    print(f"Exception: {e}")
