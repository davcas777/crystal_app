# Crystal — Frontend de AI Gateway

Una **Databricks App** con la imagen corporativa de Crystal que le da a los empleados una sola interfaz de chat para consumir los endpoints del AI Gateway (`gpt`, `claude` o cualquier otro que registren). Cada usuario tiene su propio historial de conversaciones, puede cambiar de endpoint desde un menú lateral y puede adjuntar PDFs, documentos de Word, archivos de texto o imágenes para que el modelo los analice.

Construida con **Streamlit** + la API compatible con OpenAI del Databricks AI Gateway. Lista para clonar, parametrizada y se despliega con un único comando del CLI.

---

## Funcionalidades

| | |
|---|---|
| Selector de modelo | Menú lateral con todos los endpoints listados en `app.yaml` (no requiere cambios de código para agregar nuevos) |
| Archivos adjuntos | PDF, Word (`.docx`), texto / CSV / Markdown e imágenes (PNG / JPG / WebP / GIF). El texto se inserta en el prompt; las imágenes se envían a los modelos multimodales con el esquema de visión de OpenAI |
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

## Despliegue en su propio workspace de Databricks

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
    value: '[{"name":"gpt","label":"OpenAI GPT"},{"name":"claude","label":"Anthropic Claude"}]'
```

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

### 5. Otorgarle permisos a la app sobre el AI Gateway

La app corre con un **service principal** que Databricks crea automáticamente al provisionarla. Ese service principal necesita el permiso `CAN_QUERY` sobre cada endpoint de serving que se exponga a través del gateway:

- Workspace UI → **Serving** → seleccionar el endpoint → **Permissions** → agregar el service principal de la app con **Can Query**.

En producción la app lee el token del service principal desde la variable `DATABRICKS_CLIENT_TOKEN` que Databricks Apps inyecta automáticamente — no se necesita un PAT.

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
| `AI_GATEWAY_ENDPOINTS` | sí | `gpt,claude` | Nombres separados por coma o arreglo JSON de `{name, label}` |
| `AI_GATEWAY_MAX_TOKENS` | no | `1024` | Tope de tokens por respuesta |
| `CHAT_HISTORY_DB_PATH` | no | `/tmp/crystal_chat_history.db` | Archivo SQLite para el historial |
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

## Soporte

Responsable interno: **David Cascante Espinoza** — `david.cascante@databricks.com`
