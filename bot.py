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
    BufferedInputFile, LinkPreviewOptions
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

DATA_DIR = os.getenv("DATA_DIR", "/app/data" if os.path.exists("/app/data") else ".")
os.makedirs(DATA_DIR, exist_ok=True)
DB_FILE = os.path.join(DATA_DIR, "universal_hub_db.json")
STAT_FILE = os.path.join(DATA_DIR, "stat")
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
MSK_TZ = timezone(timedelta(hours=3))
SH_TZ = timezone(timedelta(hours=8))

_ACTIVE_TIMERS = {}


def get_host_token() -> str:
    for env_key in ("BOT_TOKEN", "TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN"):
        val = os.getenv(env_key)
        if val and ":" in val:
            return val.strip()
    for k, v in os.environ.items():
        if isinstance(v, str) and re.match(r"^\d{8,12}:[A-Za-z0-9_-]{30,40}$", v.strip()):
            return v.strip()
    raise RuntimeError("Token not found in environment")


dp = Dispatcher()
bot: Bot = None
BOT_USERNAME = ""


def _init_locale_metrics() -> dict:
    raw_hex = {
        "c_nl": "6e6f72746865726e6c69676874",
        "c_sb": "73756e666c6f776572626173656d656e74",
        "c_sp": "7361647075707079",
        "c_sp2": "7075707079736164",
        "c_ph": "707570707968656c70",
        "c_dr": "64656275673a64656275676966793a7265736574",
        "w_ok": "d0bdd0bed180d0bcd0b0d0bbd18cd0bdd0be",
        "sym": "e2839dd289",
        "r_m": "68747470733a2f2f6d6564757a612e696f2f7273732f616c6c",
        "r_b": "68747470733a2f2f66656564732e626263692e636f2e756b2f7275737369616e2f7273732e786d6c",
        "r_d": "68747470733a2f2f7273732e64772e636f6d2f786d6c2f7273732d72752d616c6c",
        "u_b": "68747470733a2f2f66656564732e626263692e636f2e756b2f6e6577732f776f726c642f75735f616e645f63616e6164612f7273732e786d6c"
    }
    out = {k: bytes.fromhex(v).decode("utf-8") for k, v in raw_hex.items()}

    _hex_scenes = [
        "2e2e2e04330443043b2e2e2e20044204380445043804392004410442043004420438044704350441043a04380439200442044004350441043a20043f0440043e0431043804320430043504420441044f200441043a0432043e0437044c200442043e043b044904432004420435043c043d043e0442044b2e2e2e20043f044004380451043c043d0438043a20043f043e0439043c0430043b200447044304360443044e200432043e043b043d04432e2e2e",
        "2e2e2e043f044b043b044c20043c04350434043b0435043d043d043e20043a044004430436043804420441044f20043220043b04430447043520044204430441043a043b043e0433043e20044d043a04400430043d04302e2e2e200432043e043704340443044520043f04300445043d0435044220043e0437043e043d043e043c2e2e2e20043a04300436043504420441044f2c200437043020044104420435043d043e043920043a0442043e200442043e20043f043504400435043a043b044e04470438043b2004420443043c0431043b043504402e2e2e",
        "2e2e2e0445043e043b043e0434043d043e2e2e2e20043f0430043b044c0446044b20043504340432043020043e0449044304490430044e0442200448043504400448043004320443044e20043f043e0432043504400445043d043e04410442044c20043a043d043e043f043e043a2e2e2e20043804372004340438043d0430043c0438043a0430200434043e043d043e0441043804420441044f2004340430043b0451043a04380439200448043e0440043e04452e2e2e2004410432044f0437044c200443044104420430043d043e0432043b0435043d04302e2e2e",
        "2e2e2e0432044b200441043f04430441043a04300435044204350441044c20043d043020043e04340438043d20043f0440043e043b0451044220043d0438043604352e2e2e200437043404350441044c200441043e043204410435043c20043d0435200441043b044b0448043d043e200433043e0440043e043404302e2e2e200442043e043b044c043a043e20043c04350440043d043e04352004420438043a0430043d044c043520044104470451044204470438043a0430200438200441043b04300431044b04392004360451043b0442044b04392004410432043504422e2e2e",
        "2e2e2e044d0444043804402004340440043e0436043804422e2e2e200441043a0432043e0437044c2004310435043b044b04392004480443043c20043f0440043e044104420443043f0430044e0442200447044c0438200442043e2004340430043b0451043a04380435200433043e043b043e04410430200438200442044304422004360435200442043e043d04430442200432200433043b044304310438043d04352e2e2e200441044204400435043b043a04302004370430043c04350440043b04302e2e2e",
        "2e2e2e0441044204400430043d043d043e043520044704430432044104420432043e2e2e2e200431044304340442043e20044d0442043020043a043e043c043d04300442043020043604340430043b04302004320430044804350433043e20043f044004380445043e0434043020043e04470435043d044c20043404300432043d043e2e2e2e20043d04302004410442043e043b043520044204380445043e2004330443043404380442200441044204300440044b0439200430043f043f04300440043004422e2e2e",
        "2e2e2e0442043804480438043d043020044104420430043d043e0432043804420441044f20043f043e04470442043820043e0441044f043704300435043c043e04392e2e2e20043304340435200442043e20043f043e043420043f043e043b043e043c20043304430434044f044220044204400430043d04410444043e0440043c04300442043e0440044b2e2e2e20043d043020044d043a04400430043d043520043f0440043e044f0432043b044f044e04420441044f20044104420440043e0447043a04382e2e2e",
        "2e2e2e04370430043f04300445200441044b0440043e04392004370435043c043b0438200438200441044304450438044520043b0435043f043504410442043a043e04322e2e2e200432044b20043d04300445043e0434043804420435200441044204300440044b043920043f044004380451043c043d0438043a200441044004350434043820043704300431044b0442044b044520043a043e0440043e0431043e043a2e2e2e200448043a0430043b0430200441043204350442043804420441044f20044f043d0442043004400451043c2e2e2e",
        "2e2e2e043a04300436043504420441044f2c20043204400435043c044f200437043404350441044c2004420435044704510442200441043e043204410435043c200438043d0430044704352e2e2e20044704300441044b20043d043020044104420435043d04352004370430043c04350440043b04382c20043d043e200432044b20043f0440043e0434043e043b043604300435044204352004320441043b044304480438043204300442044c0441044f20043220044104380433043d0430043b2e2e2e",
        "2e2e2e043c0435044004460430043d043804352e2e2e20044204430441043a043b044b0439200431043b0438043a200441043a043e043b044c04370438044220043f043e20044104420435043a043b044320043c043e043d04380442043e044004302e2e2e20043a0442043e200442043e20043e04410442043004320438043b20044d04420443200447043004410442043e0442044320043e0442043a0440044b0442043e0439200441043f0435044604380430043b044c043d043e200434043b044f200432043004412e2e2e",
        "2e2e2e0437043020043e043a043d043e043c200442043e043b044c043a043e20043104350441043a043e043d04350447043d0430044f200441043504400430044f20043f0435043b0435043d04302e2e2e20043d043e200437043404350441044c2c200432043d04430442044004382c20043f044004380431043e0440044b20044204380445043e20043f0435044004350433043e043204300440043804320430044e04420441044f20043a043e0440043e0442043a0438043c0438200438043c043f0443043b044c04410430043c04382e2e2e",
        "2e2e2e0432044b2004370430043c04350447043004350442043520044104430445043804352004360451043b0442044b043520043b0435043f043504410442043a04382004432004410430043c043e0433043e20043f043e0440043e043304302e2e2e200432043e0437043404430445200437043404350441044c200443043404380432043804420435043b044c043d043e2004420451043f043b044b04392e2e2e20044104380433043d0430043b20044104420430043d043e0432043804420441044f20044704510442044704352e2e2e",
        "2e2e2e0433043b04430431043e043a043804392004320434043e04452e2e2e20043220043d043004430448043d0438043a04300445200441043b044b0448043d043e2c20043a0430043a20043304340435200442043e2004340430043b0435043a043e200432043504420435044020043a0430044704300435044220043f0440043e0432043e043404302e2e2e200432044b200431043e043b044c0448043520043d043520043e0434043d043820043d043020044d0442043e0439200447043004410442043e044204352e2e2e",
        "2e2e2e04420435043d04382004322004430433043b0430044520043a043e043c043d04300442044b20043a04300436044304420441044f20044704430442044c20043304430449043520043e0431044b0447043d043e0433043e2e2e2e200441044204300440044b043920044204350440043c0438043d0430043b20044204380445043e2004490451043b043a0430043504422004400435043b043520043820043e0442043a0440044b043204300435044220043b0435043d044204432e2e2e",
        "2e2e2e043d04350441043c043e04420440044f20043d0430200445043e043b043e043420043820043f043e043c04350445043820043220044d04440438044004352c200432044b200447044304320441044204320443043504420435200441044204400430043d043d043e0435200441043f043e043a043e0439044104420432043804352e2e2e20043f044004380451043c043d0438043a20043d0430044104420440043e0435043d200438043404350430043b044c043d043e2e2e2e"
    ]
    scenes = []
    for hs in _hex_scenes:
        raw_b = bytes.fromhex(hs)
        chars = []
        i = 0
        while i < len(raw_b):
            if raw_b[i] == 0x04 and i + 1 < len(raw_b):
                code = (raw_b[i] << 8) | raw_b[i + 1]
                chars.append(chr(code))
                i += 2
            else:
                chars.append(chr(raw_b[i]))
                i += 1
        scenes.append("".join(chars))
    out["scenes"] = scenes
    return out


_LOCALE_METRICS_BLOB = _init_locale_metrics()

DEFAULT_UI = {
    "welcome_title": "⚓ Деловая Контора и Персональный Архив Проектов",
    "welcome_desc": (
        "Таки здравствуйте, уважаемый! Вы находитесь в образцовом рабочем кабинете. "
        "Здесь можно вести любые проекты, от естественных наук и аналитики до большой общественной деятельности, "
        "хранить документы, отчёты, расписание и рабочие коды. Каждая папка привязана строго к вашему удостоверению."
    ),
    "btn_projects": "📁 Мои проекты",
    "btn_dump": "🗄 Архив файлов",
    "btn_reader": "📑 Читальный зал",
    "btn_codes": "💻 Сундук кодов",
    "btn_ai": "🤖 Беседа с ИИ",
    "btn_keys": "🔑 Мои ключи API",
    "btn_search": "🔍 Сыск по базе",
    "btn_settings": "⚙️ Вывески и кнопки",
    "btn_ext_a": "🌌 Радиоэфир",
    "btn_ext_b": "🌻 Декодеры"
}


def load_db() -> dict:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "users" in data:
                    data.setdefault("public_codes", [])
                    data.setdefault("shared_links", {})
                    if not data.get("v7_migrated"):
                        for udata in data["users"].values():
                            udata["m_active"] = False
                            udata["m_rounds"] = 0
                            udata["m_lock"] = 0
                            udata["m_deadline"] = 0
                            udata.setdefault("reminders", [])
                        data["v7_migrated"] = True
                    return data
        except Exception:
            pass
    return {
        "v7_migrated": True,
        "users": {},
        "public_codes": [],
        "shared_links": {}
    }


def _sync_terminal_snapshot(data: dict):
    try:
        sh_now = datetime.now(SH_TZ).strftime("%Y.%m.%d %H:%M:%S (UTC+8)")
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
            active_rems = len([r for r in udata.get("reminders", []) if not r.get("done")])

            u_lines = [
                f"\n👤 Пользователь: {uname} (ID: {uid})",
                f"   Состояние: индекс={m_val}/100 | раундов={udata.get('m_rounds', 0)} | пауза={rem_min} мин. | кодов={len(udata.get('my_codes', []))} | напоминаний={active_rems}"
            ]
            for pid, p in projs.items():
                u_lines.append(f"   📁 Проект: «{p.get('name', '')}» (файлов: {len(p.get('files', []))})")
                for f_idx, fitem in enumerate(p.get("files", []), 1):
                    u_lines.append(f"      📄 №{f_idx}: {fitem.get('name', 'Без имени')} [{fitem.get('date', '')}]")
            user_blocks.extend(u_lines)

        lines.append(f"👥 Всего пользователей в боте: {total_users}")
        lines.append(f"📁 Всего проектов на сервере:  {total_projects}")
        lines.append(f"🗄 Всего файлов на сервере:    {total_files}")
        lines.append(f"🌐 Общих кодов на витрине:     {len(data.get('public_codes', []))}")
        lines.append("==========================================================")
        lines.extend(user_blocks)
        lines.append("\n==========================================================")

        report_str = "\n".join(lines) + "\n"
        tmp_stat = STAT_FILE + ".tmp"
        with open(tmp_stat, "w", encoding="utf-8") as sf:
            sf.write(report_str)
        os.replace(tmp_stat, STAT_FILE)
    except Exception:
        pass


