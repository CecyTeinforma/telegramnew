from flask import Flask, request
import os
import requests
import openai
from dotenv import load_dotenv
from collections import defaultdict
conversaciones = defaultdict(list)
# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)

# Obtener valores del .env
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Configurar APIs
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
openai.api_key = OPENAI_API_KEY
WEBHOOK_URL = 'https://cecytelegram.onrender.com/webhook'  # URL de tu webhook

# Configurar el webhook de Telegram
def set_telegram_webhook():
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook'
    payload = {'url': WEBHOOK_URL}
    response = requests.post(url, json=payload)
    print("Respuesta de Telegram al configurar el webhook:", response.json())

# Llamar a esta función cuando inicie el servidor
set_telegram_webhook()

@app.route('/', methods=['GET'])
def home():
    return '✅ CecyBot para Telegram está activo.'
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    print("📥 Datos recibidos del webhook:", data)

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        user_message = data["message"]["text"]
        print(f"💬 Mensaje recibido: {user_message}")

        # Detectar saludo o despedida
        if user_message.lower() in ["hola", "buenos días", "hey", "hi"]:
            conversaciones[chat_id] = []  # reinicia conversación
        elif user_message.lower() in ["adiós", "bye", "nos vemos", "gracias"]:
            conversaciones[chat_id] = []  # termina conversación

        # Obtener respuesta de ChatGPT con historial
        bot_response = obtener_respuesta_chatgpt(chat_id, user_message)
        print(f"🤖 Respuesta generada: {bot_response}")

        enviar_mensaje_telegram(chat_id, bot_response)

    return 'ok', 200



def obtener_respuesta_chatgpt(chat_id, mensaje_usuario):
    try:
        # Si es la primera vez, agregamos el mensaje system
        if not conversaciones[chat_id]:
            conversaciones[chat_id].append({
                "role": "system",
                "content": (
                    "Eres Cecy, una asistente amable e inteligente que conversa de forma natural. "
                    "Mantén el foco en el tema que el usuario está tratando, pero si detectas un cambio de tema, adáptate. "
                    "No saludes a cada rato, solo al principio o si el usuario lo hace. "
                    "Cuando el usuario se despida, termina la conversación. Sé clara, breve y útil."
                )
            })

        # Agrega mensaje del usuario
        conversaciones[chat_id].append({
            "role": "user",
            "content": mensaje_usuario
        })

        # Limita el historial si es muy largo
        if len(conversaciones[chat_id]) > 15:
            conversaciones[chat_id] = conversaciones[chat_id][-15:]

        # Llamada a OpenAI
        respuesta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=conversaciones[chat_id]
        )

        # Guardar respuesta en el historial
        contenido = respuesta["choices"][0]["message"]["content"]
        conversaciones[chat_id].append({
            "role": "assistant",
            "content": contenido
        })

        return contenido.strip()

    except Exception as e:
        print("❌ Error al obtener respuesta de ChatGPT:", e)
        return "Lo siento, ocurrió un error al procesar tu mensaje."


# Función para enviar el mensaje a Telegram
def enviar_mensaje_telegram(chat_id, texto):
    payload = {
        'chat_id': chat_id,
        'text': texto
    }
    response = requests.post(TELEGRAM_API_URL, json=payload)
    print("Respuesta de Telegram:", response.text)

if __name__ == '__main__':
    # Configurar el webhook cuando el servidor arranque
    set_telegram_webhook()
    app.run(host='0.0.0.0', port=5001, debug=True)