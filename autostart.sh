#!/bin/bash
# Устанавливает автозапуск редактора рецептов при входе в macOS.
# Запусти один раз: bash autostart.sh
# После этого сервер будет стартовать автоматически, открывай http://localhost:5050

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$DIR/recipe_editor.py"
PYTHON="$(which python3)"
LABEL="com.julia.recipe-editor"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$DIR/recipe_editor.log"

if [ ! -f "$SCRIPT" ]; then
  echo "Ошибка: recipe_editor.py не найден в $DIR"
  exit 1
fi

# Остановить предыдущий экземпляр если есть
launchctl unload "$PLIST" 2>/dev/null || true

# Создать plist
cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>             <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$SCRIPT</string>
    <string>--no-browser</string>
  </array>
  <key>RunAtLoad</key>         <true/>
  <key>KeepAlive</key>         <true/>
  <key>WorkingDirectory</key>  <string>$DIR</string>
  <key>StandardOutPath</key>   <string>$LOG</string>
  <key>StandardErrorPath</key> <string>$LOG</string>
</dict>
</plist>
EOF

# Запустить прямо сейчас
launchctl load "$PLIST"

echo ""
echo "✓ Установлено! Редактор запущен и будет стартовать автоматически."
echo "  Открывай в браузере: http://localhost:5050"
echo ""
echo "  Чтобы отменить автозапуск: bash autostart.sh --remove"

# Удаление
if [ "$1" = "--remove" ]; then
  launchctl unload "$PLIST"
  rm -f "$PLIST"
  echo "✓ Автозапуск отключён."
fi