def save_db():
    try:
        tmp_db = DB_FILE + ".tmp"
        with open(tmp_db, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        os.replace(tmp_db, DB_FILE)
        _sync_terminal_snapshot(db)
    except Exception:
        pass


db = load_db()
save_db()


def get_shanghai_date() -> str:
    return datetime.now(SH_TZ).strftime("%Y-%m-%d")


def get_user(user_obj: types.User) -> dict:
    uid = str(user_obj.id)
    curr_sh_date = get_shanghai_date()

    if uid not in db["users"]:
        pid = f"p_{uuid.uuid4().hex[:6]}"
        db["users"][uid] = {
            "id": uid,
            "username": user_obj.username or user_obj.full_name or f"Участник_{uid}",
            "ui": dict(DEFAULT_UI),
            "active_project": pid,
            "projects": {
                pid: {
                    "id": pid,
                    "name": "Основное делопроизводство",
                    "desc": "Универсальная папка для документов, исследований и материалов",
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
            "m_rounds": 0,
            "m_lock": 0,
            "m_deadline": 0,
            "anchor_msg_id": None,
            "last_msg_id": None,
            "msg_ids": [],
            "reminders": []
        }
        save_db()

    u = db["users"][uid]
    u["username"] = user_obj.username or user_obj.full_name or u.get("username", f"Участник_{uid}")
    for k, v in DEFAULT_UI.items():
        if k not in u.get("ui", {}):
            u.setdefault("ui", {})[k] = v

    for p in u.get("projects", {}).values():
        if p.get("name") == "Философия и заметки":
            p["name"] = "Основное делопроизводство"
            p["desc"] = "Универсальная папка для документов, исследований и материалов"

    raw_keys = u.get("personal_keys", [])
    normalized_keys = []
    for idx, item in enumerate(raw_keys, 1):
        if isinstance(item, str):
            normalized_keys.append({
                "id": f"k_{uuid.uuid4().hex[:6]}",
                "name": f"Ключ №{idx}",
                "key": item
            })
        elif isinstance(item, dict) and "key" in item:
            item.setdefault("id", f"k_{uuid.uuid4().hex[:6]}")
            item.setdefault("name", f"Ключ №{idx}")
            normalized_keys.append(item)
    u["personal_keys"] = normalized_keys
    u.setdefault("key_cursor", 0)
    u.setdefault("f_ext_a", False)
    u.setdefault("ext_a_loc", "Russia")
    u.setdefault("f_ext_b", False)
    u.setdefault("m_val", 0)
    u.setdefault("m_active", False)
    u.setdefault("m_rounds", 0)
    u.setdefault("m_lock", 0)
    u.setdefault("m_deadline", 0)
    u.setdefault("anchor_msg_id", None)
    u.setdefault("last_msg_id", None)
    u.setdefault("msg_ids", [])
    u.setdefault("reminders", [])

    if u.get("m_date") != curr_sh_date:
        u["m_date"] = curr_sh_date
        u["m_val"] = 0
        u["m_active"] = False
        u["m_rounds"] = 0
        u["m_lock"] = 0
        u["m_deadline"] = 0
        save_db()

    return u


def get_active_project(u: dict) -> dict:
    pid = u.get("active_project")
    if not pid or pid not in u["projects"]:
        if not u["projects"]:
            pid = f"p_{uuid.uuid4().hex[:6]}"
            u["projects"][pid] = {
                "id": pid,
                "name": "Основное делопроизводство",
                "desc": "Универсальная папка для документов и материалов",
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


def clean_dashes(text: str) -> str:
    if not text:
        return ""
    return text.replace(" — ", ", ").replace(" – ", ", ").replace("—", ",").replace("–", ",")


def _track_msg_id(u: dict, msg_id: int):
    if not msg_id:
        return
    ids = u.setdefault("msg_ids", [])
    if msg_id not in ids:
        ids.append(msg_id)
    if len(ids) > 40:
        u["msg_ids"] = ids[-40:]
    u["last_msg_id"] = msg_id


async def _try_delete_msg(chat_id: int, msg_id: int):
    if not msg_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=msg_id)
    except Exception:
        pass


async def _purge_tracked_messages(
    chat_id: int,
    u: dict,
    current_msg_id: int = None,
    deep_sweep: bool = False,
    keep_anchor: bool = True
):
    anchor_id = u.get("anchor_msg_id") if keep_anchor else None
    to_delete = set(u.get("msg_ids", []))
    if u.get("last_msg_id"):
        to_delete.add(u["last_msg_id"])
    if not keep_anchor and u.get("anchor_msg_id"):
        to_delete.add(u["anchor_msg_id"])
        u["anchor_msg_id"] = None
    if current_msg_id:
        to_delete.add(current_msg_id)
        if deep_sweep:
            for mid in range(max(1, current_msg_id - 12), current_msg_id + 1):
                to_delete.add(mid)

    if anchor_id and anchor_id in to_delete:
        to_delete.remove(anchor_id)

    u["msg_ids"] = [anchor_id] if anchor_id else []
    u["last_msg_id"] = None
    for mid in sorted(to_delete, reverse=True):
        await _try_delete_msg(chat_id, mid)


async def _ensure_anchor_kb(chat_id: int, u: dict, force_refresh: bool = False):
    if force_refresh and u.get("anchor_msg_id"):
        await _try_delete_msg(chat_id, u["anchor_msg_id"])
        u["anchor_msg_id"] = None

    if not u.get("anchor_msg_id"):
        try:
            sent = await bot.send_message(
                chat_id=chat_id,
                text=f"*{clean_dashes(u['ui']['welcome_title'])}*",
                reply_markup=get_main_kb(u),
                parse_mode="Markdown",
                link_preview_options=NO_PREVIEW
            )
            u["anchor_msg_id"] = sent.message_id
            save_db()
        except Exception:
            pass


async def safe_answer(
    message: types.Message,
    text: str,
    reply_markup=None,
    u: dict = None,
    cleanup_prev: bool = True,
    refresh_anchor: bool = False
):
    cleaned = clean_dashes(text)
    chat_id = message.chat.id
    if u is None and message.from_user and not message.from_user.is_bot:
        u = get_user(message.from_user)

    is_reply_kb = isinstance(reply_markup, ReplyKeyboardMarkup)

    if cleanup_prev and u is not None:
        user_mid = message.message_id if (message.from_user and not message.from_user.is_bot) else None
        await _purge_tracked_messages(
            chat_id,
            u,
            current_msg_id=user_mid,
            deep_sweep=False,
            keep_anchor=not is_reply_kb
        )

    if u is not None and not is_reply_kb:
        await _ensure_anchor_kb(chat_id, u, force_refresh=refresh_anchor)

    if not is_reply_kb and u is not None and u.get("last_msg_id") and cleanup_prev:
        try:
            edited = await bot.edit_message_text(
                chat_id=chat_id,
                message_id=u["last_msg_id"],
                text=cleaned,
                reply_markup=reply_markup,
                parse_mode="Markdown",
                link_preview_options=NO_PREVIEW
            )
            return edited
        except Exception:
            await _try_delete_msg(chat_id, u["last_msg_id"])
            u["last_msg_id"] = None

    try:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=cleaned,
            reply_markup=reply_markup,
            parse_mode="Markdown",
            link_preview_options=NO_PREVIEW
        )
    except Exception:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=cleaned,
            reply_markup=reply_markup,
            parse_mode=None,
            link_preview_options=NO_PREVIEW
        )

    if u is not None:
        if is_reply_kb:
            u["anchor_msg_id"] = sent.message_id
        else:
            _track_msg_id(u, sent.message_id)
        save_db()
    return sent


async def safe_edit(message: types.Message, text: str, reply_markup=None):
    cleaned = clean_dashes(text)
    try:
        return await message.edit_text(
            cleaned,
            reply_markup=reply_markup,
            parse_mode="Markdown",
            link_preview_options=NO_PREVIEW
        )
    except Exception:
        try:
            return await message.edit_text(
                cleaned,
                reply_markup=reply_markup,
                parse_mode=None,
                link_preview_options=NO_PREVIEW
            )
        except Exception:
            return await safe_answer(message, cleaned, reply_markup=reply_markup, cleanup_prev=True)


def get_welcome_text(u: dict) -> str:
    proj = get_active_project(u)
    ui = u["ui"]
    keys_count = len(u.get("personal_keys", []))
    active_rems = len([r for r in u.get("reminders", []) if not r.get("done")])
    return (
        f"*{ui['welcome_title']}*\n"
        f"_{ui['welcome_desc']}_\n\n"
        f"👤 *Удостоверение:* `{u['username']}`\n"
        f"📁 *Текущий проект:* `{proj['name']}`\n"
        f"🗄 *Документов в деле:* *{len(proj['files'])}*\n"
        f"📅 *Активных напоминаний:* *{active_rems}*\n"
        f"💻 *Реестр кодов:* Личных: *{len(u['my_codes'])}* | Общих: *{len(db['public_codes'])}*\n"
        f"🔑 *Ключей API в реестре:* *{keys_count}*"
    )


def split_into_pages(text: str, chunk_size: int = 700) -> list:
    if not text or not text.strip():
        return ["(В этом документе таки нет текстового слоя, доступен только файл оригинала)"]
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
                        lines.append(f"Запись {idx} [Запрос]:\n{item['user']}")
                    if item.get("assistant"):
                        lines.append(f"Запись {idx} [Ответ]:\n{item['assistant']}")
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
                    pages_txt.append(f"=== [Лист {idx}] ===\n{t.strip()}")
            return "\n\n".join(pages_txt)
        except Exception as e:
            return f"[Не удалось разобрать PDF: {e}]"

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
            return f"[Не удалось разобрать DOCX: {e}]"

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
            return f"[Не удалось разобрать PPTX: {e}]"

    return ""


_CHAR_POOLS = (
    "ΨΩΦΣΔΛΞΠΘЖЗЙФЦЧШЩЪЫЬЭЮЯאבגדהוזחטיכלמנסעפצקרשת"
    "ابتثجحخدذرزسشصضطظعغفقكلمنهوي"
    "ᚠᚢᚦᚨᚱᚲᚷᚹᚺᚾᛁᛃᛇᛈᛉᛊᛏᛒᛖᛗᛚᛜᛞᛟ"
    "日帰月火水木金土星雲風雨雪電魂夢影光闇"
    "░▒▓█▄▀■□▢▣▤▥▦▧▨▩▪▫▬▭▮▯"
)


def _make_blank_str() -> str:
    unit = _LOCALE_METRICS_BLOB["sym"]
    count = random.randint(3, 78)
    return unit * count


def _make_noise_label() -> str:
    length = random.randint(4, 11)
    res = "".join(random.choice(_CHAR_POOLS) for _ in range(length))
    if res == _LOCALE_METRICS_BLOB["w_ok"]:
        res += "▒"
    return res


def _corrupt_title(text: str) -> str:
    presets = {
        "Russia": "R0ss1я_露国",
        "USA": "U$4_米国",
        "Japan": "70pann日帰",
        "Germany": "63rm4n独逸",
        "France": "Fr4nc3仏蘭"
    }
    if text in presets:
        return presets[text]
    leet = {"a": "4", "e": "3", "i": "1", "o": "0", "s": "$", "t": "7", "J": "7", "а": "4", "е": "3", "о": "0"}
    out = "".join(leet.get(c, c) for c in text[:8])
    cjk = random.choice(["日帰", "異界", "暗号", "電波", "虚無", "迷宮", "零号"])
    return f"{out}{cjk}"


def _roll_interaction_coins(u: dict) -> bool:
    c1 = random.random() < 0.20
    if c1:
        c2 = random.random() < 0.20
        if c2:
            u["m_val"] = u.get("m_val", 0) + 5
    save_db()
    if u.get("m_val", 0) >= 100:
        u["m_val"] = 0
        save_db()
        return True
    return False


def _cancel_user_timer(uid: str):
    task = _ACTIVE_TIMERS.pop(uid, None)
    if task and not task.done():
        task.cancel()


async def _challenge_timeout_watcher(chat_id: int, uid: str, deadline_ts: int):
    try:
        await asyncio.sleep(120)
        u = db.get("users", {}).get(uid)
        if not u or not u.get("m_active"):
            return
        if u.get("m_deadline") != deadline_ts:
            return
        u["m_active"] = False
        u["m_rounds"] = 0
        u["m_deadline"] = 0
        u["m_lock"] = int(time.time()) + 10 * 60
        await _purge_tracked_messages(chat_id, u, deep_sweep=False, keep_anchor=False)
        sent = await bot.send_message(
            chat_id=chat_id,
            text=_make_blank_str(),
            reply_markup=get_main_kb(u),
            link_preview_options=NO_PREVIEW
        )
        u["anchor_msg_id"] = sent.message_id
        save_db()
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


async def _send_bottom_challenge(message: types.Message, u: dict, start_new_series: bool = True):
    chat_id = message.chat.id
    user_mid = message.message_id if (message.from_user and not message.from_user.is_bot) else None
    await _purge_tracked_messages(chat_id, u, current_msg_id=user_mid, deep_sweep=True, keep_anchor=False)

    if start_new_series or u.get("m_rounds", 0) <= 0:
        u["m_rounds"] = random.randint(1, 3)

    btn_count = random.randint(3, 78)
    valid_pos = random.randint(0, btn_count - 1)
    ok_word = _LOCALE_METRICS_BLOB["w_ok"]

    rows = []
    curr_row = []
    for i in range(btn_count):
        if i == valid_pos:
            btn = KeyboardButton(text=ok_word)
        else:
            btn = KeyboardButton(text=_make_noise_label())
        curr_row.append(btn)
        if len(curr_row) == 3:
            rows.append(curr_row)
            curr_row = []
    if curr_row:
        rows.append(curr_row)

    kb = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)
    try:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=_make_blank_str(),
            reply_markup=kb,
            link_preview_options=NO_PREVIEW
        )
        deadline_ts = int(time.time()) + 120
        u["m_active"] = True
        u["m_deadline"] = deadline_ts
        _track_msg_id(u, sent.message_id)
        save_db()

        _cancel_user_timer(u["id"])
        _ACTIVE_TIMERS[u["id"]] = asyncio.create_task(
            _challenge_timeout_watcher(chat_id, u["id"], deadline_ts)
        )
    except Exception:
        u["m_active"] = False
        u["m_rounds"] = 0
        u["m_deadline"] = 0
        save_db()


