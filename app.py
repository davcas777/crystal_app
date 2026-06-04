"""
Crystal — AI Gateway Frontend (Databricks App)

A branded Streamlit chat app that fronts Databricks AI Gateway endpoints.
- Endpoint picker (configured via env vars)
- File attachments (PDF / Word / Excel / text / image) sent to the model
- Per-user chat history (multiple conversations per user, persisted to SQLite)
- Databricks-native authentication (reads X-Forwarded-Email header)
"""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path

import streamlit as st
from openai import OpenAI

from utils.auth import get_current_user
from utils.chat_history import ChatHistoryStore
from utils.config import load_config
from utils.file_handler import extract_file_content

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Crystal AI Assistant",
    page_icon="static/logo.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Config & singletons
# ---------------------------------------------------------------------------
config = load_config()
user = get_current_user()
store = ChatHistoryStore(db_path=config.history_db_path)

# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------
if "active_conversation_id" not in st.session_state:
    st.session_state.active_conversation_id = None
if "pending_attachments" not in st.session_state:
    st.session_state.pending_attachments = []
if "selected_endpoint" not in st.session_state:
    st.session_state.selected_endpoint = config.endpoints[0]["name"]
if "theme" not in st.session_state:
    st.session_state.theme = "light"
if "image_mode" not in st.session_state:
    st.session_state.image_mode = False

