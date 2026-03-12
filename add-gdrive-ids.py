"""
Скрипт добавления прямых ссылок Google Drive в каталог.

Читает Google Drive file ID из расширенных атрибутов синхронизированных файлов
(macOS + Google Drive for Desktop), добавляет поле gdrive_url в каждую запись
catalog.json и перестраивает cookbook.html.

Запускать после add-gdrive-ids.py не нужно — достаточно update-catalog.py.
Но при первоначальной настройке или при добавлении новых PDF запусти:

    python3 add-gdrive-ids.py

Требования: Python 3, Google Drive for Desktop (файлы должны быть синхронизированы).
"""

import json
import os

RECIPES_DIR = os.path.dirname(os.path.abspath(__file__))
CATALOG_PATH = os.path.join(RECIPES_DIR, "catalog.json")
HTML_PATH = os.path.join(RECIPES_DIR, "cookbook.html")

GDRIVE_URL_TEMPLATE = "https://drive.google.com/file/d/{file_id}/view"


def get_gdrive_id(fpath):
    """Читает Google Drive file ID из расширенных атрибутов файла."""
    try:
        attrs = os.listxattr(fpath)
        gdrive_attr = next((a for a in attrs if "item-id" in a), None)
        if gdrive_attr:
            return os.getxattr(fpath, gdrive_attr).decode("utf-8", errors="replace")
    except (OSError, StopIteration):
        pass
    return None


def update_catalog_with_gdrive_ids():
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    found = 0
    missing_file = 0
    no_attr = 0

    for entry in catalog:
        if entry.get("type") == "my_recipe":
            continue

        pdf_path = os.path.join(RECIPES_DIR, entry["path"])

        if not os.path.exists(pdf_path):
            print(f"  ⚠ Файл не найден: {entry['path']}")
            missing_file += 1
            continue

        file_id = get_gdrive_id(pdf_path)
        if file_id:
            entry["gdrive_url"] = GDRIVE_URL_TEMPLATE.format(file_id=file_id)
            found += 1
        else:
            print(f"  ⚠ Нет Google Drive ID: {entry['name']}")
            no_attr += 1

    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    print(f"\nКаталог обновлён:")
    print(f"  ✓ {found} PDF получили прямые ссылки Google Drive")
    if missing_file:
        print(f"  ⚠ {missing_file} файлов не найдено")
    if no_attr:
        print(f"  ⚠ {no_attr} файлов без Google Drive ID (не синхронизированы?)")

    return catalog


def update_html(catalog):
    """Обновляет DATA в cookbook.html."""
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    marker = "const DATA = "
    start = html.find(marker) + len(marker)
    depth = 0
    in_str = False
    esc = False
    end = start
    for i in range(start, len(html)):
        ch = html[i]
        if esc:
            esc = False
            continue
        if ch == "\\" and in_str:
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if not in_str:
            if ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

    new_data = json.dumps(catalog, ensure_ascii=False)
    new_html = html[:start] + new_data + html[end:]

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(new_html)

    print(f"  ✓ cookbook.html обновлён")


if __name__ == "__main__":
    print("Читаю Google Drive file IDs из атрибутов файлов...")
    catalog = update_catalog_with_gdrive_ids()

    print("\nОбновляю cookbook.html...")
    update_html(catalog)

    print("\nГотово! Теперь на GitHub Pages каждый PDF открывается напрямую.")