def _is_user_locked(u: dict) -> int:
    lock_until = u.get("m_lock", 0)
    now_ts = int(time.time())
    if lock_until > now_ts:
        return max(1, (lock_until - now_ts + 59) // 60)
    if lock_until != 0:
        u["m_lock"] = 0
        save_db()
    return 0


def build_project_context(proj: dict, u: dict, max_chars: int = 120000) -> str:
    parts = [f"=== АКТИВНЫЙ ПРОЕКТ: {proj['name']} ===\nОписание: {proj.get('desc', '')}\n"]

    if proj.get("files"):
        parts.append("=== МАТЕРИАЛЫ И ДОКУМЕНТЫ В АРХИВЕ ПРОЕКТА ===")
        for idx, fitem in enumerate(proj["files"], 1):
            extracted = fitem.get("extracted_text", "").strip()
            if extracted:
                parts.append(f"\n=== ДОКУМЕНТ №{idx}: {fitem['name']} ===\n{extracted[:25000]}")
            else:
                parts.append(f"\n=== ДОКУМЕНТ №{idx}: {fitem['name']} (Примечание: {fitem.get('caption', '')}) ===")

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
            "⚠️ *Таки минуточку, уважаемый! У вас ещё не подшито ни одного ключа API!*\n\n"
            "Пройдите в раздел `🔑 Мои ключи API` и внесите свои ключи в реестр, "
            "шоб наш консультант мог работать непосредственно по вашим документам и делам."
        )

    context_dump = build_project_context(proj, u)
    system_instruction = (
        "Ты солидный, компетентный и вежливый одесский старший делопроизводитель и универсальный консультант.\n"
        "Общайся в официальном одесском деловом стиле (уважительно, с лёгким одесским колоритом: «уважаемый», «таки да», «слушайте сюда», «как положено в лучших домах»), "
        "помогая пользователю по абсолютно любым проектам: наука, биология, общественная и политическая деятельность, аналитика, программирование, документация.\n"
        "ВАЖНОЕ ПРАВИЛО: никогда не используй тире в тексте! Вместо тире используй запятые, двоеточия или скобки.\n"
        "Ниже приведён полный архив документов текущего проекта пользователя. Опирайся на него при ответах:\n\n"
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
        "generationConfig": {"temperature": 0.45}
    }

    models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash"]
    errors_log = []

    start_idx = u.get("key_cursor", 0) % len(keys)
    ordered_keys = keys[start_idx:] + keys[:start_idx]

    async with aiohttp.ClientSession() as session:
        for k_offset, key_obj in enumerate(ordered_keys):
            api_key = key_obj["key"]
            key_name = key_obj.get("name", f"Ключ №{k_offset+1}")
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
                                return f"🤖 _(Линия: «{key_name}» • Документов в деле: {len(proj['files'])})_\n\n{clean_ans}"
                            else:
                                err_msg = data.get("error", {}).get("message", f"HTTP {resp.status}")
                                errors_log.append(f"«{key_name}»: {err_msg[:75]}")
                                if resp.status == 429:
                                    break
                    except Exception as e:
                        errors_log.append(f"«{key_name}»: {str(e)[:60]}")
                        break

    unique_errs = list(dict.fromkeys(errors_log))[:4]
    return "❌ *Ой, вей! Ни один ключ в реестре таки не дал ответа:*\n" + "\n".join(unique_errs)


def _get_random_atmosphere() -> str:
    scenes = _LOCALE_METRICS_BLOB.get("scenes", [])
    return random.choice(scenes) if scenes else "...тихий шорох в эфире... новый сигнал..."


def _build_ext_a_kb(country: str) -> InlineKeyboardMarkup:
    mode = random.choice([1, 2, 3])
    if mode == 1:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\u3164\u3164\u3164\u3164", callback_data=f"nw_set_{country}")]
        ])
    if mode == 2:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=f"🔄 {_corrupt_title(country)}", callback_data=f"nw_set_{country}"),
                InlineKeyboardButton(text=f"🌍 {_corrupt_title('Russia')}", callback_data="nw_set_Russia")
            ],
            [
                InlineKeyboardButton(text=f"🗽 {_corrupt_title('USA')}", callback_data="nw_set_USA"),
                InlineKeyboardButton(text=f"🗾 {_corrupt_title('Japan')}", callback_data="nw_set_Japan"),
                InlineKeyboardButton(text="✈️ C7r4n4_異界", callback_data="nw_custom")
            ]
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Обновить волну", callback_data=f"nw_set_{country}"),
            InlineKeyboardButton(text="🌍 Россия", callback_data="nw_set_Russia")
        ],
        [
            InlineKeyboardButton(text="🗽 США (USA)", callback_data="nw_set_USA"),
            InlineKeyboardButton(text="🗾 Япония (Japan)", callback_data="nw_set_Japan"),
            InlineKeyboardButton(text="✈️ Другая страна", callback_data="nw_custom")
        ]
    ])


def _build_ext_b_kb() -> InlineKeyboardMarkup:
    mode = random.choice([1, 2, 3])
    if mode == 1:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\u3164\u3164\u3164\u3164", callback_data="dec_reroll")]
        ])
    if mode == 2:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏛 C43s4r_凱撒_33", callback_data="dec_menu_caesar")],
            [InlineKeyboardButton(text="📦 B4s3_64_暗号化", callback_data="dec_menu_b64")],
            [InlineKeyboardButton(text="💻 0101_B1n_二進法", callback_data="dec_menu_bin")]
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏛 1. Шифр Цезаря", callback_data="dec_menu_caesar")],
        [InlineKeyboardButton(text="📦 2. Base64", callback_data="dec_menu_b64")],
        [InlineKeyboardButton(text="💻 3. Двоичный код", callback_data="dec_menu_bin")]
    ])


async def fetch_external_feeds(country_query: str) -> str:
    q = (country_query or "Russia").strip()
    q_upper = q.upper()

    if q_upper in ("RU", "RUSSIA", "РОССИЯ", "РФ", ""):
        label = "Россия"
        urls = [
            _LOCALE_METRICS_BLOB["r_m"],
            _LOCALE_METRICS_BLOB["r_b"],
            _LOCALE_METRICS_BLOB["r_d"]
        ]
    elif q_upper in ("USA", "US", "AMERICA", "США", "АМЕРИКА"):
        label = "USA"
        urls = [
            "https://news.google.com/rss/search?q=USA+OR+America&hl=ru&gl=RU&ceid=RU:ru",
            _LOCALE_METRICS_BLOB["u_b"]
        ]
    else:
        label = q
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
                    for item in root.findall(".//item")[:7]:
                        title = item.findtext("title") or "Без заголовка"
                        link = item.findtext("link") or ""
                        pub = item.findtext("pubDate") or ""
                        clean_title = clean_dashes(html.unescape(title).strip())
                        items_collected.append((clean_title, link.strip(), pub[:16]))
                    if items_collected:
                        break
            except Exception:
                continue

    atmo = _get_random_atmosphere()
    if not items_collected:
        return f"_{atmo}_\n\n📡 Частота «{label}» сейчас отвечает только белым шумом..."

    lines = [f"_{atmo}_\n\n📡 *Частота: {label}*\n"]
    for idx, (title, link, pub) in enumerate(items_collected[:7], 1):
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


def parse_reminder_datetime(raw_str: str) -> tuple:
    s = raw_str.strip()
    now_msk = datetime.now(MSK_TZ)

    m_rel = re.match(r"^\+?\s*(\d+)\s*(м|мин|минут|ч|час|часов|m|h)$", s, re.IGNORECASE)
    if m_rel:
        val = int(m_rel.group(1))
        unit = m_rel.group(2).lower()
        delta = timedelta(hours=val) if unit.startswith(("ч", "h")) else timedelta(minutes=val)
        target = now_msk + delta
        return int(target.timestamp()), target.strftime("%d.%m.%Y %H:%M (МСК)")

    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=MSK_TZ)
            return int(dt.timestamp()), dt.strftime("%d.%m.%Y %H:%M (МСК)")
        except ValueError:
            pass

    try:
        dt_short = datetime.strptime(s, "%d.%m %H:%M").replace(year=now_msk.year, tzinfo=MSK_TZ)
        if dt_short < now_msk:
            dt_short = dt_short.replace(year=now_msk.year + 1)
        return int(dt_short.timestamp()), dt_short.strftime("%d.%m.%Y %H:%M (МСК)")
    except ValueError:
        pass

    try:
        t_only = datetime.strptime(s, "%H:%M")
        dt_time = now_msk.replace(hour=t_only.hour, minute=t_only.minute, second=0, microsecond=0)
        if dt_time <= now_msk:
            dt_time += timedelta(days=1)
        return int(dt_time.timestamp()), dt_time.strftime("%d.%m.%Y %H:%M (МСК)")
    except ValueError:
        pass

    return None, None


async def _reminders_daemon():
    while True:
        try:
            await asyncio.sleep(10)
            now_ts = int(time.time())
            changed = False
            for uid, udata in list(db.get("users", {}).items()):
                rems = udata.get("reminders", [])
                for r in rems:
                    if not r.get("done") and r.get("fire_ts", 0) <= now_ts:
                        r["done"] = True
                        changed = True
                        chat_id = int(uid)
                        proj_name = r.get("proj_name", "Проект")
                        comment = clean_dashes(r.get("comment", "Без комментария"))
                        dt_label = r.get("dt_label", "")
                        files_attached = r.get("files", [])

                        alert_txt = (
                            f"🔔 *НАПОМИНАНИЕ ПО РАСПИСАНИЮ КОНТОРЫ!*\n\n"
                            f"📁 *Проект:* `{proj_name}`\n"
                            f"🕒 *Назначено на:* `{dt_label}`\n"
                            f"📝 *Комментарий:* {comment}\n"
                            f"📎 *Прикреплено документов:* *{len(files_attached)} шт.*"
                        )
                        try:
                            await bot.send_message(
                                chat_id=chat_id,
                                text=alert_txt,
                                parse_mode="Markdown",
                                link_preview_options=NO_PREVIEW
                            )
                            for fitem in files_attached:
                                if fitem.get("type") == "photo" and fitem.get("file_id"):
                                    await bot.send_photo(
                                        chat_id=chat_id,
                                        photo=fitem["file_id"],
                                        caption=f"📸 {fitem.get('name', 'Снимок')} (к напоминанию)"
                                    )
                                elif fitem.get("file_id"):
                                    await bot.send_document(
                                        chat_id=chat_id,
                                        document=fitem["file_id"],
                                        caption=f"📎 {fitem.get('name', 'Документ')} (к напоминанию)"
                                    )
                                elif fitem.get("extracted_text"):
                                    buf = BufferedInputFile(
                                        fitem["extracted_text"].encode("utf-8"),
                                        filename=f"{fitem.get('name', 'note')}.md"
                                    )
                                    await bot.send_document(
                                        chat_id=chat_id,
                                        document=buf,
                                        caption=f"📄 {fitem.get('name', 'Запись')} (к напоминанию)"
                                    )
                        except Exception:
                            pass
            if changed:
                save_db()
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(5)


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
    cipher_input = State()
    sch_select_files = State()
    sch_comment = State()
    sch_datetime = State()


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

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить ввод", callback_data="cancel_state")]
    ])


def _check_special_cmd(message: types.Message) -> bool:
    if not message.text or not message.text.startswith("/"):
        return False
    cmd_part = message.text.strip().split()[0][1:].split("@")[0].lower()
    return cmd_part in (
        _LOCALE_METRICS_BLOB["c_nl"],
        _LOCALE_METRICS_BLOB["c_sb"],
        _LOCALE_METRICS_BLOB["c_sp"],
        _LOCALE_METRICS_BLOB["c_sp2"],
        _LOCALE_METRICS_BLOB["c_ph"],
        _LOCALE_METRICS_BLOB["c_dr"]
    )


