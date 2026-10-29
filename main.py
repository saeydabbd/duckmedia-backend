import os
import re
import time
import urllib.parse
import yt_dlp
from fastapi import FastAPI, HTTPException, Query, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
import httpx

app = FastAPI(title="DuckMedia Downloader Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
COOKIE_PATH = "cookies.txt" if os.path.exists("cookies.txt") else None

@app.get("/")
def home():
    return {
        "status": "online",
        "message": "DuckMedia Universal Engine is Running 🦆",
        "cookies": "مفعّل ✅" if COOKIE_PATH else "غير موجود ⚠️"
    }

# --- محرك فيسبوك المعتمد ---
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

# --- محرك إنستغرام المعتمد ---
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

# --- نقطة فحص واستخراج بيانات المقطع ---
@app.get("/api/resolve")
async def resolve_media(request: Request, url: str = Query(...), format: str = Query("video")):
    is_audio = (format == "audio")
    target_url = url.strip()

    is_yt = any(d in target_url.lower() for d in ["youtube.com", "youtu.be"])
    is_fb = any(d in target_url.lower() for d in ["facebook.com", "fb.watch"])
    is_ig = "instagram.com" in target_url.lower()

    if is_yt:
        if "/shorts/" in target_url:
            s_match = re.search(r'shorts/([a-zA-Z0-9_-]+)', target_url)
            if s_match:
                target_url = f"https://www.youtube.com/watch?v={s_match.group(1)}"

        # فحص عام لليوتيوب بدون قيود صيغة تسبب فشل الطلب
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'noplaylist': True,
            'cookiefile': COOKIE_PATH,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'web']
                }
            },
            'http_headers': {'User-Agent': USER_AGENT}
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(target_url, download=False)
                if info:
                    title = info.get("title", "وسائط YouTube")
                    cover = info.get("thumbnail", "")
                    base_url = str(request.base_url).rstrip("/")
                    encoded_url = urllib.parse.quote(target_url)
                    stream_url = f"{base_url}/api/stream?url={encoded_url}&format={format}"
                    return {
                        "success": True,
                        "title": title,
                        "cover": cover,
                        "downloadUrl": stream_url,
                        "type": "audio" if is_audio else "video"
                    }
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"خطأ يوتيوب: {str(e)}")

    # معالجة فيسبوك وإنستغرام
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

# --- نقطة التنزيل والبث الشاملة لليوتيوب ---
@app.get("/api/stream")
async def stream_media(background_tasks: BackgroundTasks, url: str = Query(...), format: str = Query("video")):
    is_audio = (format == "audio")
    
    # 1. البحث أولاً عن مسار مباشر قابل للبث الفوري
    ydl_opts_info = {
        'quiet': True,
        'skip_download': True,
        'cookiefile': COOKIE_PATH,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios']
            }
        },
        'http_headers': {'User-Agent': USER_AGENT}
    }
    
    info = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        pass

    direct_stream_url = None
    if info:
        formats = info.get("formats", [])
        if is_audio:
            # استخراج أفضل مسار صوتي
            audio_formats = [f for f in formats if f.get("acodec") != "none" and f.get("url")]
            if audio_formats:
                audio_formats.sort(key=lambda x: x.get("abr") or x.get("tbr") or 0, reverse=True)
                direct_stream_url = audio_formats[0].get("url")
        else:
            # استخراج مسار يجمع الصوت والصورة معاً
            prog_formats = [
                f for f in formats 
                if f.get("acodec") != "none" and f.get("vcodec") != "none" and f.get("url") and "m3u8" not in f.get("url", "")
            ]
            if prog_formats:
                prog_formats.sort(key=lambda x: x.get("height") or x.get("tbr") or 0, reverse=True)
                direct_stream_url = prog_formats[0].get("url")

    # في حال وجد مسار مباشر، يتم البث فوراً عبر السيرفر
    if direct_stream_url:
        async def stream_generator():
            headers = {'User-Agent': USER_AGENT}
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", direct_stream_url, headers=headers) as resp:
                    async for chunk in resp.aiter_bytes(chunk_size=1024 * 64):
                        yield chunk

        media_type = "audio/mpeg" if is_audio else "video/mp4"
        return StreamingResponse(stream_generator(), media_type=media_type)

    # 2. في حال كانت المسارات مفصولة تماماً (كما في الفيديوهات عالية الدقة):
    # يقوم السيرفر بدمج الصوت والصورة تلقائياً عبر FFmpeg إلى ملف نظيف
    video_id = re.sub(r'[^a-zA-Z0-9_-]', '', info.get("id", "media") if info else f"media_{int(time.time())}")
    ext = "mp3" if is_audio else "mp4"
    out_file = f"/tmp/{video_id}_{int(time.time())}.{ext}"

    ydl_download_opts = {
        'quiet': True,
        'no_warnings': True,
        'cookiefile': COOKIE_PATH,
        'outtmpl': out_file,
        'http_headers': {'User-Agent': USER_AGENT},
    }

    if is_audio:
        ydl_download_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }],
        })
    else:
        ydl_download_opts.update({
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
            'merge_output_format': 'mp4',
        })

    try:
        with yt_dlp.YoutubeDL(ydl_download_opts) as ydl:
            ydl.download([url])

        actual_file = out_file
        if not os.path.exists(actual_file):
            matches = [os.path.join("/tmp", f) for f in os.listdir("/tmp") if f.startswith(f"{video_id}_")]
            if matches:
                actual_file = matches[0]

        if os.path.exists(actual_file):
            def cleanup():
                try:
                    if os.path.exists(actual_file):
                        os.remove(actual_file)
                except Exception:
                    pass
            background_tasks.add_task(cleanup)

            media_type = "audio/mpeg" if is_audio else "video/mp4"
            return FileResponse(actual_file, media_type=media_type, filename=f"duck_{video_id}.{ext}")
    except Exception as dl_err:
        raise HTTPException(status_code=500, detail=f"فشل دمج وتجهيز الفيديو: {str(dl_err)}")

    raise HTTPException(status_code=404, detail="تعذر استخراج أو تجهيز ملف الوسائط.")
