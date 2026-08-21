#!/usr/bin/env bash

set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
errors=0

fail() {
  echo "context-check: $*" >&2
  errors=$((errors + 1))
}

check_budget() {
  local label=$1
  local limit=$2
  shift 2
  local total=0
  local path

  for path in "$@"; do
    if [[ ! -f "$path" ]]; then
      fail "$label: отсутствует ${path#"$repo_root"/}"
      return
    fi
    total=$((total + $(wc -c < "$path")))
  done

  if ((total > limit)); then
    fail "$label: $total байт, лимит $limit"
  fi
}

root_agents="$repo_root/AGENTS.md"
check_budget "root AGENTS" 4096 "$root_agents"

while IFS= read -r service_dir; do
  service_agents="$service_dir/AGENTS.md"
  if [[ ! -f "$service_agents" ]]; then
    fail "сервис ${service_dir#"$repo_root"/} не содержит AGENTS.md"
    continue
  fi
  check_budget "цепочка ${service_dir#"$repo_root"/}" 12288 \
    "$root_agents" "$service_agents"
done < <(find "$repo_root/apps" -mindepth 1 -maxdepth 1 -type d | sort)

backend_agents="$repo_root/apps/backend/AGENTS.md"
modules_root="$repo_root/apps/backend/src/app/modules"
while IFS= read -r module_file; do
  module_dir=$(dirname "$module_file")
  module_agents="$module_dir/AGENTS.md"
  if [[ ! -f "$module_agents" ]]; then
    fail "модуль ${module_dir#"$modules_root"/} не содержит AGENTS.md"
    continue
  fi
  check_budget "цепочка модуля ${module_dir#"$modules_root"/}" 20480 \
    "$root_agents" "$backend_agents" "$module_agents"
done < <(find "$modules_root" -mindepth 2 -maxdepth 2 -name module.py -type f | sort)

check_budget "цепочка infra" 12288 "$root_agents" "$repo_root/infra/AGENTS.md"

while IFS= read -r skill_file; do
  skill_dir=$(dirname "$skill_file")
  folder_name=$(basename "$skill_dir")
  size=$(wc -c < "$skill_file")

  if ((size > 12288)); then
    fail "${skill_file#"$repo_root"/}: $size байт, лимит SKILL.md 12288"
  fi

  skill_name=$(awk -F ': *' '/^name:/ {print $2; exit}' "$skill_file" | tr -d "\"'")
  if [[ -z "$skill_name" ]]; then
    fail "${skill_file#"$repo_root"/}: нет name во frontmatter"
  elif [[ "$skill_name" != "$folder_name" ]]; then
    fail "${skill_file#"$repo_root"/}: name '$skill_name' не совпадает с каталогом '$folder_name'"
  fi

  if ! sed -n '1,/^---$/p' "$skill_file" | grep -q '^description:'; then
    fail "${skill_file#"$repo_root"/}: нет description во frontmatter"
  fi

  while IFS= read -r reference; do
    [[ -z "$reference" ]] && continue
    if [[ ! -f "$skill_dir/$reference" ]]; then
      fail "${skill_file#"$repo_root"/}: отсутствует $reference"
    fi
  done < <(
    grep -oE '\]\((references/[^)#]+\.md)\)' "$skill_file" \
      | sed -E 's/^\]\((.*)\)$/\1/' \
      | sort -u || true
  )
done < <(
  find "$repo_root" \
    -path '*/.venv' -prune -o \
    -path '*/.agents/skills/*/SKILL.md' -type f -print \
    | sort
)

if (cd "$repo_root" && rg -n --hidden --glob '!.git/**' \
  --glob '!scripts/check-agent-context.sh' \
  '\.agents/rules/backend|\.claude/CLAUDE\.md' . >/dev/null); then
  fail "найдены устаревшие пути .agents/rules/backend или .claude/CLAUDE.md"
fi

if ((errors > 0)); then
  exit 1
fi

echo "context-check: OK"
