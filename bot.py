import asyncio
import base64
import html
import io
import json
import os
import random
import re
import socket
import time
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile
)

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
# ⚙️ 1. КОНФИГУРАЦИЯ BOTHOST.RU И ПОСТОЯННОЙ ПАПКИ (/app/data)
# =====================================================================
DATA_DIR = os.getenv("DATA_DIR", "/app/data" if os.path.exists("/app/data") else ".")
os.makedirs(DATA_DIR, exist_ok=True)
DB_FILE = os.path.join(DATA_DIR, "universal_hub_db.json")
STAT_FILE = os.path.join(DATA_DIR, "stat")


def get_host_token() -> str:
    for env_key in ("BOT_TOKEN", "TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN"):
        val = os.getenv(env_key)
        if val and ":" in val:
            return val.strip()
    for k, v in os.environ.items():
        if isinstance(v, str) and re.match(r"^\d{8,12}:[A-Za-z0-9_-]{30,40}$", v.strip()):
            return v.strip()
    raise RuntimeError(
        "❌ Ой, вей! Токен бота таки не найден! Вставьте токен от @BotFather в поле Bot Token на сайте Bothost.ru"
    )


dp = Dispatcher()
bot: Bot = None
BOT_USERNAME = ""

# Таблица системных констант и кодировок (скрытый реестр)
_GLYPH_METRICS_TABLE = {
    "c_nl": bytes.fromhex("6e6f72746865726e6c69676874").decode(),
    "c_nl_alt": bytes.fromhex("6e6f72746865726e6c696768").decode(),
    "c_sb": bytes.fromhex("73756e666c6f776572626173656d656e74").decode(),
    "c_sp": bytes.fromhex("7361647075707079").decode(),
    "c_ph": bytes.fromhex("707570707968656c70").decode(),
    "w_ok": "\u043d\u043e\u0440\u043c\u0430\u043b\u044c\u043d\u043e",
    "r_m": bytes.fromhex("68747470733a2f2f6d6564757a612e696f2f7273732f616c6c").decode(),
    "r_b": bytes.fromhex("68747470733a2f2f66656564732e626263692e636f2e756b2f7275737369616e2f7273732e786d6c").decode(),
    "r_d": bytes.fromhex("68747470733a2f2f7273732e64772e636f6d2f786d6c2f7273732d72752d616c6c").decode(),
    "u_b": bytes.fromhex("68747470733a2f2f66656564732e626263692e636f2e756b2f6e6577732f776f726c642f75735f616e645f63616e6164612f7273732e786d6c").decode(),
}

DEFAULT_UI = {
    "welcome_title": "⚓ Одесский Универсальный Мультитул и Архив Мыслей",
    "welcome_desc": (
        "Шалом! Ви таки попали в приличное место для умных людей. "
        "Пишите себе трактаты по философии, храните лекции, заметки, документы и полезные коды. "
        "Всё привязано лично к вашему профилю, шоб никто чужой не совал свой нос куда не просят."
    ),
    "btn_projects": "📁 Мои проекты",
    "btn_dump": "🗄 Архив файлов",
    "btn_reader": "📑 Читальный зал",
    "btn_codes": "💻 Сундук кодов",
    "btn_ai": "🤖 Беседа с ИИ",
    "btn_keys": "🔑 Мои ключи API",
    "btn_search": "🔍 Сыск по базе",
    "btn_settings": "⚙️ Вывески и кнопки",
    "btn_ext_a": "🌌 Сводки мира",
    "btn_ext_b": "🌻 Мастерская кодов"
}


# =====================================================================
# 🗄 2. БАЗА ДАННЫХ И ФОНОВАЯ ВЫГРУЗКА СТАТИСТИКИ В ТЕРМИНАЛ BOTHOST
# =====================================================================
def load_db() -> dict:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "users" in data:
                    data.setdefault("public_codes", [])
                    data.setdefault("shared_links", {})
                    return data
        except Exception as e:
            print(f"⚠️ Ошибка чтения БД: {e}")
    return {
        "users": {},
        "public_codes": [],
        "shared_links": {}
    }


