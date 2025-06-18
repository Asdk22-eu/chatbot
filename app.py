import os
import json
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import logging
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
import re

# Cargar variables de entorno
load_dotenv()

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Inicializar Flask
app = Flask(__name__)

# Configuración de Twilio
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_NUMBER')

# Inicializar cliente de Twilio
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Inicializar Firebase
cred = credentials.Certificate(os.getenv('FIREBASE_CREDENTIALS_PATH'))
firebase_admin.initialize_app(cred)
db = firestore.client()

# Estados del formulario
FORM_STATES = {
    'START': 'start',
    'NOMBRE': 'waiting_nombre',
    'CEDULA': 'waiting_cedula',
    'CORREO': 'waiting_correo',
    'TELEFONO': 'waiting_telefono',
    'TELEFONO2': 'waiting_telefono2',
    'DIRECCION': 'waiting_direccion',
    'BARRIO': 'waiting_barrio',
    'PROVINCIA': 'waiting_provincia',
    'SERVICIO': 'waiting_servicio',
    'TIPO_VENTA': 'waiting_tipo_venta',
    'TIPO_PAGO': 'waiting_tipo_pago',
    'NUM_CUENTA': 'waiting_num_cuenta',
    'COORDENADAS': 'waiting_coordenadas',
    'OBSERVACIONES': 'waiting_observaciones',
    'COMPLETED': 'completed'
}

# Preguntas del formulario
FORM_QUESTIONS = {
    FORM_STATES['NOMBRE']: " **FORMULARIO DE VISITA DE VENTAS** \n\n¡Hola! Vamos a registrar una nueva visita de ventas.\n\n👤 **Paso 1:** ¿Cuál es el nombre completo del cliente?",
    FORM_STATES['CEDULA']: " **Paso 2:** Ingresa el número de cédula del cliente (sin guiones ni espacios):",
    FORM_STATES['CORREO']: " **Paso 3:** ¿Cuál es el correo electrónico del cliente?",
    FORM_STATES['TELEFONO']: " **Paso 4:** Ingresa el teléfono principal del cliente:",
    FORM_STATES['TELEFONO2']: " **Paso 5:** ¿Tiene un teléfono secundario? (Si no tiene, escribe 'NO'):",
    FORM_STATES['DIRECCION']: " **Paso 6:** Ingresa la dirección completa del cliente:",
    FORM_STATES['BARRIO']: " **Paso 7:** ¿En qué barrio/sector se encuentra?",
    FORM_STATES['PROVINCIA']: " **Paso 8:** Selecciona la provincia:\n\n1️⃣ Guayas\n2️⃣ Pichincha\n3️⃣ Manabí\n4️⃣ El Oro\n5️⃣ Los Ríos\n6️⃣ Otra\n\nEscribe el número:",
    FORM_STATES['SERVICIO']: " **Paso 9:** Selecciona el servicio de interés:\n\n1️⃣ Internet Fijo\n2️⃣ Internet Móvil\n3️⃣ Telefonía\n4️⃣ TV Cable\n5️⃣ Paquete Combo\n\nEscribe el número:",
    FORM_STATES['TIPO_VENTA']: " **Paso 10:** Selecciona el tipo de venta:\n\n1️⃣ Nueva Instalación\n2️⃣ Renovación\n3️⃣ Upgrade\n4️⃣ Adicional\n\nEscribe el número:",
    FORM_STATES['TIPO_PAGO']: " **Paso 11:** ¿Cuál es la forma de pago preferida?\n\n1️⃣ Ventanilla\n2️⃣ Débito Automático\n3️⃣ Transferencia\n4️⃣ Efectivo\n\nEscribe el número:",
    FORM_STATES['NUM_CUENTA']: " **Paso 12:** Si tiene cuenta bancaria para débito, ingresa el número (si no aplica, escribe 'NO'):",
    FORM_STATES['COORDENADAS']: " **Paso 13:** Por favor, comparte tu ubicación actual para registrar las coordenadas de la visita.\n\n*Si no puedes compartir ubicación, escribe las coordenadas manualmente:*\n\nEjemplo: -2.1234567, -79.9876543",
    FORM_STATES['OBSERVACIONES']: " **Paso 14 (Final):** Agrega cualquier observación importante sobre la visita:"
}

