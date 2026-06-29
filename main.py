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
        "cookiefile": "cookies.txt", 
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
            audio_formats = []
            
            for f in info.get("formats", []):
                # Ambil URL stream langsung, atau fallback ke manifest url jika direct link tidak ada
                download_url = f.get("url") or f.get("manifest_url")
                if not download_url:
                    continue
                
                # Cek tipe codec untuk memisahkan Video dan Audio
                vcodec = f.get("vcodec", "none")
                acodec = f.get("acodec", "none")
                
                # 1. Jika mengandung video (Bisa video+audio atau video saja/adaptive)
                if vcodec != "none" and vcodec is not None:
                    formats.append({
                        "quality": f.get("format_note") or f.get("resolution") or "unknown",
                        "height": f.get("height", 0) or 0,
                        "url": download_url,
                        "ext": f.get("ext", "mp4"),
                        "filesize": f.get("filesize") or f.get("filesize_approx") or 0
                    })
                
                # 2. Jika murni audio saja
                elif acodec != "none" and acodec is not None and (vcodec == "none" or vcodec is None):
                    audio_formats.append({
                        "quality": f.get("format_note") or f.get("abr", "audio"),
                        "url": download_url,
                        "ext": f.get("ext", "mp3"),
                        "filesize": f.get("filesize") or f.get("filesize_approx") or 0
                    })

            # Jika setelah dilonggarkan masih kosong, beri fallback manual dari entry utama video
            if not formats and info.get("url"):
                formats.append({
                    "quality": "Default",
                    "height": 360,
                    "url": info.get("url"),
                    "ext": "mp4",
                    "filesize": 0
                })

            return jsonify({
                "title": info.get("title", "YouTube Video"),
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
