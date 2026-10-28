from flask import Flask, render_template, request, send_file, jsonify
from pathlib import Path
from PIL import Image
import tempfile, uuid, subprocess, traceback, re, shutil

app=Flask(__name__)
app.config["MAX_CONTENT_LENGTH"]=25*1024*1024
JOBS=Path(tempfile.gettempdir())/"zafrik_vectorize_color"
JOBS.mkdir(exist_ok=True)

@app.get("/")
def home(): return render_template("index.html")

def prepare(src,max_side=1600):
    im=Image.open(src).convert("RGBA"); original=im.size
    s=min(1.0,max_side/max(im.size))
    if s<1: im=im.resize((max(1,round(im.width*s)),max(1,round(im.height*s))),Image.Resampling.LANCZOS)
    return im,original

def quantize(im,colors):
    alpha=im.getchannel("A")
    base=Image.new("RGB",im.size,(255,255,255))
    base.paste(im.convert("RGB"),mask=alpha)
    q=base.quantize(colors=colors,method=Image.Quantize.MEDIANCUT,dither=Image.Dither.NONE)
    pal=q.getpalette()
    used=sorted(q.getcolors(maxcolors=65536) or [],reverse=True)
    return q,alpha,[(idx,tuple(pal[idx*3:idx*3+3]),count) for count,idx in used]

def mask_for(q,alpha,idx,dst):
    qi=q.load(); ai=alpha.load()
    m=Image.new("1",q.size,1); mp=m.load()
    for y in range(q.height):
        for x in range(q.width):
            if ai[x,y]>20 and qi[x,y]==idx: mp[x,y]=0
    m.save(dst,"PBM")

def trace(mask,svg):
    return subprocess.run(["potrace",str(mask),"-s","-o",str(svg),"--turdsize","2","--alphamax","1.0","--opttolerance","0.18"],
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=35)

def body(txt):
    m=re.search(r"<svg[^>]*>(.*)</svg>",txt,flags=re.S|re.I)
    if not m:return ""
    b=re.sub(r"<metadata>.*?</metadata>","",m.group(1),flags=re.S|re.I)
    return b.replace('fill="#000000"','fill="currentColor"').strip()

@app.get("/api/health")
def health():
    r=subprocess.run(["potrace","--version"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=5)
    return jsonify(ok=r.returncode==0,engine=(r.stdout or r.stderr).splitlines()[0])

@app.post("/api/vectorize")
def vectorize():
    f=request.files.get("image")
    if not f or not f.filename:return jsonify(ok=False,error="Selecciona una imagen."),400
    try: colors=max(2,min(32,int(request.form.get("colors","16"))))
    except: colors=16
    job=uuid.uuid4().hex; work=JOBS/job; work.mkdir(exist_ok=True)
    raw=work/"input"; out=JOBS/(job+".svg"); f.save(raw)
    try:
        im,original=prepare(raw)
        q,alpha,layers=quantize(im,colors)
        minimum=max(3,int(im.width*im.height*0.0002))
        layers=[x for x in layers if x[2]>=minimum]
        groups=[]
        for n,(idx,rgb,count) in enumerate(layers):
            pbm=work/f"l{n}.pbm"; sv=work/f"l{n}.svg"
            mask_for(q,alpha,idx,pbm); r=trace(pbm,sv)
            if r.returncode==0 and sv.exists():
                b=body(sv.read_text(errors="ignore"))
                if b:
                    hx="#%02x%02x%02x"%rgb
                    groups.append('<g style="color:%s">%s</g>'%(hx,b))
        if not groups:return jsonify(ok=False,error="No se pudieron generar capas vectoriales."),422
        w,h=im.size
        final='<?xml version="1.0" standalone="no"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="%s" height="%s" viewBox="0 0 %s %s" preserveAspectRatio="xMidYMid meet">\n%s\n</svg>'%(w,h,w,h,"".join(groups))
        out.write_text(final,encoding="utf-8")
        print("[ZAFRIK V5.4 COLOR]",original,im.size,"layers",len(groups),flush=True)
        return jsonify(ok=True,job=job,svg="/api/svg/"+job,engine="Potrace Color Layers",colors=len(groups))
    except Exception as e:
        traceback.print_exc()
        return jsonify(ok=False,error="No se pudo vectorizar.",detail=str(e)),500
    finally: shutil.rmtree(work,ignore_errors=True)

@app.get("/api/svg/<job>")
def svg(job):
    p=JOBS/(job+".svg")
    if not job.isalnum() or not p.exists():return "Archivo no encontrado",404
    return send_file(p,mimetype="image/svg+xml")

@app.get("/api/download/<job>")
def download(job):
    p=JOBS/(job+".svg")
    if not job.isalnum() or not p.exists():return "Archivo no encontrado",404
    return send_file(p,mimetype="image/svg+xml",as_attachment=True,download_name="ZAFRIK_VECTORIZE_PRO_COLOR.svg")
