import asyncio
import io
import json
import os
import re
import socket
import uuid
from datetime import datetime
from dotenv import load_dotenv
import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile
)

# Опциональные парсеры для офисных файлов Алгоритмики (.pdf, .docx, .pptx)
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    import docx
except ImportError:
    docx = None

try:
    from pptx import Presentation
except ImportError:
    Presentation = None

load_dotenv()

# =====================================================================
# ⚙️ 1. КОНФИГУРАЦИЯ BOTHOST.RU И ПОСТОЯННОЙ БАЗЫ (/app/data)
# =====================================================================
DATA_DIR = os.getenv("DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)
DB_FILE = os.path.join(DATA_DIR, "universal_hub_db.json")


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

# Стандартные названия кнопок и описаний (каждый пользователь может поменять их под себя в боте!)
DEFAULT_UI = {
    "welcome_title": "⚡ Персональный Хаб и Дамп Проектов",
    "welcome_desc": "Все твои проекты, дампы файлов и личные коды привязаны к твоему аккаунту. Закидывай любые файлы прямо в чат — они сохранятся в активный проект.",
    "btn_projects": "📁 Мои проекты",
    "btn_dump": "🗄 Дамп файлов",
    "btn_reader": "📑 Читалка дампа",
    "btn_codes": "💻 База кодов",
    "btn_ai": "🤖 ИИ-Чат (по Дампу)",
    "btn_keys": "🔑 Ключи Gemini",
    "btn_search": "🔍 Поиск по базе",
    "btn_settings": "⚙️ Настройки кнопок"
}


# =====================================================================
# 🗄 2. БАЗА ДАННЫХ (ПРИВЯЗКА К ПОЛЬЗОВАТЕЛЮ + ОБЩИЕ КОДЫ)
# =====================================================================
def load_db() -> dict:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "users" in data and "public_codes" in data:
                    return data
        except Exception as e:
            print(f"⚠️ Ошибка чтения БД: {e}")
    return {
        "users": {},
        "public_codes": [],      # Общая база кодов, доступная всем пользователям
        "shared_api_keys": [],   # Общий пул ключей Gemini (на 4+ аккаунта)
        "key_cursor": 0
    }


def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Ошибка сохранения БД: {e}")


db = load_db()


def get_user(user_obj: types.User) -> dict:
    uid = str(user_obj.id)
    if uid not in db["users"]:
        pid = f"p_{uuid.uuid4().hex[:6]}"
        db["users"][uid] = {
            "id": uid,
            "username": user_obj.username or user_obj.full_name or f"User_{uid}",
            "ui": dict(DEFAULT_UI),
            "active_project": pid,
            "projects": {
                pid: {
                    "id": pid,
                    "name": "Основной проект",
                    "desc": "Чистый проект для файлов и заметок",
                    "created": datetime.now().strftime("%d.%m.%Y"),
                    "files": [],         # Все загруженные файлы и их текстовый дамп
                    "active_file": 0,    # Индекс открытого файла в читалке
                    "curr_page": 0,      # Текущий шаг/страница в читалке
                    "ai_history": []     # История диалога с ИИ внутри этого проекта
                }
            },
            "my_codes": [],              # Личные коды пользователя (чисто с нуля!)
            "personal_keys": []          # Личные ключи Gemini пользователя
        }
        save_db()
    # Подстраховка при обновлениях структуры
    u = db["users"][uid]
    for k, v in DEFAULT_UI.items():
        if k not in u.get("ui", {}):
            u.setdefault("ui", {})[k] = v
    return u


def get_active_project(u: dict) -> dict:
    pid = u.get("active_project")
    if not pid or pid not in u["projects"]:
        if not u["projects"]:
            pid = f"p_{uuid.uuid4().hex[:6]}"
            u["projects"][pid] = {
                "id": pid,
                "name": "Основной проект",
                "desc": "Чистый проект",
                "created": datetime.now().strftime("%d.%m.%Y"),
                "files": [],
                "active_file": 0,
                "curr_page": 0,
                "ai_history": []
            }
        else:
            pid = next(iter(u["projects"].keys()))
        u["active_project"] = pid
        save_db()
    return u["projects"][pid]


# =====================================================================
# 🛠 3. ИЗВЛЕЧЕНИЕ ТЕКСТА ИЗ ФАЙЛОВ АЛГОРИТМИКИ (.MD, .PDF, .DOCX, .PPTX, .JSON)
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


def split_into_pages(text: str, chunk_size: int = 700) -> list:
    if not text or not text.strip():
        return ["(В этом файле нет текстового содержимого — только бинарный оригинал для скачивания)"]
    raw_blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    merged = []
    buffer = ""
    for b in raw_blocks:
        if len(buffer) + len(b) < chunk_size:
            buffer = f"{buffer}\n\n{b}".strip() if buffer else b
        else:
            if buffer:
                merged.append(buffer)
            if len(b) > chunk_size:
                for i in range(0, len(b), chunk_size):
                    merged.append(b[i:i + chunk_size])
                buffer = ""
            else:
                buffer = b
    if buffer:
        merged.append(buffer)
    return merged if merged else [text[:chunk_size]]


def extract_text_from_bytes(file_bytes: bytes, filename: str) -> str:
    fname = filename.lower()
    # 1. Текстовые файлы, Markdown и скрипты
    if fname.endswith((".md", ".txt", ".lua", ".luau", ".py", ".csv", ".html", ".xml", ".js")):
        return file_bytes.decode("utf-8", errors="ignore").strip()

    # 2. JSON-файлы (чаты Gemini, конфиги, дампы)
    if fname.endswith(".json"):
        raw = file_bytes.decode("utf-8", errors="ignore")
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and "items" in data:
                lines = []
                for idx, item in enumerate(data.get("items", []), 1):
                    if item.get("user"):
                        lines.append(f"## Шаг {idx} [Пользователь]:\n{item['user']}")
                    if item.get("assistant"):
                        lines.append(f"## Шаг {idx} [Ответ]:\n{item['assistant']}")
                return "\n\n".join(lines)
            elif isinstance(data, list):
                lines = [f"[{i.get('role', 'item')}]: {i.get('text', str(i))}" for i in data if isinstance(i, dict)]
                if lines:
                    return "\n\n".join(lines)
        except Exception:
            pass
        return raw[:50000]

    # 3. PDF-файлы (методички и презентации)
    if fname.endswith(".pdf") and PdfReader is not None:
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            pages_txt = []
            for idx, page in enumerate(reader.pages, 1):
                t = page.extract_text()
                if t and t.strip():
                    pages_txt.append(f"--- [Слайд/Страница {idx}] ---\n{t.strip()}")
            return "\n\n".join(pages_txt)
        except Exception as e:
            return f"[Ошибка чтения PDF: {e}]"

    # 4. Word (.docx) методички
    if fname.endswith(".docx") and docx is not None:
        try:
            doc = docx.Document(io.BytesIO(file_bytes))
            paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    row_txt = " | ".join([cell.text.strip() for cell in row.cells if cell.text.strip()])
                    if row_txt:
                        paras.append(row_txt)
            return "\n\n".join(paras)
        except Exception as e:
            return f"[Ошибка чтения DOCX: {e}]"

    # 5. PowerPoint (.pptx) презентации
    if fname.endswith(".pptx") and Presentation is not None:
        try:
            prs = Presentation(io.BytesIO(file_bytes))
            slides_txt = []
            for idx, slide in enumerate(prs.slides, 1):
                s_lines = []
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        s_lines.append(shape.text.strip())
                if s_lines:
                    slides_txt.append(f"--- [Слайд {idx}] ---\n" + "\n".join(s_lines))
            return "\n\n".join(slides_txt)
        except Exception as e:
            return f"[Ошибка чтения PPTX: {e}]"

    return ""


# =====================================================================
# 🔑 4. РОТАТОР КЛЮЧЕЙ GEMINI API (4+ АККАУНТА) + ЧАТ ПО ДАМПУ ПРОЕКТА
# =====================================================================
def get_available_keys(u: dict) -> list:
    # Сначала личные ключи пользователя, затем общие ключи из пула
    keys = list(u.get("personal_keys", []))
    for k in db.get("shared_api_keys", []):
        if k not in keys:
            keys.append(k)
    return keys


def build_project_context(proj: dict, u: dict, max_chars: int = 120000) -> str:
    """Собирает весь текстовый дамп проекта + коды для отправки в контекст Gemini."""
    parts = [f"=== АКТИВНЫЙ ПРОЕКТ: {proj['name']} ===\nОписание: {proj.get('desc', '')}\n"]

    if proj.get("files"):
        parts.append("=== ЗАГРУЖЕННЫЕ В ДАМП ФАЙЛЫ И МЕТОДИЧКИ ===")
        for idx, fitem in enumerate(proj["files"], 1):
            extracted = fitem.get("extracted_text", "").strip()
            if extracted:
                parts.append(f"\n--- ФАЙЛ #{idx}: {fitem['name']} ---\n{extracted[:25000]}")
            else:
                parts.append(f"\n--- ФАЙЛ #{idx}: {fitem['name']} (Бинарный файл/Скриншот: {fitem.get('caption', '')}) ---")

    if u.get("my_codes"):
        parts.append("\n=== ЛИЧНЫЕ КОДЫ И СКРИПТЫ ПОЛЬЗОВАТЕЛЯ ===")
        for c in u["my_codes"][:15]:
            parts.append(f"• {c['title']} ({c.get('desc', '')}):\n{c.get('code', '')[:3000]}")

    full_ctx = "\n".join(parts)
    return full_ctx[:max_chars]


async def ask_gemini_with_rotation(u: dict, proj: dict, user_prompt: str, photo_bytes: bytes = None) -> str:
    keys = get_available_keys(u)
    if not keys:
        return (
            "⚠️ *Не добавлено ни одного API-ключа Gemini!*\n\n"
            "Открой меню `🔑 Ключи Gemini` и добавь 1–4 бесплатных ключа из Google AI Studio (`aistudio.google.com`), "
            "чтобы общаться с нейросетью прямо внутри бота по всему своему дампу файлов."
        )

    context_dump = build_project_context(proj, u)
    system_instruction = (
        "Ты — умный технический и методический ассистент, встроенный в закрытый хаб разработчика.\n"
        "Ниже приведён ПОЛНЫЙ ДАМП ФАЙЛОВ И КОНТЕКСТ текущего проекта пользователя.\n"
        "Опирайся на эти материалы при ответе, отвечай чётко, по делу и без воды.\n\n"
        f"{context_dump}"
    )

    # Формируем историю последних сообщений проекта
    contents = []
    for h in proj.get("ai_history", [])[-8:]:
        role = "user" if h["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": h["text"][:4000]}]})

    user_parts = [{"text": user_prompt}]
    if photo_bytes:
        import base64
        b64_img = base64.b64encode(photo_bytes).decode("utf-8")
        user_parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": b64_img
            }
        })
    contents.append({"role": "user", "parts": user_parts})

    payload = {
        "system_instruction": {"parts": [{"text": system_instruction}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.4}
    }

    models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash"]
    errors_log = []

    start_idx = db.get("key_cursor", 0) % len(keys)
    ordered_keys = keys[start_idx:] + keys[:start_idx]

    async with aiohttp.ClientSession() as session:
        for k_offset, api_key in enumerate(ordered_keys):
            key_num = ((start_idx + k_offset) % len(keys)) + 1
            for model_name in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                try:
                    async with session.post(url, json=payload, timeout=45) as resp:
                        data = await resp.json()
                        if resp.status == 200 and "candidates" in data:
                            # Сдвигаем курсор на следующий аккаунт для равномерной ротации 4 ключей
                            db["key_cursor"] = (start_idx + k_offset + 1) % len(keys)
                            save_db()
                            text_ans = data["candidates"][0]["content"]["parts"][0]["text"]
                            return f"🤖 _(Ключ #{key_num} • {model_name} • Дамп: {len(proj['files'])} файл.)_\n\n{text_ans}"
                        else:
                            err_msg = data.get("error", {}).get("message", f"HTTP {resp.status}")
                            errors_log.append(f"Ключ #{key_num} ({model_name}): {err_msg[:80]}")
                            # Если ошибка 429 (лимит квоты) или 403 — сразу пробуем следующий ключ
                            if resp.status in (429, 400, 403):
                                break
                except Exception as e:
                    errors_log.append(f"Ключ #{key_num}: {str(e)[:60]}")
                    break

    return "❌ *Все ключи в пуле вернули ошибку или исчерпали лимит:*\n" + "\n".join(errors_log[:5])


# =====================================================================
# 🎛 5. КЛАВИАТУРА И СОСТОЯНИЯ (С ЗАЩИТОЙ ОТ ЗАВИСАНИЯ МЕНЮ)
# =====================================================================
class HubStates(StatesGroup):
    # Проекты
    new_proj_name = State()
    new_proj_desc = State()
    rename_proj = State()
    # Читалка дампа (редактирование текста файла)
    edit_page_text = State()
    add_text_note = State()
    # База кодов (Личные + Общие)
    code_title = State()
    code_desc = State()
    code_body = State()
    code_edit_val = State()
    # ИИ-Чат по дампу
    ai_chat_mode = State()
    # Ключи Gemini
    add_api_key = State()
    # Поиск
    search_query = State()
    # Настройки кнопок и текстов
    edit_ui_val = State()


def get_main_kb(u: dict):
    ui = u["ui"]
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=ui["btn_projects"]), KeyboardButton(text=ui["btn_dump"])],
            [KeyboardButton(text=ui["btn_reader"]), KeyboardButton(text=ui["btn_codes"])],
            [KeyboardButton(text=ui["btn_ai"]), KeyboardButton(text=ui["btn_keys"])],
            [KeyboardButton(text=ui["btn_search"]), KeyboardButton(text=ui["btn_settings"])]
        ],
        resize_keyboard=True
    )


def cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить ввод", callback_data="cancel_state")]
    ])


@dp.callback_query(F.data == "cancel_state", StateFilter("*"))
async def cancel_state_cb(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    u = get_user(callback.from_user)
    await callback.answer("Ввод отменён")
    await safe_answer(callback.message, "✅ Действие отменено. Выбери нужный раздел в меню:", reply_markup=get_main_kb(u))


# =====================================================================
# 🛡 6. ГЛАВНЫЙ ПЕРЕХВАТЧИК КНОПОК МЕНЮ (РАБОТАЕТ В ЛЮБОМ СОСТОЯНИИ!)
# =====================================================================
@dp.message(Command("start", "menu", "cancel"), StateFilter("*"))
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    u = get_user(message.from_user)
    proj = get_active_project(u)
    ui = u["ui"]
    keys_count = len(get_available_keys(u))

    await safe_answer(
        message,
        f"*{ui['welcome_title']}*\n"
        f"_{ui['welcome_desc']}_\n\n"
        f"👤 *Профиль:* `{u['username']}`\n"
        f"📁 *Активный проект:* `{proj['name']}`\n"
        f"🗄 *Файлов в дампе проекта:* *{len(proj['files'])}*\n"
        f"💻 *Кодов:* Моих: *{len(u['my_codes'])}* | Доступных всем: *{len(db['public_codes'])}*\n"
        f"🔑 *Активных ключей Gemini в пуле:* *{keys_count}*",
        reply_markup=get_main_kb(u)
    )


def is_menu_button(message: types.Message) -> bool:
    if not message.text or not message.from_user:
        return False
    u = get_user(message.from_user)
    return message.text in u["ui"].values()


@dp.message(is_menu_button, StateFilter("*"))
async def handle_any_menu_button(message: types.Message, state: FSMContext):
    """Перехватывает нажатие любой нижней кнопки даже внутри незавершённого ввода, чтобы бот НИКОГДА не зависал!"""
    await state.clear()
    u = get_user(message.from_user)
    ui = u["ui"]
    txt = message.text

    if txt == ui["btn_projects"]:
        await open_projects_menu(message, u)
    elif txt == ui["btn_dump"]:
        await open_dump_menu(message, u)
    elif txt == ui["btn_reader"]:
        await open_reader_menu(message, u)
    elif txt == ui["btn_codes"]:
        await open_codes_menu(message, u)
    elif txt == ui["btn_ai"]:
        await open_ai_chat_mode(message, u, state)
    elif txt == ui["btn_keys"]:
        await open_keys_menu(message, u)
    elif txt == ui["btn_search"]:
        await state.set_state(HubStates.search_query)
        await safe_answer(
            message,
            "🔍 *ПОИСК ПО БАЗЕ*\nВведи слово или фразу — я найду совпадения во всех твоих дампах файлов, методичках и в базе кодов:",
            reply_markup=cancel_kb()
        )
    elif txt == ui["btn_settings"]:
        await open_settings_menu(message, u)


# =====================================================================
# 📁 7. МОИ ПРОЕКТЫ (ЛИЧНЫЕ ПАПКИ ПОД КУРСЫ И ЗАДАЧИ)
# =====================================================================
async def open_projects_menu(message: types.Message, u: dict):
    proj = get_active_project(u)
    buttons = []
    for pid, p in u["projects"].items():
        mark = "✅ " if pid == u["active_project"] else "📁 "
        buttons.append([InlineKeyboardButton(
            text=f"{mark}{p['name']} (Файлов: {len(p['files'])})",
            callback_data=f"psel_{pid}"
        )])

    buttons.append([
        InlineKeyboardButton(text="➕ Создать проект", callback_data="p_new"),
        InlineKeyboardButton(text="✏️ Переименовать", callback_data="p_ren")
    ])
    buttons.append([
        InlineKeyboardButton(text="📥 Выгрузить дамп проекта (.MD)", callback_data="p_exp"),
        InlineKeyboardButton(text="🗑 Удалить проект", callback_data="p_del")
    ])

    await safe_answer(
        message,
        f"📁 *МОИ ПРОЕКТЫ (ЛИЧНОЕ ПРОСТРАНСТВО)*\n\n"
        f"Сейчас открыт: *{proj['name']}*\n"
        f"Описание: _{proj.get('desc', '—')}_\n"
        f"Файлов в дампе: *{len(proj['files'])}*\n\n"
        f"Выбери проект для переключения или создай новый:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@dp.callback_query(F.data.startswith("psel_"))
async def select_proj_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    pid = callback.data.replace("psel_", "")
    if pid in u["projects"]:
        u["active_project"] = pid
        save_db()
        await callback.answer(f"Открыт: {u['projects'][pid]['name']}")
        await open_projects_menu(callback.message, u)


@dp.callback_query(F.data == "p_new")
async def new_proj_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(HubStates.new_proj_name)
    await safe_answer(callback.message, "📁 Введи *название нового проекта* (например: _«Алгоритмика: Геймдизайн»_):", reply_markup=cancel_kb())
    await callback.answer()


@dp.message(HubStates.new_proj_name)
async def new_proj_name_step(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(HubStates.new_proj_desc)
    await safe_answer(message, "📝 Введи *описание проекта* (или отправь `-`, чтобы пропустить):", reply_markup=cancel_kb())


@dp.message(HubStates.new_proj_desc)
async def new_proj_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    u = get_user(message.from_user)
    pid = f"p_{uuid.uuid4().hex[:6]}"
    desc = "" if message.text.strip() == "-" else message.text.strip()
    u["projects"][pid] = {
        "id": pid,
        "name": data["name"],
        "desc": desc,
        "created": datetime.now().strftime("%d.%m.%Y"),
        "files": [],
        "active_file": 0,
        "curr_page": 0,
        "ai_history": []
    }
    u["active_project"] = pid
    save_db()
    await safe_answer(
        message,
        f"✅ Проект *{data['name']}* создан и выбран!\nТеперь можешь просто пересылать или скидывать сюда любые файлы — они попадут в дамп этого проекта.",
        reply_markup=get_main_kb(u)
    )


@dp.callback_query(F.data == "p_ren")
async def ren_proj_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(HubStates.rename_proj)
    await safe_answer(callback.message, "✏️ Введи новое название для текущего проекта:", reply_markup=cancel_kb())
    await callback.answer()


@dp.message(HubStates.rename_proj)
async def ren_proj_done(message: types.Message, state: FSMContext):
    await state.clear()
    u = get_user(message.from_user)
    proj = get_active_project(u)
    if message.text:
        proj["name"] = message.text.strip()
        save_db()
    await safe_answer(message, f"✅ Проект переименован в *{proj['name']}*!", reply_markup=get_main_kb(u))


@dp.callback_query(F.data == "p_del")
async def del_proj_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if len(u["projects"]) <= 1:
        await callback.answer("⚠️ Нельзя удалить единственный проект!", show_alert=True)
        return
    pid = u["active_project"]
    del u["projects"][pid]
    u["active_project"] = next(iter(u["projects"].keys()))
    save_db()
    await callback.answer("Проект удалён")
    await open_projects_menu(callback.message, u)


@dp.callback_query(F.data == "p_exp")
async def exp_proj_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    out = [f"# 📁 ПРОЕКТ: {proj['name']}\nОписание: {proj.get('desc', '')}\n"]
    for idx, f in enumerate(proj["files"], 1):
        out.append(f"## 📄 Файл #{idx}: {f['name']} ({f.get('date', '')})\n")
        if f.get("extracted_text"):
            out.append(f["extracted_text"] + "\n\n---\n")
    md_bytes = "\n".join(out).encode("utf-8")
    doc_file = BufferedInputFile(md_bytes, filename=f"dump_{proj['id']}.md")
    await callback.message.answer_document(doc_file, caption=f"📥 Полный текстовый дамп проекта «{proj['name']}»")
    await callback.answer()


# =====================================================================
# 🗄 8. ДАМП ХРАНЕНИЯ ФАЙЛОВ (МАССОВАЯ ЗАГРУЗКА ЛЮБЫХ ФАЙЛОВ И СКРИНОВ)
# =====================================================================
async def open_dump_menu(message: types.Message, u: dict):
    proj = get_active_project(u)
    buttons = []
    for idx, fitem in enumerate(proj["files"][-15:], max(0, len(proj["files"]) - 15)):
        icon = "📸" if fitem["type"] == "photo" else ("📄" if fitem.get("extracted_text") else "📦")
        buttons.append([
            InlineKeyboardButton(text=f"{icon} #{idx+1} {fitem['name'][:28]}", callback_data=f"fvw_{idx}"),
            InlineKeyboardButton(text="📥", callback_data=f"fdl_{idx}"),
            InlineKeyboardButton(text="🗑", callback_data=f"fdel_{idx}")
        ])

    buttons.append([InlineKeyboardButton(text="➕ Добавить текстовую заметку в дамп", callback_data="f_add_note")])
    if proj["files"]:
        buttons.append([
            InlineKeyboardButton(text="📥 Выгрузить весь дамп (.MD)", callback_data="p_exp"),
            InlineKeyboardButton(text="🧹 Очистить дамп проекта", callback_data="f_clear_all")
        ])

    await safe_answer(
        message,
        f"🗄 *ДАМП ФАЙЛОВ ПРОЕКТА «{proj['name']}»*\n\n"
        f"Всего загружено файлов: *{len(proj['files'])}*\n"
        f"• *Как загрузить:* просто выдели и отправь в этот чат сколько угодно файлов (`.pdf`, `.docx`, `.pptx`, `.md`, `.json`, `.txt`, `.rbxl`, `.zip` или скриншотов).\n"
        f"• Текст из документов автоматически индексируется для ИИ-чата и читалки.\n"
        f"• Нажми на файл ниже, чтобы открыть его в читалке, `📥` — чтобы скачать оригинал:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@dp.message(F.document, StateFilter("*"))
async def handle_any_document_dump(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    proj = get_active_project(u)
    doc = message.document
    fname = doc.file_name or f"file_{len(proj['files'])+1}"

    extracted_text = ""
    # Скачиваем и индексируем текст, если файл до 20 МБ и текстового/офисного формата
    if doc.file_size and doc.file_size < 19 * 1024 * 1024:
        if fname.lower().endswith((".md", ".txt", ".json", ".lua", ".luau", ".py", ".csv", ".pdf", ".docx", ".pptx", ".html")):
            try:
                tg_file = await bot.get_file(doc.file_id)
                file_bytes = (await bot.download_file(tg_file.file_path)).read()
                extracted_text = extract_text_from_bytes(file_bytes, fname)
            except Exception as e:
                extracted_text = f"[Не удалось извлечь текст: {e}]"

    pages = split_into_pages(extracted_text) if extracted_text else []
    proj["files"].append({
        "type": "doc",
        "file_id": doc.file_id,
        "name": fname,
        "caption": message.caption or "",
        "extracted_text": extracted_text,
        "pages": pages,
        "date": datetime.now().strftime("%d.%m %H:%M")
    })
    proj["active_file"] = len(proj["files"]) - 1
    proj["curr_page"] = 0
    save_db()

    idx = len(proj["files"]) - 1
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📑 Читать по шагам", callback_data=f"fvw_{idx}"),
            InlineKeyboardButton(text="🤖 Спросить ИИ по файлу", callback_data=f"fai_{idx}")
        ]
    ])
    status_txt = f"Извлечено текста: *{len(extracted_text)} симв.* ({len(pages)} стр.)" if extracted_text else "Сохранён как бинарный файл"
    await safe_answer(
        message,
        f"✅ *Файл `{fname}` добавлен в дамп проекта «{proj['name']}»!*\n"
        f"📊 {status_txt}",
        reply_markup=kb
    )


@dp.message(F.photo, StateFilter("*"))
async def handle_any_photo_dump(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    proj = get_active_project(u)
    photo = message.photo[-1]
    caption = message.caption or f"Скриншот #{len(proj['files'])+1}"

    # Если пользователь сейчас находится в режиме ИИ-чата — сразу отправляем скриншот в Gemini Vision!
    curr_state = await state.get_state()
    if curr_state == HubStates.ai_chat_mode.state:
        wait_msg = await message.answer("⏳ Анализирую скриншот с учётом дампа проекта...")
        tg_file = await bot.get_file(photo.file_id)
        photo_bytes = (await bot.download_file(tg_file.file_path)).read()
        ans = await ask_gemini_with_rotation(u, proj, caption, photo_bytes=photo_bytes)
        await wait_msg.delete()
        await send_long_text(message, ans)
        return

    proj["files"].append({
        "type": "photo",
        "file_id": photo.file_id,
        "name": caption[:35],
        "caption": caption,
        "extracted_text": f"[Скриншот: {caption}]",
        "pages": [f"📸 Скриншот: {caption}"],
        "date": datetime.now().strftime("%d.%m %H:%M")
    })
    save_db()
    idx = len(proj["files"]) - 1
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Разebрать этот скриншот через ИИ", callback_data=f"fvision_{idx}")]
    ])
    await safe_answer(
        message,
        f"📸 *Скриншот сохранён в дамп проекта «{proj['name']}»!*\n📝 Подпись: _{caption}_",
        reply_markup=kb
    )


@dp.callback_query(F.data.startswith("fvision_"))
async def analyze_saved_photo_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    idx = int(callback.data.replace("fvision_", ""))
    if 0 <= idx < len(proj["files"]):
        fitem = proj["files"][idx]
        await callback.answer("Отправляю скриншот в Gemini...")
        wait_msg = await callback.message.answer("⏳ Разбираю скриншот с контекстом твоего дампа...")
        tg_file = await bot.get_file(fitem["file_id"])
        photo_bytes = (await bot.download_file(tg_file.file_path)).read()
        prompt = fitem.get("caption") or "Разбери подробно, что на этом скриншоте, и если есть ошибка — напиши, как исправить."
        ans = await ask_gemini_with_rotation(u, proj, prompt, photo_bytes=photo_bytes)
        await wait_msg.delete()
        await send_long_text(callback.message, ans)


@dp.callback_query(F.data.startswith("fdl_"))
async def download_dump_file_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    idx = int(callback.data.replace("fdl_", ""))
    if 0 <= idx < len(proj["files"]):
        fitem = proj["files"][idx]
        if fitem["type"] == "photo":
            await callback.message.answer_photo(fitem["file_id"], caption=f"📸 {fitem['name']}")
        elif fitem.get("file_id"):
            await callback.message.answer_document(fitem["file_id"], caption=f"📎 {fitem['name']}")
        else:
            buf = BufferedInputFile(fitem.get("extracted_text", "").encode("utf-8"), filename=f"{fitem['name']}.md")
            await callback.message.answer_document(buf)
    await callback.answer()


@dp.callback_query(F.data.startswith("fdel_"))
async def delete_dump_file_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    idx = int(callback.data.replace("fdel_", ""))
    if 0 <= idx < len(proj["files"]):
        removed = proj["files"].pop(idx)
        proj["active_file"] = max(0, len(proj["files"]) - 1)
        save_db()
        await callback.answer(f"Удалено: {removed['name']}")
        await open_dump_menu(callback.message, u)


@dp.callback_query(F.data == "f_clear_all")
async def clear_project_dump_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    proj["files"] = []
    proj["active_file"] = 0
    proj["curr_page"] = 0
    save_db()
    await callback.answer("Дамп проекта очищен")
    await open_dump_menu(callback.message, u)


@dp.callback_query(F.data == "f_add_note")
async def add_text_note_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(HubStates.add_text_note)
    await safe_answer(callback.message, "📝 Отправь любой текст, конспект или методичку — она сохранится как файл в дампе проекта:", reply_markup=cancel_kb())
    await callback.answer()


@dp.message(HubStates.add_text_note)
async def add_text_note_done(message: types.Message, state: FSMContext):
    await state.clear()
    u = get_user(message.from_user)
    proj = get_active_project(u)
    if message.text:
        txt = message.text.strip()
        title = txt.split("\n")[0][:30].strip("#* ") or f"Заметка #{len(proj['files'])+1}"
        proj["files"].append({
            "type": "note",
            "file_id": None,
            "name": title,
            "caption": "",
            "extracted_text": txt,
            "pages": split_into_pages(txt),
            "date": datetime.now().strftime("%d.%m %H:%M")
        })
        proj["active_file"] = len(proj["files"]) - 1
        proj["curr_page"] = 0
        save_db()
    await safe_answer(message, "✅ Заметка сохранена в дамп проекта!", reply_markup=get_main_kb(u))
    await open_reader_menu(message, u)


# =====================================================================
# 📑 9. ЧИТАЛКА И РЕДАКТОР ДАМПА ПО СТРАНИЦАМ / АБЗАЦАМ
# =====================================================================
async def open_reader_menu(message: types.Message, u: dict):
    proj = get_active_project(u)
    if not proj["files"]:
        await safe_answer(
            message,
            f"📭 В дампе проекта *{proj['name']}* пока нет файлов.\n"
            f"Просто скинь сюда любой файл (`.md`, `.docx`, `.pptx`, `.pdf`, `.json`, `.txt`)!"
        )
        return

    f_idx = min(proj.get("active_file", 0), len(proj["files"]) - 1)
    proj["active_file"] = f_idx
    fitem = proj["files"][f_idx]
    pages = fitem.get("pages") or split_into_pages(fitem.get("extracted_text", ""))
    fitem["pages"] = pages

    p_idx = min(proj.get("curr_page", 0), len(pages) - 1)
    proj["curr_page"] = p_idx
    page_text = pages[p_idx]

    await safe_answer(
        message,
        f"📁 *{proj['name']}* $\\rightarrow$ 📄 *{fitem['name']}*\n"
        f"📑 *Страница {p_idx+1} из {len(pages)}:*\n\n{page_text}",
        reply_markup=get_reader_kb(f_idx, p_idx, len(pages), len(proj["files"]))
    )


def get_reader_kb(f_idx: int, p_idx: int, total_pages: int, total_files: int):
    nav = []
    if p_idx > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Пред.", callback_data=f"rnav_{p_idx-1}"))
    nav.append(InlineKeyboardButton(text=f"📄 {p_idx+1}/{total_pages}", callback_data="r_noop"))
    if p_idx < total_pages - 1:
        nav.append(InlineKeyboardButton(text="След. ➡️", callback_data=f"rnav_{p_idx+1}"))

    edit_row = [
        InlineKeyboardButton(text="✏️ Править страницу", callback_data=f"redit_{p_idx}"),
        InlineKeyboardButton(text="📥 Скачать оригинал", callback_data=f"fdl_{f_idx}")
    ]
    file_switch = [
        InlineKeyboardButton(text=f"🗄 Выбрать другой файл дампа ({total_files})", callback_data="r_all_files")
    ]
    return InlineKeyboardMarkup(inline_keyboard=[nav, edit_row, file_switch])


@dp.callback_query(F.data == "r_noop")
async def r_noop_cb(callback: types.CallbackQuery):
    await callback.answer()


@dp.callback_query(F.data == "r_all_files")
async def r_all_files_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    await open_dump_menu(callback.message, u)
    await callback.answer()


@dp.callback_query(F.data.startswith("fvw_"))
async def open_specific_file_in_reader(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    idx = int(callback.data.replace("fvw_", ""))
    if 0 <= idx < len(proj["files"]):
        proj["active_file"] = idx
        proj["curr_page"] = 0
        save_db()
        await open_reader_menu(callback.message, u)
    await callback.answer()


@dp.callback_query(F.data.startswith("rnav_"))
async def reader_navigate_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    p_idx = int(callback.data.replace("rnav_", ""))
    f_idx = proj.get("active_file", 0)
    if 0 <= f_idx < len(proj["files"]):
        fitem = proj["files"][f_idx]
        pages = fitem.get("pages", [])
        if 0 <= p_idx < len(pages):
            proj["curr_page"] = p_idx
            save_db()
            await safe_edit(
                callback.message,
                f"📁 *{proj['name']}* $\\rightarrow$ 📄 *{fitem['name']}*\n"
                f"📑 *Страница {p_idx+1} из {len(pages)}:*\n\n{pages[p_idx]}",
                reply_markup=get_reader_kb(f_idx, p_idx, len(pages), len(proj["files"]))
            )
    await callback.answer()


@dp.callback_query(F.data.startswith("redit_"))
async def reader_edit_page_start(callback: types.CallbackQuery, state: FSMContext):
    p_idx = int(callback.data.replace("redit_", ""))
    await state.update_data(p_idx=p_idx)
    await state.set_state(HubStates.edit_page_text)
    await safe_answer(callback.message, f"✏️ Отправь новый текст для *Страницы #{p_idx+1}*:", reply_markup=cancel_kb())
    await callback.answer()


@dp.message(HubStates.edit_page_text)
async def reader_edit_page_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    u = get_user(message.from_user)
    proj = get_active_project(u)
    f_idx = proj.get("active_file", 0)
    p_idx = data.get("p_idx", 0)
    if 0 <= f_idx < len(proj["files"]) and message.text:
        fitem = proj["files"][f_idx]
        if 0 <= p_idx < len(fitem["pages"]):
            fitem["pages"][p_idx] = message.text.strip()
            fitem["extracted_text"] = "\n\n".join(fitem["pages"])
            save_db()
    await safe_answer(message, "✅ Текст страницы обновлён!", reply_markup=get_main_kb(u))
    await open_reader_menu(message, u)


# =====================================================================
# 💻 10. БАЗА КОДОВ (ЛИЧНЫЕ ПОЛЬЗОВАТЕЛЯ + ОБЩИЕ ДОСТУПНЫЕ ВСЕМ)
# =====================================================================
async def open_codes_menu(message: types.Message, u: dict, tab: str = "my"):
    buttons = []
    tab_switch = [
        InlineKeyboardButton(
            text=("🟢 👤 Мои коды" if tab == "my" else "👤 Мои коды") + f" ({len(u['my_codes'])})",
            callback_data="ctab_my"
        ),
        InlineKeyboardButton(
            text=("🟢 🌐 Доступные всем" if tab == "pub" else "🌐 Доступные всем") + f" ({len(db['public_codes'])})",
            callback_data="ctab_pub"
        )
    ]
    buttons.append(tab_switch)

    if tab == "my":
        for idx, c in enumerate(u["my_codes"]):
            pub_icon = "🌐" if c.get("is_public") else "🔒"
            buttons.append([InlineKeyboardButton(
                text=f"{pub_icon} {c['title']}",
                callback_data=f"cmy_{idx}"
            )])
        buttons.append([InlineKeyboardButton(text="➕ Написать / добавить свой код", callback_data="c_new")])
        desc_text = (
            "💻 *МОЯ ЛИЧНАЯ БАЗА КОДОВ*\n\n"
            "Здесь хранятся только твои скрипты и заготовки (🔒). Ты можешь в любой момент изменить их код, описание или опубликовать в общую базу (🌐), чтобы другие пользователи бота тоже могли их посмотреть."
        )
    else:
        for idx, c in enumerate(db["public_codes"]):
            buttons.append([InlineKeyboardButton(
                text=f"🌐 {c['title']} (от @{c.get('author_name', 'user')})",
                callback_data=f"cpub_{idx}"
            )])
        buttons.append([InlineKeyboardButton(text="➕ Добавить свой код", callback_data="c_new")])
        desc_text = (
            "🌐 *ОБЩАЯ БАЗА КОДОВ (ДОСТУПНЫЕ ВСЕМ)*\n\n"
            "Здесь лежат коды, которыми поделились участники бота. Любой код можно открыть, скопировать или забрать себе в «Мои коды» и отредактировать под себя!"
        )

    await safe_answer(message, desc_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@dp.callback_query(F.data.startswith("ctab_"))
async def switch_code_tab_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    tab = callback.data.replace("ctab_", "")
    await open_codes_menu(callback.message, u, tab=tab)
    await callback.answer()


@dp.callback_query(F.data == "c_new")
async def new_code_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(HubStates.code_title)
    await safe_answer(callback.message, "💻 Введи *название нового кода / скрипта*:", reply_markup=cancel_kb())
    await callback.answer()


@dp.message(HubStates.code_title)
async def new_code_title_step(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(HubStates.code_desc)
    await safe_answer(message, "📝 Введи *описание или инструкцию* (как использовать этот код, или `-` чтобы пропустить):", reply_markup=cancel_kb())


@dp.message(HubStates.code_desc)
async def new_code_desc_step(message: types.Message, state: FSMContext):
    desc = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(desc=desc)
    await state.set_state(HubStates.code_body)
    await safe_answer(message, "💻 Теперь отправь *сам текст кода / скрипта*:", reply_markup=cancel_kb())


@dp.message(HubStates.code_body)
async def new_code_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    u = get_user(message.from_user)
    cid = f"code_{uuid.uuid4().hex[:6]}"
    u["my_codes"].append({
        "id": cid,
        "title": data["title"],
        "desc": data["desc"],
        "code": (message.text or "").strip(),
        "author_id": u["id"],
        "author_name": u["username"],
        "is_public": False
    })
    save_db()
    await safe_answer(message, f"✅ Код *{data['title']}* сохранён в твои личные коды!", reply_markup=get_main_kb(u))
    await open_codes_menu(message, u, tab="my")


@dp.callback_query(F.data.startswith("cmy_"))
async def view_my_code_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("cmy_", ""))
    if not (0 <= idx < len(u["my_codes"])):
        await callback.answer("Не найдено")
        return

    c = u["my_codes"][idx]
    pub_label = "🔒 Убрать из общих" if c.get("is_public") else "🌐 Опубликовать в общие"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Изм. код", callback_data=f"ced_{idx}_code"),
            InlineKeyboardButton(text="📝 Изм. описание", callback_data=f"ced_{idx}_desc"),
            InlineKeyboardButton(text="🏷 Название", callback_data=f"ced_{idx}_title")
        ],
        [
            InlineKeyboardButton(text=pub_label, callback_data=f"cpubtoggle_{idx}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"cdel_{idx}")
        ],
        [InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="ctab_my")]
    ])

    status = "🌐 Опубликован (доступен всем)" if c.get("is_public") else "🔒 Личный (видишь только ты)"
    text = (
        f"📌 *{c['title']}*\n"
        f"Статус: _{status}_\n"
        f"Описание: _{c.get('desc') or '—'}_\n\n"
        f"```lua\n{c.get('code', '')}\n```"
    )
    await safe_answer(callback.message, text, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("cpubtoggle_"))
