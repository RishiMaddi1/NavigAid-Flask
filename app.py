from flask import Flask, request, jsonify, Response
import cloudinary
import cloudinary.uploader
import tempfile
import requests

# Cloudinary configuration
cloudinary.config(
    cloud_name="du54acioe",
    api_key="532718876252765",
    api_secret="8xIh7tTVV_VsW_996YltNBdEG8Q"
)

# Groq API Key
groq_api_key = "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"

# Flask app
app = Flask(_name_)

# Upload Image to Cloudinary
def upload_image_to_cloudinary(file_path):
    upload_result = cloudinary.uploader.upload(
        file_path,
        public_id="image_as_jpg",
        fetch_format="jpg"
    )
    return upload_result["secure_url"]

# Generate image context using Groq Vision
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

    resp.raise_for_status()

    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()

# Translate audio to text
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

# Answer user question based on context
def answer_user_question(context, user_question):
    prompt = (
        f"Context:\n{context}\n\n"
        f"Question:\n{user_question}\n\n"
        "Please provide a conversational answer and be friendly. "
        "Do not include any additional commentary, explanations, or headings."
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

# Convert text to speech
def text_to_speech(
    text: str,
    model: str = "playai-tts",
    voice: str = "Mitch-PlayAI",
    response_format: str = "mp3",
) -> bytes:
    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "voice": voice,
        "input": text,
        "response_format": response_format,
    }

    resp = requests.post(
        "https://api.groq.com/openai/v1/audio/speech",
        headers=headers,
        json=payload,
    )
    resp.raise_for_status()

    return resp.content

# ROUTES

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
