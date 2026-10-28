from flask import Flask, render_template, request, send_file, jsonify
from pathlib import Path
import tempfile, uuid, os
import vtracer

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
JOBS = Path(tempfile.gettempdir()) / "zafrik_vectorize"
JOBS.mkdir(exist_ok=True)

@app.get("/")
def home():
    return render_template("index.html")

@app.post("/api/vectorize")
def vectorize():
    f = request.files.get("image")
    if not f or not f.filename:
        return jsonify(error="Selecciona una imagen."), 400

    mode = request.form.get("mode", "detail")
    job = uuid.uuid4().hex
    ext = Path(f.filename).suffix.lower() or ".png"
    inp = JOBS / f"{job}{ext}"
    out = JOBS / f"{job}.svg"
    f.save(inp)

    try:
        # VTracer real: spline curves + color tracing.
        if mode == "flat":
            vtracer.convert_image_to_svg_py(
                str(inp), str(out),
                colormode="color",
                hierarchical="cutout",
                mode="spline",
                filter_speckle=8,
                color_precision=4,
                layer_difference=24,
                corner_threshold=60,
                length_threshold=5.0,
                max_iterations=10,
                splice_threshold=45,
                path_precision=3
            )
        else:
            vtracer.convert_image_to_svg_py(
                str(inp), str(out),
                colormode="color",
                hierarchical="cutout",
                mode="spline",
                filter_speckle=4,
                color_precision=6,
                layer_difference=12,
                corner_threshold=60,
                length_threshold=4.0,
                max_iterations=10,
                splice_threshold=45,
                path_precision=4
            )
        return jsonify(job=job, svg=f"/api/svg/{job}")
    except Exception as e:
        return jsonify(error=f"No se pudo vectorizar: {e}"), 500
    finally:
        try: inp.unlink(missing_ok=True)
        except: pass

@app.get("/api/svg/<job>")
def svg(job):
    if not job.isalnum(): return "ID inválido", 400
    p = JOBS / f"{job}.svg"
    if not p.exists(): return "Archivo no encontrado", 404
    return send_file(p, mimetype="image/svg+xml", as_attachment=False)

@app.get("/api/download/<job>")
def download(job):
    if not job.isalnum(): return "ID inválido", 400
    p = JOBS / f"{job}.svg"
    if not p.exists(): return "Archivo no encontrado", 404
    return send_file(p, mimetype="image/svg+xml", as_attachment=True,
                     download_name="ZAFRIK_VECTORIZE_PRO.svg")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
