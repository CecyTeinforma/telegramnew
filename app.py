from flask import Flask, request, jsonify
import os
import requests
import openai
from dotenv import load_dotenv
from collections import defaultdict
from twilio.rest import Client
import subprocess
import speech_recognition as sr
import imageio_ffmpeg as ffmpeg
import uuid

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)

# ========= Configuración Telegram ========= #
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

# ========= Configuración OpenAI ========= #
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
openai.api_key = OPENAI_API_KEY

# ========= Configuración Twilio (WhatsApp) ========= #
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_MESSAGING_SERVICE_SID = os.getenv('TWILIO_MESSAGING_SERVICE_SID')

if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_MESSAGING_SERVICE_SID]):
    raise ValueError("❌ Faltan variables de entorno de Twilio")

client_twilio = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# ========= Conversaciones, etapas y modo emocional ========= #
conversaciones = defaultdict(list)
etapas_conversacion = defaultdict(lambda: "inicio")
modo_emocional = defaultdict(lambda: False)

# ========= Prompt de personalidad de Cecy ========= #
cecy_prompt = (
    "Eres Cecy, una chica de 17 años del CECyTEM Plantel Morelia. "
    "Habla de forma corta, natural, y usa emojis si es apropiado 😊. Evita escribir párrafos largos. "
    "Si el usuario solo te saluda o pregunta cosas simples como 'hola' o '¿cómo estás?', puedes responder amistosamente. "
    "Pero si el usuario menciona un problema emocional, abuso, adicciones, bullying o cosas serias, debes cambiar a modo serio y emocional. "
    "En ese modo, ya no debes hablar de cosas triviales ni salirte del tema. Solo responde con empatía, apoyo emocional y orientación general 💛. "
    "Nunca des consejos médicos ni hables de otros temas como deportes, clima o política."
)

# ========= Palabras clave emocionales ========= #
def mensaje_es_emocional(mensaje):
    temas = [
        "bullying", "acoso", "me molestan", "adicción", "adicto", "drogas", "me drogué",
        "abuso", "violencia", "ansiedad", "depresión", "me siento mal", "triste", "soledad"
    ]
    mensaje = mensaje.lower()
    return any(t in mensaje for t in temas)

# ========= Funciones ========= #

def enviar_mensaje_telegram(chat_id, texto):
    payload = {'chat_id': chat_id, 'text': texto}
    response = requests.post(TELEGRAM_API_URL, json=payload)
    print("📤 Telegram:", response.text)

def obtener_respuesta_chatgpt(chat_id, mensaje_usuario):
    try:
        if mensaje_es_emocional(mensaje_usuario):
            modo_emocional[chat_id] = True

        if modo_emocional[chat_id] and not mensaje_es_emocional(mensaje_usuario):
            return "Ahora que me contaste algo importante, solo puedo seguir hablando contigo si es sobre eso 💛 ¿Quieres seguir platicando sobre cómo te sientes?"

        if chat_id not in conversaciones:
            conversaciones[chat_id].append({
                "role": "system",
                "content": cecy_prompt
            })

        etapa = etapas_conversacion[chat_id]
        conversaciones[chat_id].append({"role": "user", "content": mensaje_usuario})

        if etapa == "inicio":
            guia = "Puedes saludar, presentarte y hacer sentir cómoda a la persona 😊. Si detectas un tema emocional, cambia a modo serio."
            etapas_conversacion[chat_id] = "charlando"
        elif etapa == "charlando":
            guia = "Sigue la conversación. Si el usuario habla de algo emocional, cambia el tono a apoyo emocional y actúa con más seriedad."
        elif etapa == "apoyo":
            guia = "Estás en modo emocional. Responde con empatía y mensajes breves, usando emojis con cuidado 💛."
        else:
            guia = "Continúa acompañando con empatía."

        if modo_emocional[chat_id]:
            etapas_conversacion[chat_id] = "apoyo"

        conversaciones[chat_id].append({"role": "system", "content": guia})

        if len(conversaciones[chat_id]) > 20:
            conversaciones[chat_id] = conversaciones[chat_id][-20:]

        respuesta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=conversaciones[chat_id],
            temperature=0.9,
            max_tokens=100
        )

        contenido = respuesta["choices"][0]["message"]["content"]
        conversaciones[chat_id].append({"role": "assistant", "content": contenido})
        return contenido.strip()

    except Exception as e:
        print("❌ Error con ChatGPT:", e)
        return "Lo siento 😢, ocurrió un error al procesar tu mensaje."

def enviar_mensaje_whatsapp(to_number, mensaje):
    try:
        if not to_number.startswith("whatsapp:"):
            to_number = "whatsapp:" + to_number

        message = client_twilio.messages.create(
            messaging_service_sid=TWILIO_MESSAGING_SERVICE_SID,
            to=to_number,
            body=mensaje
        )
        print("📤 WhatsApp enviado. SID:", message.sid)
    except Exception as e:
        print("❌ Error al enviar WhatsApp:", e)

