import os
import urllib.parse
import yt_dlp
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import httpx

app = FastAPI(title="DuckMedia Downloader Backend")

# السماح للاتصال من تطبيق الهاتف بدون قيود
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"status": "online", "message": "DuckMedia Backend is Running 🦆"}

@app.get("/api/resolve")
async def resolve_media(request: Request, url: str = Query(...), format: str = Query("video")):
    is_audio = (format == "audio")
    is_youtube = any(domain in url.lower() for domain in ["youtube.com", "youtu.be"])

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
        'format': 'bestaudio/best' if is_audio else 'best[ext=mp4]/best',
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise HTTPException(status_code=400, detail="تعذر استخراج بيانات الفيديو.")

            title = info.get("title", "وسائط DuckMedia")
            cover = info.get("thumbnail", "")
            
            # إذا كان الرابط من يوتيوب، نوجهه لنقطة البث بالسيرفر لتجاوز حظر IP جوجل (403)
            base_url = str(request.base_url).rstrip("/")
            if is_youtube:
                encoded_url = urllib.parse.quote(url)
                download_url = f"{base_url}/api/stream?url={encoded_url}&format={format}"
            else:
                download_url = info.get("url")

            return {
                "success": True,
                "title": title,
                "cover": cover,
                "downloadUrl": download_url,
                "type": "audio" if is_audio else "video"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stream")
async def stream_media(url: str = Query(...), format: str = Query("video")):
    is_audio = (format == "audio")
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'format': 'bestaudio/best' if is_audio else 'best[ext=mp4]/best',
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        direct_stream_url = info.get("url")

    if not direct_stream_url:
        raise HTTPException(status_code=404, detail="تعذر جلب تيار البث.")

    async def stream_generator():
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("GET", direct_stream_url, headers=headers) as resp:
                async for chunk in resp.aiter_bytes(chunk_size=1024 * 64):
                    yield chunk

    media_type = "audio/mpeg" if is_audio else "video/mp4"
    return StreamingResponse(stream_generator(), media_type=media_type)