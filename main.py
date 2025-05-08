# File: main.py
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
import psycopg2 # Added psycopg2 import

# Archivo para guardar las credenciales de acceso
CREDENTIALS_FILE = "fb_credentials.json"

# Configuración para la API de Gemini
GEMINI_API_KEY = 'AIzaSyDRivvwFML1GTZ_S-h5Qfx4qP3EKforMoM' # Consider using environment variables for keys
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
        "PyPDF2",
        "psycopg2-binary" # Added psycopg2 dependency
    ]

    print("Instalando dependencias necesarias...")
    for dep in dependencies:
        try:
            # Check if the main package is importable
            if dep == "psycopg2-binary":
                 __import__("psycopg2")
            else:
                __import__(dep.replace("-", "_"))
            print(f"{dep} ya está instalado")
        except ImportError:
            print(f"Instalando {dep}...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", dep])
            except Exception as e:
                print(f"❌ Error installing {dep}: {e}")
                print("Please try installing it manually: pip install {dep}")


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
    except ImportError:
        print("❌ Error: La librería PyPDF2 no está instalada. No se puede extraer texto del PDF.")
        return None
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

# Improved function to find the most relevant chunks for the query (from k.js)
def find_relevant_chunks(chunks, query, max_chunks=5):
    """Encuentra los fragmentos más relevantes para la consulta usando TF-IDF simplificado."""
    if not chunks:
        return []

    lower_query = query.lower()

    stop_words = ['el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'y', 'o', 'a', 'ante', 'bajo', 'con', 'de', 'desde', 'en', 'entre', 'hacia', 'hasta', 'para', 'por', 'según', 'sin', 'sobre', 'tras']
    query_terms = [term.replace(r'[^\wáéíóúñ]', '').strip() for term in lower_query.split()]
    query_terms = [term for term in query_terms if len(term) > 2 and term not in stop_words]

    price_numbers = [int(match) for match in re.findall(r'\d+', lower_query)]

    scored_chunks = []
    for chunk in chunks:
        lower_chunk = chunk.lower()
        score = 0

        for term in query_terms:
            matches = lower_chunk.split(term).count('') - 1 # Corrected split count
            if matches > 0:
                score += matches * (len(term) / 3)

        if price_numbers:
            chunk_numbers = [int(match) for match in re.findall(r'\d+', lower_chunk)]
            for chunk_num in chunk_numbers:
                for price_num in price_numbers:
                    if abs(chunk_num - price_num) <= price_num * 0.1:
                        score += 2

        term_matches = len([term for term in query_terms if term in lower_chunk])
        if term_matches > 1:
            score *= (1 + (term_matches / len(query_terms)))

        scored_chunks.append({"chunk": chunk, "score": score})

    scored_chunks.sort(key=lambda x: x["score"], reverse=True)
    relevant_chunks = [item["chunk"] for item in scored_chunks[:max_chunks]]

    print(f'🔍 Puntuaciones más altas: {[round(c["score"], 2) for c in scored_chunks[:min(3, len(scored_chunks))]]}') # Added min check

    return relevant_chunks

# Function to search in PostgreSQL database (from k.js, adapted for Python)
def searchInDatabase(query):
    """Searches for products in the PostgreSQL database based on the query."""
    conn = None
    cur = None
    try:
        # Get DB connection details from environment variables or use defaults
        db_host = os.environ.get('DB_HOST', 'localhost')
        db_name = os.environ.get('DB_NAME', 'catalogo_db')
        db_user = os.environ.get('DB_USER', 'postgres')
        db_password = os.environ.get('DB_PASSWORD', '123')
        db_port = os.environ.get('DB_PORT', '5432')

        conn = psycopg2.connect(
            host=db_host,
            database=db_name,
            user=db_user,
            password=db_password,
            port=db_port
        )
        cur = conn.cursor()
        print('✅ Conectado a PostgreSQL para consulta')

        query_lower = query.lower()

        categorias = ['laptop', 'computadora', 'pc', 'celular', 'smartphone', 'tablet', 'monitor',
            'impresora', 'scanner', 'teclado', 'mouse', 'audífono', 'auricular', 'cámara',
            'disco', 'memoria', 'usb', 'router', 'televisor', 'tv']

        precio_regex = r'(\d+)(?:\s*(?:a|y|hasta|entre|soles?|s\/\.?|dolares?|\$)\s*(\d+)?)?'
        min_precio = None
        max_precio = None
        match_precio = re.search(precio_regex, query_lower)

        if match_precio:
            precio1 = int(match_precio.group(1))
            precio2 = int(match_precio.group(2)) if match_precio.group(2) else None

            if precio1 is not None and precio2 is not None:
                min_precio = min(precio1, precio2)
                max_precio = max(precio1, precio2)
            elif precio1 is not None:
                pre_context = query_lower[max(0, match_precio.start() - 15):match_precio.start()]
                if "menos" in pre_context or "bajo" in pre_context or "económico" in pre_context or "barato" in pre_context or "menos de" in query_lower or "máximo" in query_lower:
                    max_precio = precio1
                elif "más" in pre_context or "encima" in pre_context or "mayor" in pre_context or "mínimo" in pre_context or "más de" in query_lower or "mínimo" in query_lower:
                    min_precio = precio1
                else:
                    min_precio = max(0, precio1 - round(precio1 * 0.1))
                    max_precio = precio1 + round(precio1 * 0.1)

        palabras_comunes = ['que', 'cual', 'cuales', 'cuanto', 'como', 'donde', 'quien', 'cuando',
            'hay', 'tiene', 'tengan', 'con', 'sin', 'por', 'para', 'entre', 'los', 'las',
            'uno', 'una', 'unos', 'unas', 'del', 'desde', 'hasta', 'hacia', 'durante',
            'mediante', 'según', 'sin', 'sobre', 'tras', 'versus']

        palabras_clave = [word.replace(r'[^\wáéíóúñ]', '').strip() for word in query_lower.split()]
        palabras_clave = [word for word in palabras_clave if len(word) > 2 and word not in palabras_comunes]

        categorias_mencionadas = [cat for cat in categorias if cat in query_lower or any(cat in palabra for palabra in palabras_clave)] # Corrected category check

        print('📊 Análisis de la consulta:')
        print('- Palabras clave:', palabras_clave)
        print('- Rango de precios:', min_precio, '-', max_precio)
        print('- Categorías detectadas:', categorias_mencionadas)

        if not palabras_clave and not categorias_mencionadas and min_precio is None and max_precio is None:
            return {
                "success": False,
                "products": [],
                "message": "No se encontraron términos válidos para buscar"
            }

        conditions = []
        params = []
        param_index = 1

        # PASO 1: Primero intentar una búsqueda específica por precio si está presente
        if min_precio is not None or max_precio is not None:
            price_conditions = []
            current_params = []
            current_param_index = 1

            if min_precio is not None:
                price_conditions.append(f'precio >= %s')
                current_params.append(min_precio)
                current_param_index += 1
            if max_precio is not None:
                price_conditions.append(f'precio <= %s')
                current_params.append(max_precio)
                current_param_index += 1

            sql_price_query = 'SELECT codigo, nombre, descripcion, precio, stock, categoria, imagen_url FROM productos'
            if price_conditions:
                sql_price_query += ' WHERE ' + ' AND '.join(price_conditions)
            sql_price_query += ' ORDER BY precio ASC'

            print('🔍 Ejecutando consulta de precio básica:')
            print('Query:', sql_price_query)
            print('Params:', current_params)

            cur.execute(sql_price_query, current_params)
            price_result = cur.fetchall()

            if price_result:
                print(f'✅ Encontrados {len(price_result)} productos por precio')
                products = [{"codigo": row[0], "nombre": row[1], "descripcion": row[2], "precio": row[3], "stock": row[4], "categoria": row[5], "imagen_url": row[6]} for row in price_result]

                if palabras_clave or categorias_mencionadas:
                    products = sorted(products, key=lambda product: (
                        sum(1 for palabra in palabras_clave if palabra in f"{product['codigo']} {product['nombre']} {product['descripcion'] or ''} {product['categoria']}".lower()) +
                        sum(2 for categoria in categorias_mencionadas if categoria in product['categoria'].lower())
                    ), reverse=True)

                return {
                    "success": True,
                    "products": products,
                    "message": f"Se encontraron {len(products)} productos en el rango de precio solicitado"
                }

            print('⚠️ No se encontraron productos con el rango de precio exacto. Ampliando búsqueda...')

        # PASO 2: Si no hay results solo por precio, construir una consulta más completa
        # Reset params for new query
        conditions = []
        params = []
        param_index = 1

        if palabras_clave:
            keyword_conditions = []
            for palabra in palabras_clave:
                if len(palabra) > 2:
                    like_expr = f'%{palabra}%'
                    keyword_conditions.append(f"""(
                        LOWER(codigo) LIKE %s OR
                        LOWER(nombre) LIKE %s OR
                        LOWER(descripcion) LIKE %s OR
                        LOWER(categoria) LIKE %s
                    )""")
                    params.extend([like_expr] * 4) # Add the same param 4 times
                    param_index += 4 # Increment index by 4

            if keyword_conditions:
                conditions.append(f'({" OR ".join(keyword_conditions)})')

        if categorias_mencionadas:
            category_conditions = []
            for categoria in categorias_mencionadas:
                category_conditions.append(f'LOWER(categoria) LIKE %s')
                params.append(f'%{categoria}%')
                param_index += 1
            conditions.append(f'({" OR ".join(category_conditions)})')

        if min_precio is not None:
            conditions.append(f'precio >= %s')
            flexible_min_price = max(0, min_precio - round(min_precio * 0.05))
            params.append(flexible_min_price)
            param_index += 1

        if max_precio is not None:
            conditions.append(f'precio <= %s')
            flexible_max_price = max_precio + round(max_precio * 0.05)
            params.append(flexible_max_price)
            param_index += 1

        sql_query = 'SELECT codigo, nombre, descripcion, precio, stock, categoria, imagen_url FROM productos'
        if conditions:
            sql_query += ' WHERE ' + ' AND '.join(conditions)
        sql_query += ' ORDER BY precio ASC'

        print('🔍 Ejecutando consulta SQL completa:')
        print('Query:', sql_query)
        print('Params:', params)

        cur.execute(sql_query, params)
        result = cur.fetchall()

        if result:
            print(f'✅ Encontrados {len(result)} productos en la base de datos')
            products = [{"codigo": row[0], "nombre": row[1], "descripcion": row[2], "precio": row[3], "stock": row[4], "categoria": row[5], "imagen_url": row[6]} for row in result]
            return {
                "success": True,
                "products": products,
                "message": f"Se encontraron {len(products)} productos relacionados"
            }
        else:
            print('⚠️ No se encontraron productos con la búsqueda completa')

            if conditions:
                print('🔄 Intentando búsqueda más flexible...')
                flexible_query = 'SELECT codigo, nombre, descripcion, precio, stock, categoria, imagen_url FROM productos WHERE '
                flexible_query += ' OR '.join(conditions)
                flexible_query += ' ORDER BY precio ASC'

                cur.execute(flexible_query, params)
                flexible_result = cur.fetchall()

                if flexible_result:
                    print(f'✅ Búsqueda flexible encontró {len(flexible_result)} productos')
                    products = [{"codigo": row[0], "nombre": row[1], "descripcion": row[2], "precio": row[3], "stock": row[4], "categoria": row[5], "imagen_url": row[6]} for row in flexible_result]
                    return {
                        "success": True,
                        "products": products,
                        "message": f"Se encontraron {len(products)} productos relacionados (búsqueda ampliada)"
                    }

            if min_precio is not None or max_precio is not None:
                print('🔄 Último intento: ampliando rango de precios significativamente...')
                params = []
                param_index = 1
                last_query = 'SELECT codigo, nombre, descripcion, precio, stock, categoria, imagen_url FROM productos WHERE '

                if min_precio is not None:
                    very_flexible_min_price = max(0, min_precio - round(min_precio * 0.15))
                    last_query += f'precio >= %s'
                    params.append(very_flexible_min_price)
                    param_index += 1

                if max_precio is not None:
                    if min_precio is not None:
                        last_query += ' AND '
                    very_flexible_max_price = max_precio + round(max_precio * 0.15)
                    last_query += f'precio <= %s'
                    params.append(very_flexible_max_price)
                    param_index += 1

                last_query += ' ORDER BY precio ASC'

                cur.execute(last_query, params)
                last_result = cur.fetchall()

                if last_result:
                    print(f'✅ Búsqueda con rango ampliado encontró {len(last_result)} productos')
                    products = [{"codigo": row[0], "nombre": row[1], "descripcion": row[2], "precio": row[3], "stock": row[4], "categoria": row[5], "imagen_url": row[6]} for row in last_result]
                    return {
                        "success": True,
                        "products": products,
                        "message": f"Se encontraron {len(products)} productos en un rango de precio similar (±15%)"
                    }

            return {
                "success": False,
                "products": [],
                "message": "No se encontraron productos que coincidan con tu búsqueda"
            }
    except ImportError:
        print("❌ Error: La librería psycopg2 no está instalada. No se puede conectar a la base de datos.")
        return {
            "success": False,
            "products": [],
            "message": "Error: La funcionalidad de base de datos requiere la librería psycopg2."
        }
    except Exception as db_error:
        print('❌ Error en la consulta a la base de datos:', db_error)
        return {
            "success": False,
            "products": [],
            "message": f"Error consultando base de datos: {db_error}"
        }
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
        print('✅ Conexión a PostgreSQL cerrada')


def process_query_with_gemini(query, pdf_path=CATALOG_PATH):
    """Processes a query using Gemini AI, the PostgreSQL database, and the PDF catalog."""
    try:
        # 1. Search in PostgreSQL database
        print('🗄️ Consulting PostgreSQL database...')
        db_results = searchInDatabase(query)

        # 2. Search in PDF catalog
        print('📄 Consulting PDF catalog as backup...')
        pdf_text = extract_text_from_pdf(pdf_path)
        pdf_results = {"success": False, "chunks": [], "message": "No se encontró el archivo del catálogo"}
        if pdf_text:
            chunks = split_text_into_chunks(pdf_text)
            if chunks:
                relevant_chunks = find_relevant_chunks(chunks, query)
                if relevant_chunks:
                    pdf_results = {"success": True, "chunks": relevant_chunks, "message": f"Se encontraron {len(relevant_chunks)} secciones relevantes en el catálogo"}
                else:
                    pdf_results = {"success": False, "chunks": [], "message": "No se encontró información relevante en el catálogo"}
            else:
                 pdf_results = {"success": False, "chunks": [], "message": "No se pudo procesar el texto del catálogo."}
        else:
             pdf_results = {"success": False, "chunks": [], "message": "No se pudo extraer el texto del catálogo PDF."}

        # 3. Combine information and generate response with Gemini
        print('🤖 Generating final response with Gemini...')

        db_context = ''
        # Recopilar URLs de las imágenes para enviarlas después
        image_urls = []
        
        if db_results["success"] and db_results["products"]:
            db_context = "### INFORMACIÓN DE BASE DE DATOS\n"
            products_to_include = db_results["products"][:5] # Limit to 5 products for context

            for index, product in enumerate(products_to_include):
                db_context += f"\nPRODUCTO {index + 1}:\n"
                db_context += f"Código: {product.get('codigo', 'N/A')}\n"
                db_context += f"Nombre: {product.get('nombre', 'N/A')}\n"
                db_context += f"Descripción: {product.get('descripcion', 'No disponible')}\n"
                db_context += f"Precio: {product.get('precio', 'N/A')}\n"
                db_context += f"Stock: {product.get('stock', 'N/A')}\n"
                db_context += f"Categoría: {product.get('categoria', 'N/A')}\n"
                # Guardar la URL de la imagen para enviarla después
                if product.get('imagen_url'):
                    db_context += f"Imagen: {product['imagen_url']}\n"
                    # Añadir la URL a la lista de imágenes
                    image_urls.append({
                        "url": product['imagen_url'],
                        "name": product.get('nombre', 'Producto')
                    })

            if len(db_results["products"]) > 5:
                 db_context += f"\n(Y {len(db_results['products']) - 5} productos más encontrados)\n"

        pdf_context = ''
        if pdf_results["success"] and pdf_results["chunks"]:
            pdf_context = "\n### INFORMACIÓN ADICIONAL DEL CATÁLOGO PDF\n"
            pdf_context += "\n\n".join(pdf_results["chunks"])

        if not db_context and not pdf_context:
             return "No se encontró información relevante en nuestro sistema para tu consulta."

        # Create the prompt for Gemini - MODIFICADO para no incluir URLs en formato markdown
        prompt = f"""### CONSULTA DEL USUARIO
"{query}"

{db_context}

{pdf_context}

### OBJETIVO
Proporcionar una respuesta clara, precisa y estructurada sobre la información solicitada.

### INSTRUCCIONES DE CONTENIDO
1. Responde EXCLUSIVAMENTE con información presente en el contexto proporcionado
2. Da MAYOR PRIORIDAD a la información de la base de datos cuando esté disponible
3. Complementa con información del catálogo PDF si es necesario
4. Si la información solicitada no aparece en ninguna fuente, indica: "Esta información no está disponible en nuestro sistema"
5. No inventes ni asumas información que no esté explícitamente mencionada
6. Mantén SIEMPRE el idioma español en toda la respuesta
7. Extrae las características técnicas más importantes y omite las secundarias
8. Identifica el rango de precios cuando se comparan múltiples productos
9. Destaca la disponibilidad de stock solo cuando sea relevante para la consulta
10. Prioriza características relevantes según la consulta del usuario
11. IMPORTANTE: NO incluyas URLs de imágenes en tu respuesta - las enviaremos por separado

### INSTRUCCIONES DE FORMATO
1. ESTRUCTURA GENERAL:
   - Inicia con un título claro y descriptivo en negrita relacionado con la consulta
   - Divide la información en secciones lógicas con subtítulos cuando sea apropiado
   - Utiliza máximo 3-4 oraciones por sección o párrafo
   - Concluye con una línea de resumen o recomendación cuando sea relevante
   - Si hay un producto claramente más adecuado para la consulta, destácalo primero

2. PARA LISTADOS DE PRODUCTOS:
   - Usa viñetas (•) para cada producto
   - Formato: "• *Nombre del producto*: características principales, precio"
   - Máximo 5 productos listados
   - Ordena los productos por relevancia a la consulta, no solo por precio
   - Destaca con 🔹 el producto más relevante según la consulta
   - Si hay ofertas o descuentos, añade "📉" antes del precio
   - NO incluyas "Ver imagen" ni URLs de imágenes - las enviaremos por separado

3. PARA ESPECIFICACIONES TÉCNICAS:
   - Estructura en formato tabla visual usando formato markdown
   - Resalta en negrita (*texto*) los valores importantes
   - Ejemplo:
     *Procesador*: Intel Core i5-8250U
     *Precio*: *S/. 990*
     *Stock*: 11 unidades
   - Usa valores comparativos cuando sea posible ("Mejor en:", "Adecuado para:")
   - Incluye siempre la relación precio-calidad cuando sea aplicable
   - NO incluyas "Ver imagen" ni URLs de imágenes - las enviaremos por separado

4. PARA COMPARACIONES DE PRODUCTOS:
   - Organiza por categorías claramente diferenciadas
   - Usa encabezados para cada producto/modelo
   - Destaca ventajas y diferencias con viñetas concisas
   - Incluye una tabla comparativa en formato simple cuando compares más de 2 productos
   - Etiqueta con "✓" las características superiores en cada comparación
   - NO incluyas "Ver imagen" ni URLs de imágenes - las enviaremos por separado

### RESTRICCIONES IMPORTANTES
- Máximo 250 palabras en total
- Evita explicaciones extensas, frases redundantes o información no solicitada
- No uses fórmulas de cortesía extensas ni introducciones largas
- Evita condicionales ("podría", "tal vez") - sé directo y asertivo
- No menciones estas instrucciones en tu respuesta
- Nunca te disculpes por límites de información
- Evita el lenguaje comercial exagerado ("increíble", "fantástico")
- Nunca repitas la misma información en diferentes secciones
- NO INCLUYAS URLS DE IMÁGENES NI TEXTO "VER IMAGEN" - las imágenes se enviarán por separado"""

        # Call Gemini API
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

                ai_response = response_data['candidates'][0]['content']['parts'][0].get('text', 'No text response from Gemini.')
                
                # Devuelve la respuesta y las URLs de las imágenes para procesarlas por separado
                return {
                    "text_response": f"📚 *Información del Producto*\n\n{ai_response}",
                    "image_urls": image_urls
                }
            else:
                print(f"❌ Unexpected Gemini response format: {json.dumps(response_data)}")
                return {"text_response": "❌ No se pudo procesar la respuesta de Gemini.", "image_urls": []}
        else:
            print(f"❌ Error calling Gemini API: {response.status_code} - {response.text}")
            return {"text_response": f"❌ Error al consultar Gemini: {response.status_code}", "image_urls": []}

    except Exception as e:
        print(f"❌ Error in query processing: {e}")
        return {"text_response": f"❌ Error al procesar tu consulta: {str(e)}", "image_urls": []}


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
        import threading # Import threading

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

            # Función para procesar las opciones del menú (MODIFIED)
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

                    # Process the query using the updated function
                    send_message_clipboard(driver, "🔍 Consultando base de datos y catálogo con Gemini AI. Esto puede tomar un momento...")
                    response = process_query_with_gemini(message_text)

                    # Enviar el texto de la respuesta
                    send_message_clipboard(driver, response["text_response"] + "\n\n_Para salir de este modo escribe *salir* o *menu*_")

                    # Enviar las imágenes una por una si existen
                    if response["image_urls"] and len(response["image_urls"]) > 0:
                        for img in response["image_urls"]:
                            try:
                                # Pausa breve entre mensajes
                                time.sleep(1)

                                # Usar selenium para pegar la URL de la imagen directamente
                                # Esto hará que Facebook renderice la imagen en el chat
                                message_input = WebDriverWait(driver, 10).until(
                                    EC.presence_of_element_located((By.XPATH, "//div[@role='textbox' and (@aria-label='Mensaje' or @aria-label='Message')]"))
                                )

                                # Hacer clic y pegar la URL
                                message_input.click()
                                pyperclip.copy(img["url"])
                                message_input.send_keys(Keys.CONTROL, 'v')
                                time.sleep(0.5)
                                message_input.send_keys(Keys.RETURN)

                                print(f"✅ Imagen enviada: {img['url']}")
                            except Exception as img_error:
                                print(f"❌ Error al enviar imagen: {img_error}")

                    return True

                # Ignore 'menu' and 'salir' silently if not in query mode
                if message_text.lower() in ['menu', 'salir']:
                    print(f"🔇 Ignoring keyword: {message_text.lower()}")
                    return False

                # Extract the clean option number
                clean_option = extract_option_number(message_text)
                print(f"Opción extraída: '{clean_option}'")

                if clean_option == '4':
                    # Opción 4: Consulta con Gemini using the database and PDF
                    # Mark that we are waiting for a query from this user
                    waiting_for_query[user_id] = True

                    # After 2 minutes, release the state
                    def reset_waiting_state(user_id):
                        time.sleep(120)  # 2 minutes
                        if user_id in waiting_for_query:
                            waiting_for_query[user_id] = False

                    # Start a thread to reset the state after a while
                    threading.Thread(target=reset_waiting_state, args=(user_id,), daemon=True).start()

                    send_message_clipboard(driver, "🔍 *Modo Consulta al Catálogo y Base de Datos*\n\nAhora puedes hacer preguntas sobre nuestros productos.\nConsultaremos primero nuestra base de datos y luego el catálogo PDF.\nPara volver al menú principal, escribe *salir* o *menu*.")
                    return True

                elif clean_option in chat_data['respuestas']:
                    print(f"✅ Responding to option {clean_option}: {chat_data['respuestas'][clean_option]}")
                    return send_message_clipboard(driver, chat_data['respuestas'][clean_option])

                else:
                    print(f'⚠️ Invalid option: "{clean_option}". Showing menu again...')
                    send_message_clipboard(driver, "⚠️ Opción no válida. Por favor, selecciona una de las opciones del menú.")
                    return send_welcome_menu(driver)

            # Variable to avoid responding multiple times to the same message
            last_processed_message = ""

            # Function to respond to a message
            def respond_to_message(driver):
                nonlocal last_processed_message
                try:
                    # Get the last messages
                    last_messages = driver.find_elements(By.XPATH, "//div[@role='row']")

                    if last_messages:
                        # Get the last message
                        last_message = last_messages[-1]
                        message_text = last_message.text.strip()

                        # If this message was already processed, ignore it
                        if message_text == last_processed_message:
                            print("This message was already processed. Ignoring.")
                            return False

                        # Update the last processed message
                        last_processed_message = message_text

                        # Ignore empty messages or messages that seem to be just loading interfaces
                        if not message_text or message_text.lower() == "cargando...":
                            print("Message ignored: empty or system message")
                            return False

                        # Check if the message seems to be a previous bot response
                        bot_identifiers = [
                            "✨ ¡bienvenido", "opción no válida", "información del producto", # Updated identifier
                            "📦 *catálogo", "🏷️ *ofertas", "🚚 *información", "🔍 *modo consulta"
                        ]

                        for identifier in bot_identifiers:
                            if identifier in message_text.lower():
                                print("This message seems to be a previous bot response. Skipping.")
                                return False

                        print(f"Message detected: {message_text}")

                        # Generate a unique user ID based on the current conversation
                        # (In an ideal implementation, this would be a real user ID)
                        user_id = f"user_{hash(driver.current_url) % 10000}"

                        # Check if it's a start command
                        if any(cmd in message_text.lower() for cmd in START_COMMANDS):
                            print(f"🚀 Activation command detected: {message_text}")
                            if user_id in waiting_for_query:
                                waiting_for_query[user_id] = False
                            return send_welcome_menu(driver)

                        # Process menu options
                        return handle_menu_options(driver, message_text, user_id)
                    else:
                        print("No messages found in the conversation")
                        return False
                except Exception as e:
                    print(f"Error processing messages: {e}")
                    return False

            # Main loop
            while True:
                try:
                    if target_chat_id:
                        # Specific chat mode: only respond to the open chat
                        responded = respond_to_message(driver)
                        if not responded:
                            print("No new messages to respond to in this chat")
                    else:
                        # General mode: look for unread conversations
                        unread_conversations = driver.find_elements(By.XPATH,
                            "//div[contains(@aria-label, 'No leído') or contains(@aria-label, 'Unread') or contains(@aria-label, 'New message')]")

                        if unread_conversations:
                            print(f"Found {len(unread_conversations)} unread conversations")

                            for conversation in unread_conversations:
                                try:
                                    # Click on the conversation
                                    conversation.click()
                                    time.sleep(2)  # Wait for the conversation to load

                                    # Respond to the message
                                    respond_to_message(driver)
                                    time.sleep(2)  # Wait a bit before checking the next conversation
                                except Exception as e:
                                    print(f"Error processing conversation: {str(e)}")
                        else:
                            print("No unread conversations at the moment")

                    # Wait before checking again
                    print("Waiting 15 seconds before checking again...")
                    time.sleep(15)

                    # If in specific chat mode, refresh the page
                    if target_chat_id:
                        driver.refresh()
                        time.sleep(3)  # Wait for it to load after refreshing
                    else:
                        # In general mode, go back to the main Messenger page
                        driver.get("https://www.facebook.com/messages/t/")
                        time.sleep(3)  # Wait for it to load

                except KeyboardInterrupt:
                    print("Bot stopped manually")
                    break
                except Exception as e:
                    print(f"Error in main loop: {str(e)}")
                    time.sleep(10)  # Wait a bit before retying

        except Exception as e:
            print(f"Error during execution: {str(e)}")

        finally:
            # Keep the browser open so the user can see what happened
            print("Session finished. The browser will remain open.")
            print("You can close it manually when you want.")
            try:
                input("Press Enter to close the browser...")
                driver.quit()
            except:
                pass

    except ImportError as e:
        print(f"Error importing dependencies: {str(e)}")
        print("Make sure all dependencies are installed correctly.")
    except Exception as e:
        print(f"Unexpected error: {str(e)}")

if __name__ == "__main__":
    # Install necessary dependencies
    install_dependencies()

    # Ask the user if they want to respond to a specific chat
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
        # Run the bot in general mode
        facebook_messenger_bot()