# Opciones de respuesta
PROVINCIA_OPTIONS = {
    '1': {'name': 'Guayas', 'id': '96051UCSRPobUpMUs0Ga'},
    '2': {'name': 'Pichincha', 'id': '96051UCSRPobUpMUs1Pb'},
    '3': {'name': 'Manabí', 'id': '96051UCSRPobUpMUs2Mb'},
    '4': {'name': 'El Oro', 'id': '96051UCSRPobUpMUs3Eo'},
    '5': {'name': 'Los Ríos', 'id': '96051UCSRPobUpMUs4Lr'},
    '6': {'name': 'Otra', 'id': '96051UCSRPobUpMUs5Ot'}
}

SERVICIO_OPTIONS = {
    '1': 'Internet Fijo',
    '2': 'Internet Móvil',
    '3': 'Telefonía',
    '4': 'TV Cable',
    '5': 'Paquete Combo'
}

TIPO_VENTA_OPTIONS = {
    '1': {'name': 'Nueva Instalación', 'id': 'W4E4Zh9gh5D05P2tjRPT'},
    '2': {'name': 'Renovación', 'id': 'W4E4Zh9gh5D05P2tjRP1'},
    '3': {'name': 'Upgrade', 'id': 'W4E4Zh9gh5D05P2tjRP2'},
    '4': {'name': 'Adicional', 'id': 'W4E4Zh9gh5D05P2tjRP3'}
}

TIPO_PAGO_OPTIONS = {
    '1': 'Ventanilla',
    '2': 'Débito Automático',
    '3': 'Transferencia',
    '4': 'Efectivo'
}

