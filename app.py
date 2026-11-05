from flask import Flask, render_template, request, send_file, jsonify
from pathlib import Path
from PIL import Image, ImageOps
import tempfile
import uuid
import traceback
import re
import shutil
import cairosvg
import vtracer

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

JOBS = Path(tempfile.gettempdir()) / "zafrik_vectorize_v5"
JOBS.mkdir(exist_ok=True)


def prepare_image(src, max_side=1800):
    image = Image.open(src)
    image = ImageOps.exif_transpose(image).convert("RGBA")
    original_size = image.size

    scale = min(1.0, max_side / max(image.size))
    if scale < 1:
        image = image.resize(
            (max(1, round(image.width * scale)),
             max(1, round(image.height * scale))),
            Image.Resampling.LANCZOS
        )
    return image, original_size


def remove_background_auto(image, tolerance=38, feather=24):
    """
    Detecta el color predominante en el borde y lo vuelve transparente.
    La coincidencia se aplica a toda la imagen para quitar también los
    huecos interiores que tengan el mismo color de fondo.
    """
    from collections import Counter

    rgba = image.convert("RGBA")
    pixels = rgba.load()
    width, height = rgba.size

    # Muestreo de los cuatro bordes; cuantizar reduce ruido de antialiasing.
    samples = []
    step = max(1, min(width, height) // 500)
    for x in range(0, width, step):
        samples.append(pixels[x, 0][:3])
        samples.append(pixels[x, height - 1][:3])
    for y in range(0, height, step):
        samples.append(pixels[0, y][:3])
        samples.append(pixels[width - 1, y][:3])

    buckets = Counter(
        (r // 16, g // 16, b // 16) for r, g, b in samples
    )
    dominant = buckets.most_common(1)[0][0]
    cluster = [
        color for color in samples
        if (color[0] // 16, color[1] // 16, color[2] // 16) == dominant
    ]
    bg = tuple(
        sum(c[i] for c in cluster) // max(1, len(cluster))
        for i in range(3)
    )

    # Distancia RGB euclidiana. La banda de feather suaviza bordes
    # antialiasados sin aplicar desenfoque a los contornos.
    hard_limit = max(1, int(tolerance))
    soft_limit = hard_limit + max(0, int(feather))

    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            distance = ((r-bg[0])**2 + (g-bg[1])**2 + (b-bg[2])**2) ** 0.5
            if distance <= hard_limit:
                pixels[x, y] = (r, g, b, 0)
            elif distance < soft_limit:
                alpha = int(a * (distance-hard_limit) / max(1, soft_limit-hard_limit))
                pixels[x, y] = (r, g, b, alpha)

    return rgba, "#{:02x}{:02x}{:02x}".format(*bg)


def clean_svg(svg_text):
    svg_text = re.sub(
        r"<metadata>.*?</metadata>", "", svg_text, flags=re.S | re.I
    )
    if "<svg" not in svg_text.lower():
        raise ValueError("VTracer no devolvió un SVG válido.")
    return svg_text


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify(ok=True, engine="VTracer", version="0.6.15")


@app.post("/api/vectorize")
def vectorize():
    upload = request.files.get("image")
    if not upload or not upload.filename:
        return jsonify(ok=False, error="Selecciona una imagen."), 400

    mode = request.form.get("mode", "polygon")
    if mode not in ("polygon", "spline", "binary"):
        mode = "polygon"

    try:
        detail = max(1, min(8, int(request.form.get("detail", "5"))))
        speckle = max(0, min(64, int(request.form.get("speckle", "4"))))
        tolerance = max(0, min(150, int(request.form.get("tolerance", "38"))))
    except (TypeError, ValueError):
        detail, speckle, tolerance = 5, 4, 38
    remove_bg = request.form.get("remove_bg", "true").lower() == "true"

    job = uuid.uuid4().hex
    work = JOBS / job
    work.mkdir(exist_ok=True)
    source = work / "input_image"
    prepared = work / "prepared.png"
    output = JOBS / (job + ".svg")
    upload.save(source)

    try:
        image, original_size = prepare_image(source)
        detected_background = None
        if remove_bg:
            image, detected_background = remove_background_auto(
                image, tolerance=tolerance, feather=24
            )
        image.save(prepared, format="PNG")

        colormode = "binary" if mode == "binary" else "color"
        hierarchy = "cutout" if mode == "polygon" else "stacked"
        trace_mode = "polygon" if mode in ("polygon", "binary") else "spline"

        vtracer.convert_image_to_svg_py(
            str(prepared),
            str(output),
            colormode=colormode,
            hierarchical=hierarchy,
            mode=trace_mode,
            filter_speckle=speckle,
            color_precision=max(3, min(8, detail)),
            layer_difference=max(8, 32 - detail * 3),
            corner_threshold=60,
            length_threshold=4.0,
            max_iterations=10,
            splice_threshold=45,
            path_precision=3
        )

        svg_text = clean_svg(
            output.read_text(encoding="utf-8", errors="replace")
        )
        output.write_text(svg_text, encoding="utf-8")

        print(
            "[ZAFRIK VECTORIZE PRO V5 - VTRACER]",
            original_size, image.size, mode, flush=True
        )

        return jsonify(
            ok=True,
            job=job,
            svg="/api/svg/" + job,
            engine="VTracer",
            mode=mode,
            background_removed=remove_bg,
            detected_background=detected_background,
            note=(
                "Fondo detectado: " + str(detected_background) + ". "
                "La imagen se ajustó a un máximo de 1800 px por lado."
                if remove_bg else
                "Eliminación automática de fondo desactivada."
            )
        )

    except Exception as exc:
        traceback.print_exc()
        output.unlink(missing_ok=True)
        return jsonify(
            ok=False,
            error="No se pudo vectorizar la imagen.",
            detail=str(exc)
        ), 500

    finally:
        shutil.rmtree(work, ignore_errors=True)


@app.get("/api/svg/<job>")
def preview_svg(job):
    path = JOBS / (job + ".svg")
    if not job.isalnum() or not path.exists():
        return "Archivo no encontrado", 404
    return send_file(path, mimetype="image/svg+xml")


@app.get("/api/download/<job>")
def download_svg(job):
    path = JOBS / (job + ".svg")
    if not job.isalnum() or not path.exists():
        return "Archivo no encontrado", 404
    return send_file(
        path,
        mimetype="image/svg+xml",
        as_attachment=True,
        download_name="ZAFRIK_VECTORIZE_PRO_V5.svg"
    )


@app.get("/api/download-png/<job>/<int:size>")
def download_png(job, size):
    if size not in (3000, 3600, 4800):
        return jsonify(ok=False, error="Tamaño no permitido."), 400

    svg_path = JOBS / (job + ".svg")
    if not job.isalnum() or not svg_path.exists():
        return "Archivo no encontrado", 404

    png_path = JOBS / (job + "_" + str(size) + ".png")
    try:
        cairosvg.svg2png(
            url=str(svg_path),
            write_to=str(png_path),
            output_width=size
        )
        return send_file(
            png_path,
            mimetype="image/png",
            as_attachment=True,
            download_name=(
                "ZAFRIK_VECTORIZE_PRO_V5_" + str(size) + "px.png"
            )
        )
    except Exception as exc:
        return jsonify(
            ok=False,
            error="No se pudo generar el PNG.",
            detail=str(exc)
        ), 500
