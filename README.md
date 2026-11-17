# whatsapp-kb

Librería para contestar WhatsApp con lo que haya en unos archivos locales. No trae un negocio adentro: el nombre, el alcance, el prompt y los archivos los pone quien la usa.

Indexa PDF y Excel, busca por distancia de coseno y, solo si hay un trozo cerca, pide una respuesta al modelo configurado. Si el dato no está, manda el texto fijo de la configuración.

## Instalar

Hace falta Python 3.12 o 3.13. El modelo de embeddings no publica ruedas para versiones más nuevas.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Si `model.provider` es `cursor`, instalá también el extra: `pip install -e ".[cursor]"`. OpenAI, xAI y Claude usan el paquete base.

## Configurar

```bash
cp config.example.yaml config.yaml
cp .env.example .env
mkdir -p knowledge
```

Las rutas del YAML son relativas al archivo de configuración. Los secretos van en `.env`, no en el YAML.

Completá `name` y `scope` con el negocio. No dejes los marcadores `{{ }}` en esos dos campos: `serve` no arranca si siguen ahí. `refusal` es el texto cuando la consulta se sale de ese alcance o cuando el número superó el cupo. `handoff` es el texto cuando el dato no está en los archivos. `unavailable` es el texto cuando el modelo no responde: ese caso no pausa el chat. `non_text` se manda si el mensaje no es texto; si lo dejás vacío, el bot no contesta. `{{name}}` y `{{scope}}` del archivo `prompt_path` se reemplazan con esos dos campos.

El modelo que contesta:

```yaml
model:
  provider: openai          # cursor, openai, xai o anthropic
  name: gpt-4.1-mini
  api_key_env: OPENAI_API_KEY
  max_output_tokens: 180
  # base_url: https://api.openai.com/v1
```

| `provider` | Variable en `.env` | `name` de ejemplo |
| --- | --- | --- |
| `cursor` | `CURSOR_API_KEY` | `composer-2.5` |
| `openai` | `OPENAI_API_KEY` | `gpt-4.1-mini` |
| `xai` | `XAI_API_KEY` | `grok-4` |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-5` |

`CURSOR_API_KEY` se crea en [Cursor Dashboard → Integrations](https://cursor.com/dashboard/integrations). Con Cursor, `Cursor.models.list()` muestra los ids de la cuenta. `base_url` solo hace falta si usás un proxy compatible. Tiene que ser `https`, salvo `localhost` o `127.0.0.1`.

El índice local:

```yaml
embeddings:
  model: intfloat/multilingual-e5-small
  passage_prefix: "passage: "
  query_prefix: "query: "
```

Si el modelo de embeddings no usa esos prefijos, dejalos como `""`. Cambiar el modelo o los prefijos vuelve a embeber los archivos.

`retrieval.max_distance` es el tope de distancia de coseno (0.45 por defecto). Más bajo exige un trozo más parecido a la pregunta. `top_k` es cuántos trozos se mandan al modelo y `max_context_tokens` cuánto texto entran.

`limits.max_incoming_chars` recorta la pregunta. `max_reply_chars` recorta la respuesta. `pause_hours` es cuánto queda en silencio un chat después de un `handoff`. `rate_per_minute` es el cupo de mensajes por número, incluidas las respuestas que salen de la caché. Un valor `0` no deja pasar ninguno. Una falla del modelo no consume la pausa.

Para WhatsApp, en `.env`:

| Variable | Uso |
| --- | --- |
| `WHATSAPP_PHONE_NUMBER_ID` | Id del número en la app de Meta |
| `WHATSAPP_TOKEN` | Token de acceso |
| `WHATSAPP_VERIFY_TOKEN` | El que elegís al dar de alta el webhook |
| `WHATSAPP_APP_SECRET` | Secreto de la app, para firmar el webhook |

`whatsapp.graph_version` es la versión de Graph. El de defecto es `v27.0`. `server.port` es el puerto del webhook, 8080.

## Archivos

Todo `.pdf` y `.xlsx` dentro de `knowledge_dir` entra al índice. Una fila del Excel queda como `columna: valor`. Un `.xls` viejo hay que guardarlo como `.xlsx`. Si una página del PDF casi no tiene texto y el proveedor es Cursor con clave cargada, un agente con permiso de lectura transcribe esa página. El pedido de transcripción pide ignorar instrucciones que estén dentro del PDF y corre con el sandbox del SDK activado. Ese sandbox no está verificado contra una corrida real de Cursor: los tests simulan el SDK. Con OpenAI, xAI o Claude esa página queda afuera del índice. Si después agregás la clave de Cursor, la próxima indexación vuelve a leer los archivos.

Un archivo que no se puede leer se saltea y el resto sigue. `serve` arranca igual.

El índice vive en `data/index.db`, dentro de `data_dir`. Ahí también quedan números, preguntas y respuestas. Esa carpeta no debería compartirse. La primera indexación descarga el modelo de embeddings. Un archivo que no cambió no se vuelve a embeber. Si cambió, volvé a correr `whatsapp-kb reindex --config config.yaml`. `ask` y el arranque de `serve` también reindexan. `whatsapp-kb reindex --config config.yaml --force` vuelve a embeber todo.

## Usarlo

En la carpeta del proyecto, con el entorno virtual activo. Al abrir la configuración, el proceso lee el `.env` que está en la misma carpeta y no pisa variables que ya estén en el entorno. Si preferís cargarlo en el shell:

```bash
set -a
source .env
set +a
```

Dejá los `.pdf` y `.xlsx` en `knowledge/`. Para probar sin WhatsApp:

```bash
whatsapp-kb ask --config config.yaml "¿cuál es el horario?"
```

Eso reindexa y escribe la respuesta en la terminal. La primera vez descarga el modelo de embeddings. Si el dato no está, imprime el texto de `handoff`.

```bash
whatsapp-kb pending --config config.yaml
whatsapp-kb pending --config config.yaml --done 3
whatsapp-kb unpause --config config.yaml 5491111111111
```

`pending` lista las preguntas que quedaron para una persona: id, fecha, número y texto, separados por tabulador. En `ask` el número va vacío. `--done` borra esa fila. `unpause` vuelve a dejar que el bot conteste ese número.

Si cambiaste un archivo:

```bash
whatsapp-kb reindex --config config.yaml
```

Imprime cuántos trozos quedaron en el índice. Un archivo igual al anterior no se vuelve a embeber.

Para dejarlo escuchando WhatsApp:

```bash
whatsapp-kb serve --config config.yaml
```

Reindexa al arrancar y queda en `http://0.0.0.0:8080` (el `server.port` de la config). Hace falta el teléfono, el token, el verify token, el app secret y la clave del modelo. También tienen que existir el prompt y la carpeta de archivos. El proceso sigue corriendo hasta que lo cortes. Un cambio en `knowledge/` entra cuando reiniciás `serve` o corrés `reindex` en otra terminal. No corras dos `reindex` a la vez: el segundo espera un lock en `data/`.

