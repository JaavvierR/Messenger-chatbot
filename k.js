const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');
const axios = require('axios');
const fs = require('fs');
const pdf = require('pdf-parse');
const { Client: PgClient } = require('pg'); 


console.log('🚀 Iniciando el bot de WhatsApp...');

// 🔹 Verifica si la sesión está bloqueada y la elimina antes de iniciar
const sessionPath = './.wwebjs_auth/session';
if (fs.existsSync(sessionPath)) {
    console.log('🗑️ Eliminando sesión anterior para evitar bloqueos...');
    fs.rmSync(sessionPath, { recursive: true, force: true });
}

console.log('🔄 Inicializando el cliente de WhatsApp...');

const client = new Client({
    authStrategy: new LocalAuth(),
    puppeteer: {
        executablePath: process.env.CHROME_PATH  || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        headless: false,
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-extensions',
            '--disable-dev-shm-usage',
            '--disable-gpu'
        ]
    }
});

// Variable global para rastrear si estamos esperando una consulta
let waitingForQuery = {};

// Comandos de activación para iniciar el bot
const startCommands = ['!start', 'hola', 'consulta', 'inicio', 'comenzar', 'ayuda', 'start', 'hi', 'hello'];

client.on('qr', qr => {
    console.log('📷 Escanea el código QR con tu WhatsApp:');
    console.log(qr);
});

client.on('ready', () => {
    console.log('✅ Cliente de WhatsApp está listo!');
});

client.on('message', async message => {
    try {
        console.log(`📩 Mensaje recibido de ${message.from}: ${message.body}`);

        // 🔹 Responder solo a un número específico
        const numeroAutorizado = process.env.AUTHORIZED_NUMBER || '51919739431@c.us'; // Formato de WhatsApp sin "+" y con "c.us"
        if (message.from !== numeroAutorizado) {
            console.log('⛔ Mensaje ignorado, no es del número autorizado.');
            return;
        }

        if (message.isGroupMsg) return;

        if (message.hasQuotedMsg) {
            try {
                console.log('🔍 Detectado mensaje citado...');
                const quotedMsg = await Promise.race([
                    message.getQuotedMessage(),
                    new Promise((_, reject) =>
                        setTimeout(() => reject(new Error('⏳ Timeout obteniendo mensaje citado')), 5000)
                    )
                ]);

                console.log('📌 Mensaje citado:', quotedMsg.body || "[Mensaje multimedia]");
                message.reply(`🔹 Respondiste a: ${quotedMsg.body}`);
            } catch (error) {
                console.warn("⚠️ No se pudo obtener el mensaje citado:", error.message);
                message.reply("⚠️ Hubo un problema obteniendo el mensaje citado.");
            }
        }

        // Verificar si el mensaje es un comando de activación (case insensitive)
        const userMessage = message.body.trim().toLowerCase();
        if (startCommands.includes(userMessage)) {
            // Resetear el estado de espera cuando se inicia el bot
            waitingForQuery[message.from] = false;
            console.log(`🚀 Comando de activación detectado: ${userMessage}`);
            await sendWelcomeMenu(message);
        } else {
            await handleMenuOptions(message);
        }
    } catch (error) {
        console.error("❌ Error en la gestión del mensaje:", error);
    }
});


async function getChatData() {
    try {
        console.log('🌐 Obteniendo datos del chat...');
        const response = await axios.get('http://localhost:5001/api/chat');
        return response.data;
    } catch (error) {
        console.error('❌ Error al obtener datos del chat:', error.message);
        return null;
    }
}

async function sendWelcomeMenu(message) {
    const chatData = await getChatData();
    if (!chatData) {
        console.log('⚠️ No se pudo obtener el menú.');
        return message.reply("⚠️ No se pudo obtener el menú.");
    }

    const menuText = `${chatData.bienvenida}\n\n${chatData.menu.filter(op => op !== '5. Salir').join('\n')}\n\n💬 *Responde con el número de la opción deseada.*`;
    console.log('📨 Enviando menú de bienvenida...');
    message.reply(menuText);
}

