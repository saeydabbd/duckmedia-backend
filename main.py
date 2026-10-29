import os
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

# إعدادات تخطي حماية يوتيوب وخوادم السحاب
YOUTUBE_EXTRACTOR_ARGS = {
    'youtube': {
        'player_client': ['ios', 'android', 'mweb'],
    }
}

IOS_USER_AGENT = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'

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
        'extractor_args': YOUTUBE_EXTRACTOR_ARGS,
        'http_headers': {
            'User-Agent': IOS_USER_AGENT,
            'Accept-Language': 'en-US,en;q=0.9',
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise HTTPException(status_code=400, detail="تعذر استخراج بيانات الفيديو.")

            title = info.get("title", "وسائط DuckMedia")
            cover = info.get("thumbnail", "")
            
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
        'extractor_args': YOUTUBE_EXTRACTOR_ARGS,
        'http_headers': {
            'User-Agent': IOS_USER_AGENT,
            'Accept-Language': 'en-US,en;q=0.9',
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            direct_stream_url = info.get("url")

        if not direct_stream_url:
            raise HTTPException(status_code=404, detail="تعذر جلب تيار البث.")

        async def stream_generator():
            headers = {'User-Agent': IOS_USER_AGENT}
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", direct_stream_url, headers=headers) as resp:
                    async for chunk in resp.aiter_bytes(chunk_size=1024 * 64):
                        yield chunk

        media_type = "audio/mpeg" if is_audio else "video/mp4"
        return StreamingResponse(stream_generator(), media_type=media_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
