import os
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

load_dotenv()

api_key = os.getenv("ELEVEN_API_KEY")
client = ElevenLabs(api_key=api_key)

vozes = client.voices.get_all().voices

print("\n=== VOZES DISPONÍVEIS NA SUA CONTA ===\n")
for voz in vozes:
    print(f"Nome: {voz.name}")
    print(f"ID: {voz.voice_id}")
    print("-" * 40)
