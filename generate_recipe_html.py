"""
Генерирует красивые HTML-страницы из .txt файлов рецептов.
"""

import os
import re
import json

RECIPES_DIR = os.path.dirname(os.path.abspath(__file__))
MY_RECIPES_DIR = os.path.join(RECIPES_DIR, "my-recipes")
PHOTO_DIR = os.path.join(MY_RECIPES_DIR, "photo")


def parse_recipe(text):
    """Парсит .txt файл рецепта в структуру."""
    result = {
        "name": "",
        "category": "",
        "tags": "",
        "rating": "",
        "source": "",
        "related": "",
        "servings": "",
        "total_time": "",
        "active_time": "",
        "note_header": "",
        "sections": []  # [{title, items: [str]}]
    }

    # Extract metadata
    for field, key in [("Title:", "name"), ("Category:", "category"),
                       ("Tags:", "tags"), ("Rating:", "rating"),
                       ("Source:", "source"), ("Related:", "related"),
                       ("Servings:", "servings"), ("Total Time:", "total_time"),
                       ("Active Time:", "active_time")]:
        m = re.search(field + r"\s*(.+)", text)
        if m:
            result[key] = m.group(1).strip()

    # Split into sections by blank lines + capitalized headers
    # Headers: lines that end with : and are short, or ALL CAPS words
    lines = text.split("\n")

    current_section = None
    current_items = []
    skip_meta = {"Title:", "Category:", "Tags:", "Rating:", "Source:", "Related:", "Status:",
                 "Servings:", "Total Time:", "Active Time:"}

    for line in lines:
        stripped = line.strip()

        # Skip empty lines between sections
        if not stripped:
            if current_items and current_section is not None:
                pass  # keep going
            continue

        # Skip metadata lines
        if any(stripped.startswith(s) for s in skip_meta):
            continue

        # Detect section header: short line ending in : (not a numbered step)
        # OR == ... == style header
        is_eq_header = bool(re.match(r'^==\s*.+\s*==$', stripped))
        is_colon_header = (
            re.match(r'^[А-ЯЁA-Za-z].{0,60}:$', stripped) and
            not re.match(r'^\d+\.', stripped) and
            len(stripped) < 80
        )
        is_header = is_eq_header or is_colon_header

        if is_header:
            if current_section is not None and current_items:
                result["sections"].append({"title": current_section, "items": current_items})
            if is_eq_header:
                current_section = re.sub(r'^==\s*|\s*==$', '', stripped)
            else:
                current_section = stripped.rstrip(":")
            current_items = []
        else:
            if current_section is None:
                current_section = ""
            current_items.append(stripped)

    if current_section is not None and current_items:
        result["sections"].append({"title": current_section, "items": current_items})

    return result


def is_step(line):
    return bool(re.match(r'^\d+[.)]\s', line) or re.match(r'^[-*]\s', line))


def render_markdown_table(rows):
    """Рендерит блок строк вида | a | b | c | как HTML-таблицу."""
    html = '<table class="recipe-table">'
    header_done = False
    for row in rows:
        # Skip separator rows like |---|---|---|
        if re.match(r'^\|[-| :]+\|$', row.strip()):
            continue
        cells = [c.strip() for c in row.strip().strip('|').split('|')]
        if not header_done:
            html += '<thead><tr>' + ''.join(f'<th>{c}</th>' for c in cells) + '</tr></thead><tbody>'
            header_done = True
        else:
            html += '<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>'
    html += '</tbody></table>'
    return html