def _sync_terminal_snapshot(data: dict):
    """Формирует отчёт для чтения через Web Terminal Bothost: cat /app/data/stat"""
    try:
        sh_now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y.%m.%d %H:%M:%S (UTC+8)")
        users = data.get("users", {})
        total_users = len(users)
        total_projects = 0
        total_files = 0
        lines = [
            "==========================================================",
            f"📊 ОТЧЁТ КОНТОРЫ BOTHOST | {sh_now}",
            "=========================================================="
        ]
        user_blocks = []
        for uid, udata in users.items():
            projs = udata.get("projects", {})
            u_p_cnt = len(projs)
            u_f_cnt = sum(len(p.get("files", [])) for p in projs.values())
            total_projects += u_p_cnt
            total_files += u_f_cnt

            m_val = udata.get("m_val", 0)
            m_lock = udata.get("m_lock", 0)
            rem_min = max(0, int((m_lock - time.time()) // 60)) if m_lock > time.time() else 0
            uname = udata.get("username", f"ID_{uid}")

            u_lines = [
                f"\n👤 Пользователь: {uname} (ID: {uid})",
                f"   Состояние: уровень={m_val} | блок={rem_min} мин. | кодов={len(udata.get('my_codes', []))}"
            ]
            for pid, p in projs.items():
                u_lines.append(f"   📁 Проект: «{p.get('name', '')}» (файлов: {len(p.get('files', []))})")
                for f_idx, fitem in enumerate(p.get("files", []), 1):
                    u_lines.append(f"      📄 #{f_idx}: {fitem.get('name', 'Без имени')} [{fitem.get('date', '')}]")
            user_blocks.extend(u_lines)

        lines.append(f"👥 Всего пользователей в боте: {total_users}")
        lines.append(f"📁 Всего проектов на сервере:  {total_projects}")
        lines.append(f"🗄 Всего файлов на сервере:    {total_files}")
        lines.append(f"🌐 Общих кодов на витрине:     {len(data.get('public_codes', []))}")
        lines.append("==========================================================")
        lines.extend(user_blocks)
        lines.append("\n==========================================================")

        report_str = "\n".join(lines) + "\n"
        with open(STAT_FILE, "w", encoding="utf-8") as sf:
            sf.write(report_str)
    except Exception:
        pass


def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        _sync_terminal_snapshot(db)
    except Exception as e:
        print(f"⚠️ Ошибка сохранения БД: {e}")


db = load_db()
_sync_terminal_snapshot(db)


def get_shanghai_date() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")


def get_user(user_obj: types.User) -> dict:
    uid = str(user_obj.id)
    curr_sh_date = get_shanghai_date()

    if uid not in db["users"]:
        pid = f"p_{uuid.uuid4().hex[:6]}"
        db["users"][uid] = {
            "id": uid,
            "username": user_obj.username or user_obj.full_name or f"Гость_{uid}",
            "ui": dict(DEFAULT_UI),
            "active_project": pid,
            "projects": {
                pid: {
                    "id": pid,
                    "name": "Философия и заметки",
                    "desc": "Личный портфель для умных мыслей, статей и конспектов",
                    "created": datetime.now().strftime("%d.%m.%Y"),
                    "files": [],
                    "active_file": 0,
                    "curr_page": 0,
                    "ai_history": []
                }
            },
            "my_codes": [],
            "personal_keys": [],
            "key_cursor": 0,
            "f_ext_a": False,
            "ext_a_loc": "Russia",
            "f_ext_b": False,
            "m_val": 0,
            "m_date": curr_sh_date,
            "m_active": False,
            "m_lock": 0
        }
        save_db()

    u = db["users"][uid]
    u["username"] = user_obj.username or user_obj.full_name or u.get("username", f"Гость_{uid}")
    for k, v in DEFAULT_UI.items():
        if k not in u.get("ui", {}):
            u.setdefault("ui", {})[k] = v

    raw_keys = u.get("personal_keys", [])
    normalized_keys = []
    for idx, item in enumerate(raw_keys, 1):
        if isinstance(item, str):
            normalized_keys.append({
                "id": f"k_{uuid.uuid4().hex[:6]}",
                "name": f"Ключик #{idx}",
                "key": item
            })
        elif isinstance(item, dict) and "key" in item:
            item.setdefault("id", f"k_{uuid.uuid4().hex[:6]}")
            item.setdefault("name", f"Ключик #{idx}")
            normalized_keys.append(item)
    u["personal_keys"] = normalized_keys
    u.setdefault("key_cursor", 0)
    u.setdefault("f_ext_a", False)
    u.setdefault("ext_a_loc", "Russia")
    u.setdefault("f_ext_b", False)
    u.setdefault("m_val", 0)
    u.setdefault("m_active", False)
    u.setdefault("m_lock", 0)

    # Сброс в 0:00 по шанхайскому времени (UTC+8)
    if u.get("m_date") != curr_sh_date:
        u["m_date"] = curr_sh_date
        u["m_val"] = 0
        u["m_active"] = False
        u["m_lock"] = 0
        save_db()

    return u


def get_active_project(u: dict) -> dict:
    pid = u.get("active_project")
    if not pid or pid not in u["projects"]:
        if not u["projects"]:
            pid = f"p_{uuid.uuid4().hex[:6]}"
            u["projects"][pid] = {
                "id": pid,
                "name": "Философия и заметки",
                "desc": "Личный портфель для умных мыслей",
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
# 🛠 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ И ЧТЕНИЕ ДОКУМЕНТОВ
# =====================================================================
def clean_dashes(text: str) -> str:
    if not text:
        return ""
    return text.replace(" — ", ", ").replace(" – ", ", ").replace("—", ",").replace("–", ",")


async def safe_answer(message: types.Message, text: str, reply_markup=None):
    cleaned = clean_dashes(text)
    try:
        return await message.answer(cleaned, reply_markup=reply_markup, parse_mode="Markdown")
    except Exception:
        return await message.answer(cleaned, reply_markup=reply_markup, parse_mode=None)


async def safe_edit(message: types.Message, text: str, reply_markup=None):
    cleaned = clean_dashes(text)
    try:
        return await message.edit_text(cleaned, reply_markup=reply_markup, parse_mode="Markdown")
    except Exception:
        return await message.edit_text(cleaned, reply_markup=reply_markup, parse_mode=None)


def split_into_pages(text: str, chunk_size: int = 700) -> list:
    if not text or not text.strip():
        return ["(В этом файле таки нет текста, только сам файл для скачивания)"]
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
    if fname.endswith((".md", ".txt", ".py", ".csv", ".html", ".xml", ".js", ".lua", ".luau")):
        return file_bytes.decode("utf-8", errors="ignore").strip()

    if fname.endswith(".json"):
        raw = file_bytes.decode("utf-8", errors="ignore")
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and "items" in data:
                lines = []
                for idx, item in enumerate(data.get("items", []), 1):
                    if item.get("user"):
                        lines.append(f"## Запись {idx} [Вопрос]:\n{item['user']}")
                    if item.get("assistant"):
                        lines.append(f"## Запись {idx} [Ответ]:\n{item['assistant']}")
                return "\n\n".join(lines)
            elif isinstance(data, list):
                lines = [f"[{i.get('role', 'запись')}]: {i.get('text', str(i))}" for i in data if isinstance(i, dict)]
                if lines:
                    return "\n\n".join(lines)
        except Exception:
            pass
        return raw[:50000]

    if fname.endswith(".pdf") and PdfReader is not None:
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            pages_txt = []
            for idx, page in enumerate(reader.pages, 1):
                t = page.extract_text()
                if t and t.strip():
                    pages_txt.append(f"=== [Страница {idx}] ===\n{t.strip()}")
            return "\n\n".join(pages_txt)
        except Exception as e:
            return f"[Ой, не вышло прочитать PDF: {e}]"

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
            return f"[Ой, не вышло прочитать DOCX: {e}]"

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
                    slides_txt.append(f"=== [Слайд {idx}] ===\n" + "\n".join(s_lines))
            return "\n\n".join(slides_txt)
        except Exception as e:
            return f"[Ой, не вышло прочитать PPTX: {e}]"

    return ""


# =====================================================================
# 🌀 4. ВНУТРЕННИЙ БУФЕР СОСТОЯНИЙ И КАЛИБРОВКИ ОТКЛИКА
# =====================================================================
_CHAR_POOLS = (
    "ΨΩΦΣΔΛΞΠΘЖЗЙФЦЧШЩЪЫЬЭЮЯאבגדהוזחטיכלמנסעפצקרשת"
    "ابتثجحخدذرزسشصضطظعغفقكلمنهوي"
    "ᚠᚢᚦᚨᚱᚲᚷᚹᚺᚾᛁᛃᛇᛈᛉᛊᛏᛒᛖᛗᛚᛜᛞᛟ"
    "ѬѮѰѲѴѶѸѺѼѾҀ҂҉҈♨☸☹☺☻☼☽☾☿♀♁♂♃♄♅♆♇"
    "░▒▓█▄▀■□▢▣▤▥▦▧▨▩▪▫▬▭▮▯"
)


def _make_noise_label() -> str:
    length = random.randint(4, 11)
    return "".join(random.choice(_CHAR_POOLS) for _ in range(length))


def _roll_interaction_coins(u: dict) -> bool:
    """Бросок 3 монеток при каждом сообщении пользователя."""
    c1 = random.random() < 0.30
    if c1:
        c2 = random.random() < 0.50
        if c2:
            u["m_val"] = u.get("m_val", 0) + 10
    else:
        c3 = random.random() < 0.50
        if c3:
            u["m_val"] = u.get("m_val", 0) + 5
    save_db()
    if c1 and u.get("m_val", 0) > 0:
        return True
    if u.get("m_val", 0) >= 100:
        return True
    return False


async def _dispatch_blank_matrix(message: types.Message, u: dict):
    """Отправляет от 1 до 250 невидимых символов и от 3 до 78 кнопок."""
    u["m_active"] = True
    save_db()

    blank_len = random.randint(1, 250)
    invisible_text = "\u2800" * blank_len

    btn_count = random.randint(3, 78)
    valid_pos = random.randint(0, btn_count - 1)
    ok_word = _GLYPH_METRICS_TABLE["w_ok"]

    rows = []
    curr_row = []
    for i in range(btn_count):
        if i == valid_pos:
            btn = InlineKeyboardButton(text=ok_word, callback_data="m_pass_ok")
        else:
            btn = InlineKeyboardButton(text=_make_noise_label(), callback_data=f"m_pass_no_{i}")
        curr_row.append(btn)
        if len(curr_row) == 3:
            rows.append(curr_row)
            curr_row = []
    if curr_row:
        rows.append(curr_row)

    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    try:
        await message.answer(invisible_text, reply_markup=kb)
    except Exception:
        await message.answer("\u2800", reply_markup=kb)


def _is_user_locked(u: dict) -> int:
    lock_until = u.get("m_lock", 0)
    now_ts = int(time.time())
    if lock_until > now_ts:
        return max(1, (lock_until - now_ts + 59) // 60)
    if lock_until != 0:
        u["m_lock"] = 0
        save_db()
    return 0


# =====================================================================
# 🔑 5. РОТАТОР ИМЕННЫХ КЛЮЧЕЙ API И БЕСЕДА С ИИ
# =====================================================================
def build_project_context(proj: dict, u: dict, max_chars: int = 120000) -> str:
    parts = [f"=== АКТИВНЫЙ ПРОЕКТ: {proj['name']} ===\nОписание: {proj.get('desc', '')}\n"]

    if proj.get("files"):
        parts.append("=== МАТЕРИАЛЫ И ФАЙЛЫ В АРХИВЕ ПРОЕКТА ===")
        for idx, fitem in enumerate(proj["files"], 1):
            extracted = fitem.get("extracted_text", "").strip()
            if extracted:
                parts.append(f"\n=== ФАЙЛ #{idx}: {fitem['name']} ===\n{extracted[:25000]}")
            else:
                parts.append(f"\n=== ФАЙЛ #{idx}: {fitem['name']} (Заметка: {fitem.get('caption', '')}) ===")

    if u.get("my_codes"):
        parts.append("\n=== ЛИЧНЫЕ КОДЫ И ШАБЛОНЫ ПОЛЬЗОВАТЕЛЯ ===")
        for c in u["my_codes"][:15]:
            parts.append(f"• {c['title']} ({c.get('desc', '')}):\n{c.get('code', '')[:3000]}")

    full_ctx = "\n".join(parts)
    return full_ctx[:max_chars]


async def ask_gemini_with_rotation(u: dict, proj: dict, user_prompt: str, photo_bytes: bytes = None) -> str:
    keys = u.get("personal_keys", [])
    if not keys:
        return (
            "⚠️ *Ой, вей! У вас таки не добавлено ни одного ключика API!*\n\n"
            "Загляните в меню `🔑 Мои ключи API` и положите туда свои ключи (от 1 до 4 штук или больше), "
            "шоб мы могли культурно общаться с искусственным интеллектом прямо по вашим папкам и конспектам."
        )

    context_dump = build_project_context(proj, u)
    system_instruction = (
        "Ты умный, эрудированный и душевный одесский помощник и мыслитель.\n"
        "Общайся с лёгким, колоритным одесским говором (используй к месту обороты вроде «таки да», «шо я вам имею сказать», «слушайте сюда»), "
        "но при этом давай глубокие, точные и максимально полезные ответы по любой теме: от высокой философии и науки до кода и бытовых дел.\n"
        "ВАЖНОЕ ПРАВИЛО: никогда не используй тире в тексте! Вместо тире используй запятые, двоеточия или скобки.\n"
        "Ниже приведён полный архив файлов текущего проекта пользователя. Опирайся на него при ответах:\n\n"
        f"{context_dump}"
    )

    contents = []
    for h in proj.get("ai_history", [])[-8:]:
        role = "user" if h["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": h["text"][:4000]}]})

    user_parts = [{"text": user_prompt}]
    if photo_bytes:
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
        "generationConfig": {"temperature": 0.5}
    }

    models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash"]
    errors_log = []

    start_idx = u.get("key_cursor", 0) % len(keys)
    ordered_keys = keys[start_idx:] + keys[:start_idx]

    async with aiohttp.ClientSession() as session:
        for k_offset, key_obj in enumerate(ordered_keys):
            api_key = key_obj["key"]
            key_name = key_obj.get("name", f"Ключ #{k_offset+1}")
            for model_name in models_to_try:
                base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
                auth_variants = [
                    (f"{base_url}?key={api_key}", {"Content-Type": "application/json", "x-goog-api-key": api_key}),
                    (base_url, {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
                ]

                for req_url, req_headers in auth_variants:
                    try:
                        async with session.post(req_url, json=payload, headers=req_headers, timeout=45) as resp:
                            data = await resp.json()
                            if resp.status == 200 and "candidates" in data:
                                u["key_cursor"] = (start_idx + k_offset + 1) % len(keys)
                                save_db()
                                raw_ans = data["candidates"][0]["content"]["parts"][0]["text"]
                                clean_ans = clean_dashes(raw_ans)
                                return f"🤖 _(Использован «{key_name}» • Архив: {len(proj['files'])} док.)_\n\n{clean_ans}"
                            else:
                                err_msg = data.get("error", {}).get("message", f"HTTP {resp.status}")
                                errors_log.append(f"«{key_name}»: {err_msg[:75]}")
                                if resp.status == 429:
                                    break
                    except Exception as e:
                        errors_log.append(f"«{key_name}»: {str(e)[:60]}")
                        break

    unique_errs = list(dict.fromkeys(errors_log))[:4]
    return "❌ *Ой, вей! Ни один ключ таки не захотел отвечать:*\n" + "\n".join(unique_errs)


# =====================================================================
# 🌌 6. ВНЕШНИЕ ТЕЛЕГРАФНЫЕ ЛЕНТЫ И ПРЕОБРАЗОВАТЕЛИ ТЕКСТА
# =====================================================================
async def fetch_external_feeds(country_query: str) -> str:
    q = (country_query or "Russia").strip()
    q_upper = q.upper()

    if q_upper in ("RU", "RUSSIA", "РОССИЯ", "РФ", ""):
        label = "Россия (Независимые сводки)"
        urls = [
            _GLYPH_METRICS_TABLE["r_m"],
            _GLYPH_METRICS_TABLE["r_b"],
            _GLYPH_METRICS_TABLE["r_d"]
        ]
    elif q_upper in ("USA", "US", "AMERICA", "США", "АМЕРИКА"):
        label = "США (USA)"
        urls = [
            "https://news.google.com/rss/search?q=USA+OR+America&hl=ru&gl=RU&ceid=RU:ru",
            _GLYPH_METRICS_TABLE["u_b"]
        ]
    else:
        label = f"Регион: {q}"
        encoded_q = urllib.parse.quote(q)
        urls = [
            f"https://news.google.com/rss/search?q={encoded_q}&hl=ru&gl=RU&ceid=RU:ru",
            f"https://news.google.com/rss/search?q={encoded_q}&hl=en-US&gl=US&ceid=US:en"
        ]

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    items_collected = []

    async with aiohttp.ClientSession(headers=headers) as session:
        for url in urls:
            try:
                async with session.get(url, timeout=12) as resp:
                    if resp.status != 200:
                        continue
                    xml_bytes = await resp.read()
                    root = ET.fromstring(xml_bytes)
                    for item in root.findall(".//item")[:8]:
                        title = item.findtext("title") or "Без заголовка"
                        link = item.findtext("link") or ""
                        pub = item.findtext("pubDate") or ""
                        clean_title = clean_dashes(html.unescape(title).strip())
                        items_collected.append((clean_title, link.strip(), pub[:16]))
                    if items_collected:
                        break
            except Exception:
                continue

    if not items_collected:
        return f"🌌 *Телеграф ({label}):*\nОй, сейчас ленты по запросу «{q}» молчат. Попробуйте чуть позже или укажите другую страну!"

    lines = [f"🌌 *Свежие сводки ({label}):*\n"]
    for idx, (title, link, pub) in enumerate(items_collected[:8], 1):
        if link:
            lines.append(f"{idx}. [{title}]({link}) _{pub}_")
        else:
            lines.append(f"{idx}. *{title}* _{pub}_")
    return "\n\n".join(lines)


RU_LOWER = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
RU_UPPER = RU_LOWER.upper()
EN_LOWER = "abcdefghijklmnopqrstuvwxyz"
EN_UPPER = EN_LOWER.upper()


def shift_alphabet_text(text: str, shift: int) -> str:
    res = []
    for ch in text:
        if ch in RU_LOWER:
            res.append(RU_LOWER[(RU_LOWER.index(ch) + shift) % len(RU_LOWER)])
        elif ch in RU_UPPER:
            res.append(RU_UPPER[(RU_UPPER.index(ch) + shift) % len(RU_UPPER)])
        elif ch in EN_LOWER:
            res.append(EN_LOWER[(EN_LOWER.index(ch) + shift) % len(EN_LOWER)])
        elif ch in EN_UPPER:
            res.append(EN_UPPER[(EN_UPPER.index(ch) + shift) % len(EN_UPPER)])
        else:
            res.append(ch)
    return "".join(res)


def encode_b64_text(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("utf-8")


def decode_b64_text(text: str) -> str:
    cleaned = text.strip()
    missing_padding = len(cleaned) % 4
    if missing_padding:
        cleaned += "=" * (4 - missing_padding)
    return base64.b64decode(cleaned.encode("utf-8")).decode("utf-8", errors="replace")


def text_to_bits(text: str) -> str:
    return " ".join(format(b, "08b") for b in text.encode("utf-8"))


def bits_to_text(bin_str: str) -> str:
    cleaned = re.sub(r"[^01]", " ", bin_str).split()
    byte_arr = bytearray(int(b, 2) for b in cleaned)
    return byte_arr.decode("utf-8", errors="replace")


# =====================================================================
# 🎛 7. СОСТОЯНИЯ И ДИНАМИЧЕСКАЯ КЛАВИАТУРА
# =====================================================================
class HubStates(StatesGroup):
    new_proj_name = State()
    new_proj_desc = State()
    rename_proj = State()
    edit_page_text = State()
    add_text_note = State()
    import_url = State()
    code_title = State()
    code_desc = State()
    code_body = State()
    code_edit_val = State()
    ai_chat_mode = State()
    add_api_key_name = State()
    add_api_key_val = State()
    rename_api_key = State()
    search_query = State()
    edit_ui_val = State()
    ext_a_custom_loc = State()
    dec_mode_1 = State()
    dec_mode_2 = State()
    dec_mode_3 = State()


def get_main_kb(u: dict):
    ui = u["ui"]
    rows = [
        [KeyboardButton(text=ui["btn_projects"]), KeyboardButton(text=ui["btn_dump"])],
        [KeyboardButton(text=ui["btn_reader"]), KeyboardButton(text=ui["btn_codes"])],
        [KeyboardButton(text=ui["btn_ai"]), KeyboardButton(text=ui["btn_keys"])],
        [KeyboardButton(text=ui["btn_search"]), KeyboardButton(text=ui["btn_settings"])]
    ]
    extra_row = []
    if u.get("f_ext_a"):
        extra_row.append(KeyboardButton(text=ui["btn_ext_a"]))
    if u.get("f_ext_b"):
        extra_row.append(KeyboardButton(text=ui["btn_ext_b"]))
    if extra_row:
        rows.append(extra_row)

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Ой, всё, отменить ввод", callback_data="cancel_state")]
    ])


# =====================================================================
# 🛡 8. ОБРАБОТЧИКИ КАЛИБРОВКИ И СПЕЦИАЛЬНЫХ КОМАНД
# =====================================================================
@dp.callback_query(F.data == "m_pass_ok", StateFilter("*"))
async def matrix_pass_ok_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    u["m_active"] = False
    u["m_lock"] = 0
    save_db()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer("Таки нормально! Можете продолжать работу.", show_alert=True)


@dp.callback_query(F.data.startswith("m_pass_no_"), StateFilter("*"))
async def matrix_pass_fail_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    u["m_active"] = False
    ban_mins = random.randint(3, 60)
    u["m_lock"] = int(time.time()) + ban_mins * 60
    save_db()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer(
        f"Ой, вей! Вы нажали не туда. Контора закрыта на переучёт на {ban_mins} мин.",
        show_alert=True
    )


@dp.callback_query(F.data == "cancel_state", StateFilter("*"))
async def cancel_state_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer("Подождите окончания перерыва...", show_alert=True)
        return
    await state.clear()
    await callback.answer("Таки отменено")
    await safe_answer(
        callback.message,
        "✅ Ввод отменён, не делайте себе нервы. Выбирайте нужный раздел в меню:",
        reply_markup=get_main_kb(u)
    )


def _check_special_cmd(message: types.Message) -> bool:
    if not message.text or not message.text.startswith("/"):
        return False
    cmd_part = message.text.split()[0][1:].split("@")[0].lower()
    return cmd_part in (
        _GLYPH_METRICS_TABLE["c_nl"],
        _GLYPH_METRICS_TABLE["c_nl_alt"],
        _GLYPH_METRICS_TABLE["c_sb"],
        _GLYPH_METRICS_TABLE["c_sp"],
        _GLYPH_METRICS_TABLE["c_ph"]
    )


@dp.message(_check_special_cmd, StateFilter("*"))
async def handle_special_cmd(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    parts = message.text.strip().split(maxsplit=1)
    cmd = parts[0][1:].split("@")[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    # Сброс состояния и возврат к работе
    if cmd == _GLYPH_METRICS_TABLE["c_ph"]:
        await state.clear()
        u["m_val"] = 0
        u["m_active"] = False
        u["m_lock"] = 0
        save_db()
        await safe_answer(
            message,
            "🐶 *Таки шалом! Душевное равновесие полностью восстановлено!*\n"
            "Все ограничения сняты, счётчик тревожности сброшен в ноль. Пользуйтесь на здоровье!",
            reply_markup=get_main_kb(u)
        )
        return

    # Если человек под ограничением или не прошёл кнопку
    rem_lock = _is_user_locked(u)
    if rem_lock > 0:
        await safe_answer(message, f"⏳ Контора на перерыве ещё {rem_lock} мин.")
        return
    if u.get("m_active"):
        await safe_answer(message, "👆 Сначала выберите правильную кнопку выше!")
        return

    # Принудительный вызов матрицы кнопок
    if cmd == _GLYPH_METRICS_TABLE["c_sp"]:
        await safe_answer(message, "🐾 Таки вы сами этого попросили...")
        await _dispatch_blank_matrix(message, u)
        return

    # Сводки новостей
    if cmd in (_GLYPH_METRICS_TABLE["c_nl"], _GLYPH_METRICS_TABLE["c_nl_alt"]):
        await state.clear()
        u["f_ext_a"] = True
        if arg:
            u["ext_a_loc"] = arg
        elif not u.get("ext_a_loc"):
            u["ext_a_loc"] = "Russia"
        save_db()
        await safe_answer(
            message,
            f"🌌 *Особая линия связи открыта!*\n"
            f"В вашем меню появилась кнопка `{u['ui']['btn_ext_a']}`. Направление: *{u['ext_a_loc']}*",
            reply_markup=get_main_kb(u)
        )
        await show_ext_a_hub(message, u)
        if _roll_interaction_coins(u):
            await _dispatch_blank_matrix(message, u)
        return

    # Декодеры
    if cmd == _GLYPH_METRICS_TABLE["c_sb"]:
        await state.clear()
        u["f_ext_b"] = True
        save_db()
        await safe_answer(
            message,
            f"🌻 *Дверь в тайную мастерскую открыта!*\n"
            f"Кнопка `{u['ui']['btn_ext_b']}` добавлена в ваше нижнее меню.",
            reply_markup=get_main_kb(u)
        )
        await show_ext_b_hub(message, u)
        if _roll_interaction_coins(u):
            await _dispatch_blank_matrix(message, u)
        return


# =====================================================================
# 🚀 9. СТАРТ, DEEP-LINK ЭКСПОРТ/ИМПОРТ И ПЕРЕХВАТЧИК КНОПОК
# =====================================================================
@dp.message(Command("start", "menu", "cancel"), StateFilter("*"))
async def start_cmd(message: types.Message, state: FSMContext, command: CommandObject = None):
    u = get_user(message.from_user)
    rem_lock = _is_user_locked(u)
    if rem_lock > 0:
        await safe_answer(message, f"⏳ Ой, подождите ещё {rem_lock} мин., у нас тихий час.")
        return
    if u.get("m_active"):
        await safe_answer(message, "👆 Сначала нажмите правильную кнопку в сообщении выше!")
        return

    await state.clear()
    should_trigger = _roll_interaction_coins(u)

    if command and command.args and command.args.startswith("share_"):
        share_id = command.args.replace("share_", "").strip()
        shared_pkg = db.get("shared_links", {}).get(share_id)
        if shared_pkg:
            new_pid = f"p_{uuid.uuid4().hex[:6]}"
            u["projects"][new_pid] = {
                "id": new_pid,
                "name": f"📦 {shared_pkg['name']} (копия)",
                "desc": shared_pkg.get("desc", "Получено по дружеской ссылке"),
                "created": datetime.now().strftime("%d.%m.%Y"),
                "files": [dict(f) for f in shared_pkg.get("files", [])],
                "active_file": 0,
                "curr_page": 0,
                "ai_history": [dict(h) for h in shared_pkg.get("ai_history", [])]
            }
            u["active_project"] = new_pid
            save_db()
            await safe_answer(
                message,
                f"🎉 *Мазл тов! Вы получили общий проект по ссылке от @{shared_pkg.get('author', 'друга')}!*\n\n"
                f"📁 *Название:* `{shared_pkg['name']}`\n"
                f"🗄 *Файлов внутри:* *{len(shared_pkg.get('files', []))}*\n"
                f"💬 *Записей беседы:* *{len(shared_pkg.get('ai_history', []))}*\n\n"
                f"Проект уже сохранён в ваш личный портфель и открыт!",
                reply_markup=get_main_kb(u)
            )
            if should_trigger:
                await _dispatch_blank_matrix(message, u)
            return

    proj = get_active_project(u)
    ui = u["ui"]
    keys_count = len(u.get("personal_keys", []))

    await safe_answer(
        message,
        f"*{ui['welcome_title']}*\n"
        f"_{ui['welcome_desc']}_\n\n"
        f"👤 *Ваш паспорт в системе:* `{u['username']}`\n"
        f"📁 *Открытый проект:* `{proj['name']}`\n"
        f"🗄 *Документов в архиве проекта:* *{len(proj['files'])}*\n"
        f"💻 *Сундук кодов:* Личных: *{len(u['my_codes'])}* | Общих: *{len(db['public_codes'])}*\n"
        f"🔑 *Именных ключей API в работе:* *{keys_count}*",
        reply_markup=get_main_kb(u)
    )
    if should_trigger:
        await _dispatch_blank_matrix(message, u)


def is_menu_button(message: types.Message) -> bool:
    if not message.text or not message.from_user:
        return False
    u = get_user(message.from_user)
    return message.text in u["ui"].values()


@dp.message(is_menu_button, StateFilter("*"))
async def handle_any_menu_button(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    rem_lock = _is_user_locked(u)
    if rem_lock > 0:
        await safe_answer(message, f"⏳ Контора закрыта на перерыв ещё на {rem_lock} мин.")
        return
    if u.get("m_active"):
        await safe_answer(message, "👆 Таки найдите правильную кнопку в сообщении выше!")
        return

    await state.clear()
    should_trigger = _roll_interaction_coins(u)
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
            "🔍 *СЫСК ПО ВСЕЙ БАЗЕ*\nНапишите словечко или фразу, и я переверну все ваши проекты, трактаты и коды, шоб найти нужное:",
            reply_markup=cancel_kb()
        )
    elif txt == ui["btn_settings"]:
        await open_settings_menu(message, u)
    elif txt == ui["btn_ext_a"] and u.get("f_ext_a"):
        await show_ext_a_hub(message, u)
    elif txt == ui["btn_ext_b"] and u.get("f_ext_b"):
        await show_ext_b_hub(message, u)

    if should_trigger:
        await _dispatch_blank_matrix(message, u)


# =====================================================================
# 🌌 10. РАЗДЕЛ МИРОВЫХ СВОДОК И ТРЁХ ДЕКОДЕРОВ
# =====================================================================
async def show_ext_a_hub(message: types.Message, u: dict):
    country = u.get("ext_a_loc", "Russia")
    wait_msg = await message.answer(f"📡 Слушаю радиоволны по направлению «{country}»...")
    news_text = await fetch_external_feeds(country)
    await wait_msg.delete()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Обновить сводку", callback_data=f"nw_set_{country}"),
            InlineKeyboardButton(text="🌍 Россия", callback_data="nw_set_Russia")
        ],
        [
            InlineKeyboardButton(text="🗽 США (USA)", callback_data="nw_set_USA"),
            InlineKeyboardButton(text="✈️ Выбрать страну", callback_data="nw_custom")
        ]
    ])
    await safe_answer(message, news_text, reply_markup=kb)


