import os
import time
import requests
from bs4 import BeautifulSoup
from edge_tts import Communicate
from requests_toolbelt.multipart.encoder import MultipartEncoder
import subprocess
import urllib.request
import tarfile
import re
import asyncio
from datetime import datetime
import pytz

# ⚙️ פרטי התחברות
USERNAME = "0747097784"
PASSWORD = "595944"
TOKEN = f"{USERNAME}:{PASSWORD}"
UPLOAD_PATH_PREFIX = "ivr2:/3/"
GOOGLE_CHAT_WEBHOOK_URL = "https://chat.googleapis.com/v1/spaces/AAAA93D2nNk/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token=ODcYi4zhleWDhoQWrHEYKC35gv57fdMoHH3dXcnkd14"
AMIT_SEGAL_CHANNEL = "amitsegal"

# 🧾 שמות קבצים
MP3_FILE = "news.mp3"
WAV_FILE_TEMPLATE = "{:03}.wav"  # מספור: 000.wav, 001.wav וכו'
FFMPEG_PATH = "./bin/ffmpeg"

# ✅ הורדת ffmpeg אם לא קיים
def ensure_ffmpeg():
    if not os.path.exists(FFMPEG_PATH):
        print("⬇️ מוריד ffmpeg...")
        os.makedirs("bin", exist_ok=True)
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        archive_path = "bin/ffmpeg.tar.xz"
        urllib.request.urlretrieve(url, archive_path)
        with tarfile.open(archive_path) as tar:
            for member in tar.getmembers():
                if os.path.basename(member.name) == "ffmpeg":
                    member.name = "ffmpeg"
                    tar.extract(member, pathgable="bin")
        os.chmod(FFMPEG_PATH, 0o755)

# ⏰ השעה בישראל
def get_israel_time():
    tz = pytz.timezone("Asia/Jerusalem")
    now = datetime.now(tz)
    return now.strftime("%H:%M")

# 🌐 שליפת ההודעה האחרונה והסרטון מהערוץ
def get_last_telegram_message_and_video(channel_username):
    url = f"https://t.me/s/{channel_username}"
    response = requests.get(url, verify=False)
    if response.status_code != 200:
        print("❌ שגיאה בגישה לערוץ.")
        return None, None
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # שליפת ההודעה הטקסטית האחרונה
    messages = soup.find_all('div', class_='tgme_widget_message_text')
    text = messages[-1].get_text(strip=True) if messages else None
    
    # שליפת קישור וידאו אחרון (חיפוש תגיות video או קישורים עם .mp4)
    videos = soup.find_all('video') or soup.find_all('a', href=re.compile(r'\.mp4$'))
    video_url = None
    if videos:
        for video in videos[::-1]:  # בדיקה מהסרטון האחרון
            if video.name == 'video' and video.get('src'):
                video_url = video['src']
                break
            elif video.name == 'a' and video.get('href'):
                video_url = video['href']
                break
    
    return text, video_url

# 🧠 הפקת קול
async def create_voice(text):
    communicate = Communicate(text=text, voice="he-IL-AvriNeural")
    await communicate.save(MP3_FILE)

# 🔄 המרה ל־WAV
def convert_to_wav(input_file, wav_filename):
    subprocess.run([FFMPEG_PATH, "-y", "-i", input_file, "-ar", "8000", "-ac", "1", "-acodec", "pcm_s16le", wav_filename])

# ⬆️ העלאה לימות המשיח
def upload_to_yemot(wav_filename):
    with open(wav_filename, 'rb') as f:
        m = MultipartEncoder(
            fields={
                'token': TOKEN,
                'path': UPLOAD_PATH_PREFIX + os.path.basename(wav_filename),
                'message': 'uploading',
                'file': (os.path.basename(wav_filename), f, 'audio/wav')
            }
        )
        response = requests.post('https://www.call2all.co.il/ym/api/UploadFile', data=m, headers={'uvant-Type': m.content_type})
        print("📤 הועלה לימות המשיח:", response.json())

# 📤 שליחה ל-Google Chat
def send_to_google_chat(message):
    payload = {"text": message}
    response = requests.post(GOOGLE_CHAT_WEBHOOK_URL, json=payload)
    if response.status_code != 200:
        print(f"❌ שגיאה בשליחה ל-Google Chat: {response.text}")

# 🧮 מציאת מספר קובテクסט פנוי
def get_next_filename():
    i = 0
    while True:
        filename = WAV_FILE_TEMPLATE.format(i)
        if not os.path.exists(filename):
            return filename
        i += 1

# 🔁 לולאת האזנה
def main_loop():
    ensure_ffmpeg()
    last_seen_text = ""
    last_seen_video = ""
    print("🎧 מאזין לערוץ @amitsegal כל 5 דקות...")
    while True:
        print("\n🕒 בודק הודעות וסרטונים חדשים...")
        try:
            current_text, current_video_url = get_last_telegram_message_and_video(AMIT_SEGAL_CHANNEL)
            
            # טיפול בהודעה טקסטית
            if current_text and current_text != last_seen_text:
                print("🆕 הודעה טקסט חדשה נמצאה!")
                print("📄 תוכן:", current_text)
                last_seen_text = current_text
                time_prefix = f"חדשות אמש, השעה {get_israel_time()}. "
                full_text = time_prefix + current_text
                asyncio.run(create_voice(full_text))
                wav_file = get_next_filename()
                convert_to_wav(MP3_FILE, wav_file)
                upload_to_yemot(wav_file)
                send_to_google_chat(full_text)
                os.remove(wav_file)
                os.remove(MP3_FILE) if os.path.exists(MP3_FILE) else None
            else:
                print("ℹ️ אין הודעות טקסט חדשות.")
            
            # טיפול בסרטון
            if current_video_url and current_video_url != last_seen_video:
                print("🎥 סרטון חדש נמצא:", current_video_url)
                last_seen_video = current_video_url
                # הורדת הסרטון
                video_file = f"video_{int(time.time())}.mp4"
                urllib.request.urlretrieve(current_video_url, video_file)
                # המרת השמע ל-WAV
                video_wav_file = get_next_filename()
                convert_to_wav(video_file, video_wav_file)
                upload_to_yemot(video_wav_file)
                print("📤 הועלה שמע הסרטון לימות המשיח:", video_wav_file)
                # שליחת הודעה ל-Google Chat (אם אין טקסט, שולח הודעה דיפולטיבית)
                video_message = f"חדשות אמש, השעה {get_israel_time()}. סרטון ללא טקסט" if not current_text else f"חדשות אמש, השעה {get_israel_time()}. {current_text}"
                send_to_google_chat(video_message)
                os.remove(video_file)
                os.remove(video_wav_file)
            else:
                print("ℹ️ אין סרטונים חדשים.")
                
        except Exception as e:
            print("❌ שגיאה:", e)
        time.sleep(300)

if __name__ == "__main__":
    main_loop()