async function handleMenuOptions(message) {
    const chatData = await getChatData();
    if (!chatData) {
        console.log('⚠️ No se pudo obtener las opciones del menú.');
        return message.reply("⚠️ No se pudo obtener las opciones del menú.");
    }

    const userOption = message.body.trim();
    const userOptionLower = userOption.toLowerCase(); // Convertir a minúsculas para comparación
    
    // Si estamos esperando una consulta para este número, no procesamos como opción de menú
    if (waitingForQuery[message.from]) {
        console.log(`💬 Recibida consulta de ${message.from}: ${userOption}`);
        // No hacemos nada, la consulta será manejada por el listener en handleCatalogQuery
        return;
    }

    // Ignorar silenciosamente 'menu' y 'salir'
    if (userOptionLower === 'menu' || userOptionLower === 'salir') {
        console.log(`🔇 Ignorando silenciosamente la palabra clave: ${userOptionLower}`);
        return; // No hacer nada, simplemente retornar
    } else if (userOption === '4') {
        // Opción 4: Consulta con Gemini usando el catálogo PDF y Base de Datos
        // Marcar que estamos esperando una consulta de este número
        waitingForQuery[message.from] = true;
        
        // Después de un tiempo prudencial, liberamos el estado
        setTimeout(() => {
            waitingForQuery[message.from] = false;
        }, 120000); // 2 minutos
        
        await handleCatalogQuery(message);
    } else if (chatData.respuestas[userOption]) {
        console.log(`✅ Respondiendo a la opción ${userOption}: ${chatData.respuestas[userOption]}`);
        message.reply(chatData.respuestas[userOption]);
    } else {
        console.log('⚠️ Opción inválida. Mostrando menú nuevamente...');
        message.reply("⚠️ Opción no válida. Por favor, selecciona una de las opciones del menú.");
        await sendWelcomeMenu(message);
    }
}

async function handleCatalogQuery(message) {
    try {
        const exitCommands = ['salir', 'exit', 'menu', 'volver', 'regresar', 'terminar', 'finalizar', '!menu', '!start'];
        
        await message.reply("🔍 *Modo Consulta al Catálogo y Base de Datos*\n\nAhora puedes hacer preguntas sobre nuestros productos.\nConsultaremos primero nuestra base de datos y luego el catálogo PDF.\nPara volver al menú principal, escribe *salir* o *menu*.");
        
        // Configurar un listener para escuchar múltiples preguntas
        const continuousListener = async (msg) => {
            if (msg.from === message.from) {
                const userMessage = msg.body.trim().toLowerCase();
                
                if (exitCommands.includes(userMessage)) {
                    client.removeListener('message', continuousListener);
                    console.log('👋 Usuario solicitó salir del modo consulta');
                    
                    waitingForQuery[msg.from] = false;
                    
                    await msg.reply('✅ Has salido del modo consulta. Volviendo al menú principal...');
                    await sendWelcomeMenu(msg);
                    return; 
                }
                
                console.log(`❓ Consulta continua recibida: ${msg.body}`);
                
                const processingMsg = await msg.reply('🔍 Consultando base de datos y catálogo con Gemini AI. Esto puede tomar un momento...');
                
                try {
                    // Ahora processQueryWithGemini devuelve un booleano
                    const success = await processQueryWithGemini(msg);
                    
                    if (success) {
                        // Solo enviar el recordatorio de cómo salir
                        await msg.reply("_Para salir de este modo escribe *salir* o *menu*_");
                    }
                } catch (queryError) {
                    console.error('❌ Error procesando consulta:', queryError);
                    await msg.reply(`❌ Error: ${queryError.message || 'Ocurrió un problema al consultar la información.'}\n\n_Para salir de este modo escribe *salir* o *menu*_`);
                }
            }
        };
        
        // Registrar el listener para escuchar continuamente
        client.on('message', continuousListener);
        
    } catch (error) {
        console.error('❌ Error en el modo consulta continua:', error);
        message.reply('❌ Ocurrió un error al procesar tu solicitud.');
        
        waitingForQuery[message.from] = false;
        await sendWelcomeMenu(message);
    }
}

// Función para enviar imágenes desde URL 
async function sendImageFromUrl(message, imageUrl, caption = '') {
    try {
        console.log(`🖼️ Intentando enviar imagen desde URL: ${imageUrl}`);
        
        // Verificar que la URL sea válida
        if (!imageUrl || !imageUrl.startsWith('http')) {
            console.warn('⚠️ URL de imagen inválida:', imageUrl);
            return message.reply('⚠️ No se pudo procesar la URL de la imagen.');
        }
        // Crear directorio temporal si no existe
        const tempDir = './temp_images';
        if (!fs.existsSync(tempDir)) {
            fs.mkdirSync(tempDir);
        }
        // Generar un nombre de archivo único
        const fileName = `${tempDir}/img_${Date.now()}.jpg`;

        // Descargar la imagen
        console.log('⬇️ Descargando imagen...');
        const imageResponse = await axios({
            method: 'get',
            url: imageUrl,
            responseType: 'stream'
        });

        // Guardar la imagen en archivo temporal
        const writer = fs.createWriteStream(fileName);
        imageResponse.data.pipe(writer);

        // Esperar a que termine de escribir el archivo
        await new Promise((resolve, reject) => {
            writer.on('finish', resolve);
            writer.on('error', reject);
        });

        console.log(`✅ Imagen descargada y guardada en: ${fileName}`);

        // Enviar la imagen como un mensaje de WhatsApp
        const media = MessageMedia.fromFilePath(fileName);
        await message.reply(media, null, { caption: caption });
        console.log('✅ Imagen enviada exitosamente');

        // Eliminar archivo temporal después de enviarlo
        setTimeout(() => {
            try {
                fs.unlinkSync(fileName);
                console.log(`🗑️ Archivo temporal eliminado: ${fileName}`);
            } catch (err) {
                console.error(`❌ Error al eliminar archivo temporal: ${err.message}`);
            }
        }, 5000); // Esperar 5 segundos antes de eliminar
        return true;
    } catch (error) {
        console.error('❌ Error al enviar imagen:', error);
        message.reply(`❌ No se pudo enviar la imagen: ${error.message}`);
        return false;
    }
}

