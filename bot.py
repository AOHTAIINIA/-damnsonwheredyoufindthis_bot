import asyncio
import json
import os
import re
import socket
import uuid
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile
)

load_dotenv()

# =====================================================================
# ⚙️ 1. КОНФИГУРАЦИЯ ХОСТИНГА BOTHOST.RU И БАЗЫ ДАННЫХ (/app/data)
# =====================================================================
DATA_DIR = os.getenv("DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)
DB_FILE = os.path.join(DATA_DIR, "hq_database.json")


def get_host_token() -> str:
    for env_key in ("BOT_TOKEN", "TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN"):
        val = os.getenv(env_key)
        if val and ":" in val:
            return val.strip()
    for k, v in os.environ.items():
        if isinstance(v, str) and re.match(r"^\d{8,12}:[A-Za-z0-9_-]{30,40}$", v.strip()):
            return v.strip()
    raise RuntimeError(
        "❌ Токен не найден! Вставь новый токен от @BotFather в поле 'Bot Token' на сайте Bothost.ru"
    )


dp = Dispatcher()
bot: Bot = None

# Стартовые шаблоны (загружаются в базу только при первом запуске, дальше всё редактируется из бота)
DEFAULT_PROMPTS = {
    "method": {
        "title": "📘 Методичка (90 мин)",
        "text": (
            "Ты — главный методист курса геймдизайна в Roblox Studio для детей 8–14 лет.\n"
            "Напиши ПОЛНОЕ МЕТОДИЧЕСКОЕ РУКОВОДСТВО (90 минут), включая:\n"
            "1. Повторение прошлого урока (5 мин) и деконструкцию геймдизайна.\n"
            "2. Пошаговую 3D-сборку в Studio и точную схему визуальных блоков Latch / кода Luau.\n"
            "3. Разминку (5 мин) в середине урока вдали от ПК.\n"
            "4. Таблицу частых ошибок учеников и способов их быстрого решения.\n"
            "5. Завершение урока (5 мин): вопросы рефлексии, начисление баллов в «Банк робаксов», сохранение файла .rbxl и анонс."
        )
    },
    "pres": {
        "title": "🖥 Презентация (10 слайдов)",
        "text": (
            "Ты — арт-директор детского курса по геймдизайну (8–14 лет).\n"
            "Создай ПЛАН ПРЕЗЕНТАЦИИ НА 10 СЛАЙДОВ (Dark Mode #121214, неоновые акценты).\n"
            "Для каждого слайда распиши: Надзаголовок, Заголовок, Карточки шагов, Визуал, Реплику спикера и Интерактив."
        )
    },
    "raw_lesson": {
        "title": "🧩 Техническая практика",
        "text": (
            "Ты — технический разработчик курса Roblox Studio.\n"
            "Напиши ПОЛНЫЙ ПРАКТИЧЕСКИЙ РАЗБОР УРОКА без методической воды:\n"
            "1. Какие объекты создать в Explorer.\n"
            "2. Пошаговая 3D-постройка и свойства в Properties.\n"
            "3. Точная сборка блоков в Latch по категориям и проверочный код Luau (--!strict).\n"
            "4. Разбор возможных багов при тестировании."
        )
    },
    "hw": {
        "title": "🎮 Домашний квест (ДЗ)",
        "text": (
            "Придумай увлекательное ДОМАШНЕЕ ЗАДАНИЕ (Домашний квест на 20–30 минут) для учеников 8–14 лет по теме урока.\n"
            "Включи: Легенду задания, 3 уровня сложности (Базовый билд, Геймдизайн-тест, Бонус-уровень на +30 робаксов) и инструкцию по сдаче."
        )
    }
}

STARTER_TYCOON_SCRIPTS = [
    {
        "id": "tyc_claim",
        "title": "🟢 Захват базы (ClaimPad)",
        "desc": "Проверяет Humanoid, записывает владельца в переменную owner, обновляет вывеску и прячет кнопку.",
        "latch": (
            "1. Variables (вверху): make [owner] = [nil]\n"
            "2. Events: when [part] is touched by [hit]\n"
            "3. Variables: make [human] = in [hit.Parent] find [\"Humanoid\"]\n"
            "4. Control: if [human] ~= [nil] then -> if [owner] == [nil] then\n"
            "5. Variables: set [owner] to [hit.Parent.Name]\n"
            "6. Instances: set [Столб.BillboardGui.TextLabel].[Text] to [\"БАЗА: \" join owner]\n"
            "7. Instances: set [Кнопка].[Transparency] = 1, [CanCollide] = false"
        ),
        "luau": (
            "--!strict\nlocal owner = nil\nscript.Parent.Touched:Connect(function(hit)\n"
            "\tlocal human = hit.Parent:FindFirstChild(\"Humanoid\")\n"
            "\tif human ~= nil and owner == nil then\n"
            "\t\towner = hit.Parent.Name\n"
            "\t\tworkspace:WaitForChild(\"Столб\"):WaitForChild(\"BillboardGui\"):WaitForChild(\"TextLabel\").Text = \"БАЗА: \" .. tostring(owner)\n"
            "\t\tscript.Parent.Transparency = 1\n\t\tscript.Parent.CanCollide = false\n\tend\nend)"
        ),
        "photo_id": None
    },
    {
        "id": "tyc_dropper",
        "title": "💎 Дроппер руды (DropPoint)",
        "desc": "Клонирует OrePart из ServerStorage каждые 2 секунды и удаляет через 15 секунд.",
        "latch": (
            "1. Events: when run\n2. Control: while [true] do -> wait [2] seconds\n"
            "3. Variables: make [newOre] = a copy of [ServerStorage.OrePart]\n"
            "4. Instances: set [newOre].[Position] to [DropPoint.Position]\n"
            "5. Instances: set [newOre].[Parent] to [game.Workspace]\n"
            "6. Control: after [15] seconds -> destroy [newOre]"
        ),
        "luau": (
            "--!strict\nlocal ServerStorage = game:GetService(\"ServerStorage\")\n"
            "while true do\n\ttask.wait(2)\n\tlocal newOre = ServerStorage:WaitForChild(\"OrePart\"):Clone()\n"
            "\tnewOre.Position = script.Parent.Position\n\tnewOre.Parent = workspace\n"
            "\ttask.delay(15, function()\n\t\tif newOre and newOre.Parent then newOre:Destroy() end\n\tend)\nend"
        ),
        "photo_id": None
    },
    {
        "id": "tyc_collect",
        "title": "🏧 Кнопка выдачи денег (CollectButton)",
        "desc": "Переводит накопленные в станке деньги (BankCash) на счёт игрока (PlayerCash) при наступании.",
        "latch": (
            "1. Events: when [part] is touched by [hit]\n"
            "2. Variables: make [human] = in [hit.Parent] find [\"Humanoid\"]\n"
            "3. Control: if [human] ~= [nil] then\n"
            "4. Instances: set [Workspace.PlayerCash].[Value] to [PlayerCash.Value + BankCash.Value]\n"
            "5. Instances: set [Workspace.BankCash].[Value] to [0]"
        ),
        "luau": (
            "--!strict\nscript.Parent.Touched:Connect(function(hit)\n"
            "\tlocal human = hit.Parent:FindFirstChild(\"Humanoid\")\n"
            "\tif human ~= nil then\n"
            "\t\tlocal pCash = workspace:WaitForChild(\"PlayerCash\")\n"
            "\t\tlocal bCash = workspace:WaitForChild(\"BankCash\")\n"
            "\t\tpCash.Value += bCash.Value\n\t\tbCash.Value = 0\n\tend\nend)"
        ),
        "photo_id": None
    }
]


# =====================================================================
# 🗄 2. ЯДРО БАЗЫ ДАННЫХ ШТАБА (ПРОЕКТЫ, УРОКИ, СКРИПТЫ, РОБАКСЫ)
# =====================================================================
def init_empty_db() -> dict:
    default_proj_id = "proj_default"
    return {
        "active_project": default_proj_id,
        "projects": {
            default_proj_id: {
                "id": default_proj_id,
                "name": "🏭 Модуль 2: Бизнес-Тайкун",
                "desc": "Основной проект курса (Дропперы, Конвейеры, Latch)",
                "created": datetime.now().strftime("%d.%m.%Y"),
                "active_lesson": None,
                "lessons": {},
                "scripts": list(STARTER_TYCOON_SCRIPTS),
                "files": [],
                "history": []
            }
        },
        "prompts": dict(DEFAULT_PROMPTS),
        "students": {}
    }


def load_db() -> dict:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "projects" in data and data["projects"]:
                    return data
        except Exception as e:
            print(f"⚠️ Ошибка чтения БД, создаю резервную структуру: {e}")
    data = init_empty_db()
    save_db(data)
    return data


def save_db(data: dict):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Ошибка сохранения БД: {e}")


db = load_db()


def get_active_project() -> dict:
    pid = db.get("active_project")
    if not pid or pid not in db["projects"]:
        pid = next(iter(db["projects"].keys()))
        db["active_project"] = pid
        save_db(db)
    return db["projects"][pid]


def get_active_lesson(proj: dict):
    lid = proj.get("active_lesson")
    if lid and lid in proj["lessons"]:
        return proj["lessons"][lid]
    if proj["lessons"]:
        first_lid = next(iter(proj["lessons"].keys()))
        proj["active_lesson"] = first_lid
        save_db(db)
        return proj["lessons"][first_lid]
    return None


def calc_student_rank(robux: int) -> str:
    if robux >= 500:
        return "👑 Игровой магнат"
    if robux >= 250:
        return "🚀 Фаундер"
    if robux >= 100:
        return "⚡ Ментор"
    return "🟢 Разработчик"


# =====================================================================
# 🛠 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ И ПАРСЕРЫ (.MD / .JSON / .TXT)
# =====================================================================
async def safe_answer(message: types.Message, text: str, reply_markup=None):
    try:
        return await message.answer(text, reply_markup=reply_markup, parse_mode="Markdown")
    except Exception:
        return await message.answer(text, reply_markup=reply_markup, parse_mode=None)


async def safe_edit(message: types.Message, text: str, reply_markup=None):
    try:
        return await message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    except Exception:
        return await message.edit_text(text, reply_markup=reply_markup, parse_mode=None)


def split_into_paragraphs(text: str) -> list:
    raw_blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    merged = []
    buffer = ""
    for b in raw_blocks:
        if len(buffer) + len(b) < 700:
            buffer = f"{buffer}\n\n{b}".strip() if buffer else b
        else:
            if buffer:
                merged.append(buffer)
            buffer = b
    if buffer:
        merged.append(buffer)
    return merged if merged else [text]


def parse_md_content(raw_text: str) -> list:
    extracted = []
    if "### 👤 Пользователь" in raw_text or "### 🤖 Ассистент" in raw_text:
        turns = re.split(r"## Turn \d+|## Блок \d+", raw_text)
        for turn in turns:
            if not turn.strip():
                continue
            parts = re.split(r"### (👤 Пользователь|🤖 Ассистент)", turn)
            for idx in range(1, len(parts) - 1, 2):
                role_label = parts[idx]
                content = parts[idx + 1].strip()
                if content:
                    role = "user" if "Пользователь" in role_label else "model"
                    extracted.append({"role": role, "text": content})
    else:
        if raw_text.strip():
            extracted.append({"role": "model", "text": raw_text.strip()})
    return extracted


def parse_json_content(raw_text: str) -> list:
    data = json.loads(raw_text)
    extracted = []
    if isinstance(data, dict) and "items" in data:
        for item in data.get("items", []):
            if isinstance(item, dict):
                if item.get("user"):
                    extracted.append({"role": "user", "text": str(item["user"])})
                if item.get("assistant"):
                    extracted.append({"role": "model", "text": str(item["assistant"])})
    elif isinstance(data, list):
        for i in data:
            if isinstance(i, dict) and "text" in i:
                extracted.append({"role": i.get("role", "user"), "text": str(i["text"])})
    elif isinstance(data, dict) and "chunkedPrompt" in data:
        for ch in data["chunkedPrompt"].get("chunks", []):
            if ch.get("text") and not ch.get("isThought"):
                extracted.append({"role": ch.get("role", "user"), "text": ch["text"]})
    return extracted


def export_project_to_md(proj: dict) -> str:
    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    out = [
        f"# 📁 ПРОЕКТ: {proj['name']}",
        f"**Описание:** {proj.get('desc', '—')}",
        f"**Дата выгрузки:** {now_str}\n",
        "---\n"
    ]
    if proj["lessons"]:
        out.append("## 📚 УРОКИ ПРОЕКТА\n")
        for lid, les in proj["lessons"].items():
            out.append(f"### 📘 {les['title']}\n")
            out.append("\n\n".join(les.get("paragraphs", [])))
            out.append("\n\n---\n")

    if proj["scripts"]:
        out.append("## 💻 БАЗА СКРИПТОВ И МЕХАНИК (LATCH + LUAU)\n")
        for s in proj["scripts"]:
            out.append(f"### 📌 {s['title']}\n_{s.get('desc', '')}_\n")
            if s.get("latch"):
                out.append(f"**Сборка в Latch:**\n{s['latch']}\n")
            if s.get("luau"):
                out.append(f"```luau\n{s['luau']}\n```\n")
            out.append("---\n")

    if proj["history"]:
        out.append("## 💬 ИСТОРИЯ И ЗАМЕТКИ ПРОЕКТА\n")
        for idx, h in enumerate(proj["history"], 1):
            role = "### 👤 Пользователь" if h.get("role") == "user" else "### 🤖 Ассистент"
            out.append(f"## Turn {idx}\n\n{role}\n\n{h.get('text', '')}\n")

    return "\n".join(out)


# =====================================================================
# 🎛 4. СОСТОЯНИЯ (FSM) И ГЛАВНОЕ МЕНЮ ШТАБА
# =====================================================================
class HQStates(StatesGroup):
    # Проекты
    new_proj_name = State()
    new_proj_desc = State()
    rename_proj = State()
    # Уроки и абзацы
    new_lesson_title = State()
    new_lesson_content = State()
    edit_paragraph = State()
    add_paragraph = State()
    # Скрипты (Конструктор)
    scr_title = State()
    scr_desc = State()
    scr_latch = State()
    scr_luau = State()
    scr_edit_field = State()
    # Промпты
    use_prompt_task = State()
    new_prompt_title = State()
    new_prompt_text = State()
    edit_prompt_text = State()
    # Банк робаксов
    new_student_name = State()
    custom_robux = State()
    # Поиск и диалоги
    search_query = State()
    add_history_note = State()


def main_kb():
    proj = get_active_project()
    les = get_active_lesson(proj)
    les_label = f"📑 Шаги: {les['title'][:14]}.." if les else "📑 Шаги урока"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"📁 Проект: {proj['name'][:20]}"), KeyboardButton(text="📚 Уроки проекта")],
            [KeyboardButton(text=les_label), KeyboardButton(text="💻 База скриптов")],
            [KeyboardButton(text="🧠 Конструктор промптов"), KeyboardButton(text="📸 Файлы и Скрины")],
            [KeyboardButton(text="🏆 Банк робаксов"), KeyboardButton(text="🔍 Поиск по штабу")],
            [KeyboardButton(text="💬 Плашки чата"), KeyboardButton(text="📥 Импорт / Экспорт")]
        ],
        resize_keyboard=True
    )


