import telebot
import os
import re
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import yt_dlp

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

    msg = bot.reply_to(message, "🔍 Скачиваю аудио...")
    output_template = f'tt_{chat_id}'
    filename = f'{output_template}.mp3'

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_template,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
    }

    try:
        # Скачиваем через yt-dlp
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=True)
            song_title = info.get('title', 'Audio')
            artist_name = info.get('uploader', 'TikTok')

        # Очищаем название от запрещенных символов для файловой системы
        clean_filename = f"{artist_name} - {song_title}.mp3"
        clean_filename = re.sub(r'[\\/*?:"<>|]', "", clean_filename)

        bot.edit_message_text(f"✨ Готово!\n🎵 {artist_name} — {song_title}", chat_id, msg.message_id)
        
        # Отправляем готовый файл в Telegram с правильными тегами
        if os.path.exists(filename):
            with open(filename, 'rb') as audio:
                bot.send_audio(
                    chat_id, 
                    audio, 
                    title=song_title, 
                    performer=artist_name,
                    visible_file_name=clean_filename
                )
        else:
            bot.edit_message_text("❌ Ошибка: файл не был создан.", chat_id, msg.message_id)

    except Exception as e:
        print(f"Ошибка yt-dlp: {e}")
        bot.edit_message_text("❌ Не удалось скачать видео из TikTok.", chat_id, msg.message_id)
    finally:
        # Удаляем временный файл
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