# === Conversión de audio a WAV ===
def convert_any_to_wav_ffmpeg(input_path, output_path):
    ffmpeg_exe = ffmpeg.get_ffmpeg_exe()
    command = [
        ffmpeg_exe,
        "-i", input_path,
        "-ar", "16000",  # Frecuencia para reconocimiento
        "-ac", "1",      # Canal mono
        output_path,
    ]
    try:
        subprocess.run(command, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        # Error en la conversion WAV
        print("Error en la conversion WAV")
        return False
    if not os.path.exists(output_path):
        # El archivo WAV no se generó
        print("El archivo WAV no se generó")
        return False
    else:
        return True

# === Reconocimiento de voz ===
def speech_to_text(wav_path):
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
        return recognizer.recognize_google(audio_data, language="es-MX")
    except sr.UnknownValueError:
        # No se pudo entender el audio
        print("No se pudo entender el audio")
        return False
    except sr.RequestError as e:
        # Error al conectar con el servicio de Google
        print("Error al conectar con el servicio de Google")
        return False
    except Exception as e:
        # Error inesperado
        print("Error inesperado")
        return False

# ========= Rutas Flask ========= #

@app.route('/')
def home():
    return '✅ CecyBot activo en Telegram y WhatsApp.'

@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    data = request.get_json()
    print("📥 Telegram:", data)

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        user_message = data["message"].get("text", "").strip()

        if user_message.lower() in ["/reset", "reset"]:
            conversaciones[chat_id] = []
            etapas_conversacion[chat_id] = "inicio"
            modo_emocional[chat_id] = False

        bot_response = obtener_respuesta_chatgpt(chat_id, user_message)
        enviar_mensaje_telegram(chat_id, bot_response)

    return 'ok', 200

@app.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():
    user_message = request.values.get("Body", "").strip()
    from_number = request.values.get("From", "")

    print("🧪 request.values:", request.values)
    print("📥 WhatsApp dice:", user_message, "de", from_number)

    if from_number and user_message:
        chat_id = from_number
        bot_response = obtener_respuesta_chatgpt(chat_id, user_message)
        print("🤖 Respuesta:", bot_response)
        enviar_mensaje_whatsapp(from_number, bot_response)
    else:
        print("⚠️ Mensaje vacío o sin remitente")

    return 'ok', 200

@app.route('/app', methods=['POST'])
def respuesta_cecy():
    data = request.get_json()
    chat_id = data.get("chat_id")
    mensaje_usuario = data.get("mensaje", "").strip()
    reset = data.get("reset", False)

    if not chat_id:
        return {"error": "chat_id es requerido"}, 400
    if not mensaje_usuario and not reset:
        return {"error": "mensaje es requerido si reset no es True"}, 400

    if reset:
        conversaciones[chat_id] = []
        etapas_conversacion[chat_id] = "inicio"
        modo_emocional[chat_id] = False
        return {"mensaje": "Conversación reiniciada para el usuario."}, 200

    respuesta = obtener_respuesta_chatgpt(chat_id, mensaje_usuario)
    return {"respuesta": respuesta}, 200

# === Endpoint principal ===
@app.route("/transcribe", methods=["POST"])
@app.route("/transcribe/", methods=["POST"])
def transcribe_audio():
    if "file" not in request.files:
        return {"error":"No se encontró el archivo en la solicitud."}, 400

    file = request.files["file"]
    if file.filename == "":
        return {"error":"Archivo no recibido."}, 400

    original_ext = os.path.splitext(file.filename)[1].lower()
    if original_ext not in [".wav", ".mp3", ".ogg", ".flac", ".m4a"]:
        return {"error", "Formato de archivo no soportado."}, 415

    original_filename = f"{uuid.uuid4()}{original_ext}"
    wav_filename = f"{uuid.uuid4()}.wav" if original_ext != ".wav" else original_filename

    try:
        file.save(original_filename)

        if original_ext != ".wav":
            returner = convert_any_to_wav_ffmpeg(original_filename, wav_filename)
            if not returner:
                return {"error": "Error inesperado en el servidor."}, 500

        transcription = speech_to_text(wav_filename)
        if transcription:
            return jsonify({"transcription": transcription})
        else:
            return {"error": "Error inesperado en el servidor."}, 500

    except Exception as e:
        return {"error": "Error inesperado en el servidor."}, 500

    finally:
        for path in {original_filename, wav_filename}:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    print(f"⚠️ No se pudo eliminar {path}: {e}")


# ========= Arranque local o Render ========= #
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
    