async function processQueryWithGemini(message) {
    try {
        const userQuery = message.body.trim();
        console.log(`🔍 Procesando consulta: "${userQuery}"`);
        
        // 1. Primero buscamos en la base de datos PostgreSQL
        console.log('🗄️ Consultando base de datos PostgreSQL...');
        const dbResults = await searchInDatabase(userQuery);
        
        // 2. Luego buscamos en el PDF del catálogo
        console.log('📄 Consultando catálogo PDF como respaldo...');
        const pdfResults = await searchInCatalogPDF(userQuery);
        
        // 3. Combinamos la información y generamos respuesta con Gemini
        console.log('🤖 Generando respuesta final con Gemini...');
        const combinedResponse = await generateGeminiResponse(userQuery, dbResults, pdfResults);

        const cleanedResponse = combinedResponse.replace(/🖼️\s*\[Ver imagen\]\(https?:\/\/[^\s)]+\)/g, '');
        
        // 4. Envía la respuesta de texto primero
        await message.reply(`📊 *Información del Producto*\n\n${cleanedResponse}`);
        
        // 5. Buscar URLs de imágenes en la respuesta y enviarlas como imágenes reales
        const imageUrlRegex = /\[Ver imagen\]\((https?:\/\/[^\s)]+)\)/g;
        let match;
        let imageCount = 0;
        let imagePromises = [];
        
        while ((match = imageUrlRegex.exec(combinedResponse)) !== null && imageCount < 5) {
            const imageUrl = match[1];
            console.log(`🖼️ Procesando imagen: ${imageUrl}`);
            
            // Pequeña pausa para evitar saturar la API
            await new Promise(resolve => setTimeout(resolve, 1000 * imageCount));
            
            try {
                await sendImageFromUrl(message, imageUrl, `🖼️ *Imagen del producto ${imageCount + 1}*`);
                imageCount++;
            } catch (imgError) {
                console.error(`❌ Error al enviar imagen: ${imgError.message}`);
            }
        }
        
        // Devolver true para indicar éxito, en lugar de la respuesta completa
        return true;
    } catch (error) {
        console.error('❌ Error en processQueryWithGemini:', error);
        throw new Error(`No se pudo procesar tu consulta: ${error.message}`);
    }
}

