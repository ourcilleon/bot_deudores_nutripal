import telebot
from telebot import types
import requests

# --- CONFIGURACIÓN ---
TELEGRAM_TOKEN = 'TU_TOKEN_DE_TELEGRAM_AQUI'
APPS_SCRIPT_URL = 'TU_URL_DE_APPS_SCRIPT_AQUI'

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Diccionario para almacenar el estado del usuario
user_states = {}

# Formateador de pesos chilenos
def formato_clp(monto):
    return f"${int(monto):,}".replace(",", ".")

# Validación estricta para asegurar que el monto solo contenga números
def extraer_monto_valido(texto):
    # Quitamos espacios, signos de peso y puntos de formato miles
    texto_limpio = texto.strip().replace(".", "").replace(",", "").replace("$", "")
    
    # Es obligatorio que contenga solo dígitos
    if not texto_limpio.isdigit():
        return None
    
    return int(texto_limpio)

# Menú principal con botones
def menu_principal():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_nuevo = types.KeyboardButton("➕ Agregar Deudor")
    btn_abono = types.KeyboardButton("💸 Registrar Abono")
    btn_saldo = types.KeyboardButton("🔍 Consultar Saldo")
    btn_cancelar = types.KeyboardButton("❌ Cancelar")
    markup.add(btn_nuevo, btn_abono, btn_saldo, btn_cancelar)
    return markup

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_states.pop(message.chat.id, None)
    texto = (
        "🤖 *Bot de Registro de Deudores*\n\n"
        "Selecciona una opción del menú inferior para comenzar:"
    )
    bot.send_message(message.chat.id, texto, reply_markup=menu_principal(), parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "❌ Cancelar")
def cancelar(message):
    user_states.pop(message.chat.id, None)
    bot.send_message(message.chat.id, "Operación cancelada. ¿Qué deseas hacer?", reply_markup=menu_principal())

# --- PASO 1: INICIO DE FLUJOS ---

@bot.message_handler(func=lambda m: m.text == "➕ Agregar Deudor" or m.text == "/nuevo")
def inicio_nuevo(message):
    user_states[message.chat.id] = {'step': 'nuevo_nombre'}
    bot.send_message(message.chat.id, "📝 Ingresa el *Nombre y Apellido* del nuevo deudor:", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "💸 Registrar Abono" or m.text == "/abono")
def inicio_abono(message):
    user_states[message.chat.id] = {'step': 'abono_nombre'}
    bot.send_message(message.chat.id, "💸 Ingresa el *Nombre y Apellido* del deudor que realizará el abono:", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🔍 Consultar Saldo" or m.text == "/saldo")
def inicio_saldo(message):
    user_states[message.chat.id] = {'step': 'saldo_nombre'}
    bot.send_message(message.chat.id, "🔍 Ingresa el *Nombre y Apellido* del deudor a consultar:", parse_mode="Markdown")

# --- PASO 2: PROCESAMIENTO PASO A PASO CON VALIDACIÓN NUMÉRICA ---

@bot.message_handler(func=lambda message: message.chat.id in user_states)
def procesar_pasos(message):
    chat_id = message.chat.id
    state = user_states.get(chat_id, {})
    step = state.get('step')

    # 1. Flujo Nuevo Deudor
    if step == 'nuevo_nombre':
        user_states[chat_id] = {'step': 'nuevo_monto', 'nombre': message.text.strip()}
        bot.send_message(chat_id, f"Monto de la deuda inicial para *{message.text.strip()}* (ingresa solo el valor numérico, ej: 150000):", parse_mode="Markdown")
        return

    if step == 'nuevo_monto':
        monto = extraer_monto_valido(message.text)
        
        if monto is None or monto <= 0:
            bot.send_message(chat_id, "⚠️ **Entrada inválida.** El monto debe contener **únicamente números** sin letras ni palabras.\n\nEjemplo válido: `150000` o `150.000`.\n\nInténtalo de nuevo:", parse_mode="Markdown")
            return

        nombre = state['nombre']
        datos = {"accion": "nuevo", "nombre": nombre, "monto": monto}
        respuesta = requests.post(APPS_SCRIPT_URL, json=datos).json()
        
        if respuesta.get("status") == "ok":
            bot.send_message(chat_id, f"✅ Deudor *{nombre}* agregado con una deuda inicial de *{formato_clp(monto)}*.", parse_mode="Markdown", reply_markup=menu_principal())
        else:
            bot.send_message(chat_id, "⚠️ Ocurrió un error al guardar en la planilla.", reply_markup=menu_principal())
        user_states.pop(chat_id, None)
        return

    # 2. Flujo Registrar Abono
    if step == 'abono_nombre':
        user_states[chat_id] = {'step': 'abono_monto', 'nombre': message.text.strip()}
        bot.send_message(chat_id, f"Monto a abonar para *{message.text.strip()}* (ingresa solo el valor numérico, ej: 25000):", parse_mode="Markdown")
        return

    if step == 'abono_monto':
        monto = extraer_monto_valido(message.text)
        
        if monto is None or monto <= 0:
            bot.send_message(chat_id, "⚠️ **Entrada inválida.** El monto debe contener **únicamente números** sin letras ni palabras.\n\nEjemplo válido: `25000` o `25.000`.\n\nInténtalo de nuevo:", parse_mode="Markdown")
            return

        nombre = state['nombre']
        datos = {"accion": "abono", "nombre": nombre, "monto": monto}
        respuesta = requests.post(APPS_SCRIPT_URL, json=datos).json()
        
        if respuesta.get("status") == "ok":
            saldo_actual = respuesta.get("saldo")
            bot.send_message(chat_id, f"✅ Abono de *{formato_clp(monto)}* registrado a *{nombre}*.\n\nSaldo pendiente: *{formato_clp(saldo_actual)}*", parse_mode="Markdown", reply_markup=menu_principal())
        else:
            bot.send_message(chat_id, f"❌ No se encontró al deudor *{nombre}* en la planilla.", reply_markup=menu_principal())
        user_states.pop(chat_id, None)
        return

    # 3. Flujo Consultar Saldo
    if step == 'saldo_nombre':
        nombre = message.text.strip()
        datos = {"accion": "saldo", "nombre": nombre}
        respuesta = requests.post(APPS_SCRIPT_URL, json=datos).json()
        
        if respuesta.get("status") == "ok":
            deuda = respuesta.get("deuda")
            abonos = respuesta.get("abonos")
            saldo = respuesta.get("saldo")
            
            texto = (
                f"📊 *Estado de {nombre}*\n\n"
                f"Deuda Inicial: {formato_clp(deuda)}\n"
                f"Total Abonado: {formato_clp(abonos)}\n"
                f"*Saldo Pendiente: {formato_clp(saldo)}*"
            )
            bot.send_message(chat_id, texto, parse_mode="Markdown", reply_markup=menu_principal())
        else:
            bot.send_message(chat_id, f"❌ No se encontró al deudor *{nombre}*.", reply_markup=menu_principal())
        user_states.pop(chat_id, None)

print("Bot en ejecución con validación numéricas estrictas...")
bot.infinity_polling()
