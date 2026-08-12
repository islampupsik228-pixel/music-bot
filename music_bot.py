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
    bot.reply_to(
        message, 
        "🎧 **Музыка Ямарова**\n\n"
        "• Отправь мне ссылку на TikTok — я скачаю звук, распознаю трек через Shazam и отправлю его тебе!"
    )

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.strip()
    chat_id = message.chat.id

    url_match = re.search(r'https?://[^\s\)]+', text)
    clean_url = url_match.group(0) if url_match else text
    
    if "tiktok.com" not in clean_url:
        bot.reply_to(message, "❌ Отправь нормальную ссылку на TikTok!")
        return

    msg = bot.reply_to(message, "🔍 Скачиваю и распознаю трек...")
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

        # Конвертируем в нормальный mp3 для Shazam
        converted_file = f'conv_{chat_id}.mp3'
        subprocess.run(
            [FFMPEG_PATH, '-y', '-i', mp3_file, '-acodec', 'libmp3lame', '-ar', '44100', converted_file],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        
        target_file = converted_file if os.path.exists(converted_file) else mp3_file

        # Распознаем трек целиком через Shazam
        async def recognize_track():
            shazam = Shazam()
            out = await shazam.recognize(target_file)
            return out

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        out = loop.run_until_complete(recognize_track())

        track_info = ""
        if 'track' in out:
            title = out['track'].get('title', 'Неизвестно')
            artist = out['track'].get('subtitle', 'Неизвестный исполнитель')
            track_info = f"\n\n🎵 **Распознанный трек:**\n• {artist} — {title}"

        user_data[chat_id] = {
            'file': mp3_file,
            'title': tt_title
        }

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(text="📥 Получить аудиофайлом", callback_data="send_audio"))

        bot.edit_message_text(
            f"✨ **Готово!**{track_info}", 
            chat_id=chat_id, 
            message_id=msg.message_id, 
            reply_markup=markup
        )

        # Чистим временный файл конвертации
        if os.path.exists(converted_file):
            os.remove(converted_file)

    except Exception as e:
        print(f"Error: {e}")
        if os.path.exists(mp3_file):
            os.remove(mp3_file)
        bot.edit_message_text("❌ Не удалось обработать ссылку или найти трек.", chat_id=chat_id, message_id=msg.message_id)

@bot.callback_query_handler(func=lambda call: call.data == 'send_audio')
def callback_send_audio(call):
    chat_id = call.message.chat.id
    if chat_id not in user_data:
        bot.answer_callback_query(call.id, "Сессия истекла. Отправь ссылку снова.")
        return

    bot.answer_callback_query(call.id, "Отправляю файл...")
    data = user_data[chat_id]

    if os.path.exists(data['file']):
        with open(data['file'], 'rb') as audio:
            bot.send_audio(chat_id, audio, title=data['title'], caption="🎧 **Музыка Ямарова**\ntt: yamarovv")
        bot.delete_message(chat_id, call.message.message_id)
        os.remove(data['file'])

print("🚀 Бот запущен!")
bot.infinity_polling()