def render_item_block(items):
    """Рендерит однородный блок строк (без таблиц)."""
    if not items:
        return ""
    steps = [i for i in items if re.match(r'^\d+[.)]\s', i)]
    bullets = [i for i in items if re.match(r'^[-•*]\s', i)]

    if len(steps) >= len(items) * 0.5:
        html = '<ol class="steps">'
        for item in items:
            clean = re.sub(r'^\d+[.)]\s*', '', item)
            html += f'<li>{clean}</li>'
        html += '</ol>'
    elif len(bullets) >= len(items) * 0.5:
        html = '<ul class="notes-list">'
        for item in items:
            clean = re.sub(r'^[-•*]\s*', '', item)
            html += f'<li>{clean}</li>'
        html += '</ul>'
    else:
        # Long text lines → render as paragraphs
        avg_len = sum(len(i) for i in items) / len(items) if items else 0
        if avg_len > 60:
            html = ''.join(f'<p class="para">{item}</p>' for item in items)
        else:
            html = '<ul class="ingr-list">'
            for item in items:
                m = re.match(r'^([\d½¼¾.,/]+\s*(?:г|кг|мл|л|шт|ст\.л\.|ч\.л\.|стакан|cup|tbsp|tsp|lb|oz|ml|g)[^—]*?)\s*[—-]?\s*(.*)$', item)
                if m:
                    html += f'<li><span class="qty">{m.group(1)}</span> {m.group(2)}</li>'
                else:
                    html += f'<li>{item}</li>'
            html += '</ul>'
    return html


def render_section_items(items):
    """Рендерит список строк, разбивая на блоки: таблицы, шаги, списки, параграфы."""
    if not items:
        return ""
    html = ""
    i = 0
    while i < len(items):
        item = items[i]
        # Sub-header: short line ending with ":" (e.g. "для соуса:")
        if (item.endswith(':') and len(item) <= 60
                and not re.match(r'^\d', item)
                and not item.startswith('|')):
            html += f'<p class="ingr-subheader">{item}</p>'
            i += 1
        # Collect a table block
        elif item.startswith('|'):
            block = []
            while i < len(items) and items[i].startswith('|'):
                block.append(items[i])
                i += 1
            html += render_markdown_table(block)
        else:
            # Collect a non-table block (stop at sub-headers and tables)
            block = []
            while i < len(items) and not items[i].startswith('|') and not (
                    items[i].endswith(':') and len(items[i]) <= 60
                    and not re.match(r'^\d', items[i])):
                block.append(items[i])
                i += 1
            html += render_item_block(block)
    return html