# =====================================================================
# 🚀 5. СТАРТ И УПРАВЛЕНИЕ ПРОЕКТАМИ (КУРСАМИ / МОДУЛЯМИ)
# =====================================================================
@dp.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    proj = get_active_project()
    les = get_active_lesson(proj)
    les_name = les["title"] if les else "Нет уроков (создай в меню «📚 Уроки проекта»)"
    await safe_answer(
        message,
        f"⚡ *ШТАБ КУРСОВ ROBLOX (Полная автономность)*\n\n"
        f"📁 *Активный проект:* `{proj['name']}`\n"
        f"📘 *Активный урок:* `{les_name}`\n"
        f"📊 *Внутри проекта:* Уроков: *{len(proj['lessons'])}* | Скриптов: *{len(proj['scripts'])}* | Файлов/Скринов: *{len(proj['files'])}* | Плашек чата: *{len(proj['history'])}*\n\n"
        f"💡 _Любой файл (`.md`, `.json`, `.txt`, `.rbxl`, `.pdf`) или скриншот можно просто переслать сюда — бот сам предложит, куда его сохранить!_",
        reply_markup=main_kb()
    )


@dp.message(F.text.startswith("📁 Проект:"))
async def projects_menu(message: types.Message):
    proj = get_active_project()
    buttons = []
    for pid, p in db["projects"].items():
        mark = "✅ " if pid == db["active_project"] else "📁 "
        buttons.append([InlineKeyboardButton(
            text=f"{mark}{p['name']} (Ур: {len(p['lessons'])} | Скр: {len(p['scripts'])})",
            callback_data=f"psel_{pid}"
        )])

    buttons.append([
        InlineKeyboardButton(text="➕ Создать новый проект", callback_data="p_create"),
        InlineKeyboardButton(text="✏️ Переименовать", callback_data="p_rename")
    ])
    buttons.append([
        InlineKeyboardButton(text="📥 Выгрузить проект в .MD", callback_data="p_export_md"),
        InlineKeyboardButton(text="🗑 Удалить проект", callback_data="p_delete")
    ])
    await safe_answer(
        message,
        f"📁 *УПРАВЛЕНИЕ ПРОЕКТАМИ (КУРСАМИ И МОДУЛЯМИ)*\n\n"
        f"Сейчас выбран: *{proj['name']}*\n"
        f"Описание: _{proj.get('desc', '—')}_\n\n"
        f"Переключись на нужный проект или создай новый:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@dp.callback_query(F.data.startswith("psel_"))
async def select_project_cb(callback: types.CallbackQuery):
    pid = callback.data.replace("psel_", "")
    if pid in db["projects"]:
        db["active_project"] = pid
        save_db(db)
        proj = db["projects"][pid]
        await callback.answer(f"Выбран проект: {proj['name']}")
        await safe_answer(
            callback.message,
            f"✅ Активный проект переключён на: *{proj['name']}*\n"
            f"Уроков: *{len(proj['lessons'])}* | Скриптов: *{len(proj['scripts'])}* | Файлов: *{len(proj['files'])}*",
            reply_markup=main_kb()
        )


@dp.callback_query(F.data == "p_create")
async def create_project_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(HQStates.new_proj_name)
    await safe_answer(callback.message, "📁 Введи *название нового проекта/модуля* (например: _«Модуль 3: Хоррор DOORS»_):")
    await callback.answer()


@dp.message(HQStates.new_proj_name)
async def create_project_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(HQStates.new_proj_desc)
    await safe_answer(message, "📝 Введи *краткое описание проекта* (или отправь `-`, чтобы пропустить):")


@dp.message(HQStates.new_proj_desc)
async def create_project_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    pid = f"p_{uuid.uuid4().hex[:6]}"
    desc = "" if message.text.strip() == "-" else message.text.strip()
    db["projects"][pid] = {
        "id": pid,
        "name": data["name"],
        "desc": desc,
        "created": datetime.now().strftime("%d.%m.%Y"),
        "active_lesson": None,
        "lessons": {},
        "scripts": [],
        "files": [],
        "history": []
    }
    db["active_project"] = pid
    save_db(db)
    await safe_answer(
        message,
        f"🎉 Проект *{data['name']}* создан и выбран как активный!\n"
        f"Теперь можешь добавлять в него уроки, скрипты или закидывать файлы `.md` / `.json`.",
        reply_markup=main_kb()
    )


@dp.callback_query(F.data == "p_rename")
async def rename_project_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(HQStates.rename_proj)
    await callback.message.answer("✏️ Введи новое название для текущего проекта:")
    await callback.answer()


@dp.message(HQStates.rename_proj)
async def rename_project_done(message: types.Message, state: FSMContext):
    proj = get_active_project()
    if message.text:
        proj["name"] = message.text.strip()
        save_db(db)
    await state.clear()
    await safe_answer(message, f"✅ Проект переименован в *{proj['name']}*!", reply_markup=main_kb())


@dp.callback_query(F.data == "p_delete")
async def delete_project_cb(callback: types.CallbackQuery):
    if len(db["projects"]) <= 1:
        await callback.answer("⚠️ Нельзя удалить единственный проект!", show_alert=True)
        return
    pid = db["active_project"]
    pname = db["projects"][pid]["name"]
    del db["projects"][pid]
    db["active_project"] = next(iter(db["projects"].keys()))
    save_db(db)
    await callback.answer("Проект удалён")
    await safe_answer(
        callback.message,
        f"🗑 Проект *{pname}* удалён. Активный проект: *{get_active_project()['name']}*",
        reply_markup=main_kb()
    )


@dp.callback_query(F.data == "p_export_md")
async def export_project_md_cb(callback: types.CallbackQuery):
    proj = get_active_project()
    md_text = export_project_to_md(proj)
    safe_fname = re.sub(r"[^a-zA-Z0-9а-яА-Я_-]", "_", proj["name"])[:30] + ".md"
    f_out = BufferedInputFile(md_text.encode("utf-8"), filename=safe_fname)
    await callback.message.answer_document(f_out, caption=f"📁 Полная выгрузка проекта «{proj['name']}» в формате .MD")
    await callback.answer()


# =====================================================================
# 📚 6. УРОКИ ВНУТРИ ПРОЕКТА И ПОШАГОВЫЙ НАВИГАТОР ПО АБЗАЦАМ
# =====================================================================
@dp.message(F.text == "📚 Уроки проекта")
async def lessons_menu(message: types.Message):
    proj = get_active_project()
    buttons = []
    for lid, les in proj["lessons"].items():
        mark = "🟢 " if lid == proj.get("active_lesson") else "📘 "
        p_count = len(les.get("paragraphs", []))
        buttons.append([InlineKeyboardButton(
            text=f"{mark}{les['title']} ({p_count} абз.)",
            callback_data=f"lsel_{lid}"
        )])

    buttons.append([InlineKeyboardButton(text="➕ Создать новый урок", callback_data="l_create")])
    if proj.get("active_lesson") and proj["active_lesson"] in proj["lessons"]:
        buttons.append([
            InlineKeyboardButton(text="📥 Скачать урок в .MD", callback_data="l_export"),
            InlineKeyboardButton(text="🗑 Удалить текущий урок", callback_data="l_delete")
        ])

    await safe_answer(
        message,
        f"📚 *УРОКИ ПРОЕКТА «{proj['name']}»*\n\n"
        f"Выбери урок для работы с его шагами/абзацами или создай новый (также можно просто скинуть в чат файл `.md` или `.txt`):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@dp.callback_query(F.data.startswith("lsel_"))
async def select_lesson_cb(callback: types.CallbackQuery, state: FSMContext):
    lid = callback.data.replace("lsel_", "")
    proj = get_active_project()
    if lid in proj["lessons"]:
        proj["active_lesson"] = lid
        proj["lessons"][lid]["curr_p"] = 0
        save_db(db)
        await callback.answer(f"Выбран: {proj['lessons'][lid]['title']}")
        await show_lesson_paragraphs(callback.message, state)


@dp.callback_query(F.data == "l_create")
async def create_lesson_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(HQStates.new_lesson_title)
    await safe_answer(callback.message, "📘 Введи *название нового урока* (например: _«Урок 2: Дроппер и Конвейер»_):")
    await callback.answer()


@dp.message(HQStates.new_lesson_title)
async def create_lesson_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(HQStates.new_lesson_content)
    await safe_answer(
        message,
        "📝 Теперь отправь *текст урока/методички* (я автоматически разобью его на удобные шаги-абзацы) или отправь `-`, чтобы создать пустой урок:"
    )


@dp.message(HQStates.new_lesson_content)
async def create_lesson_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    proj = get_active_project()
    lid = f"les_{uuid.uuid4().hex[:6]}"
    raw_text = "" if (not message.text or message.text.strip() == "-") else message.text.strip()
    paragraphs = split_into_paragraphs(raw_text) if raw_text else ["Первый шаг урока (нажми «✏️ Править», чтобы изменить)."]

    proj["lessons"][lid] = {
        "id": lid,
        "title": data["title"],
        "paragraphs": paragraphs,
        "curr_p": 0
    }
    proj["active_lesson"] = lid
    save_db(db)
    await safe_answer(
        message,
        f"✅ Урок *{data['title']}* создан в проекте «{proj['name']}» (разбит на *{len(paragraphs)}* абз.)!",
        reply_markup=main_kb()
    )
    await show_lesson_paragraphs(message, state)


@dp.callback_query(F.data == "l_delete")
async def delete_lesson_cb(callback: types.CallbackQuery):
    proj = get_active_project()
    lid = proj.get("active_lesson")
    if lid and lid in proj["lessons"]:
        title = proj["lessons"][lid]["title"]
        del proj["lessons"][lid]
        proj["active_lesson"] = next(iter(proj["lessons"].keys()), None)
        save_db(db)
        await safe_answer(callback.message, f"🗑 Урок *{title}* удалён.", reply_markup=main_kb())
    await callback.answer()


@dp.callback_query(F.data == "l_export")
async def export_lesson_cb(callback: types.CallbackQuery):
    proj = get_active_project()
    les = get_active_lesson(proj)
    if not les:
        await callback.answer("Нет активного урока")
        return
    full_md = f"# {les['title']}\n\n" + "\n\n".join(les["paragraphs"])
    fname = re.sub(r"[^a-zA-Z0-9а-яА-Я_-]", "_", les["title"])[:30] + ".md"
    f_out = BufferedInputFile(full_md.encode("utf-8"), filename=fname)
    await callback.message.answer_document(f_out, caption=f"📘 Урок «{les['title']}» (.MD)")
    await callback.answer()


def get_paragraph_kb(idx: int, total: int):
    nav = []
    if idx > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Пред.", callback_data=f"pnav_{idx-1}"))
    nav.append(InlineKeyboardButton(text=f"📄 {idx+1}/{total}", callback_data="p_noop"))
    if idx < total - 1:
        nav.append(InlineKeyboardButton(text="След. ➡️", callback_data=f"pnav_{idx+1}"))

    actions = [
        InlineKeyboardButton(text="✏️ Править шаг", callback_data=f"pedit_{idx}"),
        InlineKeyboardButton(text="➕ Добавить шаг после", callback_data=f"padd_{idx}"),
        InlineKeyboardButton(text="❌ Удалить", callback_data=f"pdel_{idx}")
    ]
    extra = [
        InlineKeyboardButton(text="📚 Все уроки", callback_data="p_all_lessons"),
        InlineKeyboardButton(text="📥 Скачать весь урок (.MD)", callback_data="l_export")
    ]
    return InlineKeyboardMarkup(inline_keyboard=[nav, actions, extra])


@dp.message(F.text.startswith("📑 Шаги"))
async def show_lesson_paragraphs(message: types.Message, state: FSMContext):
    proj = get_active_project()
    les = get_active_lesson(proj)
    if not les:
        await safe_answer(
            message,
            f"📭 В проекте *{proj['name']}* пока нет уроков.\n"
            f"Нажми `📚 Уроки проекта` -> `➕ Создать новый урок` или просто скинь мне файл `.md` / `.json`!"
        )
        return

    paragraphs = les.get("paragraphs", [])
    if not paragraphs:
        paragraphs = ["Пустой урок"]
        les["paragraphs"] = paragraphs

    idx = min(les.get("curr_p", 0), len(paragraphs) - 1)
    les["curr_p"] = idx
    p_text = paragraphs[idx]

    await safe_answer(
        message,
        f"📁 *{proj['name']}* $\\rightarrow$ 📘 *{les['title']}*\n"
        f"📑 *Шаг #{idx+1} из {len(paragraphs)}:*\n\n{p_text}\n\n"
        f"📋 _Копирование шага:_\n```text\n{p_text}\n```",
        reply_markup=get_paragraph_kb(idx, len(paragraphs))
    )


@dp.callback_query(F.data == "p_noop")
async def noop_cb(callback: types.CallbackQuery):
    await callback.answer()


@dp.callback_query(F.data == "p_all_lessons")
async def go_all_lessons_cb(callback: types.CallbackQuery):
    await lessons_menu(callback.message)
    await callback.answer()


@dp.callback_query(F.data.startswith("pnav_"))
async def navigate_paragraphs(callback: types.CallbackQuery):
    idx = int(callback.data.replace("pnav_", ""))
    proj = get_active_project()
    les = get_active_lesson(proj)
    if les and 0 <= idx < len(les["paragraphs"]):
        les["curr_p"] = idx
        save_db(db)
        p_text = les["paragraphs"][idx]
        await safe_edit(
            callback.message,
            f"📁 *{proj['name']}* $\\rightarrow$ 📘 *{les['title']}*\n"
            f"📑 *Шаг #{idx+1} из {len(les['paragraphs'])}:*\n\n{p_text}\n\n"
            f"📋 _Копирование шага:_\n```text\n{p_text}\n```",
            reply_markup=get_paragraph_kb(idx, len(les["paragraphs"]))
        )
    await callback.answer()


@dp.callback_query(F.data.startswith("pedit_"))
async def edit_paragraph_start(callback: types.CallbackQuery, state: FSMContext):
    idx = int(callback.data.replace("pedit_", ""))
    await state.update_data(edit_idx=idx)
    await state.set_state(HQStates.edit_paragraph)
    await safe_answer(callback.message, f"✏️ Отправь новый текст для *Шага #{idx+1}*:")
    await callback.answer()


@dp.message(HQStates.edit_paragraph)
async def edit_paragraph_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    idx = data.get("edit_idx", 0)
    proj = get_active_project()
    les = get_active_lesson(proj)
    if les and 0 <= idx < len(les["paragraphs"]) and message.text:
        les["paragraphs"][idx] = message.text.strip()
        les["curr_p"] = idx
        save_db(db)
    await state.clear()
    await safe_answer(message, "✅ Шаг урока обновлён!", reply_markup=main_kb())
    await show_lesson_paragraphs(message, state)


@dp.callback_query(F.data.startswith("padd_"))
async def add_paragraph_start(callback: types.CallbackQuery, state: FSMContext):
    idx = int(callback.data.replace("padd_", ""))
    await state.update_data(after_idx=idx)
    await state.set_state(HQStates.add_paragraph)
    await safe_answer(callback.message, f"➕ Отправь текст нового шага (он встанет сразу после шага #{idx+1}):")
    await callback.answer()


@dp.message(HQStates.add_paragraph)
async def add_paragraph_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    after_idx = data.get("after_idx", 0)
    proj = get_active_project()
    les = get_active_lesson(proj)
    if les and message.text:
        les["paragraphs"].insert(after_idx + 1, message.text.strip())
        les["curr_p"] = after_idx + 1
        save_db(db)
    await state.clear()
    await safe_answer(message, "✅ Новый шаг вставлен в урок!", reply_markup=main_kb())
    await show_lesson_paragraphs(message, state)


@dp.callback_query(F.data.startswith("pdel_"))
async def delete_paragraph_cb(callback: types.CallbackQuery):
    idx = int(callback.data.replace("pdel_", ""))
    proj = get_active_project()
    les = get_active_lesson(proj)
    if les and len(les["paragraphs"]) > 1 and 0 <= idx < len(les["paragraphs"]):
        les["paragraphs"].pop(idx)
        les["curr_p"] = max(0, idx - 1)
        save_db(db)
        new_idx = les["curr_p"]
        p_text = les["paragraphs"][new_idx]
        await safe_edit(
            callback.message,
            f"📁 *{proj['name']}* $\\rightarrow$ 📘 *{les['title']}*\n"
            f"📑 *Шаг #{new_idx+1} из {len(les['paragraphs'])}:*\n\n{p_text}",
            reply_markup=get_paragraph_kb(new_idx, len(les["paragraphs"]))
        )
        await callback.answer("Шаг удалён")
    else:
        await callback.answer("⚠️ В уроке должен остаться хотя бы 1 шаг!", show_alert=True)


# =====================================================================
# 💻 7. ДИНАМИЧЕСКАЯ БАЗА СКРИПТОВ И МЕХАНИК (LATCH + LUAU + СКРИН)
# =====================================================================
@dp.message(F.text == "💻 База скриптов")
async def scripts_vault_menu(message: types.Message):
    proj = get_active_project()
    buttons = []
    for idx, s in enumerate(proj["scripts"]):
        buttons.append([InlineKeyboardButton(text=s["title"], callback_data=f"svw_{idx}")])

    buttons.append([InlineKeyboardButton(text="➕ Добавить свой скрипт / схему Latch", callback_data="s_add")])
    if not proj["scripts"]:
        buttons.append([InlineKeyboardButton(text="📥 Загрузить стартовый пак Тайкуна", callback_data="s_load_starter")])

    await safe_answer(
        message,
        f"💻 *БАЗА СКРИПТОВ ПРОЕКТА «{proj['name']}»*\n\n"
        f"Скриптов в этом проекте: *{len(proj['scripts'])}*\n"
        f"Выбери нужный механизм или создай свой прямо в боте:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@dp.callback_query(F.data == "s_load_starter")
async def load_starter_scripts_cb(callback: types.CallbackQuery):
    proj = get_active_project()
    proj["scripts"].extend([dict(x) for x in STARTER_TYCOON_SCRIPTS])
    save_db(db)
    await callback.answer("✅ Стартовые скрипты Тайкуна добавлены!")
    await scripts_vault_menu(callback.message)


@dp.callback_query(F.data.startswith("svw_"))
async def view_script_card(callback: types.CallbackQuery):
    idx = int(callback.data.replace("svw_", ""))
    proj = get_active_project()
    if not (0 <= idx < len(proj["scripts"])):
        await callback.answer("Не найдено")
        return

    s = proj["scripts"][idx]
    text = f"📌 *{s['title']}*\n_{s.get('desc', '')}_\n\n"
    if s.get("latch"):
        text += f"🧩 *Схема блоков (Latch / Логика):*\n{s['latch']}\n\n"
    if s.get("luau"):
        text += f"💻 *Код Luau (нажми для копирования):*\n```luau\n{s['luau']}\n```"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Изм. код/схему", callback_data=f"sedit_{idx}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"sdel_{idx}")
        ],
        [InlineKeyboardButton(text="⬅️ Назад к списку скриптов", callback_data="s_back")]
    ])

    if s.get("photo_id"):
        await callback.message.answer_photo(photo=s["photo_id"], caption=f"📸 Схема к скрипту «{s['title']}»")
    await safe_answer(callback.message, text, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "s_back")