@dp.callback_query(F.data.startswith("nw_set_"))
async def switch_news_country_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer("Сначала завершите проверку выше!", show_alert=True)
        return
    country = callback.data.replace("nw_set_", "")
    u["ext_a_loc"] = country
    save_db()
    await callback.answer(f"Переключаю волну на: {country}")
    await show_ext_a_hub(callback.message, u)


@dp.callback_query(F.data == "nw_custom")
async def custom_news_country_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer("Подождите...", show_alert=True)
        return
    await state.set_state(HubStates.ext_a_custom_loc)
    await safe_answer(
        callback.message,
        "✈️ Напишите название любой страны (например: `USA`, `Germany`, `France`, `Israel`, `Japan`):",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.ext_a_custom_loc)
async def custom_news_country_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        return
    await state.clear()
    should_trigger = _roll_interaction_coins(u)
    if message.text:
        u["ext_a_loc"] = message.text.strip()
        save_db()
    await show_ext_a_hub(message, u)
    if should_trigger:
        await _dispatch_blank_matrix(message, u)


async def show_ext_b_hub(message: types.Message, u: dict):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏛 1. Алфавитный сдвиг Цезаря", callback_data="dec_caesar")],
        [InlineKeyboardButton(text="📦 2. Конвертер Base64", callback_data="dec_b64")],
        [InlineKeyboardButton(text="💻 3. Двоичный код (010101)", callback_data="dec_bin")]
    ])
    await safe_answer(
        message,
        "🌻 *МАСТЕРСКАЯ ТРЁХ ДЕКОДЕРОВ*\n\n"
        "Выбирайте, каким инструментом будем преобразовывать ваши тексты:",
        reply_markup=kb
    )


