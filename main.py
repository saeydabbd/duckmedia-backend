import os
import re
import time
import urllib.parse
import yt_dlp
from fastapi import FastAPI, HTTPException, Query, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import httpx

app = FastAPI(title="DuckMedia Downloader Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
COOKIE_PATH = "cookies.txt" if os.path.exists("cookies.txt") else None

@app.get("/")
def home():
    return {
        "status": "online",
        "message": "DuckMedia Universal Engine is Running 🦆",
        "cookies": "مفعّل ✅" if COOKIE_PATH else "غير موجود ⚠️"
    }

# --- محرك فيسبوك المعتمد الناجح ---
async def fallback_facebook(url: str):
    endpoints = [
        f"https://api.dorratz.com/fb?url={urllib.parse.quote(url)}",
        f"https://api.tiklydown.eu.org/api/download?url={urllib.parse.quote(url)}",
        f"https://api.siputzx.my.id/api/d/facebook?url={urllib.parse.quote(url)}"
    ]
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for ep in endpoints:
            try:
                res = await client.get(ep, headers={"User-Agent": USER_AGENT})
                data = res.json()
                if "data" in data and isinstance(data["data"], dict):
                    v = data["data"].get("video", {})
                    link = v.get("hd") or v.get("sd") or data["data"].get("url")
                    if link:
                        return {"title": data["data"].get("title", "ريلز فيسبوك"), "url": link}
                if "video" in data and data["video"].get("noWatermark"):
                    return {"title": data.get("title", "ريلز فيسبوك"), "url": data["video"]["noWatermark"]}
                if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
                    hd = next((item for item in data["data"] if "hd" in str(item.get("quality", "")).lower()), data["data"][0])
                    if hd.get("url"):
                        return {"title": "ريلز فيسبوك", "url": hd["url"]}
            except Exception:
                continue
    return None

# --- محرك إنستغرام المعتمد الناجح ---
async def fallback_instagram(url: str):
    endpoints = [
        f"https://api.dorratz.com/ig?url={urllib.parse.quote(url)}",
        f"https://api.tiklydown.eu.org/api/download?url={urllib.parse.quote(url)}",
        f"https://api.siputzx.my.id/api/d/ig?url={urllib.parse.quote(url)}"
    ]
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for ep in endpoints:
            try:
                res = await client.get(ep, headers={"User-Agent": USER_AGENT})
                data = res.json()
                if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
                    link = data["data"][0].get("url") or data["data"][0].get("download_url")
                    if link:
                        return {"title": "ريلز إنستغرام", "url": link}
                if "video" in data and data["video"].get("noWatermark"):
                    return {"title": data.get("title", "ريلز إنستغرام"), "url": data["video"]["noWatermark"]}
            except Exception:
                continue
    return None

# --- فحص المقطع واستخراج معلوماته ---
@app.get("/api/resolve")
async def resolve_media(request: Request, url: str = Query(...), format: str = Query("video")):
    is_audio = (format == "audio")
    target_url = url.strip()

    is_yt = any(d in target_url.lower() for d in ["youtube.com", "youtu.be"])
    is_fb = any(d in target_url.lower() for d in ["facebook.com", "fb.watch"])
    is_ig = "instagram.com" in target_url.lower()

    # مسار يوتيوب (Shorts وفيديوهات عادية)
    if is_yt:
        if "/shorts/" in target_url:
            s_match = re.search(r'shorts/([a-zA-Z0-9_-]+)', target_url)
            if s_match:
                target_url = f"https://www.youtube.com/watch?v={s_match.group(1)}"

        # استخراج معلومات الفيديو دون تقييد الصيغة لتفادي أي خطأ
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'noplaylist': True,
            'cookiefile': COOKIE_PATH,
            'http_headers': {'User-Agent': USER_AGENT}
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(target_url, download=False)
                if not info:
                    raise Exception("تعذر قراءة بيانات المقطع من YouTube.")

                title = info.get("title", "وسائط YouTube")
                cover = info.get("thumbnail", "")
                base_url = str(request.base_url).rstrip("/")
                encoded_url = urllib.parse.quote(target_url)
                download_url = f"{base_url}/api/stream?url={encoded_url}&format={format}"

                return {
                    "success": True,
                    "title": title,
                    "cover": cover,
                    "downloadUrl": download_url,
                    "type": "audio" if is_audio else "video"
                }
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"خطأ يوتيوب: {str(e)}")

    # مسار فيسبوك وإنستغرام
    if "facebook.com/reel/" in target_url:
        reel_id_match = re.search(r'reel/(\d+)', target_url)
        if reel_id_match:
            target_url = f"https://www.facebook.com/watch/?v={reel_id_match.group(1)}"

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
        'format': 'bestaudio/best' if is_audio else 'best[ext=mp4]/best',
        'http_headers': {'User-Agent': USER_AGENT}
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target_url, download=False)
            if info and info.get("url"):
                return {
                    "success": True,
                    "title": info.get("title", "وسائط DuckMedia"),
                    "cover": info.get("thumbnail", ""),
                    "downloadUrl": info.get("url"),
                    "type": "audio" if is_audio else "video"
                }
    except Exception:
        pass

    fallback_res = None
    if is_fb:
        fallback_res = await fallback_facebook(target_url)
    elif is_ig:
        fallback_res = await fallback_instagram(target_url)

    if fallback_res and fallback_res.get("url"):
        return {
            "success": True,
            "title": fallback_res.get("title", "وسائط DuckMedia"),
            "cover": "",
            "downloadUrl": fallback_res["url"],
            "type": "audio" if is_audio else "video"
        }

    raise HTTPException(status_code=400, detail="تعذر معالجة هذا المقطع. تأكد من أن الرابط عام وصحيح.")

# --- محرك دمج وبث وسائط يوتيوب عبر FFmpeg ---
@app.get("/api/stream")
def stream_media(background_tasks: BackgroundTasks, url: str = Query(...), format: str = Query("video")):
    is_audio = (format == "audio")
    file_id = f"duck_{int(time.time())}_{os.urandom(4).hex()}"
    out_tmpl = f"/tmp/{file_id}.%(ext)s"

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'cookiefile': COOKIE_PATH,
        'outtmpl': out_tmpl,
        'noplaylist': True,
        'http_headers': {'User-Agent': USER_AGENT}
    }

    if is_audio:
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }]
        })
    else:
        ydl_opts.update({
            'format': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best',
            'merge_output_format': 'mp4'
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"فشل معالجة المقطع عبر السيرفر: {str(e)}")

    expected_ext = "mp3" if is_audio else "mp4"
    target_file = f"/tmp/{file_id}.{expected_ext}"

    if not os.path.exists(target_file):
        matches = [os.path.join("/tmp", f) for f in os.listdir("/tmp") if f.startswith(file_id)]
        if matches:
            target_file = matches[0]

    if not os.path.exists(target_file):
        raise HTTPException(status_code=404, detail="تعذر العثور على الملف المعالج.")

    def cleanup():
        try:
            if os.path.exists(target_file):
                os.remove(target_file)
        except Exception:
            pass

    background_tasks.add_task(cleanup)

    media_type = "audio/mpeg" if is_audio else "video/mp4"
    return FileResponse(
        target_file,
        media_type=media_type,
        filename=f"duckmedia_{file_id}.{expected_ext}"
    )
