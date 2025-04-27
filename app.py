from flask import Flask, request, jsonify, Response
import cloudinary.uploader
from huggingface_hub import InferenceClient
import re
import tempfile
import requests
import re

# Cloudinary configuration
CLOUDINARY_API_KEY = "532718876252765"
CLOUDINARY_API_SECRET = "8xIh7tTVV_VsW_996YltNBdEG8Q"
CLOUDINARY_CLOUD_NAME = "du54acioe"

# HuggingFace Inference Client



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


def generate_image_context_grok(
    image_url: str,
    groq_api_key: str = "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",
    model: str = "meta-llama/llama-4-scout-17b-16e-instruct",
    temperature: float = 1.0,
    max_completion_tokens: int = 5000,
) -> str:
    """
    Calls Groq Cloud's OpenAI-compatible vision chat endpoint to analyze an image URL.
    Uses Llama 4 Scout (multimodal) by default and returns the text analysis.
    """
    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json",
    }

    # Groq Vision expects `content` to be a list of {type, text} and {type, image_url}
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

    # Debug on error
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


def answer_user_question(context, user_question):
    prompt = (
        f"Context:\n{context}\n\n"
        f"Question:\n{user_question}\n\n"
        "Please provide a conversational answer and be friendly. Do not include any additional commentary, explanations, or headings."
    )
    import requests
    groq_api_key = "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"
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


# … if you already have a groq_api_key defined for vision, you can reuse it:
groq_api_key = "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"


def translate_audio(
    audio_file_path: str,
    model: str = "whisper-large-v3",
    response_format: str = "text",
) -> str:
    """
    Calls Groq’s translation endpoint to turn speech (any language) into English text.
    """
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


def text_to_speech(
    text: str,
    model: str = "playai-tts",
    voice: str = "Mitch-PlayAI",
    response_format: str = "wav",
) -> bytes:
    """
    Calls Groq’s text-to-speech endpoint and returns raw audio bytes (WAV by default).
    If there’s an HTTP error, prints the status and body for debugging.
    """
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

    if resp.status_code != 200:
        # dump the returned JSON or text so we can see the error message
        try:
            print("TTS error response JSON:", resp.json())
        except Exception:
            print("TTS error response text:", resp.text)
        resp.raise_for_status()

    return resp.content


app = Flask(__name__)


@app.route("/analyze_image", methods=["POST"])
def analyze_image():
    # 1) receive an image file
    if "image" not in request.files:
        return jsonify({"error": "No image file provided"}), 400
    img = request.files["image"]

    # 2) save to temp and upload
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        img.save(tmp.name)
        local_path = tmp.name

    image_url = upload_image_to_cloudinary(local_path)
    context = generate_image_context_grok(image_url)

    # 3) return the vision context
    return jsonify({"context": context})

@app.route("/")
def home():
    return "Welcome to NavigAid!"
    
@app.route("/ask_question", methods=["POST"])
def ask_question():
    # 1) get the image context from the client
    
    context = request.form.get("context")
    if not context:
        return jsonify({"error": "No context provided"}), 400

    # 2) receive audio file
    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided"}), 400
    audio = request.files["audio"]

    # 3) save to temp and translate
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        audio.save(tmp.name)
        audio_path = tmp.name

    translated_question = translate_audio(audio_path)

    # 4) ask your vision QA model
    final_answer = answer_user_question(context, translated_question)

    # 5) render answer as speech
    mp3_bytes = text_to_speech(
        final_answer,
        model="playai-tts",
        voice="Mitch-PlayAI",
        response_format="mp3"
    )

    # 6) return raw WAV data
    return Response(mp3_bytes, mimetype="audio/mpeg")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