async def back_to_scripts_cb(callback: types.CallbackQuery):
    await scripts_vault_menu(callback.message)
    await callback.answer()


@dp.callback_query(F.data == "s_add")
async def add_script_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(HQStates.scr_title)
    await safe_answer(callback.message, "💻 Введи *название нового скрипта/механики* (например: _«⚡ Урок 3: Апгрейдер руды»_):")
    await callback.answer()


@dp.message(HQStates.scr_title)
async def add_script_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(HQStates.scr_desc)
    await safe_answer(message, "📝 Введи *краткое описание* (что делает скрипт и какие объекты нужны в Explorer):")


@dp.message(HQStates.scr_desc)
async def add_script_desc(message: types.Message, state: FSMContext):
    await state.update_data(desc=message.text.strip())
    await state.set_state(HQStates.scr_latch)
    await safe_answer(
        message,
        "🧩 Отправь *пошаговую сборку блоков в Latch* (или прикрепи *скриншот блоков* с подписью! Если не нужно — отправь `-`):"
    )


@dp.message(HQStates.scr_latch)
async def add_script_latch(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id if message.photo else None
    latch_text = message.caption if message.photo else (message.text or "")
    if latch_text.strip() == "-":
        latch_text = ""
    await state.update_data(latch=latch_text.strip(), photo_id=photo_id)
    await state.set_state(HQStates.scr_luau)
    await safe_answer(message, "💻 Теперь отправь *проверочный код Luau* (или отправь `-`, если скрипт только на блоках):")


@dp.message(HQStates.scr_luau)
async def add_script_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    luau_code = "" if (not message.text or message.text.strip() == "-") else message.text.strip()

    proj = get_active_project()
    proj["scripts"].append({
        "id": f"scr_{uuid.uuid4().hex[:6]}",
        "title": data["title"],
        "desc": data["desc"],
        "latch": data["latch"],
        "luau": luau_code,
        "photo_id": data.get("photo_id")
    })
    save_db(db)
    await safe_answer(
        message,
        f"✅ Скрипт *{data['title']}* сохранён в базу проекта «{proj['name']}»!",
        reply_markup=main_kb()
    )
    await scripts_vault_menu(message)


@dp.callback_query(F.data.startswith("sdel_"))
async def delete_script_cb(callback: types.CallbackQuery):
    idx = int(callback.data.replace("sdel_", ""))
    proj = get_active_project()
    if 0 <= idx < len(proj["scripts"]):
        removed = proj["scripts"].pop(idx)
        save_db(db)
        await callback.answer(f"Удалено: {removed['title']}")
        await scripts_vault_menu(callback.message)


@dp.callback_query(F.data.startswith("sedit_"))
async def edit_script_start(callback: types.CallbackQuery, state: FSMContext):
    idx = int(callback.data.replace("sedit_", ""))
    await state.update_data(s_idx=idx)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить схему Latch", callback_data="sef_latch")],
        [InlineKeyboardButton(text="💻 Изменить код Luau", callback_data="sef_luau")],
        [InlineKeyboardButton(text="📝 Изменить описание", callback_data="sef_desc")]
    ])
    await safe_answer(callback.message, "Что именно хочешь обновить в этом скрипте?", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("sef_"))
