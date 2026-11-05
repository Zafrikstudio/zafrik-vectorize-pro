from flask import Flask, render_template, request, send_file, jsonify
from pathlib import Path
from PIL import Image, ImageOps, ImageChops
import tempfile
import uuid
import traceback
import re
import shutil
import time
import cairosvg
import vtracer

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 30_000_000

JOBS = Path(tempfile.gettempdir()) / "zafrik_vectorize_v5_2"
JOBS.mkdir(exist_ok=True)

# V5.2: reducir el pico de RAM en el plan gratuito de Render.
MAX_TRACE_SIDE = 1200
ALLOWED_MODES = ("polygon", "spline", "binary")


def cleanup_old_jobs(max_age=6 * 60 * 60):
    """Elimina resultados temporales antiguos para no acumular archivos."""
    cutoff = time.time() - max_age
    try:
        for item in JOBS.iterdir():
            try:
                if item.stat().st_mtime < cutoff:
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        item.unlink(missing_ok=True)
            except OSError:
                pass
    except OSError:
        pass


def prepare_image(src, max_side=MAX_TRACE_SIDE):
    image = Image.open(src)
    image = ImageOps.exif_transpose(image)
    image.load()
    image = image.convert("RGBA")
    original_size = image.size

    # thumbnail modifica la imagen en sitio y evita conservar otra copia grande.
    image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return image, original_size


