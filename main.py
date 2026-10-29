import os
import re
import urllib.parse
import yt_dlp
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
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

@app.get("/")
def home():
    return {"status": "online", "message": "DuckMedia Universal Engine is Running 🦆"}

# محرك احتياطي لفيسبوك
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
                # فحص استجابة dorratz
                if "data" in data and isinstance(data["data"], dict):
                    v = data["data"].get("video", {})
                    link = v.get("hd") or v.get("sd") or data["data"].get("url")
                    if link:
                        return {"title": data["data"].get("title", "ريلز فيسبوك"), "url": link}
                # فحص استجابة tiklydown
                if "video" in data and data["video"].get("noWatermark"):
                    return {"title": data.get("title", "ريلز فيسبوك"), "url": data["video"]["noWatermark"]}
                # فحص استجابة siputzx
                if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
                    hd = next((item for item in data["data"] if "hd" in str(item.get("quality", "")).lower()), data["data"][0])
                    if hd.get("url"):
                        return {"title": "ريلز فيسبوك", "url": hd["url"]}
            except Exception:
                continue
    return None

# محرك احتياطي لإنستغرام
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

# محرك احتياطي ليوتيوب لتجاوز حظر البوت
async def fallback_youtube(url: str, is_audio: bool):
    cobalt_servers = [
        "https://api.cobalt.tools/",
        "https://cobalt.api.scmn.me/"
    ]
    async with httpx.AsyncClient(timeout=12.0) as client:
        for srv in cobalt_servers:
            try:
                res = await client.post(
                    srv,
                    headers={"Accept": "application/json", "Content-Type": "application/json"},
                    json={
                        "url": url,
                        "downloadMode": "audio" if is_audio else "auto",
                        "audioFormat": "mp3",
                        "audioBitrate": "320",
                        "videoQuality": "720"
                    }
                )
                data = res.json()
                if data and "url" in data:
                    return {"title": "صوت YouTube MP3" if is_audio else "فيديو YouTube", "url": data["url"]}
            except Exception:
                continue

    # بديل Invidious المباشر
    yt_match = re.search(r'(?:youtu\.be\/|youtube\.com\/(?:embed\/|v\/|watch\?v=|watch\?.+&v=|shorts\/|live\/))([\w-]{11})', url)
    if yt_match:
        vid_id = yt_match.group(1)
        mirrors = ["https://inv.nadeko.net/api/v1/videos/", "https://invidious.nerdvpn.de/api/v1/videos/"]
        async with httpx.AsyncClient(timeout=10.0) as client:
            for m in mirrors:
                try:
                    res = await client.get(f"{m}{vid_id}")
                    data = res.json()
                    if is_audio and "adaptiveFormats" in data:
                        auds = [f for f in data["adaptiveFormats"] if f.get("type", "").startswith("audio/")]
                        auds.sort(key=lambda x: int(x.get("bitrate", 0)), reverse=True)
                        if auds and auds[0].get("url"):
                            return {"title": data.get("title", "صوت YouTube MP3"), "url": auds[0]["url"]}
                    elif not is_audio and "formatStreams" in data:
                        stream = next((f for f in data["formatStreams"] if f.get("qualityLabel") == "720p"), data["formatStreams"][0] if data["formatStreams"] else None)
                        if stream and stream.get("url"):
                            return {"title": data.get("title", "فيديو YouTube"), "url": stream["url"]}
                except Exception:
                    continue
    return None

@app.get("/api/resolve")
async def resolve_media(request: Request, url: str = Query(...), format: str = Query("video")):
    is_audio = (format == "audio")
    target_url = url.strip()

    # تحويل رابط فيسبوك ريلز إلى مسار متوافق
    if "facebook.com/reel/" in target_url:
        reel_id_match = re.search(r'reel/(\d+)', target_url)
        if reel_id_match:
            target_url = f"https://www.facebook.com/watch/?v={reel_id_match.group(1)}"

    is_yt = any(d in target_url.lower() for d in ["youtube.com", "youtu.be"])
    is_fb = any(d in target_url.lower() for d in ["facebook.com", "fb.watch"])
    is_ig = "instagram.com" in target_url.lower()

    # 1. محاولة الاستخراج عبر yt-dlp الأساسي
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
            if info:
                title = info.get("title", "وسائط DuckMedia")
                cover = info.get("thumbnail", "")
                download_url = info.get("url")

                # توجيه يوتيوب للبث الداخلي إذا وجد
                base_url = str(request.base_url).rstrip("/")
                if is_yt:
                    encoded_url = urllib.parse.quote(target_url)
                    download_url = f"{base_url}/api/stream?url={encoded_url}&format={format}"

                if download_url:
                    return {
                        "success": True,
                        "title": title,
                        "cover": cover,
                        "downloadUrl": download_url,
                        "type": "audio" if is_audio else "video"
                    }
    except Exception:
        pass  # عند حدوث أي خطأ في yt-dlp، ننتقل فوراً للمحركات البديلة الذكية

    # 2. المحركات البديلة عند فشل yt-dlp
    fallback_res = None
    if is_fb:
        fallback_res = await fallback_facebook(target_url)
    elif is_ig:
        fallback_res = await fallback_instagram(target_url)
    elif is_yt:
        fallback_res = await fallback_youtube(target_url, is_audio)

    if fallback_res and fallback_res.get("url"):
        return {
            "success": True,
            "title": fallback_res.get("title", "وسائط DuckMedia"),
            "cover": "",
            "downloadUrl": fallback_res["url"],
            "type": "audio" if is_audio else "video"
        }

    raise HTTPException(status_code=400, detail="تعذر معالجة هذا المقطع. تأكد من أن المقطع عام (Public) وليس خاصاً.")

@app.get("/api/stream")
async def stream_media(url: str = Query(...), format: str = Query("video")):
    is_audio = (format == "audio")
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'format': 'bestaudio/best' if is_audio else 'best[ext=mp4]/best',
        'http_headers': {'User-Agent': USER_AGENT}
    }

    direct_stream_url = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            direct_stream_url = info.get("url")
    except Exception:
        pass

    if not direct_stream_url:
        fb_res = await fallback_youtube(url, is_audio)
        if fb_res:
            direct_stream_url = fb_res.get("url")

    if not direct_stream_url:
        raise HTTPException(status_code=404, detail="تعذر سحب تيار البث.")

    async def stream_generator():
        headers = {'User-Agent': USER_AGENT}
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("GET", direct_stream_url, headers=headers) as resp:
                async for chunk in resp.aiter_bytes(chunk_size=1024 * 64):
                    yield chunk

    media_type = "audio/mpeg" if is_audio else "video/mp4"
    return StreamingResponse(stream_generator(), media_type=media_type)