async def edit_script_field_choice(callback: types.CallbackQuery, state: FSMContext):
    field = callback.data.replace("sef_", "")
    await state.update_data(s_field=field)
    await state.set_state(HQStates.scr_edit_field)
    await callback.message.answer("✍️ Отправь новое значение:")
    await callback.answer()


@dp.message(HQStates.scr_edit_field)
async def edit_script_field_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    idx = data.get("s_idx", 0)
    field = data.get("s_field", "luau")
    proj = get_active_project()
    if 0 <= idx < len(proj["scripts"]) and message.text:
        proj["scripts"][idx][field] = message.text.strip()
        save_db(db)
    await safe_answer(message, "✅ Скрипт обновлён!", reply_markup=main_kb())


# =====================================================================
# 🧠 8. РЕДАКТИРУЕМЫЙ КОНСТРУКТОР ПРОМПТОВ (СВОИ ШАБЛОНЫ)
# =====================================================================
@dp.message(F.text == "🧠 Конструктор промптов")
async def prompts_menu(message: types.Message):
    buttons = []
    for pkey, pval in db["prompts"].items():
        buttons.append([
            InlineKeyboardButton(text=f"🚀 {pval['title']}", callback_data=f"puse_{pkey}"),
            InlineKeyboardButton(text="✏️", callback_data=f"pedt_{pkey}"),
            InlineKeyboardButton(text="🗑", callback_data=f"pdelp_{pkey}")
        ])
    buttons.append([InlineKeyboardButton(text="➕ Создать свой шаблон промпта", callback_data="p_new_tpl")])
    await safe_answer(
        message,
        "🧠 *КОНСТРУКТОР УМНЫХ ПРОМПТОВ*\n\n"
        "• Нажми на название шаблона (`🚀`), чтобы собрать готовый промпт с учётом контекста твоего текущего проекта.\n"
        "• Нажми `✏️`, чтобы отредактировать правила любого шаблона под себя, или `➕`, чтобы добавить новую кнопку:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@dp.callback_query(F.data.startswith("puse_"))
async def use_prompt_start(callback: types.CallbackQuery, state: FSMContext):
    pkey = callback.data.replace("puse_", "")
    if pkey in db["prompts"]:
        await state.update_data(pkey=pkey)
        await state.set_state(HQStates.use_prompt_task)
        tpl = db["prompts"][pkey]
        await safe_answer(
            callback.message,
            f"🎯 Шаблон: *{tpl['title']}*\n"
            f"Напиши тему урока или задачу (контекст активного проекта «{get_active_project()['name']}» подставится автоматически):"
        )
    await callback.answer()


@dp.message(HQStates.use_prompt_task)
async def use_prompt_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    pkey = data.get("pkey")
    tpl = db["prompts"].get(pkey, {"title": "Промпт", "text": ""})
    task_text = message.text or ""

    proj = get_active_project()
    proj["history"].append({"role": "user", "text": task_text})
    save_db(db)

    # Авто-сборка контекста из текущего проекта (уроки + скрипты + последние сообщения)
    ctx_parts = [f"Проект: {proj['name']} ({proj.get('desc', '')})"]
    les = get_active_lesson(proj)
    if les:
        ctx_parts.append(f"Текущий активный урок: {les['title']}")
    if proj["scripts"]:
        scr_names = ", ".join([s["title"] for s in proj["scripts"][:8]])
        ctx_parts.append(f"Механики/скрипты проекта: {scr_names}")
    if len(proj["history"]) > 1:
        for h in proj["history"][:-1][-4:]:
            tag = "Автор" if h["role"] == "user" else "ИИ"
            ctx_parts.append(f"[{tag}]: {h['text'][:500]}")

    context_block = "\n".join(ctx_parts)
    full_prompt = f"{tpl['text']}\n\n=== КОНТЕКСТ ПРОЕКТА ===\n{context_block}\n\n=== ТЕКУЩАЯ ЗАДАЧА ===\n{task_text}"

    if len(full_prompt) <= 3800:
        await safe_answer(
            message,
            f"🔥 *Готовый промпт (скопируй одним нажатием):*\n```text\n{full_prompt}\n```",
            reply_markup=main_kb()
        )
    else:
        f_out = BufferedInputFile(full_prompt.encode("utf-8"), filename="prompt_ready.md")
        await message.answer_document(f_out, caption="🔥 Полный промпт с историей проекта (.md)")


@dp.callback_query(F.data == "p_new_tpl")
async def new_prompt_tpl_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(HQStates.new_prompt_title)
    await callback.message.answer("🧠 Введи название новой кнопки-шаблона (например: _«🎬 Сценарий рилса / трейлера»_):")
    await callback.answer()


@dp.message(HQStates.new_prompt_title)
async def new_prompt_tpl_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(HQStates.new_prompt_text)
    await message.answer("📝 Теперь отправь системную инструкцию (правила) для этого шаблона:")


@dp.message(HQStates.new_prompt_text)
async def new_prompt_tpl_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    pkey = f"prm_{uuid.uuid4().hex[:5]}"
    db["prompts"][pkey] = {"title": data["title"], "text": message.text.strip()}
    save_db(db)
    await safe_answer(message, f"✅ Шаблон *{data['title']}* добавлен в конструктор!", reply_markup=main_kb())
    await prompts_menu(message)


@dp.callback_query(F.data.startswith("pedt_"))
async def edit_prompt_tpl_start(callback: types.CallbackQuery, state: FSMContext):
    pkey = callback.data.replace("pedt_", "")
    if pkey in db["prompts"]:
        await state.update_data(pkey=pkey)
        await state.set_state(HQStates.edit_prompt_text)
        curr = db["prompts"][pkey]
        await safe_answer(
            callback.message,
            f"✏️ *Текущий текст шаблона «{curr['title']}»:*\n```text\n{curr['text']}\n```\n\nОтправь новый текст инструкции:"
        )
    await callback.answer()


@dp.message(HQStates.edit_prompt_text)
async def edit_prompt_tpl_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    pkey = data.get("pkey")
    if pkey in db["prompts"] and message.text:
        db["prompts"][pkey]["text"] = message.text.strip()
        save_db(db)
    await safe_answer(message, "✅ Инструкция шаблона обновлена!", reply_markup=main_kb())
    await prompts_menu(message)


@dp.callback_query(F.data.startswith("pdelp_"))
async def delete_prompt_tpl_cb(callback: types.CallbackQuery):
    pkey = callback.data.replace("pdelp_", "")
    if pkey in db["prompts"]:
        del db["prompts"][pkey]
        save_db(db)
        await callback.answer("Шаблон удалён")
        await prompts_menu(callback.message)


# =====================================================================
# 📸 9. ХРАНИЛИЩЕ ФАЙЛОВ, СКРИНШОТОВ И ИМПОРТ .MD / .JSON
# =====================================================================
@dp.message(F.photo)
async def handle_photo_upload(message: types.Message):
    proj = get_active_project()
    file_id = message.photo[-1].file_id
    caption = message.caption or f"Скриншот #{len(proj['files']) + 1}"
    item_idx = len(proj["files"])
    proj["files"].append({
        "type": "photo",
        "file_id": file_id,
        "name": caption,
        "date": datetime.now().strftime("%d.%m %H:%M")
    })
    proj["history"].append({"role": "user", "text": f"[СКРИНШОТ]: {caption}"})
    save_db(db)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛠 Сгенерировать промпт на разбор бага", callback_data=f"fbug_{item_idx}")]
    ])
    await safe_answer(
        message,
        f"📸 Скриншот сохранён в проект *{proj['name']}*!\n📝 Заметка: _{caption}_",
        reply_markup=kb
    )