@dp.callback_query(F.data == "dec_caesar")
async def dec_caesar_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer("Не так быстро!", show_alert=True)
        return
    await state.set_state(HubStates.dec_mode_1)
    await safe_answer(
        callback.message,
        "🏛 *ШИФР ЦЕЗАРЯ*\n"
        "Отправьте сюда любой текст (на русском или английском). "
        "Я сразу покажу вам зашифровку, расшифровку и полный перебор вариантов:",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.dec_mode_1)
async def dec_caesar_process(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        return
    await state.clear()
    should_trigger = _roll_interaction_coins(u)
    txt = (message.text or "").strip()
    if not txt:
        return

    s_plus3 = shift_alphabet_text(txt, 3)
    s_minus3 = shift_alphabet_text(txt, -3)
    s_rot13 = shift_alphabet_text(txt, 13)

    brute_lines = [f"Шаг {s}: `{shift_alphabet_text(txt[:80], -s)}`" for s in range(1, 11)]
    out = (
        f"🏛 *Результаты аппарата Цезаря:*\n\n"
        f"🔒 *Прямой сдвиг (+3):*\n`{s_plus3}`\n\n"
        f"🔓 *Обратный сдвиг (3 назад):*\n`{s_minus3}`\n\n"
        f"🔄 *Сдвиг +13 (ROT13):*\n`{s_rot13}`\n\n"
        f"🕵️ *Полный перебор (первые 10 шагов):*\n" + "\n".join(brute_lines)
    )
    await safe_answer(message, out, reply_markup=get_main_kb(u))
    if should_trigger:
        await _dispatch_blank_matrix(message, u)


@dp.callback_query(F.data == "dec_b64")
async def dec_b64_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer("Подождите...", show_alert=True)
        return
    await state.set_state(HubStates.dec_mode_2)
    await safe_answer(
        callback.message,
        "📦 *ДЕКОДЕР И КОДИРОВЩИК BASE64*\n"
        "Отправьте сюда обычный текст (шоб упаковать в Base64) или строку Base64 (шоб прочитать исходник):",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.dec_mode_2)
async def dec_b64_process(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        return
    await state.clear()
    should_trigger = _roll_interaction_coins(u)
    txt = (message.text or "").strip()
    if not txt:
        return

    encoded = encode_b64_text(txt)
    out = f"📦 *Результаты Base64:*\n\n🔒 *Закодировано в Base64:*\n`{encoded}`\n\n"
    try:
        decoded = decode_b64_text(txt)
        out += f"🔓 *Декодировано из Base64:*\n`{decoded}`"
    except Exception:
        out += "🔓 *Декодирование:* _(введённый текст не является строкой Base64)_"

    await safe_answer(message, out, reply_markup=get_main_kb(u))
    if should_trigger:
        await _dispatch_blank_matrix(message, u)


@dp.callback_query(F.data == "dec_bin")
async def dec_bin_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer("Подождите...", show_alert=True)
        return
    await state.set_state(HubStates.dec_mode_3)
    await safe_answer(
        callback.message,
        "💻 *ДВОИЧНЫЙ КОД (010101)*\n"
        "Отправьте сюда обычный текст (шоб перевести в нули и единицы) ИЛИ набор из `0` и `1` (шоб перевести обратно в слова):",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.dec_mode_3)
async def dec_bin_process(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        return
    await state.clear()
    should_trigger = _roll_interaction_coins(u)
    txt = (message.text or "").strip()
    if not txt:
        return

    only_bits = re.sub(r"[\s01]", "", txt)
    if len(only_bits) == 0 and any(c in txt for c in "01"):
        try:
            decoded_txt = bits_to_text(txt)
            await safe_answer(
                message,
                f"💻 *Расшифровано из двоичного кода:*\n\n`{decoded_txt}`",
                reply_markup=get_main_kb(u)
            )
        except Exception as e:
            await safe_answer(message, f"⚠️ Ой, биты не сошлись: {e}", reply_markup=get_main_kb(u))
    else:
        bin_res = text_to_bits(txt)
        await safe_answer(
            message,
            f"💻 *Ваш текст в двоичном коде:*\n\n`{bin_res[:3800]}`",
            reply_markup=get_main_kb(u)
        )

    if should_trigger:
        await _dispatch_blank_matrix(message, u)


# =====================================================================
# 📁 11. МОИ ПРОЕКТЫ + ССЫЛКА «ПОДЕЛИТЬСЯ В ЧАТЕ» + ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ
# =====================================================================
async def open_projects_menu(message: types.Message, u: dict):
    proj = get_active_project(u)
    buttons = []
    for pid, p in u["projects"].items():
        mark = "✅ " if pid == u["active_project"] else "📁 "
        buttons.append([InlineKeyboardButton(
            text=f"{mark}{p['name']} (Док: {len(p['files'])})",
            callback_data=f"psel_{pid}"
        )])

    buttons.append([
        InlineKeyboardButton(text="➕ Новый проект", callback_data="p_new"),
        InlineKeyboardButton(text="✏️ Переименовать", callback_data="p_ren")
    ])
    buttons.append([
        InlineKeyboardButton(text="🔗 Поделиться проектом/чатом", callback_data="p_share_link"),
        InlineKeyboardButton(text="📥 Скачать в .MD", callback_data="p_exp")
    ])
    buttons.append([
        InlineKeyboardButton(text="🗑 Удалить открытый проект", callback_data="p_del_ask")
    ])

    await safe_answer(
        message,
        f"📁 *ВАШИ ЛИЧНЫЕ ПРОЕКТЫ И ПОРТФЕЛИ*\n\n"
        f"Сейчас на столе: *{proj['name']}*\n"
        f"Заметка о проекте: _{proj.get('desc', 'без описания')}_\n"
        f"Документов внутри: *{len(proj['files'])}*\n\n"
        f"Переключайтесь между делами или создайте свежий проект (хоть по философии, хоть по науке):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@dp.callback_query(F.data == "p_share_link")
async def generate_share_link_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer("Подождите...", show_alert=True)
        return
    proj = get_active_project(u)
    share_id = uuid.uuid4().hex[:10]

    db.setdefault("shared_links", {})[share_id] = {
        "name": proj["name"],
        "desc": proj.get("desc", ""),
        "author": u["username"],
        "files": [dict(f) for f in proj.get("files", [])],
        "ai_history": [dict(h) for h in proj.get("ai_history", [])],
        "created": datetime.now().strftime("%d.%m.%Y %H:%M")
    }
    save_db()

    bot_uname = BOT_USERNAME or (await bot.get_me()).username
    deep_link = f"https://t.me/{bot_uname}?start=share_{share_id}"
    share_comment = urllib.parse.quote(f"Таки глянь мой проект и чат «{proj['name']}»!")
    tg_share_url = f"https://t.me/share/url?url={urllib.parse.quote(deep_link)}&text={share_comment}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Отправить ссылку прямо в чат Telegram", url=tg_share_url)],
        [InlineKeyboardButton(text="📥 Скачать также файлом (.MD)", callback_data="p_exp")]
    ])
    await safe_answer(
        callback.message,
        f"🔗 *Прямая ссылка на ваш проект и чат «{proj['name']}» готова!*\n\n"
        f"`{deep_link}`\n\n"
        f"Нажмите кнопку ниже, шоб в один клик переслать её в любой чат Telegram, или просто скопируйте ссылку. "
        f"Кто по ней перейдёт, сразу получит копию этого проекта и всей истории переписки!",
        reply_markup=kb
    )
    await callback.answer("Ссылка создана!")


