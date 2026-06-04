# Crystal — Frontend de AI Gateway

Una **Databricks App** con la imagen corporativa de Crystal que le da a los empleados una sola interfaz de chat para consumir los endpoints del AI Gateway (`gpt`, `claude` o cualquier otro que registren). Cada usuario tiene su propio historial de conversaciones, puede cambiar de endpoint desde un menú lateral y puede adjuntar PDFs, documentos de Word, archivos de texto o imágenes para que el modelo los analice.

Construida con **Streamlit** + la API compatible con OpenAI del Databricks AI Gateway. Lista para clonar, parametrizada y se despliega con un único comando del CLI.

---

## Funcionalidades

| | |
|---|---|
| Selector de modelo | Menú lateral con todos los endpoints listados en `app.yaml` (no requiere cambios de código para agregar nuevos) |
| Archivos adjuntos | PDF, Word (`.docx`), Excel (`.xlsx`/`.xls`), texto / CSV / Markdown e imágenes (PNG / JPG / WebP / GIF). El texto se inserta en el prompt; las imágenes se envían a los modelos multimodales con el esquema de visión de OpenAI |
| **Generación de imágenes** | Con modelos OpenAI, un botón **🎨 Imagen** genera imágenes a partir del texto del usuario, vía la **Responses API** + herramienta `image_generation`. Se transmite por streaming (la imagen aparece de forma progresiva) y se guarda en el historial. Ver la sección [Generación de imágenes](#generación-de-imágenes-modelos-openai) |
| Historial por usuario | Almacenado en SQLite e indexado por el correo del usuario (`X-Forwarded-Email`). Cada usuario puede crear, renombrar, alternar y borrar múltiples conversaciones |
| Imagen de Crystal | Logo, paleta corporativa (negro + rojo) y el lema *"Tejemos vida para nuestro planeta"* |
| Respuestas en streaming | Los tokens se imprimen en vivo en el panel de chat |
| 100% parametrizada | URL base, lista de endpoints, máximo de tokens y ruta del historial vienen de variables de entorno en `app.yaml` |

---

## Estructura del repositorio

```
crystal_app/
├── app.py                  ← Punto de entrada de Streamlit
├── app.yaml                ← Configuración de Databricks Apps (variables de entorno)
├── requirements.txt
├── README.md
├── .env.example
├── .gitignore
├── .streamlit/
│   └── config.toml         ← Tema visual de Streamlit
├── static/
│   ├── logo.png            ← Logo de Crystal (reemplazable)
│   └── styles.css          ← CSS de marca
└── utils/
    ├── auth.py             ← Lee al usuario autenticado desde los headers de Databricks
    ├── chat_history.py     ← Persistencia de conversaciones en SQLite
    ├── config.py           ← Configuración basada en variables de entorno
    └── file_handler.py     ← Extracción de contenido de PDF / Word / texto / imagen
```

---

## Despliegue rápido (un solo comando)

Si ya tiene el CLI de Databricks autenticado, basta con:

```bash
git clone https://github.com/davcas777/crystal_app.git
cd crystal_app

./scripts/deploy.sh \
  --host  https://<SU-WORKSPACE>.azuredatabricks.net \
  --user  usted@crystal.com.co \
  --app   crystal-ai-assistant \
  --endpoints gpt,claude
```

El script hace todo:

1. Sincroniza el código al workspace
2. Crea la app (si no existe)
3. Resuelve el service principal de la app y le otorga `CAN_QUERY` sobre cada endpoint del AI Gateway que liste en `--endpoints`
4. Despliega el código
5. Imprime la URL pública

Si prefiere hacerlo a mano, siga los pasos detallados abajo.

---

## Despliegue manual paso a paso

### 1. Clonar el repositorio

```bash
git clone https://github.com/davcas777/crystal_app.git
cd crystal_app
```

### 2. Editar `app.yaml` con su AI Gateway

Abra `app.yaml` y actualice los dos campos que apuntan a su workspace:

```yaml
env:
  - name: AI_GATEWAY_BASE_URL
    value: "https://<SU-WORKSPACE>.azuredatabricks.net/ai-gateway/mlflow/v1"

  - name: AI_GATEWAY_ENDPOINTS
    value: '[{"name":"gpt","label":"OpenAI GPT","image_model":"gpt"},{"name":"claude","label":"Anthropic Claude"}]'
```

> El campo opcional `"image_model"` habilita la generación de imágenes en esa ruta (solo modelos OpenAI). Ver [Generación de imágenes](#generación-de-imágenes-modelos-openai).

Los endpoints aceptan dos formatos:

- **Formato corto** — solo nombres: `gpt,claude,llama-3`
- **Formato completo** — arreglo JSON con etiquetas de visualización (recomendado para usuarios finales):
  ```json
  [
    {"name": "gpt",    "label": "OpenAI GPT"},
    {"name": "claude", "label": "Anthropic Claude"}
  ]
  ```

El campo `name` debe coincidir exactamente con el nombre del endpoint registrado en el AI Gateway.

### 3. (Opcional) Cambiar el logo

Reemplace `static/logo.png` con la versión que prefiera (cualquier tamaño razonable; la barra lateral lo renderiza a 160 px de ancho).

### 4. Crear y desplegar la app con el CLI de Databricks

Instale y autentíquese una sola vez:

```bash
pip install databricks-cli
databricks auth login --host https://<SU-WORKSPACE>.azuredatabricks.net
```

Suba el código a una carpeta del workspace y cree + despliegue la app:

```bash
# 1. Subir el código al workspace
databricks workspace import-dir . /Workspace/Users/<usted@crystal.com.co>/crystal_app --overwrite

# 2. Crear la app (una sola vez)
databricks apps create crystal-ai-assistant \
  --description "Crystal AI Assistant — frontend del AI Gateway"

# 3. Desplegar el código sincronizado
databricks apps deploy crystal-ai-assistant \
  --source-code-path /Workspace/Users/<usted@crystal.com.co>/crystal_app
```

El CLI devuelve la URL pública cuando el build termina (2 a 4 minutos típicamente).

### 5. Otorgarle permisos a la app sobre los endpoints del AI Gateway

> **Importante:** los endpoints registrados en el **AI Gateway** (los que se consumen vía `/ai-gateway/mlflow/v1/chat/completions`) son un tipo de objeto distinto a los *Model Serving Endpoints* normales. No los encontrará en *Serving* — están bajo **Settings → AI Gateway → Endpoints**. Los permisos se manejan por separado.

Al crearse la app, Databricks le asigna un **service principal** propio (lo verá en la salida de `databricks apps get crystal-ai-assistant` en el campo `service_principal_client_id`). Ese SP necesita `CAN_QUERY` sobre cada endpoint del AI Gateway que la app vaya a usar.

#### Opción A — UI (recomendado)

1. Workspace UI → **Serving** (menú lateral) → pestaña **AI Gateway** (o ir directamente a `https://<workspace>/ml/aigateway`).
2. Click en el endpoint (`gpt`, `claude`, etc.) → botón **Permissions**.
3. **Add permissions** → buscar el service principal por nombre (algo como `app-xxxxxx crystal-ai-assistant`) → asignar **Can Query** → **Save**.
4. Repetir para cada endpoint expuesto en `AI_GATEWAY_ENDPOINTS`.

#### Opción B — REST API / curl (para automatizar)

```bash
SP="<service_principal_client_id de la app>"
HOST="https://<su-workspace>.azuredatabricks.net"
TOKEN=$(databricks auth token --profile DEFAULT | jq -r .access_token)

for ep in gpt claude; do
  curl -X PATCH "$HOST/api/2.0/permissions/ai-gateway-endpoints/$ep" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"access_control_list\":[{\"service_principal_name\":\"$SP\",\"permission_level\":\"CAN_QUERY\"}]}"
done
```

El object_type es `ai-gateway-endpoints` (con guiones) — **no** es `serving-endpoints`. Si intenta el path de serving endpoints obtendrá `RESOURCE_DOES_NOT_EXIST`.

#### Autenticación dentro de la app

En tiempo de ejecución la app **no usa PAT**. Databricks Apps inyecta `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID` y `DATABRICKS_CLIENT_SECRET`, y la app usa el SDK de Databricks (`WorkspaceClient`) para conseguir un bearer token OAuth fresco en cada llamada al AI Gateway. Esto está implementado en `app.py` → `get_llm_client()`.

---

## Ejecución local (desarrollo)

```bash
# 1. Crear un entorno virtual e instalar dependencias
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Copiar la plantilla de variables y completarla con su PAT
cp .env.example .env
# editar .env

# 3. Exportar y ejecutar
set -a; source .env; set +a
streamlit run app.py
```

En modo local la app se autentica con el personal access token (`DATABRICKS_TOKEN`) y usa `LOCAL_USER_EMAIL` como identidad simulada.

---

## Referencia de configuración

Todas las opciones se configuran con variables de entorno (en `app.yaml` para la app desplegada o en `.env` localmente).

| Variable | Requerida | Valor por defecto | Descripción |
|---|---|---|---|
| `AI_GATEWAY_BASE_URL` | sí | — | URL base compatible con OpenAI, debe terminar en `/ai-gateway/mlflow/v1` |
| `AI_GATEWAY_ENDPOINTS` | sí | `gpt,claude` | Nombres separados por coma o arreglo JSON de `{name, label, image_model?}`. `image_model` habilita la generación de imágenes en esa ruta (solo OpenAI) |
| `AI_GATEWAY_MAX_TOKENS` | no | `1024` | Tope de tokens por respuesta |
| `CHAT_HISTORY_DB_PATH` | no | `/tmp/crystal_chat_history.db` | Archivo SQLite para el historial |
| `AI_GATEWAY_RESPONSES_BASE_URL` | no | derivado de `AI_GATEWAY_BASE_URL` + `/ai-gateway/openai/v1` | Base de la Responses API (generación de imágenes). Por defecto se deriva del host |
| `AI_GATEWAY_IMAGE_FORMAT` | no | `webp` | Formato de la imagen generada: `webp` / `jpeg` / `png` |
| `AI_GATEWAY_IMAGE_QUALITY` | no | `medium` | Calidad: `low` / `medium` / `high` |
| `AI_GATEWAY_IMAGE_SIZE` | no | `1024x1024` | Tamaño: `1024x1024` / `1024x1536` / `1536x1024` / `auto` |
| `AI_GATEWAY_IMAGE_COMPRESSION` | no | `60` | Compresión 0–100 (webp/jpeg) |
| `AI_GATEWAY_IMAGE_PARTIALS` | no | `2` | Nº de imágenes parciales progresivas durante el streaming |
| `DATABRICKS_TOKEN` | solo local | — | PAT para desarrollo local |
| `LOCAL_USER_EMAIL` | solo local | `anonymous@local` | Identidad simulada para desarrollo local |

### Persistir el historial entre reinicios

La ruta `/tmp` se borra cuando el pod de la Databricks App se reinicia. Para retención más larga:

1. **Rápido:** apuntar `CHAT_HISTORY_DB_PATH` a un Volumen de Databricks montado (`/Volumes/<catalog>/<schema>/<volume>/chat.db`).
2. **Producción:** reemplazar el store de SQLite en `utils/chat_history.py` por una tabla Delta consumida vía Databricks SQL. La interfaz pública del store es pequeña (`create_conversation`, `add_message`, `list_messages`, etc.) — una implementación basada en Delta es un reemplazo directo.

---

## Agregar un nuevo endpoint

1. Provisione el endpoint en el AI Gateway (cualquier modelo de cualquier proveedor — OpenAI, Anthropic, Bedrock, OSS).
2. Otórguele `CAN_QUERY` al service principal de la app.
3. Agréguelo a `AI_GATEWAY_ENDPOINTS` en `app.yaml`.
4. Ejecute `databricks apps deploy …` de nuevo.

Eso es todo — el selector de la barra lateral lo detecta automáticamente.

---

## Cómo se invoca el AI Gateway

La app utiliza el SDK de OpenAI para Python apuntando al Databricks AI Gateway. Equivale a:

```python
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.environ["DATABRICKS_TOKEN"],
    base_url="https://<workspace>.azuredatabricks.net/ai-gateway/mlflow/v1",
)

resp = client.chat.completions.create(
    model="claude",                # o "gpt", o el nombre que tengan registrado
    messages=[{"role": "user", "content": "Hola Crystal"}],
    max_tokens=1024,
    stream=True,
)
```

Para turnos multimodales (imagen adjunta), el mensaje del usuario se convierte en un arreglo de partes:

```python
{
  "role": "user",
  "content": [
    {"type": "text",      "text": "¿Qué ves en esta imagen?"},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
  ]
}
```

---

## Generación de imágenes (modelos OpenAI)

La app puede **generar imágenes** a partir del texto del usuario cuando la ruta seleccionada apunta a un **modelo OpenAI** (p.ej. la ruta `gpt`). En la barra inferior aparece un botón **🎨 Imagen**: al activarlo, ese turno genera una imagen en lugar de una respuesta de texto.

### Cómo funciona por dentro

El chat normal y la generación de imágenes usan **dos superficies distintas del mismo AI Gateway**:

| | Chat (texto) | Imagen (🎨 activado) |
|---|---|---|
| API | Chat Completions | **Responses API** + herramienta `image_generation` |
| Path | `…/ai-gateway/mlflow/v1/chat/completions` | `…/ai-gateway/openai/v1/responses` |
| Modelo | la ruta seleccionada (`gpt`, `claude`, …) | el `image_model` de esa ruta |
| Streaming | tokens de texto | imágenes parciales progresivas (`partial_images`) |

Puntos clave:

- **Solo modelos OpenAI** soportan `image_generation`. Claude (u otros no-OpenAI) no muestran el botón.
- La generación pasa por la **misma ruta gobernada del AI Gateway** que el chat (mismo `image_model`), por lo que **hereda sus ACLs, rate limits, usage tracking y guardrails**. No se le pega directo a un endpoint de sistema.
- El path de imágenes (`/ai-gateway/openai/v1`) **se deriva automáticamente** del host de `AI_GATEWAY_BASE_URL`; no hay que configurarlo (se puede sobreescribir con `AI_GATEWAY_RESPONSES_BASE_URL`).
- Se usa **streaming** a propósito: evita el límite síncrono de ~640 KB de la respuesta, muestra la imagen de forma progresiva y expone el error real del proveedor si algo falla.
- La imagen vuelve como **base64**, se renderiza en el chat y se **persiste embebida en el historial** (se vuelve a mostrar al reabrir la conversación).

### Habilitarla en una ruta

Agregue `"image_model"` a la entrada del endpoint en `AI_GATEWAY_ENDPOINTS`. Apúntelo a la **misma ruta** (para gobernanza unificada) o a una ruta dedicada (para presupuesto/límites separados):

```json
[
  {"name": "gpt",    "label": "OpenAI GPT", "image_model": "gpt"},
  {"name": "claude", "label": "Anthropic Claude"}
]
```

- `image_model` presente → la ruta es capaz de generar imágenes (aparece el botón 🎨).
- `image_model` ausente → la ruta es solo texto.

### Equivalente en código

```python
from openai import OpenAI
import os, base64

client = OpenAI(
    api_key=os.environ["DATABRICKS_TOKEN"],
    base_url="https://<workspace>.azuredatabricks.net/ai-gateway/openai/v1",
)

stream = client.responses.create(
    model="gpt",                       # la ruta OpenAI del AI Gateway (image_model)
    input="Genera una imagen de una camiseta blanca con un logo rojo.",
    tools=[{"type": "image_generation", "output_format": "webp",
            "quality": "medium", "partial_images": 2}],
    tool_choice="auto",
    stream=True,
)

for event in stream:
    if event.type == "response.image_generation_call.partial_image":
        with open("salida.webp", "wb") as f:
            f.write(base64.b64decode(event.partial_image_b64))
```

La implementación está en `app.py` → `get_responses_client()` y la rama `use_responses` del manejador de turnos. Los ajustes de imagen (formato, calidad, tamaño, compresión, parciales) son variables de entorno — ver la [Referencia de configuración](#referencia-de-configuración).

> **Nota de proveedor:** la herramienta `image_generation` resuelve al modelo de imágenes de OpenAI por detrás (p.ej. `gpt-image-*`). Si ese backend tiene una caída temporal río arriba, la app muestra un mensaje amigable y deja el error técnico real en un desplegable. Reintente en unos minutos.

---

## Troubleshooting

### `Missing credentials. Please pass an api_key…`
La app no encontró un bearer token. Causas típicas:

- Está ejecutando en local sin `DATABRICKS_TOKEN` en el `.env`.
- En la Databricks App, el SDK no logró autenticarse con OAuth M2M (revise que el SP tenga `Can Use` sobre el workspace y que las variables `DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET` estén disponibles — ambas se inyectan automáticamente, pero pueden faltar si la app está en un estado raro; redepliegue con `databricks apps deploy …`).

### `403 PERMISSION_DENIED — Doesn't have permission to query AI Gateway endpoint 'X'`
El service principal de la app no tiene `CAN_QUERY` sobre el endpoint del AI Gateway. Aplique los permisos como se describe en **Paso 5 — Otorgarle permisos a la app sobre los endpoints del AI Gateway**, o vuelva a correr `./scripts/deploy.sh`.

### `list index out of range` durante el streaming
Pasaba en versiones anteriores cuando el proveedor (ej. el endpoint `gpt`) emitía un chunk final con `choices: []` (solo estadísticas de uso). Ya está corregido en `app.py`. Si reaparece con un proveedor nuevo, la condición está en `for chunk in stream:` — sólo agregue su variante de chunk vacío al guard.

### `can only concatenate str (not "list") to str`
Pasa cuando un endpoint del AI Gateway proxia a Anthropic (u otro modelo con *content blocks*) y emite chunks de streaming con `delta.content` como **lista de bloques** en vez de string. Ya está manejado en `app.py` aplanando los bloques tipo `{"type":"text","text":"…"}`. Si aparece con un formato nuevo, extender el `isinstance(delta, list)` en el `for chunk in stream:` para cubrir el nuevo schema.

### El selector solo muestra un modelo
Su variable `AI_GATEWAY_ENDPOINTS` en `app.yaml` no quedó como JSON o como lista separada por comas. Use exactamente uno de:

```yaml
value: "gpt,claude"
```
o
```yaml
value: '[{"name":"gpt","label":"OpenAI GPT"},{"name":"claude","label":"Anthropic Claude"}]'
```

### El historial se borra cada vez que reinicia la app
Esperado — `/tmp` es efímero por pod. Cambie `CHAT_HISTORY_DB_PATH` a un Volumen de Databricks montado (`/Volumes/…/chat.db`) o reemplace el store por una tabla Delta (ver sección **Persistir el historial entre reinicios**).

---

## Soporte

Responsable interno: **David Cascante Espinoza** — `david.cascante@databricks.com`