async def toggle_code_public_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("cpubtoggle_", ""))
    if 0 <= idx < len(u["my_codes"]):
        c = u["my_codes"][idx]
        c["is_public"] = not c.get("is_public", False)
        # Синхронизируем с общей базой public_codes
        db["public_codes"] = [x for x in db["public_codes"] if x.get("id") != c["id"]]
        if c["is_public"]:
            db["public_codes"].append(dict(c))
            await callback.answer("🌐 Код опубликован в общую базу!", show_alert=True)
        else:
            await callback.answer("🔒 Код скрыт из общей базы (теперь только личный).", show_alert=True)
        save_db()
        callback.data = f"cmy_{idx}"
        await view_my_code_cb(callback)


@dp.callback_query(F.data.startswith("ced_"))
async def edit_my_code_start(callback: types.CallbackQuery, state: FSMContext):
    _, idx_str, field = callback.data.split("_")
    await state.update_data(c_idx=int(idx_str), c_field=field)
    await state.set_state(HubStates.code_edit_val)
    labels = {"code": "новый текст кода", "desc": "новое описание", "title": "новое название"}
    await safe_answer(callback.message, f"✏️ Отправь *{labels.get(field, 'новое значение')}*:", reply_markup=cancel_kb())
    await callback.answer()


@dp.message(HubStates.code_edit_val)
async def edit_my_code_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    u = get_user(message.from_user)
    idx = data.get("c_idx", 0)
    field = data.get("c_field", "code")
    if 0 <= idx < len(u["my_codes"]) and message.text:
        c = u["my_codes"][idx]
        c[field] = message.text.strip()
        # Если код опубликован — обновляем его и в общей базе
        for pub_c in db["public_codes"]:
            if pub_c.get("id") == c["id"]:
                pub_c[field] = c[field]
        save_db()
    await safe_answer(message, "✅ Код успешно обновлён!", reply_markup=get_main_kb(u))
    await open_codes_menu(message, u, tab="my")