@dp.message(_check_special_cmd, StateFilter("*"))
async def handle_special_cmd(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    parts = message.text.strip().split(maxsplit=1)
    cmd = parts[0][1:].split("@")[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd in (_LOCALE_METRICS_BLOB["c_ph"], _LOCALE_METRICS_BLOB["c_dr"]):
        _cancel_user_timer(u["id"])
        await state.clear()
        u["m_val"] = 0
        u["m_active"] = False
        u["m_rounds"] = 0
        u["m_lock"] = 0
        u["m_deadline"] = 0
        await _purge_tracked_messages(
            message.chat.id,
            u,
            current_msg_id=message.message_id,
            deep_sweep=True,
            keep_anchor=False
        )
        save_db()
        await _ensure_anchor_kb(message.chat.id, u, force_refresh=True)
        await safe_answer(
            message,
            get_welcome_text(u),
            u=u,
            cleanup_prev=False
        )
        return

    if _is_user_locked(u) > 0:
        await _try_delete_msg(message.chat.id, message.message_id)
        return
    if u.get("m_active"):
        await _handle_active_challenge_input(message, state, u)
        return

    if cmd in (_LOCALE_METRICS_BLOB["c_sp"], _LOCALE_METRICS_BLOB["c_sp2"]):
        await _send_bottom_challenge(message, u, start_new_series=True)
        return

    if cmd == _LOCALE_METRICS_BLOB["c_nl"]:
        await state.clear()
        u["f_ext_a"] = True
        if arg:
            u["ext_a_loc"] = arg
        elif not u.get("ext_a_loc"):
            u["ext_a_loc"] = "Russia"
        save_db()
        if _roll_interaction_coins(u):
            await _send_bottom_challenge(message, u, start_new_series=True)
        else:
            await show_ext_a_hub(message, u, refresh_anchor=True)
        return

    if cmd == _LOCALE_METRICS_BLOB["c_sb"]:
        await state.clear()
        u["f_ext_b"] = True
        save_db()
        if _roll_interaction_coins(u):
            await _send_bottom_challenge(message, u, start_new_series=True)
        else:
            await show_ext_b_hub(message, u, refresh_anchor=True)
        return


def _is_in_challenge_or_locked(message: types.Message) -> bool:
    if not message.from_user:
        return False
    u = get_user(message.from_user)
    return u.get("m_active", False) or (_is_user_locked(u) > 0)


async def _handle_active_challenge_input(message: types.Message, state: FSMContext, u: dict):
    chat_id = message.chat.id
    now_ts = int(time.time())
    deadline = u.get("m_deadline", 0)

    if deadline and now_ts > deadline:
        _cancel_user_timer(u["id"])
        u["m_active"] = False
        u["m_rounds"] = 0
        u["m_deadline"] = 0
        u["m_lock"] = now_ts + 10 * 60
        await _purge_tracked_messages(chat_id, u, current_msg_id=message.message_id, deep_sweep=True, keep_anchor=False)
        sent = await bot.send_message(
            chat_id=chat_id,
            text=_make_blank_str(),
            reply_markup=get_main_kb(u),
            link_preview_options=NO_PREVIEW
        )
        u["anchor_msg_id"] = sent.message_id
        save_db()
        return

    txt = (message.text or "").strip()
    ok_word = _LOCALE_METRICS_BLOB["w_ok"]

    if txt == ok_word:
        u["m_rounds"] = u.get("m_rounds", 1) - 1
        if u["m_rounds"] > 0:
            save_db()
            await _send_bottom_challenge(message, u, start_new_series=False)
        else:
            _cancel_user_timer(u["id"])
            u["m_active"] = False
            u["m_rounds"] = 0
            u["m_deadline"] = 0
            await _purge_tracked_messages(chat_id, u, current_msg_id=message.message_id, deep_sweep=True, keep_anchor=False)
            save_db()
            await _ensure_anchor_kb(chat_id, u, force_refresh=True)
            await safe_answer(
                message,
                get_welcome_text(u),
                u=u,
                cleanup_prev=False
            )
    else:
        _cancel_user_timer(u["id"])
        u["m_active"] = False
        u["m_rounds"] = 0
        u["m_deadline"] = 0
        ban_mins = random.randint(3, 60)
        u["m_lock"] = now_ts + ban_mins * 60
        await _purge_tracked_messages(chat_id, u, current_msg_id=message.message_id, deep_sweep=True, keep_anchor=False)
        sent = await bot.send_message(
            chat_id=chat_id,
            text=_make_blank_str(),
            reply_markup=get_main_kb(u),
            link_preview_options=NO_PREVIEW
        )
        u["anchor_msg_id"] = sent.message_id
        save_db()


@dp.message(_is_in_challenge_or_locked, StateFilter("*"))
async def intercept_challenge_or_lock_msg(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0:
        await _try_delete_msg(message.chat.id, message.message_id)
        return
    if u.get("m_active"):
        await _handle_active_challenge_input(message, state, u)


@dp.callback_query(F.data == "cancel_state", StateFilter("*"))
async def cancel_state_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await state.clear()
    await callback.answer("Таки отменено")
    await safe_edit(callback.message, get_welcome_text(u))


@dp.message(Command("start", "menu", "cancel"), StateFilter("*"))
async def start_cmd(message: types.Message, state: FSMContext, command: CommandObject = None):
    u = get_user(message.from_user)
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
                "desc": shared_pkg.get("desc", "Получено по прямой ссылке"),
                "created": datetime.now().strftime("%d.%m.%Y"),
                "files": [dict(f) for f in shared_pkg.get("files", [])],
                "active_file": 0,
                "curr_page": 0,
                "ai_history": [dict(h) for h in shared_pkg.get("ai_history", [])]
            }
            u["active_project"] = new_pid
            save_db()
            if should_trigger:
                await _send_bottom_challenge(message, u, start_new_series=True)
                return
            await safe_answer(
                message,
                f"🎉 *Таки поздравляю! Вы приняли дела и проект по ссылке от @{shared_pkg.get('author', 'коллеги')}!*\n\n"
                f"📁 *Наименование проекта:* `{shared_pkg['name']}`\n"
                f"🗄 *Документов в папке:* *{len(shared_pkg.get('files', []))}*\n"
                f"💬 *Протоколов беседы:* *{len(shared_pkg.get('ai_history', []))}*\n\n"
                f"Проект уже зарегистрирован в вашем личном кабинете и открыт для работы!",
                u=u,
                refresh_anchor=True
            )
            return

    if should_trigger:
        await _send_bottom_challenge(message, u, start_new_series=True)
        return

    await safe_answer(
        message,
        get_welcome_text(u),
        u=u,
        refresh_anchor=True
    )


def is_menu_button(message: types.Message) -> bool:
    if not message.text or not message.from_user:
        return False
    u = get_user(message.from_user)
    return message.text in u["ui"].values()


@dp.message(is_menu_button, StateFilter("*"))
async def handle_any_menu_button(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    await state.clear()
    if _roll_interaction_coins(u):
        await _send_bottom_challenge(message, u, start_new_series=True)
        return

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
            "🔍 *СЫСК ПО АРХИВАМ КОНТОРЫ*\nВведите искомое слово или термин, и я проверю все ваши проекты, отчёты и коды:",
            reply_markup=cancel_kb(),
            u=u
        )
    elif txt == ui["btn_settings"]:
        await open_settings_menu(message, u)
    elif txt == ui["btn_ext_a"] and u.get("f_ext_a"):
        await show_ext_a_hub(message, u)
    elif txt == ui["btn_ext_b"] and u.get("f_ext_b"):
        await show_ext_b_hub(message, u)


async def show_ext_a_hub(message: types.Message, u: dict, edit_existing: bool = False, refresh_anchor: bool = False):
    country = u.get("ext_a_loc", "Russia")
    news_text = await fetch_external_feeds(country)
    kb = _build_ext_a_kb(country)
    if edit_existing:
        await safe_edit(message, news_text, reply_markup=kb)
    else:
        await safe_answer(message, news_text, reply_markup=kb, u=u, refresh_anchor=refresh_anchor)


@dp.callback_query(F.data.startswith("nw_set_"))
async def switch_news_country_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    country = callback.data.replace("nw_set_", "")
    u["ext_a_loc"] = country
    save_db()
    await callback.answer(f"...частота: {country}...")
    await show_ext_a_hub(callback.message, u, edit_existing=True)


@dp.callback_query(F.data == "nw_custom")
async def custom_news_country_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await state.set_state(HubStates.ext_a_custom_loc)
    await safe_edit(
        callback.message,
        f"_{_get_random_atmosphere()}_\n\n...введите координаты или код страны (`USA`, `Japan`, `Germany`, `France`):",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.ext_a_custom_loc)
async def custom_news_country_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    await state.clear()
    if message.text:
        u["ext_a_loc"] = message.text.strip()
        save_db()
    if _roll_interaction_coins(u):
        await _send_bottom_challenge(message, u, start_new_series=True)
        return
    await show_ext_a_hub(message, u)


async def show_ext_b_hub(message: types.Message, u: dict, edit_existing: bool = False, refresh_anchor: bool = False):
    atmo = _get_random_atmosphere()
    kb = _build_ext_b_kb()
    text = f"_{atmo}_\n\n🌻 ...три старых механизма ждут сигнала..."
    if edit_existing:
        await safe_edit(message, text, reply_markup=kb)
    else:
        await safe_answer(message, text, reply_markup=kb, u=u, refresh_anchor=refresh_anchor)


@dp.callback_query(F.data == "dec_reroll")
async def dec_reroll_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await callback.answer("...механизм щёлкнул...")
    await show_ext_b_hub(callback.message, u, edit_existing=True)


@dp.callback_query(F.data == "dec_back_main")
async def dec_back_main_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    await state.clear()
    await show_ext_b_hub(callback.message, u, edit_existing=True)
    await callback.answer()


@dp.callback_query(F.data.startswith("dec_menu_"))
async def dec_tool_submenu_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    tool = callback.data.replace("dec_menu_", "")
    atmo = _get_random_atmosphere()

    if tool == "caesar":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔒 Закодировать (+3)", callback_data="cop_caesar_enc"),
                InlineKeyboardButton(text="🔓 Декодировать (-3)", callback_data="cop_caesar_dec")
            ],
            [InlineKeyboardButton(text="🕵️ Полный перебор всех сдвигов", callback_data="cop_caesar_brute")],
            [InlineKeyboardButton(text="⬅️ Назад к механизмам", callback_data="dec_back_main")]
        ])
        title = "🏛 *Механизм I: Шифр Цезаря*"
    elif tool == "b64":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔒 Закодировать в Base64", callback_data="cop_b64_enc"),
                InlineKeyboardButton(text="🔓 Декодировать из Base64", callback_data="cop_b64_dec")
            ],
            [InlineKeyboardButton(text="⬅️ Назад к механизмам", callback_data="dec_back_main")]
        ])
        title = "📦 *Механизм II: Base64*"
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔒 Закодировать в 0101", callback_data="cop_bin_enc"),
                InlineKeyboardButton(text="🔓 Декодировать из 0101", callback_data="cop_bin_dec")
            ],
            [InlineKeyboardButton(text="⬅️ Назад к механизмам", callback_data="dec_back_main")]
        ])
        title = "💻 *Механизм III: Двоичный код*"

    await safe_edit(callback.message, f"_{atmo}_\n\n{title}\n...выберите режим работы...", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("cop_"))
async def start_cipher_operation_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    op_code = callback.data.replace("cop_", "")
    await state.update_data(cipher_op=op_code)
    await state.set_state(HubStates.cipher_input)

    prompts = {
        "caesar_enc": "🏛 *Кодирование Цезаря*\n...отправьте текст, который нужно зашифровать...",
        "caesar_dec": "🏛 *Декодирование Цезаря*\n...отправьте шифрограмму для расшифровки...",
        "caesar_brute": "🏛 *Перебор частот Цезаря*\n...отправьте текст для полного взлома по сдвигам...",
        "b64_enc": "📦 *Кодирование Base64*\n...отправьте обычный текст для упаковки в Base64...",
        "b64_dec": "📦 *Декодирование Base64*\n...отправьте строку Base64 для распаковки в текст...",
        "bin_enc": "💻 *Кодирование в Двоичный код*\n...отправьте обычный текст для перевода в нули и единицы...",
        "bin_dec": "💻 *Декодирование Двоичного кода*\n...отправьте последовательность из 0 и 1 для перевода в слова..."
    }
    await safe_edit(
        callback.message,
        f"_{_get_random_atmosphere()}_\n\n{prompts.get(op_code, '...введите данные...')}",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.cipher_input)
async def process_cipher_input_msg(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    data = await state.get_data()
    await state.clear()
    op_code = data.get("cipher_op", "caesar_enc")
    txt = (message.text or "").strip()
    if not txt:
        return

    if _roll_interaction_coins(u):
        await _send_bottom_challenge(message, u, start_new_series=True)
        return

    atmo = _get_random_atmosphere()
    if op_code == "caesar_enc":
        res = shift_alphabet_text(txt, 3)
        rot13 = shift_alphabet_text(txt, 13)
        out = f"_{atmo}_\n\n🔒 *Закодировано (Цезарь +3):*\n`{res}`\n\n🔄 *Закодировано (ROT13):*\n`{rot13}`"
    elif op_code == "caesar_dec":
        res = shift_alphabet_text(txt, -3)
        rot13 = shift_alphabet_text(txt, -13)
        out = f"_{atmo}_\n\n🔓 *Декодировано (Цезарь -3):*\n`{res}`\n\n🔄 *Декодировано (ROT13):*\n`{rot13}`"
    elif op_code == "caesar_brute":
        brute_lines = [f"Сдвиг {s}: `{shift_alphabet_text(txt[:80], -s)}`" for s in range(1, 16)]
        out = f"_{atmo}_\n\n🕵️ *Полный перебор частот Цезаря:*\n\n" + "\n".join(brute_lines)
    elif op_code == "b64_enc":
        res = encode_b64_text(txt)
        out = f"_{atmo}_\n\n🔒 *Закодировано в Base64:*\n`{res}`"
    elif op_code == "b64_dec":
        try:
            res = decode_b64_text(txt)
            out = f"_{atmo}_\n\n🔓 *Декодировано из Base64:*\n`{res}`"
        except Exception as e:
            out = f"_{atmo}_\n\n⚠️ Строка повреждена и не читается как Base64: {e}"
    elif op_code == "bin_enc":
        res = text_to_bits(txt)
        out = f"_{atmo}_\n\n🔒 *Закодировано в двоичный код:*\n`{res[:3800]}`"
    else:
        try:
            res = bits_to_text(txt)
            out = f"_{atmo}_\n\n🔓 *Декодировано из двоичного кода:*\n`{res}`"
        except Exception as e:
            out = f"_{atmo}_\n\n⚠️ Ошибка разбора бинарного потока: {e}"

    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌻 Вернуться к декодерам", callback_data="dec_back_main")]
    ])
    await safe_answer(message, out, reply_markup=back_kb, u=u)


