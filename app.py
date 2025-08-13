# app.py
import os
import re
import textwrap
from flask import Flask, render_template, request, redirect, url_for, flash
from youtube_transcript_api import YouTubeTranscriptApi
from dotenv import load_dotenv

# Try to import Google's legacy SDK (matches your original)
try:
    import google.generativeai as genai
    LEGACY_GENAI = True
except Exception:
    genai = None
    LEGACY_GENAI = False

load_dotenv()  # loads .env if present

# GENAI_API_KEY = os.getenv("GENAI_API_KEY")  # put your key here
GENAI_API_KEY = "AIzaSyBeEjmSLXVAFS-Chr6gHvRDBpaLeLD9-BI"
if GENAI_API_KEY and LEGACY_GENAI:
    genai.configure(api_key=GENAI_API_KEY)
elif GENAI_API_KEY and not LEGACY_GENAI:
    # If the legacy SDK isn't installed, leave for user to install proper package,
    # or they can switch to the newer google-genai SDK (not auto-configured here).
    print("GENAI key found but google.generativeai package not importable. Install google-generativeai or switch SDK.")

app = Flask(__name__)
# app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret")
app.config["SECRET_KEY"] = "a0c1b6e3b77a8217a0ef3f983f01c7b"

# ---------------- utility functions ----------------
def get_video_id(url: str) -> str:
    if "watch?v=" in url:
        return url.split("watch?v=")[1].split("&")[0]
    return ""

def get_transcript(video_id: str, languages: list) -> tuple[str, str] | tuple[None, None]:
    """Fetches a video transcript in plain text, trying multiple languages."""
    try:    
        ytt_api = YouTubeTranscriptApi()
        transcript_list = ytt_api.list(video_id)
        transcript = transcript_list.find_transcript(languages)
        transcript_data = transcript.fetch()
        # transcript_text = " ".join([segment['text'] for segment in transcript_data])
        transcript_text = " ".join([segment.text for segment in transcript_data])
        return transcript_text, transcript.language

    except Exception as e:
        print(f"An error occurred while fetching the transcript: {e}")
        return None, None

def chunk_text(text: str, max_chars: int = 3000) -> list[str]:
    """
    Simple sentence-based chunking. Keeps chunks under max_chars.
    """
    if not text:
        return []
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    cur = ""
    for s in sentences:
        if len(cur) + len(s) + 1 <= max_chars:
            cur = (cur + " " + s).strip() if cur else s
        else:
            if cur:
                chunks.append(cur)
            cur = s
    if cur:
        chunks.append(cur)
    return chunks

def summarize_chunk_gemini(chunk: str, model_name: str = "gemini-1.5-flash-latest") -> str:
    """
    Call Gemini (legacy google.generativeai) to summarize the chunk.
    Returns the model text or None on error.
    """
    if not GENAI_API_KEY:
        return None  # caller should fallback
    try:
        # using legacy SDK usage pattern
        model = genai.GenerativeModel(model_name)
        prompt = f"Please provide a summary of the following text and do not loose any analytical data:\n\n{chunk}"
        resp = model.generate_content(prompt)
        # resp.text contains generated text in legacy SDK
        return resp.text.strip() if getattr(resp, "text", None) else str(resp)
    except Exception as e:
        print("Gemini summarization error:", e)
        return None

def summarize_transcript(transcript: str) -> str:
    """
    Two-pass summarization:
     1. Summarize each chunk
     2. Summarize the combination of chunk summaries into the final short summary
    If GENAI_API_KEY not present, return a short fallback summary for quick local testing.
    """
    if not transcript:
        return "No transcript to summarize."
    if not GENAI_API_KEY:
        # fallback: first ~200 words as a 'quick' summary (good for testing)
        words = transcript.split()
        return " ".join(words[:200]) + ("..." if len(words) > 200 else "")
    # real summarization
    chunks = chunk_text(transcript, max_chars=3000)
    chunk_summaries = []
    for i, ch in enumerate(chunks):
        s = summarize_chunk_gemini(ch)
        if s:
            chunk_summaries.append(s)
    if not chunk_summaries:
        return "Could not generate chunk summaries."
    # combine
    combined = "\n\n".join(chunk_summaries)
    final = summarize_chunk_gemini(combined)
    return final or ("\n\n".join(chunk_summaries))

# ---------------- Flask routes ----------------
@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/summarize", methods=["POST"])
def summarize_route():
    youtube_url = request.form.get("youtube_url", "").strip()
    if not youtube_url:
        flash("Enter a YouTube URL.", "danger")
        return redirect(url_for("index"))

    video_id = get_video_id(youtube_url)
    if not video_id:
        flash("Couldn't parse a video ID from that URL. Paste a full YouTube watch URL.", "danger")
        return redirect(url_for("index"))

    transcript, language = get_transcript(video_id, languages=["en", "hi"])
    if not transcript:
        flash("Transcript not available for this video (captions may be disabled or private).", "warning")
        return redirect(url_for("index"))

    summary = summarize_transcript(transcript)
    # keep summary reasonably short in UI
    short_summary = textwrap.fill(summary, width=100)
    return render_template("index.html",
                           youtube_url=youtube_url,
                        #    transcript=transcript,
                        #    language=language,
                           summary=short_summary
                           )

if __name__ == "__main__":
    # For development only
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
