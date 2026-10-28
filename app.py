from flask import Flask,render_template,request,send_file,jsonify
from pathlib import Path
from PIL import Image
import tempfile,uuid,os,subprocess,sys
app=Flask(__name__); app.config["MAX_CONTENT_LENGTH"]=25*1024*1024
JOBS=Path(tempfile.gettempdir())/"zafrik_vectorize"; JOBS.mkdir(exist_ok=True)
@app.get("/")
def home(): return render_template("index.html")
def prep(src,dst,maxside):
    with Image.open(src) as im:
        im=im.convert("RGBA"); orig=im.size; s=min(1,maxside/max(im.size))
        if s<1: im=im.resize((round(im.width*s),round(im.height*s)),Image.Resampling.LANCZOS)
        size=im.size; im.save(dst,"PNG"); return orig,size
def trace(inp,out,mode,safe):
    worker=JOBS/(uuid.uuid4().hex+"_worker.py")
    worker.write_text('import sys,vtracer\ninp,out,mode,safe=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4]=="1"\nif safe:\n    kw=dict(colormode="color",hierarchical="cutout",mode="polygon",filter_speckle=12,color_precision=3,layer_difference=32,corner_threshold=60,length_threshold=6.0,max_iterations=5,splice_threshold=45,path_precision=2)\nelif mode=="flat":\n    kw=dict(colormode="color",hierarchical="cutout",mode="spline",filter_speckle=10,color_precision=4,layer_difference=24,corner_threshold=60,length_threshold=5.0,max_iterations=6,splice_threshold=45,path_precision=3)\nelse:\n    kw=dict(colormode="color",hierarchical="cutout",mode="spline",filter_speckle=7,color_precision=4,layer_difference=20,corner_threshold=60,length_threshold=5.0,max_iterations=6,splice_threshold=45,path_precision=3)\nvtracer.convert_image_to_svg_py(inp,out,**kw)\n',encoding="utf-8")
    try:
        return subprocess.run([sys.executable,str(worker),str(inp),str(out),mode,"1" if safe else "0"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=45)
    finally: worker.unlink(missing_ok=True)
@app.post("/api/vectorize")
def vectorize():
    f=request.files.get("image")
    if not f or not f.filename:return jsonify(ok=False,error="Selecciona una imagen."),400
    mode=request.form.get("mode","detail"); job=uuid.uuid4().hex
    raw=JOBS/(job+"_raw"); safe=JOBS/(job+"_safe.png"); out=JOBS/(job+".svg"); f.save(raw)
    try:
        orig,size=prep(raw,safe,1100); print("[ZAFRIK] original",orig,"prepared",size,"mode",mode,flush=True)
        r=trace(safe,out,mode,False); print("[ZAFRIK] normal code",r.returncode,"stderr",r.stderr[-1500:],flush=True)
        fallback=False
        if r.returncode!=0 or not out.exists() or out.stat().st_size<100:
            fallback=True; out.unlink(missing_ok=True); _,size2=prep(raw,safe,700); print("[ZAFRIK] fallback prepared",size2,flush=True)
            r=trace(safe,out,mode,True); print("[ZAFRIK] fallback code",r.returncode,"stderr",r.stderr[-1500:],flush=True)
        if r.returncode!=0 or not out.exists() or out.stat().st_size<100:
            detail=(r.stderr or "").strip()[-800:] or ("VTracer code "+str(r.returncode)); print("[ZAFRIK] ERROR",detail,flush=True)
            return jsonify(ok=False,error="El motor no pudo procesar esta imagen.",detail=detail),422
        print("[ZAFRIK] OK bytes",out.stat().st_size,"fallback",fallback,flush=True)
        return jsonify(ok=True,job=job,svg="/api/svg/"+job,fallback=fallback)
    except subprocess.TimeoutExpired:
        print("[ZAFRIK] TIMEOUT",flush=True); return jsonify(ok=False,error="La vectorización tardó demasiado."),504
    except Exception as e:
        print("[ZAFRIK] EXCEPTION",repr(e),flush=True); return jsonify(ok=False,error="No se pudo vectorizar.",detail=str(e)),500
    finally: raw.unlink(missing_ok=True); safe.unlink(missing_ok=True)
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