@dp.callback_query(F.data.startswith("cdel_"))
async def delete_my_code_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("cdel_", ""))
    if 0 <= idx < len(u["my_codes"]):
        c = u["my_codes"].pop(idx)
        db["public_codes"] = [x for x in db["public_codes"] if x.get("id") != c["id"]]
        save_db()
        await callback.answer("Код удалён")
        await open_codes_menu(callback.message, u, tab="my")


@dp.callback_query(F.data.startswith("cpub_"))
async def view_public_code_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("cpub_", ""))
    if not (0 <= idx < len(db["public_codes"])):
        await callback.answer("Не найдено")
        return

    c = db["public_codes"][idx]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Скопировать себе в «Мои коды» (для правки)", callback_data=f"cfork_{idx}")],
        [InlineKeyboardButton(text="⬅️ Назад к общим кодам", callback_data="ctab_pub")]
    ])
    text = (
        f"🌐 *{c['title']}*\n"
        f"Автор: `@{c.get('author_name', 'user')}`\n"
        f"Описание: _{c.get('desc') or '—'}_\n\n"
        f"```lua\n{c.get('code', '')}\n```"
    )
    await safe_answer(callback.message, text, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("cfork_"))
async def fork_public_code_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("cfork_", ""))
    if 0 <= idx < len(db["public_codes"]):
        orig = db["public_codes"][idx]
        u["my_codes"].append({
            "id": f"code_{uuid.uuid4().hex[:6]}",
            "title": f"{orig['title']} (моя копия)",
            "desc": orig.get("desc", ""),
            "code": orig.get("code", ""),
            "author_id": u["id"],
            "author_name": u["username"],
            "is_public": False
        })
        save_db()
        await callback.answer("✅ Скопировано в «Мои коды»! Теперь можешь менять его под себя.", show_alert=True)
        await open_codes_menu(callback.message, u, tab="my")