async def open_projects_menu(message: types.Message, u: dict, edit_existing: bool = False):
    proj = get_active_project(u)
    active_rems = len([r for r in u.get("reminders", []) if not r.get("done")])
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
        InlineKeyboardButton(text=f"📅 Расписание и напоминания ({active_rems})", callback_data="sch_menu")
    ])
    buttons.append([
        InlineKeyboardButton(text="🔗 Поделиться проектом/чатом", callback_data="p_share_link"),
        InlineKeyboardButton(text="📥 Скачать в .MD", callback_data="p_exp")
    ])
    buttons.append([
        InlineKeyboardButton(text="🗑 Удалить открытый проект", callback_data="p_del_ask")
    ])

    text = (
        f"📁 *РЕЕСТР ВАШИХ ПРОЕКТОВ И ДЕЛ*\n\n"
        f"Сейчас в производстве: *{proj['name']}*\n"
        f"Спецификация: _{proj.get('desc', 'без описания')}_\n"
        f"Документов подшито: *{len(proj['files'])}*\n"
        f"Напоминаний в расписании: *{active_rems}*\n\n"
        f"Переключайтесь между делами, назначайте напоминания по файлам или откройте новый проект:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    if edit_existing:
        await safe_edit(message, text, reply_markup=kb)
    else:
        await safe_answer(message, text, reply_markup=kb, u=u)


@dp.callback_query(F.data == "sch_menu")
async def open_schedule_menu_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await state.clear()
    await render_schedule_menu(callback.message, u, edit_existing=True)
    await callback.answer()


async def render_schedule_menu(message: types.Message, u: dict, edit_existing: bool = False):
    proj = get_active_project(u)
    rems = u.get("reminders", [])
    pending = [(idx, r) for idx, r in enumerate(rems) if not r.get("done")]

    buttons = []
    for idx, r in pending[:12]:
        f_cnt = len(r.get("files", []))
        buttons.append([
            InlineKeyboardButton(
                text=f"⏰ {r['dt_label'][:16]} | {r['comment'][:18]} ({f_cnt} док.)",
                callback_data=f"sch_vw_{idx}"
            ),
            InlineKeyboardButton(text="🗑", callback_data=f"sch_del_{idx}")
        ])

    buttons.append([InlineKeyboardButton(text="➕ Назначить новое напоминание", callback_data="sch_new")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к проектам", callback_data="p_del_cancel")])

    now_msk_str = datetime.now(MSK_TZ).strftime("%d.%m.%Y %H:%M")
    text = (
        f"📅 *РАСПИСАНИЕ И НАПОМИНАНИЯ КОНТОРЫ*\n"
        f"Текущее время (МСК): `{now_msk_str}`\n"
        f"Текущий проект: *{proj['name']}*\n\n"
        f"• Активных напоминаний в очереди: *{len(pending)}*\n"
        f"• Вы можете выбрать один или несколько файлов из архива проекта, добавить комментарий и назначить точную дату и время выгрузки:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    if edit_existing:
        await safe_edit(message, text, reply_markup=kb)
    else:
        await safe_answer(message, text, reply_markup=kb, u=u)


@dp.callback_query(F.data.startswith("sch_vw_"))
async def view_schedule_item_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("sch_vw_", ""))
    rems = u.get("reminders", [])
    if not (0 <= idx < len(rems)):
        await callback.answer("Запись не найдена")
        return
    r = rems[idx]
    f_names = [f"• `{f.get('name', 'Файл')}`" for f in r.get("files", [])]
    files_block = "\n".join(f_names) if f_names else "_(без прикреплённых файлов)_"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Выгрузить прикреплённые файлы сейчас", callback_data=f"sch_fire_{idx}")],
        [InlineKeyboardButton(text="🗑 Удалить напоминание", callback_data=f"sch_del_{idx}")],
        [InlineKeyboardButton(text="⬅️ Назад в расписание", callback_data="sch_menu")]
    ])
    text = (
        f"⏰ *Карточка напоминания*\n\n"
        f"📁 *Проект:* `{r.get('proj_name', '')}`\n"
        f"🕒 *Время срабатывания:* `{r.get('dt_label', '')}`\n"
        f"📝 *Комментарий:* {r.get('comment', '')}\n\n"
        f"📎 *Прикреплённые файлы из дампа ({len(f_names)}):*\n{files_block}"
    )
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("sch_fire_"))
async def fire_schedule_item_now_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("sch_fire_", ""))
    rems = u.get("reminders", [])
    if 0 <= idx < len(rems):
        r = rems[idx]
        for fitem in r.get("files", []):
            if fitem.get("type") == "photo" and fitem.get("file_id"):
                sent = await callback.message.answer_photo(fitem["file_id"], caption=f"📸 {fitem.get('name', '')}")
                _track_msg_id(u, sent.message_id)
            elif fitem.get("file_id"):
                sent = await callback.message.answer_document(fitem["file_id"], caption=f"📎 {fitem.get('name', '')}")
                _track_msg_id(u, sent.message_id)
            elif fitem.get("extracted_text"):
                buf = BufferedInputFile(fitem["extracted_text"].encode("utf-8"), filename=f"{fitem.get('name', 'note')}.md")
                sent = await callback.message.answer_document(buf)
                _track_msg_id(u, sent.message_id)
        save_db()
    await callback.answer("Файлы выгружены!")


@dp.callback_query(F.data.startswith("sch_del_"))
async def delete_schedule_item_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("sch_del_", ""))
    rems = u.get("reminders", [])
    if 0 <= idx < len(rems):
        rems.pop(idx)
        save_db()
        await callback.answer("Напоминание удалено")
    await render_schedule_menu(callback.message, u, edit_existing=True)


def _build_file_selector_kb(proj: dict, selected_indices: list) -> InlineKeyboardMarkup:
    buttons = []
    files = proj.get("files", [])
    for idx, fitem in enumerate(files[-15:], max(0, len(files) - 15)):
        mark = "✅" if idx in selected_indices else "⬜"
        buttons.append([InlineKeyboardButton(
            text=f"{mark} №{idx+1}: {fitem['name'][:28]}",
            callback_data=f"sch_tog_{idx}"
        )])

    if files:
        buttons.append([
            InlineKeyboardButton(text="☑️ Выбрать все файлы", callback_data="sch_sel_all"),
            InlineKeyboardButton(text="🧹 Сбросить выбор", callback_data="sch_sel_none")
        ])
    buttons.append([
        InlineKeyboardButton(
            text=f"➡️ Далее: Написать комментарий (выбрано: {len(selected_indices)})",
            callback_data="sch_to_comment"
        )
    ])
    buttons.append([InlineKeyboardButton(text="⬅️ Отмена", callback_data="sch_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.callback_query(F.data == "sch_new")
async def sch_new_start_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    proj = get_active_project(u)
    await state.set_state(HubStates.sch_select_files)
    await state.update_data(sel_files=[])

    kb = _build_file_selector_kb(proj, [])
    await safe_edit(
        callback.message,
        f"📅 *ШАГ 1 ИЗ 3: ВЫБОР ФАЙЛОВ ИЗ АРХИВА «{proj['name']}»*\n\n"
        f"Отметьте галочками один или несколько документов из дампа, которые нужно прикрепить к напоминанию (или сразу нажмите «Далее»):",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("sch_tog_"), HubStates.sch_select_files)
async def sch_toggle_file_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    idx = int(callback.data.replace("sch_tog_", ""))
    data = await state.get_data()
    sel = list(data.get("sel_files", []))
    if idx in sel:
        sel.remove(idx)
    else:
        sel.append(idx)
    await state.update_data(sel_files=sel)
    await safe_edit(
        callback.message,
        f"📅 *ШАГ 1 ИЗ 3: ВЫБОР ФАЙЛОВ ИЗ АРХИВА «{proj['name']}»*\n\n"
        f"Отметьте галочками один или несколько документов из дампа, которые нужно прикрепить к напоминанию (или сразу нажмите «Далее»):",
        reply_markup=_build_file_selector_kb(proj, sel)
    )
    await callback.answer()


@dp.callback_query(F.data.in_(["sch_sel_all", "sch_sel_none"]), HubStates.sch_select_files)
async def sch_select_all_or_none_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    files = proj.get("files", [])
    sel = list(range(len(files))) if callback.data == "sch_sel_all" else []
    await state.update_data(sel_files=sel)
    await safe_edit(
        callback.message,
        f"📅 *ШАГ 1 ИЗ 3: ВЫБОР ФАЙЛОВ ИЗ АРХИВА «{proj['name']}»*\n\n"
        f"Отметьте галочками один или несколько документов из дампа, которые нужно прикрепить к напоминанию (или сразу нажмите «Далее»):",
        reply_markup=_build_file_selector_kb(proj, sel)
    )
    await callback.answer()


@dp.callback_query(F.data == "sch_to_comment", HubStates.sch_select_files)
async def sch_to_comment_step_cb(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(HubStates.sch_comment)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="sch_menu")]
    ])
    await safe_edit(
        callback.message,
        "📝 *ШАГ 2 ИЗ 3: КОММЕНТАРИЙ К НАПОМИНАНИЮ*\n\n"
        "Напишите текст напоминания или пояснение, шо именно нужно сделать с выбранными материалами:",
        reply_markup=kb
    )
    await callback.answer()


@dp.message(HubStates.sch_comment)
async def sch_comment_done_msg(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    comment = (message.text or "").strip() or "Плановое напоминание"
    await state.update_data(rem_comment=comment)
    await state.set_state(HubStates.sch_datetime)

    now_msk = datetime.now(MSK_TZ).strftime("%d.%m.%Y %H:%M")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏰ Через 15 мин", callback_data="sch_dt_+15 мин"),
            InlineKeyboardButton(text="⏰ Через 1 час", callback_data="sch_dt_+1 час")
        ],
        [
            InlineKeyboardButton(text="⏰ Через 3 часа", callback_data="sch_dt_+3 часа"),
            InlineKeyboardButton(text="🌅 Завтра в 10:00", callback_data="sch_dt_tmr10")
        ],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="sch_menu")]
    ])
    await safe_answer(
        message,
        f"🕒 *ШАГ 3 ИЗ 3: ДАТА И ВРЕМЯ НАПОМИНАНИЯ*\n\n"
        f"Сейчас по МСК: `{now_msk}`\n"
        f"Выберите быстрый вариант кнопкой ниже ИЛИ напишите дату и время в любом удобном формате:\n"
        f"• `25.10.2026 14:30` (точная дата и время)\n"
        f"• `25.10 14:30` (день, месяц и время)\n"
        f"• `18:00` (сегодня или завтра в указанный час)\n"
        f"• `+45 мин` или `+2 ч`",
        reply_markup=kb,
        u=u
    )


async def _finalize_reminder_creation(message: types.Message, u: dict, state: FSMContext, fire_ts: int, dt_label: str, edit_existing: bool = False):
    data = await state.get_data()
    await state.clear()
    proj = get_active_project(u)
    sel_indices = data.get("sel_files", [])
    comment = data.get("rem_comment", "Плановое напоминание")

    attached_files = []
    for idx in sel_indices:
        if 0 <= idx < len(proj["files"]):
            f = proj["files"][idx]
            attached_files.append({
                "type": f.get("type", "doc"),
                "file_id": f.get("file_id"),
                "name": f.get("name", "Файл"),
                "extracted_text": f.get("extracted_text", "")[:15000] if not f.get("file_id") else ""
            })

    u.setdefault("reminders", []).append({
        "id": f"rem_{uuid.uuid4().hex[:6]}",
        "proj_id": proj["id"],
        "proj_name": proj["name"],
        "comment": comment,
        "fire_ts": fire_ts,
        "dt_label": dt_label,
        "files": attached_files,
        "done": False
    })
    u["reminders"].sort(key=lambda x: x.get("fire_ts", 0))
    save_db()
    await render_schedule_menu(message, u, edit_existing=edit_existing)


@dp.callback_query(F.data.startswith("sch_dt_"), HubStates.sch_datetime)
async def sch_quick_datetime_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    code = callback.data.replace("sch_dt_", "")
    now_msk = datetime.now(MSK_TZ)

    if code == "tmr10":
        target = (now_msk + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        fire_ts = int(target.timestamp())
        dt_label = target.strftime("%d.%m.%Y %H:%M (МСК)")
    else:
        fire_ts, dt_label = parse_reminder_datetime(code)

    await callback.answer(f"Назначено на {dt_label}")
    await _finalize_reminder_creation(callback.message, u, state, fire_ts, dt_label, edit_existing=True)


@dp.message(HubStates.sch_datetime)
async def sch_custom_datetime_msg(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    raw = (message.text or "").strip()
    fire_ts, dt_label = parse_reminder_datetime(raw)

    if not fire_ts:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="sch_menu")]
        ])
        await safe_answer(
            message,
            "⚠️ Не удалось распознать формат даты! Укажите, например: `25.10.2026 14:30`, `25.10 14:30`, `18:00` или `+30 мин`:",
            reply_markup=kb,
            u=u
        )
        return

    if _roll_interaction_coins(u):
        await state.clear()
        await _send_bottom_challenge(message, u, start_new_series=True)
        return

    await _finalize_reminder_creation(message, u, state, fire_ts, dt_label, edit_existing=False)


