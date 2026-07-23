import os
from PIL import Image
ROOT="review-artifacts/togal-faithful-rebuild"
REF=os.path.join(ROOT,"reference"); FIN=os.path.join(ROOT,"final")
OUTC=os.path.join(ROOT,"final-comparison"); OUTO=os.path.join(ROOT,"final-overlay")
os.makedirs(OUTC,exist_ok=True); os.makedirs(OUTO,exist_ok=True)
VPS=["390x844","834x1194","1440x1000","768x1024","430x932","1024x1366","1920x1080"]
def load(p,w):
    im=Image.open(p).convert("RGB"); ww,hh=im.size; return im.resize((w,int(hh*w/ww)))
for vp in VPS:
    r=os.path.join(REF,f"togal-{vp}.png"); f=os.path.join(FIN,f"mobi-rebuilt-{vp}.png")
    if not(os.path.exists(r) and os.path.exists(f)): continue
    col=520
    a=load(r,col); b=load(f,col)
    H=max(a.height,b.height)
    # side-by-side (full height, capped)
    cap=min(H,5200)
    cv=Image.new("RGB",(col*2+24,cap),(240,242,246))
    cv.paste(a.crop((0,0,col,min(a.height,cap))),(0,0)); cv.paste(b.crop((0,0,col,min(b.height,cap))),(col+24,0))
    cv.save(os.path.join(OUTC,f"compare-{vp}.png"))
    # overlay: reference red-ish vs final blue-ish, aligned top, common width, first 2600px
    oh=min(a.height,b.height,2600)
    A=a.crop((0,0,col,oh)); B=b.crop((0,0,col,oh))
    ov=Image.blend(A,B,0.5); ov.save(os.path.join(OUTO,f"overlay-{vp}.png"))
    print("done",vp,"sideheight",cap,"overlayheight",oh)
print("DONE")
