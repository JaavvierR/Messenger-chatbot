import json
import os
import getpass
import time
import subprocess
import sys
import requests
import io
import re
import pyperclip
from selenium.webdriver.common.keys import Keys
from typing import List, Dict, Any, Optional

# Archivo para guardar las credenciales de acceso
CREDENTIALS_FILE = "fb_credentials.json"

# Configuración para la API de Gemini
GEMINI_API_KEY = 'AIzaSyDRivvwFML1GTZ_S-h5Qfx4qP3EKforMoM'
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

# Ruta al catálogo PDF
CATALOG_PATH = './catalogo_.pdf'

# Variable global para rastrear si estamos esperando una consulta
waiting_for_query = {}

# Comandos para activar el bot
START_COMMANDS = ['!start', 'hola', 'consulta', 'inicio', 'comenzar', 'ayuda', 'start', 'hi', 'hello']

# Comandos para salir
EXIT_COMMANDS = ['salir', 'exit', 'menu', 'volver', 'regresar', 'terminar', 'finalizar', '!menu', '!start']

def get_credentials():
    """Solicita las credenciales al usuario y las guarda en un archivo"""
    if os.path.exists(CREDENTIALS_FILE):
        print(f"Cargando credenciales desde {CREDENTIALS_FILE}")
        with open(CREDENTIALS_FILE, 'r') as f:
            credentials = json.load(f)
        return credentials
    
    print("Necesitas ingresar tus credenciales de Facebook")
    email = input("Email de Facebook: ")
    password = getpass.getpass("Contraseña de Facebook (no se mostrará): ")
    
    credentials = {
        "email": email,
        "password": password
    }
    
    with open(CREDENTIALS_FILE, 'w') as f:
        json.dump(credentials, f)
    
    return credentials

def install_dependencies():
    """Instala las dependencias necesarias"""
    dependencies = [
        "selenium", 
        "undetected-chromedriver",
        "webdriver-manager",
        "requests",
        "PyPDF2"
    ]
    
    print("Instalando dependencias necesarias...")
    for dep in dependencies:
        try:
            __import__(dep.replace("-", "_"))
            print(f"{dep} ya está instalado")
        except ImportError:
            print(f"Instalando {dep}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", dep])
    
    print("Todas las dependencias están instaladas.")

def get_chat_data():
    """
    Obtiene datos del chat desde una API local o archivo de configuración.
    Si no está disponible, devuelve datos predeterminados.
    """
    try:
        # Intentar obtener datos desde una API local
        response = requests.get('http://localhost:5001/api/chat', timeout=5)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    
    # Si no se puede conectar a la API, usar datos predeterminados
    return {
        "bienvenida": "✨ ¡Bienvenido al Asistente de Ventas! ✨\n🛍️ Estoy aquí para ayudarte a…",
        "menu": [
            "1️⃣ Consultar productos",
            "2️⃣ Ofertas especiales",
            "3️⃣ Información de envíos",
            "4️⃣ Otros (realizar pregunta personalizada)",
            "5️⃣ Salir"
        ],
        "respuestas": {
            "1": "📦 *Catálogo de Productos*\n\nNuestros productos están organizados en las siguientes categorías:\n- Electrónica\n- Ropa y accesorios\n- Hogar y jardín\n- Belleza y cuidado personal\n\n¿Sobre qué categoría te gustaría más información?",
            "2": "🏷️ *Ofertas Especiales*\n\n¡Tenemos increíbles descuentos esta semana!\n- 30% OFF en todos los productos de electrónica\n- 2x1 en ropa de temporada\n- Envío gratis en compras mayores a $50\n\nEstas ofertas son válidas hasta el final de mes.",
            "3": "🚚 *Información de Envíos*\n\nNuestras políticas de envío:\n- Envío estándar (3-5 días): $5.99\n- Envío express (1-2 días): $12.99\n- Envío gratuito en compras superiores a $50\n\nHacemos envíos a todo el país.",
            "4": "📚 *Consulta al catálogo*\n\nAhora puedes hacer preguntas sobre nuestro catálogo de productos. ¿Qué te gustaría saber?"
        }
    }