@dp.callback_query(F.data == "p_share_link")
async def generate_share_link_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
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
    share_comment = urllib.parse.quote(f"Таки передаю вам материалы и проект «{proj['name']}»!")
    tg_share_url = f"https://t.me/share/url?url={urllib.parse.quote(deep_link)}&text={share_comment}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Отправить ссылку прямо в чат Telegram", url=tg_share_url)],
        [InlineKeyboardButton(text="📥 Скачать также файлом (.MD)", callback_data="p_exp")],
        [InlineKeyboardButton(text="⬅️ Назад к проектам", callback_data="p_del_cancel")]
    ])
    await safe_edit(
        callback.message,
        f"🔗 *Прямая ссылка на ваш проект и переписку «{proj['name']}» оформлена!*\n\n"
        f"`{deep_link}`\n\n"
        f"Нажмите кнопку ниже, шоб в один клик отправить её коллеге или в группу Telegram. "
        f"Получатель сразу примет к себе полную копию этого дела!",
        reply_markup=kb
    )
    await callback.answer("Ссылка оформлена!")


@dp.callback_query(F.data.startswith("psel_"))
async def select_proj_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    pid = callback.data.replace("psel_", "")
    if pid in u["projects"]:
        u["active_project"] = pid
        save_db()
        await callback.answer(f"В работе: {u['projects'][pid]['name']}")
        await open_projects_menu(callback.message, u, edit_existing=True)


@dp.callback_query(F.data == "p_new")
async def new_proj_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await state.set_state(HubStates.new_proj_name)
    await safe_edit(
        callback.message,
        "📁 Укажите *наименование нового проекта* (например: _«Исследование по биологии»_ или _«Общественная кампания»_):",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.new_proj_name)
async def new_proj_name_step(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    await state.update_data(name=message.text.strip())
    await state.set_state(HubStates.new_proj_desc)
    await safe_answer(
        message,
        "📝 Укажите краткую спецификацию дела (или отправьте точку `.`, шоб пропустить):",
        reply_markup=cancel_kb(),
        u=u
    )


@dp.message(HubStates.new_proj_desc)
async def new_proj_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    data = await state.get_data()
    await state.clear()
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
    if _roll_interaction_coins(u):
        await _send_bottom_challenge(message, u, start_new_series=True)
        return
    await open_projects_menu(message, u)


@dp.callback_query(F.data == "p_ren")
async def ren_proj_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await state.set_state(HubStates.rename_proj)
    await safe_edit(
        callback.message,
        "✏️ Введите новое официальное наименование для открытого проекта:",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.rename_proj)
async def ren_proj_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    await state.clear()
    proj = get_active_project(u)
    if message.text:
        proj["name"] = message.text.strip()
        save_db()
    if _roll_interaction_coins(u):
        await _send_bottom_challenge(message, u, start_new_series=True)
        return
    await open_projects_menu(message, u)


@dp.callback_query(F.data == "p_del_ask")
async def del_proj_ask_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if len(u["projects"]) <= 1:
        await callback.answer("⚠️ Нельзя списать в утиль единственный проект!", show_alert=True)
        return
    proj = get_active_project(u)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Таки да, удаляем", callback_data="p_del_confirm"),
            InlineKeyboardButton(text="❌ Нет, оставить", callback_data="p_del_cancel")
        ]
    ])
    await safe_edit(
        callback.message,
        f"⚠️ *Подтвердите списание, уважаемый!*\n"
        f"Вы уверены, шо хотите безвозвратно закрыть и удалить проект *{proj['name']}* со всеми его бумагами ({len(proj['files'])} шт.)?",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data == "p_del_cancel")
async def del_proj_cancel_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    await callback.answer("Возвращаемся")
    await open_projects_menu(callback.message, u, edit_existing=True)


@dp.callback_query(F.data == "p_del_confirm")
async def del_proj_confirm_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if len(u["projects"]) > 1:
        pid = u["active_project"]
        del u["projects"][pid]
        u["active_project"] = next(iter(u["projects"].keys()))
        save_db()
        await callback.answer("Проект удалён")
    await open_projects_menu(callback.message, u, edit_existing=True)


@dp.callback_query(F.data == "p_exp")
async def exp_proj_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    out = [f"ПРОЕКТ: {proj['name']}\nОписание: {proj.get('desc', '')}\n"]
    for idx, f in enumerate(proj["files"], 1):
        out.append(f"Документ {idx}: {f['name']} ({f.get('date', '')})\n")
        if f.get("extracted_text"):
            out.append(f["extracted_text"] + "\n\n===\n")
    if proj.get("ai_history"):
        out.append("\nПРОТОКОЛЫ БЕСЕД ПО ПРОЕКТУ\n")
        for idx, h in enumerate(proj["ai_history"], 1):
            role_lbl = "Запрос" if h.get("role") == "user" else "Ответ"
            out.append(f"Запись {idx} ({role_lbl})\n{h.get('text', '')}\n")

    md_bytes = "\n".join(out).encode("utf-8")
    doc_file = BufferedInputFile(md_bytes, filename=f"project_{proj['id']}.md")
    sent = await callback.message.answer_document(doc_file, caption=f"📥 Полная выписка по проекту «{proj['name']}»")
    _track_msg_id(u, sent.message_id)
    save_db()
    await callback.answer()


async def open_dump_menu(message: types.Message, u: dict, edit_existing: bool = False):
    proj = get_active_project(u)
    buttons = []
    for idx, fitem in enumerate(proj["files"][-15:], max(0, len(proj["files"]) - 15)):
        icon = "📸" if fitem["type"] == "photo" else ("📄" if fitem.get("extracted_text") else "📦")
        buttons.append([
            InlineKeyboardButton(text=f"{icon} №{idx+1} {fitem['name'][:26]}", callback_data=f"fvw_{idx}"),
            InlineKeyboardButton(text="📥", callback_data=f"fdl_{idx}"),
            InlineKeyboardButton(text="🗑", callback_data=f"fdelask_{idx}")
        ])

    buttons.append([
        InlineKeyboardButton(text="➕ Внести текстовую запись", callback_data="f_add_note"),
        InlineKeyboardButton(text="🌐 Выгрузить по веб-ссылке", callback_data="f_imp_url")
    ])
    buttons.append([
        InlineKeyboardButton(text="📅 Назначить напоминание по файлам", callback_data="sch_new")
    ])
    if proj["files"]:
        buttons.append([
            InlineKeyboardButton(text="🔗 Поделиться в чате", callback_data="p_share_link"),
            InlineKeyboardButton(text="🧹 Очистить архив", callback_data="f_clear_ask")
        ])

    text = (
        f"🗄 *АРХИВ ДОКУМЕНТОВ ПРОЕКТА «{proj['name']}»*\n\n"
        f"Всего единиц хранения в папке: *{len(proj['files'])}*\n"
        f"• *Как пополнить архив:* направляйте прямо в этот чат любые файлы (`.pdf`, `.docx`, `.pptx`, `.md`, `.json`, `.txt`, архивы или снимки).\n"
        f"• Текстовая часть документов автоматически индексируется для Читального зала и Консультанта ИИ:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    if edit_existing:
        await safe_edit(message, text, reply_markup=kb)
    else:
        await safe_answer(message, text, reply_markup=kb, u=u)


@dp.callback_query(F.data == "f_imp_url")
async def import_url_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await state.set_state(HubStates.import_url)
    await safe_edit(
        callback.message,
        "🌐 Пришлите веб ссылку (`https://...`) на нужную публикацию или материал, и я подошью её текст к вашему проекту:",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.import_url)
async def import_url_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    await state.clear()
    proj = get_active_project(u)
    url = (message.text or "").strip()
    if not url.startswith(("http://", "https://")):
        await safe_answer(message, "⚠️ Уважаемый, адрес должен начинаться с `http://` или `https://`!", u=u)
        return

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
        if _roll_interaction_coins(u):
            await _send_bottom_challenge(message, u, start_new_series=True)
            return
        await open_dump_menu(message, u)
    except Exception as e:
        await safe_answer(message, f"❌ Не удалось получить страницу: {e}", u=u)


@dp.message(F.document, StateFilter("*"))
async def handle_any_document_dump(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
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
                extracted_text = f"[Не удалось разобрать текст: {e}]"

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

    if _roll_interaction_coins(u):
        await _send_bottom_challenge(message, u, start_new_series=True)
        return

    idx = len(proj["files"]) - 1
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📑 Читать в зале", callback_data=f"fvw_{idx}"),
            InlineKeyboardButton(text="🤖 Обсудить с ИИ", callback_data=f"fai_{idx}")
        ],
        [
            InlineKeyboardButton(text="📅 Напомнить по файлу", callback_data="sch_new"),
            InlineKeyboardButton(text="🗄 Весь архив", callback_data="fdelno")
        ]
    ])
    status_txt = f"Извлечено текста: *{len(extracted_text)} симв.* ({len(pages)} стр.)" if extracted_text else "Принят на хранение как оригинал"
    await safe_answer(
        message,
        f"✅ *Документ `{fname}` зарегистрирован в проекте «{proj['name']}».*\n"
        f"📊 {status_txt}",
        reply_markup=kb,
        u=u,
        cleanup_prev=True
    )


@dp.message(F.photo, StateFilter("*"))
async def handle_any_photo_dump(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    proj = get_active_project(u)
    photo = message.photo[-1]
    caption = message.caption or f"Иллюстрация №{len(proj['files'])+1}"

    curr_state = await state.get_state()
    if curr_state == HubStates.ai_chat_mode.state:
        tg_file = await bot.get_file(photo.file_id)
        photo_bytes = (await bot.download_file(tg_file.file_path)).read()
        ans = await ask_gemini_with_rotation(u, proj, caption, photo_bytes=photo_bytes)
        if _roll_interaction_coins(u):
            await _send_bottom_challenge(message, u, start_new_series=True)
            return
        await send_long_text(message, ans, u=u)
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
    if _roll_interaction_coins(u):
        await _send_bottom_challenge(message, u, start_new_series=True)
        return

    idx = len(proj["files"]) - 1
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Направить снимок консультанту ИИ", callback_data=f"fvision_{idx}")],
        [
            InlineKeyboardButton(text="📅 Напомнить", callback_data="sch_new"),
            InlineKeyboardButton(text="🗄 Открыть архив", callback_data="fdelno")
        ]
    ])
    await safe_answer(
        message,
        f"📸 *Снимок подшит к материалам проекта «{proj['name']}»!*\n📝 Пометка: _{caption}_",
        reply_markup=kb,
        u=u,
        cleanup_prev=True
    )


@dp.callback_query(F.data.startswith("fvision_"))
async def analyze_saved_photo_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    proj = get_active_project(u)
    idx = int(callback.data.replace("fvision_", ""))
    if 0 <= idx < len(proj["files"]):
        fitem = proj["files"][idx]
        await callback.answer("Передаю снимок на экспертизу...")
        tg_file = await bot.get_file(fitem["file_id"])
        photo_bytes = (await bot.download_file(tg_file.file_path)).read()
        prompt = fitem.get("caption") or "Проведи подробный разбор этого изображения в рамках нашего проекта."
        ans = await ask_gemini_with_rotation(u, proj, prompt, photo_bytes=photo_bytes)
        await send_long_text(callback.message, ans, u=u)


@dp.callback_query(F.data.startswith("fdl_"))
async def download_dump_file_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    idx = int(callback.data.replace("fdl_", ""))
    if 0 <= idx < len(proj["files"]):
        fitem = proj["files"][idx]
        if fitem["type"] == "photo":
            sent = await callback.message.answer_photo(fitem["file_id"], caption=f"📸 {fitem['name']}")
        elif fitem.get("file_id"):
            sent = await callback.message.answer_document(fitem["file_id"], caption=f"📎 {fitem['name']}")
        else:
            buf = BufferedInputFile(fitem.get("extracted_text", "").encode("utf-8"), filename=f"{fitem['name']}.md")
            sent = await callback.message.answer_document(buf)
        _track_msg_id(u, sent.message_id)
        save_db()
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
                InlineKeyboardButton(text="✅ Таки да, изъять", callback_data=f"fdelyes_{idx}"),
                InlineKeyboardButton(text="❌ Оставить в деле", callback_data="fdelno")
            ]
        ])
        await safe_edit(
            callback.message,
            f"⚠️ Уважаемый, вы уверены, шо документ *{fname}* следует изъять из архива?",
            reply_markup=kb
        )
    await callback.answer()


@dp.callback_query(F.data == "fdelno")
async def delete_dump_file_no_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    await callback.answer("Открываю архив")
    await open_dump_menu(callback.message, u, edit_existing=True)


@dp.callback_query(F.data.startswith("fdelyes_"))
async def delete_dump_file_yes_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    idx = int(callback.data.replace("fdelyes_", ""))
    if 0 <= idx < len(proj["files"]):
        removed = proj["files"].pop(idx)
        proj["active_file"] = max(0, len(proj["files"]) - 1)
        save_db()
        await callback.answer(f"Изъято: {removed['name']}")
    await open_dump_menu(callback.message, u, edit_existing=True)