// Función mejorada para buscar en la base de datos PostgreSQL
async function searchInDatabase(query) {
    const pgClient = new PgClient({
        user: process.env.DB_USER || 'postgres',
        host: process.env.DB_HOST || 'postgres', // Usar el nombre del servicio en docker-compose
        database: process.env.DB_NAME || 'catalogo_db',
        password: process.env.DB_PASSWORD || '123',
        port: parseInt(process.env.DB_PORT || '5432'),
    });
    
    try {
        await pgClient.connect();
        console.log('✅ Conectado a PostgreSQL para consulta');
        
        // Análisis avanzado de la consulta
        const queryLower = query.toLowerCase();
        
        // Detectar categorías comunes de productos
        const categorias = ['laptop', 'computadora', 'pc', 'celular', 'smartphone', 'tablet', 'monitor', 
            'impresora', 'scanner', 'teclado', 'mouse', 'audífono', 'auricular', 'cámara', 
            'disco', 'memoria', 'usb', 'router', 'televisor', 'tv'];
        
        // Detección de rangos de precios
        const precioRegex = /(\d+)(?:\s*(?:a|y|hasta|entre|soles?|s\/\.?|dolares?|\$)\s*(\d+)?)?/gi;
        let minPrecio = null;
        let maxPrecio = null;
        let matchPrecio;
        
        while ((matchPrecio = precioRegex.exec(queryLower)) !== null) {
            const precio1 = parseInt(matchPrecio[1]);
            const precio2 = matchPrecio[2] ? parseInt(matchPrecio[2]) : null;
            
            if (precio1 && precio2) {
                
                minPrecio = Math.min(precio1, precio2);
                maxPrecio = Math.max(precio1, precio2);
                break;
            } else if (precio1) {
                
                const preContext = queryLower.substring(Math.max(0, matchPrecio.index - 15), matchPrecio.index);
                
                if (preContext.includes("menos") || preContext.includes("bajo") || 
                    preContext.includes("económico") || preContext.includes("barato") || 
                    queryLower.includes("menos de") || queryLower.includes("máximo")) {
                    maxPrecio = precio1;
                } else if (preContext.includes("más") || preContext.includes("encima") || 
                          preContext.includes("mayor") || preContext.includes("mínimo") ||
                          queryLower.includes("más de") || queryLower.includes("mínimo")) {
                    minPrecio = precio1;
                } else {
                    // Si no hay contexto claro, intentamos inferir por el resto de la consulta
                    if (queryLower.includes("menos") || queryLower.includes("máximo") || 
                        queryLower.includes("hasta") || queryLower.includes("no más")) {
                        maxPrecio = precio1;
                    } else if (queryLower.includes("más") || queryLower.includes("mínimo") || 
                              queryLower.includes("desde") || queryLower.includes("arriba")) {
                        minPrecio = precio1;
                    } else {
                        
                        minPrecio = Math.max(0, precio1 - Math.round(precio1 * 0.1)); // 10% menos
                        maxPrecio = precio1 + Math.round(precio1 * 0.1); // 10% más
                    }
                }
            }
        }
        
        
        const palabrasComunes = ['que', 'cual', 'cuales', 'cuanto', 'como', 'donde', 'quien', 'cuando', 
            'hay', 'tiene', 'tengan', 'con', 'sin', 'por', 'para', 'entre', 'los', 'las',
            'uno', 'una', 'unos', 'unas', 'del', 'desde', 'hasta', 'hacia', 'durante',
            'mediante', 'según', 'sin', 'sobre', 'tras', 'versus'];
        
        
        const palabrasClave = queryLower.split(/\s+/)
            .map(word => word.replace(/[^\wáéíóúñ]/gi, '').trim())
            .filter(word => word.length > 2)
            .filter(word => !palabrasComunes.includes(word));
        
        
        const categoriasMencionadas = categorias.filter(cat => 
            queryLower.includes(cat) || 
            palabrasClave.some(palabra => palabra.includes(cat))
        );
        
        console.log('📊 Análisis de la consulta:');
        console.log('- Palabras clave:', palabrasClave);
        console.log('- Rango de precios:', minPrecio, '-', maxPrecio);
        console.log('- Categorías detectadas:', categoriasMencionadas);
        
        // Si no hay términos válidos para buscar después del análisis
        if (palabrasClave.length === 0 && categoriasMencionadas.length === 0 && !minPrecio && !maxPrecio) {
            return { 
                success: false, 
                products: [], 
                message: "No se encontraron términos válidos para buscar" 
            };
        }
        
        // ===== CAMBIOS PRINCIPALES AQUÍ =====
        
        // Construir consulta SQL más inteligente
        let conditions = [];
        let params = [];
        let paramIndex = 1;
        let hasPriceCondition = false;
        
        // PASO 1: Primero intentar una búsqueda específica por precio si está presente
        if (minPrecio !== null || maxPrecio !== null) {
            let priceConditions = [];
            
            if (minPrecio !== null) {
                priceConditions.push(`precio >= $${paramIndex}`);
                params.push(minPrecio);
                paramIndex++;
            }
            
            if (maxPrecio !== null) {
                priceConditions.push(`precio <= $${paramIndex}`);
                params.push(maxPrecio);
                paramIndex++;
            }
            
            // Primera consulta: intentar sólo con las condiciones de precio
            // MODIFICADO: Asegúrate de seleccionar también la columna imagen_url
            let sqlPriceQuery = 'SELECT *, imagen_url FROM productos';
            
            if (priceConditions.length > 0) {
                sqlPriceQuery += ' WHERE ' + priceConditions.join(' AND ');
                hasPriceCondition = true;
            }
            
            // Añadir ordenamiento y límites
            sqlPriceQuery += ' ORDER BY precio ASC';
            
            console.log(`🔍 Ejecutando consulta de precio básica:`);
            console.log('Query:', sqlPriceQuery);
            console.log('Params:', params);
            
            const priceResult = await pgClient.query(sqlPriceQuery, params);
            
            if (priceResult.rows.length > 0) {
                console.log(`✅ Encontrados ${priceResult.rows.length} productos por precio`);
                
                // Si tenemos resultados solo por precio, filtramos los resultados por relevancia
                let filteredResults = priceResult.rows;
                
                // Si hay palabras clave o categorías, las usamos para filtrar y ordenar los resultados
                if (palabrasClave.length > 0 || categoriasMencionadas.length > 0) {
                    // Filtrar resultados por relevancia
                    filteredResults = priceResult.rows.map(product => {
                        let score = 0;
                        const productText = `${product.codigo} ${product.nombre} ${product.descripcion || ''} ${product.categoria}`.toLowerCase();
                        
                        // Puntuar por palabras clave
                        palabrasClave.forEach(palabra => {
                            if (productText.includes(palabra)) {
                                score += 1;
                            }
                        });
                        
                        // Puntuar por categorías
                        categoriasMencionadas.forEach(categoria => {
                            if (product.categoria.toLowerCase().includes(categoria)) {
                                score += 2;
                            }
                        });
                        
                        return { product, score };
                    })
                    .sort((a, b) => b.score - a.score)
                    .map(item => item.product);
                }
                
                return { 
                    success: true,
                    products: filteredResults,
                    message: `Se encontraron ${filteredResults.length} productos en el rango de precio solicitado`
                };
            }
            
            // Si no hay resultados con sólo precio, continuamos con la búsqueda completa
            console.log('⚠️ No se encontraron productos con el rango de precio exacto. Ampliando búsqueda...');
        }
        
        // PASO 2: Si no hay resultados solo por precio, construir una consulta más completa
        
        // Reset de parámetros para nueva consulta
        conditions = [];
        params = [];
        paramIndex = 1;
        
        // Condiciones por palabras clave - usar OR entre ellas
        if (palabrasClave.length > 0) {
            const keywordConditions = [];
            
            for (const palabra of palabrasClave) {
                if (palabra.length > 2) {  // Ignorar palabras muy cortas
                    const likeExpr = `%${palabra}%`;
                    keywordConditions.push(`(
                        LOWER(codigo) LIKE $${paramIndex} OR 
                        LOWER(nombre) LIKE $${paramIndex} OR 
                        LOWER(descripcion) LIKE $${paramIndex} OR
                        LOWER(categoria) LIKE $${paramIndex}
                    )`);
                    params.push(likeExpr);
                    paramIndex++;
                }
            }
            
            if (keywordConditions.length > 0) {
                // Usar OR entre palabras clave para búsqueda más flexible
                conditions.push(`(${keywordConditions.join(' OR ')})`);
            }
        }
        
        // Condiciones por categoría - separado de las palabras clave
        if (categoriasMencionadas.length > 0) {
            const categoryConditions = [];
            
            for (const categoria of categoriasMencionadas) {
                categoryConditions.push(`LOWER(categoria) LIKE $${paramIndex}`);
                params.push(`%${categoria}%`);
                paramIndex++;
            }
            
            conditions.push(`(${categoryConditions.join(' OR ')})`);
        }
        
        // Añadir condiciones de precio - más flexibles en la búsqueda completa
        if (minPrecio !== null) {
            // Hacemos el rango un poco más amplio para aumentar resultados
            conditions.push(`precio >= $${paramIndex}`);
            const flexibleMinPrice = Math.max(0, minPrecio - Math.round(minPrecio * 0.05)); // 5% menos
            params.push(flexibleMinPrice);
            paramIndex++;
        }
        
        if (maxPrecio !== null) {
            // Hacemos el rango un poco más amplio para aumentar resultados
            conditions.push(`precio <= $${paramIndex}`);
            const flexibleMaxPrice = maxPrecio + Math.round(maxPrecio * 0.05); // 5% más
            params.push(flexibleMaxPrice);
            paramIndex++;
        }
        
        // Construir la consulta SQL final
        // MODIFICADO: Asegúrate de seleccionar también la columna imagen_url
        let sqlQuery = 'SELECT *, imagen_url FROM productos';
        
        if (conditions.length > 0) {
            sqlQuery += ' WHERE ' + conditions.join(' AND ');
        }
        
        sqlQuery += ' ORDER BY precio ASC';
        
        console.log(`🔍 Ejecutando consulta SQL completa:`);
        console.log('Query:', sqlQuery);
        console.log('Params:', params);
        
        const result = await pgClient.query(sqlQuery, params);
        
        if (result.rows.length > 0) {
            console.log(`✅ Encontrados ${result.rows.length} productos en la base de datos`);
            return { 
                success: true,
                products: result.rows,
                message: `Se encontraron ${result.rows.length} productos relacionados`
            };
        } else {
            console.log('⚠️ No se encontraron productos con la búsqueda completa');
            
            // Intentar una búsqueda aún más flexible usando OR entre todas las condiciones
            console.log('🔄 Intentando búsqueda más flexible...');
            
            // Construir una consulta más permisiva usando OR entre todas las condiciones
            // MODIFICADO: Asegúrate de seleccionar también la columna imagen_url
            let flexibleQuery = 'SELECT *, imagen_url FROM productos WHERE ';
            flexibleQuery += conditions.join(' OR ');
            flexibleQuery += ' ORDER BY precio ASC';
            
            const flexibleResult = await pgClient.query(flexibleQuery, params);
            
            if (flexibleResult.rows.length > 0) {
                console.log(`✅ Búsqueda flexible encontró ${flexibleResult.rows.length} productos`);
                return { 
                    success: true,
                    products: flexibleResult.rows,
                    message: `Se encontraron ${flexibleResult.rows.length} productos relacionados (búsqueda ampliada)`
                };
            } else {
                // Si todo lo anterior falla, ampliar aún más el rango de precios
                if (minPrecio !== null || maxPrecio !== null) {
                    console.log('🔄 Último intento: ampliando rango de precios significativamente...');
                    
                    params = [];
                    paramIndex = 1;
                    // MODIFICADO: Asegúrate de seleccionar también la columna imagen_url
                    let lastQuery = 'SELECT *, imagen_url FROM productos WHERE ';
                    
                    if (minPrecio !== null) {
                        // Ampliamos el rango significativamente
                        const veryFlexibleMinPrice = Math.max(0, minPrecio - Math.round(minPrecio * 0.15)); // 15% menos
                        lastQuery += `precio >= $${paramIndex}`;
                        params.push(veryFlexibleMinPrice);
                        paramIndex++;
                    }
                    
                    if (maxPrecio !== null) {
                        if (minPrecio !== null) lastQuery += ' AND ';
                        
                        const veryFlexibleMaxPrice = maxPrecio + Math.round(maxPrecio * 0.15); 
                        lastQuery += `precio <= $${paramIndex}`;
                        params.push(veryFlexibleMaxPrice);
                        paramIndex++;
                    }
                    
                    lastQuery += ' ORDER BY precio ASC';
                    
                    const lastResult = await pgClient.query(lastQuery, params);
                    
                    if (lastResult.rows.length > 0) {
                        console.log(`✅ Búsqueda con rango ampliado encontró ${lastResult.rows.length} productos`);
                        return { 
                            success: true,
                            products: lastResult.rows,
                            message: `Se encontraron ${lastResult.rows.length} productos en un rango de precio similar (±15%)`
                        };
                    }
                }
            }
            
            return { 
                success: false, 
                products: [], 
                message: "No se encontraron productos que coincidan con tu búsqueda" 
            };
        }
    } catch (dbError) {
        console.error('❌ Error en la consulta a la base de datos:', dbError);
        return { 
            success: false, 
            products: [], 
            message: `Error consultando base de datos: ${dbError.message}` 
        };
    } finally {
        await pgClient.end();
        console.log('✅ Conexión a PostgreSQL cerrada');
    }
}