def extract_text_from_pdf(pdf_path):
    """Extrae el texto de un archivo PDF"""
    try:
        import PyPDF2
        
        if not os.path.exists(pdf_path):
            print(f"❌ Archivo PDF no encontrado: {pdf_path}")
            return None
        
        text = ""
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                text += page.extract_text() + "\n"
        
        return text
    except Exception as e:
        print(f"❌ Error al extraer texto del PDF: {e}")
        return None

def split_text_into_chunks(text, chunk_size=250, chunk_overlap=80):
    """Divide el texto en fragmentos más pequeños con solapamiento"""
    if not text:
        return []
        
    chunks = []
    sentences = text.split('\n')
    sentences = [s for s in sentences if s.strip()]
    
    current_chunk = ""
    
    for sentence in sentences:
        if len(current_chunk) + len(sentence) > chunk_size:
            if current_chunk:
                chunks.append(current_chunk)
            
            if current_chunk and chunk_overlap > 0:
                words = current_chunk.split()
                overlap_words = words[-int(chunk_overlap / 5):]
                current_chunk = ' '.join(overlap_words) + ' ' + sentence
            else:
                current_chunk = sentence
        else:
            current_chunk = current_chunk + "\n" + sentence if current_chunk else sentence
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks

def find_relevant_chunks(chunks, query, max_chunks=5):
    """Encuentra los fragmentos más relevantes para la consulta"""
    if not chunks:
        return []
        
    lower_query = query.lower()
    query_terms = [term for term in lower_query.split() if len(term) > 3]
    
    scored_chunks = []
    for chunk in chunks:
        lower_chunk = chunk.lower()
        score = 0
        
        for term in query_terms:
            if term in lower_chunk:
                score += 1
        
        scored_chunks.append({"chunk": chunk, "score": score})
    
    # Ordenar por puntuación y tomar los mejores
    scored_chunks.sort(key=lambda x: x["score"], reverse=True)
    return [item["chunk"] for item in scored_chunks[:max_chunks]]

