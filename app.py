from flask import Flask,render_template,request,send_file,jsonify
from pathlib import Path
from PIL import Image,ImageOps,ImageFilter
import tempfile,uuid,subprocess,traceback
app=Flask(__name__); app.config["MAX_CONTENT_LENGTH"]=25*1024*1024
JOBS=Path(tempfile.gettempdir())/"zafrik_vectorize"; JOBS.mkdir(exist_ok=True)
@app.get("/")
def home(): return render_template("index.html")
def prep(src,dst,max_side=1800):
    with Image.open(src) as im:
        im=im.convert("RGBA"); original=im.size
        s=min(1.0,max_side/max(im.size))
        if s<1: im=im.resize((max(1,round(im.width*s)),max(1,round(im.height*s))),Image.Resampling.LANCZOS)
        alpha=im.getchannel("A")
        # Trace visible silhouette/details. Transparent background stays white.
        gray=ImageOps.grayscale(im.convert("RGB"))
        # Composite transparent pixels to white before thresholding.
        white=Image.new("L",im.size,255)
        gray=Image.composite(gray,white,alpha)
        gray=gray.filter(ImageFilter.GaussianBlur(0.35))
        # adaptive-ish threshold from histogram median, clamped for artwork
        hist=gray.histogram(); total=sum(hist); acc=0; med=160
        for i,n in enumerate(hist):
            acc+=n
            if acc>=total*0.58: med=i; break
        th=max(105,min(205,med))
        bw=gray.point(lambda p: 0 if p<th else 255,"1")
        bw.save(dst,"PPM")
        return original,im.size,th
def trace(inp,out,mode):
    cmd=["potrace",str(inp),"-s","-o",str(out),"--turdsize","2" if mode=="detail" else "8",
         "--alphamax","1.0","--opttolerance","0.2" if mode=="detail" else "0.5"]
    return subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=45)
@app.get("/api/health")
def health():
    r=subprocess.run(["potrace","--version"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=5)
    return jsonify(ok=r.returncode==0,engine=(r.stdout or r.stderr).splitlines()[0],code=r.returncode)
@app.post("/api/vectorize")
def vectorize():
    f=request.files.get("image")
    if not f or not f.filename:return jsonify(ok=False,error="Selecciona una imagen."),400
    mode=request.form.get("mode","detail"); job=uuid.uuid4().hex
    raw=JOBS/(job+"_raw"); bitmap=JOBS/(job+".ppm"); out=JOBS/(job+".svg"); f.save(raw)
    try:
        original,size,th=prep(raw,bitmap)
        print("[ZAFRIK V5.3 POTRACE]",original,size,"threshold",th,flush=True)
        r=trace(bitmap,out,mode)
        print("[ZAFRIK V5.3] code",r.returncode,"stderr",r.stderr[-1500:],flush=True)
        if r.returncode!=0 or not out.exists() or out.stat().st_size<100:
            return jsonify(ok=False,error="El motor no pudo procesar esta imagen.",detail=(r.stderr or "Potrace no generó SVG")[-800:]),422
        return jsonify(ok=True,job=job,svg="/api/svg/"+job,engine="Potrace")
    except Exception as e:
        print("[ZAFRIK V5.3] ERROR",repr(e),flush=True); traceback.print_exc()
        return jsonify(ok=False,error="No se pudo vectorizar.",detail=str(e)),500
    finally: raw.unlink(missing_ok=True); bitmap.unlink(missing_ok=True)
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