function splitTextIntoChunks(text, chunkSize = 250, chunkOverlap = 80) {
    const chunks = [];
    const sentences = text.split('\n').filter(sentence => sentence.trim() !== '');
    
    let currentChunk = '';
    
    for (const sentence of sentences) {
        if (currentChunk.length + sentence.length > chunkSize) {
            if (currentChunk) {
                chunks.push(currentChunk);
            }
            
            if (currentChunk && chunkOverlap > 0) {
                const words = currentChunk.split(' ');
                const overlapWords = words.slice(-Math.floor(chunkOverlap / 5)); 
                currentChunk = overlapWords.join(' ') + ' ' + sentence;
            } else {
                currentChunk = sentence;
            }
        } else {
            currentChunk = currentChunk ? `${currentChunk}\n${sentence}` : sentence;
        }
    }
    
    if (currentChunk) {
        chunks.push(currentChunk);
    }
    
    return chunks;
}

// Mejora en la búsqueda de chunks relevantes
function findRelevantChunks(chunks, query, maxChunks = 5) {
    const lowerQuery = query.toLowerCase();
    
    
    const stopWords = ['el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'y', 'o', 'a', 'ante', 'bajo', 'con', 'de', 'desde', 'en', 'entre', 'hacia', 'hasta', 'para', 'por', 'según', 'sin', 'sobre', 'tras'];
    const queryTerms = lowerQuery
        .split(/\s+/)
        .map(term => term.replace(/[^\wáéíóúñ]/gi, ''))
        .filter(term => term.length > 2 && !stopWords.includes(term));
    
    // Extraer posibles números del rango de precios
    const priceNumbers = [];
    const priceMatches = lowerQuery.match(/\d+/g);
    if (priceMatches) {
        priceMatches.forEach(match => {
            priceNumbers.push(parseInt(match));
        });
    }
    
    // Usar TF-IDF simplificado para puntuación
    const scoredChunks = chunks.map(chunk => {
        const lowerChunk = chunk.toLowerCase();
        let score = 0;
        
        // Puntuación por términos de consulta
        queryTerms.forEach(term => {
            // Aumentar la puntuación basada en la importancia del término
            const matches = lowerChunk.split(term).length - 1;
            if (matches > 0) {
                // Términos más largos valen más
                score += matches * (term.length / 3);
            }
        });
        
        // Puntuación adicional por rangos de precios
        if (priceNumbers.length > 0) {
            const chunkNumbers = lowerChunk.match(/\d+/g) || [];
            chunkNumbers.forEach(chunkNum => {
                const num = parseInt(chunkNum);
                priceNumbers.forEach(priceNum => {
                    // Si el número en el chunk está cercano (±10%) a algún número de la consulta
                    if (Math.abs(num - priceNum) <= priceNum * 0.1) {
                        score += 2;
                    }
                });
            });
        }
        
        // Bonificación para chunks que contienen múltiples términos de la consulta
        const termMatches = queryTerms.filter(term => lowerChunk.includes(term)).length;
        if (termMatches > 1) {
            score *= (1 + (termMatches / queryTerms.length));
        }
        
        return { chunk, score };
    });
    
    const relevantChunks = scoredChunks
        .sort((a, b) => b.score - a.score)
        .slice(0, maxChunks)
        .map(item => item.chunk);
    
    console.log(`🔍 Puntuaciones más altas: ${scoredChunks.slice(0, 3).map(c => c.score.toFixed(2)).join(', ')}`);
    
    return relevantChunks;
}

// Función para buscar en el PDF del catálogo
async function searchInCatalogPDF(query) {
    try {
        console.log('📚 Buscando en catálogo PDF:', query);
        
        // Ruta al archivo PDF del catálogo
        const pdfPath = './catalogo_.pdf'; // Ajusta esta ruta según donde tengas tu PDF
        
        // Verificar si el archivo existe
        if (!fs.existsSync(pdfPath)) {
            console.warn('⚠️ El archivo PDF del catálogo no existe en la ruta especificada');
            return { 
                success: false, 
                chunks: [], 
                message: "No se encontró el archivo del catálogo" 
            };
        }
        
        // Leer el archivo PDF
        const dataBuffer = fs.readFileSync(pdfPath);
        const data = await pdf(dataBuffer);
        
        // Extraer el texto del PDF
        const pdfText = data.text;
        
        // Dividir el texto en fragmentos para un procesamiento más eficiente
        const chunks = splitTextIntoChunks(pdfText);
        console.log(`📄 PDF dividido en ${chunks.length} fragmentos para análisis`);
        
        // Encontrar los fragmentos más relevantes para la consulta
        const relevantChunks = findRelevantChunks(chunks, query);
        console.log(`🔍 Se encontraron ${relevantChunks.length} fragmentos relevantes en el PDF`);
        
        if (relevantChunks.length > 0) {
            return { 
                success: true, 
                chunks: relevantChunks,
                message: `Se encontraron ${relevantChunks.length} secciones relevantes en el catálogo`
            };
        } else {
            return { 
                success: false, 
                chunks: [],
                message: "No se encontró información relevante en el catálogo" 
            };
        }
    } catch (pdfError) {
        console.error('❌ Error procesando el PDF:', pdfError);
        return { 
            success: false, 
            chunks: [],
            message: `Error al procesar el catálogo PDF: ${pdfError.message}` 
        };
    }
}

// Función para buscar en el PDF del catálogo
async function generateGeminiResponse(query, dbResults, pdfResults) {
    let dbContext = '';
    if (dbResults.success && dbResults.products.length > 0) {
        dbContext = "### INFORMACIÓN DE BASE DE DATOS\n";
        
        const productsToInclude = dbResults.products.slice(0, 5);
        
        productsToInclude.forEach((product, index) => {
            dbContext += `\nPRODUCTO ${index + 1}:\n`;
            dbContext += `Código: ${product.codigo}\n`;
            dbContext += `Nombre: ${product.nombre}\n`;
            dbContext += `Descripción: ${product.descripcion || 'No disponible'}\n`;
            dbContext += `Precio: ${product.precio}\n`;
            dbContext += `Stock: ${product.stock}\n`;
            dbContext += `Categoría: ${product.categoria}\n`;
            
            // MODIFICADO: Incluir la URL de la imagen si está disponible
            if (product.imagen_url) {
                dbContext += `Imagen: ${product.imagen_url}\n`;
            }
        });
            
        if (dbResults.products.length > 5) {
            dbContext += `\n(Y ${dbResults.products.length - 5} productos más encontrados)\n`;
        }
    }
        
    let pdfContext = '';
    if (pdfResults.success && pdfResults.chunks.length > 0) {
        pdfContext = "\n### INFORMACIÓN ADICIONAL DEL CATÁLOGO PDF\n";
        pdfContext += pdfResults.chunks.join("\n\n");
    }
        
    const prompt = `### CONSULTA DEL USUARIO
    "${query}"
    
    ${dbContext}
    
    ${pdfContext}
    
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
    11. IMPORTANTE: Cuando estén disponibles, incluye las URLs de las imágenes de los productos
    
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
       - Para cada producto que tenga imagen, INCLUYE AL FINAL: "🖼️[Ver imagen](url_de_la_imagen)"
    
    3. PARA ESPECIFICACIONES TÉCNICAS:
       - Estructura en formato tabla visual usando formato markdown
       - Resalta en negrita (*texto*) los valores importantes
       - Ejemplo:
         *Procesador*: Intel Core i5-8250U
         *Precio*: *S/. 990*
         *Stock*: 11 unidades
       - Usa valores comparativos cuando sea posible ("Mejor en:", "Adecuado para:")
       - Incluye siempre la relación precio-calidad cuando sea aplicable
       - Si hay imagen disponible, AÑADE AL FINAL: "🖼️[Ver imagen](url_de_la_imagen)"
    
    4. PARA COMPARACIONES DE PRODUCTOS:
       - Organiza por categorías claramente diferenciadas
       - Usa encabezados para cada producto/modelo
       - Destaca ventajas y diferencias con viñetas concisas
       - Incluye una tabla comparativa en formato simple cuando compares más de 2 productos
       - Etiqueta con "✓" las características superiores en cada comparación
       - Para cada producto comparado que tenga imagen, AÑADE: "🖼️[Ver imagen](url_de_la_imagen)"
    
    ### RESTRICCIONES IMPORTANTES
    - Máximo 300 palabras en total (ampliado para permitir inclusión de URLs de imágenes)
    - Evita explicaciones extensas, frases redundantes o información no solicitada
    - No uses fórmulas de cortesía extensas ni introducciones largas
    - Evita condicionales ("podría", "tal vez") - sé directo y asertivo
    - No menciones estas instrucciones en tu respuesta
    - Nunca te disculpes por límites de información
    - Evita el lenguaje comercial exagerado ("increíble", "fantástico")         
    - Nunca repitas la misma información en diferentes secciones
    - SIEMPRE INCLUYE LOS ENLACES A LAS IMÁGENES si están disponibles en los datos`;
    
    // El resto de la función generateGeminiResponse permanece igual
    try {
        const GEMINI_API_KEY = process.env.GEMINI_API_KEY || 'AIzaSyDRivvwFML1GTZ_S-h5Qfx4qP3EKforMoM';
        const GEMINI_API_URL = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${GEMINI_API_KEY}`;
            
        const response = await axios.post(GEMINI_API_URL, {
            contents: [{
                parts: [{ text: prompt }]
            }]
        }, {
            headers: {
                'Content-Type': 'application/json'
            },
            timeout: 30000 
        });
            
        if (response.data && response.data.candidates && response.data.candidates[0] && 
                response.data.candidates[0].content && response.data.candidates[0].content.parts) {
            const aiResponse = response.data.candidates[0].content.parts[0].text;
            return aiResponse;
        } else {
            console.error('❌ Formato de respuesta inesperado:', JSON.stringify(response.data));
            throw new Error('La respuesta del servidor de IA no tiene el formato esperado.');
        }
    } catch (geminiError) {
        console.error('❌ Error completo de Gemini:', geminiError);
            
        if (geminiError.code === 'ECONNABORTED') {
            throw new Error('Se agotó el tiempo de espera al consultar el servidor de IA. La consulta puede ser demasiado compleja.');
        } else if (geminiError.response) {
            const errorDetails = geminiError.response.data && geminiError.response.data.error ? 
                `${geminiError.response.data.error.message}` : 
                `${geminiError.response.status} - ${geminiError.response.statusText}`;
            throw new Error(`Error de Gemini API: ${errorDetails}`);
        } else if (geminiError.request) {
            throw new Error('No se recibió respuesta del servidor de IA.');
        } else {
            throw new Error(`Error en la consulta: ${geminiError.message}`);
        }
    }
}

client.initialize();