## Desde otro proyecto

```python
from whatsapp_kb import KnowledgeBot

bot = KnowledgeBot.open("config.yaml")
bot.reindex()
outcome = bot.answer("pregunta del cliente")
app = bot.asgi()
```

`outcome.handed_off` dice si salió el texto fijo. `app` es una aplicación ASGI con `GET /webhook` y `POST /webhook`, para montarla en otro servicio. `bot.serve()` la levanta sola.

Para sumar una fuente o una revisión de salida, publicá un entry point en `whatsapp_kb.sources` o `whatsapp_kb.guards`. La clase de fuente implementa `supports(path)` y `load(path)`. La revisión implementa `allow(text, cited)`.

## WhatsApp

`serve` tiene que estar corriendo y el webhook tiene que ser una URL HTTPS pública. En local alcanza un túnel (`cloudflared` o ngrok) hacia el puerto 8080.

1. Creá una app en Meta, agregá el producto WhatsApp y suscribí el campo `messages`.
2. Empezá con el número de prueba y agendá los celulares que pueden escribirle. Así no migrás el número que ya atiende una persona.
3. En el webhook, la URL es `https://<tu-host>/webhook` y el verify token es `WHATSAPP_VERIFY_TOKEN`.
4. Escribile al número. El bot contesta texto dentro de la ventana de 24 horas que abre ese mensaje. Valida el token, revisa la firma `X-Hub-Signature-256` y no responde dos veces el mismo envío.

Conectar el número que ya usa la app del teléfono puede dejar ese chat fuera del teléfono, salvo que la cuenta tenga la coexistencia de Meta. Ese paso es de quien despliega.

Un chat que el bot no puede contestar queda pausado (`pause_hours`) para que una persona siga la conversación sin que el bot vuelva a escribir.

## Docker

```bash
cp config.example.yaml config.yaml
cp .env.example .env
mkdir -p knowledge data
docker compose up --build
```

Los volúmenes son la config, `knowledge/`, `prompts/` y `data/`. El proceso corre con el usuario 1000. `data/` tiene que poder escribirse con ese usuario.

## Seguridad

El mensaje de la persona y el texto de los archivos entran como datos, con `<` y `>` escapados. Cursor corre en local, con `tools=[]` para contestar, sin ajustes del proyecto ni del usuario, y con una carpeta de trabajo vacía. OpenAI, xAI y Claude reciben solo ese texto, sin herramientas. La respuesta se envía si el JSON cita trozos de esa búsqueda y, en el texto, los importes coinciden en valor con los citados, y las URLs, los mails, los teléfonos y los enteros de dos o más cifras aparecen en esos trozos. `$1.000` y `$1000` cuentan como el mismo valor. `$10.00` no cuenta como `$1000`. Los números escritos con palabras no se verifican. Citar un trozo no prueba que cada frase salga de él: un horario o una dirección inventados, sin números ni links, pueden pasar. Si la revisión no cierra, sale el texto fijo de la config, no el texto del modelo.

No hay memoria de chat. Una respuesta aceptada, con los mismos archivos y la misma configuración, no vuelve a llamar al modelo. Cambiar el prompt, el nombre, el alcance, los textos fijos o el modelo deja de usar esa caché. Un `handoff` no se cachea: cada número queda pausado y en `pending`. Si la búsqueda queda lejos del umbral, el modelo no se llama. Hay un cupo de mensajes por número.

La firma del webhook se calcula sobre el cuerpo, con un tope de 1 MB. El verify token se compara sin filtrar el largo. El `phone_number_id` tiene que ser el de la config. No hay `/docs` ni otro endpoint de administración. Un error al procesar un mensaje no frena el resto del envío.
