#!/usr/bin/env bash
#
# Despliega la Crystal AI Assistant en su workspace y le otorga al service
# principal los permisos necesarios sobre los endpoints del AI Gateway.
#
# Uso:
#   ./scripts/deploy.sh \
#       --host  https://<su-workspace>.azuredatabricks.net \
#       --user  usted@crystal.com.co \
#       --app   crystal-ai-assistant \
#       --endpoints gpt,claude
#
# Requisitos:
#   - databricks CLI v0.230+ autenticado con un profile (DEFAULT por defecto)
#   - jq y curl en el PATH

set -euo pipefail

APP_NAME="crystal-ai-assistant"
PROFILE="DEFAULT"
ENDPOINTS="gpt,claude"
HOST=""
USER_EMAIL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)       HOST="$2"; shift 2 ;;
    --user)       USER_EMAIL="$2"; shift 2 ;;
    --app)        APP_NAME="$2"; shift 2 ;;
    --endpoints)  ENDPOINTS="$2"; shift 2 ;;
    --profile)    PROFILE="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,15p' "$0"; exit 0 ;;
    *)
      echo "Opción desconocida: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$HOST" || -z "$USER_EMAIL" ]]; then
  echo "Faltan --host o --user. Use --help para ver el uso." >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE_PATH="/Workspace/Users/${USER_EMAIL}/${APP_NAME}"

echo "==> Sincronizando código a ${WORKSPACE_PATH}"
# Excluir .git temporalmente para no subir basura
if [[ -d "${ROOT}/.git" ]]; then
  mv "${ROOT}/.git" "${ROOT}/.git.bak"
  trap 'mv "${ROOT}/.git.bak" "${ROOT}/.git" 2>/dev/null || true' EXIT
fi

databricks workspace import-dir "${ROOT}" "${WORKSPACE_PATH}" \
  --overwrite --profile "${PROFILE}"

echo ""
echo "==> Creando la app (si no existe)"
if ! databricks apps get "${APP_NAME}" --profile "${PROFILE}" >/dev/null 2>&1; then
  databricks apps create "${APP_NAME}" \
    --description "Crystal AI Assistant — frontend del AI Gateway" \
    --profile "${PROFILE}" >/dev/null
  echo "   App creada: ${APP_NAME}"
else
  echo "   App ya existía, se reutiliza."
fi

echo ""
echo "==> Obteniendo identidad del service principal"
SP=$(databricks apps get "${APP_NAME}" --profile "${PROFILE}" \
     | jq -r .service_principal_client_id)
APP_URL=$(databricks apps get "${APP_NAME}" --profile "${PROFILE}" | jq -r .url)
echo "   SP client_id: ${SP}"
echo "   App URL:      ${APP_URL}"

echo ""
echo "==> Otorgando CAN_QUERY al SP sobre los endpoints del AI Gateway"
TOKEN=$(databricks auth token --profile "${PROFILE}" | jq -r .access_token)
IFS=',' read -r -a EP_ARRAY <<< "${ENDPOINTS}"
for ep in "${EP_ARRAY[@]}"; do
  ep_trim="$(echo "${ep}" | xargs)"
  echo "   - ${ep_trim}"
  curl -sS -X PATCH "${HOST}/api/2.0/permissions/ai-gateway-endpoints/${ep_trim}" \
       -H "Authorization: Bearer ${TOKEN}" \
       -H "Content-Type: application/json" \
       -d "{\"access_control_list\":[{\"service_principal_name\":\"${SP}\",\"permission_level\":\"CAN_QUERY\"}]}" \
       -o /dev/null -w "     HTTP %{http_code}\n"
done

echo ""
echo "==> Desplegando código"
databricks apps deploy "${APP_NAME}" \
  --source-code-path "${WORKSPACE_PATH}" \
  --profile "${PROFILE}"

echo ""
echo "==================================================================="
echo " Listo. Abra la app en:"
echo "   ${APP_URL}"
echo "==================================================================="