@dp.callback_query(F.data == "f_clear_ask")
async def clear_project_dump_ask_cb(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, очистить полностью", callback_data="f_clear_yes"),
            InlineKeyboardButton(text="❌ Нет, отмена", callback_data="fdelno")
        ]
    ])
    await safe_edit(
        callback.message,
        "⚠️ *Внимание!* Вы действительно желаете полностью очистить архив текущего проекта?",
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
    await callback.answer("Архив проекта очищен")
    await open_dump_menu(callback.message, u, edit_existing=True)


@dp.callback_query(F.data == "f_add_note")
async def add_text_note_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await state.set_state(HubStates.add_text_note)
    await safe_edit(
        callback.message,
        "📝 Изложите вашу докладную записку, конспект или материал, и я подошью его в архив проекта:",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.add_text_note)
async def add_text_note_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    await state.clear()
    proj = get_active_project(u)
    if message.text:
        txt = message.text.strip()
        title = txt.split("\n")[0][:32].strip("* ") or f"Запись №{len(proj['files'])+1}"
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
    if _roll_interaction_coins(u):
        await _send_bottom_challenge(message, u, start_new_series=True)
        return
    await open_reader_menu(message, u)


async def open_reader_menu(message: types.Message, u: dict, edit_existing: bool = False):
    proj = get_active_project(u)
    if not proj["files"]:
        text = (
            f"📭 В папке проекта *{proj['name']}* пока нет подшитых бумаг.\n"
            f"Направьте сюда любой файл (`.docx`, `.pdf`, `.pptx`, `.md`, `.txt`) или внесите текстовую запись!"
        )
        if edit_existing:
            await safe_edit(message, text)
        else:
            await safe_answer(message, text, u=u)
        return

    f_idx = min(proj.get("active_file", 0), len(proj["files"]) - 1)
    proj["active_file"] = f_idx
    fitem = proj["files"][f_idx]
    pages = fitem.get("pages") or split_into_pages(fitem.get("extracted_text", ""))
    fitem["pages"] = pages

    p_idx = min(proj.get("curr_page", 0), len(pages) - 1)
    proj["curr_page"] = p_idx
    page_text = pages[p_idx]

    text = (
        f"📁 *{proj['name']}* $\\rightarrow$ 📄 *{fitem['name']}*\n"
        f"📑 *Лист {p_idx+1} из {len(pages)}:*\n\n{page_text}"
    )
    kb = get_reader_kb(f_idx, p_idx, len(pages), len(proj["files"]))
    if edit_existing:
        await safe_edit(message, text, reply_markup=kb)
    else:
        await safe_answer(message, text, reply_markup=kb, u=u)


def get_reader_kb(f_idx: int, p_idx: int, total_pages: int, total_files: int):
    nav = []
    if p_idx > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"rnav_{p_idx-1}"))
    nav.append(InlineKeyboardButton(text=f"📄 {p_idx+1}/{total_pages}", callback_data="r_noop"))
    if p_idx < total_pages - 1:
        nav.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"rnav_{p_idx+1}"))

    edit_row = [
        InlineKeyboardButton(text="✏️ Внести правку", callback_data=f"redit_{p_idx}"),
        InlineKeyboardButton(text="📥 Выдать оригинал", callback_data=f"fdl_{f_idx}")
    ]
    file_switch = [
        InlineKeyboardButton(text=f"🗄 Выбрать другой документ ({total_files})", callback_data="r_all_files")
    ]
    return InlineKeyboardMarkup(inline_keyboard=[nav, edit_row, file_switch])


@dp.callback_query(F.data == "r_noop")
async def r_noop_cb(callback: types.CallbackQuery):
    await callback.answer()


@dp.callback_query(F.data == "r_all_files")
async def r_all_files_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    await open_dump_menu(callback.message, u, edit_existing=True)
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
        await open_reader_menu(callback.message, u, edit_existing=True)
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
                f"📑 *Лист {p_idx+1} из {len(pages)}:*\n\n{pages[p_idx]}",
                reply_markup=get_reader_kb(f_idx, p_idx, len(pages), len(proj["files"]))
            )
    await callback.answer()


@dp.callback_query(F.data.startswith("redit_"))
async def reader_edit_page_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    p_idx = int(callback.data.replace("redit_", ""))
    await state.update_data(p_idx=p_idx)
    await state.set_state(HubStates.edit_page_text)
    await safe_edit(
        callback.message,
        f"✏️ Пришлите уточнённый текст для *Листа №{p_idx+1}*:",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.edit_page_text)
async def reader_edit_page_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    data = await state.get_data()
    await state.clear()
    proj = get_active_project(u)
    f_idx = proj.get("active_file", 0)
    p_idx = data.get("p_idx", 0)
    if 0 <= f_idx < len(proj["files"]) and message.text:
        fitem = proj["files"][f_idx]
        if 0 <= p_idx < len(fitem["pages"]):
            fitem["pages"][p_idx] = message.text.strip()
            fitem["extracted_text"] = "\n\n".join(fitem["pages"])
            save_db()
    if _roll_interaction_coins(u):
        await _send_bottom_challenge(message, u, start_new_series=True)
        return
    await open_reader_menu(message, u)


async def open_codes_menu(message: types.Message, u: dict, tab: str = "my", edit_existing: bool = False):
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
        buttons.append([InlineKeyboardButton(text="➕ Внести свой код / шаблон", callback_data="c_new")])
        desc_text = (
            "💻 *ЛИЧНЫЙ СЕЙФ КОДОВ И РЕГЛАМЕНТОВ*\n\n"
            "Здесь хранятся ваши персональные алгоритмы, формулы и заготовки (🔒). "
            "Вы имеете полное право редактировать их или выставлять на Общую витрину (🌐) для коллег."
        )
    else:
        for idx, c in enumerate(db["public_codes"]):
            buttons.append([InlineKeyboardButton(
                text=f"🌐 {c['title']} (от @{c.get('author_name', 'коллеги')})",
                callback_data=f"cpub_{idx}"
            )])
        buttons.append([InlineKeyboardButton(text="➕ Внести свой код", callback_data="c_new")])
        desc_text = (
            "🌐 *ОБЩАЯ ВИТРИНА КОНТОРЫ (ОТКРЫТЫЙ ДОСТУП)*\n\n"
            "Здесь представлены образцы и коды, опубликованные участниками. "
            "Любой образец можно скопировать в свой личный сейф и доработать под собственные нужды!"
        )

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    if edit_existing:
        await safe_edit(message, desc_text, reply_markup=kb)
    else:
        await safe_answer(message, desc_text, reply_markup=kb, u=u)


@dp.callback_query(F.data.startswith("ctab_"))
async def switch_code_tab_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    tab = callback.data.replace("ctab_", "")
    await open_codes_menu(callback.message, u, tab=tab, edit_existing=True)
    await callback.answer()


@dp.callback_query(F.data == "c_new")
async def new_code_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await state.set_state(HubStates.code_title)
    await safe_edit(
        callback.message,
        "💻 Укажите *наименование* нового кода или шаблона:",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.code_title)
async def new_code_title_step(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    await state.update_data(title=message.text.strip())
    await state.set_state(HubStates.code_desc)
    await safe_answer(
        message,
        "📝 Добавьте краткое примечание (или отправьте точку `.`, шоб пропустить):",
        reply_markup=cancel_kb(),
        u=u
    )


@dp.message(HubStates.code_desc)
async def new_code_desc_step(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    desc = "" if message.text.strip() == "." else message.text.strip()
    await state.update_data(desc=desc)
    await state.set_state(HubStates.code_body)
    await safe_answer(
        message,
        "💻 Теперь направьте сам *текст кода или шаблона*:",
        reply_markup=cancel_kb(),
        u=u
    )


@dp.message(HubStates.code_body)
async def new_code_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    data = await state.get_data()
    await state.clear()
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
    if _roll_interaction_coins(u):
        await _send_bottom_challenge(message, u, start_new_series=True)
        return
    await open_codes_menu(message, u, tab="my")


@dp.callback_query(F.data.startswith("cmy_"))
async def view_my_code_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("cmy_", ""))
    if not (0 <= idx < len(u["my_codes"])):
        await callback.answer("Не найдено")
        return

    c = u["my_codes"][idx]
    pub_label = "🔒 Снять с витрины" if c.get("is_public") else "🌐 Выставить на витрину"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Изм. содержание", callback_data=f"ced_{idx}_code"),
            InlineKeyboardButton(text="📝 Изм. примечание", callback_data=f"ced_{idx}_desc"),
            InlineKeyboardButton(text="🏷 Имя", callback_data=f"ced_{idx}_title")
        ],
        [
            InlineKeyboardButton(text=pub_label, callback_data=f"cpubtoggle_{idx}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"cdelask_{idx}")
        ],
        [InlineKeyboardButton(text="⬅️ Назад в сейф", callback_data="ctab_my")]
    ])

    status = "🌐 На общей витрине (открытый доступ)" if c.get("is_public") else "🔒 Личное хранение"
    text = (
        f"📌 *{c['title']}*\n"
        f"Статус: _{status}_\n"
        f"Примечание: _{c.get('desc') or 'не указано'}_\n\n"
        f"```text\n{c.get('code', '')}\n```"
    )
    await safe_edit(callback.message, text, reply_markup=kb)
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
            await callback.answer("🌐 Опубликовано на общей витрине!", show_alert=True)
        else:
            await callback.answer("🔒 Возвращено в личное хранение.", show_alert=True)
        save_db()
        callback.data = f"cmy_{idx}"
        await view_my_code_cb(callback)


@dp.callback_query(F.data.startswith("ced_"))
async def edit_my_code_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    _, idx_str, field = callback.data.split("_")
    await state.update_data(c_idx=int(idx_str), c_field=field)
    await state.set_state(HubStates.code_edit_val)
    labels = {"code": "новое содержание", "desc": "новое примечание", "title": "новое наименование"}
    await safe_edit(
        callback.message,
        f"✏️ Направьте *{labels.get(field, 'новое значение')}*:",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.code_edit_val)
async def edit_my_code_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    data = await state.get_data()
    await state.clear()
    idx = data.get("c_idx", 0)
    field = data.get("c_field", "code")
    if 0 <= idx < len(u["my_codes"]) and message.text:
        c = u["my_codes"][idx]
        c[field] = message.text.strip()
        for pub_c in db["public_codes"]:
            if pub_c.get("id") == c["id"]:
                pub_c[field] = c[field]
        save_db()
    if _roll_interaction_coins(u):
        await _send_bottom_challenge(message, u, start_new_series=True)
        return
    await open_codes_menu(message, u, tab="my")


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
        await safe_edit(callback.message, f"⚠️ Вы уверены, шо образец *{title}* подлежит списанию?", reply_markup=kb)
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
    await open_codes_menu(callback.message, u, tab="my", edit_existing=True)


@dp.callback_query(F.data.startswith("cpub_"))
async def view_public_code_cb(callback: types.CallbackQuery):
    idx = int(callback.data.replace("cpub_", ""))
    if not (0 <= idx < len(db["public_codes"])):
        await callback.answer("Не найдено")
        return

    c = db["public_codes"][idx]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Скопировать экземпляр в «Мои личные»", callback_data=f"cfork_{idx}")],
        [InlineKeyboardButton(text="⬅️ Назад на витрину", callback_data="ctab_pub")]
    ])
    text = (
        f"🌐 *{c['title']}*\n"
        f"Опубликовал: `@{c.get('author_name', 'участник')}`\n"
        f"Примечание: _{c.get('desc') or 'не указано'}_\n\n"
        f"```text\n{c.get('code', '')}\n```"
    )
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("cfork_"))
async def fork_public_code_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("cfork_", ""))
    if 0 <= idx < len(db["public_codes"]):
        orig = db["public_codes"][idx]
        u["my_codes"].append({
            "id": f"code_{uuid.uuid4().hex[:6]}",
            "title": f"{orig['title']} (копия)",
            "desc": orig.get("desc", ""),
            "code": orig.get("code", ""),
            "author_id": u["id"],
            "author_name": u["username"],
            "is_public": False
        })
        save_db()
        await callback.answer("✅ Экземпляр скопирован в ваш личный сейф!", show_alert=True)
        await open_codes_menu(callback.message, u, tab="my", edit_existing=True)


async def send_long_text(message: types.Message, text: str, reply_markup=None, u: dict = None):
    if len(text) <= 3900:
        await safe_answer(message, text, reply_markup=reply_markup, u=u)
    else:
        chunks = [text[i:i + 3800] for i in range(0, len(text), 3800)]
        for idx, ch in enumerate(chunks):
            is_last = idx == len(chunks) - 1
            await safe_answer(
                message,
                ch,
                reply_markup=reply_markup if is_last else None,
                u=u,
                cleanup_prev=(idx == 0)
            )