# =====================================================================
# 🤖 11. ИИ-ЧАТ ПО ДАМПУ ПРОЕКТА И ПУЛ КЛЮЧЕЙ GEMINI (4+ АККАУНТА)
# =====================================================================
async def send_long_text(message: types.Message, text: str):
    if len(text) <= 3900:
        await safe_answer(message, text)
    else:
        for i in range(0, len(text), 3800):
            await safe_answer(message, text[i:i + 3800])


async def open_ai_chat_mode(message: types.Message, u: dict, state: FSMContext):
    proj = get_active_project(u)
    keys = get_available_keys(u)
    await state.set_state(HubStates.ai_chat_mode)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧹 Очистить историю диалога с ИИ", callback_data="ai_clear_hist")],
        [InlineKeyboardButton(text="❌ Выйти из режима ИИ-чата", callback_data="cancel_state")]
    ])
    await safe_answer(
        message,
        f"🤖 *РЕЖИМ ПРЯМОГО ЧАТА С GEMINI ПО ДАМПУ ПРОЕКТА*\n\n"
        f"• *Открытый проект:* `{proj['name']}`\n"
        f"• *Подключено файлов из дампа:* *{len(proj['files'])} шт.*\n"
        f"• *Ключей в ротации:* *{len(keys)} шт.*\n\n"
        f"✍️ *Пиши любой вопрос, задачу или скидывай скриншот прямо сюда* — нейросеть уже видит все загруженные в этот проект файлы и коды!\n"
        f"_(Чтобы переключиться в другое меню — просто нажми любую кнопку внизу)_",
        reply_markup=kb
    )


