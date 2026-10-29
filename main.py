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

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
COOKIE_PATH = "cookies.txt" if os.path.exists("cookies.txt") else None

@app.get("/")
def home():
    return {
        "status": "online",
        "message": "DuckMedia Universal Engine is Running 🦆",
        "cookies": "مفعّل ✅" if COOKIE_PATH else "غير موجود ⚠️"
    }

def get_youtube_id(url: str):
    patterns = [
        r'(?:v=|\/vi\/|youtu\.be\/|\/embed\/|\/shorts\/)([a-zA-Z0-9_-]{11})',
        r'(?:watch\?.*v=)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$'
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

# --- محرك يوتيوب 1: Y2Mate (سريع ويدمج الصوت والصورة مسبقاً) ---
async def resolve_y2mate(url: str, is_audio: bool):
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.y2mate.com/",
        "Origin": "https://www.y2mate.com",
        "X-Requested-With": "XMLHttpRequest"
    }
    async with httpx.AsyncClient(timeout=14.0, headers=headers, follow_redirects=True) as client:
        res = await client.post(
            "https://www.y2mate.com/mates/analyzeV2/ajax",
            data={"k_query": url, "k_page": "home", "hl": "en", "q_auto": "0"}
        )
        data = res.json()
        if data.get("status") != "success":
            return None

        vid = data.get("vid")
        title = data.get("title", "فيديو YouTube")
        links = data.get("links", {})
        k = None

        if is_audio:
            mp3_links = links.get("mp3", {})
            for key in ["mp3128", "auto", "mp3"]:
                if key in mp3_links:
                    k = mp3_links[key].get("k")
                    break
            if not k and mp3_links:
                k = list(mp3_links.values())[0].get("k")
        else:
            mp4_links = links.get("mp4", {})
            for key in ["auto", "136", "18", "22", "135", "134"]:
                if key in mp4_links:
                    k = mp4_links[key].get("k")
                    break
            if not k and mp4_links:
                k = list(mp4_links.values())[0].get("k")

        if not k:
            return None

        conv_res = await client.post(
            "https://www.y2mate.com/mates/convertV2/index",
            data={"vid": vid, "k": k}
        )
        c_data = conv_res.json()
        if c_data.get("status") == "success" and c_data.get("dlink"):
            return {
                "title": title,
                "cover": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
                "url": c_data["dlink"]
            }
    return None

# --- محرك يوتيوب 2: Vevioz ---
async def resolve_vevioz(vid: str, is_audio: bool):
    endpoint = f"https://api.vevioz.com/api/button/{'mp3' if is_audio else 'videos'}/{vid}"
    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(timeout=10.0, headers=headers, follow_redirects=True) as client:
        res = await client.get(endpoint)
        data = res.json()
        if data.get("url"):
            return {
                "title": data.get("title", "وسائط YouTube"),
                "cover": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
                "url": data["url"]
            }
    return None

# --- محرك يوتيوب 3: الخوادم البديلة المشتركة ---
async def resolve_external_yt(url: str, is_audio: bool, vid: str):
    encoded = urllib.parse.quote(url)
    endpoints = [
        f"https://api.dorratz.com/{'ytmp3' if is_audio else 'ytmp4'}?url={encoded}",
        f"https://api.siputzx.my.id/api/d/{'ytmp3' if is_audio else 'ytmp4'}?url={encoded}",
        f"https://bk9.fun/download/{'youtube-audio' if is_audio else 'youtube'}?url={encoded}"
    ]
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for ep in endpoints:
            try:
                res = await client.get(ep, headers={"User-Agent": USER_AGENT})
                data = res.json()
                if data.get("status") and "data" in data and isinstance(data["data"], dict):
                    link = data["data"].get("mp3" if is_audio else "mp4") or data["data"].get("dl")
                    if link:
                        return {
                            "title": data["data"].get("title", "وسائط YouTube"),
                            "cover": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
                            "url": link
                        }
                if data.get("status") and "BK9" in data:
                    bk = data["BK9"]
                    link = bk.get("downloadUrl") or bk.get("url")
                    if link:
                        return {
                            "title": bk.get("title", "وسائط YouTube"),
                            "cover": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
                            "url": link
                        }
            except Exception:
                continue
    return None