@dp.callback_query(F.data.startswith("fbug_"))
async def generate_bug_prompt_cb(callback: types.CallbackQuery):
    idx = int(callback.data.replace("fbug_", ""))
    proj = get_active_project()
    if 0 <= idx < len(proj["files"]):
        fitem = proj["files"][idx]
        prompt = (
            f"Проект: {proj['name']}\n"
            f"Описание проблемы на скриншоте: {fitem['name']}\n\n"
            "Проанализируй скриншот из Roblox Studio / Latch и укажи без воды:\n"
            "1. Причину бага (кавычки вокруг переменных, 0 вместо nil, несовпадение имён в WaitForChild, Anchored/CanCollide).\n"
            "2. Точную пошаговую инструкцию, какие блоки переставить в Latch и какой код Luau должен получиться."
        )
        await safe_answer(callback.message, f"🔥 *Промпт для разбора скриншота:*\n```text\n{prompt}\n```")
    await callback.answer()


@dp.message(F.document)
async def handle_document_upload(message: types.Message):
    proj = get_active_project()
    doc = message.document
    fname = doc.file_name or "file"
    lower_name = fname.lower()

    # Если это текстовый файл (.md, .json, .txt) — парсим его как урок и историю!
    if lower_name.endswith((".md", ".json", ".txt")):
        file = await bot.get_file(doc.file_id)
        raw = (await bot.download_file(file.file_path)).read().decode("utf-8", errors="ignore")
        try:
            if lower_name.endswith(".json"):
                extracted = parse_json_content(raw)
            else:
                extracted = parse_md_content(raw)

            if not extracted:
                await message.answer("⚠️ Файл пуст или не содержит текстовых блоков.")
                return

            proj["history"].extend(extracted)
            # Создаём из файла отдельный урок внутри активного проекта, чтобы его было удобно листать по абзацам
            lid = f"les_{uuid.uuid4().hex[:6]}"
            last_text = extracted[-1]["text"] if len(extracted) == 1 else "\n\n---\n\n".join(
                [f"**[{'Я' if x['role']=='user' else 'ИИ'}]:**\n{x['text']}" for x in extracted[-15:]]
            )
            paragraphs = split_into_paragraphs(last_text)
            proj["lessons"][lid] = {
                "id": lid,
                "title": f"📥 {fname[:28]}",
                "paragraphs": paragraphs,
                "curr_p": 0
            }
            proj["active_lesson"] = lid
            save_db(db)

            await safe_answer(
                message,
                f"✅ *Файл `{fname}` импортирован в проект «{proj['name']}»!*\n"
                f"• Загружено плашек диалога: *{len(extracted)}*\n"
                f"• Создан урок `📥 {fname[:28]}` на *{len(paragraphs)} шагов/абзацев*.\n\n"
                f"Жми кнопку `📑 Шаги...` внизу, чтобы листать!",
                reply_markup=main_kb()
            )
            return
        except Exception as e:
            await message.answer(f"❌ Ошибка разбора файла: {e}")
            return

    # Любые другие файлы (.rbxl, .pdf, .pptx, .zip, картинки без сжатия) сохраняем в файловое хранилище проекта
    proj["files"].append({
        "type": "doc",
        "file_id": doc.file_id,
        "name": f"{fname} ({message.caption or 'без описания'})",
        "date": datetime.now().strftime("%d.%m %H:%M")
    })
    save_db(db)
    await safe_answer(
        message,
        f"📎 Файл `{fname}` сохранён в хранилище проекта *{proj['name']}*! (Доступен в меню `📸 Файлы и Скрины`).",
        reply_markup=main_kb()
    )