@dp.callback_query(F.data.startswith("fai_"))
async def ask_ai_about_file_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    await callback.answer()
    await open_ai_chat_mode(callback.message, u, state)


@dp.callback_query(F.data == "ai_clear_hist", StateFilter("*"))
async def clear_ai_hist_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    proj["ai_history"] = []
    save_db()
    await callback.answer("История диалога с ИИ очищена!", show_alert=True)


@dp.message(HubStates.ai_chat_mode, F.text)
async def handle_ai_chat_message(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    proj = get_active_project(u)
    user_q = message.text.strip()

    wait_msg = await message.answer(f"⏳ Gemini читает дамп «{proj['name']}» ({len(proj['files'])} файл.) и пишет ответ...")
    answer_text = await ask_gemini_with_rotation(u, proj, user_q)
    await wait_msg.delete()

    proj.setdefault("ai_history", []).append({"role": "user", "text": user_q})
    proj["ai_history"].append({"role": "model", "text": answer_text})
    save_db()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💾 Сохранить этот ответ как файл в Дамп", callback_data="ai_save_last")]
    ])
    await send_long_text(message, answer_text)
    await message.answer("👆 Действия с ответом:", reply_markup=kb)


@dp.callback_query(F.data == "ai_save_last", StateFilter("*"))
async def save_last_ai_to_dump_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    if proj.get("ai_history"):
        last_ans = proj["ai_history"][-1]["text"]
        title = f"Ответ ИИ ({datetime.now().strftime('%H:%M')})"
        proj["files"].append({
            "type": "note",
            "file_id": None,
            "name": title,
            "caption": "",
            "extracted_text": last_ans,
            "pages": split_into_pages(last_ans),
            "date": datetime.now().strftime("%d.%m %H:%M")
        })
        save_db()
        await callback.answer("✅ Ответ сохранён в Дамп файлов проекта!", show_alert=True)
    else:
        await callback.answer("Нет последнего ответа")