class SalesVisitChatbot:
    def __init__(self):
        self.sessions = {}
        # ID del vendedor por defecto (debería venir de autenticación)
        self.default_vendor_id = "5WNxFf3NQzdPO6L1LREz80gBQ1h1"
    
    def send_message(self, to_number, message):
        """Enviar mensaje de WhatsApp via Twilio"""
        try:
            message = twilio_client.messages.create(
                body=message,
                from_=TWILIO_WHATSAPP_NUMBER,
                to=f'whatsapp:{to_number}'
            )
            logger.info(f"Mensaje enviado exitosamente. SID: {message.sid}")
            return True
        except Exception as e:
            logger.error(f"Error enviando mensaje: {e}")
            return False
    
    def get_user_session(self, phone_number):
        """Obtener sesión del usuario"""
        if phone_number not in self.sessions:
            self.sessions[phone_number] = {
                'state': FORM_STATES['START'],
                'data': {},
                'created_at': datetime.now().isoformat()
            }
        return self.sessions[phone_number]
    
    def save_to_firebase(self, phone_number, form_data):
        """Guardar datos del formulario en Firebase"""
        try:
            # Preparar coordenadas
            coordenadas = None
            if form_data.get('coordenadas'):
                coords_text = form_data['coordenadas']
                lat, lng = self.parse_coordinates(coords_text)
                if lat and lng:
                    coordenadas = firestore.GeoPoint(lat, lng)
            
            # Estructura completa para sales_visits
            doc_data = {
                'banco': form_data.get('banco', ''),
                'barrio': form_data.get('barrio', ''),
                'catalogo_servicio': [form_data.get('servicio', '')],
                'cedula': form_data.get('cedula', ''),
                'coordenadas': coordenadas,
                'correo': form_data.get('correo', ''),
                'datos_tecnicos': {
                    'armario': '',
                    'caja': '',
                    'descripción': '',
                    'distribuidor': '',
                    'imei1': '',
                    'imei2': '',
                    'imsi': ''
                },
                'dirección': form_data.get('direccion', ''),
                'distribuidor': None,
                'estado': 'verde',
                'id_cliente': form_data.get('cedula', ''),
                'nombre_cliente': form_data.get('nombre', '').upper(),
                'num_cuenta': form_data.get('num_cuenta', ''),
                'observaciones': form_data.get('observaciones', ''),
                'provincia': form_data.get('provincia_id', ''),
                'teléfono': form_data.get('telefono', ''),
                'telefono2': form_data.get('telefono2', ''),
                'timestamp': firestore.SERVER_TIMESTAMP,
                'tipo_pago': form_data.get('tipo_pago', ''),
                'tipo_venta': form_data.get('tipo_venta_id', ''),
                'vendedorId': self.default_vendor_id
            }
            
            # Guardar en colección 'sales_visits'
            doc_ref = db.collection('sales_visits').add(doc_data)
            logger.info(f"Visita de ventas guardada en Firebase con ID: {doc_ref[1].id}")
            return doc_ref[1].id
        except Exception as e:
            logger.error(f"Error guardando en Firebase: {e}")
            return None
    
    def validate_email(self, email):
        """Validar formato de email"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    def validate_cedula(self, cedula):
        """Validar cédula ecuatoriana básica"""
        cedula = cedula.strip()
        return cedula.isdigit() and len(cedula) in [10, 13]
    
    def validate_phone(self, phone):
        """Validar teléfono ecuatoriano"""
        phone = re.sub(r'[^\d]', '', phone)
        return len(phone) >= 9 and (phone.startswith('09') or phone.startswith('593'))
    
    def parse_coordinates(self, coords_text):
        """Parsear coordenadas desde texto"""
        try:
            coords_text = coords_text.replace('°', '').replace(',', ' ')
            numbers = re.findall(r'-?\d+\.?\d*', coords_text)
            if len(numbers) >= 2:
                lat = float(numbers[0])
                lng = float(numbers[1])
                # Validar rangos aproximados para Ecuador
                if -5 <= lat <= 2 and -82 <= lng <= -75:
                    return lat, lng
        except:
            pass
        return None, None
    
    def process_message(self, phone_number, message_text):
        """Procesar mensaje del usuario"""
        session = self.get_user_session(phone_number)
        current_state = session['state']
        user_data = session['data']
        
        # Estado inicial
        if current_state == FORM_STATES['START']:
            session['state'] = FORM_STATES['NOMBRE']
            return FORM_QUESTIONS[FORM_STATES['NOMBRE']]
        
        # Nombre del cliente
        elif current_state == FORM_STATES['NOMBRE']:
            if len(message_text.strip()) < 5:
                return " Por favor, ingresa el nombre completo del cliente (mínimo 5 caracteres):"
            
            user_data['nombre'] = message_text.strip()
            session['state'] = FORM_STATES['CEDULA']
            return FORM_QUESTIONS[FORM_STATES['CEDULA']]
        
        # Cédula
        elif current_state == FORM_STATES['CEDULA']:
            if not self.validate_cedula(message_text):
                return " Por favor, ingresa una cédula válida:"
            
            user_data['cedula'] = message_text.strip()
            session['state'] = FORM_STATES['CORREO']
            return FORM_QUESTIONS[FORM_STATES['CORREO']]
        
        # Correo
        elif current_state == FORM_STATES['CORREO']:
            if not self.validate_email(message_text.strip()):
                return " Por favor, ingresa un correo electrónico válido:"
            
            user_data['correo'] = message_text.strip().lower()
            session['state'] = FORM_STATES['TELEFONO']
            return FORM_QUESTIONS[FORM_STATES['TELEFONO']]
        
        # Teléfono principal
        elif current_state == FORM_STATES['TELEFONO']:
            if not self.validate_phone(message_text):
                return " Por favor, ingresa un número de teléfono válido (ej: 0987654321):"
            
            user_data['telefono'] = re.sub(r'[^\d]', '', message_text.strip())
            session['state'] = FORM_STATES['TELEFONO2']
            return FORM_QUESTIONS[FORM_STATES['TELEFONO2']]
        
        # Teléfono secundario
        elif current_state == FORM_STATES['TELEFONO2']:
            if message_text.strip().upper() == 'NO':
                user_data['telefono2'] = ''
            else:
                if not self.validate_phone(message_text):
                    return " Por favor, ingresa un teléfono válido o escribe 'NO':"
                user_data['telefono2'] = re.sub(r'[^\d]', '', message_text.strip())
            
            session['state'] = FORM_STATES['DIRECCION']
            return FORM_QUESTIONS[FORM_STATES['DIRECCION']]
        
        # Dirección
        elif current_state == FORM_STATES['DIRECCION']:
            if len(message_text.strip()) < 10:
                return " Por favor, ingresa una dirección más completa (mínimo 10 caracteres):"
            
            user_data['direccion'] = message_text.strip()
            session['state'] = FORM_STATES['BARRIO']
            return FORM_QUESTIONS[FORM_STATES['BARRIO']]
        
        # Barrio
        elif current_state == FORM_STATES['BARRIO']:
            user_data['barrio'] = message_text.strip()
            session['state'] = FORM_STATES['PROVINCIA']
            return FORM_QUESTIONS[FORM_STATES['PROVINCIA']]
        
        # Provincia
        elif current_state == FORM_STATES['PROVINCIA']:
            if message_text.strip() not in PROVINCIA_OPTIONS:
                return "❌ Por favor, selecciona una opción válida (1-6):\n\n" + FORM_QUESTIONS[FORM_STATES['PROVINCIA']].split('\n\n')[1]
            
            provincia = PROVINCIA_OPTIONS[message_text.strip()]
            user_data['provincia'] = provincia['name']
            user_data['provincia_id'] = provincia['id']
            session['state'] = FORM_STATES['SERVICIO']
            return FORM_QUESTIONS[FORM_STATES['SERVICIO']]
        
        # Servicio
        elif current_state == FORM_STATES['SERVICIO']:
            if message_text.strip() not in SERVICIO_OPTIONS:
                return "❌ Por favor, selecciona una opción válida (1-5):\n\n" + FORM_QUESTIONS[FORM_STATES['SERVICIO']].split('\n\n')[1]
            
            user_data['servicio'] = SERVICIO_OPTIONS[message_text.strip()]
            session['state'] = FORM_STATES['TIPO_VENTA']
            return FORM_QUESTIONS[FORM_STATES['TIPO_VENTA']]
        
        # Tipo de venta
        elif current_state == FORM_STATES['TIPO_VENTA']:
            if message_text.strip() not in TIPO_VENTA_OPTIONS:
                return " Por favor, selecciona una opción válida (1-4):\n\n" + FORM_QUESTIONS[FORM_STATES['TIPO_VENTA']].split('\n\n')[1]
            
            tipo_venta = TIPO_VENTA_OPTIONS[message_text.strip()]
            user_data['tipo_venta'] = tipo_venta['name']
            user_data['tipo_venta_id'] = tipo_venta['id']
            session['state'] = FORM_STATES['TIPO_PAGO']
            return FORM_QUESTIONS[FORM_STATES['TIPO_PAGO']]
        
        # Tipo de pago
        elif current_state == FORM_STATES['TIPO_PAGO']:
            if message_text.strip() not in TIPO_PAGO_OPTIONS:
                return " Por favor, selecciona una opción válida (1-4):\n\n" + FORM_QUESTIONS[FORM_STATES['TIPO_PAGO']].split('\n\n')[1]
            
            user_data['tipo_pago'] = TIPO_PAGO_OPTIONS[message_text.strip()]
            session['state'] = FORM_STATES['NUM_CUENTA']
            return FORM_QUESTIONS[FORM_STATES['NUM_CUENTA']]
        
        # Número de cuenta
        elif current_state == FORM_STATES['NUM_CUENTA']:
            if message_text.strip().upper() == 'NO':
                user_data['num_cuenta'] = ''
            else:
                user_data['num_cuenta'] = message_text.strip()
            
            session['state'] = FORM_STATES['COORDENADAS']
            return FORM_QUESTIONS[FORM_STATES['COORDENADAS']]
        
        # Coordenadas
        elif current_state == FORM_STATES['COORDENADAS']:
            user_data['coordenadas'] = message_text.strip()
            session['state'] = FORM_STATES['OBSERVACIONES']
            return FORM_QUESTIONS[FORM_STATES['OBSERVACIONES']]
        
        # Observaciones finales
        elif current_state == FORM_STATES['OBSERVACIONES']:
            user_data['observaciones'] = message_text.strip()
            
            # Guardar en Firebase
            doc_id = self.save_to_firebase(phone_number, user_data)
            
            if doc_id:
                session['state'] = FORM_STATES['COMPLETED']
                
                # Mensaje de confirmación
                confirmation = f"""
