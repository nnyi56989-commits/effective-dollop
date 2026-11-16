import os, uuid, json, subprocess, shutil
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from groq import Groq
import edge_tts

load_dotenv()
ROOT=Path(__file__).parent
DATA=ROOT/"data"; DATA.mkdir(exist_ok=True)
app=FastAPI(title="KOPHYOE RECAP API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/media", StaticFiles(directory=DATA), name="media")
def run(cmd):
    p=subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode: raise RuntimeError(p.stderr[-2500:])
    return p.stdout
def ffmpeg_ok():
    if not shutil.which("ffmpeg"): raise HTTPException(500,"FFmpeg is not installed on the server.")
def project(pid):
    p=DATA/pid
    if not p.exists(): raise HTTPException(404,"Project not found")
    return p
@app.get("/api/health")
def health(): return {"ok":True,"app":"KOPHYOE RECAP","ffmpeg":bool(shutil.which("ffmpeg")),"groq_configured":bool(os.getenv("GROQ_API_KEY"))}
@app.post("/api/upload")
async def upload(video: UploadFile=File(...)):
    ffmpeg_ok()
    if not video.filename.lower().endswith((".mp4",".mov",".mkv",".webm",".m4v")): raise HTTPException(400,"Upload MP4, MOV, MKV, or WebM.")
    pid=uuid.uuid4().hex[:12]; d=DATA/pid; d.mkdir()
    path=d/("source"+Path(video.filename).suffix.lower())
    with path.open("wb") as f:
        while chunk:=await video.read(1024*1024): f.write(chunk)
    try:
        run(["ffmpeg","-y","-i",str(path),"-vn","-ac","1","-ar","16000",str(d/"audio.wav")])
        probe=json.loads(run(["ffprobe","-v","quiet","-print_format","json","-show_format","-show_streams",str(path)]))
        duration=float(probe.get("format",{}).get("duration",0))
    except Exception as e: raise HTTPException(500,f"Video ingest failed: {e}")
    meta={"id":pid,"filename":video.filename,"source":path.name,"duration":duration,"created":datetime.utcnow().isoformat(),"status":"uploaded"}
    (d/"project.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    return meta
@app.post("/api/transcribe/{pid}")
def transcribe(pid:str):
    d=project(pid); key=os.getenv("GROQ_API_KEY")
    if not key: raise HTTPException(400,"Set GROQ_API_KEY in backend/.env")
    try:
        client=Groq(api_key=key)
        with open(d/"audio.wav","rb") as f:
            result=client.audio.transcriptions.create(file=("audio.wav",f.read()),model="whisper-large-v3",response_format="verbose_json",timestamp_granularities=["segment"])
        data={"text":result.text,"segments":[{"start":s.start,"end":s.end,"text":s.text} for s in (result.segments or [])]}
        (d/"transcript.json").write_text(json.dumps(data,ensure_ascii=False,indent=2))
        return data
    except Exception as e: raise HTTPException(502,f"Groq transcription failed: {e}")
@app.post("/api/translate/{pid}")
def translate(pid:str, target_language:str=Form("Burmese")):
    d=project(pid)
    if not (d/"transcript.json").exists(): raise HTTPException(400,"Transcribe first.")
    client=Groq(api_key=os.getenv("GROQ_API_KEY"))
    data=json.loads((d/"transcript.json").read_text())
    # Preserve timing and translate each segment independently.
    segments=data["segments"]
    for i in range(0,len(segments),20):
        batch=segments[i:i+20]
        prompt="Translate each segment into natural spoken Burmese for a clear movie-recap narrator. Keep meaning, names, and order. Return ONLY a JSON array of translated strings, same length. Segments:\n"+json.dumps([x["text"] for x in batch],ensure_ascii=False)
        try:
            r=client.chat.completions.create(model="llama-3.3-70b-versatile",temperature=0.2,messages=[{"role":"user","content":prompt}])
            vals=json.loads(r.choices[0].message.content.strip().removeprefix("```json").removesuffix("```").strip())
            if len(vals)!=len(batch): raise ValueError("Translation segment count mismatch")
            for seg,val in zip(batch,vals): seg["translated"]=val
        except Exception as e: raise HTTPException(502,f"Groq translation failed: {e}")
    (d/"burmese.json").write_text(json.dumps({"segments":segments},ensure_ascii=False,indent=2))
    return {"segments":segments}
@app.post("/api/voice/{pid}")
async def voice(pid:str, provider:str=Form("edge"), voice:str=Form("my-MM-NilarNeural")):
    d=project(pid); f=d/"burmese.json"
    if not f.exists(): raise HTTPException(400,"Translate first.")
    segs=json.loads(f.read_text())["segments"]
    text=" ".join(s.get("translated","") for s in segs).strip()
    out=d/"voice.mp3"
    try:
        if provider=="edge":
            if voice not in ("my-MM-NilarNeural","my-MM-ThihaNeural"): raise HTTPException(400,"Unsupported Edge Burmese voice.")
            await edge_tts.Communicate(text,voice).save(str(out))
        elif provider=="google":
            from google.cloud import texttospeech
            client=texttospeech.TextToSpeechClient()
            # User must select a verified Burmese voice ID from their Google Cloud project.
            if not voice.startswith("my-MM-"): raise HTTPException(400,"Choose a verified my-MM Google voice ID.")
            response=client.synthesize_speech(input=texttospeech.SynthesisInput(text=text),voice=texttospeech.VoiceSelectionParams(language_code="my-MM",name=voice),audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3))
            out.write_bytes(response.audio_content)
        else: raise HTTPException(400,"Unknown TTS provider")
        return {"audio_url":f"/media/{pid}/voice.mp3","download_url":f"/media/{pid}/voice.mp3"}
    except HTTPException: raise
    except Exception as e: raise HTTPException(502,f"TTS failed: {e}")
