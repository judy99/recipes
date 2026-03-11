# Моя кулинарная библиотека — как пользоваться

## Открыть каталог

Открой файл **cookbook.html** в браузере.
Там 145 рецептов с поиском по ингредиентам и фильтрами по типу.

### Поиск

- Одно слово: `тыква` — найдёт всё с тыквой
- Несколько слов через пробел: `тыква суп` — найдёт только там, где есть оба слова
- Через запятую: `тыква, pumpkin` — найдёт либо тыква, либо pumpkin (ИЛИ)
- Комбинация: `тыква суп, pumpkin soup` — (тыква И суп) ИЛИ (pumpkin И soup)

### Рейтинги

- `new` — ещё не готовила
- `would make again ✓` — понравилось
- `meh` — так себе
- `favorite ♥` — любимый

---

## Добавить новый рецепт

### Через чат (основной способ)

1. Открой Cowork
2. Напиши:
   «Помоги с проектом рецептов, папка: /Users/lia/Library/CloudStorage/GoogleDrive-julia.kurianova@gmail.com/My Drive/cooking»
3. Скинь рецепт текстом — в любом формате, на любом языке
4. Claude создаст файл, сгенерирует HTML и обновит каталог

### С телефона или iPad

1. Сохрани рецепт в Apple Notes
2. Когда будешь за Mac — открой Cowork
3. Напиши: «Помоги с проектом рецептов, папка: /Users/lia/Library/CloudStorage/GoogleDrive-julia.kurianova@gmail.com/My Drive/cooking»
4. Скинь рецепт из Notes в чат — Claude добавит его в каталог

### Вручную добавляешь или обновляешь рецепт

1. Создай `.txt` файл в папке `my-recipes/` по шаблону ниже
2. В Терминале перейди в папку и запусти скрипт:

```bash
cd ~/Library/CloudStorage/GoogleDrive-julia.kurianova@gmail.com/My\ Drive/cooking/recipes

python3 update-catalog.py
```

---

## Шаблон рецепта (.txt)

```
Title: Recipe name
Category: category
Rating: new

Ingredients:
amount ingredient
...

Instructions:

1. Step one
2. Step two
   ...

Tips:

- tips from the recipe

My Notes:

- my personal notes after cooking
```

Писать **е** вместо **ё**. Не переводить рецепты.

---

## Добавить фото к рецепту

Положи фото в папку `my-recipes/photo/`
Назови файл точно как рецепт: `Оладушки.jpg`
Фото появится на странице рецепта автоматически.

---

## Хранение и доступ с других устройств

Папку с рецептами (~1.5 ГБ без видео) положи в **Google Drive** —
тогда каталог и все рецепты будут доступны с любого устройства.

Видео курса PraCooking (папки 03-Нарезка, 04-Технологии) — 70 ГБ —
лучше оставить локально или убрать в архив если уже просмотрено.

---

## Добавить ссылку на сайт с рецептами

Скажи мне в чате: «Добавь сайт» и дай ссылку + краткое описание.
Я обновлю файл `links.json` — ссылка сразу появится во вкладке **Sites** каталога.
Запускать `update-catalog.py` не нужно.

Формат в `links.json`:
```json
{
  "name": "Название сайта",
  "url": "https://...",
  "description": "Краткое описание",
  "tags": ["tag1", "tag2"]
}
```

---

## Структура папки

```
recipes/
├── cookbook.html              ← открывать в браузере
├── catalog.json               ← база данных
├── update-catalog.py          ← запустить после добавления рецептов
├── generate_recipe_html.py    ← генерирует HTML из .txt
├── PROJECT.md                 ← инструкция для Claude
├── README.md                  ← этот файл
├── links.json                 ← ссылки на сайты с рецептами
│
├── my-recipes/                ← 10 личных рецептов
│   ├── *.txt                  ← исходники
│   ├── *.html                 ← красивые страницы
│   └── photo/                 ← фото блюд
│
├── PraCooking/                ← карточки по продуктам (PDF)
├── PraCooking-BASE-COURSE/    ← базовый курс (PDF)
└── RECEPIES_PraCooking/       ← сборники рецептов (PDF)
```

---

## my-recipes сейчас

1. Lentil Bread
2. Lentil Bread with Vegetables
3. Vegan Lentil Dinner Rolls
4. Заварные булочки
5. Заливной пирог с капустой ✓
6. Капустный пирог (Ольга Брейн)
7. Оладушки ✓
8. Пирог киш ✓
9. Пицца
10. Пшенная каша
