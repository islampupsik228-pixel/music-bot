import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import os
import re
import asyncio
import requests
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from shazamio import Shazam

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

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "🎧 Музыка Ямарова работает!")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.strip()
    chat_id = message.chat.id
    
    url_match = re.search(r'https?://[^\s\)]+', text)
    clean_url = url_match.group(0) if url_match else text
    
    if "tiktok.com" not in clean_url:
        return

    msg = bot.reply_to(message, "🔍 Обрабатываю...")
    filename = f'tt_{chat_id}.mp3'

    try:
        res = requests.post("https://www.tikwm.com/api/", data={"url": clean_url, "hd": 1}).json()
        
        if "data" not in res or "music" not in res["data"]:
            bot.edit_message_text("❌ Ошибка: не удалось получить аудио из TikTok.", chat_id, msg.message_id)
            return

        audio_bytes = requests.get(res["data"]["music"]).content
        with open(filename, 'wb') as f: 
            f.write(audio_bytes)

        song_title = res["data"].get("title", "Audio")
        artist_name = "TikTok"

        # Пытаемся распознать через Shazam
        try:
            async def recognize():
                shazam = Shazam()
                return await shazam.recognize(filename)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            out = loop.run_until_complete(recognize())

            if 'track' in out:
                artist_name = out['track'].get('subtitle', 'TikTok')
                song_title = out['track'].get('title', song_title)
        except Exception as shazam_err:
            print(f"Шазам пропущен: {shazam_err}")

        clean_filename = f"{artist_name} - {song_title}.mp3"
        clean_filename = re.sub(r'[\\/*?:"<>|]', "", clean_filename)

        # СРАЗУ отправляем аудиофайл без всяких лишних кнопок, раз трек один!
        bot.edit_message_text(f"✨ Готово!\n🎵 {artist_name} — {song_title}", chat_id, msg.message_id)
        
        with open(filename, 'rb') as audio:
            bot.send_audio(
                chat_id, 
                audio, 
                title=song_title, 
                performer=artist_name,
                visible_file_name=clean_filename
            )
            
    except Exception as e:
        print(f"Ошибка: {e}")
        bot.edit_message_text("❌ Ошибка при обработке ссылки.", chat_id, msg.message_id)
    finally:
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except:
                pass

print("🚀 Запуск ручного пуллинга...")
offset = 0

while True:
    try:
        updates = bot.get_updates(offset=offset, timeout=20, allowed_updates=["message", "callback_query"])
        for update in updates:
            offset = update.update_id + 1
            bot.process_new_updates([update])
    except Exception as e:
        print(f"Ошибка пуллинга: {e}")
        time.sleep(3)
        
