import os
import re
import urllib.parse
import yt_dlp
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
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

# --- محرك يوتيوب المتخصص (تجاوز حظر Datacenter IP) ---
async def resolve_youtube(url: str, is_audio: bool):
    # تطبيع الرابط لضمان توافقه التام مع محركات الفحص (Shorts و youtu.be)
    target_url = url
    if "/shorts/" in target_url:
        s_match = re.search(r'shorts/([a-zA-Z0-9_-]+)', target_url)
        if s_match:
            target_url = f"https://www.youtube.com/watch?v={s_match.group(1)}"
    elif "youtu.be/" in target_url:
        y_match = re.search(r'youtu\.be/([a-zA-Z0-9_-]+)', target_url)
        if y_match:
            target_url = f"https://www.youtube.com/watch?v={y_match.group(1)}"

    encoded = urllib.parse.quote(target_url)

    # المحرك 1: Dorratz السريع
    try:
        ep = f"https://api.dorratz.com/ytmp3?url={encoded}" if is_audio else f"https://api.dorratz.com/ytmp4?url={encoded}"
        async with httpx.AsyncClient(timeout=14.0, follow_redirects=True) as client:
            res = await client.get(ep, headers={"User-Agent": USER_AGENT})
            data = res.json()
            if data.get("status") and "data" in data:
                media_link = data["data"].get("mp3") if is_audio else data["data"].get("mp4")
                if media_link:
                    return {
                        "title": data["data"].get("title", "صوت YouTube MP3" if is_audio else "فيديو YouTube"),
                        "cover": data["data"].get("thumbnail", ""),
                        "url": media_link
                    }
    except Exception:
        pass

    # المحرك 2: BK9
    try:
        ep = f"https://bk9.fun/download/youtube-audio?url={encoded}" if is_audio else f"https://bk9.fun/download/youtube?url={encoded}"
        async with httpx.AsyncClient(timeout=14.0, follow_redirects=True) as client:
            res = await client.get(ep, headers={"User-Agent": USER_AGENT})
            data = res.json()
            if data.get("status") and "BK9" in data:
                bk = data["BK9"]
                media_link = bk.get("downloadUrl") or bk.get("url")
                if media_link:
                    return {
                        "title": bk.get("title", "صوت YouTube MP3" if is_audio else "فيديو YouTube"),
                        "cover": bk.get("thumbnail", ""),
                        "url": media_link
                    }
    except Exception:
        pass

    # المحرك 3: Siputzx
    try:
        ep = f"https://api.siputzx.my.id/api/d/ytmp3?url={encoded}" if is_audio else f"https://api.siputzx.my.id/api/d/ytmp4?url={encoded}"
        async with httpx.AsyncClient(timeout=14.0, follow_redirects=True) as client:
            res = await client.get(ep, headers={"User-Agent": USER_AGENT})
            data = res.json()
            if data.get("status") and "data" in data:
                dl = data["data"].get("dl")
                if dl:
                    return {
                        "title": data["data"].get("title", "صوت YouTube MP3" if is_audio else "فيديو YouTube"),
                        "cover": data["data"].get("thumbnail", ""),
                        "url": dl
                    }
    except Exception:
        pass

    # المحرك 4: Agatz
    try:
        ep = f"https://api.agatz.xyz/api/ytmp3?url={encoded}" if is_audio else f"https://api.agatz.xyz/api/ytmp4?url={encoded}"
        async with httpx.AsyncClient(timeout=14.0, follow_redirects=True) as client:
            res = await client.get(ep, headers={"User-Agent": USER_AGENT})
            data = res.json()
            if data.get("status") == 200 and "data" in data:
                dl = data["data"].get("downloadUrl") or data["data"].get("url")
                if dl:
                    return {
                        "title": data["data"].get("title", "صوت YouTube MP3" if is_audio else "فيديو YouTube"),
                        "cover": "",
                        "url": dl
                    }
    except Exception:
        pass

    return None

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

@app.get("/api/resolve")
async def resolve_media(request: Request, url: str = Query(...), format: str = Query("video")):
    is_audio = (format == "audio")
    target_url = url.strip()

    is_yt = any(d in target_url.lower() for d in ["youtube.com", "youtu.be"])
    is_fb = any(d in target_url.lower() for d in ["facebook.com", "fb.watch"])
    is_ig = "instagram.com" in target_url.lower()

    # توجيه يوتيوب فوراً للمحرك المخصص لتجاوز حظر Datacenter IP
    if is_yt:
        yt_res = await resolve_youtube(target_url, is_audio)
        if yt_res and yt_res.get("url"):
            return {
                "success": True,
                "title": yt_res.get("title", "وسائط DuckMedia"),
                "cover": yt_res.get("cover", ""),
                "downloadUrl": yt_res["url"],
                "type": "audio" if is_audio else "video"
            }
        raise HTTPException(status_code=400, detail="تعذر استخراج فيديو يوتيوب حالياً. يرجى تجربة مقطع آخر.")

    # معالجة روابط فيسبوك وإنستغرام
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
            if info:
                title = info.get("title", "وسائط DuckMedia")
                cover = info.get("thumbnail", "")
                download_url = info.get("url")
                if download_url:
                    return {
                        "success": True,
                        "title": title,
                        "cover": cover,
                        "downloadUrl": download_url,
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
