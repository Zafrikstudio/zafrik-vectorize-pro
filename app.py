from flask import Flask,render_template,request,send_file,jsonify
from pathlib import Path
from PIL import Image
import tempfile,uuid,subprocess,traceback
app=Flask(__name__); app.config["MAX_CONTENT_LENGTH"]=25*1024*1024
JOBS=Path(tempfile.gettempdir())/"zafrik_vectorize"; JOBS.mkdir(exist_ok=True)
@app.get("/")
def home(): return render_template("index.html")
def prepare(src,dst,max_side=1400):
    with Image.open(src) as im:
        im=im.convert("RGBA"); original=im.size; scale=min(1.0,max_side/max(im.size))
        if scale<1: im=im.resize((max(1,round(im.width*scale)),max(1,round(im.height*scale))),Image.Resampling.LANCZOS)
        size=im.size; im.save(dst,"PNG",optimize=True); return original,size
def run_trace(inp,out,mode):
    cmd=["autotrace",str(inp),"--output-format","svg","--output-file",str(out),
         "--color-count","64" if mode=="detail" else "24",
         "--despeckle-level","2" if mode=="detail" else "4",
         "--corner-threshold","100","--error-threshold","2.0"]
    return subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=55)
@app.get("/api/health")
def health():
    r=subprocess.run(["autotrace","--version"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=5)
    return jsonify(ok=r.returncode==0,engine=(r.stdout or r.stderr).strip(),code=r.returncode)
@app.post("/api/vectorize")
def vectorize():
    f=request.files.get("image")
    if not f or not f.filename:return jsonify(ok=False,error="Selecciona una imagen."),400
    mode=request.form.get("mode","detail"); job=uuid.uuid4().hex
    raw=JOBS/(job+"_raw"); prep=JOBS/(job+".png"); out=JOBS/(job+".svg"); f.save(raw)
    try:
        original,size=prepare(raw,prep); print("[ZAFRIK V5]",original,size,mode,flush=True)
        r=run_trace(prep,out,mode); print("[ZAFRIK V5] code",r.returncode,"stderr",r.stderr[-2000:],flush=True)
        if r.returncode!=0 or not out.exists() or out.stat().st_size<100:
            detail=(r.stderr or r.stdout or ("AutoTrace code "+str(r.returncode))).strip()[-1000:]
            return jsonify(ok=False,error="El motor no pudo procesar esta imagen.",detail=detail),422
        return jsonify(ok=True,job=job,svg="/api/svg/"+job,engine="AutoTrace CLI")
    except subprocess.TimeoutExpired:
        return jsonify(ok=False,error="La vectorización tardó demasiado."),504
    except Exception as e:
        print("[ZAFRIK V5] EXCEPTION",repr(e),flush=True); traceback.print_exc()
        return jsonify(ok=False,error="No se pudo vectorizar.",detail=str(e)),500
    finally: raw.unlink(missing_ok=True); prep.unlink(missing_ok=True)
@app.get("/api/svg/<job>")
def svg(job):
    p=JOBS/(job+".svg")
    if not job.isalnum() or not p.exists():return "Archivo no encontrado",404
    return send_file(p,mimetype="image/svg+xml")
@app.get("/api/download/<job>")
def download(job):
    p=JOBS/(job+".svg")
    if not job.isalnum() or not p.exists():return "Archivo no encontrado",404
    return send_file(p,mimetype="image/svg+xml",as_attachment=True,download_name="ZAFRIK_VECTORIZE_PRO.svg")