# Load CSS (base + theme override). Loaded after session-state init so the
# theme choice can flip a `data-theme` attribute on the app wrapper.
css_path = Path(__file__).parent / "static" / "styles.css"
base_css = css_path.read_text() if css_path.exists() else ""
st.markdown(f"<style>{base_css}</style>", unsafe_allow_html=True)
if st.session_state.theme == "dark":
    # Toggle is implemented by injecting a second <style> block whose
    # selectors override the light-mode variables.
    st.markdown(
        """
        <style>
        :root {
            --c-bg: #0E0E0E;
            --c-text: #F1F1F1;
            --c-text-muted: #A0A0A0;
            --c-text-soft: #6E6E6E;
            --c-border: #232323;
            --c-border-strong: #333333;
            --c-surface: #161616;
            --c-surface-hover: #1F1F1F;
            --c-shadow-soft: 0 1px 2px rgba(0,0,0,0.4);
        }
        /* ---- App + main area backgrounds ---- */
        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        .main,
        [data-testid="stMainBlockContainer"],
        [data-testid="block-container"] { background: #0E0E0E !important; color: #F1F1F1; }

        /* ---- All readable text inside main area (chat, markdown, headings) ----
           Streamlit nests text in stMarkdownContainer / stChatMessageContent with
           rules that beat my container-level color. Force light on every text node
           inside those containers in the main area. */
        .stApp p,
        .stApp li,
        .stApp ul, .stApp ol,
        .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
        .stApp span,
        .stApp strong, .stApp em, .stApp b, .stApp i,
        .stApp blockquote,
        .stApp label,
        .stMarkdown, .stMarkdown *,
        [data-testid="stMarkdownContainer"],
        [data-testid="stMarkdownContainer"] *,
        [data-testid="stChatMessage"] *,
        [data-testid="stChatMessageContent"] * { color: #F1F1F1 !important; }

        /* Subdued text (captions, hints, sidebar footer) should stay muted */
        [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] *,
        .stCaption, .stCaption *,
        .sidebar-footer, .brand-tagline,
        .sidebar-label { color: #A0A0A0 !important; }

        /* Links */
        .stApp a,
        [data-testid="stMarkdownContainer"] a,
        .stMarkdown a { color: #6BA6FF !important; }

        /* Inline + block code */
        [data-testid="stMarkdownContainer"] code,
        .stMarkdown code {
            background: #1A1A1A !important;
            color: #F8F8F2 !important;
            border: 1px solid #2E2E2E !important;
            padding: 0.05rem 0.3rem;
            border-radius: 4px;
        }
        [data-testid="stMarkdownContainer"] pre,
        .stMarkdown pre {
            background: #161616 !important;
            border: 1px solid #2E2E2E !important;
            color: #F8F8F2 !important;
        }
        [data-testid="stMarkdownContainer"] pre code,
        .stMarkdown pre code {
            background: transparent !important;
            border: none !important;
            padding: 0 !important;
            color: #F8F8F2 !important;
        }

        /* Tables (markdown) */
        [data-testid="stMarkdownContainer"] table,
        .stMarkdown table { border-color: #2E2E2E !important; }
        [data-testid="stMarkdownContainer"] th,
        .stMarkdown th {
            background: #1A1A1A !important;
            border-color: #2E2E2E !important;
            color: #F1F1F1 !important;
        }
        [data-testid="stMarkdownContainer"] td,
        .stMarkdown td {
            border-color: #2E2E2E !important;
            color: #F1F1F1 !important;
        }

        /* Blockquote */
        [data-testid="stMarkdownContainer"] blockquote,
        .stMarkdown blockquote {
            border-left-color: #3A3A3A !important;
            color: #C8C8C8 !important;
        }

        /* ---- The white bar at the bottom: Streamlit wraps st.chat_input
                in stBottom / stChatInputContainer which has a default white bg ---- */
        [data-testid="stBottom"],
        [data-testid="stBottomBlockContainer"],
        [data-testid="stChatInputContainer"],
        [data-testid="stChatInput"] { background: #0E0E0E !important; }

        /* ---- Sidebar ---- */
        section[data-testid="stSidebar"],
        section[data-testid="stSidebar"] > div,
        [data-testid="stSidebarContent"] { background: #131313 !important; border-right-color: #232323; }
        section[data-testid="stSidebar"] * { color: #F1F1F1; }

        /* ---- Selects & menus ---- */
        [data-baseweb="select"] > div { background: #1A1A1A !important; color: #F1F1F1 !important; }
        [data-baseweb="select"] svg { color: #A0A0A0 !important; }
        [data-baseweb="popover"] [role="listbox"],
        [data-baseweb="menu"] { background: #1A1A1A !important; color: #F1F1F1 !important; }
        [data-baseweb="menu"] li:hover { background: #232323 !important; }

        /* ---- Chat input pill ---- */
        [data-testid="stChatInput"] > div {
            background: #1A1A1A !important;
            border-color: #333333 !important;
        }
        [data-testid="stChatInput"] textarea { color: #F1F1F1 !important; }
        [data-testid="stChatInput"] textarea::placeholder { color: #6E6E6E !important; }

        /* ---- File uploader (inside popover) ---- */
        [data-testid="stFileUploaderDropzone"] {
            background: #161616 !important;
            border-color: #333333 !important;
            color: #F1F1F1 !important;
        }
        [data-testid="stFileUploaderDropzone"] * { color: #F1F1F1 !important; }

        /* ---- Buttons (main area) ---- */
        .stButton > button {
            background: #1A1A1A !important;
            color: #F1F1F1 !important;
            border-color: #333333 !important;
        }
        .stButton > button:hover {
            background: #232323 !important;
            border-color: #F1F1F1 !important;
        }
        .stButton > button[kind="primary"] {
            background: #1A1A1A !important;
            color: #F1F1F1 !important;
            border-color: #3A3A3A !important;
        }
        .stButton > button[kind="primary"]:hover {
            background: var(--c-accent) !important;
            border-color: var(--c-accent) !important;
            color: #FFFFFF !important;
        }

        /* ---- Sidebar buttons: history list + small actions ---- */
        section[data-testid="stSidebar"] .stButton > button,
        section[data-testid="stSidebar"] button[kind="secondary"],
        section[data-testid="stSidebar"] [data-testid^="baseButton"] {
            background: transparent !important;
            border: none !important;
            color: #F1F1F1 !important;
            box-shadow: none !important;
        }
        section[data-testid="stSidebar"] .stButton > button:hover,
        section[data-testid="stSidebar"] button[kind="secondary"]:hover,
        section[data-testid="stSidebar"] [data-testid^="baseButton"]:hover {
            background: #1F1F1F !important;
            color: #FFFFFF !important;
        }
        /* Sidebar's primary "+ Nueva conversación": dark tile with a hairline
           border so it reads as the primary action without screaming white. */
        section[data-testid="stSidebar"] .stButton > button[kind="primary"],
        section[data-testid="stSidebar"] [data-testid="baseButton-primary"] {
            background: #1A1A1A !important;
            color: #F1F1F1 !important;
            border: 1px solid #3A3A3A !important;
        }
        section[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover,
        section[data-testid="stSidebar"] [data-testid="baseButton-primary"]:hover {
            background: var(--c-accent) !important;
            color: #FFFFFF !important;
            border-color: var(--c-accent) !important;
        }

        /* ---- Popover trigger (📎) ---- */
        [data-testid="stPopover"] button {
            background: #1A1A1A !important;
            color: #F1F1F1 !important;
            border-color: #333333 !important;
        }
        [data-testid="stPopover"] button:hover {
            background: #232323 !important;
            border-color: #F1F1F1 !important;
        }

        /* ---- Misc ---- */
        hr { border-color: #232323 !important; }
        .crystal-bottom-bar { background: #0E0E0E !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Embedded-image marker — generated images are stored inline in the message
# content so they persist in history and re-render without a schema change.
# ---------------------------------------------------------------------------
IMAGE_MARKER_RE = re.compile(r"\[\[crystal-image:([A-Za-z0-9+/=\n]+)\]\]")


def render_message_content(content: str) -> None:
    """Render an assistant/user message, splitting out any inline images."""
    parts = IMAGE_MARKER_RE.split(content)
    for idx, part in enumerate(parts):
        if idx % 2 == 1:  # capture groups (base64 image payloads)
            try:
                st.image(base64.b64decode(part))
            except Exception:  # noqa: BLE001
                st.caption("⚠️ No se pudo mostrar una imagen generada.")
        elif part.strip():
            st.markdown(part)


def strip_image_markers(content: str) -> str:
    """Remove inline image payloads before sending history back to the model."""
    return IMAGE_MARKER_RE.sub("[imagen generada previamente]", content).strip()


# ---------------------------------------------------------------------------
# LLM client builders
# ---------------------------------------------------------------------------
def get_databricks_token() -> str:
    """Resolve a Databricks bearer token.

    Auth resolution order:
      1. ``DATABRICKS_TOKEN`` env var (used for local dev)
      2. Databricks SDK auth — picks up the service principal OAuth M2M
         credentials that Databricks Apps inject as
         ``DATABRICKS_HOST`` + ``DATABRICKS_CLIENT_ID`` + ``DATABRICKS_CLIENT_SECRET``
    """
    token = os.environ.get("DATABRICKS_TOKEN")
    if not token:
        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient()
        auth_headers = w.config.authenticate()
        token = auth_headers.get("Authorization", "").replace("Bearer ", "")
    return token


def get_llm_client() -> OpenAI:
    """OpenAI-compatible client for Chat Completions via the AI Gateway."""
    return OpenAI(api_key=get_databricks_token(), base_url=config.base_url)


def get_responses_client() -> OpenAI:
    """OpenAI-compatible client for the Responses API (image generation, etc.).

    Targets the AI Gateway's OpenAI-compatible path (``/ai-gateway/openai/v1``),
    which routes the Responses API. The mlflow path only exposes Chat Completions.
    """
    return OpenAI(api_key=get_databricks_token(), base_url=config.responses_base_url)


# ---------------------------------------------------------------------------
# Sidebar — brand, model picker, conversation list, theme toggle
# ---------------------------------------------------------------------------
endpoint_names = [ep["name"] for ep in config.endpoints]
endpoint_labels = {ep["name"]: ep.get("label", ep["name"]) for ep in config.endpoints}

with st.sidebar:
    st.image("static/logo.png", width=140)
    st.markdown(
        "<div class='brand-tagline'>Tejemos vida para nuestro planeta</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:0.6rem;'></div>", unsafe_allow_html=True)

    st.markdown("<div class='sidebar-label'>Modelo</div>", unsafe_allow_html=True)
    st.session_state.selected_endpoint = st.selectbox(
        "Modelo",
        options=endpoint_names,
        format_func=lambda n: endpoint_labels.get(n, n),
        index=endpoint_names.index(st.session_state.selected_endpoint)
        if st.session_state.selected_endpoint in endpoint_names
        else 0,
        label_visibility="collapsed",
    )

    if st.button("＋ Nueva conversación", use_container_width=True, type="primary"):
        st.session_state.active_conversation_id = None
        st.session_state.pending_attachments = []
        st.rerun()

    st.markdown("<hr/>", unsafe_allow_html=True)
    st.markdown("<div class='sidebar-label'>Conversaciones</div>", unsafe_allow_html=True)

    conversations = store.list_conversations(user.email)
    if conversations:
        for conv in conversations:
            cols = st.columns([6, 1])
            label = conv["title"] or "Sin título"
            if len(label) > 28:
                label = label[:28] + "…"
            with cols[0]:
                if st.button(
                    label,
                    key=f"open_{conv['id']}",
                    use_container_width=True,
                ):
                    st.session_state.active_conversation_id = conv["id"]
                    st.session_state.pending_attachments = []
                    st.rerun()
            with cols[1]:
                if st.button("✕", key=f"del_{conv['id']}", help="Eliminar"):
                    store.delete_conversation(conv["id"], user.email)
                    if st.session_state.active_conversation_id == conv["id"]:
                        st.session_state.active_conversation_id = None
                    st.rerun()
    else:
        st.caption("Aún no tienes conversaciones.")

    # Footer: user + theme toggle
    st.markdown("<hr/>", unsafe_allow_html=True)
    foot_cols = st.columns([5, 2])
    with foot_cols[0]:
        st.markdown(
            f"<div class='sidebar-footer'>Sesión · {user.display_name}</div>",
            unsafe_allow_html=True,
        )
    with foot_cols[1]:
        is_dark = st.session_state.theme == "dark"
        toggle_label = "☀️" if is_dark else "🌙"
        toggle_help = "Modo claro" if is_dark else "Modo oscuro"
        if st.button(toggle_label, key="theme_toggle", help=toggle_help):
            st.session_state.theme = "light" if is_dark else "dark"
            st.rerun()

# ---------------------------------------------------------------------------
# Main column — centered chat content, no top header (sidebar handles chrome)
# ---------------------------------------------------------------------------
st.markdown("<div class='crystal-chat-column'>", unsafe_allow_html=True)

# Ensure / create conversation
conversation_id = st.session_state.active_conversation_id
if conversation_id is None:
    conversation_id = store.create_conversation(
        user_email=user.email,
        endpoint=st.session_state.selected_endpoint,
    )
    st.session_state.active_conversation_id = conversation_id

# ---------------------------------------------------------------------------
# Chat history
# ---------------------------------------------------------------------------
messages = store.list_messages(conversation_id)
if not messages:
    st.markdown(
        "<div style='color:#8C8C8C; font-size:0.9rem; padding:0.5rem 0 1rem 0;'>"
        f"Hola {user.display_name.split()[0] if user.display_name else ''}, "
        "soy tu asistente Crystal. ¿En qué te ayudo hoy?"
        "</div>",
        unsafe_allow_html=True,
    )

for msg in messages:
    with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "static/logo.png"):
        if msg.get("attachments"):
            attach_html = "".join(
                f"<span class='crystal-attach-pill'>📎 {a}</span>" for a in msg["attachments"]
            )
            st.markdown(attach_html, unsafe_allow_html=True)
        render_message_content(msg["content"])

# ---------------------------------------------------------------------------
# Sticky bottom toolbar: paperclip popover + pending-files indicator
# (Sits just above the chat input thanks to position:sticky in styles.css.)
# ---------------------------------------------------------------------------
image_capable = config.supports_images(st.session_state.selected_endpoint)
if not image_capable:
    # The toggle is meaningless for non-image endpoints (e.g. Claude).
    st.session_state.image_mode = False

st.markdown("<div class='crystal-bottom-bar'>", unsafe_allow_html=True)
if image_capable:
    bcol_attach, bcol_img, bcol_status = st.columns([1, 2, 7])
else:
    bcol_attach, bcol_status = st.columns([1, 9])
    bcol_img = None
with bcol_attach:
    with st.popover("📎", help="Adjuntar archivo"):
        st.caption("Adjunta hasta 5 archivos (PDF, Word, Excel, texto o imagen).")
        uploaded = st.file_uploader(
            "Archivos",
            type=[
                "pdf", "docx", "doc",
                "xlsx", "xls",
                "txt", "md", "csv",
                "png", "jpg", "jpeg", "webp", "gif",
            ],
            accept_multiple_files=True,
            key=f"uploader_{conversation_id}",
            label_visibility="collapsed",
        )
        if uploaded:
            st.session_state.pending_attachments = uploaded
if bcol_img is not None:
    with bcol_img:
        st.session_state.image_mode = st.toggle(
            "🎨 Imagen",
            value=st.session_state.image_mode,
            help="Genera una imagen a partir de tu mensaje (modelos OpenAI).",
        )
with bcol_status:
    if st.session_state.pending_attachments:
        names = ", ".join(f.name for f in st.session_state.pending_attachments)
        st.markdown(
            f"<div style='color:#6E6E6E; font-size:0.82rem; padding-top:0.55rem;'>"
            f"Listo para enviar: <b>{names}</b></div>",
            unsafe_allow_html=True,
        )
    elif st.session_state.image_mode:
        st.markdown(
            "<div style='color:#6E6E6E; font-size:0.82rem; padding-top:0.55rem;'>"
            "Modo imagen activo — describe la imagen que quieres.</div>",
            unsafe_allow_html=True,
        )
st.markdown("</div>", unsafe_allow_html=True)

prompt = st.chat_input("Escribe tu mensaje…")

# Close the centered column wrapper
st.markdown("</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Handle a new turn
# ---------------------------------------------------------------------------
if prompt:
    attachments = st.session_state.pending_attachments or []
    attachment_names = [a.name for a in attachments]

    # Build user message content: text + extracted file content
    extracted_parts: list[str] = []
    image_data_uris: list[str] = []
    for f in attachments:
        result = extract_file_content(f)
        if result["kind"] == "text":
            extracted_parts.append(
                f"\n\n--- Archivo adjunto: {f.name} ---\n{result['text']}\n--- Fin del archivo ---"
            )
        elif result["kind"] == "image":
            image_data_uris.append(f"data:{result['mime']};base64,{result['b64']}")

    # Chat Completions vision payload shape (image_url object).
    image_parts = [
        {"type": "image_url", "image_url": {"url": uri}} for uri in image_data_uris
    ]

    display_text = prompt
    api_text = prompt + "".join(extracted_parts)

    # Persist user message
    store.add_message(
        conversation_id=conversation_id,
        role="user",
        content=display_text,
        attachments=attachment_names,
    )

    # Auto-title the conversation on first user turn
    if not messages:
        store.set_title(conversation_id, prompt[:60])

    # Render user message
    with st.chat_message("user", avatar="🧑"):
        if attachment_names:
            attach_html = "".join(
                f"<span class='crystal-attach-pill'>📎 {n}</span>" for n in attachment_names
            )
            st.markdown(attach_html, unsafe_allow_html=True)
        st.markdown(display_text)

    endpoint = st.session_state.selected_endpoint
    last_user_id = store.last_message_id(conversation_id)
    image_model = config.image_model_for(endpoint)
    use_responses = bool(image_model) and st.session_state.image_mode

    with st.chat_message("assistant", avatar="static/logo.png"):
        placeholder = st.empty()
        # `stored_content` is what we persist (may embed image markers);
        # the live render happens inline below.
        stored_content = ""
        try:
            if use_responses:
                # ---- Responses API path: streaming image generation ----
                # Through the AI Gateway OpenAI-compatible path, targeting the
                # configured OpenAI serving endpoint (image_model). Streaming with
                # partial_images sidesteps the synchronous ~640 KB cap, renders the
                # image progressively, and surfaces real upstream errors.
                responses_input = []
                for m in store.list_messages(conversation_id):
                    if m["role"] == "user" and m["id"] == last_user_id:
                        content_list = [{"type": "input_text", "text": api_text}]
                        for uri in image_data_uris:
                            content_list.append({"type": "input_image", "image_url": uri})
                        responses_input.append({"role": "user", "content": content_list})
                    else:
                        responses_input.append(
                            {"role": m["role"], "content": strip_image_markers(m["content"])}
                        )

                client = get_responses_client()
                img_placeholder = st.empty()
                text_out = ""
                final_image_b64 = None
                stream_error = None
                # Image generation also spends output tokens on reasoning, so
                # give it a generous floor to avoid truncating before the image.
                with st.spinner("Generando imagen…"):
                    stream = client.responses.create(
                        model=image_model,
                        input=responses_input,
                        max_output_tokens=max(config.max_tokens, 4096),
                        tools=[config.image_tool()],
                        tool_choice="auto",
                        stream=True,
                    )
                    for event in stream:
                        etype = getattr(event, "type", "") or ""
                        if etype == "response.output_text.delta":
                            text_out += getattr(event, "delta", "") or ""
                            if text_out:
                                placeholder.markdown(text_out + "▌")
                        elif etype == "response.image_generation_call.partial_image":
                            b64 = getattr(event, "partial_image_b64", None)
                            if b64:
                                final_image_b64 = b64  # latest partial = best so far
                                try:
                                    img_placeholder.image(base64.b64decode(b64))
                                except Exception:  # noqa: BLE001
                                    pass
                        elif etype == "response.completed":
                            # Prefer the final, fully-rendered image if present.
                            resp_obj = getattr(event, "response", None)
                            for item in getattr(resp_obj, "output", None) or []:
                                if getattr(item, "type", None) == "image_generation_call":
                                    result = getattr(item, "result", None)
                                    if result:
                                        final_image_b64 = result
                        elif etype in ("error", "response.failed"):
                            # Error shape varies: "error" events nest .error.message
                            # (gateway) or expose .message (SDK); "response.failed"
                            # nests it under .response.error.message.
                            err = getattr(event, "error", None)
                            resp_err = getattr(getattr(event, "response", None), "error", None)
                            stream_error = (
                                getattr(err, "message", None)
                                or getattr(resp_err, "message", None)
                                or getattr(event, "message", None)
                                or str(err or resp_err or etype)
                            )

                if stream_error:
                    raise RuntimeError(stream_error)

                if text_out:
                    placeholder.markdown(text_out)
                else:
                    placeholder.empty()
                if final_image_b64:
                    img_placeholder.image(base64.b64decode(final_image_b64))

                stored_content = text_out + (
                    f"\n\n[[crystal-image:{final_image_b64}]]" if final_image_b64 else ""
                )
                if not stored_content.strip():
                    stored_content = "_(El modelo no devolvió una imagen.)_"
                    placeholder.markdown(stored_content)
            else:
                # ---- Chat Completions path (streaming) ----
                api_messages = []
                for m in store.list_messages(conversation_id):
                    if m["role"] == "user" and m["id"] == last_user_id:
                        if image_parts:
                            api_messages.append(
                                {
                                    "role": "user",
                                    "content": [{"type": "text", "text": api_text}, *image_parts],
                                }
                            )
                        else:
                            api_messages.append({"role": "user", "content": api_text})
                    else:
                        api_messages.append({"role": m["role"], "content": m["content"]})

                client = get_llm_client()
                full_response = ""
                stream = client.chat.completions.create(
                    model=endpoint,
                    messages=api_messages,
                    max_tokens=config.max_tokens,
                    stream=True,
                )
                for chunk in stream:
                    if not getattr(chunk, "choices", None):
                        continue
                    delta = chunk.choices[0].delta.content
                    if not delta:
                        continue
                    if isinstance(delta, list):
                        delta = "".join(
                            part.get("text", "")
                            for part in delta
                            if isinstance(part, dict) and part.get("type") == "text"
                        )
                    elif not isinstance(delta, str):
                        delta = str(delta)
                    if not delta:
                        continue
                    full_response += delta
                    placeholder.markdown(full_response + "▌")
                placeholder.markdown(full_response)
                stored_content = full_response
        except Exception as exc:  # noqa: BLE001
            if use_responses:
                # Image generation can fail upstream (the synchronous path wraps
                # the provider error as a generic 400). Show a friendly message
                # and keep the technical detail tucked away for debugging.
                stored_content = (
                    "⚠️ No se pudo generar la imagen en este momento. "
                    "El servicio de generación de imágenes puede estar temporalmente "
                    "no disponible — intenta de nuevo en unos minutos."
                )
                placeholder.markdown(stored_content)
                with st.expander("Detalle técnico"):
                    st.code(str(exc))
            else:
                stored_content = (
                    f"⚠️ No se pudo obtener respuesta del endpoint "
                    f"`{endpoint}`.\n\n```\n{exc}\n```"
                )
                placeholder.markdown(stored_content)

    # Persist assistant message
    store.add_message(
        conversation_id=conversation_id,
        role="assistant",
        content=stored_content,
        attachments=[],
    )

    # Clear pending attachments
    st.session_state.pending_attachments = []
    st.rerun()