def remove_background_auto(image, tolerance=38, feather=20):
    """
    Detecta el color predominante en los bordes y crea una máscara alfa.
    Las operaciones por píxel se ejecutan con Pillow (código nativo), no con
    bucles Python, para reducir consumo de RAM y tiempo.
    """
    width, height = image.size
    px = image.load()
    step = max(1, min(width, height) // 350)
    samples = []
    for x in range(0, width, step):
        samples.append(px[x, 0][:3])
        samples.append(px[x, height - 1][:3])
    for y in range(0, height, step):
        samples.append(px[0, y][:3])
        samples.append(px[width - 1, y][:3])

    # Conteo de colores agrupados en bloques de 16 niveles.
    buckets = {}
    for r, g, b in samples:
        key = (r // 16, g // 16, b // 16)
        buckets[key] = buckets.get(key, 0) + 1
    dominant = max(buckets, key=buckets.get)
    cluster = [c for c in samples if (c[0] // 16, c[1] // 16, c[2] // 16) == dominant]
    count = max(1, len(cluster))
    bg = tuple(sum(c[i] for c in cluster) // count for i in range(3))

    rgb = image.convert("RGB")
    channels = rgb.split()
    diffs = [
        ImageChops.difference(channels[0], Image.new("L", image.size, bg[0])),
        ImageChops.difference(channels[1], Image.new("L", image.size, bg[1])),
        ImageChops.difference(channels[2], Image.new("L", image.size, bg[2])),
    ]
    distance = ImageChops.lighter(ImageChops.lighter(diffs[0], diffs[1]), diffs[2])

    hard = max(0, min(150, int(tolerance)))
    soft = hard + max(1, int(feather))
    # Máscara alfa: 0 para fondo, transición suave, 255 para primer plano.
    lut = []
    for value in range(256):
        if value <= hard:
            lut.append(0)
        elif value >= soft:
            lut.append(255)
        else:
            lut.append(int(255 * (value - hard) / (soft - hard)))
    mask = distance.point(lut)
    original_alpha = image.getchannel("A")
    mask = ImageChops.multiply(original_alpha, mask)
    image.putalpha(mask)

    # Liberar referencias intermedias explícitamente antes de VTracer.
    del rgb, channels, diffs, distance, original_alpha, mask
    return image, "#{:02x}{:02x}{:02x}".format(*bg)


def clean_svg(svg_text):
    svg_text = re.sub(r"<metadata>.*?</metadata>", "", svg_text, flags=re.S | re.I)
    if "<svg" not in svg_text.lower():
        raise ValueError("VTracer no devolvió un SVG válido.")
    return svg_text


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify(ok=True, engine="VTracer", version="0.6.15", profile="low-memory-v5.2")


@app.post("/api/vectorize")
def vectorize():
    upload = request.files.get("image")
    if not upload or not upload.filename:
        return jsonify(ok=False, error="Selecciona una imagen."), 400

    mode = request.form.get("mode", "polygon")
    if mode not in ALLOWED_MODES:
        mode = "polygon"

    try:
        detail = max(1, min(8, int(request.form.get("detail", "5"))))
        speckle = max(0, min(64, int(request.form.get("speckle", "4"))))
        tolerance = max(0, min(150, int(request.form.get("tolerance", "38"))))
    except (TypeError, ValueError):
        detail, speckle, tolerance = 5, 4, 38

    remove_bg = request.form.get("remove_bg", "true").lower() == "true"
    cleanup_old_jobs()

    job = uuid.uuid4().hex
    work = JOBS / job
    work.mkdir(exist_ok=True)
    source = work / "input_image"
    prepared = work / "prepared.png"
    output = JOBS / (job + ".svg")

    try:
        upload.save(source)
        image, original_size = prepare_image(source)

        detected_background = None
        if remove_bg:
            image, detected_background = remove_background_auto(
                image, tolerance=tolerance, feather=20
            )

        # Guardar una sola imagen reducida como entrada para VTracer.
        image.save(prepared, format="PNG", optimize=False)
        image.close()
        del image

        colormode = "binary" if mode == "binary" else "color"
        hierarchy = "cutout" if mode == "polygon" else "stacked"
        trace_mode = "polygon" if mode in ("polygon", "binary") else "spline"

        # Limitar complejidad para evitar picos de memoria en Render Free.
        vtracer.convert_image_to_svg_py(
            str(prepared),
            str(output),
            colormode=colormode,
            hierarchical=hierarchy,
            mode=trace_mode,
            filter_speckle=speckle,
            color_precision=max(3, min(6, detail)),
            layer_difference=max(10, 34 - detail * 2),
            corner_threshold=60,
            length_threshold=4.0,
            max_iterations=8,
            splice_threshold=45,
            path_precision=2
        )

        svg_text = clean_svg(output.read_text(encoding="utf-8", errors="replace"))
        output.write_text(svg_text, encoding="utf-8")

        print(
            "[ZAFRIK V5.2] Vectorización OK | original={} | procesada={} | modo={} | fondo={}".format(
                original_size, (MAX_TRACE_SIDE, MAX_TRACE_SIDE), mode, remove_bg
            ),
            flush=True
        )

        return jsonify(
            ok=True,
            job=job,
            svg="/api/svg/" + job,
            engine="VTracer",
            mode=mode,
            background_removed=remove_bg,
            detected_background=detected_background,
            processed_max_side=MAX_TRACE_SIDE,
            note=(
                "Fondo detectado: {}. Procesamiento optimizado a un máximo de {} px por lado.".format(
                    detected_background, MAX_TRACE_SIDE
                ) if remove_bg else
                "Eliminación automática de fondo desactivada. Procesamiento optimizado a {} px por lado.".format(
                    MAX_TRACE_SIDE
                )
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
        return jsonify(ok=False, error="Archivo no encontrado."), 404
    return send_file(path, mimetype="image/svg+xml")


@app.get("/api/download/<job>")
def download_svg(job):
    path = JOBS / (job + ".svg")
    if not job.isalnum() or not path.exists():
        return jsonify(ok=False, error="Archivo no encontrado."), 404
    return send_file(
        path, mimetype="image/svg+xml", as_attachment=True,
        download_name="ZAFRIK_VECTORIZE_PRO_V5_2.svg"
    )


@app.get("/api/download-png/<job>/<int:size>")
def download_png(job, size):
    if size not in (3000, 3600, 4800):
        return jsonify(ok=False, error="Tamaño no permitido."), 400

    svg_path = JOBS / (job + ".svg")
    if not job.isalnum() or not svg_path.exists():
        return jsonify(ok=False, error="Archivo no encontrado."), 404

    png_path = JOBS / (job + "_" + str(size) + ".png")
    try:
        # Renderizado directo a disco para no mantener el PNG completo en RAM.
        cairosvg.svg2png(
            url=str(svg_path),
            write_to=str(png_path),
            output_width=size
        )
        return send_file(
            png_path, mimetype="image/png", as_attachment=True,
            download_name="ZAFRIK_VECTORIZE_PRO_V5_2_{}px.png".format(size)
        )
    except Exception as exc:
        traceback.print_exc()
        png_path.unlink(missing_ok=True)
        return jsonify(
            ok=False, error="No se pudo generar el PNG.", detail=str(exc)
        ), 500