@dp.message(F.text == "📸 Файлы и Скрины")
async def show_project_files(message: types.Message):
    proj = get_active_project()
    if not proj["files"]:
        await safe_answer(
            message,
            f"📭 В проекте *{proj['name']}* пока нет сохранённых скриншотов или файлов.\n\n"
            f"Просто отправь сюда любое фото, скриншот, карту `.rbxl` или презентацию `.pdf` — они привяжутся к этому проекту!"
        )
        return

    await safe_answer(message, f"📸 *Файлы и скриншоты проекта «{proj['name']}» (последние 8):*")
    for idx in range(max(0, len(proj["files"]) - 8), len(proj["files"])):
        fitem = proj["files"][idx]
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🛠 Промпт на баг", callback_data=f"fbug_{idx}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"fdel_{idx}")
            ]
        ])
        if fitem["type"] == "photo":
            await message.answer_photo(
                photo=fitem["file_id"],
                caption=f"📸 #{idx+1} ({fitem.get('date', '')}): {fitem['name']}",
                reply_markup=kb
            )
        else:
            await message.answer_document(
                document=fitem["file_id"],
                caption=f"📎 #{idx+1} ({fitem.get('date', '')}): {fitem['name']}",
                reply_markup=kb
            )


@dp.callback_query(F.data.startswith("fdel_"))
async def delete_file_cb(callback: types.CallbackQuery):
    idx = int(callback.data.replace("fdel_", ""))
    proj = get_active_project()
    if 0 <= idx < len(proj["files"]):
        proj["files"].pop(idx)
        save_db(db)
        await callback.message.delete()
    await callback.answer("Файл удалён")