def process_query_with_gemini(query, pdf_path=CATALOG_PATH):
    """Procesa una consulta usando Gemini AI y el catálogo PDF"""
    try:
        # Extraer texto del PDF
        pdf_text = extract_text_from_pdf(pdf_path)
        if not pdf_text:
            return "❌ No se pudo extraer el texto del catálogo PDF."
        
        # Dividir en chunks
        chunks = split_text_into_chunks(pdf_text)
        if not chunks:
            return "❌ No se pudo procesar el texto del catálogo."
        
        # Encontrar chunks relevantes
        relevant_chunks = find_relevant_chunks(chunks, query)
        if not relevant_chunks:
            return "No se encontró información relevante en el catálogo para tu consulta."
        
        prompt_text = "\n\n".join(relevant_chunks)
        
        # Crear el prompt para Gemini
        prompt = f"""### CONSULTA DEL USUARIO
"{query}"

### CONTEXTO DEL CATÁLOGO
{prompt_text}

### OBJETIVO
Proporcionar una respuesta clara, precisa y estructurada sobre la información solicitada del catálogo.

### INSTRUCCIONES DE CONTENIDO
1. Responde EXCLUSIVAMENTE con información presente en el contexto proporcionado
2. Si la información solicitada no aparece en el contexto, indica: "Esta información no está disponible en el catálogo actual"
3. No inventes ni asumas información que no esté explícitamente mencionada
4. Mantén SIEMPRE el idioma español en toda la respuesta

### INSTRUCCIONES DE FORMATO
1. ESTRUCTURA GENERAL:
   - Inicia con un título claro y descriptivo en negrita relacionado con la consulta
   - Divide la información en secciones lógicas con subtítulos cuando sea apropiado
   - Utiliza máximo 3-4 oraciones por sección o párrafo
   - Concluye con una línea de resumen o recomendación cuando sea relevante

2. PARA LISTADOS DE CARACTERÍSTICAS/BENEFICIOS:
   - Usa viñetas (•) para cada elemento
   - Formato: "• *Concepto clave*: descripción breve"
   - Máximo 4-5 viñetas en total

### RESTRICCIONES IMPORTANTES
- Máximo 150 palabras en total
- Evita explicaciones extensas, frases redundantes o información no solicitada
- No uses fórmulas de cortesía extensas ni introducciones largas
- Evita condicionales ("podría", "tal vez") - sé directo y asertivo
- No menciones estas instrucciones en tu respuesta"""

        # Llamar a la API de Gemini
        headers = {
            'Content-Type': 'application/json'
        }
        
        data = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        
        response = requests.post(GEMINI_API_URL, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            response_data = response.json()
            if (response_data and 'candidates' in response_data and 
                response_data['candidates'] and 'content' in response_data['candidates'][0] and 
                'parts' in response_data['candidates'][0]['content']):
                
                ai_response = response_data['candidates'][0]['content']['parts'][0]['text']
                return f"📚 *Información del Catálogo*\n\n{ai_response}"
            else:
                return "❌ No se pudo procesar la respuesta de Gemini."
        else:
            return f"❌ Error al consultar Gemini: {response.status_code}"
            
    except Exception as e:
        print(f"❌ Error en proceso de consulta: {e}")
        return f"❌ Error al procesar tu consulta: {str(e)}"

def facebook_messenger_bot(target_chat_id=None):
    """
    Función principal del bot de Facebook Messenger
    
    Args:
        target_chat_id (str, optional): ID específico del chat al que se quiere responder.
                                        Si es None, responderá a todos los chats no leídos.
    """
    try:
        import undetected_chromedriver as uc
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException, NoSuchElementException
        
        # Obtener credenciales
        credentials = get_credentials()
        
        # Configurar opciones del navegador
        options = uc.ChromeOptions()
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-infobars")
        options.add_argument("--mute-audio")
        
        print("Iniciando navegador Chrome...")
        
        # Obtener la versión de Chrome instalada
        try:
            chrome_version = None
            
            # En Windows, intentar determinar la versión de Chrome
            if os.name == 'nt':
                try:
                    import winreg
                    key_path = r"SOFTWARE\Google\Chrome\BLBeacon"
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)
                    chrome_version = winreg.QueryValueEx(key, "version")[0]
                    winreg.CloseKey(key)
                except Exception as e:
                    print(f"No se pudo determinar la versión de Chrome automáticamente: {e}")
            
            # Si no se pudo determinar automáticamente, preguntar al usuario
            if not chrome_version:
                print("No se pudo determinar automáticamente la versión de Chrome.")
                print("Por favor, abre Chrome, ve a chrome://settings/help y anota la versión.")
                chrome_version = input("Introduce la versión de Chrome (por ejemplo, 135.0.7049.115): ")
            
            print(f"Versión de Chrome detectada: {chrome_version}")
            
            # Extraer el número principal de versión
            major_version = chrome_version.split('.')[0]
            print(f"Usando ChromeDriver compatible con Chrome {major_version}")
            
            # Crear instancia de ChromeDriver con la versión específica
            driver = uc.Chrome(version_main=int(major_version), options=options)
            
        except Exception as e:
            print(f"Error al configurar ChromeDriver específico: {e}")
            print("Intentando con configuración predeterminada...")
            driver = uc.Chrome(options=options)
        
        driver.maximize_window()
        
        try:
            # Abrir Facebook
            print("Abriendo Facebook...")
            driver.get("https://www.facebook.com")
            
            # Esperar a que se cargue la página de inicio de sesión
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "email"))
            )
            
            # Ingresar email
            print("Ingresando credenciales...")
            email_field = driver.find_element(By.ID, "email")
            email_field.clear()
            email_field.send_keys(credentials["email"])
            
            # Ingresar contraseña
            password_field = driver.find_element(By.ID, "pass")
            password_field.clear()
            password_field.send_keys(credentials["password"])
            
            # Hacer clic en el botón de inicio de sesión
            login_button = driver.find_element(By.NAME, "login")
            login_button.click()
            
            # Esperar un momento para verificar si hay verificación adicional
            print("Iniciando sesión... espera un momento")
            time.sleep(5)
            
            # Verificar si estamos en la página principal
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.XPATH, "//a[contains(@href, '/messages/')]"))
                )
                print("Inicio de sesión exitoso")
            except TimeoutException:
                print("Es posible que necesites completar verificaciones adicionales de seguridad.")
                print("Por favor, completa cualquier verificación que aparezca en el navegador.")
                print("Presiona Enter cuando hayas terminado...")
                input()
            
            # Si hay un chat específico, navegar directamente a él  
            if target_chat_id:
                chat_url = f"https://www.facebook.com/messages/e2ee/t/{target_chat_id}"
                print(f"Navegando al chat específico: {chat_url}")
                driver.get(chat_url)
                
                # Esperar a que se cargue la conversación específica
                try:
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.XPATH, "//div[@role='main']"))
                    )
                    print(f"Chat específico (ID: {target_chat_id}) abierto correctamente")
                except TimeoutException:
                    print("No se pudo cargar el chat específico. Verifica el ID del chat.")
            else:
                # Navegar a Messenger general
                print("Navegando a Messenger...")
                driver.get("https://www.facebook.com/messages/t/")
                
                # Esperar a que se cargue Messenger
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.XPATH, "//div[@role='main']"))
                )
            
            print("Bot activo. Se está ejecutando en el navegador.")
            if target_chat_id:
                print(f"El bot está configurado para responder solo al chat con ID: {target_chat_id}")
            else:
                print("El bot revisará las conversaciones no leídas y responderá automáticamente.")
            print("Para detener el bot, cierra el navegador o presiona Ctrl+C en esta terminal.")
            
            # Función para enviar un mensaje
            def send_message_clipboard(driver, message_text):
                try:
                    # Usar el portapapeles para transferir el texto (evita problemas de caracteres)
                    pyperclip.copy(message_text)
                    
                    # Encuentra el campo de entrada como antes
                    selectors = [
                        "//div[@role='textbox' and (@aria-label='Mensaje' or @aria-label='Message')]",
                        "//div[@contenteditable='true'][@role='textbox']",
                        "//div[@data-lexical-editor='true']"
                    ]
                    
                    message_input = None
                    for selector in selectors:
                        try:
                            message_input = driver.find_element(By.XPATH, selector)
                            break
                        except NoSuchElementException:
                            continue
                    
                    if message_input:
                        # Hacer clic en el campo de entrada
                        message_input.click()
                        time.sleep(0.5)
                        
                        # Usar la combinación de teclas Ctrl+V para pegar
                        # En Windows/Linux:
                        message_input.send_keys(Keys.CONTROL, 'v')
                        # O si usas Mac:
                        # message_input.send_keys(Keys.COMMAND, 'v')
                        
                        time.sleep(0.5)
                        message_input.send_keys(Keys.RETURN)
                        
                        print(f"Mensaje enviado: {message_text}")
                        return True
                    else:
                        print("No se pudo encontrar el campo de texto para enviar el mensaje")
                        return False
                except Exception as e:
                    print(f"Error al enviar mensaje: {e}")
                    return False
            
            # Función para enviar el menú de bienvenida
            def send_welcome_menu(driver):
                chat_data = get_chat_data()
                if not chat_data:
                    print("⚠️ No se pudo obtener el menú.")
                    send_message_clipboard(driver, "⚠️ No se pudo obtener el menú.")
                    return False
                
                menu_text = f"{chat_data['bienvenida']}\n\n"
                menu_text += "\n".join([op for op in chat_data['menu'] if '5. Salir' not in op])
                menu_text += "\n\n💬 *Responde con el número de la opción deseada.*"
                
                return send_message_clipboard(driver, menu_text)
            
            # Función para limpiar mensajes y extraer sólo números
            def extract_option_number(message_text):
                # Intentamos encontrar un número aislado en el mensaje
                match = re.search(r'\b[1-5]\b', message_text)
                if match:
                    return match.group(0)
                
                # Si no hay un número aislado, buscamos si el mensaje contiene solo un número
                if message_text.strip() in ["1", "2", "3", "4", "5"]:
                    return message_text.strip()
                
                return message_text
            
            # Función para procesar las opciones del menú
            def handle_menu_options(driver, message_text, user_id):
                chat_data = get_chat_data()
                if not chat_data:
                    print("⚠️ No se pudo obtener las opciones del menú.")
                    send_message_clipboard(driver, "⚠️ No se pudo obtener las opciones del menú.")
                    return False
                
                # Si estamos esperando una consulta para este usuario
                global waiting_for_query
                if user_id in waiting_for_query and waiting_for_query[user_id]:
                    print(f"💬 Recibida consulta de {user_id}: {message_text}")
                    
                    # Si el usuario quiere salir del modo consulta
                    if message_text.lower() in EXIT_COMMANDS:
                        waiting_for_query[user_id] = False
                        send_message_clipboard(driver, "✅ Has salido del modo consulta. Volviendo al menú principal...")
                        return send_welcome_menu(driver)
                    
                    # Procesar la consulta al catálogo
                    send_message_clipboard(driver, "🔍 Consultando al catálogo con Gemini AI. Esto puede tomar un momento...")
                    response = process_query_with_gemini(message_text)
                    return send_message_clipboard(driver, response + "\n\n_Para salir de este modo escribe *salir* o *menu*_")
                
                # Ignorar silenciosamente 'menu' y 'salir'
                if message_text.lower() in ['menu', 'salir']:
                    print(f"🔇 Ignorando silenciosamente la palabra clave: {message_text.lower()}")
                    return False
                
                # Extraer el número de opción limpio
                clean_option = extract_option_number(message_text)
                print(f"Opción extraída: '{clean_option}'")
                
                if clean_option == '4':
                    # Opción 4: Consulta con Gemini usando el catálogo PDF
                    # Marcar que estamos esperando una consulta de este usuario
                    waiting_for_query[user_id] = True
                    
                    # Después de 2 minutos, liberamos el estado
                    def reset_waiting_state(user_id):
                        time.sleep(120)  # 2 minutos
                        if user_id in waiting_for_query:
                            waiting_for_query[user_id] = False
                    
                    # Iniciar un hilo para resetear el estado después de un tiempo
                    import threading
                    threading.Thread(target=reset_waiting_state, args=(user_id,), daemon=True).start()
                    
                    send_message_clipboard(driver, "🔍 *Modo Consulta al Catálogo*\n\nAhora puedes hacer preguntas sobre el catálogo.\nEscribe cualquier pregunta y Gemini AI te responderá.\nPara volver al menú principal, escribe *salir* o *menu*.")
                    return True
                elif clean_option in chat_data['respuestas']:
                    print(f"✅ Respondiendo a la opción {clean_option}: {chat_data['respuestas'][clean_option]}")
                    return send_message_clipboard(driver, chat_data['respuestas'][clean_option])
                else:
                    print(f'⚠️ Opción inválida: "{clean_option}". Mostrando menú nuevamente...')
                    send_message_clipboard(driver, "⚠️ Opción no válida. Por favor, selecciona una de las opciones del menú.")
                    return send_welcome_menu(driver)
            
            # Variable para evitar responder múltiples veces al mismo mensaje
            last_processed_message = ""
            
            # Función para responder a un mensaje
            def respond_to_message(driver):
                nonlocal last_processed_message
                try:
                    # Obtener los últimos mensajes
                    last_messages = driver.find_elements(By.XPATH, "//div[@role='row']")
                    
                    if last_messages:
                        # Obtener el último mensaje
                        last_message = last_messages[-1]
                        message_text = last_message.text.strip()
                        
                        # Si este mensaje ya fue procesado, ignorarlo
                        if message_text == last_processed_message:
                            print("Este mensaje ya fue procesado. Ignorando.")
                            return False
                        
                        # Actualizar el último mensaje procesado
                        last_processed_message = message_text
                        
                        # Ignorar mensajes vacíos o que parecen ser solo interfaces de carga
                        if not message_text or message_text.lower() == "cargando...":
                            print("Mensaje ignorado: vacío o mensaje de sistema")
                            return False
                        
                        # Verificar si el mensaje parece ser una respuesta anterior del bot
                        bot_identifiers = [
                            "✨ ¡bienvenido", "opción no válida", "información del catálogo",
                            "📦 *catálogo", "🏷️ *ofertas", "🚚 *información", "🔍 *modo consulta"
                        ]
                        
                        for identifier in bot_identifiers:
                            if identifier in message_text.lower():
                                print("Este mensaje parece ser una respuesta anterior del bot. Omitiendo.")
                                return False
                        
                        print(f"Mensaje detectado: {message_text}")
                        
                        # Generar un ID de usuario único basado en la conversación actual
                        # (En una implementación ideal, esto sería un ID real del usuario)
                        user_id = f"user_{hash(driver.current_url) % 10000}" 
                        
                        # Verificar si es un comando de inicio
                        if any(cmd in message_text.lower() for cmd in START_COMMANDS):
                            print(f"🚀 Comando de activación detectado: {message_text}")
                            if user_id in waiting_for_query:
                                waiting_for_query[user_id] = False
                            return send_welcome_menu(driver)
                        
                        # Procesar las opciones del menú
                        return handle_menu_options(driver, message_text, user_id)
                    else:
                        print("No se encontraron mensajes en la conversación")
                        return False
                except Exception as e:
                    print(f"Error al procesar mensajes: {e}")
                    return False
            
            # Bucle principal
            while True:
                try:
                    if target_chat_id:
                        # Modo de chat específico: solo responder al chat abierto
                        responded = respond_to_message(driver)
                        if not responded:
                            print("No hay nuevos mensajes para responder en este chat")
                    else:
                        # Modo general: buscar conversaciones no leídas
                        unread_conversations = driver.find_elements(By.XPATH, 
                            "//div[contains(@aria-label, 'No leído') or contains(@aria-label, 'Unread') or contains(@aria-label, 'New message')]")
                        
                        if unread_conversations:
                            print(f"Se encontraron {len(unread_conversations)} conversaciones no leídas")
                            
                            for conversation in unread_conversations:
                                try:
                                    # Hacer clic en la conversación
                                    conversation.click()
                                    time.sleep(2)  # Esperar a que se cargue la conversación
                                    
                                    # Responder al mensaje
                                    respond_to_message(driver)
                                    time.sleep(2)  # Esperar un poco antes de revisar la siguiente conversación
                                except Exception as e:
                                    print(f"Error al procesar conversación: {str(e)}")
                        else:
                            print("No hay conversaciones no leídas por el momento")
                    
                    # Esperar antes de volver a verificar
                    print("Esperando 15 segundos antes de volver a verificar...")
                    time.sleep(15)
                    
                    # Si estamos en modo de chat específico, actualizar la página
                    if target_chat_id:
                        driver.refresh()
                        time.sleep(3)  # Esperar a que se cargue después de actualizar
                    else:
                        # En modo general, volver a la página principal de Messenger
                        driver.get("https://www.facebook.com/messages/t/")
                        time.sleep(3)  # Esperar a que se cargue
                    
                except KeyboardInterrupt:
                    print("Bot detenido manualmente")
                    break
                except Exception as e:
                    print(f"Error en el bucle principal: {str(e)}")
                    time.sleep(10)  # Esperar un poco antes de reintentar
        
        except Exception as e:
            print(f"Error durante la ejecución: {str(e)}")
        
        finally:
            # Mantener el navegador abierto para que el usuario pueda ver lo que ocurrió
            print("Sesión finalizada. El navegador permanecerá abierto.")
            print("Puedes cerrarlo manualmente cuando quieras.")
            try:
                input("Presiona Enter para cerrar el navegador...")
                driver.quit()
            except:
                pass
    
    except ImportError as e:
        print(f"Error al importar las dependencias: {str(e)}")
        print("Asegúrate de que todas las dependencias estén instaladas correctamente.")
    except Exception as e:
        print(f"Error inesperado: {str(e)}")

if __name__ == "__main__":
    # Instalar las dependencias necesarias
    install_dependencies()
    
    # Preguntar al usuario si quiere responder a un chat específico
    print("\nOpciones para ejecutar el bot:")
    print("1. Responder a todas las conversaciones no leídas")
    print("2. Responder a una conversación específica (necesitas el ID)")
    option = input("Selecciona una opción (1/2): ")
    
    if option == "2":
        chat_id = input("Introduce el ID del chat (ej. 29355186307462875): ")
        if chat_id.strip():
            print(f"Ejecutando bot para el chat específico con ID: {chat_id}")
            facebook_messenger_bot(chat_id.strip())
        else:
            print("No se proporcionó un ID válido. Ejecutando en modo general...")
            facebook_messenger_bot()
    else:
        # Ejecutar el bot en modo general
        facebook_messenger_bot()