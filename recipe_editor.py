#!/usr/bin/env python3
"""
Редактор личных заметок к рецептам.
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

    gen = os.path.join(RECIPES_DIR, "generate_recipe_html.py")
    subprocess.run(["python3", gen, path], capture_output=True)


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

        elif path.startswith("/api/photo/"):
            slug = path[len("/api/photo/"):]
            body = self.read_json()
            ext = os.path.splitext(body.get("filename", "photo.jpg"))[1].lower() or ".jpg"
            filename = f"my-{slug}{ext}"
            filepath = os.path.join(IMAGES_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(base64.b64decode(body["data"]))
            self.send_json({"path": f"images/{filename}"})

        else:
            self.send_response(404); self.end_headers()


# ─── HTML ─────────────────────────────────────────────────────────────────────

HTML_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Мои рецепты — заметки</title>
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

.form-wrap { max-width: 600px; }
.form-title { font-size: 22px; font-weight: 700; color: #1a1714; margin-bottom: 24px;
              padding-bottom: 12px; border-bottom: 2px solid #f0e8e0; }

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

/* Notes */
textarea { width: 100%; min-height: 120px; padding: 12px; border: 1.5px solid #e0cfc0;
           border-radius: 10px; font-size: 14px; line-height: 1.6;
           font-family: inherit; outline: none; resize: vertical; background: #fffef5; }
textarea:focus { border-color: #c05f2a; }

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
</style>
</head>
<body>

<div class="sidebar">
  <div class="sidebar-head">
    <h1>📖 Мои рецепты</h1>
    <input class="search" type="text" placeholder="Поиск..." oninput="filterList(this.value)">
  </div>
  <div class="recipe-list" id="recipe-list"></div>
</div>

<div class="main">
  <div class="empty-state" id="empty-state">
    <div class="icon">🥘</div>
    <p>Выбери рецепт слева</p>
  </div>

  <div class="form-wrap" id="form-wrap" style="display:none">
    <div class="form-title" id="form-title"></div>

    <div class="field">
      <label>Оценка</label>
      <div class="stars">
        <span class="star" onclick="setRating(1)">★</span>
        <span class="star" onclick="setRating(2)">★</span>
        <span class="star" onclick="setRating(3)">★</span>
        <span class="star" onclick="setRating(4)">★</span>
        <span class="star" onclick="setRating(5)">★</span>
        <span class="clear-rating" onclick="setRating(0)">убрать</span>
      </div>
    </div>

    <div class="field">
      <label>Когда готовила</label>
      <div class="cooked-list" id="cooked-list"></div>
      <button class="btn-add" onclick="addCookedRow('')">+ Добавить дату</button>
    </div>

    <div class="field">
      <label>Мои заметки</label>
      <textarea id="notes-input" placeholder="Впечатления, изменения в рецепте..."></textarea>
    </div>

    <div class="field">
      <label>Моё фото готового блюда</label>
      <div class="photo-section">
        <div class="photo-preview" id="photo-preview">
          <span class="no-photo">📷</span>
        </div>
        <div class="photo-btns">
          <button class="btn-upload" onclick="document.getElementById('photo-file').click()">
            Загрузить фото
          </button>
          <button class="btn-clear-photo" id="btn-clear-photo" onclick="clearPhoto()"
                  style="display:none">Удалить фото</button>
          <div class="photo-name" id="photo-name"></div>
        </div>
      </div>
      <input type="file" id="photo-file" accept="image/*" onchange="uploadPhoto(this)">
    </div>

    <div class="save-row">
      <button class="btn-save" id="btn-save" onclick="saveRecipe()">Сохранить</button>
      <span class="save-ok" id="save-ok">✓ Сохранено</span>
    </div>
  </div>
</div>

<script>
let allRecipes = [];
let currentSlug = null;
let currentRating = 0;
let currentMyPhoto = "";

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
  setRating(starsToNum(data.rating));
  document.getElementById('cooked-list').innerHTML = '';
  (data.cooked || []).forEach(c => addCookedRow(c));
  document.getElementById('notes-input').value = data.my_notes || '';
  currentMyPhoto = data.my_photo || '';
  renderPhotoPreview();
  document.getElementById('save-ok').classList.remove('show');
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
            placeholder="напр. 15.03.2026 — очень вкусно!">
     <button class="btn-del" onclick="this.parentElement.remove()" title="Удалить">×</button>`;
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

// ── save ───────────────────────────────────────────────────────────────────
async function saveRecipe() {
  if (!currentSlug) return;
  const btn = document.getElementById('btn-save');
  btn.disabled = true;
  btn.textContent = 'Сохраняю...';
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
  btn.disabled = false;
  btn.textContent = 'Сохранить';
  const ok = document.getElementById('save-ok');
  ok.classList.add('show');
  setTimeout(() => ok.classList.remove('show'), 2500);
}

function esc(s) {
  return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

loadList();
</script>
</body>
</html>"""


# ─── run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    server = HTTPServer(("", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"✓ Редактор запущен: {url}")
    print("  Ctrl+C для остановки")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлен.")