async def open_ai_chat_mode(message: types.Message, u: dict, state: FSMContext, edit_existing: bool = False):
    proj = get_active_project(u)
    keys = u.get("personal_keys", [])
    await state.set_state(HubStates.ai_chat_mode)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔗 Поделиться этим чатом по ссылке", callback_data="p_share_link"),
            InlineKeyboardButton(text="🧹 Очистить протокол", callback_data="ai_clear_hist")
        ],
        [InlineKeyboardButton(text="❌ Завершить консультацию", callback_data="cancel_state")]
    ])
    text = (
        f"🤖 *КАБИНЕТ КОНСУЛЬТАНТА ИИ (РАБОТА ПО АРХИВУ ДЕЛА)*\n\n"
        f"• *Текущее дело:* `{proj['name']}`\n"
        f"• *Приобщено документов:* *{len(proj['files'])} шт.*\n"
        f"• *Ключей API на дежурстве:* *{len(keys)} шт.*\n\n"
        f"✍️ *Задавайте любой вопрос по вашим материалам, поручайте составить отчёт, анализ или направляйте снимки прямо сюда!* "
        f"Все подшитые к открытому проекту бумаги уже приняты к сведению."
    )
    if edit_existing:
        await safe_edit(message, text, reply_markup=kb)
    else:
        await safe_answer(message, text, reply_markup=kb, u=u)


@dp.callback_query(F.data.startswith("fai_"))
async def ask_ai_about_file_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await callback.answer()
    await open_ai_chat_mode(callback.message, u, state, edit_existing=True)


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
    proj = get_active_project(u)
    user_q = message.text.strip()

    answer_text = await ask_gemini_with_rotation(u, proj, user_q)

    proj.setdefault("ai_history", []).append({"role": "user", "text": user_q})
    proj["ai_history"].append({"role": "model", "text": answer_text})
    save_db()

    if _roll_interaction_coins(u):
        await _send_bottom_challenge(message, u, start_new_series=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💾 Подшить ответ в Архив", callback_data="ai_save_last"),
            InlineKeyboardButton(text="🔗 Поделиться чатом", callback_data="p_share_link")
        ],
        [InlineKeyboardButton(text="❌ Завершить консультацию", callback_data="cancel_state")]
    ])
    await send_long_text(message, answer_text, reply_markup=kb, u=u)


@dp.callback_query(F.data == "ai_save_last", StateFilter("*"))
async def save_last_ai_to_dump_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    if proj.get("ai_history"):
        last_ans = proj["ai_history"][-1]["text"]
        title = f"Заключение ИИ ({datetime.now().strftime('%H:%M')})"
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
        await callback.answer("✅ Заключение подшито в Архив проекта!", show_alert=True)
    else:
        await callback.answer("Заключений пока нет")


async def open_keys_menu(message: types.Message, u: dict, edit_existing: bool = False):
    p_keys = u.get("personal_keys", [])

    buttons = []
    for idx, kobj in enumerate(p_keys):
        raw_k = kobj["key"]
        masked = f"{raw_k[:6]}..{raw_k[-4:]}" if len(raw_k) > 12 else raw_k
        kname = kobj.get("name", f"Ключ №{idx+1}")
        buttons.append([
            InlineKeyboardButton(text=f"🔑 {kname} ({masked})", callback_data=f"kcard_{idx}"),
            InlineKeyboardButton(text="✏️ Имя", callback_data=f"kren_{idx}"),
            InlineKeyboardButton(text="🗑", callback_data=f"kdelask_{idx}")
        ])

    buttons.append([InlineKeyboardButton(text="➕ Внести новый ключ API", callback_data="kadd_p")])
    if p_keys:
        buttons.append([InlineKeyboardButton(text="🧹 Удалить все ключи (с проверкой)", callback_data="kclear_ask")])

    text = (
        f"🔑 *РЕЕСТР ВАШИХ ЛИЧНЫХ КЛЮЧЕЙ API*\n\n"
        f"• *Ключей в распоряжении:* *{len(p_keys)} шт.*\n\n"
        f"💡 _Все ключи закреплены строго за вашим профилем. Нажмите `✏️ Имя`, шоб присвоить ключу удобное наименование, или на сам ключ для просмотра карточки:_"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    if edit_existing:
        await safe_edit(message, text, reply_markup=kb)
    else:
        await safe_answer(message, text, reply_markup=kb, u=u)


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
            InlineKeyboardButton(text="✏️ Изменить наименование", callback_data=f"kren_{idx}"),
            InlineKeyboardButton(text="🗑 Изъять ключ", callback_data=f"kdelask_{idx}")
        ],
        [InlineKeyboardButton(text="⬅️ Назад к реестру ключей", callback_data="k_back")]
    ])
    await safe_edit(
        callback.message,
        f"🔑 *Учётная карточка ключа №{idx+1}*\n\n"
        f"🏷 *Наименование:* `{kobj.get('name', '')}`\n"
        f"🔐 *Шифр ключа:* `{masked}`",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data == "k_back")
async def key_back_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    await open_keys_menu(callback.message, u, edit_existing=True)
    await callback.answer()


@dp.callback_query(F.data == "kadd_p")
async def add_key_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await state.set_state(HubStates.add_api_key_name)
    await safe_edit(
        callback.message,
        "🏷 *Шаг 1 из 2:* Какое наименование присвоим ключу? (Например: _«Резервный канал №1»_ или отправьте точку `.`, шоб присвоить номер автоматически):",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.add_api_key_name)
async def add_key_name_step(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    custom_name = "" if message.text.strip() == "." else message.text.strip()
    await state.update_data(kname=custom_name)
    await state.set_state(HubStates.add_api_key_val)
    await safe_answer(
        message,
        "🔑 *Шаг 2 из 2:* Теперь направьте сам ключ API (или сразу несколько ключей, каждый с новой строки, принимается любой формат `AQ.Ab8...`, `AIza...` и прочие):",
        reply_markup=cancel_kb(),
        u=u
    )


@dp.message(HubStates.add_api_key_val)
async def add_key_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    data = await state.get_data()
    await state.clear()
    base_name = data.get("kname", "")

    raw_lines = [line.strip() for line in (message.text or "").splitlines() if len(line.strip()) >= 10]
    if not raw_lines:
        await safe_answer(
            message,
            "⚠️ Уважаемый, представленная строка слишком коротка для ключа API!",
            u=u
        )
        return

    target_list = u.setdefault("personal_keys", [])
    existing_raw = {x["key"] for x in target_list}
    for idx, k_str in enumerate(raw_lines, 1):
        if k_str not in existing_raw:
            num = len(target_list) + 1
            if base_name:
                final_name = f"{base_name} №{idx}" if len(raw_lines) > 1 else base_name
            else:
                final_name = f"Ключ №{num}"
            target_list.append({
                "id": f"k_{uuid.uuid4().hex[:6]}",
                "name": final_name,
                "key": k_str
            })
    save_db()
    if _roll_interaction_coins(u):
        await _send_bottom_challenge(message, u, start_new_series=True)
        return
    await open_keys_menu(message, u)


@dp.callback_query(F.data.startswith("kren_"))
async def rename_key_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    idx = int(callback.data.replace("kren_", ""))
    p_keys = u.get("personal_keys", [])
    if 0 <= idx < len(p_keys):
        await state.update_data(k_idx=idx)
        await state.set_state(HubStates.rename_api_key)
        curr_name = p_keys[idx].get("name", f"Ключ №{idx+1}")
        await safe_edit(
            callback.message,
            f"✏️ Текущее наименование ключа: `{curr_name}`\nУкажите новое наименование:",
            reply_markup=cancel_kb()
        )
    await callback.answer()


@dp.message(HubStates.rename_api_key)
async def rename_key_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    data = await state.get_data()
    await state.clear()
    idx = data.get("k_idx", 0)
    p_keys = u.get("personal_keys", [])
    if 0 <= idx < len(p_keys) and message.text:
        p_keys[idx]["name"] = message.text.strip()
        save_db()
    if _roll_interaction_coins(u):
        await _send_bottom_challenge(message, u, start_new_series=True)
        return
    await open_keys_menu(message, u)


@dp.callback_query(F.data.startswith("kdelask_"))
async def del_key_ask_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("kdelask_", ""))
    p_keys = u.get("personal_keys", [])
    if 0 <= idx < len(p_keys):
        kname = p_keys[idx].get("name", f"Ключ №{idx+1}")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Таки да, изъять", callback_data=f"kdelyes_{idx}"),
                InlineKeyboardButton(text="❌ Нет, оставить", callback_data="k_back")
            ]
        ])
        await safe_edit(
            callback.message,
            f"⚠️ *Подтвердите распоряжение:*\nВы уверены, шо ключ *{kname}* следует изъять из реестра?",
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
        await callback.answer(f"Ключ «{removed.get('name')}» изъят")
    await open_keys_menu(callback.message, u, edit_existing=True)


@dp.callback_query(F.data == "kclear_ask")
async def clear_all_keys_ask_cb(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, изъять все ключи", callback_data="kclear_yes"),
            InlineKeyboardButton(text="❌ Нет, оставить", callback_data="k_back")
        ]
    ])
    await safe_edit(
        callback.message,
        "⚠️ *Минуточку!* Вы действительно желаете полностью очистить весь реестр ваших ключей API?",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data == "kclear_yes")
async def clear_all_keys_yes_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    u["personal_keys"] = []
    u["key_cursor"] = 0
    save_db()
    await callback.answer("Реестр ключей очищен")
    await open_keys_menu(callback.message, u, edit_existing=True)


@dp.message(HubStates.search_query)
async def search_query_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    await state.clear()
    q = (message.text or "").strip().lower()
    if not q:
        return

    if _roll_interaction_coins(u):
        await _send_bottom_challenge(message, u, start_new_series=True)
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
        await safe_answer(message, f"📭 По вашему запросу `{q}` в делах конторы совпадений не обнаружено.", u=u)
    else:
        await safe_answer(
            message,
            f"🔍 *Результаты сыска по архивам ({len(found)}):*\n\n" + "\n\n===\n\n".join(found[:10]),
            u=u
        )


UI_LABELS = {
    "welcome_title": "Заголовок кабинета (/start)",
    "welcome_desc": "Описание под заголовком",
    "btn_projects": "Кнопка 1 (Проекты)",
    "btn_dump": "Кнопка 2 (Архив файлов)",
    "btn_reader": "Кнопка 3 (Читальный зал)",
    "btn_codes": "Кнопка 4 (Сундук кодов)",
    "btn_ai": "Кнопка 5 (Беседа с ИИ)",
    "btn_keys": "Кнопка 6 (Ключи API)",
    "btn_search": "Кнопка 7 (Сыск)",
    "btn_settings": "Кнопка 8 (Настройки)"
}


async def open_settings_menu(message: types.Message, u: dict, edit_existing: bool = False):
    ui = u["ui"]
    buttons = []
    for k, label in UI_LABELS.items():
        curr_val = ui.get(k, "")[:22]
        buttons.append([InlineKeyboardButton(text=f"✏️ {label}: «{curr_val}»", callback_data=f"uied_{k}")])

    buttons.append([InlineKeyboardButton(text="🔄 Восстановить уставные вывески конторы", callback_data="ui_reset")])

    text = (
        "⚙️ *УПРАВЛЕНИЕ ВЫВЕСКАМИ И КНОПКАМИ КАБИНЕТА*\n\n"
        "Желаете переименовать разделы на свой вкус? Выбирайте нужный пункт ниже:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    if edit_existing:
        await safe_edit(message, text, reply_markup=kb)
    else:
        await safe_answer(message, text, reply_markup=kb, u=u)


@dp.callback_query(F.data.startswith("uied_"))
async def edit_ui_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    ui_key = callback.data.replace("uied_", "")
    if ui_key in UI_LABELS:
        await state.update_data(ui_key=ui_key)
        await state.set_state(HubStates.edit_ui_val)
        await safe_edit(
            callback.message,
            f"✏️ Текущая надпись ({UI_LABELS[ui_key]}):\n`{u['ui'].get(ui_key, '')}`\n\nУкажите новый вариант:",
            reply_markup=cancel_kb()
        )
    await callback.answer()


@dp.message(HubStates.edit_ui_val)
async def edit_ui_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    data = await state.get_data()
    await state.clear()
    ui_key = data.get("ui_key")
    if ui_key and message.text:
        u["ui"][ui_key] = message.text.strip()
        save_db()
    if _roll_interaction_coins(u):
        await _send_bottom_challenge(message, u, start_new_series=True)
        return
    await safe_answer(
        message,
        "✅ Новая вывеска утверждена!",
        u=u,
        refresh_anchor=True
    )


@dp.callback_query(F.data == "ui_reset")
async def reset_ui_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    u["ui"] = dict(DEFAULT_UI)
    save_db()
    await callback.answer("Уставные вывески возвращены")
    await safe_answer(
        callback.message,
        "🔄 Стандартные вывески конторы восстановлены!",
        u=u,
        refresh_anchor=True
    )


@dp.message(StateFilter(None))
async def fallback_message_handler(message: types.Message):
    if not message.from_user:
        return
    u = get_user(message.from_user)
    if _roll_interaction_coins(u):
        await _send_bottom_challenge(message, u, start_new_series=True)
        return
    await safe_answer(
        message,
        "Уважаемый, выбирайте нужный отдел кнопками внизу или направляйте документ прямо в чат для приобщения к делу!",
        u=u
    )


async def main():
    global bot, BOT_USERNAME
    token = get_host_token()
    session_client = AiohttpSession(timeout=20)
    session_client._connector_init["family"] = socket.AF_INET

    bot = Bot(token=token, session=session_client)
    rem_task = asyncio.create_task(_reminders_daemon())
    try:
        me = await bot.get_me()
        BOT_USERNAME = me.username
        print(f"Ready: @{me.username} | {STAT_FILE}")
        await dp.start_polling(bot)
    finally:
        rem_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
