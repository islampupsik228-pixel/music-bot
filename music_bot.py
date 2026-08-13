import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import os
import re
import asyncio
import requests
import subprocess
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from shazamio import Shazam

FFMPEG_PATH = os.path.abspath('./ffmpeg') if os.path.exists('./ffmpeg') else 'ffmpeg'

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
        audio_bytes = requests.get(res["data"]["music"]).content
        with open(filename, 'wb') as f: f.write(audio_bytes)

        async def recognize():
            shazam = Shazam()
            return await shazam.recognize(filename)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        out = loop.run_until_complete(recognize())

        text_res = "✨ Готово!"
        song_title = res["data"].get("title", "Audio")
        artist_name = "TikTok"

        if 'track' in out:
            artist_name = out['track'].get('subtitle', 'TikTok')
            song_title = out['track'].get('title', song_title)
            text_res += f"\n🎵 {artist_name} — {song_title}"
        
        user_data[chat_id] = {
            'file': filename, 
            'title': song_title,
            'performer': artist_name
        }
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(text="📥 Скачать", callback_data="send_audio"))
        bot.edit_message_text(text_res, chat_id, msg.message_id, reply_markup=markup)
    except Exception as e:
        bot.edit_message_text("❌ Ошибка.", chat_id, msg.message_id)

@bot.callback_query_handler(func=lambda call: call.data == 'send_audio')
def callback_send_audio(call):
    chat_id = call.message.chat.id
    if chat_id in user_data:
        data = user_data[chat_id]
        if os.path.exists(data['file']):
            title = data.get('title', 'Audio')
            performer = data.get('performer', 'TikTok')
            
            clean_filename = f"{performer} - {title}.mp3"
            clean_filename = re.sub(r'[\\/*?:"<>|]', "", clean_filename)

            with open(data['file'], 'rb') as audio:
                bot.send_audio(
                    chat_id, 
                    audio, 
                    title=title, 
                    performer=performer,
                    visible_file_name=clean_filename
                )
            os.remove(data['file'])

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
