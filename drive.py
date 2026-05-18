"""
Google Drive integration — read training files, save outputs
"""

import io, json, os
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/drive"]

FOLDER_NAMES = {
    "training":   "1_Damodaran_Training",
    "templates":  "2_Valuation_Templates",
    "watchlists": "3_Watchlists",
    "musaffa":    "4_Musaffa_Reports",
    "outputs":    "5_Outputs",
}

DAMODARAN_FILES = [
   "betaUSA.xls", "wacc.xls", "margin.xls",
    "pe.xls", "vebitda.xls", "fundgrEB.xls",
]


def get_drive_service(credentials_json: dict):
    creds = Credentials.from_service_account_info(credentials_json, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def get_or_create_folder(service, name, parent_id=None):
    q = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        q += f" and '{parent_id}' in parents"
    results = service.files().list(q=q, fields="files(id,name)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]
    meta = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        meta["parents"] = [parent_id]
    folder = service.files().create(body=meta, fields="id").execute()
    return folder["id"]


def ensure_folder_structure(service, root_folder_id=None):
    if root_folder_id:
        root_id = root_folder_id
    else:
        root_id = get_or_create_folder(service, "Islamic Screener")
    folder_ids = {"root": root_id}
    for key, name in FOLDER_NAMES.items():
        folder_ids[key] = get_or_create_folder(service, name, root_id)
    return folder_ids

def list_files_in_folder(service, folder_id):
    q = f"'{folder_id}' in parents and trashed=false"
    results = service.files().list(q=q, fields="files(id,name,mimeType,modifiedTime)").execute()
    return results.get("files", [])


def download_file_bytes(service, file_id):
    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buf.seek(0)
    return buf.read()


def upload_file(service, folder_id, filename, content_bytes, mime_type="application/octet-stream"):
    existing = list_files_in_folder(service, folder_id)
    existing_ids = [f["id"] for f in existing if f["name"] == filename]

    media = MediaIoBaseUpload(io.BytesIO(content_bytes), mimetype=mime_type)

    if existing_ids:
        service.files().update(
            fileId=existing_ids[0],
            media_body=media,
        ).execute()
        return existing_ids[0]
    else:
        meta = {"name": filename, "parents": [folder_id]}
        f = service.files().create(body=meta, media_body=media, fields="id").execute()
        return f["id"]


def get_damodaran_files_status(service, folder_ids):
    files = list_files_in_folder(service, folder_ids["training"])
    found = {f["name"]: f for f in files}
    status = {}
    for fname in DAMODARAN_FILES:
        if fname in found:
            status[fname] = {
                "uploaded": True,
                "modified": found[fname].get("modifiedTime", ""),
                "id": found[fname]["id"],
            }
        else:
            status[fname] = {"uploaded": False, "modified": None, "id": None}
    return status


def get_musaffa_pdfs(service, folder_ids):
    files = list_files_in_folder(service, folder_ids["musaffa"])
    return [f for f in files if f["name"].lower().endswith(".pdf")]


def get_valuation_templates(service, folder_ids):
    files = list_files_in_folder(service, folder_ids["templates"])
    return [f for f in files if f["name"].lower().endswith((".xlsx", ".xls"))]


def get_watchlist_files(service, folder_ids):
    files = list_files_in_folder(service, folder_ids["watchlists"])
    return [f for f in files if f["name"].lower().endswith(".csv")]


def save_output(service, folder_ids, filename, content_bytes):
    return upload_file(
        service, folder_ids["outputs"], filename,
        content_bytes,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def upload_to_folder(service, folder_ids, folder_key, filename, content_bytes, mime_type="application/octet-stream"):
    return upload_file(service, folder_ids[folder_key], filename, content_bytes, mime_type)
