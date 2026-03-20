"""
Скрипт обновления кулинарного каталога.
Запускать когда добавлены новые рецепты в папку "my-recipes".

Что делает:
- Генерирует HTML-страницу для каждого .txt рецепта
- Обновляет catalog.json
- Пересобирает HTML каталог "cookbook.html"
"""

import json
import os
import re
import sys

TRANSLIT = {
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh',
    'з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o',
    'п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'kh','ц':'ts',
    'ч':'ch','ш':'sh','щ':'sch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya',
    'А':'A','Б':'B','В':'V','Г':'G','Д':'D','Е':'E','Ё':'E','Ж':'Zh',
    'З':'Z','И':'I','Й':'Y','К':'K','Л':'L','М':'M','Н':'N','О':'O',
    'П':'P','Р':'R','С':'S','Т':'T','У':'U','Ф':'F','Х':'Kh','Ц':'Ts',
    'Ч':'Ch','Ш':'Sh','Щ':'Sch','Ъ':'','Ы':'Y','Ь':'','Э':'E','Ю':'Yu','Я':'Ya',
}

def to_latin(name):
    result = ''.join(TRANSLIT.get(ch, ch) for ch in name)
    result = result.lower()
    result = re.sub(r'[^a-z0-9]+', '-', result)
    return result.strip('-')

RECIPES_DIR = os.path.dirname(os.path.abspath(__file__))
MY_RECIPES_DIR = os.path.join(RECIPES_DIR, "my-recipes")
CATALOG_PATH = os.path.join(RECIPES_DIR, "catalog.json")
HTML_PATH = os.path.join(RECIPES_DIR, "cookbook.html")


def extract_ingredient_lines(text):
    ingr_match = re.search(r"(?:Ingredients|Ингредиенты)[^:]*:(.*?)(?:Instructions|Приготовление|Соус|==|\Z)", text, re.DOTALL)
    if not ingr_match:
        return [l.strip() for l in text.split("\n") if l.strip() and not l.startswith("#") and len(l.strip()) > 3][:40]
    section = ingr_match.group(1).strip()
    return [l.strip() for l in section.split("\n") if l.strip() and not l.startswith("#")][:40]


def load_txt_recipe(fpath):
    with open(fpath, "r", encoding="utf-8") as f:
        text = f.read()

    fname = os.path.basename(fpath)
    base = fname.replace(".txt", "")
    # Rename file to Latin if needed
    latin_base = to_latin(base)
    if base != latin_base:
        new_fpath = os.path.join(os.path.dirname(fpath), latin_base + ".txt")
        os.rename(fpath, new_fpath)
        fpath = new_fpath
        fname = latin_base + ".txt"
        base = latin_base
        with open(fpath, "r", encoding="utf-8") as f2:
            text = f2.read()

    name_match = re.search(r"(?:Title|Название):\s*(.+)", text)
    name = name_match.group(1).strip() if name_match else base

    tags_match = re.search(r"Tags:\s*(.+)", text)
    tags = tags_match.group(1).strip() if tags_match else ""

    source_match = re.search(r"Source:\s*(.+)", text)
    source = source_match.group(1).strip() if source_match else ""

    category_match = re.search(r"Category:\s*(.+)", text)
    display_category = category_match.group(1).strip() if category_match else ""

    image_match = re.search(r"Image:\s*(.+)", text)
    image = image_match.group(1).strip() if image_match else ""

    # Fallback: check legacy photo/ directory if no Image: field
    if not image:
        for ext in [".jpg", ".jpeg", ".png"]:
            photo_path = os.path.join(MY_RECIPES_DIR, "photo", base + ext)
            if os.path.exists(photo_path):
                image = f"photo/{base}{ext}"
                break

    ingr_lines = extract_ingredient_lines(text)

    return {
        "name": name,
        "original_name": base,
        "path": "my-recipes/" + fname,
        "type": "my_recipe",
        "category": "my-recipes",
        "tags": tags,
        "source": source,
        "display_category": display_category,
        "image": "my-recipes/" + image if image else "",
        "pages": 1,
        "recipes": [],
        "preview": text[:200].replace("\n", " "),
        "search_text": text,
        "recipe_sections": [{
            "name": name,
            "page": 1,
            "ingredients": ingr_lines,
            "text": text[:2000]
        }]
    }


def update_catalog():
    # Load existing catalog
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    # Remove all my_recipe entries (will re-add from files)
    catalog = [e for e in catalog if e.get("type") != "my_recipe"]

    # Add all .txt files from my-recipes/
    added = []
    for fname in sorted(os.listdir(MY_RECIPES_DIR)):
        if not fname.endswith(".txt"):
            continue
        fpath = os.path.join(MY_RECIPES_DIR, fname)
        entry = load_txt_recipe(fpath)
        # Use .html path (generated from .txt)
        entry["path"] = "my-recipes/" + fname.replace(".txt", ".html")
        catalog.append(entry)
        added.append(entry["name"])

    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    print(f"Каталог обновлён: {len(catalog)} записей, из них {len(added)} личных рецептов:")
    for name in added:
        print(f"  - {name}")
    return catalog


def update_html(catalog):
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

    # Also update embedded LINKS data
    links_path = os.path.join(RECIPES_DIR, "links.json")
    if os.path.exists(links_path):
        with open(links_path, "r", encoding="utf-8") as f:
            links_data = json.load(f)
        with open(HTML_PATH, "r", encoding="utf-8") as f:
            html_content = f.read()
        marker = "const LINKS = "
        ls = html_content.find(marker)
        if ls >= 0:
            le = html_content.find(";", ls + len(marker))
            new_links = json.dumps(links_data, ensure_ascii=False)
            html_content = html_content[:ls + len(marker)] + new_links + html_content[le:]
            with open(HTML_PATH, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"  ✓ Links updated: {len(links_data)} sites")

    print(f"HTML обновлён: {HTML_PATH}")


if __name__ == "__main__":
    # Step 1: generate HTML pages for each recipe (only if .txt is newer than .html)
    print("Генерирую HTML страницы рецептов...")
    sys.path.insert(0, RECIPES_DIR)
    import generate_recipe_html as gen
    for fname in sorted(os.listdir(MY_RECIPES_DIR)):
        if fname.endswith(".txt"):
            txt_path = os.path.join(MY_RECIPES_DIR, fname)
            html_path = os.path.join(MY_RECIPES_DIR, fname.replace(".txt", ".html"))
            if os.path.exists(html_path) and os.path.getmtime(html_path) >= os.path.getmtime(txt_path):
                print(f"  — {fname.replace('.txt', '.html')} (без изменений, пропущен)")
                continue
            out = gen.generate_html(txt_path)
            print(f"  ✓ {os.path.basename(out)}")

    # Step 2: update catalog
    print("Обновляю каталог...")
    catalog = update_catalog()

    # Step 3: rebuild main HTML
    print("Обновляю HTML каталог...")
    update_html(catalog)
    print("Готово!")
