#!/usr/bin/env bash

set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
errors=0
report=false
case "${1:-}" in
  --report) report=true ;;
  "") ;;
  *) echo "Использование: $0 [--report]" >&2; exit 2 ;;
esac

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
  local seen="|"

  for path in "$@"; do
    [[ "$seen" == *"|$path|"* ]] && continue
    seen+="$path|"
    if [[ ! -f "$path" ]]; then
      fail "$label: отсутствует ${path#"$repo_root"/}"
      return
    fi
    total=$((total + $(wc -c < "$path")))
  done

  if "$report"; then
    printf '%7d / %7d  %s\n' "$total" "$limit" "$label"
  fi
  if ((total > limit)); then
    fail "$label: $total байт, лимит $limit"
  fi
}

root_agents="$repo_root/AGENTS.md"
check_budget "root AGENTS" 2304 "$root_agents"

while IFS= read -r service_dir; do
  service_agents="$service_dir/AGENTS.md"
  if [[ ! -f "$service_agents" ]]; then
    fail "сервис ${service_dir#"$repo_root"/} не содержит AGENTS.md"
    continue
  fi
  check_budget "цепочка ${service_dir#"$repo_root"/}" 7168 \
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
  check_budget "цепочка модуля ${module_dir#"$modules_root"/}" 8192 \
    "$root_agents" "$backend_agents" "$module_agents"
done < <(find "$modules_root" -mindepth 2 -maxdepth 2 -name module.py -type f | sort)

check_budget "цепочка infra" 7168 "$root_agents" "$repo_root/infra/AGENTS.md"

# Сценарии — явные наборы чтения; не попытка угадать ссылки из естественного языка.
while IFS=$'\t' read -r label limit paths; do
  [[ -z "$label" || "$label" == \#* ]] && continue
  if [[ ! "$limit" =~ ^[1-9][0-9]*$ || -z "$paths" ]]; then
    fail "некорректный сценарий: $label"
    continue
  fi
  read -r -a scenario_paths <<< "$paths"
  for i in "${!scenario_paths[@]}"; do
    scenario_paths[$i]="$repo_root/${scenario_paths[$i]}"
  done
  check_budget "сценарий $label" "$limit" "${scenario_paths[@]}"
done < "$repo_root/scripts/agent-context-scenarios.tsv"

while IFS= read -r skill_file; do
  skill_dir=$(dirname "$skill_file")
  folder_name=$(basename "$skill_dir")
  check_budget "${skill_file#"$repo_root"/}" 6144 "$skill_file"

  if ! awk 'NR == 1 {if ($0 != "---") exit 1; next} /^---$/ {closed=1; exit} END {if (!closed) exit 1}' "$skill_file"; then
    fail "${skill_file#"$repo_root"/}: отсутствует закрытый YAML frontmatter"
  fi
  frontmatter=$(awk 'NR == 1 {if ($0 != "---") exit; next} /^---$/ {exit} {print}' "$skill_file")
  skill_name=$(printf '%s\n' "$frontmatter" | awk -F ': *' '/^name:/ {print $2; exit}' | tr -d "\"'")
  if [[ -z "$skill_name" ]]; then
    fail "${skill_file#"$repo_root"/}: нет name во frontmatter"
  elif [[ "$skill_name" != "$folder_name" ]]; then
    fail "${skill_file#"$repo_root"/}: name '$skill_name' не совпадает с каталогом '$folder_name'"
  fi

  description=$(printf '%s\n' "$frontmatter" | sed -n 's/^description: *//p')
  if [[ -z "$description" ]]; then
    fail "${skill_file#"$repo_root"/}: нет description во frontmatter"
  fi
  if (($(printf '%s' "$description" | wc -c) > 512)); then
    fail "${skill_file#"$repo_root"/}: description превышает 512 байт"
  fi
done < <(
  find "$repo_root" \
    -type d \( -name .venv -o -name node_modules -o -name .git -o -name .next \) -prune -o \
    -path '*/.agents/skills/*/SKILL.md' -type f -print \
    | sort
)

# Проверяем также ссылки ../rules, AGENTS и вложенных references.
while IFS= read -r context_file; do
  while IFS= read -r target; do
    target=${target%%#*}
    case "$target" in
      ""|*://*|mailto:*) continue ;;
    esac
    if [[ ! -e "$(dirname "$context_file")/$target" ]]; then
      fail "${context_file#"$repo_root"/}: отсутствует ссылка $target"
    fi
  done < <(grep -oE '\]\([^ )]+\)' "$context_file" | sed -E 's/^\]\((.*)\)$/\1/' | sort -u || true)
done < <(
  find "$repo_root" \
    -type d \( -name .venv -o -name node_modules -o -name .git -o -name .next \) -prune -o \
    -type f \( -name AGENTS.md -o -path '*/.agents/*.md' -o -path '*/docs/agent-context.md' \) -print
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