async def open_keys_menu(message: types.Message, u: dict):
    p_keys = u.get("personal_keys", [])
    s_keys = db.get("shared_api_keys", [])

    buttons = []
    for idx, k in enumerate(p_keys):
        masked = f"{k[:8]}...{k[-4:]}"
        buttons.append([InlineKeyboardButton(text=f"🔒 Личный ключ #{idx+1} ({masked}) — Удалить", callback_data=f"kdel_p_{idx}")])

    for idx, k in enumerate(s_keys):
        masked = f"{k[:8]}...{k[-4:]}"
        buttons.append([InlineKeyboardButton(text=f"🌐 Общий ключ #{idx+1} ({masked}) — Удалить", callback_data=f"kdel_s_{idx}")])

    buttons.append([
        InlineKeyboardButton(text="➕ Добавить личный ключ", callback_data="kadd_p"),
        InlineKeyboardButton(text="➕ Добавить в общий пул (на всех)", callback_data="kadd_s")
    ])

    await safe_answer(
        message,
        f"🔑 *ПУЛ КЛЮЧЕЙ GEMINI API (АВТО-РОТАЦИЯ 4+ АККАУНТОВ)*\n\n"
        f"• *Личных ключей:* *{len(p_keys)}*\n"
        f"• *Общих ключей в пуле:* *{len(s_keys)}*\n\n"
        f"💡 _Ты можешь создать 4 бесплатных ключа на разных Google-аккаунтах в [Google AI Studio](https://aistudio.google.com/apikey) и закинуть их сюда (по одному или сразу списком через перенос строки). Бот будет автоматически чередовать их по кругу и переключаться при лимитах!_",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@dp.callback_query(F.data.in_(["kadd_p", "kadd_s"]))
async def add_key_start(callback: types.CallbackQuery, state: FSMContext):
    ktype = "personal" if callback.data == "kadd_p" else "shared"
    await state.update_data(ktype=ktype)
    await state.set_state(HubStates.add_api_key)
    await safe_answer(
        callback.message,
        "🔑 Отправь один или сразу несколько ключей `AIzaSy...` (каждый с новой строки):",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.add_api_key)
async def add_key_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    u = get_user(message.from_user)
    ktype = data.get("ktype", "personal")

    raw_lines = [line.strip() for line in (message.text or "").splitlines() if line.strip().startswith("AIza")]
    if not raw_lines:
        await safe_answer(message, "⚠️ Ключи Gemini должны начинаться с `AIza...`. Попробуй ещё раз.", reply_markup=get_main_kb(u))
        return

    target_list = u.setdefault("personal_keys", []) if ktype == "personal" else db.setdefault("shared_api_keys", [])
    added = 0
    for k in raw_lines:
        if k not in target_list:
            target_list.append(k)
            added += 1
    save_db()
    await safe_answer(message, f"✅ Добавлено ключей в ротацию: *{added} шт.*!", reply_markup=get_main_kb(u))
    await open_keys_menu(message, u)


@dp.callback_query(F.data.startswith("kdel_"))
async def del_key_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    _, mode, idx_str = callback.data.split("_")
    idx = int(idx_str)
    target = u.get("personal_keys", []) if mode == "p" else db.get("shared_api_keys", [])
    if 0 <= idx < len(target):
        target.pop(idx)
        save_db()
        await callback.answer("Ключ удалён")
        await open_keys_menu(callback.message, u)


# =====================================================================
# 🔍 12. УМНЫЙ ПОИСК ПО ДАМПАМ ФАЙЛОВ И КОДАМ
# =====================================================================
@dp.message(HubStates.search_query)
async def search_query_done(message: types.Message, state: FSMContext):
    await state.clear()
    u = get_user(message.from_user)
    q = (message.text or "").strip().lower()
    if not q:
        return

    found = []
    # Поиск по всем проектам и файлам пользователя
    for pid, p in u["projects"].items():
        for f_idx, fitem in enumerate(p["files"]):
            txt = fitem.get("extracted_text", "")
            if q in fitem["name"].lower() or q in txt.lower():
                pos = txt.lower().find(q)
                snippet = txt[max(0, pos - 60):pos + 140].replace("\n", " ") if pos != -1 else fitem.get("caption", "")
                found.append(f"📁 *{p['name']}* $\\rightarrow$ 📄 *{fitem['name']}*:\n`...{snippet}...`")

    # Поиск по личным и общим кодам
    for c in u["my_codes"] + db["public_codes"]:
        if q in c["title"].lower() or q in c.get("code", "").lower() or q in c.get("desc", "").lower():
            found.append(f"💻 *Код: {c['title']}*\n_{c.get('desc', '')}_")

    if not found:
        await safe_answer(message, f"📭 По запросу `{q}` ничего не найдено.", reply_markup=get_main_kb(u))
        return

    await safe_answer(
        message,
        f"🔍 *Найдено совпадений ({len(found)}):*\n\n" + "\n\n---\n\n".join(found[:10]),
        reply_markup=get_main_kb(u)
    )


# =====================================================================
# ⚙️ 13. НАСТРОЙКА НАЗВАНИЙ КНОПОК И ОПИСАНИЙ САМИМ ПОЛЬЗОВАТЕЛЕМ
# =====================================================================
UI_LABELS = {
    "welcome_title": "Заголовок приветствия (/start)",
    "welcome_desc": "Описание под приветствием",
    "btn_projects": "Кнопка 1 (Проекты)",
    "btn_dump": "Кнопка 2 (Дамп файлов)",
    "btn_reader": "Кнопка 3 (Читалка)",
    "btn_codes": "Кнопка 4 (База кодов)",
    "btn_ai": "Кнопка 5 (ИИ-Чат)",
    "btn_keys": "Кнопка 6 (Ключи Gemini)",
    "btn_search": "Кнопка 7 (Поиск)",
    "btn_settings": "Кнопка 8 (Настройки)"
}


async def open_settings_menu(message: types.Message, u: dict):
    ui = u["ui"]
    buttons = []
    for k, label in UI_LABELS.items():
        curr_val = ui.get(k, "")[:22]
        buttons.append([InlineKeyboardButton(text=f"✏️ {label}: «{curr_val}»", callback_data=f"uied_{k}")])

    buttons.append([InlineKeyboardButton(text="🔄 Сбросить названия по умолчанию", callback_data="ui_reset")])

    await safe_answer(
        message,
        "⚙️ *НАСТРОЙКА КНОПОК И ОПИСАНИЙ ИНТЕРФЕЙСА*\n\n"
        "Нажми на любую кнопку или текст ниже, чтобы переименовать их под себя:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@dp.callback_query(F.data.startswith("uied_"))
async def edit_ui_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    ui_key = callback.data.replace("uied_", "")
    if ui_key in UI_LABELS:
        await state.update_data(ui_key=ui_key)
        await state.set_state(HubStates.edit_ui_val)
        await safe_answer(
            callback.message,
            f"✏️ Текущее значение ({UI_LABELS[ui_key]}):\n`{u['ui'].get(ui_key, '')}`\n\nОтправь новое название/текст:",
            reply_markup=cancel_kb()
        )
    await callback.answer()


@dp.message(HubStates.edit_ui_val)
async def edit_ui_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    u = get_user(message.from_user)
    ui_key = data.get("ui_key")
    if ui_key and message.text:
        u["ui"][ui_key] = message.text.strip()
        save_db()
    await safe_answer(message, "✅ Интерфейс и кнопки обновлены!", reply_markup=get_main_kb(u))
    await open_settings_menu(message, u)


@dp.callback_query(F.data == "ui_reset")
async def reset_ui_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    u["ui"] = dict(DEFAULT_UI)
    save_db()
    await callback.answer("Настройки сброшены по умолчанию")
    await safe_answer(callback.message, "🔄 Стандартные названия кнопок восстановлены!", reply_markup=get_main_kb(u))


# =====================================================================
# 🔌 14. ЗАПУСК БОТА
# =====================================================================
async def main():
    global bot
    token = get_host_token()
    session_client = AiohttpSession(timeout=20)
    session_client._connector_init["family"] = socket.AF_INET

    bot = Bot(token=token, session=session_client)
    try:
        me = await bot.get_me()
        print(f"✅ УСПЕХ! Универсальный хаб @{me.username} запущен!")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
