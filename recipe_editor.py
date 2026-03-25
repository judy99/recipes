#!/usr/bin/env python3
"""
Редактор личных заметок к рецептам.
Запуск: python3 recipe_editor.py
Затем открыть: http://localhost:5050
"""
import os
import re
import json
import subprocess
import mimetypes
import tornado.ioloop
import tornado.web

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

    # My Notes: remove existing section, append at end
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


# ─── handlers ────────────────────────────────────────────────────────────────

class RecipesHandler(tornado.web.RequestHandler):
    def get(self):
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(list_recipes(), ensure_ascii=False))


class RecipeHandler(tornado.web.RequestHandler):
    def get(self, slug):
        data = read_personal_data(slug)
        if data is None:
            self.set_status(404)
            return
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(data, ensure_ascii=False))


class UpdateHandler(tornado.web.RequestHandler):
    def post(self, slug):
        body = json.loads(self.request.body)
        write_personal_data(
            slug,
            rating=body.get("rating", ""),
            cooked_entries=body.get("cooked", []),
            my_notes=body.get("my_notes", ""),
            my_photo=body.get("my_photo", ""),
        )
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({"ok": True}))


class PhotoHandler(tornado.web.RequestHandler):
    def post(self, slug):
        if not self.request.files.get("photo"):
            self.set_status(400)
            return
        file_info = self.request.files["photo"][0]
        ext = os.path.splitext(file_info["filename"])[1].lower() or ".jpg"
        filename = f"my-{slug}{ext}"
        filepath = os.path.join(IMAGES_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(file_info["body"])
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({"path": f"images/{filename}"}))


