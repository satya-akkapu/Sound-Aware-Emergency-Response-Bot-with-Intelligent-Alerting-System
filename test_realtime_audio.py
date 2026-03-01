import numpy as np
import librosa
import sounddevice as sd
import tensorflow as tf
import time
import sqlite3
import os
import requests

from sms_alert import send_sms
from location import get_live_location

APP_URL = "http://127.0.0.1:5000"

# ================= CONFIG =================
SR = 22050
DURATION = 3
SAMPLES = SR * DURATION
N_MELS = 128

THRESHOLD = 0.40
TRIGGER_COUNT = 2
ALERT_COOLDOWN = 30

MODEL_PATH = r"C:\Users\DELL\Downloads\safety bot\models\emergency_model.h5"

CONTROL_FLAG = "control.flag"
EMERGENCY_FLAG = "emergency.flag"

# ================= LOAD MODEL =================
model = tf.keras.models.load_model(MODEL_PATH)
print("✅ Model loaded")

_emergency_hits = 0
last_alert_time = 0

# ================= HELPERS =================
def get_latest_location():
    try:
        r = requests.get(APP_URL + "/get_location", timeout=2)
        return r.json()
    except:
        return {"lat": None, "lon": None}


def notify_emergency():
    try:
        requests.post(APP_URL + "/set_emergency", timeout=1)
    except:
        pass


def get_current_user():
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT first_name, last_name, relative_phone1, relative_phone2
        FROM users ORDER BY id DESC LIMIT 1
    """)
    row = cur.fetchone()
    conn.close()

    if not row:
        return None, []

    first, last, r1, r2 = row
    return f"{first} {last}", [r1, r2]


def extract_features(y):
    y = y / (np.max(np.abs(y)) + 1e-6)
    y = y[:SAMPLES] if len(y) > SAMPLES else np.pad(y, (0, SAMPLES - len(y)))

    mel = librosa.feature.melspectrogram(y=y, sr=SR, n_mels=N_MELS)
    mel = librosa.power_to_db(mel)
    mel = (mel - mel.mean()) / (mel.std() + 1e-6)

    return mel[..., np.newaxis]


def record_audio():
    audio = sd.rec(int(SAMPLES), samplerate=SR, channels=1, dtype="float32")
    sd.wait()
    return audio.flatten()


# ================= MAIN LOOP =================
def listen_forever():
    global _emergency_hits, last_alert_time

    print("🎧 Background listener started")

    while True:
        # 🔴 STOP condition
        if not os.path.exists(CONTROL_FLAG):
            time.sleep(1)
            continue

        y = record_audio()
        features = extract_features(y)[np.newaxis, ...]

        prob = model.predict(features, verbose=0)[0][0]
        print(f"🔍 Probability: {prob:.3f}")

        if prob >= THRESHOLD:
            _emergency_hits += 1
        else:
            _emergency_hits = max(0, _emergency_hits - 1)

        if _emergency_hits >= TRIGGER_COUNT:
            now = time.time()

            if now - last_alert_time >= ALERT_COOLDOWN:
                if not os.path.exists(EMERGENCY_FLAG):
                    print("🚨 EMERGENCY CONFIRMED")

                    open(EMERGENCY_FLAG, "w").close()
                    last_alert_time = now
                    _emergency_hits = 0

                    notify_emergency()

                    name, relatives = get_current_user()
                    loc = get_latest_location()
                    link = get_live_location(loc["lat"], loc["lon"])

                    for num in relatives:
                        if num:
                            send_sms(num, name, link)
                            print("📨 SMS sent to", num)

        # Clear emergency flag after cooldown
        if os.path.exists(EMERGENCY_FLAG):
            if time.time() - last_alert_time > ALERT_COOLDOWN:
                os.remove(EMERGENCY_FLAG)

        time.sleep(0.2)


# ================= RUN =================
if __name__ == "__main__":
    listen_forever()
