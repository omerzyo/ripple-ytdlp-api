from flask import Flask, request, jsonify, Response
import yt_dlp
import os

app = Flask(__name__)

def build_ydl_opts(extra=None):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "cookiefile": "cookies.txt" if os.path.exists("cookies.txt") else None,
        "extractor_args": {
            "youtube": {
                "player_client": ["ios", "android"],
            }
        },
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

                # ✅ Hanya ambil format yang punya KEDUA video+audio (progressive)
                # Skip adaptive stream (video-only atau audio-only dari YouTube)
                if vcodec != "none" and vcodec is not None and acodec != "none" and acodec is not None:
                    formats.append({
                        "quality": f.get("format_note") or f.get("resolution") or "unknown",
                        "height": height,
                        "url": f"/download?url={url}&height={height}&type=video",  # ✅ Pakai endpoint download
                        "ext": f.get("ext", "mp4"),
                        "filesize": f.get("filesize") or f.get("filesize_approx") or 0
                    })

                elif acodec != "none" and acodec is not None and (vcodec == "none" or vcodec is None):
                    abr = f.get("abr") or 0
                    audio_formats.append({
                        "quality": f.get("format_note") or str(abr),
                        "url": f"/download?url={url}&abr={int(abr)}&type=audio",  # ✅ Pakai endpoint download
                        "ext": "mp3",
                        "filesize": f.get("filesize") or f.get("filesize_approx") or 0
                    })

            # Deduplicate berdasarkan height
            seen_heights = set()
            unique_formats = []
            for f in sorted(formats, key=lambda x: x["height"], reverse=True):
                if f["height"] not in seen_heights:
                    seen_heights.add(f["height"])
                    unique_formats.append(f)

            # Deduplicate audio
            seen_abr = set()
            unique_audio = []
            for f in audio_formats:
                key = f["quality"]
                if key not in seen_abr:
                    seen_abr.add(key)
                    unique_audio.append(f)

            # Fallback jika tidak ada progressive format
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
    Android download dari sini — tidak perlu URL YouTube yang expire.
    """
    url = request.args.get("url")
    height = request.args.get("height", "0")
    abr = request.args.get("abr", "0")
    media_type = request.args.get("type", "video")

    if not url:
        return jsonify({"error": "url required"}), 400

    # Pilih format selector berdasarkan tipe dan kualitas
    if media_type == "audio":
        # Format audio terbaik, convert ke mp3
        if abr and abr != "0":
            fmt = f"bestaudio[abr<={abr}]/bestaudio"
        else:
            fmt = "bestaudio"
        postprocessors = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": abr if abr != "0" else "192",
        }]
        mime = "audio/mpeg"
        ext = "mp3"
    else:
        h = int(height) if height and height != "0" else 0
        if h > 0:
            # Progressive format (video+audio dalam 1 file) untuk height tertentu
            fmt = f"best[height<={h}][vcodec!=none][acodec!=none]/best[height<={h}]/best"
        else:
            fmt = "best[vcodec!=none][acodec!=none]/best"
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
            # Temukan file hasil download
            filename = ydl.prepare_filename(info)
            # Handle kasus postprocessor ganti ekstensi
            if not os.path.exists(filename):
                base = os.path.splitext(filename)[0]
                for candidate_ext in [ext, "mp4", "webm", "mp3", "m4a"]:
                    candidate = f"{base}.{candidate_ext}"
                    if os.path.exists(candidate):
                        filename = candidate
                        break

        def generate():
            with open(filename, "rb") as f:
                while chunk := f.read(65536):
                    yield chunk
            # Hapus file setelah selesai dikirim
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