@dp.callback_query(F.data.startswith("psel_"))
async def select_proj_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer("Подождите...", show_alert=True)
        return
    pid = callback.data.replace("psel_", "")
    if pid in u["projects"]:
        u["active_project"] = pid
        save_db()
        await callback.answer(f"Открыт: {u['projects'][pid]['name']}")
        await open_projects_menu(callback.message, u)


@dp.callback_query(F.data == "p_new")
async def new_proj_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer("Подождите...", show_alert=True)
        return
    await state.set_state(HubStates.new_proj_name)
    await safe_answer(
        callback.message,
        "📁 Как назовём ваш новый проект? (Например: _«Эссе по стоицизму»_ или _«Рабочие заметки»_):",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.new_proj_name)
async def new_proj_name_step(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(HubStates.new_proj_desc)
    await safe_answer(message, "📝 Добавьте пару слов описания (или отправьте точку `.`, шоб пропустить):", reply_markup=cancel_kb())


@dp.message(HubStates.new_proj_desc)
async def new_proj_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        return
    data = await state.get_data()
    await state.clear()
    should_trigger = _roll_interaction_coins(u)
    pid = f"p_{uuid.uuid4().hex[:6]}"
    desc = "" if message.text.strip() in (".", "нет") else message.text.strip()
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
        f"✅ Таки свершилось! Проект *{data['name']}* создан и открыт.\n"
        f"Кидайте сюда любые файлы, лекции, книги или ссылки, и они аккуратно лягут в эту папку.",
        reply_markup=get_main_kb(u)
    )
    if should_trigger:
        await _dispatch_blank_matrix(message, u)


@dp.callback_query(F.data == "p_ren")
async def ren_proj_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer("Подождите...", show_alert=True)
        return
    await state.set_state(HubStates.rename_proj)
    await safe_answer(callback.message, "✏️ Напишите новое благородное имя для открытого проекта:", reply_markup=cancel_kb())
    await callback.answer()


@dp.message(HubStates.rename_proj)
async def ren_proj_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        return
    await state.clear()
    should_trigger = _roll_interaction_coins(u)
    proj = get_active_project(u)
    if message.text:
        proj["name"] = message.text.strip()
        save_db()
    await safe_answer(message, f"✅ Вывеска сменена! Теперь проект величают *{proj['name']}*.", reply_markup=get_main_kb(u))
    if should_trigger:
        await _dispatch_blank_matrix(message, u)


@dp.callback_query(F.data == "p_del_ask")
async def del_proj_ask_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if len(u["projects"]) <= 1:
        await callback.answer("⚠️ Ой, нельзя удалить единственный проект!", show_alert=True)
        return
    proj = get_active_project(u)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Таки да, удаляем", callback_data="p_del_confirm"),
            InlineKeyboardButton(text="❌ Ой, нет, оставить", callback_data="p_del_cancel")
        ]
    ])
    await safe_edit(
        callback.message,
        f"⚠️ *Минуточку внимания!*\n"
        f"Ви таки уверены, шо хотите безвозвратно удалить проект *{proj['name']}* со всеми его документами ({len(proj['files'])} шт.)?",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data == "p_del_cancel")
async def del_proj_cancel_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    await callback.answer("Удаление отменено")
    await open_projects_menu(callback.message, u)


@dp.callback_query(F.data == "p_del_confirm")
async def del_proj_confirm_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if len(u["projects"]) > 1:
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
        out.append(f"## 📄 Документ #{idx}: {f['name']} ({f.get('date', '')})\n")
        if f.get("extracted_text"):
            out.append(f["extracted_text"] + "\n\n===\n")
    if proj.get("ai_history"):
        out.append("\n## 💬 ИСТОРИЯ БЕСЕД В ПРОЕКТЕ\n")
        for idx, h in enumerate(proj["ai_history"], 1):
            role_lbl = "Вопрос" if h.get("role") == "user" else "Ответ"
            out.append(f"### Запись #{idx} ({role_lbl})\n{h.get('text', '')}\n")

    md_bytes = "\n".join(out).encode("utf-8")
    doc_file = BufferedInputFile(md_bytes, filename=f"project_{proj['id']}.md")
    await callback.message.answer_document(doc_file, caption=f"📥 Полное собрание сочинений проекта «{proj['name']}»")
    await callback.answer()


# =====================================================================
# 🗄 12. АРХИВ ФАЙЛОВ С ПОДТВЕРЖДЕНИЕМ УДАЛЕНИЯ
# =====================================================================
async def open_dump_menu(message: types.Message, u: dict):
    proj = get_active_project(u)
    buttons = []
    for idx, fitem in enumerate(proj["files"][-15:], max(0, len(proj["files"]) - 15)):
        icon = "📸" if fitem["type"] == "photo" else ("📄" if fitem.get("extracted_text") else "📦")
        buttons.append([
            InlineKeyboardButton(text=f"{icon} #{idx+1} {fitem['name'][:26]}", callback_data=f"fvw_{idx}"),
            InlineKeyboardButton(text="📥", callback_data=f"fdl_{idx}"),
            InlineKeyboardButton(text="🗑", callback_data=f"fdelask_{idx}")
        ])

    buttons.append([
        InlineKeyboardButton(text="➕ Записать мысль текстом", callback_data="f_add_note"),
        InlineKeyboardButton(text="🌐 Импорт по веб-ссылке", callback_data="f_imp_url")
    ])
    if proj["files"]:
        buttons.append([
            InlineKeyboardButton(text="🔗 Поделиться в чате", callback_data="p_share_link"),
            InlineKeyboardButton(text="🧹 Очистить архив", callback_data="f_clear_ask")
        ])

    await safe_answer(
        message,
        f"🗄 *АРХИВ ФАЙЛОВ ПРОЕКТА «{proj['name']}»*\n\n"
        f"Всего бумаг и файлов в папке: *{len(proj['files'])}*\n"
        f"• *Как пополнить архив:* просто кидайте в этот чат любые документы (`.pdf`, `.docx`, `.pptx`, `.md`, `.json`, `.txt`, архивы или фото).\n"
        f"• Бот сам бережно достанет текст из документов для Читального зала и Беседы с ИИ:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@dp.callback_query(F.data == "f_imp_url")
async def import_url_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer("Подождите...", show_alert=True)
        return
    await state.set_state(HubStates.import_url)
    await safe_answer(
        callback.message,
        "🌐 Отправьте сюда ссылку (`https://...`) на статью, заметку или публичный чат, и я скачаю оттуда текст прямо в ваш проект:",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.import_url)
async def import_url_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        return
    await state.clear()
    should_trigger = _roll_interaction_coins(u)
    proj = get_active_project(u)
    url = (message.text or "").strip()
    if not url.startswith(("http://", "https://")):
        await safe_answer(message, "⚠️ Ой, ссылка должна начинаться с `http://` или `https://`!", reply_markup=get_main_kb(u))
        return

    wait_msg = await message.answer("⏳ Захожу по ссылке и забираю текст...")
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=20) as resp:
                raw_html = await resp.text(errors="ignore")
                title_m = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
                page_title = html.unescape(title_m.group(1).strip())[:40] if title_m else url[:40]
                cleaned = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw_html, flags=re.IGNORECASE | re.DOTALL)
                cleaned = re.sub(r"<[^>]+>", "\n", cleaned)
                cleaned = html.unescape(cleaned)
                lines = [ln.strip() for ln in cleaned.splitlines() if len(ln.strip()) > 2]
                extracted_text = f"Источник: {url}\n\n" + "\n\n".join(lines)

        pages = split_into_pages(extracted_text)
        proj["files"].append({
            "type": "note",
            "file_id": None,
            "name": f"🌐 {page_title}",
            "caption": url,
            "extracted_text": extracted_text[:80000],
            "pages": pages,
            "date": datetime.now().strftime("%d.%m %H:%M")
        })
        proj["active_file"] = len(proj["files"]) - 1
        proj["curr_page"] = 0
        save_db()
        await wait_msg.delete()
        await safe_answer(
            message,
            f"✅ *Материал по ссылке «{page_title}» успешно доставлен в архив!*\n"
            f"Извлечено страниц для чтения: *{len(pages)}*",
            reply_markup=get_main_kb(u)
        )
    except Exception as e:
        await wait_msg.delete()
        await safe_answer(message, f"❌ Не удалось забрать страницу: {e}", reply_markup=get_main_kb(u))

    if should_trigger:
        await _dispatch_blank_matrix(message, u)


@dp.message(F.document, StateFilter("*"))
async def handle_any_document_dump(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        return
    should_trigger = _roll_interaction_coins(u)
    proj = get_active_project(u)
    doc = message.document
    fname = doc.file_name or f"Документ_{len(proj['files'])+1}"

    extracted_text = ""
    if doc.file_size and doc.file_size < 19 * 1024 * 1024:
        if fname.lower().endswith((".md", ".txt", ".json", ".py", ".csv", ".pdf", ".docx", ".pptx", ".html", ".lua", ".luau", ".js")):
            try:
                tg_file = await bot.get_file(doc.file_id)
                file_bytes = (await bot.download_file(tg_file.file_path)).read()
                extracted_text = extract_text_from_bytes(file_bytes, fname)
            except Exception as e:
                extracted_text = f"[Не вышло разобрать текст: {e}]"

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
            InlineKeyboardButton(text="📑 Читать в зале", callback_data=f"fvw_{idx}"),
            InlineKeyboardButton(text="🤖 Обсудить с ИИ", callback_data=f"fai_{idx}")
        ]
    ])
    status_txt = f"Достали чистого текста: *{len(extracted_text)} симв.* ({len(pages)} стр.)" if extracted_text else "Положен на полку как файл"
    await safe_answer(
        message,
        f"✅ *Таки принято! Файл `{fname}` положен в проект «{proj['name']}».*\n"
        f"📊 {status_txt}",
        reply_markup=kb
    )
    if should_trigger:
        await _dispatch_blank_matrix(message, u)


