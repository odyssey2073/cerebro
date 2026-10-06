#!/bin/bash
# CEREBRO - Multi-project RAG brain manager
# Usage: cerebro

_CEREBRO_HOME="/c/software/cerebro"
_CEREBRO_PY="$_CEREBRO_HOME/.venv/Scripts/python.exe"

cerebro() {
  local choice
  echo ""
  echo "=============================="
  echo "  CEREBRO - RAG Brain Manager"
  echo "=============================="
  echo "  [1] Nuovo progetto"
  echo "  [2] Re-index"
  echo "  [3] Status"
  echo "  [4] Rimuovi progetto"
  echo "  [q] Esci"
  echo ""
  read -rp "Scelta: " choice
  case "$choice" in
    1) _cerebro_new_project ;;
    2) _cerebro_reindex ;;
    3) _cerebro_status ;;
    4) _cerebro_remove ;;
    q|Q) return 0 ;;
    *) echo "Scelta non valida."; cerebro ;;
  esac
}

_cerebro_new_project() {
  local name slug root docs tool gf graphify_flag=""

  read -rp "Nome progetto: " name
  slug=$(echo "$name" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/_/g')
  echo "  slug: $slug"

  read -rp "Root path del progetto: " root
  if [[ ! -d "$root" ]]; then
    echo "ERRORE: path '$root' non trovato."; return 1
  fi

  read -rp "Docs path [default: $root/docs]: " docs
  docs="${docs:-$root/docs}"

  echo "Agent tools: both / claude / copilot"
  read -rp "Tool [default: both]: " tool
  tool="${tool:-both}"

  read -rp "Graphify knowledge graph? [y/N]: " gf
  [[ "$gf" =~ ^[Yy]$ ]] && graphify_flag="--graphify"

  echo ""
  cd "$_CEREBRO_HOME" || return 1

  echo ">>> Registrazione..."
  "$_CEREBRO_PY" scripts/register_project.py add "$slug" --docs "$docs" --root "$root" || return 1

  echo ">>> Istruzioni..."
  "$_CEREBRO_PY" scripts/register_project.py instructions "$slug" --tool "$tool" $graphify_flag || return 1

  echo ">>> Ingest docs..."
  "$_CEREBRO_PY" scripts/ingest_docs.py --project "$slug" || return 1

  echo ""
  echo ">>> Verifica..."
  "$_CEREBRO_PY" scripts/query_qdrant.py --project "$slug" count
  "$_CEREBRO_PY" scripts/query_qdrant.py --project "$slug" search "test" --limit 3
  echo "Progetto '$slug' registrato."
}

_cerebro_reindex() {
  local name
  echo "Progetti disponibili:"; _cerebro_list
  read -rp "Nome progetto: " name
  cd "$_CEREBRO_HOME" || return 1
  "$_CEREBRO_PY" scripts/ingest_docs.py --project "$name"
}

_cerebro_status() {
  cd "$_CEREBRO_HOME" || return 1
  "$_CEREBRO_PY" scripts/register_project.py list
}

_cerebro_remove() {
  local name c1 c2
  echo "Progetti disponibili:"; _cerebro_list
  read -rp "Nome progetto da rimuovere: " name
  read -rp "Conferma '$name'? [y/N]: " c1
  [[ ! "$c1" =~ ^[Yy]$ ]] && echo "Annullato." && return 0
  read -rp "DOPPIA CONFERMA - rimuovere '$name'? [y/N]: " c2
  [[ ! "$c2" =~ ^[Yy]$ ]] && echo "Annullato." && return 0
  cd "$_CEREBRO_HOME" || return 1
  "$_CEREBRO_PY" scripts/register_project.py remove "$name"
  echo "Nota: la collection Qdrant NON e' stata cancellata."
}

_cerebro_list() {
  cd "$_CEREBRO_HOME" || return 1
  "$_CEREBRO_PY" scripts/register_project.py list 2>/dev/null || echo "(nessuno)"
}
