import logging
import os
import re
import time
import io
import asyncio
import aiohttp
import uvloop
import cloudscraper

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from google.oauth2.service_account import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# Set event loop policy to uvloop
uvloop.install()

async def download_file_with_aria2(url, dest_path):
    # Menggunakan aria2 untuk mengunduh file
    result = subprocess.run(['aria2c', '-x', '16', '-s', '16', '-k', '1M', '-o', dest_path, url], capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        raise Exception("Failed to download file using aria2")
    else:
        print(f"Downloaded {dest_path}")

# URL untuk file yang akan diunduh jika tidak ditemukan
TOKEN_URL = "https://github.com/Ilham311/newmirror/raw/refs/heads/main/token.pickle"
DIRECT_LINK_GENERATOR_URL = "https://github.com/Ilham311/newmirror/raw/refs/heads/main/direct_link_generator.py"

# Periksa dan unduh file direct_link_generator.py jika tidak ditemukan
if not os.path.exists('direct_link_generator.py'):
    asyncio.run(download_file_with_aria2(DIRECT_LINK_GENERATOR_URL, 'direct_link_generator.py'))

# Impor fungsi direct_link_generator dari modul yang baru dibuat
from direct_link_generator import direct_link_generator

API_ID = 961780
API_HASH = "bbbfa43f067e1e8e2fb41f334d32a6a7"
BOT_TOKEN = "6324930447:AAEK_w2_6XELCbkpVLwPN0_Sm4pfaZYv1G0"
FOLDER_ID = '14kWVa9dUOJr7yraefAkTs5nfzV3vpGbj'

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive']

async def authenticate():
    creds = None
    # Periksa dan unduh file token.pickle jika tidak ditemukan
    if not os.path.exists('token.pickle'):
        await download_file_with_aria2(TOKEN_URL, 'token.pickle')

    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return creds

def extract_file_id(url_or_id):
    match = re.search(r'[-\w]{25,}', url_or_id)
    return match.group(0) if match else url_or_id

async def check_duplicate(file_name, folder_id):
    creds = await authenticate()
    service = build('drive', 'v3', credentials=creds)
    query = f"'{folder_id}' in parents and name='{file_name}' and trashed=false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    return results.get('files', [])

async def upload_file_to_drive(file_name, file_stream, folder_id, message: Message):
    creds = await authenticate()
    service = build('drive', 'v3', credentials=creds)
    media = MediaIoBaseUpload(file_stream, mimetype='application/octet-stream', resumable=True)
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    request = service.files().create(body=file_metadata, media_body=media, fields='id')

    response = None
    total_size = file_stream.getbuffer().nbytes
    start_time = time.time()

    while response is None:
        status, response = request.next_chunk()
        if status:
            current_time = time.time()
            speed = status.resumable_progress / (current_time - start_time)
            await progress_bar(status.resumable_progress, total_size, speed, message, operation="upload")
            await asyncio.sleep(3)  # Update every 3 seconds

    return response.get('id')

async def progress_bar(current, total, speed, message: Message, operation: str):
    percentage = current / total * 100
    progress = int(percentage // 5)
    bar = '■' * progress + '□' * (20 - progress)
    speed_str = human_readable_size(speed) + '/s'
    current_str = human_readable_size(current)
    total_str = human_readable_size(total)
    op_text = "Uploading" if operation == "upload" else "Downloading"
    progress_message = (
        f"**{op_text}...**\n"
        f"┌┤{bar}│ {percentage:.2f}%\n"
        f"├ **Speed** : {speed_str}\n"
        f"├ **Progress** : {current_str} / {total_str}"
    )
    await message.edit_text(progress_message)

def human_readable_size(size, decimal_places=2):
    for unit in ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB']:
        if size < 1024.0:
            return f"{size:.{decimal_places}f} {unit}"
        size /= 1024.0
    return f"{size:.{decimal_places}f} YiB"

async def get_filename_from_response(url):
    scraper = cloudscraper.create_scraper()
    response = scraper.get(url, stream=True, allow_redirects=True)
    cd = response.headers.get("Content-Disposition", "")
    filename = ""
    if cd:
        filename = cd.split("filename=")[-1].strip('"')
    if not filename:
        filename = os.path.basename(response.url)
    if not filename:
        extension_map = {
            "application/pdf": ".pdf", "application/zip": ".zip", "application/x-rar-compressed": ".rar",
            "application/octet-stream": ".bin", "application/json": ".json", "application/xml": ".xml",
            "application/vnd.ms-excel": ".xls", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
            "application/msword": ".doc", "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/vnd.ms-powerpoint": ".ppt", "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
            "text/plain": ".txt", "text/html": ".html", "text/css": ".css", "text/javascript": ".js",
            "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/bmp": ".bmp", "image/svg+xml": ".svg",
            "audio/mpeg": ".mp3", "audio/wav": ".wav", "audio/ogg": ".ogg",
            "video/mp4": ".mp4", "video/x-matroska": ".mkv", "video/x-msvideo": ".avi", "video/quicktime": ".mov", "video/webm": ".webm",
            "application/x-7z-compressed": ".7z", "application/x-tar": ".tar", "application/x-gzip": ".gz"
        }
        extension = extension_map.get(response.headers.get("Content-Type", ""), "")
        filename = "default_file" + extension if extension else "default_file"
    return filename

if os.path.exists("my_bot.session"):
    os.remove("my_bot.session")

app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("clone"))
async def clone(client, message):
    user = message.from_user
    logger.info("User %s started cloning", user.first_name)
    args = message.text.split()
    if len(args) != 2:
        await message.reply_text('Usage: /clone <file_id_or_url>')
        return
    file_id_or_url = args[1]
    file_id = extract_file_id(file_id_or_url)
    try:
        copied_file_id, file_name, file_size, is_duplicate = await copy_file_to_folder(file_id, FOLDER_ID)
        file_size_gb = int(file_size) / (1024 * 1024 * 1024)
        drive_link = f'https://drive.google.com/file/d/{copied_file_id}/view?usp=sharing'
        response = (
            f"Contoh Title: {file_name}\n"
            f"Size: {file_size_gb:.2f} GB\n"
            + ("Sudah tersedia.\n" if is_duplicate else "")
        )
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📥Download Link", url=drive_link)]])
        await message.reply_text(response, reply_markup=keyboard)
    except Exception as e:
        logger.error("Error cloning file: %s", e)
        await message.reply_text('Failed to clone the file.')

@app.on_message(filters.command("mirror"))
async def mirror(client, message):
    user = message.from_user
    logger.info("User %s started mirroring", user.first_name)
    args = message.text.split()
    if len(args) != 2:
        await message.reply_text('Usage: /mirror <url>')
        return
    file_url = args[1]
    try:
        # Generate direct link if possible
        direct_link = direct_link_generator(file_url)
        if direct_link:
            file_url = direct_link

        # Get the filename from response
        file_name = await get_filename_from_response(file_url)
        await download_file_with_aria2(file_url, file_name)

        # Read the downloaded file into BytesIO
        with open(file_name, 'rb') as f:
            file_stream = io.BytesIO(f.read())

        total_size = len(file_stream.getbuffer())
        start_time = time.time()

        # Create a temporary message to update progress
        progress_message = await message.reply_text("Starting upload...")

        file_stream.seek(0)
        uploaded_file_id = await upload_file_to_drive(file_name, file_stream, FOLDER_ID, progress_message)
        drive_link = f'https://drive.google.com/file/d/{uploaded_file_id}/view?usp=sharing'
        response_text = f"File {file_name} telah diunggah ke Google Drive.\n📥Download Link"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📥Download Link", url=drive_link)]])
        await progress_message.edit_text(response_text, reply_markup=keyboard)
    except Exception as e:
        logger.error("Error mirroring file: %s", e)
        await message.reply_text('Failed to mirror the file.')

app.run()