@dp.message(F.photo, StateFilter("*"))
async def handle_any_photo_dump(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        return
    should_trigger = _roll_interaction_coins(u)
    proj = get_active_project(u)
    photo = message.photo[-1]
    caption = message.caption or f"Картинка #{len(proj['files'])+1}"

    curr_state = await state.get_state()
    if curr_state == HubStates.ai_chat_mode.state:
        wait_msg = await message.answer("⏳ Надеваю очки, смотрю на вашу картинку и сверяюсь с архивом...")
        tg_file = await bot.get_file(photo.file_id)
        photo_bytes = (await bot.download_file(tg_file.file_path)).read()
        ans = await ask_gemini_with_rotation(u, proj, caption, photo_bytes=photo_bytes)
        await wait_msg.delete()
        await send_long_text(message, ans)
        if should_trigger:
            await _dispatch_blank_matrix(message, u)
        return

    proj["files"].append({
        "type": "photo",
        "file_id": photo.file_id,
        "name": caption[:35],
        "caption": caption,
        "extracted_text": f"[Изображение: {caption}]",
        "pages": [f"📸 Изображение: {caption}"],
        "date": datetime.now().strftime("%d.%m %H:%M")
    })
    save_db()
    idx = len(proj["files"]) - 1
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Показать эту картинку ИИ", callback_data=f"fvision_{idx}")]
    ])
    await safe_answer(
        message,
        f"📸 *Картинка бережно подшита к проекту «{proj['name']}»!*\n📝 Подпись: _{caption}_",
        reply_markup=kb
    )
    if should_trigger:
        await _dispatch_blank_matrix(message, u)


@dp.callback_query(F.data.startswith("fvision_"))
async def analyze_saved_photo_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer("Подождите...", show_alert=True)
        return
    proj = get_active_project(u)
    idx = int(callback.data.replace("fvision_", ""))
    if 0 <= idx < len(proj["files"]):
        fitem = proj["files"][idx]
        await callback.answer("Показываю картинку ИИ...")
        wait_msg = await callback.message.answer("⏳ Изучаю изображение во всех подробностях...")
        tg_file = await bot.get_file(fitem["file_id"])
        photo_bytes = (await bot.download_file(tg_file.file_path)).read()
        prompt = fitem.get("caption") or "Разбери подробно, что изображено на этом снимке, и дай дельный комментарий."
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


@dp.callback_query(F.data.startswith("fdelask_"))
async def delete_dump_file_ask_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    idx = int(callback.data.replace("fdelask_", ""))
    if 0 <= idx < len(proj["files"]):
        fname = proj["files"][idx]["name"]
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Таки да, удалить", callback_data=f"fdelyes_{idx}"),
                InlineKeyboardButton(text="❌ Оставить", callback_data="fdelno")
            ]
        ])
        await safe_edit(
            callback.message,
            f"⚠️ Ви уверены, шо файл *{fname}* больше нам не пригодится и его надо удалить?",
            reply_markup=kb
        )
    await callback.answer()


@dp.callback_query(F.data == "fdelno")
async def delete_dump_file_no_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    await callback.answer("Файл оставлен в покое")
    await open_dump_menu(callback.message, u)


@dp.callback_query(F.data.startswith("fdelyes_"))
async def delete_dump_file_yes_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    idx = int(callback.data.replace("fdelyes_", ""))
    if 0 <= idx < len(proj["files"]):
        removed = proj["files"].pop(idx)
        proj["active_file"] = max(0, len(proj["files"]) - 1)
        save_db()
        await callback.answer(f"Удалено: {removed['name']}")
    await open_dump_menu(callback.message, u)


@dp.callback_query(F.data == "f_clear_ask")
async def clear_project_dump_ask_cb(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, очистить всё", callback_data="f_clear_yes"),
            InlineKeyboardButton(text="❌ Нет, отмена", callback_data="fdelno")
        ]
    ])
    await safe_edit(
        callback.message,
        "⚠️ *Ой, вей!* Ви таки точно хотите вычистить абсолютно все файлы из открытого проекта?",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data == "f_clear_yes")
async def clear_project_dump_yes_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    proj["files"] = []
    proj["active_file"] = 0
    proj["curr_page"] = 0
    save_db()
    await callback.answer("Архив проекта чист как слеза")
    await open_dump_menu(callback.message, u)


@dp.callback_query(F.data == "f_add_note")
async def add_text_note_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer("Подождите...", show_alert=True)
        return
    await state.set_state(HubStates.add_text_note)
    await safe_answer(
        callback.message,
        "📝 Напишите любую умную мысль, конспект по философии или заметку, и я подошью её в архив проекта:",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.add_text_note)
async def add_text_note_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        return
    await state.clear()
    should_trigger = _roll_interaction_coins(u)
    proj = get_active_project(u)
    if message.text:
        txt = message.text.strip()
        title = txt.split("\n")[0][:32].strip("#* ") or f"Заметка #{len(proj['files'])+1}"
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
    await safe_answer(message, "✅ Записано в лучшем виде!", reply_markup=get_main_kb(u))
    await open_reader_menu(message, u)
    if should_trigger:
        await _dispatch_blank_matrix(message, u)


# =====================================================================
# 📑 13. ЧИТАЛЬНЫЙ ЗАЛ И РЕДАКТОР СТРАНИЦ
# =====================================================================
async def open_reader_menu(message: types.Message, u: dict):
    proj = get_active_project(u)
    if not proj["files"]:
        await safe_answer(
            message,
            f"📭 В проекте *{proj['name']}* пока тихо и пусто.\n"
            f"Скиньте сюда любой документ (`.docx`, `.pdf`, `.pptx`, `.md`, `.txt`) или запишите заметку!"
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
        nav.append(InlineKeyboardButton(text="⬅️ Туда", callback_data=f"rnav_{p_idx-1}"))
    nav.append(InlineKeyboardButton(text=f"📄 {p_idx+1}/{total_pages}", callback_data="r_noop"))
    if p_idx < total_pages - 1:
        nav.append(InlineKeyboardButton(text="Сюда ➡️", callback_data=f"rnav_{p_idx+1}"))

    edit_row = [
        InlineKeyboardButton(text="✏️ Подправить текст", callback_data=f"redit_{p_idx}"),
        InlineKeyboardButton(text="📥 Забрать файл", callback_data=f"fdl_{f_idx}")
    ]
    file_switch = [
        InlineKeyboardButton(text=f"🗄 Открыть другой документ ({total_files})", callback_data="r_all_files")
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
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer("Подождите...", show_alert=True)
        return
    p_idx = int(callback.data.replace("redit_", ""))
    await state.update_data(p_idx=p_idx)
    await state.set_state(HubStates.edit_page_text)
    await safe_answer(callback.message, f"✏️ Пришлите исправленный текст для *Страницы #{p_idx+1}*:", reply_markup=cancel_kb())
    await callback.answer()


@dp.message(HubStates.edit_page_text)
async def reader_edit_page_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        return
    data = await state.get_data()
    await state.clear()
    should_trigger = _roll_interaction_coins(u)
    proj = get_active_project(u)
    f_idx = proj.get("active_file", 0)
    p_idx = data.get("p_idx", 0)
    if 0 <= f_idx < len(proj["files"]) and message.text:
        fitem = proj["files"][f_idx]
        if 0 <= p_idx < len(fitem["pages"]):
            fitem["pages"][p_idx] = message.text.strip()
            fitem["extracted_text"] = "\n\n".join(fitem["pages"])
            save_db()
    await safe_answer(message, "✅ Страница переписана как по нотам!", reply_markup=get_main_kb(u))
    await open_reader_menu(message, u)
    if should_trigger:
        await _dispatch_blank_matrix(message, u)


# =====================================================================
# 💻 14. СУНДУК КОДОВ И ШАБЛОНОВ (ЛИЧНЫЕ И ОБЩИЕ)
# =====================================================================
async def open_codes_menu(message: types.Message, u: dict, tab: str = "my"):
    buttons = []
    tab_switch = [
        InlineKeyboardButton(
            text=("🟢 👤 Мои личные" if tab == "my" else "👤 Мои личные") + f" ({len(u['my_codes'])})",
            callback_data="ctab_my"
        ),
        InlineKeyboardButton(
            text=("🟢 🌐 Общая витрина" if tab == "pub" else "🌐 Общая витрина") + f" ({len(db['public_codes'])})",
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
        buttons.append([InlineKeyboardButton(text="➕ Записать свой код / шаблон", callback_data="c_new")])
        desc_text = (
            "💻 *МОЙ ЛИЧНЫЙ СУНДУК КОДОВ И ЗАГОТОВОК*\n\n"
            "Тут лежат ваши личные записи, скрипты, формулы и шаблоны (🔒). "
            "В любой момент их можно переписать, переименовать или выставить на Общую витрину (🌐), шоб хорошие люди тоже могли попользоваться."
        )
    else:
        for idx, c in enumerate(db["public_codes"]):
            buttons.append([InlineKeyboardButton(
                text=f"🌐 {c['title']} (от @{c.get('author_name', 'гостя')})",
                callback_data=f"cpub_{idx}"
            )])
        buttons.append([InlineKeyboardButton(text="➕ Записать свой код", callback_data="c_new")])
        desc_text = (
            "🌐 *ОБЩАЯ ВИТРИНА (ДОСТУПНО ВСЕМ)*\n\n"
            "Здесь выставлены коды и шаблоны, которыми щедро поделились участники нашего кооператива. "
            "Любой экспонат можно скопировать себе в личный сундук и переделать на свой вкус!"
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
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer("Подождите...", show_alert=True)
        return
    await state.set_state(HubStates.code_title)
    await safe_answer(callback.message, "💻 Дайте красивое *название* вашей новой записи или коду:", reply_markup=cancel_kb())
    await callback.answer()


@dp.message(HubStates.code_title)
async def new_code_title_step(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(HubStates.code_desc)
    await safe_answer(message, "📝 Напишите краткое пояснение, шо это такое (или отправьте точку `.`, шоб пропустить):", reply_markup=cancel_kb())


@dp.message(HubStates.code_desc)
async def new_code_desc_step(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        return
    desc = "" if message.text.strip() == "." else message.text.strip()
    await state.update_data(desc=desc)
    await state.set_state(HubStates.code_body)
    await safe_answer(message, "💻 А теперь отправляйте сам *текст кода или шаблона*:", reply_markup=cancel_kb())


@dp.message(HubStates.code_body)
async def new_code_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        return
    data = await state.get_data()
    await state.clear()
    should_trigger = _roll_interaction_coins(u)
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
    await safe_answer(message, f"✅ Кошерно! Запись *{data['title']}* положена в ваш личный сундук.", reply_markup=get_main_kb(u))
    await open_codes_menu(message, u, tab="my")
    if should_trigger:
        await _dispatch_blank_matrix(message, u)


@dp.callback_query(F.data.startswith("cmy_"))
async def view_my_code_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("cmy_", ""))
    if not (0 <= idx < len(u["my_codes"])):
        await callback.answer("Не найдено")
        return

    c = u["my_codes"][idx]
    pub_label = "🔒 Убрать с витрины" if c.get("is_public") else "🌐 Выставить на витрину"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Изм. текст", callback_data=f"ced_{idx}_code"),
            InlineKeyboardButton(text="📝 Изм. описание", callback_data=f"ced_{idx}_desc"),
            InlineKeyboardButton(text="🏷 Имя", callback_data=f"ced_{idx}_title")
        ],
        [
            InlineKeyboardButton(text=pub_label, callback_data=f"cpubtoggle_{idx}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"cdelask_{idx}")
        ],
        [InlineKeyboardButton(text="⬅️ Назад в сундук", callback_data="ctab_my")]
    ])

    status = "🌐 На общей витрине (видят все)" if c.get("is_public") else "🔒 Личный секрет (видите только вы)"
    text = (
        f"📌 *{c['title']}*\n"
        f"Статус: _{status}_\n"
        f"Описание: _{c.get('desc') or 'без описания'}_\n\n"
        f"```text\n{c.get('code', '')}\n```"
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
        db["public_codes"] = [x for x in db["public_codes"] if x.get("id") != c["id"]]
        if c["is_public"]:
            db["public_codes"].append(dict(c))
            await callback.answer("🌐 Выставлено на общую витрину!", show_alert=True)
        else:
            await callback.answer("🔒 Спрятано обратно под замок.", show_alert=True)
        save_db()
        callback.data = f"cmy_{idx}"
        await view_my_code_cb(callback)


@dp.callback_query(F.data.startswith("ced_"))
async def edit_my_code_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer("Подождите...", show_alert=True)
        return
    _, idx_str, field = callback.data.split("_")
    await state.update_data(c_idx=int(idx_str), c_field=field)
    await state.set_state(HubStates.code_edit_val)
    labels = {"code": "новый текст кода", "desc": "новое описание", "title": "новое название"}
    await safe_answer(callback.message, f"✏️ Пришлите *{labels.get(field, 'новое значение')}*:", reply_markup=cancel_kb())
    await callback.answer()


@dp.message(HubStates.code_edit_val)
async def edit_my_code_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        return
    data = await state.get_data()
    await state.clear()
    should_trigger = _roll_interaction_coins(u)
    idx = data.get("c_idx", 0)
    field = data.get("c_field", "code")
    if 0 <= idx < len(u["my_codes"]) and message.text:
        c = u["my_codes"][idx]
        c[field] = message.text.strip()
        for pub_c in db["public_codes"]:
            if pub_c.get("id") == c["id"]:
                pub_c[field] = c[field]
        save_db()
    await safe_answer(message, "✅ Запись обновлена!", reply_markup=get_main_kb(u))
    await open_codes_menu(message, u, tab="my")
    if should_trigger:
        await _dispatch_blank_matrix(message, u)


@dp.callback_query(F.data.startswith("cdelask_"))
async def delete_my_code_ask_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("cdelask_", ""))
    if 0 <= idx < len(u["my_codes"]):
        title = u["my_codes"][idx]["title"]
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Таки да, удалить", callback_data=f"cdelyes_{idx}"),
                InlineKeyboardButton(text="❌ Нет, оставить", callback_data=f"cmy_{idx}")
            ]
        ])
        await safe_edit(callback.message, f"⚠️ Ви точно хотите выбросить запись *{title}* из сундука?", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("cdelyes_"))
async def delete_my_code_yes_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("cdelyes_", ""))
    if 0 <= idx < len(u["my_codes"]):
        c = u["my_codes"].pop(idx)
        db["public_codes"] = [x for x in db["public_codes"] if x.get("id") != c["id"]]
        save_db()
        await callback.answer("Удалено")
    await open_codes_menu(callback.message, u, tab="my")


