import os
import time
import requests

# --- Configuration ---
BASE_URL = os.environ.get("BASE_URL", "YOUR_RENDER_APP_URL_HERE") # e.g., "https://my-minecraft-bot.onrender.com"

PING_INTERVAL_SECONDS = 5 * 60 # Ping every 5 minutes to keep Render.com service awake

def pinger_job():
    if "YOUR_RENDER_APP_URL_HERE" in BASE_URL:
        print("Pinger: BASE_URL is not set. Skipping pinger job.")
        return

    print(f"Pinger: Starting to ping {BASE_URL} every {PING_INTERVAL_SECONDS} seconds...")
    while True:
        try:
            response = requests.get(BASE_URL)
            print(f"Pinger: Pinged {BASE_URL}. Status Code: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Pinger: Error pinging {BASE_URL}: {e}")
        time.sleep(PING_INTERVAL_SECONDS)

if __name__ == '__main__':
    pinger_job()
