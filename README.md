# whatsapp-kb

Librería para contestar WhatsApp con lo que haya en unos archivos locales. No trae un negocio adentro: el nombre, el alcance, el prompt y los archivos los pone quien la usa.

Indexa PDF y Excel, busca por distancia de coseno y, solo si hay un trozo cerca, pide una respuesta al modelo configurado. Si el dato no está, manda el texto fijo de la configuración.

## Instalar

Hace falta Python 3.12 o 3.13.

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

Las rutas del YAML son relativas al archivo de configuración. Los secretos van en `.env`, al lado de ese archivo. Completá `name` y `scope` con el negocio. `{{name}}` y `{{scope}}` del prompt se reemplazan con esos dos campos.

El modelo que contesta:

```yaml
model:
  provider: openai          # cursor, openai, xai o anthropic
  name: gpt-4.1-mini
  api_key_env: OPENAI_API_KEY
  max_output_tokens: 180
```

| `provider` | Variable en `.env` | `name` de ejemplo |
| --- | --- | --- |
| `cursor` | `CURSOR_API_KEY` | `composer-2.5` |
| `openai` | `OPENAI_API_KEY` | `gpt-4.1-mini` |
| `xai` | `XAI_API_KEY` | `grok-4` |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-5` |

`CURSOR_API_KEY` se crea en [Cursor Dashboard → Integrations](https://cursor.com/dashboard/integrations). `base_url` solo hace falta para un proxy, y tiene que ser `https` salvo localhost.

Para WhatsApp, en `.env`:

| Variable | Uso |
| --- | --- |
| `WHATSAPP_PHONE_NUMBER_ID` | Id del número en la app de Meta |
| `WHATSAPP_TOKEN` | Token de acceso |
| `WHATSAPP_VERIFY_TOKEN` | El que elegís al dar de alta el webhook |
| `WHATSAPP_APP_SECRET` | Secreto de la app, para firmar el webhook |

El resto de los valores está en `config.example.yaml`. `handoff` es el texto cuando el dato no está. `pause_hours` deja ese chat en silencio para que lo siga una persona. `rate_per_minute` es el cupo de mensajes por número.

## Archivos

Todo `.pdf` y `.xlsx` dentro de `knowledge/` entra al índice. Una fila del Excel queda como `columna: valor`. Un `.xls` hay que guardarlo como `.xlsx`. Una página de PDF casi sin texto se transcribe solo si el proveedor es Cursor. Con los otros, esa página queda afuera.

El índice vive en `data/index.db`, junto con números y preguntas. Esa carpeta no debería compartirse. Un archivo que no cambió no se vuelve a embeber. Si cambió, `whatsapp-kb reindex --config config.yaml`. `--force` vuelve a embeber todo.

## Usarlo

Dejá los PDF y Excel en `knowledge/` y, con el entorno virtual activo:

```bash
whatsapp-kb ask --config config.yaml "¿cuál es el horario?"
```

La primera vez descarga el modelo de embeddings. Si el dato no está, imprime el `handoff`.

```bash
whatsapp-kb pending --config config.yaml
whatsapp-kb pending --config config.yaml --done 3
whatsapp-kb unpause --config config.yaml 5491111111111
whatsapp-kb serve --config config.yaml
```

`pending` lista lo que quedó para una persona. `--done` borra esa fila y `unpause` vuelve a habilitar ese número. `serve` reindexa y queda en `http://0.0.0.0:8080`. Hace falta la clave del modelo y las cuatro variables de WhatsApp.

## Desde otro proyecto

```python
from whatsapp_kb import KnowledgeBot

bot = KnowledgeBot.open("config.yaml")
bot.reindex()
outcome = bot.answer("pregunta del cliente")
app = bot.asgi()
```

`app` expone `GET /webhook` y `POST /webhook`. Una fuente nueva se publica en `whatsapp_kb.sources` y una revisión de salida en `whatsapp_kb.guards`.

## WhatsApp

`serve` tiene que estar corriendo y el webhook tiene que ser una URL HTTPS pública. En local alcanza un túnel (`cloudflared` o ngrok) hacia el puerto 8080.

1. Creá una app en Meta, agregá el producto WhatsApp y suscribí el campo `messages`.
2. Empezá con el número de prueba y agendá los celulares que pueden escribirle. Así no migrás el número que ya atiende una persona.
3. En el webhook, la URL es `https://<tu-host>/webhook` y el verify token es `WHATSAPP_VERIFY_TOKEN`.
4. Escribile al número. El bot contesta texto dentro de las 24 horas que abre ese mensaje.

Conectar el número que ya usa la app del teléfono puede dejar ese chat fuera del teléfono, salvo que la cuenta tenga la coexistencia de Meta.

## Docker

```bash
cp config.example.yaml config.yaml
cp .env.example .env
mkdir -p knowledge data
docker compose up --build
```

El proceso corre con el usuario 1000. `data/` tiene que poder escribirse con ese usuario.

## Seguridad

La respuesta se envía si cita trozos de la búsqueda y los importes coinciden con esos trozos. Si el dato no está, sale el texto fijo de la configuración, no el texto del modelo. Un horario o una dirección escritos en palabras pueden colarse. El mensaje de la persona entra como dato, y no hay memoria de chat.