✅ **VISITA DE VENTAS REGISTRADA EXITOSAMENTE**

📋 **RESUMEN:**
👤 Cliente: {user_data['nombre']}
📄 Cédula: {user_data['cedula']}
📧 Email: {user_data['correo']}
📱 Teléfono: {user_data['telefono']}
🏠 Dirección: {user_data['direccion']}
🏘️ Barrio: {user_data['barrio']}
🗺️ Provincia: {user_data['provincia']}
🌐 Servicio: {user_data['servicio']}
💼 Tipo de Venta: {user_data['tipo_venta']}
💳 Tipo de Pago: {user_data['tipo_pago']}

🔗 **ID del Registro:** `{doc_id}`

¡Gracias por completar el formulario! La visita ha sido registrada correctamente en el sistema.

Para registrar otra visita, escribe **'nuevo'**
                """.strip()
                
                # Limpiar sesión
                del self.sessions[phone_number]
                return confirmation
            else:
                return " Hubo un error al guardar la información. Por favor, intenta nuevamente escribiendo 'reiniciar'."
        
        # Estado completado
        elif current_state == FORM_STATES['COMPLETED']:
            if message_text.lower() in ['nuevo', 'reiniciar', 'start']:
                del self.sessions[phone_number]
                return " Iniciando nuevo formulario de visita de ventas...\n\n" + FORM_QUESTIONS[FORM_STATES['NOMBRE']]
            else:
                return "Para registrar una nueva visita de ventas, escribe **'nuevo'**"
        
        return " No entendí tu mensaje. Escribe 'nuevo' para comenzar un nuevo registro."

# Inicializar el chatbot
chatbot = SalesVisitChatbot()

@app.route('/webhook', methods=['POST'])
def handle_twilio_webhook():
    """Manejar mensajes entrantes de Twilio WhatsApp"""
    try:
        incoming_msg = request.values.get('Body', '').strip()
        from_number = request.values.get('From', '')
        
        # Extraer número de teléfono
        phone_number = from_number.replace('whatsapp:', '')
        
        logger.info(f"Mensaje recibido de {phone_number}: {incoming_msg}")
        
        # Procesar mensaje
        response_text = chatbot.process_message(phone_number, incoming_msg)
        
        # Crear respuesta TwiML
        resp = MessagingResponse()
        resp.message(response_text)
        
        return str(resp)
    
    except Exception as e:
        logger.error(f"Error procesando webhook: {e}")
        resp = MessagingResponse()
        resp.message(" Error procesando tu mensaje. Intenta escribiendo 'nuevo'.")
        return str(resp)

@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint de salud"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'Sales Visit Chatbot'
    })

@app.route('/sessions', methods=['GET'])
def get_sessions():
    """Ver sesiones activas"""
    return jsonify({
        'active_sessions': len(chatbot.sessions),
        'sessions': chatbot.sessions
    })

if __name__ == '__main__':
    required_vars = ['TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_WHATSAPP_NUMBER', 'FIREBASE_CREDENTIALS_PATH']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Variables de entorno faltantes: {missing_vars}")
        exit(1)
    
    logger.info("Iniciando chatbot de visitas de ventas...")
    app.run(debug=True, host='0.0.0.0', port=5000)
