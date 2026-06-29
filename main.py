from flask import Flask, request, jsonify
import yt_dlp
import os

app = Flask(__name__)

@app.route("/info", methods=["GET"])
def info():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "url required"}), 400

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        # 1. MEMBACA FILE COOKIES (Solusi Mutlak Bypass Bot YouTube)
        "cookiefile": "cookies.txt", 
        
        # 2. EKSTRA PENYAMARAN (Meniru client resmi iOS dan Android)
        "extractor_args": {
            "youtube": {
                "player_client": ["ios", "android"],
            }
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            formats = []
            for f in info.get("formats", []):
                if f.get("url") and f.get("vcodec") != "none":
                    formats.append({
                        "quality": f.get("format_note", "unknown"),
                        "height": f.get("height", 0),
                        "url": f.get("url"),
                        "ext": f.get("ext", "mp4"),
                        "filesize": f.get("filesize", 0)
                    })

            audio_formats = []
            for f in info.get("formats", []):
                if f.get("url") and f.get("vcodec") == "none" and f.get("acodec") != "none":
                    audio_formats.append({
                        "quality": f.get("format_note", "audio"),
                        "url": f.get("url"),
                        "ext": f.get("ext", "mp3"),
                        "filesize": f.get("filesize", 0)
                    })

            return jsonify({
                "title": info.get("title", ""),
                "thumbnail": info.get("thumbnail", ""),
                "duration": info.get("duration", 0),
                "formats": formats,
                "audio_formats": audio_formats
            })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
