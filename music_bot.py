import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import os
import re
import asyncio
import requests
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from shazamio import Shazam

FFMPEG_PATH = os.path.abspath('./ffmpeg') if os.path.exists('./ffmpeg') else 'ffmpeg'
FFPROBE_PATH = os.path.abspath('./ffprobe') if os.path.exists('./ffprobe') else 'ffprobe'

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_health_check_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

threading.Thread(target=run_health_check_server, daemon=True).start()

TOKEN = '8986883128:AAGIPOEF-kTU7clAQnVhxzTf4dHfsP1j8no'
bot = telebot.TeleBot(TOKEN)

user_data = {}
chat_id_temp = None

def get_audio_duration(file_path):
    try:
        cmd = [FFPROBE_PATH, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
        output = subprocess.check_output(cmd).decode().strip()
        return float(output)
    except Exception:
        return 30.0

async def recognize_multiple_tracks(file_path):
    shazam = Shazam()
    duration = get_audio_duration(file_path)
    found_tracks = []
    seen_keys = set()

    chunk_size = 5
    step = 3
    start = 0
    chunk_idx = 0

    while start < duration:
        chunk_file = f"chunk_{chunk_idx}_{chat_id_temp}.mp3"
        subprocess.run(
            [FFMPEG_PATH, '-y', '-ss', str(start), '-t', str(chunk_size), '-i', file_path, '-acodec', 'libmp3lame', '-ar', '44100', chunk_file],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        try:
            out = await shazam.recognize(chunk_file)
            if 'track' in out:
                title = out['track'].get('title')
                artist = out['track'].get('subtitle')
                key = f"{artist} - {title}".lower()
                if key not in seen_keys:
                    seen_keys.add(key)
                    found_tracks.append({
                        'title': title,
                        'artist': artist
                    })
        except Exception as e:
            print(f"Error chunk {chunk_idx}: {e}")
        finally:
            if os.path.exists(chunk_file):
                os.remove(chunk_file)

        start += step
        chunk_idx += 1

    return found_tracks

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message, 
        "🎧 **Музыка Ямарова**\n\n"
        "• Отправь мне ссылку на TikTok — я скачаю звук, распознаю все треки через Shazam и скину тебе!"
    )

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.strip()
    chat_id = message.chat.id
    global chat_id_temp
    chat_id_temp = chat_id

    url_match = re.search(r'https?://[^\s\)]+', text)
    clean_url = url_match.group(0) if url_match else text
    is_tiktok = "tiktok.com" in clean_url

    if not is_tiktok:
        bot.reply_to(message, "❌ Отправь нормальную ссылку на TikTok!")
        return

    msg = bot.reply_to(message, "🔍 Скачиваю аудио из TikTok...")
    filename = f'tt_{chat_id}'
    mp3_file = f'{filename}.mp3'

    try:
        session = requests.Session()
        res_url = session.head(clean_url, allow_redirects=True).url

        res = requests.post("https://www.tikwm.com/api/", data={"url": res_url, "hd": 1}).json()
        if res.get("code") != 0:
            raise Exception("API error")

        audio_url = res["data"]["music"]
        tt_title = res["data"].get("title", "Звук из TikTok")

        audio_bytes = requests.get(audio_url).content
        with open(mp3_file, 'wb') as f:
            f.write(audio_bytes)

        bot.edit_message_text("🔍 Сканирую микро-отрезки и ищу все переходы...", chat_id=chat_id, message_id=msg.message_id)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        tracks = loop.run_until_complete(recognize_multiple_tracks(mp3_file))

        user_data[chat_id] = {
            'tt_file': mp3_file,
            'tt_title': tt_title
        }

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(text="🎬 Полный звук из TikTok", callback_data="dl_tt"))

        text_result = f"✨ **Готово!** Звук скачан.\n📌 Название: {tt_title}"
        if tracks:
            text_result += "\n\n🎵 Распознанные треки:\n" + "\n".join([f"• {t['artist']} — {t['title']}" for t in tracks])

        bot.edit_message_text(
            text_result, 
            chat_id=chat_id, 
            message_id=msg.message_id, 
            reply_markup=markup
        )

    except Exception as e:
        print(f"Error: {e}")
        if os.path.exists(mp3_file):
            os.remove(mp3_file)
        bot.edit_message_text("❌ Не удалось обработать ссылку TikTok.", chat_id=chat_id, message_id=msg.message_id)

@bot.callback_query_handler(func=lambda call: call.data == 'dl_tt')
def callback_download_tt(call):
    chat_id = call.message.chat.id
    if chat_id not in user_data:
        bot.answer_callback_query(call.id, "Сессия истекла. Отправь ссылку снова.")
        return

    bot.answer_callback_query(call.id, "Отправляю звук...")
    data = user_data[chat_id]

    if os.path.exists(data['tt_file']):
        with open(data['tt_file'], 'rb') as audio:
            bot.send_audio(chat_id, audio, title=data['tt_title'], caption="🎧 **Музыка Ямарова**\ntt: yamarovv")
        bot.delete_message(chat_id, call.message.message_id)
        os.remove(data['tt_file'])

print("🚀 Бот запущен!")
bot.infinity_polling()
