"""
Crystal — AI Gateway Frontend (Databricks App)

A branded Streamlit chat app that fronts Databricks AI Gateway endpoints.
- Endpoint picker (configured via env vars)
- File attachments (PDF / Word / text / image) sent to the model
- Per-user chat history (multiple conversations per user, persisted to SQLite)
- Databricks-native authentication (reads X-Forwarded-Email header)
"""

from __future__ import annotations

import base64
import os
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

# Load CSS
css_path = Path(__file__).parent / "static" / "styles.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

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


# ---------------------------------------------------------------------------
# LLM client builder
# ---------------------------------------------------------------------------
def get_llm_client() -> OpenAI:
    """Build an OpenAI-compatible client pointed at the Databricks AI Gateway.

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
        # `authenticate()` returns a {"Authorization": "Bearer …"} header pair
        auth_headers = w.config.authenticate()
        token = auth_headers.get("Authorization", "").replace("Bearer ", "")
    return OpenAI(api_key=token, base_url=config.base_url)


# ---------------------------------------------------------------------------
# Sidebar — branding, endpoint picker, conversation list
# ---------------------------------------------------------------------------
with st.sidebar:
    st.image("static/logo.png", width=160)
    st.markdown(
        "<div class='brand-tagline'>Tejemos vida para nuestro planeta</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    st.markdown("### Modelo")
    endpoint_names = [ep["name"] for ep in config.endpoints]
    endpoint_labels = {ep["name"]: ep.get("label", ep["name"]) for ep in config.endpoints}
    st.session_state.selected_endpoint = st.selectbox(
        "Selecciona el modelo",
        options=endpoint_names,
        format_func=lambda n: endpoint_labels.get(n, n),
        index=endpoint_names.index(st.session_state.selected_endpoint)
        if st.session_state.selected_endpoint in endpoint_names
        else 0,
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown("### Conversaciones")

    if st.button("Nueva conversación", use_container_width=True, type="primary"):
        st.session_state.active_conversation_id = None
        st.session_state.pending_attachments = []
        st.rerun()

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
        st.caption("Aún no tienes conversaciones. Inicia una desde el panel principal.")

    st.markdown("---")
    st.caption(f"Sesión: **{user.display_name}**")

# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------
st.markdown(
    "<div class='app-header'>"
    "<h1>Crystal AI Assistant</h1>"
    "<p class='subtitle'>Consulta los modelos corporativos a través del AI Gateway de Databricks.</p>"
    "</div>",
    unsafe_allow_html=True,
)

# Ensure / create conversation
conversation_id = st.session_state.active_conversation_id
if conversation_id is None:
    conversation_id = store.create_conversation(
        user_email=user.email,
        endpoint=st.session_state.selected_endpoint,
    )
    st.session_state.active_conversation_id = conversation_id

# Render history
messages = store.list_messages(conversation_id)
for msg in messages:
    with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "static/logo.png"):
        if msg.get("attachments"):
            for att in msg["attachments"]:
                st.caption(f"📎 {att}")
        st.markdown(msg["content"])

# ---------------------------------------------------------------------------
# File uploader (above the input)
# ---------------------------------------------------------------------------
with st.expander("📎 Adjuntar archivo (PDF, Word, texto, imagen)", expanded=False):
    uploaded = st.file_uploader(
        "Sube hasta 5 archivos para el modelo",
        type=["pdf", "docx", "doc", "txt", "md", "csv", "png", "jpg", "jpeg", "webp", "gif"],
        accept_multiple_files=True,
        key=f"uploader_{conversation_id}",
        label_visibility="collapsed",
    )
    if uploaded:
        st.session_state.pending_attachments = uploaded
        names = ", ".join(f.name for f in uploaded)
        st.success(f"Listo para enviar: {names}")

# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------
prompt = st.chat_input("Escribe tu mensaje…")

if prompt:
    attachments = st.session_state.pending_attachments or []
    attachment_names = [a.name for a in attachments]

    # Build user message content: text + extracted file content
    extracted_parts: list[str] = []
    image_parts: list[dict] = []
    for f in attachments:
        result = extract_file_content(f)
        if result["kind"] == "text":
            extracted_parts.append(
                f"\n\n--- Archivo adjunto: {f.name} ---\n{result['text']}\n--- Fin del archivo ---"
            )
        elif result["kind"] == "image":
            image_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{result['mime']};base64,{result['b64']}"},
                }
            )

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
        for name in attachment_names:
            st.caption(f"📎 {name}")
        st.markdown(display_text)

    # Build OpenAI-format message list from history
    api_messages = []
    for m in store.list_messages(conversation_id):
        if m["role"] == "user" and m["id"] == store.last_message_id(conversation_id):
            # Replace last user message with extracted version + image parts
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

    # Call the model
    with st.chat_message("assistant", avatar="static/logo.png"):
        placeholder = st.empty()
        try:
            client = get_llm_client()
            full_response = ""
            stream = client.chat.completions.create(
                model=st.session_state.selected_endpoint,
                messages=api_messages,
                max_tokens=config.max_tokens,
                stream=True,
            )
            for chunk in stream:
                # Some providers emit chunks with no choices (e.g. final
                # usage-only chunk on OpenAI-compatible streams).
                if not getattr(chunk, "choices", None):
                    continue
                delta = chunk.choices[0].delta.content or ""
                if not delta:
                    continue
                full_response += delta
                placeholder.markdown(full_response + "▌")
            placeholder.markdown(full_response)
        except Exception as exc:  # noqa: BLE001
            full_response = (
                f"⚠️ No se pudo obtener respuesta del endpoint "
                f"`{st.session_state.selected_endpoint}`.\n\n```\n{exc}\n```"
            )
            placeholder.markdown(full_response)

    # Persist assistant message
    store.add_message(
        conversation_id=conversation_id,
        role="assistant",
        content=full_response,
        attachments=[],
    )

    # Clear pending attachments
    st.session_state.pending_attachments = []
    st.rerun()
