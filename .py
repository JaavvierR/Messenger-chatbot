import json
import os
import getpass
import time
import subprocess
import sys

# Archivo para guardar las credenciales de acceso
CREDENTIALS_FILE = "fb_credentials.json"    

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
        "webdriver-manager"
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
        
        # Para usuarios avanzados que quieran modo headless
        # options.add_argument("--headless")
        
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
            
            # Función para responder a un mensaje
            def respond_to_message(driver):
                try:
                    # Obtener los últimos mensajes
                    last_messages = driver.find_elements(By.XPATH, "//div[@role='row']")
                    
                    if last_messages:
                        # Obtener el último mensaje
                        last_message = last_messages[-1]
                        message_text = last_message.text.lower()
                        
                        # Verificar si el mensaje ya fue respondido (buscar nuestras respuestas anteriores)
                        # Este es un mecanismo simple para evitar responder al mismo mensaje múltiples veces
                        if "¡hola! ¿cómo estás?" in message_text.lower() or "¡muy bien, gracias por preguntar!" in message_text.lower():
                            print("Este mensaje parece ser una respuesta anterior del bot. Omitiendo.")
                            return False
                        
                        print(f"Mensaje detectado: {message_text}")
                        
                        # Preparar respuesta según el contenido
                        if "hola" in message_text or "hi" in message_text or "hey" in message_text:
                            reply = "¡Hola! ¿Cómo estás?"
                        elif "cómo estás" in message_text or "how are you" in message_text or "como estas" in message_text:
                            reply = "¡Muy bien, gracias por preguntar!"
                        elif "ayuda" in message_text or "help" in message_text:
                            reply = "Estoy aquí para ayudarte. ¿En qué puedo asistirte?"
                        elif "gracias" in message_text or "thanks" in message_text:
                            reply = "¡De nada! Estoy para servirte."
                        else:
                            reply = "He recibido tu mensaje. ¿En qué puedo ayudarte?"
                        
                        # Buscar y usar el campo de texto
                        try:
                            # Intentar diferentes selectores para el campo de texto de entrada
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
                                message_input.click()
                                time.sleep(0.5)
                                message_input.send_keys(reply)
                                time.sleep(0.5)
                                message_input.send_keys(Keys.RETURN)
                                
                                print(f"Respondido: {reply}")
                                return True
                            else:
                                print("No se pudo encontrar el campo de texto para responder")
                                return False
                        except Exception as e:
                            print(f"Error al enviar respuesta: {e}")
                            return False
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