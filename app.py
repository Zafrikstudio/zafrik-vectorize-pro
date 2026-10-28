from flask import Flask, render_template, request, send_file, jsonify
from pathlib import Path
from PIL import Image
import numpy as np
from autotrace import Bitmap, VectorFormat
import tempfile, uuid, traceback

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

JOBS = Path(tempfile.gettempdir()) / "zafrik_vectorize"
JOBS.mkdir(exist_ok=True)
MAX_SIDE = 1800

@app.get("/")
def home():
    return render_template("index.html")

def prepare_image(src):
    with Image.open(src) as im:
        im = im.convert("RGBA")
        original = im.size
        scale = min(1.0, MAX_SIDE / max(im.size))
        if scale < 1:
            im = im.resize(
                (max(1, round(im.width * scale)), max(1, round(im.height * scale))),
                Image.Resampling.LANCZOS
            )
        prepared = im.size

        # AutoTrace receives RGB. Transparent pixels become white only for tracing.
        # The original upload remains untouched.
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        rgb = bg.convert("RGB")
        return original, prepared, np.asarray(rgb)

@app.post("/api/vectorize")
def vectorize():
    f = request.files.get("image")
    if not f or not f.filename:
        return jsonify(ok=False, error="Selecciona una imagen."), 400

    job = uuid.uuid4().hex
    raw = JOBS / f"{job}_raw"
    out = JOBS / f"{job}.svg"
    f.save(raw)

    try:
        original, prepared, image_array = prepare_image(raw)
        print(f"[ZAFRIK V4] original={original} prepared={prepared}", flush=True)

        bitmap = Bitmap(image_array)
        vector = bitmap.trace()
        svg_bytes = vector.encode(VectorFormat.SVG)

        if not svg_bytes or len(svg_bytes) < 100:
            raise RuntimeError("AutoTrace no generó un SVG válido.")

        out.write_bytes(svg_bytes)
        print(f"[ZAFRIK V4] OK svg_bytes={len(svg_bytes)}", flush=True)

        return jsonify(
            ok=True,
            job=job,
            svg=f"/api/svg/{job}",
            original={"width": original[0], "height": original[1]},
            processed={"width": prepared[0], "height": prepared[1]},
            engine="AutoTrace"
        )

    except Exception as e:
        print("[ZAFRIK V4] ERROR:", repr(e), flush=True)
        traceback.print_exc()
        return jsonify(
            ok=False,
            error="No se pudo vectorizar esta imagen.",
            detail=str(e)
        ), 422
    finally:
        raw.unlink(missing_ok=True)

@app.get("/api/svg/<job>")
def svg(job):
    p = JOBS / f"{job}.svg"
    if not job.isalnum() or not p.exists():
        return "Archivo no encontrado", 404
    return send_file(p, mimetype="image/svg+xml")

@app.get("/api/download/<job>")
def download(job):
    p = JOBS / f"{job}.svg"
    if not job.isalnum() or not p.exists():
        return "Archivo no encontrado", 404
    return send_file(
        p,
        mimetype="image/svg+xml",
        as_attachment=True,
        download_name="ZAFRIK_VECTORIZE_PRO.svg"
    )
