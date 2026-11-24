#!/bin/bash
# Installs the clip tool skill for Claude Code and the tool it drives.
#
#   ./install.sh              copy the files, then install what the tool needs
#   ./install.sh --no-deps    copy the files only (run setup.sh later)
#
# The skill goes to  ~/.claude/skills/clip-tool-skill
# The tool goes to   ~/clip-tool   (set CLIP_TOOL_HOME to choose another folder)
#
# Safe to run again to update: your settings (config.env), brand voice notes,
# music, finished clips and caches are never overwritten or removed.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$HOME/.claude/skills/clip-tool-skill"
TOOL_DIR="${CLIP_TOOL_HOME:-$HOME/clip-tool}"
RUN_DEPS=1
for arg in "$@"; do
  case "$arg" in
    --no-deps) RUN_DEPS=0 ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)"; exit 2 ;;
  esac
done

if [ ! -f "$HERE/skill/SKILL.md" ] || [ ! -f "$HERE/tool/process_local.py" ]; then
  echo "This script must be run from the downloaded clip-tool-skill folder (skill/ and tool/ are missing)."
  exit 1
fi
case "$TOOL_DIR" in
  *" "*) echo "The tool folder cannot have a space in its path: $TOOL_DIR"; echo "Choose another with CLIP_TOOL_HOME=/some/folder bash install.sh"; exit 1 ;;
esac
if [ "$(uname -s)" != "Darwin" ]; then
  echo "Note: this tool is built and tested on macOS. Continuing anyway."
fi

echo "== Skill -> $SKILL_DIR"
mkdir -p "$SKILL_DIR"
cp "$HERE/skill/SKILL.md" "$SKILL_DIR/SKILL.md"
if [ "$TOOL_DIR" != "$HOME/clip-tool" ]; then
  # The skill refers to ~/clip-tool; point it at the folder actually used.
  ESCAPED="$(printf '%s' "$TOOL_DIR" | sed 's/[&|\\]/\\&/g')"
  sed -i.bak "s|~/clip-tool|$ESCAPED|g" "$SKILL_DIR/SKILL.md" && rm -f "$SKILL_DIR/SKILL.md.bak"
fi

echo "== Tool  -> $TOOL_DIR"
mkdir -p "$TOOL_DIR"
# Program files are refreshed. Anything that is yours is kept.
( cd "$HERE/tool" && find . -type f \
    ! -path './.venv/*' ! -path './.cache/*' ! -path './output/*' \
    ! -path './render/node_modules/*' ! -path './render/public/*' ! -path './render/.props/*' \
    ! -name '.DS_Store' ! -name '*.pyc' -print ) | while IFS= read -r rel; do
  rel="${rel#./}"
  dest="$TOOL_DIR/$rel"
  case "$rel" in
    config.env|selector/brand_voice.md|music/music_config.json)
      if [ -e "$dest" ]; then echo "   kept your $rel"; continue; fi ;;
  esac
  mkdir -p "$(dirname "$dest")"
  cp "$HERE/tool/$rel" "$dest"
done
chmod +x "$TOOL_DIR/setup.sh"

if [ ! -f "$TOOL_DIR/config.env" ]; then
  cp "$TOOL_DIR/config.example.env" "$TOOL_DIR/config.env"
  echo "   created config.env with default settings"
else
  echo "   kept your config.env"
fi

if [ "$RUN_DEPS" -eq 1 ]; then
  echo
  echo "== Installing what the tool needs (internet required, a few minutes)"
  if ! bash "$TOOL_DIR/setup.sh"; then
    echo
    echo "Setup did not finish. Fix the item above, then run:  bash \"$TOOL_DIR/setup.sh\""
    exit 1
  fi
else
  echo
  echo "Files copied. Dependencies were not installed (--no-deps)."
  echo "Run this when you are ready:  bash \"$TOOL_DIR/setup.sh\""
fi

echo
echo "Done. Restart Claude Code, then say:  clip up /path/to/my-video.mp4"
