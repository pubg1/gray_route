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
  OPENSEARCH_SSL, OPENSEARCH_INDEX, OPENSEARCH_BATCH_SIZE,
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

HOST=${OPENSEARCH_HOST:-localhost}
PORT=${OPENSEARCH_PORT:-9200}
INDEX=${OPENSEARCH_INDEX:-cases}
USERNAME=${OPENSEARCH_USERNAME:-}
PASSWORD=${OPENSEARCH_PASSWORD:-}
SSL_FLAG=${OPENSEARCH_SSL:-false}
BATCH_SIZE=${OPENSEARCH_BATCH_SIZE:-200}
VECTOR_FIELD=${OPENSEARCH_VECTOR_FIELD:-text_vector}
VECTOR_DIM=${OPENSEARCH_VECTOR_DIM:-512}
EMBED_MODEL=${EMBEDDING_MODEL:-}
MODEL_CACHE=${MODEL_CACHE_DIR:-}
PYTHON_BIN=${PYTHON_BIN:-python3}

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "[错误] 未找到 Python 解释器: ${PYTHON_BIN}" >&2
  exit 1
fi

CMD=("${PYTHON_BIN}" "${SCRIPT_DIR}/import_to_opensearch.py"
  "--file" "${DATA_FILE}"
  "--index" "${INDEX}"
  "--host" "${HOST}"
  "--port" "${PORT}"
  "--batch-size" "${BATCH_SIZE}"
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

if [[ -n "${EMBED_MODEL}" ]]; then
  CMD+=("--embedding-model" "${EMBED_MODEL}")
fi

if [[ -n "${MODEL_CACHE}" ]]; then
  CMD+=("--model-cache" "${MODEL_CACHE}")
fi

exec "${CMD[@]}"
