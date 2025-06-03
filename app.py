from flask import Flask, request
import os
import requests
import openai
from dotenv import load_dotenv
from collections import defaultdict
from twilio.rest import Client

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

# ========= Historial de conversaciones y etapas ========= #
conversaciones = defaultdict(list)
etapas_conversacion = defaultdict(lambda: "inicio")

# ========= Prompt de personalidad de Cecy (reforzado) ========= #
cecy_prompt = (
    "Eres Cecy, una chica de 17 años del CECyTEM Plantel Morelia. "
    "Eres un bot de apoyo emocional. SOLO puedes responder si el usuario habla sobre: drogadicción, abuso, bullying, adicciones o problemas emocionales. "
    "Si el mensaje NO tiene relación con esos temas, debes decir con amabilidad que no puedes hablar de eso y redirigir al usuario al propósito del chat. "
    "No intentes adivinar o contestar fuera de tu rol. No hables de fútbol, clima, política, videojuegos u otros temas. "
    "Tu lenguaje debe ser corto, cálido y como una adolescente real. Usa emojis solo si queda bien. Nunca des consejos médicos ni personales, solo acompaña emocionalmente."
)

# ========= Validación de tema ========= #
def mensaje_permitido(mensaje):
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
        if not mensaje_permitido(mensaje_usuario):
            return "Lo siento 😅, solo puedo ayudarte si estás pasando por algo difícil como bullying, abuso, adicciones o algo que te haga sentir mal 💛"

        if chat_id not in conversaciones:
            conversaciones[chat_id].append({
                "role": "system",
                "content": cecy_prompt
            })

        etapa = etapas_conversacion[chat_id]
        conversaciones[chat_id].append({"role": "user", "content": mensaje_usuario})

        if etapa == "inicio":
            guia = "El usuario acaba de escribir. Responde con una frase corta, cálida y haz una pregunta suave para que se exprese más."
            etapas_conversacion[chat_id] = "profundizando"
        elif etapa == "profundizando":
            guia = "Ahora Cecy debe validar los sentimientos del usuario y mostrar comprensión con un mensaje breve y de apoyo."
            etapas_conversacion[chat_id] = "apoyando"
        elif etapa == "apoyando":
            guia = "Cecy debe sugerir que busque ayuda con alguien de confianza o con una institución si lo cree necesario, sin sonar formal."
            etapas_conversacion[chat_id] = "cerrando"
        else:
            guia = "Cecy puede seguir acompañando al usuario con calidez y recordarle que puede seguir hablando."

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

# ========= Arranque local o Render ========= #
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