# --- محرك يوتيوب 4: yt-dlp عبر نمط أجهزة التلفاز (TV Embedded) ---
async def resolve_ytdlp_direct(url: str, is_audio: bool, vid: str):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
        'cookiefile': COOKIE_PATH,
        'extractor_args': {
            'youtube': {
                'player_client': ['tv_embedded', 'tv', 'android_vr']
            }
        },
        'http_headers': {'User-Agent': USER_AGENT}
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None
            formats = info.get("formats", [])
            if is_audio:
                audio_formats = [f for f in formats if f.get("acodec") != "none" and f.get("url")]
                if audio_formats:
                    audio_formats.sort(key=lambda x: x.get("abr") or x.get("tbr") or 0, reverse=True)
                    return {
                        "title": info.get("title", "صوت YouTube"),
                        "cover": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
                        "url": audio_formats[0]["url"]
                    }
            else:
                prog = [f for f in formats if f.get("acodec") != "none" and f.get("vcodec") != "none" and f.get("url")]
                if prog:
                    prog.sort(key=lambda x: x.get("height") or x.get("tbr") or 0, reverse=True)
                    return {
                        "title": info.get("title", "فيديو YouTube"),
                        "cover": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
                        "url": prog[0]["url"]
                    }
                valid = [f for f in formats if f.get("url")]
                if valid:
                    valid.sort(key=lambda x: x.get("height") or x.get("tbr") or 0, reverse=True)
                    return {
                        "title": info.get("title", "فيديو YouTube"),
                        "cover": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
                        "url": valid[0]["url"]
                    }
    except Exception:
        pass
    return None

# تجميع محركات يوتيوب مع التحويل التلقائي
async def resolve_youtube(url: str, is_audio: bool):
    vid = get_youtube_id(url)
    if not vid:
        return None
    normalized_url = f"https://www.youtube.com/watch?v={vid}"

    # 1. Y2Mate
    try:
        res = await resolve_y2mate(normalized_url, is_audio)
        if res and res.get("url"):
            return res
    except Exception:
        pass

    # 2. Vevioz
    try:
        res = await resolve_vevioz(vid, is_audio)
        if res and res.get("url"):
            return res
    except Exception:
        pass

    # 3. External APIs
    try:
        res = await resolve_external_yt(normalized_url, is_audio, vid)
        if res and res.get("url"):
            return res
    except Exception:
        pass

    # 4. yt-dlp (TV Mode)
    try:
        res = await resolve_ytdlp_direct(normalized_url, is_audio, vid)
        if res and res.get("url"):
            return res
    except Exception:
        pass

    return None

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

# --- النقطة الرئيسية لتجهيز روابط التنزيل ---
@app.get("/api/resolve")
async def resolve_media(request: Request, url: str = Query(...), format: str = Query("video")):
    is_audio = (format == "audio")
    target_url = url.strip()

    is_yt = any(d in target_url.lower() for d in ["youtube.com", "youtu.be"])
    is_fb = any(d in target_url.lower() for d in ["facebook.com", "fb.watch"])
    is_ig = "instagram.com" in target_url.lower()

    # مسار يوتيوب عبر المحركات المتتالية
    if is_yt:
        yt_res = await resolve_youtube(target_url, is_audio)
        if yt_res and yt_res.get("url"):
            return {
                "success": True,
                "title": yt_res.get("title", "وسائط YouTube"),
                "cover": yt_res.get("cover", ""),
                "downloadUrl": yt_res["url"],
                "type": "audio" if is_audio else "video"
            }
        raise HTTPException(status_code=400, detail="تعذر استخراج فيديو YouTube حالياً. يرجى تجربة مقطع آخر.")

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
