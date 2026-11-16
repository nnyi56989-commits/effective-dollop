# KOPHYOE RECAP — Professional Web App Starter

A runnable full-stack starter for authorized movie/story recap editing.

## Requirements
- Python 3.11+
- Node.js 20+
- FFmpeg installed and available on PATH
- Groq API key
- Google Cloud Text-to-Speech service-account JSON (optional; Edge-TTS works without it)

## Run
1. Copy `backend/.env.example` to `backend/.env` and add keys.
2. Backend:
   ```bash
   cd backend
   python -m venv .venv
   # activate the venv, then:
   pip install -r requirements.txt
   uvicorn app:app --reload --host 0.0.0.0 --port 8000
   ```
3. Frontend (new terminal):
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
4. Open the Vite URL. Set API URL to `http://localhost:8000` if needed.

## Included now
- Upload video, extract audio, transcribe with Groq Whisper, translate transcript into Burmese with Groq.
- Edge-TTS Burmese voices (NilarNeural / ThihaNeural), optional Google Cloud TTS endpoint.
- MP3 preview/download, SRT download.
- FFmpeg export with original audio removed, optional mirror, zoom, brightness/contrast/saturation, blur region, Burmese subtitle burn-in, watermark and logo overlay.
- Exported project history stored on the server.

## Important limitations / setup
This is a deployable starter, not a hosted service. You must deploy the backend on a server with FFmpeg and configure API credentials. Google TTS voice availability depends on the voices enabled for your Google Cloud project and Burmese language support; the UI exposes the Google provider but does not pretend unsupported Burmese voices exist. Add verified voice IDs in `GOOGLE_VOICES` after checking your Cloud project.
Thumbnail frame selection and drag-to-position editing are scaffolded in the UI; production-grade AI frame ranking and image-generation headline suggestions need a separate vision/LLM step and are not represented as completed in this starter.
Use only videos you own or are authorized to adapt. Mirror/zoom/filter effects do not remove copyright obligations.