def generate_html(txt_path):
    with open(txt_path, "r", encoding="utf-8") as f:
        text = f.read()

    base = os.path.basename(txt_path).replace(".txt", "")
    recipe = parse_recipe(text)

    name = recipe["name"] or base

    # Check for photo
    photo_html = ""
    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
        photo_path = os.path.join(PHOTO_DIR, base + ext)
        if os.path.exists(photo_path):
            photo_html = f'<div class="photo-wrap"><img src="photo/{base}{ext}" alt="{name}"></div>'
            break

    # Rating badge
    rating_html = ""
    if recipe["rating"]:
        rating_html = f'<span class="rating">{recipe["rating"]}</span>'

    # Source
    source_html = ""
    if recipe["source"]:
        source_html = f'<div class="source">Source: {recipe["source"]}</div>'

    # Related recipes — look up titles from other .txt files
    related_html = ""
    if recipe["related"]:
        slugs = [s.strip() for s in recipe["related"].split(",") if s.strip()]
        links = []
        for slug in slugs:
            related_txt = os.path.join(MY_RECIPES_DIR, slug + ".txt")
            label = slug  # fallback: use filename
            if os.path.exists(related_txt):
                with open(related_txt, "r", encoding="utf-8") as rf:
                    m = re.search(r"Title:\s*(.+)", rf.read())
                    if m:
                        label = m.group(1).strip()
            links.append(f'<a class="related-link" href="{slug}.html">{label}</a>')
        related_html = (
            '<div class="related-section">'
            '<span class="related-label">Part of menu:</span> '
            + " · ".join(links)
            + '</div>'
        )

    # Category/tags
    meta_parts = []
    if recipe["category"]:
        meta_parts.append(recipe["category"])
    meta_html = f'<div class="meta">{" · ".join(meta_parts)}</div>' if meta_parts else ""

    # Time/servings info
    info_lines = []
    if recipe["servings"]:
        info_lines.append(f'<span><b>Servings:</b> {recipe["servings"]}</span>')
    if recipe["total_time"]:
        info_lines.append(f'<span><b>Total Time:</b> {recipe["total_time"]}</span>')
    if recipe["active_time"]:
        info_lines.append(f'<span><b>Active Time:</b> {recipe["active_time"]}</span>')
    info_bar_html = f'<div class="info-bar">{"  ·  ".join(info_lines)}</div>' if info_lines else ""

    # Build sections
    sections_html = ""
    for sec in recipe["sections"]:
        title = sec["title"]
        items = sec["items"]
        if not items:
            continue

        # Section icon
        icons = {
            "Ingredient": "🧂", "Состав": "🧂", "Продукт": "🧂",
            "Instruction": "👩‍🍳", "Приготовление": "👩‍🍳", "Шаги": "👩‍🍳",
            "Tips": "💡", "Примечани": "💡", "Совет": "💡",
            "Соус": "🥣", "Заправк": "🥣", "Подач": "🍽️",
            "Вариаци": "✨", "Пропорци": "📐",
            "My Notes": "✏️",
        }
        icon = "📌"
        for k, v in icons.items():
            if k.lower() in title.lower():
                icon = v
                break

        title_disp = title if title else ""

        # Special styling for My Notes section
        if title.lower() == "my notes":
            if items:
                notes_items_html = "".join(f"<p>{i}</p>" for i in items)
            else:
                notes_items_html = '<p class="empty-note">— not yet —</p>'
            sections_html += f"""
        <div class="section my-notes-section">
          <h2 class="section-title"><span class="section-icon">✏️</span>My Notes</h2>
          <div class="my-notes-box">{notes_items_html}</div>
        </div>"""
            continue

        sections_html += f"""
        <div class="section">
          {'<h2 class="section-title"><span class="section-icon">' + icon + '</span>' + title_disp + '</h2>' if title_disp else ''}
          {render_section_items(items)}
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #faf7f4; color: #2d2926; max-width: 680px; margin: 0 auto; padding-bottom: 40px; }}

  .photo-wrap img {{ width: 100%; max-height: 380px; object-fit: cover; display: block; }}

  .header {{ padding: 24px 24px 16px; }}
  h1 {{ font-size: 26px; font-weight: 700; line-height: 1.2; margin-bottom: 10px; color: #1a1714; }}
  .meta {{ font-size: 13px; color: #9a8a80; margin-bottom: 6px; }}
  .rating {{ display: inline-block; background: #fff3e6; color: #c05f2a;
             font-size: 13px; font-weight: 600; padding: 3px 10px; border-radius: 20px; margin-bottom: 8px; }}
  .source {{ font-size: 12px; color: #b0a09a; margin-top: 4px; }}

  .info-bar {{ font-size: 13px; color: #5a4a3a; margin: 6px 0 4px; }}

  .section {{ padding: 0 24px; margin-bottom: 24px; }}
  .section-title {{ font-size: 15px; font-weight: 700; color: #7a4f2a;
                    text-transform: uppercase; letter-spacing: 0.6px;
                    margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }}
  .section-icon {{ font-size: 17px; }}

  .ingr-subheader {{ font-size: 13px; font-weight: 700; text-transform: uppercase;
                     letter-spacing: 0.5px; color: #8a6a3a; margin: 14px 0 4px; }}
  .ingr-list {{ list-style: none; display: flex; flex-direction: column; gap: 8px; }}
  .ingr-list li {{ font-size: 15px; line-height: 1.5; padding: 8px 12px;
                   background: white; border-radius: 8px;
                   border-left: 3px solid #f0c080; }}
  .qty {{ font-weight: 600; color: #c05f2a; }}

  .steps {{ list-style: none; counter-reset: steps; display: flex; flex-direction: column; gap: 12px; }}
  .steps li {{ font-size: 15px; line-height: 1.6; padding: 12px 14px 12px 48px;
               background: white; border-radius: 10px; position: relative; }}
  .steps li::before {{ counter-increment: steps; content: counter(steps);
                       position: absolute; left: 12px; top: 12px;
                       width: 26px; height: 26px; background: #f0c080;
                       border-radius: 50%; display: flex; align-items: center;
                       justify-content: center; font-weight: 700; font-size: 13px; color: #7a4f2a; }}

  .notes-list {{ list-style: none; display: flex; flex-direction: column; gap: 8px; }}
  .notes-list li {{ font-size: 14px; line-height: 1.5; padding: 8px 12px 8px 32px;
                    background: #fffbf5; border-radius: 8px; position: relative;
                    border: 1px solid #f0e8d8; color: #5a4a3a; }}
  .notes-list li::before {{ content: '💡'; position: absolute; left: 8px; top: 8px; font-size: 13px; }}

  .my-notes-section {{ margin-top: 8px; }}
  .my-notes-box {{ background: #fffef5; border: 1.5px dashed #c8b870; border-radius: 12px;
                  padding: 14px 18px; font-size: 14px; line-height: 1.7; color: #5a4a30; }}
  .my-notes-box p {{ margin-bottom: 6px; }}
  .my-notes-box p:last-child {{ margin-bottom: 0; }}
  .empty-note {{ color: #c0b090; font-style: italic; }}

  .recipe-table {{ width: 100%; border-collapse: collapse; margin: 4px 0 12px; font-size: 14px; }}
  .recipe-table th {{ background: #f5ede4; color: #7a4a28; padding: 8px 12px;
                      text-align: left; border: 1px solid #e0cfc0; font-weight: 700; }}
  .recipe-table td {{ padding: 8px 12px; border: 1px solid #e8ddd5; vertical-align: top;
                      line-height: 1.5; }}
  .recipe-table tr:nth-child(even) td {{ background: #fdf8f5; }}

  p.para {{ font-size: 15px; line-height: 1.65; color: #2d2926; margin-bottom: 12px; }}
  p.para:last-child {{ margin-bottom: 0; }}

  .related-section {{ font-size: 13px; margin-top: 8px; color: #9a8a80; }}
  .related-label {{ font-weight: 600; color: #7a4f2a; }}
  .related-link {{ color: #c05f2a; text-decoration: none; font-weight: 500; }}
  .related-link:hover {{ text-decoration: underline; }}

  .back-btn {{ display: inline-block; margin: 20px 24px 4px;
               color: #c05f2a; font-size: 14px; text-decoration: none; }}
  .back-btn:hover {{ text-decoration: underline; }}

  @media (max-width: 480px) {{
    h1 {{ font-size: 22px; }}
    .steps li {{ padding-left: 42px; }}
  }}
</style>
</head>
<body>
  <a class="back-btn" href="../cookbook.html">← Catalog</a>
  {photo_html}
  <div class="header">
    {rating_html}
    <h1>{name}</h1>
    {meta_html}
    {info_bar_html}
    {related_html}
    {source_html}
  </div>
  {sections_html}
</body>
</html>"""

    out_path = txt_path.replace(".txt", ".html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    return out_path


if __name__ == "__main__":
    generated = []
    for fname in sorted(os.listdir(MY_RECIPES_DIR)):
        if not fname.endswith(".txt"):
            continue
        txt_path = os.path.join(MY_RECIPES_DIR, fname)
        out = generate_html(txt_path)
        generated.append(os.path.basename(out))
        print(f"  ✓ {os.path.basename(out)}")

    print(f"\nСгенерировано {len(generated)} HTML-страниц")