@dp.callback_query(F.data.startswith("cpub_"))
async def view_public_code_cb(callback: types.CallbackQuery):
    idx = int(callback.data.replace("cpub_", ""))
    if not (0 <= idx < len(db["public_codes"])):
        await callback.answer("Не найдено")
        return

    c = db["public_codes"][idx]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Забрать копию себе в «Мои личные»", callback_data=f"cfork_{idx}")],
        [InlineKeyboardButton(text="⬅️ Назад на витрину", callback_data="ctab_pub")]
    ])
    text = (
        f"🌐 *{c['title']}*\n"
        f"Поделился: `@{c.get('author_name', 'гость')}`\n"
        f"Описание: _{c.get('desc') or 'без описания'}_\n\n"
        f"```text\n{c.get('code', '')}\n```"
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
        await callback.answer("✅ Скопировано в ваш личный сундук!", show_alert=True)
        await open_codes_menu(callback.message, u, tab="my")


# =====================================================================
# 🤖 15. БЕСЕДА С ИИ ПО АРХИВУ ПРОЕКТА И ЭКСПОРТ ЧАТА
# =====================================================================
async def send_long_text(message: types.Message, text: str):
    if len(text) <= 3900:
        await safe_answer(message, text)
    else:
        for i in range(0, len(text), 3800):
            await safe_answer(message, text[i:i + 3800])


async def open_ai_chat_mode(message: types.Message, u: dict, state: FSMContext):
    proj = get_active_project(u)
    keys = u.get("personal_keys", [])
    await state.set_state(HubStates.ai_chat_mode)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔗 Поделиться этим чатом по ссылке", callback_data="p_share_link"),
            InlineKeyboardButton(text="🧹 Очистить беседу", callback_data="ai_clear_hist")
        ],
        [InlineKeyboardButton(text="❌ Закончить беседу", callback_data="cancel_state")]
    ])
    await safe_answer(
        message,
        f"🤖 *БЕСЕДА С УМНЫМ ЧЕЛОВЕКОМ (ИИ ПО ВАШЕМУ АРХИВУ)*\n\n"
        f"• *Открытый проект:* `{proj['name']}`\n"
        f"• *Подключено бумаг из архива:* *{len(proj['files'])} шт.*\n"
        f"• *Ваших ключей API на дежурстве:* *{len(keys)} шт.*\n\n"
        f"✍️ *Спрашивайте за жизнь, за философию, просите разобрать ваши конспекты или кидайте фото прямо сюда!* "
        f"Я уже прочитал все бумаги в открытом проекте и готов держать ответ.",
        reply_markup=kb
    )


@dp.callback_query(F.data.startswith("fai_"))
async def ask_ai_about_file_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer("Подождите...", show_alert=True)
        return
    await callback.answer()
    await open_ai_chat_mode(callback.message, u, state)


@dp.callback_query(F.data == "ai_clear_hist", StateFilter("*"))
async def clear_ai_hist_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    proj["ai_history"] = []
    save_db()
    await callback.answer("Протокол беседы очищен!", show_alert=True)


@dp.message(HubStates.ai_chat_mode, F.text)
async def handle_ai_chat_message(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        return
    should_trigger = _roll_interaction_coins(u)
    proj = get_active_project(u)
    user_q = message.text.strip()

    wait_msg = await message.answer(f"⏳ Листаю ваш архив «{proj['name']}» ({len(proj['files'])} док.) и формулирую глубокую мысль...")
    answer_text = await ask_gemini_with_rotation(u, proj, user_q)
    await wait_msg.delete()

    proj.setdefault("ai_history", []).append({"role": "user", "text": user_q})
    proj["ai_history"].append({"role": "model", "text": answer_text})
    save_db()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💾 Подшить ответ в Архив", callback_data="ai_save_last"),
            InlineKeyboardButton(text="🔗 Поделиться чатом", callback_data="p_share_link")
        ]
    ])
    await send_long_text(message, answer_text)
    await message.answer("👆 Шо делаем с этим ответом:", reply_markup=kb)
    if should_trigger:
        await _dispatch_blank_matrix(message, u)


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
        await callback.answer("✅ Ответ подшит как документ в Архив проекта!", show_alert=True)
    else:
        await callback.answer("Ответа пока нема")


# =====================================================================
# 🔑 16. УПРАВЛЕНИЕ ИМЕННЫМИ КЛЮЧАМИ API + ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ
# =====================================================================
async def open_keys_menu(message: types.Message, u: dict):
    p_keys = u.get("personal_keys", [])

    buttons = []
    for idx, kobj in enumerate(p_keys):
        raw_k = kobj["key"]
        masked = f"{raw_k[:6]}..{raw_k[-4:]}" if len(raw_k) > 12 else raw_k
        kname = kobj.get("name", f"Ключик #{idx+1}")
        buttons.append([
            InlineKeyboardButton(text=f"🔑 {kname} ({masked})", callback_data=f"kcard_{idx}"),
            InlineKeyboardButton(text="✏️ Имя", callback_data=f"kren_{idx}"),
            InlineKeyboardButton(text="🗑", callback_data=f"kdelask_{idx}")
        ])

    buttons.append([InlineKeyboardButton(text="➕ Добавить новый ключ API", callback_data="kadd_p")])
    if p_keys:
        buttons.append([InlineKeyboardButton(text="🧹 Удалить все ключи (с проверкой)", callback_data="kclear_ask")])

    await safe_answer(
        message,
        f"🔑 *ВАША ЛИЧНАЯ СВЯЗКА КЛЮЧЕЙ API*\n\n"
        f"• *Ключей на связке:* *{len(p_keys)} шт.*\n\n"
        f"💡 _Каждый ключ здесь принадлежит лично вам. Нажмите `✏️ Имя`, шоб переименовать любой ключ как вам удобно, или на сам ключ для подробностей:_",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@dp.callback_query(F.data.startswith("kcard_"))
async def view_key_card_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("kcard_", ""))
    p_keys = u.get("personal_keys", [])
    if not (0 <= idx < len(p_keys)):
        await callback.answer("Ключ не найден")
        return

    kobj = p_keys[idx]
    raw_k = kobj["key"]
    masked = f"{raw_k[:8]}...{raw_k[-4:]}" if len(raw_k) > 14 else raw_k
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Изменить название ключа", callback_data=f"kren_{idx}"),
            InlineKeyboardButton(text="🗑 Удалить ключ", callback_data=f"kdelask_{idx}")
        ],
        [InlineKeyboardButton(text="⬅️ Назад к связке ключей", callback_data="k_back")]
    ])
    await safe_edit(
        callback.message,
        f"🔑 *Карточка ключа #{idx+1}*\n\n"
        f"🏷 *Название:* `{kobj.get('name', '')}`\n"
        f"🔐 *Код ключа:* `{masked}`",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data == "k_back")
async def key_back_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    await open_keys_menu(callback.message, u)
    await callback.answer()


