from flask import Flask, request, jsonify, Response
import yt_dlp
import os

app = Flask(__name__)

def build_ydl_opts(extra=None):
    opts = {
        "quiet": True,
        "no_warnings": True,
        # ✅ Tetap menggunakan cookies dari akun tumbal untuk melewati blokir bot
        "cookiefile": "cookies.txt" if os.path.exists("cookies.txt") else None,
    }
    if extra:
        opts.update(extra)
    return opts


@app.route("/info", methods=["GET"])
def info():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "url required"}), 400

    ydl_opts = build_ydl_opts({
        "extract_flat": False,
        "ignore_no_formats_error": True, 
        "format": "all", # Menampilkan semua format mentah tanpa seleksi ketat di awal
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
                        "quality": f.get("format_note") or f"{abr}kbps" if abr else "audio",
                        "url": f"/download?url={url}&abr={abr}&type=audio",
                        "ext": "mp3",
                        "filesize": f.get("filesize") or f.get("filesize_approx") or 0
                    })

            # Deduplicate resolusi video
            seen = set()
            unique_formats = []
            for f in sorted(formats, key=lambda x: x["height"], reverse=True):
                if f["height"] not in seen:
                    seen.add(f["height"])
                    unique_formats.append(f)

            # Deduplicate audio
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

            return jsonify({
                "title": info.get("title", "YouTube Video"),
                "thumbnail": info.get("thumbnail", ""),
                "duration": info.get("duration", 0),
                "formats": unique_formats,
                "audio_formats": unique_audio
            })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/download", methods=["GET"])
def download():
    """
    Endpoint yang langsung pipe video/audio ke client.
    """
    url = request.args.get("url")
    height = request.args.get("height", "0")
    abr = request.args.get("abr", "0")
    media_type = request.args.get("type", "video")

    if not url:
        return jsonify({"error": "url required"}), 400

    # Pilih format selector berdasarkan tipe dan kualitas
    if media_type == "audio":
        # ✅ Ambil format terbaik yang tersedia lalu biarkan ffmpeg mengekstrak audionya menjadi MP3
        fmt = "best"
        postprocessors = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": abr if abr and abr != "0" else "192",
        }]
        mime = "audio/mpeg"
        ext = "mp3"
    else:
        # ✅ Ambil langsung video terbaik yang sudah menyatu agar tidak memicu error ketersediaan format terpisah
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
                base = os.path.splitext(filename)
                for candidate_ext in [ext, "mp4", "webm", "mp3", "m4a"]:
                    candidate = f"{base}.{candidate_ext}"
                    if os.path.exists(candidate):
                        filename = candidate
                        break

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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, threaded=True)
