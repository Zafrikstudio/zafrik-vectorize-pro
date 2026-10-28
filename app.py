from flask import Flask, render_template, request, send_file, jsonify
from pathlib import Path
from PIL import Image
import tempfile, uuid, os, subprocess, sys
app=Flask(__name__); app.config["MAX_CONTENT_LENGTH"]=25*1024*1024
JOBS=Path(tempfile.gettempdir())/"zafrik_vectorize"; JOBS.mkdir(exist_ok=True)
MAX_SIDE=1600

@app.get("/")
def home(): return render_template("index.html")

def prepare_image(src,dst):
    with Image.open(src) as im:
        im=im.convert("RGBA"); original=im.size
        scale=min(1.0,MAX_SIDE/max(im.size))
        if scale<1:
            im=im.resize((max(1,round(im.width*scale)),max(1,round(im.height*scale))),Image.Resampling.LANCZOS)
        prepared=im.size; im.save(dst,"PNG",optimize=True); return original,prepared

@app.post("/api/vectorize")
def vectorize():
    f=request.files.get("image")
    if not f or not f.filename: return jsonify(ok=False,error="Selecciona una imagen."),400
    mode=request.form.get("mode","detail"); job=uuid.uuid4().hex
    raw=JOBS/f"{job}_raw"; safe=JOBS/f"{job}_safe.png"; out=JOBS/f"{job}.svg"; worker=JOBS/f"{job}_worker.py"
    f.save(raw)
    try:
        original,prepared=prepare_image(raw,safe)
        worker.write_text("""import sys,vtracer
inp,out,mode=sys.argv[1],sys.argv[2],sys.argv[3]
kw=dict(colormode="color",hierarchical="cutout",mode="spline",corner_threshold=60,max_iterations=8,splice_threshold=45,path_precision=3)
if mode=="flat": kw.update(filter_speckle=10,color_precision=4,layer_difference=24,length_threshold=5.0)
else: kw.update(filter_speckle=6,color_precision=5,layer_difference=16,length_threshold=4.0)
vtracer.convert_image_to_svg_py(inp,out,**kw)
""",encoding="utf-8")
        r=subprocess.run([sys.executable,str(worker),str(safe),str(out),mode],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=55)
        if r.returncode!=0 or not out.exists() or out.stat().st_size<100:
            return jsonify(ok=False,error="El motor no pudo procesar esta imagen.",detail=(r.stderr.strip()[-700:] or f"Código {r.returncode}")),422
        return jsonify(ok=True,job=job,svg=f"/api/svg/{job}",original={"width":original[0],"height":original[1]},processed={"width":prepared[0],"height":prepared[1]})
    except subprocess.TimeoutExpired:
        return jsonify(ok=False,error="La vectorización tardó demasiado. Prueba Colores planos."),504
    except Exception as e:
        return jsonify(ok=False,error="No se pudo vectorizar.",detail=str(e)),500
    finally:
        for p in (raw,safe,worker):
            try:p.unlink(missing_ok=True)
            except:pass

@app.get("/api/svg/<job>")
def svg(job):
    p=JOBS/f"{job}.svg"
    if not job.isalnum() or not p.exists(): return "Archivo no encontrado",404
    return send_file(p,mimetype="image/svg+xml")

@app.get("/api/download/<job>")
def download(job):
    p=JOBS/f"{job}.svg"
    if not job.isalnum() or not p.exists(): return "Archivo no encontrado",404
    return send_file(p,mimetype="image/svg+xml",as_attachment=True,download_name="ZAFRIK_VECTORIZE_PRO.svg")
