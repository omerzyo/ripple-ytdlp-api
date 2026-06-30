from flask import Flask, request, jsonify, Response
import yt_dlp
import os

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_PATH = os.path.join(BASE_DIR, "cookies.txt")

DEFAULT_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
)

def build_ydl_opts(extra=None):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "cookiefile": COOKIE_PATH if os.path.exists(COOKIE_PATH) else None,
        "user_agent": DEFAULT_UA,
        "http_headers": {
            "User-Agent": DEFAULT_UA,
            "Accept-Language": "en-US,en;q=0.9",
        },
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
        # ✅ Wajib agar TikTok lolos deteksi bot — butuh curl_cffi di requirements.txt
        "impersonate": "chrome",
    }
    if extra:
        opts.update(extra)
    return opts


def detect_platform(url: str) -> str:
    u = url.lower()
    if "tiktok.com" in u:
        return "TIKTOK"
    if "instagram.com" in u:
        return "INSTAGRAM"
    if "twitter.com" in u or "x.com" in u:
        return "TWITTER"
    if "facebook.com" in u or "fb.watch" in u:
        return "FACEBOOK"
    if "youtube.com" in u or "youtu.be" in u:
        return "YOUTUBE"
    return "UNKNOWN"


@app.route("/info", methods=["GET"])
def info():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "url required"}), 400

    # ✅ TikTok Photo Post (slide foto) tidak didukung yt-dlp — tolak lebih awal
    if "tiktok.com" in url.lower() and "/photo/" in url.lower():
        return jsonify({
            "error": "TikTok Photo Post (slide foto) belum didukung. Hanya video TikTok yang bisa diunduh.",
            "platform": "TIKTOK",
            "cookie_exists": os.path.exists(COOKIE_PATH)
        }), 400

    platform = detect_platform(url)

    ydl_opts = build_ydl_opts({
        "extract_flat": False,
        "ignore_no_formats_error": True,
        "format": "all",
        "noplaylist": True,
    })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            formats = []
            audio_formats = []

            for f in info.get("formats", []):
                vcodec = f.get("vcodec", "none")
                acodec = f.get("acodec", "none")
                height = f.get("height") or 0

                if vcodec not in (None, "none") and height > 0:
                    formats.append({
                        "quality": f.get("format_note") or f.get("resolution") or f"{height}p",
                        "height": height,
                        "url": f"/download?url={url}&height={height}&type=video",
                        "ext": "mp4",
                        "filesize": f.get("filesize") or f.get("filesize_approx") or 0
                    })

                elif acodec not in (None, "none") and vcodec in (None, "none"):
                    abr = int(f.get("abr") or 0)
                    audio_formats.append({
                        "quality": f.get("format_note") or (f"{abr}kbps" if abr else "audio"),
                        "url": f"/download?url={url}&abr={abr}&type=audio",
                        "ext": "mp3",
                        "filesize": f.get("filesize") or f.get("filesize_approx") or 0
                    })

            seen = set()
            unique_formats = []
            for f in sorted(formats, key=lambda x: x["height"], reverse=True):
                if f["height"] not in seen:
                    seen.add(f["height"])
                    unique_formats.append(f)

            seen_audio = set()
            unique_audio = []
            for f in sorted(audio_formats, key=lambda x: x["quality"], reverse=True):
                if f["quality"] not in seen_audio:
                    seen_audio.add(f["quality"])
                    unique_audio.append(f)

            if not unique_formats:
                unique_formats.append({
                    "quality": "Best",
                    "height": 720,
                    "url": f"/download?url={url}&height=0&type=video",
                    "ext": "mp4",
                    "filesize": 0
                })

            default_title = {
                "TIKTOK": "TikTok Video",
                "INSTAGRAM": "Instagram Video",
                "TWITTER": "Twitter Video",
                "FACEBOOK": "Facebook Video",
                "YOUTUBE": "YouTube Video",
            }.get(platform, "Video")

            return jsonify({
                "title": info.get("title", default_title),
                "thumbnail": info.get("thumbnail", ""),
                "duration": info.get("duration", 0),
                "formats": unique_formats,
                "audio_formats": unique_audio
            })

    except Exception as e:
        error_str = str(e)
        return jsonify({
            "error": error_str,
            "platform": platform,
            "cookie_exists": os.path.exists(COOKIE_PATH)
        }), 500


@app.route("/download", methods=["GET"])
def download():
    url = request.args.get("url")
    height = request.args.get("height", "0")
    abr = request.args.get("abr", "0")
    media_type = request.args.get("type", "video")

    if not url:
        return jsonify({"error": "url required"}), 400

    if media_type == "audio":
        fmt = "best"
        postprocessors = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": abr if abr and abr != "0" else "192",
        }]
        mime = "audio/mpeg"
        ext = "mp3"
    else:
        fmt = "best"
        postprocessors = []
        mime = "video/mp4"
        ext = "mp4"

    output_path = f"/tmp/ripple_%(id)s_{height}_{abr}.%(ext)s"

    ydl_opts = build_ydl_opts({
        "format": fmt,
        "outtmpl": output_path,
        "postprocessors": postprocessors,
        "merge_output_format": ext,
        "noplaylist": True,
    })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            if not os.path.exists(filename):
                base = os.path.splitext(filename)[0]
                for candidate_ext in [ext, "mp4", "webm", "mp3", "m4a"]:
                    candidate = f"{base}.{candidate_ext}"
                    if os.path.exists(candidate):
                        filename = candidate
                        break

            if not os.path.exists(filename) or os.path.getsize(filename) < 10240:
                if os.path.exists(filename):
                    os.remove(filename)
                return jsonify({"error": "File hasil download tidak valid atau terlalu kecil."}), 500

        def generate():
            with open(filename, "rb") as f:
                while chunk := f.read(65536):
                    yield chunk
            try:
                os.remove(filename)
            except Exception:
                pass

        title = info.get("title", "video").replace(" ", "_")[:50]
        return Response(
            generate(),
            mimetype=mime,
            headers={
                "Content-Disposition": f'attachment; filename="{title}.{ext}"',
                "Content-Type": mime,
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/cookie-status", methods=["GET"])
def cookie_status():
    if not os.path.exists(COOKIE_PATH):
        return jsonify({"status": "missing", "message": "cookies.txt tidak ditemukan"}), 404

    import time
    age_seconds = os.path.getmtime(COOKIE_PATH)
    age_days = (time.time() - age_seconds) / 86400

    return jsonify({
        "status": "exists",
        "age_days": round(age_days, 1),
        "warning": "Cookies mungkin expired, sebaiknya update" if age_days > 14 else "OK"
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, threaded=True)
