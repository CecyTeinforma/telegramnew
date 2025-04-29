from flask import Flask, request
import os
import requests
import openai
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)

# Obtener valores del .env
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Configurar APIs
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
openai.api_key = OPENAI_API_KEY

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

        # Obtener respuesta de ChatGPT
        bot_response = obtener_respuesta_chatgpt(user_message)
        print(f"🤖 Respuesta generada: {bot_response}")

        # Enviar respuesta a Telegram
        enviar_mensaje_telegram(chat_id, bot_response)

    return 'ok', 200


def obtener_respuesta_chatgpt(mensaje_usuario):
    try:
        system_message = (
            "Eres Cecy, una amiga cercana y empática. 🧡 Ayudas a adolescentes con temas delicados como drogadicción, bullying, embarazo no deseado, etc. Siempre usas un tono amable y cercano."
        )

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": mensaje_usuario}
            ]
        )
        print(f"📤 Respuesta de OpenAI: {response}")  # Agregar log de respuesta
        return response['choices'][0]['message']['content']

    except Exception as e:
        print("❌ Error al obtener respuesta de ChatGPT:", e)
        return "Lo siento, por ahora no pude entender tu mensaje en este momento. 😔"


def enviar_mensaje_telegram(chat_id, texto):
    payload = {
        'chat_id': chat_id,
        'text': texto
    }
    response = requests.post(TELEGRAM_API_URL, json=payload)
    print("Respuesta de Telegram:", response.text)

#if __name__ == '__main__':
#   app.run(host='0.0.0.0', port=5001, debug=True)
    