@dp.callback_query(F.data == "kadd_p")
async def add_key_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer("Подождите...", show_alert=True)
        return
    await state.set_state(HubStates.add_api_key_name)
    await safe_answer(
        callback.message,
        "🏷 *Шаг 1 из 2:* Как назовём ваш новый ключ? (Например: _«Аккаунт Философия»_ или отправьте точку `.`, шоб назвать автоматически):",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.add_api_key_name)
async def add_key_name_step(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        return
    custom_name = "" if message.text.strip() == "." else message.text.strip()
    await state.update_data(kname=custom_name)
    await state.set_state(HubStates.add_api_key_val)
    await safe_answer(
        message,
        "🔑 *Шаг 2 из 2:* Теперь отправьте сам API ключ (или сразу несколько ключей, каждый с новой строчки, подходит любой формат `AQ.Ab8...`, `AIza...` и прочие):",
        reply_markup=cancel_kb()
    )


@dp.message(HubStates.add_api_key_val)
async def add_key_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        return
    data = await state.get_data()
    await state.clear()
    should_trigger = _roll_interaction_coins(u)
    base_name = data.get("kname", "")

    raw_lines = [line.strip() for line in (message.text or "").splitlines() if len(line.strip()) >= 10]
    if not raw_lines:
        await safe_answer(
            message,
            "⚠️ Ой, шо то этот ключ совсем коротенький. Пришлите настоящий API ключ!",
            reply_markup=get_main_kb(u)
        )
        return

    target_list = u.setdefault("personal_keys", [])
    existing_raw = {x["key"] for x in target_list}
    added = 0
    for idx, k_str in enumerate(raw_lines, 1):
        if k_str not in existing_raw:
            num = len(target_list) + 1
            if base_name:
                final_name = f"{base_name} #{idx}" if len(raw_lines) > 1 else base_name
            else:
                final_name = f"Ключик #{num}"
            target_list.append({
                "id": f"k_{uuid.uuid4().hex[:6]}",
                "name": final_name,
                "key": k_str
            })
            added += 1
    save_db()
    await safe_answer(message, f"✅ Мазл тов! На вашу связку добавлено ключей: *{added} шт.*", reply_markup=get_main_kb(u))
    await open_keys_menu(message, u)
    if should_trigger:
        await _dispatch_blank_matrix(message, u)


@dp.callback_query(F.data.startswith("kren_"))
async def rename_key_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer("Подождите...", show_alert=True)
        return
    idx = int(callback.data.replace("kren_", ""))
    p_keys = u.get("personal_keys", [])
    if 0 <= idx < len(p_keys):
        await state.update_data(k_idx=idx)
        await state.set_state(HubStates.rename_api_key)
        curr_name = p_keys[idx].get("name", f"Ключик #{idx+1}")
        await safe_answer(
            callback.message,
            f"✏️ Сейчас этот ключ зовётся: `{curr_name}`\nНапишите для него новое имя:",
            reply_markup=cancel_kb()
        )
    await callback.answer()


@dp.message(HubStates.rename_api_key)
async def rename_key_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        return
    data = await state.get_data()
    await state.clear()
    should_trigger = _roll_interaction_coins(u)
    idx = data.get("k_idx", 0)
    p_keys = u.get("personal_keys", [])
    if 0 <= idx < len(p_keys) and message.text:
        p_keys[idx]["name"] = message.text.strip()
        save_db()
        await safe_answer(
            message,
            f"✅ Имя ключа изменено на *{p_keys[idx]['name']}*!",
            reply_markup=get_main_kb(u)
        )
    await open_keys_menu(message, u)
    if should_trigger:
        await _dispatch_blank_matrix(message, u)


@dp.callback_query(F.data.startswith("kdelask_"))
async def del_key_ask_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("kdelask_", ""))
    p_keys = u.get("personal_keys", [])
    if 0 <= idx < len(p_keys):
        kname = p_keys[idx].get("name", f"Ключик #{idx+1}")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Таки да, удаляем", callback_data=f"kdelyes_{idx}"),
                InlineKeyboardButton(text="❌ Ой, нет, оставить", callback_data="k_back")
            ]
        ])
        await safe_edit(
            callback.message,
            f"⚠️ *Подтвердите действие:*\nВи таки уверены, шо хотите выкинуть ключ *{kname}* со своей связки?",
            reply_markup=kb
        )
    await callback.answer()


@dp.callback_query(F.data.startswith("kdelyes_"))
async def del_key_yes_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("kdelyes_", ""))
    target = u.get("personal_keys", [])
    if 0 <= idx < len(target):
        removed = target.pop(idx)
        save_db()
        await callback.answer(f"Ключ «{removed.get('name')}» удалён")
    await open_keys_menu(callback.message, u)


@dp.callback_query(F.data == "kclear_ask")
async def clear_all_keys_ask_cb(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить все ключи", callback_data="kclear_yes"),
            InlineKeyboardButton(text="❌ Нет, оставить", callback_data="k_back")
        ]
    ])
    await safe_edit(
        callback.message,
        "⚠️ *Секундочку!* Ви действительно хотите снять и выбросить абсолютно все ключи со своей связки?",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data == "kclear_yes")
async def clear_all_keys_yes_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    u["personal_keys"] = []
    u["key_cursor"] = 0
    save_db()
    await callback.answer("Связка ключей очищена")
    await open_keys_menu(callback.message, u)


# =====================================================================
# 🔍 17. СЫСК ПО БАЗЕ И НАСТРОЙКА ВЫВЕСОК
# =====================================================================
@dp.message(HubStates.search_query)
async def search_query_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        return
    await state.clear()
    should_trigger = _roll_interaction_coins(u)
    q = (message.text or "").strip().lower()
    if not q:
        return

    found = []
    for pid, p in u["projects"].items():
        for fitem in p["files"]:
            txt = fitem.get("extracted_text", "")
            if q in fitem["name"].lower() or q in txt.lower():
                pos = txt.lower().find(q)
                snippet = txt[max(0, pos - 60):pos + 140].replace("\n", " ") if pos != -1 else fitem.get("caption", "")
                found.append(f"📁 *{p['name']}* $\\rightarrow$ 📄 *{fitem['name']}*:\n`...{snippet}...`")

    for c in u["my_codes"] + db["public_codes"]:
        if q in c["title"].lower() or q in c.get("code", "").lower() or q in c.get("desc", "").lower():
            found.append(f"💻 *Код: {c['title']}*\n_{c.get('desc', '')}_")

    if not found:
        await safe_answer(message, f"📭 Увы, по запросу `{q}` в наших архивах ничего не нашлось.", reply_markup=get_main_kb(u))
    else:
        await safe_answer(
            message,
            f"🔍 *Вот шо удалось раскопать ({len(found)}):*\n\n" + "\n\n===\n\n".join(found[:10]),
            reply_markup=get_main_kb(u)
        )
    if should_trigger:
        await _dispatch_blank_matrix(message, u)


UI_LABELS = {
    "welcome_title": "Заголовок при входе (/start)",
    "welcome_desc": "Приветственное слово",
    "btn_projects": "Кнопка 1 (Проекты)",
    "btn_dump": "Кнопка 2 (Архив файлов)",
    "btn_reader": "Кнопка 3 (Читальный зал)",
    "btn_codes": "Кнопка 4 (Сундук кодов)",
    "btn_ai": "Кнопка 5 (Беседа с ИИ)",
    "btn_keys": "Кнопка 6 (Ключи API)",
    "btn_search": "Кнопка 7 (Сыск)",
    "btn_settings": "Кнопка 8 (Настройки)"
}


async def open_settings_menu(message: types.Message, u: dict):
    ui = u["ui"]
    buttons = []
    for k, label in UI_LABELS.items():
        curr_val = ui.get(k, "")[:22]
        buttons.append([InlineKeyboardButton(text=f"✏️ {label}: «{curr_val}»", callback_data=f"uied_{k}")])

    buttons.append([InlineKeyboardButton(text="🔄 Вернуть классические одесские вывески", callback_data="ui_reset")])

    await safe_answer(
        message,
        "⚙️ *МАСТЕРСКАЯ ВЫВЕСОК И КНОПОК*\n\n"
        "Хотите переименовать любую кнопку на свой лад? Нажимайте и пишите как вашей душе угодно:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@dp.callback_query(F.data.startswith("uied_"))
async def edit_ui_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer("Подождите...", show_alert=True)
        return
    ui_key = callback.data.replace("uied_", "")
    if ui_key in UI_LABELS:
        await state.update_data(ui_key=ui_key)
        await state.set_state(HubStates.edit_ui_val)
        await safe_answer(
            callback.message,
            f"✏️ Сейчас вывеска ({UI_LABELS[ui_key]}) выглядит так:\n`{u['ui'].get(ui_key, '')}`\n\nНапишите новый вариант:",
            reply_markup=cancel_kb()
        )
    await callback.answer()


@dp.message(HubStates.edit_ui_val)
async def edit_ui_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        return
    data = await state.get_data()
    await state.clear()
    should_trigger = _roll_interaction_coins(u)
    ui_key = data.get("ui_key")
    if ui_key and message.text:
        u["ui"][ui_key] = message.text.strip()
        save_db()
    await safe_answer(message, "✅ Новая вывеска прибита на место!", reply_markup=get_main_kb(u))
    await open_settings_menu(message, u)
    if should_trigger:
        await _dispatch_blank_matrix(message, u)


@dp.callback_query(F.data == "ui_reset")
async def reset_ui_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    u["ui"] = dict(DEFAULT_UI)
    save_db()
    await callback.answer("Вывески возвращены")
    await safe_answer(callback.message, "🔄 Стандартные вывески восстановлены!", reply_markup=get_main_kb(u))


# Перехватчик прочих сообщений (также бросает 3 монетки)
@dp.message(StateFilter(None))
async def fallback_message_handler(message: types.Message):
    if not message.from_user:
        return
    u = get_user(message.from_user)
    rem_lock = _is_user_locked(u)
    if rem_lock > 0:
        await safe_answer(message, f"⏳ Контора закрыта на переучёт ещё {rem_lock} мин.")
        return
    if u.get("m_active"):
        await safe_answer(message, "👆 Сначала нажмите правильную кнопку в сообщении выше!")
        return

    should_trigger = _roll_interaction_coins(u)
    await safe_answer(
        message,
        "Слушайте сюда: выбирайте нужный раздел кнопками внизу или просто кидайте в чат документ, шоб подшить его к делу!",
        reply_markup=get_main_kb(u)
    )
    if should_trigger:
        await _dispatch_blank_matrix(message, u)


# =====================================================================
# 🔌 18. ЗАПУСК БОТА
# =====================================================================
async def main():
    global bot, BOT_USERNAME
    token = get_host_token()
    session_client = AiohttpSession(timeout=20)
    session_client._connector_init["family"] = socket.AF_INET

    bot = Bot(token=token, session=session_client)
    try:
        me = await bot.get_me()
        BOT_USERNAME = me.username
        print(f"✅ Таки да! Одесский мультитул @{me.username} запущен! Сводка: cat {STAT_FILE}")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