class ImageHandler(tornado.web.RequestHandler):
    def get(self, filename):
        filepath = os.path.join(IMAGES_DIR, filename)
        if not os.path.exists(filepath):
            self.set_status(404)
            return
        mime = mimetypes.guess_type(filepath)[0] or "image/jpeg"
        self.set_header("Content-Type", mime)
        with open(filepath, "rb") as f:
            self.write(f.read())


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.set_header("Content-Type", "text/html; charset=utf-8")
        self.write(HTML_PAGE)


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
.recipe-count { font-size: 12px; color: #b0a090; margin-top: 4px; }

/* ── Main panel ── */
.main { flex: 1; overflow-y: auto; padding: 32px; }
.empty-state { display: flex; flex-direction: column; align-items: center;
               justify-content: center; height: 60%; color: #c0a898; }
.empty-state .icon { font-size: 48px; margin-bottom: 12px; }
.empty-state p { font-size: 15px; }

.form-wrap { max-width: 600px; }
.form-title { font-size: 22px; font-weight: 700; color: #1a1714; margin-bottom: 24px;
              padding-bottom: 12px; border-bottom: 2px solid #f0e8e0; }

.field { margin-bottom: 24px; }
.field label { display: block; font-size: 12px; font-weight: 700;
               text-transform: uppercase; letter-spacing: 0.6px;
               color: #7a4f2a; margin-bottom: 8px; }

/* Stars */
.stars { display: flex; gap: 6px; }
.star { font-size: 28px; cursor: pointer; color: #d8cfc4; transition: color 0.1s; line-height: 1; }
.star.on { color: #f0a020; }
.star:hover { color: #f0a020; }

/* Cooked list */
.cooked-list { display: flex; flex-direction: column; gap: 6px; }
.cooked-row { display: flex; gap: 8px; align-items: center; }
.cooked-input { flex: 1; padding: 8px 12px; border: 1.5px solid #e0cfc0;
                border-radius: 8px; font-size: 14px; outline: none; background: white; }
.cooked-input:focus { border-color: #c05f2a; }
.btn-del { background: none; border: none; cursor: pointer; color: #c0a0a0;
           font-size: 18px; padding: 4px; line-height: 1; }
.btn-del:hover { color: #c03030; }
.btn-add { margin-top: 6px; background: none; border: 1.5px dashed #d0c0b0;
           color: #8a6a4a; font-size: 13px; padding: 6px 14px;
           border-radius: 20px; cursor: pointer; }
.btn-add:hover { border-color: #c05f2a; color: #c05f2a; }

/* Notes textarea */
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
.photo-preview .no-photo { font-size: 28px; }
.photo-btns { display: flex; flex-direction: column; gap: 8px; }
.btn-upload { background: #f5ede4; color: #7a4f2a; border: none; font-size: 13px;
              font-weight: 600; padding: 8px 16px; border-radius: 20px;
              cursor: pointer; }
.btn-upload:hover { background: #f0dfd0; }
.btn-clear-photo { background: none; border: none; color: #b09080; font-size: 13px;
                   cursor: pointer; padding: 4px 0; text-decoration: underline; }
.photo-filename { font-size: 12px; color: #a09080; margin-top: 4px; }
#photo-file { display: none; }

/* Save */
.save-row { display: flex; align-items: center; gap: 14px; margin-top: 8px; }
.btn-save { background: #c05f2a; color: white; border: none; font-size: 15px;
            font-weight: 700; padding: 12px 32px; border-radius: 24px;
            cursor: pointer; }
.btn-save:hover { background: #a04e22; }
.btn-save:disabled { background: #c0a090; cursor: default; }
.save-ok { color: #5a9a5a; font-size: 14px; font-weight: 600; opacity: 0;
           transition: opacity 0.4s; }
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

<div class="main" id="main">
  <div class="empty-state" id="empty-state">
    <div class="icon">🥘</div>
    <p>Выбери рецепт слева</p>
  </div>
  <div class="form-wrap" id="form-wrap" style="display:none">
    <div class="form-title" id="form-title"></div>

    <div class="field">
      <label>Оценка</label>
      <div class="stars" id="stars">
        <span class="star" data-n="1" onclick="setRating(1)">★</span>
        <span class="star" data-n="2" onclick="setRating(2)">★</span>
        <span class="star" data-n="3" onclick="setRating(3)">★</span>
        <span class="star" data-n="4" onclick="setRating(4)">★</span>
        <span class="star" data-n="5" onclick="setRating(5)">★</span>
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
          <button class="btn-clear-photo" id="btn-clear-photo" onclick="clearPhoto()" style="display:none">
            Удалить фото
          </button>
          <div class="photo-filename" id="photo-filename"></div>
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

// ── load recipe list ──────────────────────────────────────────────────────
async function loadList() {
  const r = await fetch('/api/recipes');
  allRecipes = await r.json();
  renderList(allRecipes);
}

function renderList(items) {
  const el = document.getElementById('recipe-list');
  el.innerHTML = items.map(r =>
    `<div class="recipe-item${r.slug === currentSlug ? ' active' : ''}"
          onclick="selectRecipe('${r.slug}', ${JSON.stringify(r.title)})">${r.title}</div>`
  ).join('');
}

function filterList(q) {
  const lq = q.toLowerCase();
  renderList(allRecipes.filter(r => r.title.toLowerCase().includes(lq)));
}

// ── select recipe ─────────────────────────────────────────────────────────
async function selectRecipe(slug, title) {
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
  hideSaveOk();
}

// ── rating ────────────────────────────────────────────────────────────────
function setRating(n) {
  currentRating = n;
  document.querySelectorAll('.star').forEach(s => {
    s.classList.toggle('on', parseInt(s.dataset.n) <= n);
  });
}

function starsToNum(rating) {
  return (rating || '').split('').filter(c => c === '★').length;
}

function numToStars(n) {
  return '★'.repeat(n);
}

// ── cooked list ───────────────────────────────────────────────────────────
function addCookedRow(value) {
  const list = document.getElementById('cooked-list');
  const row = document.createElement('div');
  row.className = 'cooked-row';
  row.innerHTML = `
    <input class="cooked-input" type="text" value="${escHtml(value)}"
           placeholder="напр. 15.03.2026 — очень вкусно!">
    <button class="btn-del" onclick="this.parentElement.remove()">✕</button>`;
  list.appendChild(row);
  row.querySelector('input').focus();
}

// ── photo ─────────────────────────────────────────────────────────────────
async function uploadPhoto(input) {
  if (!input.files[0] || !currentSlug) return;
  const fd = new FormData();
  fd.append('photo', input.files[0]);
  const r = await fetch('/api/photo/' + currentSlug, {method: 'POST', body: fd});
  const data = await r.json();
  currentMyPhoto = data.path;
  renderPhotoPreview();
  input.value = '';
}

function clearPhoto() {
  currentMyPhoto = '';
  renderPhotoPreview();
}

function renderPhotoPreview() {
  const preview = document.getElementById('photo-preview');
  const btn = document.getElementById('btn-clear-photo');
  const fname = document.getElementById('photo-filename');
  if (currentMyPhoto) {
    preview.innerHTML = `<img src="/img/${currentMyPhoto.replace('images/', '')}" onerror="this.style.display='none'">`;
    btn.style.display = '';
    fname.textContent = currentMyPhoto.split('/').pop();
  } else {
    preview.innerHTML = '<span class="no-photo">📷</span>';
    btn.style.display = 'none';
    fname.textContent = '';
  }
}

// ── save ──────────────────────────────────────────────────────────────────
async function saveRecipe() {
  if (!currentSlug) return;
  const btn = document.getElementById('btn-save');
  btn.disabled = true;
  btn.textContent = 'Сохраняю...';
  const cooked = [...document.querySelectorAll('.cooked-input')]
    .map(i => i.value.trim()).filter(Boolean);
  const body = {
    rating: numToStars(currentRating),
    cooked,
    my_notes: document.getElementById('notes-input').value,
    my_photo: currentMyPhoto,
  };
  await fetch('/api/update/' + currentSlug, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  btn.disabled = false;
  btn.textContent = 'Сохранить';
  showSaveOk();
}

function showSaveOk() {
  const el = document.getElementById('save-ok');
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 2500);
}
function hideSaveOk() {
  document.getElementById('save-ok').classList.remove('show');
}

function escHtml(s) {
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

loadList();
</script>
</body>
</html>"""


# ─── app ──────────────────────────────────────────────────────────────────────

def make_app():
    return tornado.web.Application([
        (r"/", MainHandler),
        (r"/api/recipes", RecipesHandler),
        (r"/api/recipe/(.+)", RecipeHandler),
        (r"/api/update/(.+)", UpdateHandler),
        (r"/api/photo/(.+)", PhotoHandler),
        (r"/img/(.+)", ImageHandler),
    ])


if __name__ == "__main__":
    app = make_app()
    app.listen(PORT)
    print(f"✓ Редактор запущен: http://localhost:{PORT}")
    print("  Ctrl+C для остановки")
    tornado.ioloop.IOLoop.current().start()