# =====================================================================
# 🏆 10. БАНК РОБАКСОВ И РЕЙТИНГ УЧЕНИКОВ
# =====================================================================
@dp.message(F.text == "🏆 Банк робаксов")
async def robux_bank_menu(message: types.Message):
    students = db.get("students", {})
    buttons = []
    sorted_stds = sorted(students.items(), key=lambda x: x[1].get("robux", 0), reverse=True)
    for sid, st in sorted_stds:
        rank = calc_student_rank(st["robux"])
        buttons.append([InlineKeyboardButton(
            text=f"{st['name']} — 💰 {st['robux']} R$ ({rank})",
            callback_data=f"std_{sid}"
        )])

    buttons.append([
        InlineKeyboardButton(text="➕ Добавить ученика", callback_data="std_add"),
        InlineKeyboardButton(text="📋 Таблица в текст", callback_data="std_export")
    ])
    await safe_answer(
        message,
        "🏆 *БАНК РОБАКСОВ (МОТИВАЦИОННАЯ СИСТЕМА КУРСА)*\n\n"
        "Нажми на ученика, чтобы начислить или списать робаксы за урок, плейтест или домашний квест:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@dp.callback_query(F.data == "std_add")
async def add_student_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(HQStates.new_student_name)
    await callback.message.answer("👤 Введи имя или ник нового ученика:")
    await callback.answer()


@dp.message(HQStates.new_student_name)
async def add_student_done(message: types.Message, state: FSMContext):
    await state.clear()
    if message.text:
        sid = f"s_{uuid.uuid4().hex[:5]}"
        db["students"][sid] = {"name": message.text.strip(), "robux": 0}
        save_db(db)
    await robux_bank_menu(message)


@dp.callback_query(F.data.startswith("std_"))
async def student_card_cb(callback: types.CallbackQuery):
    sid = callback.data.replace("std_", "")
    if sid not in db["students"]:
        await callback.answer()
        return
    st = db["students"][sid]
    rank = calc_student_rank(st["robux"])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="+10 R$", callback_data=f"rb_{sid}_10"),
            InlineKeyboardButton(text="+25 R$", callback_data=f"rb_{sid}_25"),
            InlineKeyboardButton(text="+50 R$", callback_data=f"rb_{sid}_50")
        ],
        [
            InlineKeyboardButton(text="-25 R$ (Магазин)", callback_data=f"rb_{sid}_-25"),
            InlineKeyboardButton(text="-50 R$ (Магазин)", callback_data=f"rb_{sid}_-50")
        ],
        [
            InlineKeyboardButton(text="🗑 Удалить ученика", callback_data=f"stddel_{sid}"),
            InlineKeyboardButton(text="⬅️ К списку", callback_data="std_back")
        ]
    ])
    await safe_edit(
        callback.message,
        f"👤 *Ученик:* {st['name']}\n"
        f"💰 *Баланс:* `{st['robux']} R$`\n"
        f"🎖 *Статус:* {rank}",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data == "std_back")
async def std_back_cb(callback: types.CallbackQuery):
    await robux_bank_menu(callback.message)
    await callback.answer()