@app.get("/api/subtitles/{pid}")
def subtitles(pid:str):
    d=project(pid); f=d/"burmese.json"
    if not f.exists(): raise HTTPException(400,"Translate first.")
    segs=json.loads(f.read_text())["segments"]
    def stamp(t):
        ms=int(round(float(t)*1000)); h,ms=divmod(ms,3600000); m,ms=divmod(ms,60000); s,ms=divmod(ms,1000)
        return f"{h:02}:{m:02}:{s:02},{ms:03}"
    body=[]
    for i,s in enumerate(segs,1):
        body += [str(i),f"{stamp(s['start'])} --> {stamp(s['end'])}",s.get("translated",s["text"]),""] 
    out=d/"burmese.srt"; out.write_text("\n".join(body),encoding="utf-8")
    return {"url":f"/media/{pid}/burmese.srt"}
@app.post("/api/export/{pid}")
def export(pid:str, mirror:bool=Form(False), zoom:float=Form(1.0), brightness:float=Form(0.0), contrast:float=Form(1.0), saturation:float=Form(1.0), watermark:str=Form(""), watermark_opacity:float=Form(.35), subtitle:bool=Form(True)):
    ffmpeg_ok(); d=project(pid); meta=json.loads((d/"project.json").read_text()); src=d/meta["source"]
    vf=[]
    if mirror: vf.append("hflip")
    if zoom>1: vf.append(f"scale=iw*{min(max(zoom,1),1.5)}:ih*{min(max(zoom,1),1.5)},crop=iw/{min(max(zoom,1),1.5)}:ih/{min(max(zoom,1),1.5)}")
    vf.append(f"eq=brightness={min(max(brightness,-1),1)}:contrast={min(max(contrast,0.5),2)}:saturation={min(max(saturation,0),2)}")
    if subtitle and (d/"burmese.srt").exists(): vf.append(f"subtitles={str(d/'burmese.srt').replace(chr(92),'/').replace(':',r'\\:')}")
    if watermark:
        safe=watermark.replace("'","").replace(":"," ")
        vf.append(f"drawtext=text='{safe}':fontcolor=white@{min(max(watermark_opacity,0),1)}:fontsize=28:x=w-tw-28:y=h-th-28:box=1:boxcolor=black@0.25:boxborderw=8")
    out=d/"apple_recap_1080p.mp4"
    cmd=["ffmpeg","-y","-i",str(src)]
    if (d/"voice.mp3").exists():
        cmd += ["-i",str(d/"voice.mp3"),"-map","0:v:0","-map","1:a:0"]
    else: cmd += ["-map","0:v:0","-an"]
    cmd += ["-vf",",".join(vf),"-c:v","libx264","-preset","medium","-crf","20","-pix_fmt","yuv420p","-s","1920x1080","-c:a","aac","-b:a","192k","-shortest",str(out)]
    try: run(cmd)
    except Exception as e: raise HTTPException(500,f"Export failed: {e}")
    meta["status"]="exported"; meta["output"]=out.name; meta["updated"]=datetime.utcnow().isoformat()
    (d/"project.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    return {"video_url":f"/media/{pid}/{out.name}","filename":out.name}
@app.get("/api/history")
def history():
    rows=[]
    for p in DATA.iterdir():
        f=p/"project.json"
        if f.exists():
            try:
                m=json.loads(f.read_text()); rows.append(m)
            except: pass
    return sorted(rows,key=lambda x:x.get("created",""),reverse=True)
                   
