#!/usr/bin/env python3
"""
Recipe editor: personal notes + content.
Запуск: python3 recipe_editor.py
Затем открыть: http://localhost:5050

Только стандартная библиотека Python — никаких зависимостей.
"""
import os
import re
import json
import base64
import mimetypes
import subprocess
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

RECIPES_DIR = os.path.dirname(os.path.abspath(__file__))
MY_RECIPES_DIR = os.path.join(RECIPES_DIR, "my-recipes")
IMAGES_DIR = os.path.join(MY_RECIPES_DIR, "images")
PORT = 5050


# ─── recipe helpers ──────────────────────────────────────────────────────────

def get_txt_path(slug):
    return os.path.join(MY_RECIPES_DIR, slug + ".txt")


def _split_header_body(text):
    """Return (header_str, body_str) splitting at the first blank line after headers."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.strip() == "":
            # blank line — everything up to here is header
            return "\n".join(lines[:i]), "\n".join(lines[i + 1:])
    return text, ""


def read_personal_data(slug):
    path = get_txt_path(slug)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    data = {"title": slug, "rating": "", "cooked": [], "my_photo": "", "my_notes": ""}
    for field, key in [("Title", "title"), ("Rating", "rating"), ("My Photo", "my_photo")]:
        m = re.search(rf"^{field}:\s*(.+)", text, re.M)
        if m:
            data[key] = m.group(1).strip()
    data["cooked"] = re.findall(r"^Cooked:\s*(.+)", text, re.M)
    m = re.search(r"\nMy Notes:\s*\n([\s\S]*?)$", text)
    if m:
        data["my_notes"] = m.group(1).strip()
    return data


def read_body_data(slug):
    """Return {description, ingredients, method} from the recipe body."""
    path = get_txt_path(slug)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    _, body = _split_header_body(text)

    # Strip My Notes from the end before parsing
    body = re.sub(r"\n\nMy Notes:[\s\S]*$", "", body)
    body = re.sub(r"\nMy Notes:[\s\S]*$", "", body)

    # Split on section headers Ингредиенты: and Метод:
    parts = re.split(r"\n(Ингредиенты:|Метод:)\n", body)
    # parts[0] = description, then alternating: label, content, label, content ...
    description = parts[0].strip()
    ingredients = ""
    method = ""
    i = 1
    while i < len(parts) - 1:
        label = parts[i]
        content = parts[i + 1].strip()
        if label == "Ингредиенты:":
            ingredients = content
        elif label == "Метод:":
            method = content
        i += 2

    return {"description": description, "ingredients": ingredients, "method": method}


def write_personal_data(slug, rating, cooked_entries, my_notes, my_photo):
    path = get_txt_path(slug)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    def upsert(text, field, value):
        pattern = rf"^{re.escape(field)}:[ \t]*[^\n]*"
        if value:
            if re.search(pattern, text, re.M):
                return re.sub(pattern, f"{field}: {value}", text, flags=re.M)
            for anchor in ["Image:", "My Photo:", "Source:", "Tags:"]:
                if re.search(rf"^{re.escape(anchor)}", text, re.M):
                    return re.sub(
                        rf"^({re.escape(anchor)}[^\n]*)",
                        rf"\1\n{field}: {value}",
                        text, flags=re.M, count=1,
                    )
            return text + f"\n{field}: {value}\n"
        else:
            return re.sub(pattern + r"\n?", "", text, flags=re.M)

    content = upsert(content, "Rating", rating)
    content = upsert(content, "My Photo", my_photo)

    # Cooked: remove all, re-insert after Rating/My Photo/Image/Source
    content = re.sub(r"^Cooked:[ \t]*[^\n]*\n?", "", content, flags=re.M)
    if cooked_entries:
        block = "\n".join(f"Cooked: {c}" for c in cooked_entries if c.strip())
        for anchor in ["Rating:", "My Photo:", "Image:", "Source:"]:
            if re.search(rf"^{re.escape(anchor)}", content, re.M):
                content = re.sub(
                    rf"^({re.escape(anchor)}[^\n]*)",
                    rf"\1\n{block}",
                    content, flags=re.M, count=1,
                )
                break

    # My Notes: remove existing, append at end
    content = re.sub(r"\n\nMy Notes:[\s\S]*$", "", content)
    content = re.sub(r"\nMy Notes:[\s\S]*$", "", content)
    if my_notes.strip():
        content = content.rstrip("\n") + "\n\nMy Notes:\n" + my_notes.strip() + "\n"

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    _regen(path)


def write_body_data(slug, description, ingredients, method):
    """Rewrite the recipe body (description / Ингредиенты / Метод) keeping header & My Notes intact."""
    path = get_txt_path(slug)
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    header, old_body = _split_header_body(text)

    # Preserve My Notes if present
    my_notes = ""
    m = re.search(r"\n\nMy Notes:\s*\n([\s\S]*?)$", old_body)
    if not m:
        m = re.search(r"\nMy Notes:\s*\n([\s\S]*?)$", old_body)
    if m:
        my_notes = m.group(1).strip()

    # Build new body
    parts = []
    if description.strip():
        parts.append(description.strip())
    if ingredients.strip():
        parts.append("Ингредиенты:\n" + ingredients.strip())
    if method.strip():
        parts.append("Метод:\n" + method.strip())

    new_body = "\n\n".join(parts)

    if my_notes:
        new_body = new_body.rstrip("\n") + "\n\nMy Notes:\n" + my_notes + "\n"

    new_text = header + "\n\n" + new_body + "\n"

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_text)

    _regen(path)


def _regen(path):
    gen = os.path.join(RECIPES_DIR, "generate_recipe_html.py")
    subprocess.run(["python3", gen, path], capture_output=True)


def create_recipe(slug, title, category, tags, servings, active_time,
                  total_time, source, description, ingredients, method):
    """Create a new .txt recipe file. Returns error string or None on success."""
    if not slug or not re.match(r'^[a-z0-9][a-z0-9\-]*$', slug):
        return "Filename must be lowercase letters, digits and hyphens only."
    path = get_txt_path(slug)
    if os.path.exists(path):
        return f"File '{slug}.txt' already exists."

    header_lines = [f"Title: {title}"]
    if category:    header_lines.append(f"Category: {category}")
    if tags:        header_lines.append(f"Tags: {tags}")
    if servings:    header_lines.append(f"Servings: {servings}")
    if active_time: header_lines.append(f"Active Time: {active_time}")
    if total_time:  header_lines.append(f"Total Time: {total_time}")
    if source:      header_lines.append(f"Source: {source}")

    body_parts = []
    if description.strip():
        body_parts.append(description.strip())
    if ingredients.strip():
        body_parts.append("Ингредиенты:\n" + ingredients.strip())
    if method.strip():
        body_parts.append("Метод:\n" + method.strip())

    content = "\n".join(header_lines) + "\n\n" + "\n\n".join(body_parts) + "\n"

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    _regen(path)
    return None


def list_recipes():
    result = []
    for fname in sorted(os.listdir(MY_RECIPES_DIR)):
        if not fname.endswith(".txt"):
            continue
        slug = fname[:-4]
        with open(os.path.join(MY_RECIPES_DIR, fname), "r", encoding="utf-8") as f:
            content = f.read()
        m = re.search(r"^Title:\s*(.+)", content, re.M)
        title = m.group(1).strip() if m else slug
        result.append({"slug": slug, "title": title})
    return sorted(result, key=lambda r: r["title"].lower())


# ─── HTTP handler ─────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):

    def log_message(self, *args):
        pass  # silence request log

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length))

    def send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/":
            self.send_html(HTML_PAGE)

        elif path == "/api/recipes":
            self.send_json(list_recipes())

        elif path.startswith("/api/recipe/"):
            slug = path[len("/api/recipe/"):]
            data = read_personal_data(slug)
            if data is None:
                self.send_json({"error": "not found"}, 404)
            else:
                self.send_json(data)

        elif path.startswith("/api/body/"):
            slug = path[len("/api/body/"):]
            data = read_body_data(slug)
            if data is None:
                self.send_json({"error": "not found"}, 404)
            else:
                self.send_json(data)

        elif path.startswith("/img/"):
            filename = path[len("/img/"):]
            filepath = os.path.join(IMAGES_DIR, filename)
            if not os.path.exists(filepath):
                self.send_response(404); self.end_headers(); return
            mime = mimetypes.guess_type(filepath)[0] or "image/jpeg"
            with open(filepath, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path

        if path.startswith("/api/update/"):
            slug = path[len("/api/update/"):]
            body = self.read_json()
            write_personal_data(
                slug,
                rating=body.get("rating", ""),
                cooked_entries=body.get("cooked", []),
                my_notes=body.get("my_notes", ""),
                my_photo=body.get("my_photo", ""),
            )
            self.send_json({"ok": True})

        elif path.startswith("/api/update-body/"):
            slug = path[len("/api/update-body/"):]
            body = self.read_json()
            write_body_data(
                slug,
                description=body.get("description", ""),
                ingredients=body.get("ingredients", ""),
                method=body.get("method", ""),
            )
            self.send_json({"ok": True})

        elif path.startswith("/api/photo/"):
            slug = path[len("/api/photo/"):]
            body = self.read_json()
            ext = os.path.splitext(body.get("filename", "photo.jpg"))[1].lower() or ".jpg"
            filename = f"my-{slug}{ext}"
            filepath = os.path.join(IMAGES_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(base64.b64decode(body["data"]))
            self.send_json({"path": f"images/{filename}"})

        elif path == "/api/create-recipe":
            body = self.read_json()
            err = create_recipe(
                slug=body.get("slug", "").strip(),
                title=body.get("title", "").strip(),
                category=body.get("category", "").strip(),
                tags=body.get("tags", "").strip(),
                servings=body.get("servings", "").strip(),
                active_time=body.get("active_time", "").strip(),
                total_time=body.get("total_time", "").strip(),
                source=body.get("source", "").strip(),
                description=body.get("description", ""),
                ingredients=body.get("ingredients", ""),
                method=body.get("method", ""),
            )
            if err:
                self.send_json({"error": err}, 400)
            else:
                self.send_json({"ok": True, "slug": body.get("slug", "").strip()})

        else:
            self.send_response(404); self.end_headers()


# ─── HTML ─────────────────────────────────────────────────────────────────────

HTML_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>My Recipes — Editor</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: #faf7f4; color: #2d2926; height: 100vh; display: flex; overflow: hidden; }

/* ── Sidebar ── */
.sidebar { width: 280px; min-width: 280px; background: #fff;
           border-right: 1px solid #e8ddd5;
           display: flex; flex-direction: column; height: 100vh; }
.sidebar-head { padding: 16px; border-bottom: 1px solid #f0e8e0; }
.sidebar-head h1 { font-size: 16px; font-weight: 700; color: #7a4f2a; margin-bottom: 10px; }
.search { width: 100%; padding: 8px 12px; border: 1.5px solid #e0cfc0;
          border-radius: 20px; font-size: 14px; outline: none; background: #faf7f4; }
.search:focus { border-color: #c05f2a; }
.recipe-list { flex: 1; overflow-y: auto; }
.recipe-item { padding: 11px 16px; cursor: pointer; font-size: 14px;
               border-bottom: 1px solid #f5f0eb; line-height: 1.3;
               transition: background 0.1s; }
.recipe-item:hover { background: #fdf5ee; }
.recipe-item.active { background: #fff3e6; font-weight: 600; color: #c05f2a; }

/* ── Main panel ── */
.main { flex: 1; overflow-y: auto; padding: 32px; }
.empty-state { display: flex; flex-direction: column; align-items: center;
               justify-content: center; height: 60%; color: #c0a898; }
.empty-state .icon { font-size: 48px; margin-bottom: 12px; }

.form-wrap { max-width: 640px; }
.form-title { font-size: 22px; font-weight: 700; color: #1a1714; margin-bottom: 24px;
              padding-bottom: 12px; border-bottom: 2px solid #f0e8e0; }

/* ── Tabs ── */
.tabs { display: flex; gap: 0; border-bottom: 2px solid #f0e8e0; margin-bottom: 24px; }
.tab { padding: 8px 20px; font-size: 14px; font-weight: 600; cursor: pointer;
       color: #a09080; border-bottom: 2px solid transparent; margin-bottom: -2px;
       transition: color 0.15s; }
.tab:hover { color: #7a4f2a; }
.tab.active { color: #c05f2a; border-bottom-color: #c05f2a; }
.tab-panel { display: none; }
.tab-panel.active { display: block; }

.field { margin-bottom: 24px; }
.field label { display: block; font-size: 12px; font-weight: 700;
               text-transform: uppercase; letter-spacing: 0.6px;
               color: #7a4f2a; margin-bottom: 8px; }

/* Stars */
.stars { display: flex; gap: 6px; align-items: center; }
.star { font-size: 30px; cursor: pointer; color: #d8cfc4; transition: color 0.1s; line-height: 1;
        user-select: none; }
.star.on { color: #f0a020; }
.star:hover { color: #f0a020; }
.clear-rating { font-size: 12px; color: #b0a090; cursor: pointer; margin-left: 8px;
                text-decoration: underline; }

/* Cooked */
.cooked-list { display: flex; flex-direction: column; gap: 6px; }
.cooked-row { display: flex; gap: 8px; align-items: center; }
.cooked-input { flex: 1; padding: 8px 12px; border: 1.5px solid #e0cfc0;
                border-radius: 8px; font-size: 14px; outline: none; background: white; }
.cooked-input:focus { border-color: #c05f2a; }
.btn-del { background: none; border: none; cursor: pointer; color: #c0a0a0;
           font-size: 20px; padding: 2px 6px; line-height: 1; }
.btn-del:hover { color: #c03030; }
.btn-add { margin-top: 6px; background: none; border: 1.5px dashed #d0c0b0;
           color: #8a6a4a; font-size: 13px; padding: 6px 14px;
           border-radius: 20px; cursor: pointer; }
.btn-add:hover { border-color: #c05f2a; color: #c05f2a; }

/* Textareas */
textarea { width: 100%; padding: 12px; border: 1.5px solid #e0cfc0;
           border-radius: 10px; font-size: 14px; line-height: 1.6;
           font-family: inherit; outline: none; resize: vertical; background: #fffef5; }
textarea:focus { border-color: #c05f2a; }
#desc-input   { min-height: 100px; }
#ingr-input   { min-height: 180px; }
#method-input { min-height: 260px; }
#notes-input  { min-height: 120px; }

/* Photo */
.photo-section { display: flex; gap: 16px; align-items: flex-start; }
.photo-preview { width: 120px; height: 90px; border-radius: 10px;
                 background: #f0e8e0; display: flex; align-items: center;
                 justify-content: center; overflow: hidden; flex-shrink: 0;
                 border: 2px solid #e8d8c8; }
.photo-preview img { width: 100%; height: 100%; object-fit: cover; }
.no-photo { font-size: 28px; }
.photo-btns { display: flex; flex-direction: column; gap: 8px; }
.btn-upload { background: #f5ede4; color: #7a4f2a; border: 1.5px solid #e0cfc0;
              font-size: 13px; font-weight: 600; padding: 8px 16px;
              border-radius: 20px; cursor: pointer; }
.btn-upload:hover { background: #f0dfd0; }
.btn-clear-photo { background: none; border: none; color: #b09080; font-size: 13px;
                   cursor: pointer; padding: 4px 0; text-decoration: underline; }
.photo-name { font-size: 12px; color: #a09080; margin-top: 2px; }
#photo-file { display: none; }

/* Save */
.save-row { display: flex; align-items: center; gap: 14px; margin-top: 8px; padding-top: 8px; }
.btn-save { background: #c05f2a; color: white; border: none; font-size: 15px;
            font-weight: 700; padding: 12px 32px; border-radius: 24px; cursor: pointer; }
.btn-save:hover { background: #a04e22; }
.btn-save:disabled { background: #c0a090; cursor: default; }
.save-ok { color: #5a9a5a; font-size: 14px; font-weight: 600;
           opacity: 0; transition: opacity 0.3s; }
.save-ok.show { opacity: 1; }

/* Warning */
.edit-warning { font-size: 12px; color: #a09070; background: #fffae8;
                border: 1px solid #e8d888; border-radius: 8px;
                padding: 8px 12px; margin-bottom: 20px; line-height: 1.5; }

/* New Recipe button */
.btn-new { margin: 12px 16px 4px; padding: 9px 16px; width: calc(100% - 32px);
           background: #c05f2a; color: white; border: none; border-radius: 20px;
           font-size: 13px; font-weight: 700; cursor: pointer; text-align: center; }
.btn-new:hover { background: #a04e22; }

/* Modal */
.modal-backdrop { display: none; position: fixed; inset: 0;
                  background: rgba(0,0,0,0.45); z-index: 100;
                  align-items: center; justify-content: center; }
.modal-backdrop.open { display: flex; }
.modal { background: #fff; border-radius: 16px; padding: 28px 32px;
         width: 620px; max-width: 96vw; max-height: 90vh; overflow-y: auto;
         box-shadow: 0 8px 40px rgba(0,0,0,0.22); }
.modal h2 { font-size: 18px; font-weight: 700; color: #7a4f2a;
            margin-bottom: 20px; padding-bottom: 12px; border-bottom: 2px solid #f0e8e0; }
.modal .field { margin-bottom: 18px; }
.modal .field label { display: block; font-size: 11px; font-weight: 700;
                      text-transform: uppercase; letter-spacing: 0.6px;
                      color: #7a4f2a; margin-bottom: 6px; }
.modal input[type=text] { width: 100%; padding: 9px 12px; border: 1.5px solid #e0cfc0;
                          border-radius: 8px; font-size: 14px; outline: none; background: #fff; }
.modal input[type=text]:focus { border-color: #c05f2a; }
.modal .hint { font-size: 11px; color: #a09080; margin-top: 4px; }
.modal .row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.modal textarea { width: 100%; padding: 10px 12px; border: 1.5px solid #e0cfc0;
                  border-radius: 8px; font-size: 13px; font-family: inherit;
                  outline: none; resize: vertical; background: #fffef5; }
.modal textarea:focus { border-color: #c05f2a; }
.modal #m-desc   { min-height: 80px; }
.modal #m-ingr   { min-height: 140px; }
.modal #m-method { min-height: 180px; }
.modal-footer { display: flex; gap: 12px; align-items: center; margin-top: 20px;
                padding-top: 16px; border-top: 1px solid #f0e8e0; }
.btn-create { background: #c05f2a; color: white; border: none; font-size: 14px;
              font-weight: 700; padding: 11px 28px; border-radius: 20px; cursor: pointer; }
.btn-create:hover { background: #a04e22; }
.btn-create:disabled { background: #c0a090; cursor: default; }
.btn-cancel { background: none; border: 1.5px solid #d0c0b0; color: #7a6a5a;
              font-size: 14px; padding: 10px 20px; border-radius: 20px; cursor: pointer; }
.btn-cancel:hover { border-color: #c05f2a; color: #c05f2a; }
.modal-err { color: #c03030; font-size: 13px; }
.slug-preview { font-size: 11px; color: #a09080; margin-top: 4px; font-family: monospace; }
</style>
</head>
<body>

<div class="sidebar">
  <div class="sidebar-head">
    <h1>📖 My Recipes</h1>
    <input class="search" type="text" placeholder="Search..." oninput="filterList(this.value)">
  </div>
  <button class="btn-new" onclick="openNewModal()">+ New Recipe</button>
  <div class="recipe-list" id="recipe-list"></div>
</div>

<!-- ── New Recipe Modal ── -->
<div class="modal-backdrop" id="new-modal" onclick="closeNewModalOnBackdrop(event)">
  <div class="modal">
    <h2>✍️ New Recipe</h2>

    <div class="field">
      <label>Title <span style="color:#c05f2a">*</span></label>
      <input type="text" id="m-title" placeholder="e.g. Tomato soup"
             oninput="suggestSlug(this.value)">
    </div>

    <div class="field">
      <label>Filename (slug) <span style="color:#c05f2a">*</span></label>
      <input type="text" id="m-slug" placeholder="e.g. iyul-tomato-soup">
      <div class="hint">Lowercase letters, digits and hyphens only. No spaces.</div>
      <div class="slug-preview" id="slug-preview"></div>
    </div>

    <div class="row2">
      <div class="field">
        <label>Category</label>
        <input type="text" id="m-category" placeholder="e.g. Salads">
      </div>
      <div class="field">
        <label>Tags</label>
        <input type="text" id="m-tags" placeholder="e.g. PraCooking, июль">
      </div>
    </div>

    <div class="row2">
      <div class="field">
        <label>Servings</label>
        <input type="text" id="m-servings" placeholder="e.g. 4">
      </div>
      <div class="field">
        <label>Source</label>
        <input type="text" id="m-source" placeholder="Book / URL / name">
      </div>
    </div>

    <div class="row2">
      <div class="field">
        <label>Active Time</label>
        <input type="text" id="m-active-time" placeholder="e.g. 20 мин">
      </div>
      <div class="field">
        <label>Total Time</label>
        <input type="text" id="m-total-time" placeholder="e.g. 1 час">
      </div>
    </div>

    <div class="field">
      <label>Description</label>
      <textarea id="m-desc" placeholder="A few words about this dish..."></textarea>
    </div>

    <div class="field">
      <label>Ingredients</label>
      <textarea id="m-ingr" placeholder="1 onion&#10;2 cloves garlic&#10;..."></textarea>
    </div>

    <div class="field">
      <label>Method</label>
      <textarea id="m-method" placeholder="1. Preheat oven...&#10;2. ..."></textarea>
    </div>

    <div class="modal-footer">
      <button class="btn-create" id="btn-create" onclick="submitNewRecipe()">Create Recipe</button>
      <button class="btn-cancel" onclick="closeNewModal()">Cancel</button>
      <span class="modal-err" id="modal-err"></span>
    </div>
  </div>
</div>

<div class="main">
  <div class="empty-state" id="empty-state">
    <div class="icon">🥘</div>
    <p>Select a recipe on the left</p>
  </div>

  <div class="form-wrap" id="form-wrap" style="display:none">
    <div class="form-title" id="form-title"></div>

    <div class="tabs">
      <div class="tab active" onclick="switchTab('notes')">Notes</div>
      <div class="tab" onclick="switchTab('recipe')">Recipe</div>
    </div>

    <!-- ── TAB: Notes ── -->
    <div class="tab-panel active" id="tab-notes">

      <div class="field">
        <label>Rating</label>
        <div class="stars">
          <span class="star" onclick="setRating(1)">★</span>
          <span class="star" onclick="setRating(2)">★</span>
          <span class="star" onclick="setRating(3)">★</span>
          <span class="star" onclick="setRating(4)">★</span>
          <span class="star" onclick="setRating(5)">★</span>
          <span class="clear-rating" onclick="setRating(0)">clear</span>
        </div>
      </div>

      <div class="field">
        <label>When I cooked it</label>
        <div class="cooked-list" id="cooked-list"></div>
        <button class="btn-add" onclick="addCookedRow('')">+ Add date</button>
      </div>

      <div class="field">
        <label>My notes</label>
        <textarea id="notes-input" placeholder="Impressions, changes to the recipe..."></textarea>
      </div>

      <div class="field">
        <label>My photo of the dish</label>
        <div class="photo-section">
          <div class="photo-preview" id="photo-preview">
            <span class="no-photo">📷</span>
          </div>
          <div class="photo-btns">
            <button class="btn-upload" onclick="document.getElementById('photo-file').click()">
              Upload photo
            </button>
            <button class="btn-clear-photo" id="btn-clear-photo" onclick="clearPhoto()"
                    style="display:none">Remove photo</button>
            <div class="photo-name" id="photo-name"></div>
          </div>
        </div>
        <input type="file" id="photo-file" accept="image/*" onchange="uploadPhoto(this)">
      </div>

      <div class="save-row">
        <button class="btn-save" id="btn-save-notes" onclick="saveNotes()">Save</button>
        <span class="save-ok" id="save-ok-notes">✓ Saved</span>
      </div>
    </div>

    <!-- ── TAB: Recipe ── -->
    <div class="tab-panel" id="tab-recipe">
      <div class="edit-warning">
        ✏️ You can edit the recipe text here. The HTML will update automatically after saving.
      </div>

      <div class="field">
        <label>Description</label>
        <textarea id="desc-input" placeholder="Introduction text..."></textarea>
      </div>

      <div class="field">
        <label>Ingredients</label>
        <textarea id="ingr-input" placeholder="List of ingredients..."></textarea>
      </div>

      <div class="field">
        <label>Method</label>
        <textarea id="method-input" placeholder="Preparation steps..."></textarea>
      </div>

      <div class="save-row">
        <button class="btn-save" id="btn-save-recipe" onclick="saveRecipeBody()">Save</button>
        <span class="save-ok" id="save-ok-recipe">✓ Saved</span>
      </div>
    </div>

  </div>
</div>

<script>
let allRecipes = [];
let currentSlug = null;
let currentRating = 0;
let currentMyPhoto = "";
let currentTab = 'notes';

async function loadList() {
  const r = await fetch('/api/recipes');
  allRecipes = await r.json();
  renderList(allRecipes);
}

function renderList(items) {
  document.getElementById('recipe-list').innerHTML = items.map(r =>
    `<div class="recipe-item${r.slug === currentSlug ? ' active' : ''}"
          onclick="selectRecipe('${r.slug}')">${esc(r.title)}</div>`
  ).join('');
}

function filterList(q) {
  const lq = q.toLowerCase();
  renderList(allRecipes.filter(r => r.title.toLowerCase().includes(lq)));
}

async function selectRecipe(slug) {
  currentSlug = slug;
  renderList(allRecipes.filter(r =>
    r.title.toLowerCase().includes(document.querySelector('.search').value.toLowerCase())
  ));
  const r = await fetch('/api/recipe/' + slug);
  const data = await r.json();
  document.getElementById('form-title').textContent = data.title;
  document.getElementById('empty-state').style.display = 'none';
  document.getElementById('form-wrap').style.display = '';

  // Fill notes tab
  setRating(starsToNum(data.rating));
  document.getElementById('cooked-list').innerHTML = '';
  (data.cooked || []).forEach(c => addCookedRow(c));
  document.getElementById('notes-input').value = data.my_notes || '';
  currentMyPhoto = data.my_photo || '';
  renderPhotoPreview();
  document.getElementById('save-ok-notes').classList.remove('show');

  // Fill recipe tab (lazy: only if tab is active or pre-load now)
  loadBodyData(slug);
  document.getElementById('save-ok-recipe').classList.remove('show');
}

async function loadBodyData(slug) {
  const r = await fetch('/api/body/' + slug);
  const data = await r.json();
  document.getElementById('desc-input').value   = data.description  || '';
  document.getElementById('ingr-input').value   = data.ingredients  || '';
  document.getElementById('method-input').value = data.method       || '';
}

// ── tabs ───────────────────────────────────────────────────────────────────
function switchTab(name) {
  currentTab = name;
  document.querySelectorAll('.tab').forEach((t, i) => {
    const names = ['notes', 'recipe'];
    t.classList.toggle('active', names[i] === name);
  });
  document.getElementById('tab-notes').classList.toggle('active', name === 'notes');
  document.getElementById('tab-recipe').classList.toggle('active', name === 'recipe');
}

// ── rating ────────────────────────────────────────────────────────────────
function setRating(n) {
  currentRating = n;
  document.querySelectorAll('.star').forEach((s, i) => {
    s.classList.toggle('on', i < n);
  });
}
function starsToNum(s) { return (s || '').split('').filter(c => c === '★').length; }
function numToStars(n) { return '★'.repeat(n); }

// ── cooked ─────────────────────────────────────────────────────────────────
function addCookedRow(value) {
  const list = document.getElementById('cooked-list');
  const row = document.createElement('div');
  row.className = 'cooked-row';
  row.innerHTML =
    `<input class="cooked-input" type="text" value="${esc(value)}"
            placeholder="e.g. 15.03.2026 — delicious!">
     <button class="btn-del" onclick="this.parentElement.remove()" title="Remove">×</button>`;
  list.appendChild(row);
  if (!value) row.querySelector('input').focus();
}

// ── photo ──────────────────────────────────────────────────────────────────
function uploadPhoto(input) {
  const file = input.files[0];
  if (!file || !currentSlug) return;
  const reader = new FileReader();
  reader.onload = async (e) => {
    const b64 = e.target.result.split(',')[1];
    const r = await fetch('/api/photo/' + currentSlug, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({filename: file.name, data: b64})
    });
    const data = await r.json();
    currentMyPhoto = data.path;
    renderPhotoPreview();
  };
  reader.readAsDataURL(file);
  input.value = '';
}

function clearPhoto() {
  currentMyPhoto = '';
  renderPhotoPreview();
}

function renderPhotoPreview() {
  const preview = document.getElementById('photo-preview');
  const btn = document.getElementById('btn-clear-photo');
  const name = document.getElementById('photo-name');
  if (currentMyPhoto) {
    const src = '/img/' + currentMyPhoto.replace('images/', '');
    preview.innerHTML = `<img src="${src}" onerror="this.parentElement.innerHTML='<span class=\\'no-photo\\'>📷</span>'">`;
    btn.style.display = '';
    name.textContent = currentMyPhoto.split('/').pop();
  } else {
    preview.innerHTML = '<span class="no-photo">📷</span>';
    btn.style.display = 'none';
    name.textContent = '';
  }
}

// ── save notes ─────────────────────────────────────────────────────────────
async function saveNotes() {
  if (!currentSlug) return;
  const btn = document.getElementById('btn-save-notes');
  btn.disabled = true; btn.textContent = 'Saving...';
  const cooked = [...document.querySelectorAll('.cooked-input')]
    .map(i => i.value.trim()).filter(Boolean);
  await fetch('/api/update/' + currentSlug, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      rating: numToStars(currentRating),
      cooked,
      my_notes: document.getElementById('notes-input').value,
      my_photo: currentMyPhoto,
    }),
  });
  btn.disabled = false; btn.textContent = 'Save';
  const ok = document.getElementById('save-ok-notes');
  ok.classList.add('show');
  setTimeout(() => ok.classList.remove('show'), 2500);
}

// ── save recipe body ────────────────────────────────────────────────────────
async function saveRecipeBody() {
  if (!currentSlug) return;
  const btn = document.getElementById('btn-save-recipe');
  btn.disabled = true; btn.textContent = 'Saving...';
  await fetch('/api/update-body/' + currentSlug, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      description: document.getElementById('desc-input').value,
      ingredients: document.getElementById('ingr-input').value,
      method:      document.getElementById('method-input').value,
    }),
  });
  btn.disabled = false; btn.textContent = 'Save';
  const ok = document.getElementById('save-ok-recipe');
  ok.classList.add('show');
  setTimeout(() => ok.classList.remove('show'), 2500);
}

function esc(s) {
  return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── new recipe modal ────────────────────────────────────────────────────────
function openNewModal() {
  // clear all fields
  ['m-title','m-slug','m-category','m-tags','m-servings','m-source',
   'm-active-time','m-total-time','m-desc','m-ingr','m-method'].forEach(id => {
    const el = document.getElementById(id);
    el.value = '';
  });
  document.getElementById('modal-err').textContent = '';
  document.getElementById('slug-preview').textContent = '';
  document.getElementById('new-modal').classList.add('open');
  setTimeout(() => document.getElementById('m-title').focus(), 50);
}

function closeNewModal() {
  document.getElementById('new-modal').classList.remove('open');
}

function closeNewModalOnBackdrop(e) {
  if (e.target === document.getElementById('new-modal')) closeNewModal();
}

function suggestSlug(title) {
  // Auto-fill slug from title if user hasn't typed in slug manually
  const slugInput = document.getElementById('m-slug');
  const preview = document.getElementById('slug-preview');
  // Only auto-suggest if slug field is empty or was previously auto-suggested
  if (slugInput.dataset.manual === 'yes') return;
  const slug = title.toLowerCase()
    .replace(/[^\w\s\-]/g, '')   // remove special chars
    .replace(/\s+/g, '-')         // spaces to hyphens
    .replace(/-+/g, '-')          // collapse hyphens
    .replace(/^-|-$/g, '');       // trim hyphens
  slugInput.value = slug;
  preview.textContent = slug ? slug + '.txt' : '';
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('m-slug').addEventListener('input', function() {
    this.dataset.manual = this.value ? 'yes' : '';
    const preview = document.getElementById('slug-preview');
    preview.textContent = this.value ? this.value + '.txt' : '';
  });
});

async function submitNewRecipe() {
  const slug  = document.getElementById('m-slug').value.trim();
  const title = document.getElementById('m-title').value.trim();
  const errEl = document.getElementById('modal-err');
  errEl.textContent = '';

  if (!title) { errEl.textContent = 'Title is required.'; return; }
  if (!slug)  { errEl.textContent = 'Filename is required.'; return; }

  const btn = document.getElementById('btn-create');
  btn.disabled = true; btn.textContent = 'Creating...';

  const resp = await fetch('/api/create-recipe', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      slug,
      title,
      category:    document.getElementById('m-category').value.trim(),
      tags:        document.getElementById('m-tags').value.trim(),
      servings:    document.getElementById('m-servings').value.trim(),
      active_time: document.getElementById('m-active-time').value.trim(),
      total_time:  document.getElementById('m-total-time').value.trim(),
      source:      document.getElementById('m-source').value.trim(),
      description: document.getElementById('m-desc').value,
      ingredients: document.getElementById('m-ingr').value,
      method:      document.getElementById('m-method').value,
    }),
  });

  btn.disabled = false; btn.textContent = 'Create Recipe';

  const data = await resp.json();
  if (data.error) {
    errEl.textContent = data.error;
    return;
  }

  closeNewModal();
  await loadList();
  selectRecipe(slug);
}

loadList();
</script>
</body>
</html>"""


# ─── run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    open_browser = "--no-browser" not in sys.argv
    server = HTTPServer(("", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"✓ Editor running: {url}")
    print("  Ctrl+C to stop")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