@dp.callback_query(F.data.startswith("rb_"))
async def change_robux_cb(callback: types.CallbackQuery):
    _, sid, delta_str = callback.data.split("_")
    if sid in db["students"]:
        db["students"][sid]["robux"] = max(0, db["students"][sid]["robux"] + int(delta_str))
        save_db(db)
        await callback.answer(f"Баланс обновлён: {db['students'][sid]['robux']} R$")
        callback.data = f"std_{sid}"
        await student_card_cb(callback)


@dp.callback_query(F.data.startswith("stddel_"))
async def delete_student_cb(callback: types.CallbackQuery):
    sid = callback.data.replace("stddel_", "")
    if sid in db["students"]:
        del db["students"][sid]
        save_db(db)
    await robux_bank_menu(callback.message)
    await callback.answer("Ученик удалён")


@dp.callback_query(F.data == "std_export")
async def export_students_table_cb(callback: types.CallbackQuery):
    students = db.get("students", {})
    if not students:
        await callback.answer("Список пуст", show_alert=True)
        return
    sorted_stds = sorted(students.values(), key=lambda x: x["robux"], reverse=True)
    lines = ["🏆 *ТАБЛИЦА ЛИДЕРОВ (БАНК РОБАКСОВ):*\n"]
    for idx, st in enumerate(sorted_stds, 1):
        lines.append(f"{idx}. *{st['name']}* — `{st['robux']} R$` ({calc_student_rank(st['robux'])})")
    await safe_answer(callback.message, "\n".join(lines))
    await callback.answer()


# =====================================================================
# 🔍 11. ПОИСК ПО ШТАБУ, ПЛАШКИ ЧАТА И ПОЛНЫЙ БЭКАП
# =====================================================================
@dp.message(F.text == "🔍 Поиск по штабу")
async def search_hq_start(message: types.Message, state: FSMContext):
    await state.set_state(HQStates.search_query)
    await safe_answer(message, "🔍 Введи слово или фразу для поиска по всем проектам, урокам и скриптам (например: _«BillboardGui»_ или _«CanCollide»_):")


@dp.message(HQStates.search_query)
async def search_hq_done(message: types.Message, state: FSMContext):
    await state.clear()
    q = (message.text or "").strip().lower()
    if not q:
        return
    results = []
    for pid, p in db["projects"].items():
        for lid, les in p["lessons"].items():
            for p_idx, par in enumerate(les.get("paragraphs", [])):
                if q in par.lower() or q in les["title"].lower():
                    results.append(f"📁 *{p['name']}* $\\rightarrow$ 📘 *{les['title']}* (Шаг #{p_idx+1}):\n_{par[:220]}..._")
        for s in p["scripts"]:
            if q in s["title"].lower() or q in s.get("latch", "").lower() or q in s.get("luau", "").lower():
                results.append(f"📁 *{p['name']}* $\\rightarrow$ 💻 *Скрипт: {s['title']}*\n_{s.get('desc', '')}_")

    if not results:
        await safe_answer(message, f"📭 По запросу `{q}` ничего не найдено.", reply_markup=main_kb())
        return

    out = f"🔍 *Найдено совпадений ({len(results)}):*\n\n" + "\n\n---\n\n".join(results[:8])
    await safe_answer(message, out, reply_markup=main_kb())


@dp.message(F.text == "💬 Плашки чата")
async def show_history_cards(message: types.Message):
    proj = get_active_project()
    kb_top = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить заметку / сообщение в проект", callback_data="h_add_note")]
    ])
    if not proj["history"]:
        await safe_answer(
            message,
            f"📭 В проекте *{proj['name']}* пока нет записей диалога.\n"
            f"Скинь сюда файл `.md` / `.json` или добавь заметку кнопкой ниже:",
            reply_markup=kb_top
        )
        return

    await safe_answer(message, f"💬 *Последние плашки проекта «{proj['name']}» (всего: {len(proj['history'])}):*", reply_markup=kb_top)
    total = len(proj["history"])
    for i in range(max(0, total - 6), total):
        item = proj["history"][i]
        icon = "👤" if item["role"] == "user" else "🤖"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📘 Сделать из этой плашки Урок", callback_data=f"h2les_{i}")]
        ])
        preview = item["text"][:320].replace("`", "'")
        await safe_answer(message, f"*Плашка #{i+1} [{icon}]*\n{preview}...", reply_markup=kb)


@dp.callback_query(F.data == "h_add_note")
async def add_history_note_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(HQStates.add_history_note)
    await callback.message.answer("✍️ Отправь любой текст, идею или ответ нейросети для сохранения в активный проект:")
    await callback.answer()


@dp.message(HQStates.add_history_note)
async def add_history_note_done(message: types.Message, state: FSMContext):
    await state.clear()
    proj = get_active_project()
    if message.text:
        proj["history"].append({"role": "model", "text": message.text.strip()})
        save_db(db)
    await safe_answer(message, f"✅ Запись сохранена в проект *{proj['name']}*!", reply_markup=main_kb())


@dp.callback_query(F.data.startswith("h2les_"))
async def convert_history_to_lesson(callback: types.CallbackQuery, state: FSMContext):
    idx = int(callback.data.replace("h2les_", ""))
    proj = get_active_project()
    if 0 <= idx < len(proj["history"]):
        text = proj["history"][idx]["text"]
        lid = f"les_{uuid.uuid4().hex[:6]}"
        first_line = text.split("\n")[0][:35].strip("#* ") or f"Урок из плашки #{idx+1}"
        proj["lessons"][lid] = {
            "id": lid,
            "title": first_line,
            "paragraphs": split_into_paragraphs(text),
            "curr_p": 0
        }
        proj["active_lesson"] = lid
        save_db(db)
        await callback.answer("✅ Создан новый урок!")
        await show_lesson_paragraphs(callback.message, state)


@dp.message(F.text == "📥 Импорт / Экспорт")
async def import_export_menu(message: types.Message):
    proj = get_active_project()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📝 Скачать проект «{proj['name'][:18]}» в .MD", callback_data="p_export_md")],
        [InlineKeyboardButton(text="📦 Скачать ПОЛНЫЙ БЭКАП всего Штаба (.JSON)", callback_data="hq_full_backup")]
    ])
    await safe_answer(
        message,
        "📥 *ИМПОРТ И ЭКСПОРТ ШТАБА*\n\n"
        "• *Как импортировать:* просто прикрепи и отправь в этот чат любой файл `.md`, `.json`, `.txt`, `.rbxl` или скриншот — бот автоматически загрузит его в открытый проект.\n"
        "• *Как экспортировать:* выбери нужный формат выгрузки ниже:",
        reply_markup=kb
    )


@dp.callback_query(F.data == "hq_full_backup")
async def full_hq_backup_cb(callback: types.CallbackQuery):
    raw_json = json.dumps(db, ensure_ascii=False, indent=2).encode("utf-8")
    f_out = BufferedInputFile(raw_json, filename="roblox_hq_full_backup.json")
    await callback.message.answer_document(
        f_out,
        caption="📦 Полный JSON-слепок всех твоих проектов, уроков, скриптов, шаблонов и банка робаксов"
    )
    await callback.answer()


# =====================================================================
# 🔌 12. БЕЗОПАСНЫЙ ЗАПУСК С КОРРЕКТНЫМ ЗАКРЫТИЕМ СЕССИИ
# =====================================================================
async def main():
    global bot
    token = get_host_token()
    session_client = AiohttpSession(timeout=15)
    session_client._connector_init["family"] = socket.AF_INET

    bot = Bot(token=token, session=session_client)
    try:
        me = await bot.get_me()
        print(f"✅ УСПЕХ! Штаб-бот @{me.username} запущен! База данных: {DB_FILE}")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
