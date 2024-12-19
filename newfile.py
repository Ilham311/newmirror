import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from google.oauth2.service_account import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import requests
import io
import pickle
import os
import re

API_ID = 961780
API_HASH = "bbbfa43f067e1e8e2fb41f334d32a6a7"
BOT_TOKEN = "7692879400:AAHkBRffGCdH6YQzxYqvIHZYn4iCrj3I75s"
FOLDER_ID = '14kWVa9dUOJr7yraefAkTs5nfzV3vpGbj'

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive']

def authenticate():
    creds = None
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

def check_duplicate(file_name, folder_id):
    creds = authenticate()
    service = build('drive', 'v3', credentials=creds)
    query = f"'{folder_id}' in parents and name='{file_name}' and trashed=false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    return results.get('files', [])

def upload_file_to_drive(file_name, file_stream, folder_id):
    creds = authenticate()
    service = build('drive', 'v3', credentials=creds)
    media = MediaIoBaseUpload(file_stream, mimetype='application/octet-stream', resumable=True)
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    uploaded_file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    return uploaded_file.get('id')

def copy_file_to_folder(file_id, folder_id):
    creds = authenticate()
    service = build('drive', 'v3', credentials=creds)
    original_file = service.files().get(fileId=file_id, fields='name, size').execute()
    original_file_name = original_file.get('name')
    original_file_size = original_file.get('size')
    duplicates = check_duplicate(original_file_name, folder_id)
    if duplicates:
        return duplicates[0]['id'], original_file_name, original_file_size, True
    file_metadata = {'name': original_file_name, 'parents': [folder_id]}
    copied_file = service.files().copy(fileId=file_id, body=file_metadata).execute()
    return copied_file.get('id'), original_file_name, original_file_size, False

if os.path.exists("my_bot.session"):
    os.remove("my_bot.session")

app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("clone"))
def clone(client, message):
    user = message.from_user
    logger.info("User %s started cloning", user.first_name)
    args = message.text.split()
    if len(args) != 2:
        message.reply_text('Usage: /clone <file_id_or_url>')
        return
    file_id_or_url = args[1]
    file_id = extract_file_id(file_id_or_url)
    try:
        copied_file_id, file_name, file_size, is_duplicate = copy_file_to_folder(file_id, FOLDER_ID)
        file_size_gb = int(file_size) / (1024 * 1024 * 1024)
        drive_link = f'https://drive.google.com/file/d/{copied_file_id}/view?usp=sharing'
        response = (
            f"Contoh Title: {file_name}\n"
            f"Size: {file_size_gb:.2f} GB\n"
            + ("Sudah tersedia.\n" if is_duplicate else "")
        )
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📥Download Link", url=drive_link)]])
        message.reply_text(response, reply_markup=keyboard)
    except Exception as e:
        logger.error("Error cloning file: %s", e)
        message.reply_text('Failed to clone the file.')

@app.on_message(filters.command("mirror"))
def mirror(client, message):
    user = message.from_user
    logger.info("User %s started mirroring", user.first_name)
    args = message.text.split()
    if len(args) != 2:
        message.reply_text('Usage: /mirror <url>')
        return
    file_url = args[1]
    try:
        response = requests.get(file_url, stream=True)
        file_name = file_url.split('/')[-1]
        file_stream = io.BytesIO()
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                file_stream.write(chunk)
        file_stream.seek(0)
        uploaded_file_id = upload_file_to_drive(file_name, file_stream, FOLDER_ID)
        drive_link = f'https://drive.google.com/file/d/{uploaded_file_id}/view?usp=sharing'
        response_text = f"File {file_name} telah diunggah ke Google Drive.\n📥Download Link"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📥Download Link", url=drive_link)]])
        message.reply_text(response_text, reply_markup=keyboard)
    except Exception as e:
        logger.error("Error mirroring file: %s", e)
        message.reply_text('Failed to mirror the file.')

app.run()