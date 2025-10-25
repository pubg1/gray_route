#!/usr/bin/env bash
# 将数据导入 OpenSearch 的 cases 索引，并开启 kNN 支持

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd "${SCRIPT_DIR}/.." && pwd)

usage() {
  cat <<'USAGE'
用法: import_cases_knn.sh [数据文件路径]

不指定参数时，脚本会尝试使用 $OPENSEARCH_DATA_FILE 或 ../data/servicingcase_last.json。
可以通过环境变量自定义 OpenSearch 连接信息：
  OPENSEARCH_HOST, OPENSEARCH_PORT, OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD,
  OPENSEARCH_SSL, OPENSEARCH_VERIFY_CERTS, OPENSEARCH_TIMEOUT,
  OPENSEARCH_INDEX, OPENSEARCH_BATCH_SIZE,
  OPENSEARCH_VECTOR_FIELD, OPENSEARCH_VECTOR_DIM,
  EMBEDDING_MODEL, MODEL_CACHE_DIR, PYTHON_BIN。
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

DATA_FILE="${1:-${OPENSEARCH_DATA_FILE:-${ROOT_DIR}/data/servicingcase_last.json}}"

if [[ ! -f "${DATA_FILE}" ]]; then
  echo "[错误] 数据文件不存在: ${DATA_FILE}" >&2
  usage
  exit 1
fi

PYTHON_BIN=${PYTHON_BIN:-python3}

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "[错误] 未找到 Python 解释器: ${PYTHON_BIN}" >&2
  exit 1
fi

read_config_value() {
  local field="$1"
  "${PYTHON_BIN}" - "$field" <<PY
import sys
import pathlib

field = sys.argv[1]
script_dir = pathlib.Path(r"${SCRIPT_DIR}")
sys.path.insert(0, str(script_dir))

try:
    from opensearch_config import OPENSEARCH_CONFIG
except ModuleNotFoundError:
    OPENSEARCH_CONFIG = {}

value = OPENSEARCH_CONFIG.get(field)
if isinstance(value, bool):
    print("true" if value else "false", end="")
elif value is None:
    print("", end="")
else:
    print(value, end="")
PY
}

HOST_DEFAULT=$(read_config_value host)
PORT_DEFAULT=$(read_config_value port)
USERNAME_DEFAULT=$(read_config_value username)
PASSWORD_DEFAULT=$(read_config_value password)
SSL_DEFAULT=$(read_config_value use_ssl)
VERIFY_DEFAULT=$(read_config_value verify_certs)
TIMEOUT_DEFAULT=$(read_config_value timeout)

HOST=${OPENSEARCH_HOST:-${HOST_DEFAULT:-localhost}}
PORT=${OPENSEARCH_PORT:-${PORT_DEFAULT:-9200}}
INDEX=${OPENSEARCH_INDEX:-cases}
USERNAME=${OPENSEARCH_USERNAME:-${USERNAME_DEFAULT}}
PASSWORD=${OPENSEARCH_PASSWORD:-${PASSWORD_DEFAULT}}
SSL_FLAG=${OPENSEARCH_SSL:-${SSL_DEFAULT:-false}}
VERIFY_CERTS=${OPENSEARCH_VERIFY_CERTS:-${VERIFY_DEFAULT:-false}}
TIMEOUT=${OPENSEARCH_TIMEOUT:-${TIMEOUT_DEFAULT:-30}}
BATCH_SIZE=${OPENSEARCH_BATCH_SIZE:-200}
VECTOR_FIELD=${OPENSEARCH_VECTOR_FIELD:-text_vector}
VECTOR_DIM=${OPENSEARCH_VECTOR_DIM:-512}
EMBED_MODEL=${EMBEDDING_MODEL:-}
MODEL_CACHE=${MODEL_CACHE_DIR:-}

TEMP_JSON=""

cleanup_temp() {
  if [[ -n "${TEMP_JSON}" && -f "${TEMP_JSON}" ]]; then
    rm -f "${TEMP_JSON}"
  fi
}

shopt -s nocasematch
if [[ "${DATA_FILE}" == *.zip ]]; then
  TEMP_JSON=$(mktemp "${TMPDIR:-/tmp}/cases_import_XXXXXX.jsonl")
  trap cleanup_temp EXIT
  TABLE_ARGS=()
  if [[ -n "${SQL_TABLES:-}" ]]; then
    TABLE_ARGS=(--tables ${SQL_TABLES})
  fi
  echo "[信息] 检测到 ZIP 数据包，正在转换为 JSONL: ${DATA_FILE}" >&2
  "${PYTHON_BIN}" "${SCRIPT_DIR}/convert_sql_to_jsonl.py" \
    --zip "${DATA_FILE}" \
    --output "${TEMP_JSON}" \
    --index "${INDEX}" \
    "${TABLE_ARGS[@]}"
  DATA_FILE="${TEMP_JSON}"
fi
shopt -u nocasematch

CMD=("${PYTHON_BIN}" "${SCRIPT_DIR}/import_to_opensearch.py"
  "--file" "${DATA_FILE}"
  "--index" "${INDEX}"
  "--host" "${HOST}"
  "--port" "${PORT}"
  "--timeout" "${TIMEOUT}"
  "--batch-size" "${BATCH_SIZE}"
  "--clone-mapping-from" "automotive_cases"
  "--enable-vector"
  "--vector-field" "${VECTOR_FIELD}"
  "--vector-dim" "${VECTOR_DIM}")

if [[ -n "${USERNAME}" && -n "${PASSWORD}" ]]; then
  CMD+=("--username" "${USERNAME}" "--password" "${PASSWORD}")
fi

case "${SSL_FLAG}" in
  true|TRUE|True|1|yes|YES)
    CMD+=("--ssl")
    ;;
  *)
    ;;
esac

case "${VERIFY_CERTS}" in
  true|TRUE|True|1|yes|YES)
    CMD+=("--verify-certs")
    ;;
  *)
    ;;
esac

if [[ -n "${EMBED_MODEL}" ]]; then
  CMD+=("--embedding-model" "${EMBED_MODEL}")
fi

if [[ -n "${MODEL_CACHE}" ]]; then
  CMD+=("--model-cache" "${MODEL_CACHE}")
fi

exec "${CMD[@]}"
