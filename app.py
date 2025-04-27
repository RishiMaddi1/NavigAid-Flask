from flask import Flask, request, jsonify, Response
import cloudinary.uploader
import tempfile
import requests
import re
import io
import pyttsx3
import os

# Cloudinary configuration
CLOUDINARY_API_KEY = "532718876252765"
CLOUDINARY_API_SECRET = "8xIh7tTVV_VsW_996YltNBdEG8Q"
CLOUDINARY_CLOUD_NAME = "du54acioe"

# Groq API Key
groq_api_key = "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"

# Upload image to Cloudinary
def upload_image_to_cloudinary(file_path):
    upload_result = cloudinary.uploader.upload(
        file_path,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET,
        cloud_name=CLOUDINARY_CLOUD_NAME,
        public_id="image_as_jpg",
        fetch_format="jpg",
    )
    return upload_result["secure_url"]

# Generate context from image using Groq
def generate_image_context_grok(
    image_url: str,
    model: str = "meta-llama/llama-4-scout-17b-16e-instruct",
    temperature: float = 1.0,
    max_completion_tokens: int = 1024,
) -> str:
    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json",
    }

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "This is a live photo taken. Please analyze the image "
                        "and provide a structured response without making unsupported assumptions.\n\n"
                        "Response format:\n"
                        "1. Overall Description (3 paragraphs)\n"
                        "2. Objects (each object described in 2 paragraphs)"
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {"url": image_url},
                },
            ],
        }
    ]

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_completion_tokens": max_completion_tokens,
    }

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers,
        json=payload,
    )

    if resp.status_code != 200:
        print("=== Groq API Error ===")
        print("Status code:", resp.status_code)
        print("Body:", resp.text)
        resp.raise_for_status()

    data = resp.json()
    raw_input_str = str(data["choices"][0]["message"]["content"])

    match = re.search(r"content=\"(.*?)\"", raw_input_str, re.DOTALL)
    if match:
        context = match.group(1)
    else:
        context = raw_input_str.strip()

    return context

# Answer user question based on context
def answer_user_question(context, user_question):
    prompt = (
        f"Context:\n{context}\n\n"
        f"Question:\n{user_question}\n\n"
        "Please provide a conversational answer and be friendly. Do not include any additional commentary, explanations, or headings."
    )
    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_completion_tokens": 500,
    }

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers,
        json=payload,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()

# Translate audio to English text
def translate_audio(
    audio_file_path: str,
    model: str = "whisper-large-v3",
    response_format: str = "text",
) -> str:
    with open(audio_file_path, "rb") as f:
        files = {"file": f}
        data = {
            "model": model,
            "response_format": response_format,
            "temperature": 0.0,
            "language": "en",
        }
        headers = {"Authorization": f"Bearer {groq_api_key}"}

        resp = requests.post(
            "https://api.groq.com/openai/v1/audio/translations",
            headers=headers,
            files=files,
            data=data,
        )
        resp.raise_for_status()
        return resp.text.strip()

# Text-to-Speech using pyttsx3 (offline)
def text_to_speech(
    text: str,
    model: str = "playai-tts",  # Ignored
    voice: str = "Mitch-PlayAI", # Ignored
    response_format: str = "mp3",
) -> bytes:
    """
    Converts text to speech using pyttsx3 and returns MP3 bytes.
    """
    engine = pyttsx3.init()
    engine.setProperty('rate', 150)  # Speed
    engine.setProperty('volume', 1)  # Max volume

    # Save to temporary WAV file
    temp_wav = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
    temp_wav_path = temp_wav.name
    temp_wav.close()
    engine.save_to_file(text, temp_wav_path)
    engine.runAndWait()

    # Convert WAV to MP3 if needed
    from pydub import AudioSegment  # Requires pip install pydub
    audio = AudioSegment.from_wav(temp_wav_path)
    mp3_io = io.BytesIO()
    audio.export(mp3_io, format="mp3")
    mp3_io.seek(0)

    # Cleanup temp wav
    os.remove(temp_wav_path)

    return mp3_io.read()

# Flask App
app = Flask(_name_)

@app.route("/")
def home():
    return "Welcome to NavigAid!"

@app.route("/analyze_image", methods=["POST"])
def analyze_image():
    if "image" not in request.files:
        return jsonify({"error": "No image file provided"}), 400
    img = request.files["image"]

    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        img.save(tmp.name)
        local_path = tmp.name

    image_url = upload_image_to_cloudinary(local_path)
    context = generate_image_context_grok(image_url)

    return jsonify({"context": context})

@app.route("/ask_question", methods=["POST"])
def ask_question():
    context = request.form.get("context")
    if not context:
        return jsonify({"error": "No context provided"}), 400

    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided"}), 400
    audio = request.files["audio"]

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        audio.save(tmp.name)
        audio_path = tmp.name

    translated_question = translate_audio(audio_path)
    final_answer = answer_user_question(context, translated_question)

    mp3_bytes = text_to_speech(
        final_answer,
        model="playai-tts",
        voice="Mitch-PlayAI",
        response_format="mp3"
    )

    return Response(mp3_bytes, mimetype="audio/mpeg")

if _name_ == "_main_":
    app.run(host="0.0.0.0", port=5000, debug=True)
