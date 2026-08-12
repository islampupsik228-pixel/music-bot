import telebot
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp
import os
import re
import asyncio
import requests
import subprocess
from shazamio import Shazam

TOKEN = '8986883128:AAE7XgMQyf0UkThA1L38vsiSPz7FbJU_Us8'
bot = telebot.TeleBot(TOKEN)

user_data = {}

def get_audio_duration(file_path):
    try:
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
        output = subprocess.check_output(cmd).decode().strip()
        return float(output)
    except Exception:
        return 30.0

async def recognize_multiple_tracks(file_path):
    shazam = Shazam()
    duration = get_audio_duration(file_path)
    found_tracks = []
    seen_keys = set()

    # Размер куска 5 сек, шаг 3 сек для максимальной точности на коротких переходах
    chunk_size = 5
    step = 3
    start = 0
    chunk_idx = 0

    while start < duration:
        chunk_file = f"chunk_{chunk_idx}_{chat_id_temp}.mp3"
        subprocess.run(
            ['ffmpeg', '-y', '-ss', str(start), '-t', str(chunk_size), '-i', file_path, '-acodec', 'libmp3lame', '-ar', '44100', chunk_file],
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
                        'artist': artist,
                        'search_query': f"{artist} - {title}"
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
        "• Напиши название песни для поиска.\n"
        "• Отправь ссылку на TikTok — я нарежу звук с микро-шагом, распознаю все треки через Shazam и выведу кнопки!"
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

    if is_tiktok:
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
                'tt_title': tt_title,
                'tracks': tracks
            }

            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton(text="🎬 Полный звук из TikTok", callback_data="dl_tt"))
            
            for idx, trk in enumerate(tracks):
                btn_text = f"🎧 Shazam: {trk['artist']} - {trk['title']}"
                markup.add(InlineKeyboardButton(text=btn_text, callback_data=f"dl_shz_{idx}"))

            text_result = "✨ **Найдено несколько треков!** Выбери, что скачать:" if tracks else "✨ Shazam не нашёл отдельных треков, но ты можешь скачать полный звук:"

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

    else:
        msg = bot.reply_to(message, f"🔎 Ищу: «{clean_url}»...")
        download_and_send(chat_id, clean_url, msg.message_id, search=True)

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

@bot.callback_query_handler(func=lambda call: call.data.startswith('dl_shz_'))
def callback_download_shazam_track(call):
    chat_id = call.message.chat.id
    if chat_id not in user_data:
        bot.answer_callback_query(call.id, "Сессия истекла. Отправь ссылку снова.")
        return

    idx = int(call.data.split('_')[-1])
    tracks = user_data[chat_id].get('tracks', [])
    if idx >= len(tracks):
        bot.answer_callback_query(call.id, "Ошибка выбора трека.")
        return

    track = tracks[idx]
    query = track['search_query']
    
    bot.answer_callback_query(call.id, f"Скачиваю: {query}")
    bot.edit_message_text(f"🔎 Скачиваю полную версию: **{query}**...", chat_id=chat_id, message_id=call.message.message_id)
    
    if os.path.exists(user_data[chat_id]['tt_file']):
        os.remove(user_data[chat_id]['tt_file'])
        
    download_and_send(chat_id, query, call.message.message_id, search=True)

def download_and_send(chat_id, query, msg_id, search=False):
    filename = f'song_{chat_id}'
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{filename}.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
    }
    if search:
        ydl_opts['default_search'] = 'ytsearch1:'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=True)
            track_info = info['entries'][0] if 'entries' in info else info
            title = track_info.get('title', query)

        mp3_file = f'{filename}.mp3'
        if os.path.exists(mp3_file):
            with open(mp3_file, 'rb') as audio:
                bot.send_audio(chat_id, audio, title=title, caption="🎧 **Музыка Ямарова**\ntt: yamarovv")
            bot.delete_message(chat_id, msg_id)
            os.remove(mp3_file)
    except Exception as e:
        print(f"Error downloading YouTube track: {e}")
        bot.edit_message_text("❌ Ошибка скачивания.", chat_id=chat_id, message_id=msg_id)

print("🚀 Бот с Shazam (High-Precision) запущен!")
bot.infinity_polling()
