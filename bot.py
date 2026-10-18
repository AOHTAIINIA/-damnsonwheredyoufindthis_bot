import asyncio
import json
import os
import re
import socket
from datetime import datetime
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

# =====================================================================
# ⚙️ 1. НАСТРОЙКИ ТОКЕНА И ПОДКЛЮЧЕНИЯ (BOTHOST + ЛОКАЛЬНЫЙ ПРОКСИ)
# =====================================================================
# На Bothost.ru токен подхватится сам из поля Bot Token / Переменных окружения.
# Для запуска на домашнем ПК можно вписать токен во вторые кавычки:
BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TOKEN") or "8669029978:AAGFh4c1zsXDa4Hw8RI-N-5n8Ve3a_tPJDY"

# Сначала пробуем прямое подключение (для сервера в Нидерландах на Bothost),
# а если не вышло — проверяем локальный порт 1337 (для домашнего ПК)
PROXY_CANDIDATES = [
    None,
    "socks5://127.0.0.1:1337",
    "http://127.0.0.1:1337",
]

dp = Dispatcher()
bot: Bot = None

DB_FILE = "vault_db.json"

# =====================================================================
# 💻 2. ВСТРОЕННАЯ БАЗА СКРИПТИНГА (LATCH + LUAU)
# =====================================================================
SCRIPTS_VAULT = {
    "claim": {
        "title": "🟢 Урок 1: Захват базы (ClaimPad)",
        "desc": "Защищённый скрипт захвата участка. Игнорирует пол и спавн (проверяет Humanoid), записывает владельца и прячет кнопку.",
        "latch": (
            "🧩 *СБОРКА В LATCH (на детали Кнопки захвата):*\n"
            "1. *Variables (в самом верху холста):* `make [ owner ] type [ auto ] = [ nil ]`\n"
            "2. *Events:* `when [ part ] is touched by [ hit ]`\n"
            "3. *Variables + Instances:* `make [ human ] = in [ hit.Parent ] find [ \"Humanoid\" ]`\n"
            "4. *Control:* `if [ human ] ~= [ nil ] then` _(ОБЯЗАТЕЛЬНО синий овал human без кавычек!)_\n"
            "5. *Control (внутри первого if):* `if [ owner ] == [ nil ] then`\n"
            "6. *Variables:* `set [ owner ] to [ hit.Parent.Name ]`\n"
            "7. *Instances:* `set [ Столб.BillboardGui.TextLabel ] . [ Text ] to [ \"БАЗА: \" join owner ]`\n"
            "8. *Instances:* `set [ Кнопка ] . [ Transparency ] to [ 1 ]` и `CanCollide = false`"
        ),
        "luau": (
            "--!strict\n"
            "local owner = nil\n\n"
            "script.Parent.Touched:Connect(function(hit)\n"
            "\tlocal human = hit.Parent:FindFirstChild(\"Humanoid\")\n"
            "\tif human ~= nil then\n"
            "\t\tif owner == nil then\n"
            "\t\t\towner = hit.Parent.Name\n"
            "\t\t\tworkspace:WaitForChild(\"Столб\"):WaitForChild(\"BillboardGui\"):WaitForChild(\"TextLabel\").Text = \"БАЗА: \" .. tostring(owner)\n"
            "\t\t\tscript.Parent.Transparency = 1\n"
            "\t\t\tscript.Parent.CanCollide = false\n"
            "\t\tend\n"
            "\tend\n"
            "end)"
        )
    },
    "dropper": {
        "title": "💎 Урок 2: Дроппер руды (DropPoint)",
        "desc": "Бесконечный цикл спавна руды каждые 2 секунды из ServerStorage с автоудалением через 15 секунд.",
        "latch": (
            "🧩 *СБОРКА В LATCH (на невидимой детали DropPoint в трубе):*\n"
            "• В `ServerStorage` лежит деталь `OrePart` (`Anchored = false`, `CanCollide = true`).\n"
            "1. *Events:* `when run`\n"
            "2. *Control:* `while [ true ] do`\n"
            "3. *Control:* `wait [ 2 ] seconds`\n"
            "4. *Variables + Instances:* `make [ newOre ] = a copy of [ ServerStorage.OrePart ]`\n"
            "5. *Instances:* `set [ newOre ] . [ Position ] to [ Workspace.DropPoint.Position ]`\n"
            "6. *Instances:* `set [ newOre ] . [ Parent ] to [ game.Workspace ]`\n"
            "7. *Control:* `after [ 15 ] seconds` -> `destroy [ newOre ]`"
        ),
        "luau": (
            "--!strict\n"
            "local ServerStorage = game:GetService(\"ServerStorage\")\n\n"
            "while true do\n"
            "\ttask.wait(2)\n"
            "\tlocal newOre = ServerStorage:WaitForChild(\"OrePart\"):Clone()\n"
            "\tnewOre.Position = script.Parent.Position\n"
            "\tnewOre.Parent = workspace\n"
            "\ttask.delay(15, function()\n"
            "\t\tif newOre and newOre.Parent then\n"
            "\t\t\tnewOre:Destroy()\n"
            "\t\tend\n"
            "\tend)\n"
            "end"
        )
    },
    "receiver": {
        "title": "🔥 Урок 2: Приёмник руды (Receiver)",
        "desc": "Уничтожает доехавшую по конвейеру руду и начисляет +5$ в буфер станка (БанкДеньги).",
        "latch": (
            "🧩 *СБОРКА В LATCH (на красной детали Приёмника в конце конвейера):*\n"
            "• В `Workspace` создан `IntValue` с именем `БанкДеньги`.\n"
            "1. *Events:* `when [ part ] is touched by [ hit ]`\n"
            "2. *Control:* `if [ hit.Name ] == [ \"OrePart\" ] then`\n"
            "3. *Instances:* `destroy [ hit ]`\n"
            "4. *Instances:* `set [ Workspace.БанкДеньги ] . [ Value ] to [ Workspace.БанкДеньги.Value + 5 ]`"
        ),
        "luau": (
            "--!strict\n"
            "script.Parent.Touched:Connect(function(hit)\n"
            "\tif hit.Name == \"OrePart\" then\n"
            "\t\thit:Destroy()\n"
            "\t\tlocal bank = workspace:WaitForChild(\"БанкДеньги\")\n"
            "\t\tbank.Value = bank.Value + 5\n"
            "\tend\n"
            "end)"
        )
    },
    "collect_btn": {
        "title": "🏧 Урок 2: Кнопка сбора денег (СобратьДеньги)",
        "desc": "Когда игрок встаёт ногами на кнопку, деньги из станка (БанкДеньги) переходят на баланс игрока (ИгрокДеньги) и обновляют табло.",
        "latch": (
            "🧩 *СБОРКА В LATCH (на зелёной кнопке СобратьДеньги):*\n"
            "• В `Workspace` есть два `IntValue`: `БанкДеньги` и `ИгрокДеньги`.\n"
            "1. *Events:* `when [ part ] is touched by [ hit ]`\n"
            "2. *Variables + Instances:* `make [ human ] = in [ hit.Parent ] find [ \"Humanoid\" ]`\n"
            "3. *Control:* `if [ human ] ~= [ nil ] then` _(синий овал human без кавычек!)_\n"
            "4. *Instances:* `set [ Workspace.ИгрокДеньги ] . [ Value ] to [ Workspace.ИгрокДеньги.Value + Workspace.БанкДеньги.Value ]`\n"
            "5. *Instances:* `set [ Workspace.БанкДеньги ] . [ Value ] to [ 0 ]`\n"
            "6. *Instances:* `set [ СобратьДеньги.BillboardGui.TextLabel ] . [ Text ] to [ \"Ваш Баланс: $\" join Workspace.ИгрокДеньги.Value ]`"
        ),
        "luau": (
            "--!strict\n"
            "script.Parent.Touched:Connect(function(hit)\n"
            "\tlocal human = hit.Parent:FindFirstChild(\"Humanoid\")\n"
            "\tif human ~= nil then\n"
            "\t\tlocal playerMoney = workspace:WaitForChild(\"ИгрокДеньги\")\n"
            "\t\tlocal bankMoney = workspace:WaitForChild(\"БанкДеньги\")\n"
            "\t\tlocal label = workspace:WaitForChild(\"СобратьДеньги\"):WaitForChild(\"BillboardGui\"):WaitForChild(\"TextLabel\")\n\n"
            "\t\tplayerMoney.Value = playerMoney.Value + bankMoney.Value\n"
            "\t\tbankMoney.Value = 0\n"
            "\t\tlabel.Text = \"Ваш Баланс: $\" .. tostring(playerMoney.Value)\n"
            "\tend\n"
            "end)"
        )
    },
    "upgrader": {
        "title": "⚡ Урок 3: Лазерный Апгрейдер (Upgrader)",
        "desc": "Арка над конвейером: красит проезжающую руду в изумрудный цвет и мгновенно накидывает +10$ бонусом.",
        "latch": (
            "🧩 *СБОРКА В LATCH (на полупрозрачном экране лазера с CanCollide = false):*\n"
            "1. *Events:* `when [ part ] is touched by [ hit ]`\n"
            "2. *Control:* `if [ hit.Name ] == [ \"OrePart\" ] then`\n"
            "3. *Instances:* `set [ hit ] . [ Color ] to [ colour r:0 g:255 b:100 ]`\n"
            "4. *Instances:* `set [ Workspace.БанкДеньги ] . [ Value ] to [ Workspace.БанкДеньги.Value + 10 ]`"
        ),
        "luau": (
            "--!strict\n"
            "script.Parent.Touched:Connect(function(hit)\n"
            "\tif hit.Name == \"OrePart\" then\n"
            "\t\thit.Color = Color3.fromRGB(0, 255, 100)\n"
            "\t\tlocal bank = workspace:WaitForChild(\"БанкДеньги\")\n"
            "\t\tbank.Value = bank.Value + 10\n"
            "\tend\n"
            "end)"
        )
    },
    "buypad": {
        "title": "🧱 Урок 4: Кнопка покупки стен/апгрейдов (BuyPad)",
        "desc": "Проверяет, хватает ли игроку денег (50$), списывает сумму, проявляет купленную стену и прячет кнопку.",
        "latch": (
            "🧩 *СБОРКА В LATCH (на кнопке покупки):*\n"
            "1. *Variables (вверху):* `make [ bought ] = [ false ]`\n"
            "2. *Events:* `when [ part ] is touched by [ hit ]`\n"
            "3. *Variables:* `make [ human ] = in [ hit.Parent ] find [ \"Humanoid\" ]`\n"
            "4. *Control:* `if [ human ~= nil ] and [ bought == false ] then`\n"
            "5. *Control:* `if [ Workspace.ИгрокДеньги.Value ] >= [ 50 ] then`\n"
            "6. *Variables:* `set [ bought ] to [ true ]`\n"
            "7. *Instances:* списываем `-50` из `ИгрокДеньги.Value`, ставим купленному объекту `Transparency = 0` и `CanCollide = true`, а кнопке `Transparency = 1`."
        ),
        "luau": (
            "--!strict\n"
            "local bought = false\n"
            "local COST = 50\n\n"
            "script.Parent.Touched:Connect(function(hit)\n"
            "\tlocal human = hit.Parent:FindFirstChild(\"Humanoid\")\n"
            "\tif human ~= nil and bought == false then\n"
            "\t\tlocal playerMoney = workspace:WaitForChild(\"ИгрокДеньги\")\n"
            "\t\tif playerMoney.Value >= COST then\n"
            "\t\t\tbought = true\n"
            "\t\t\tplayerMoney.Value = playerMoney.Value - COST\n\n"
            "\t\t\tlocal item = workspace:WaitForChild(\"Стена1\")\n"
            "\t\t\titem.Transparency = 0\n"
            "\t\t\titem.CanCollide = true\n\n"
            "\t\t\tscript.Parent.Transparency = 1\n"
            "\t\t\tscript.Parent.CanCollide = false\n"
            "\t\tend\n"
            "\tend\n"
            "end)"
        )
    },
    "ownerdoor": {
        "title": "🛡 Урок 5: Лазерная дверь владельца (OwnerDoor)",
        "desc": "Пропускает хозяина базы сквозь поле и обнуляет здоровье чужакам.",
        "latch": (
            "🧩 *СБОРКА В LATCH (на лазерном барьере ворот):*\n"
            "• В `Workspace` есть `StringValue` с именем `OwnerName`.\n"
            "1. *Events:* `when [ part ] is touched by [ hit ]`\n"
            "2. *Variables:* `make [ human ] = in [ hit.Parent ] find [ \"Humanoid\" ]`\n"
            "3. *Control:* `if [ human ] ~= [ nil ] then`\n"
            "4. *Control:* `if [ hit.Parent.Name ] == [ Workspace.OwnerName.Value ] then` -> открыть на 1 сек (`CanCollide = false`, `wait 1`, `CanCollide = true`).\n"
            "5. *Иначе (чужак):* `set [ human ] . [ Health ] to [ 0 ]`."
        ),
        "luau": (
            "--!strict\n"
            "local door = script.Parent\n\n"
            "door.Touched:Connect(function(hit)\n"
            "\tlocal human = hit.Parent:FindFirstChild(\"Humanoid\")\n"
            "\tif human ~= nil then\n"
            "\t\tlocal ownerName = workspace:WaitForChild(\"OwnerName\").Value\n"
            "\t\tif hit.Parent.Name == ownerName then\n"
            "\t\t\tdoor.CanCollide = false\n"
            "\t\t\tdoor.Transparency = 0.8\n"
            "\t\t\ttask.wait(1)\n"
            "\t\t\tdoor.CanCollide = true\n"
            "\t\t\tdoor.Transparency = 0.4\n"
            "\t\telse\n"
            "\t\t\thuman.Health = 0\n"
            "\t\tend\n"
            "\tend\n"
            "end)"
        )
    }
}

# =====================================================================
# 🧠 3. ВШИТЫЕ УМНЫЕ ПРОМПТЫ (СТАНДАРТ 61 ФАЙЛА + МЕТОДИКА)
# =====================================================================
SYSTEM_PROMPTS = {
    "method": (
        "Ты — главный методист курса геймдизайна в Roblox Studio для детей 8–14 лет (36 уроков, визуальное программирование Latch).\n"
        "Напиши ПОЛНОЕ МЕТОДИЧЕСКОЕ РУКОВОДСТВО (90 минут), строго включая:\n"
        "1. Правило Latch: скрипт НЕ создается вручную! Выделить деталь -> вкладка Plugins -> нажать Latch -> собрать блоки -> нажать 'Save to script'.\n"
        "2. Повторение прошлого урока (5 мин) и деконструкцию геймдизайна.\n"
        "3. Пошаговую 3D-сборку в Studio и точную схему блоков Latch (без кавычек вокруг переменных!).\n"
        "4. Настройку BillboardGui: AlwaysOnTop = false, LightInfluence = 0, StudsOffsetWorldSpace, TextScaled = true.\n"
        "5. Разминку (5 мин) в середине урока вдали от ПК для восстановления концентрации.\n"
        "6. Проверку ошибок: точный регистр букв в именах папок и элементов (WaitForChild), свойство Anchored = true, CollisionFidelity = Default.\n"
        "7. Завершение урока (5 мин): вопросы рефлексии («Что нового вы сегодня узнали?», «Что было легко/сложно?»), подсчёт баллов в таблицу «Банк робаксов» (и «Магазин робаксов», пароли 1235453 / 1235351), сохранение файла .rbxl на ПК (File -> Save to File As) и Google Диск, анонс следующего урока."
    ),
    "pres": (
        "Ты — арт-директор детского курса по Roblox Studio (8–14 лет).\n"
        "Создай ПЛАН ПРЕЗЕНТАЦИИ НА 10 СЛАЙДОВ (Dark Mode #121214, неоновые акценты).\n"
        "Для каждого слайда распиши: Надзаголовок, Заголовок, Карточки шагов (конкретные блоки Latch и свойства Properties), Визуал, Реплику спикера и Интерактив.\n"
        "В конце обязательно слайды: сетевой тест (2 Players), рефлексия, «Банк робаксов», сохранение файла .rbxl на ПК и анонс."
    ),
    "raw_lesson": (
        "Ты — технический разработчик курса Roblox Studio (плагин Latch - visual Luau).\n"
        "Напиши ПОЛНЫЙ ПРАКТИЧЕСКИЙ РАЗБОР УРОКА без методической воды и таймингов (максимально подробно):\n"
        "1. Какие объекты (IntValue, StringValue, Part, BillboardGui) создать в Explorer.\n"
        "2. Пошаговая 3D-постройка и свойства в Properties (Anchored, CanCollide, AssemblyLinearVelocity).\n"
        "3. Точная сборка блоков в Latch по категориям (Events, Control, Logic, Math, Variables, Tables, Instances).\n"
        "4. Готовый проверочный код Luau (--!strict) и разбор частых багов."
    )
}

# =====================================================================
# 🗄 4. БАЗА ДАННЫХ, ПАРСЕРЫ MD/JSON И БЕЗОПАСНАЯ ОТПРАВКА
# =====================================================================
def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


db = load_db()


def get_user(uid: str):
    if uid not in db:
        db[uid] = {
            "history": [],
            "paragraphs": [],
            "curr_p": 0,
            "screenshots": []
        }
        save_db(db)
    if "screenshots" not in db[uid]:
        db[uid]["screenshots"] = []
    return db[uid]


async def safe_answer(message: types.Message, text: str, reply_markup=None):
    """Безопасная отправка: если в тексте сломана разметка Markdown, отправляет обычным текстом без ошибки."""
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
        if len(buffer) + len(b) < 650:
            buffer = f"{buffer}\n\n{b}".strip() if buffer else b
        else:
            if buffer:
                merged.append(buffer)
            buffer = b
    if buffer:
        merged.append(buffer)
    return merged if merged else [text]


def parse_md_content(raw_text: str) -> list:
    """Парсит как экспорт чата Gemini (chat.md с Turn / Пользователь / Ассистент), так и обычные .md файлы."""
    extracted = []
    if "### 👤 Пользователь" in raw_text or "### 🤖 Ассистент" in raw_text:
        turns = re.split(r"## Turn \d+", raw_text)
        for turn in turns:
            if not turn.strip():
                continue
            parts = re.split(r"### (👤 Пользователь|🤖 Ассистент)", turn)
            # parts: [header, role1, text1, role2, text2...]
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
    """Поддерживает формат gemini-voyager (items), AI Studio (chunkedPrompt) и стандартный список."""
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


def build_markdown_export(history: list) -> str:
    """Собирает всю историю в красивый .md файл в формате Gemini Chat."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# Экспорт курса по геймдизайну в Roblox (ИИ-Комбайн)",
        f"**Date**: {now_str}",
        f"**Total blocks**: {len(history)}\n",
        "---\n"
    ]
    turn_num = 1
    for item in history:
        role_title = "### 👤 Пользователь" if item.get("role") == "user" else "### 🤖 Ассистент"
        lines.append(f"## Блок {turn_num}\n\n{role_title}\n\n{item.get('text', '')}\n")
        turn_num += 1
    return "\n".join(lines)


class BotStates(StatesGroup):
    add_user = State()
    add_ai = State()
    split_text = State()
    edit_paragraph = State()
    prompt_task = State()
    edit_screen_note = State()


# =====================================================================
# 🎛 5. ГЛАВНОЕ МЕНЮ КНОПОК
# =====================================================================
def main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💻 Скриптинг (Latch + Luau)"), KeyboardButton(text="📑 Разбор по абзацам")],
            [KeyboardButton(text="👤 + Моё сообщение"), KeyboardButton(text="🤖 + Ответ нейросети")],
            [KeyboardButton(text="📘 Промпт: Методичка"), KeyboardButton(text="🖥 Промпт: Презентация")],
            [KeyboardButton(text="🧩 Промпт: Практика"), KeyboardButton(text="📸 Скриншоты и баги")],
            [KeyboardButton(text="🗂 Плашки диалога"), KeyboardButton(text="📥 Выгрузить (MD / JSON)")],
            [KeyboardButton(text="🗑 Очистить сессию")]
        ],
        resize_keyboard=True
    )


# =====================================================================
# 🚀 6. ОБРАБОТЧИКИ КОМАНД И МЕНЮ
# =====================================================================
@dp.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    u = get_user(str(message.from_user.id))
    await safe_answer(
        message,
        f"⚡ *ИИ-Комбайн 3.0 (Геймдев-Мультитул) запущен!*\n\n"
        f"• *Импорт файлов:* просто перешли или прикрепи сюда любой файл `.md`, `.json` или `.txt` — бот сам разберёт весь чат на плашки и абзацы!\n"
        f"• *Скриншоты:* отправь сюда любой скриншот из Roblox Studio / Latch — я сохраню его и сделаю промпт на разбор бага.\n"
        f"• *Скриптинг:* готовые схемы Latch и проверочный код Luau по кнопке снизу.\n\n"
        f"📊 Плашек в памяти: *{len(u['history'])}* | Абзацев: *{len(u['paragraphs'])}* | Скринов: *{len(u['screenshots'])}*",
        reply_markup=main_kb()
    )


@dp.message(F.text == "💻 Скриптинг (Latch + Luau)")
async def scripting_menu(message: types.Message):
    buttons = []
    for key, val in SCRIPTS_VAULT.items():
        buttons.append([InlineKeyboardButton(text=val["title"], callback_data=f"scr_{key}")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await safe_answer(
        message,
        "💻 *Встроенное хранилище скриптов Тайкуна (Latch + Luau):*\n"
        "Выбери нужный механизм — я мгновенно пришлю схему блоков и чистый код:",
        reply_markup=kb
    )


@dp.callback_query(F.data.startswith("scr_"))
async def send_script_card(callback: types.CallbackQuery):
    key = callback.data.replace("scr_", "")
    item = SCRIPTS_VAULT.get(key)
    if not item:
        await callback.answer("Не найдено")
        return

    text = (
        f"📌 *{item['title']}*\n"
        f"_{item['desc']}_\n\n"
        f"{item['latch']}\n\n"
        f"💻 *Готовый код Luau (нажми, чтобы скопировать):*\n"
        f"```luau\n{item['luau']}\n```"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить этот скрипт в контекст", callback_data=f"addscr_{key}")]
    ])
    await safe_answer(callback.message, text, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("addscr_"))
async def add_script_to_context(callback: types.CallbackQuery):
    key = callback.data.replace("addscr_", "")
    item = SCRIPTS_VAULT.get(key)
    if item:
        u = get_user(str(callback.from_user.id))
        u["history"].append({
            "role": "model",
            "text": f"{item['title']}\n{item['latch']}\n\nКод Luau:\n{item['luau']}"
        })
        save_db(db)
        await callback.answer("✅ Скрипт добавлен в твой активный контекст!", show_alert=True)


# =====================================================================
# 📑 7. НАВИГАТОР И РЕДАКТОР ПО АБЗАЦАМ
# =====================================================================
def get_paragraph_kb(idx: int, total: int):
    nav = []
    if idx > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Пред.", callback_data=f"pnav_{idx-1}"))
    nav.append(InlineKeyboardButton(text=f"📄 {idx+1}/{total}", callback_data="p_noop"))
    if idx < total - 1:
        nav.append(InlineKeyboardButton(text="След. ➡️", callback_data=f"pnav_{idx+1}"))

    actions = [
        InlineKeyboardButton(text="✏️ Править абзац", callback_data=f"pedit_{idx}"),
        InlineKeyboardButton(text="❌ Удалить", callback_data=f"pdel_{idx}")
    ]
    extra = [
        InlineKeyboardButton(text="➕ Загрузить новый текст", callback_data="pnew"),
        InlineKeyboardButton(text="📥 Собрать абзацы в .MD", callback_data="pmerge")
    ]
    return InlineKeyboardMarkup(inline_keyboard=[nav, actions, extra])


@dp.message(F.text == "📑 Разбор по абзацам")
async def show_paragraphs(message: types.Message, state: FSMContext):
    u = get_user(str(message.from_user.id))
    if not u["paragraphs"] and u["history"]:
        u["paragraphs"] = split_into_paragraphs(u["history"][-1]["text"])
        u["curr_p"] = 0
        save_db(db)

    if not u["paragraphs"]:
        await state.set_state(BotStates.split_text)
        await safe_answer(
            message,
            "📑 *Отправь мне любой большой текст, урок или прикрепи файл (.md / .json)* — я автоматически разберу его по абзацам, чтобы ты мог удобно листать, копировать или редактировать каждый шаг!"
        )
        return

    idx = min(u.get("curr_p", 0), len(u["paragraphs"]) - 1)
    u["curr_p"] = idx
    p_text = u["paragraphs"][idx]
    await safe_answer(
        message,
        f"📑 *Абзац #{idx+1} из {len(u['paragraphs'])}:*\n\n{p_text}\n\n"
        f"📋 _Быстрое копирование:_\n```text\n{p_text}\n```",
        reply_markup=get_paragraph_kb(idx, len(u["paragraphs"]))
    )


@dp.message(BotStates.split_text)
async def process_new_split_text(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer("Отправь текстовое сообщение или выйди в меню через /start.")
        return
    u = get_user(str(message.from_user.id))
    u["paragraphs"] = split_into_paragraphs(message.text)
    u["curr_p"] = 0
    u["history"].append({"role": "model", "text": message.text})
    save_db(db)
    await state.clear()
    await show_paragraphs(message, state)


@dp.callback_query(F.data == "p_noop")
async def noop_cb(callback: types.CallbackQuery):
    await callback.answer()


@dp.callback_query(F.data.startswith("pnav_"))
async def navigate_paragraphs(callback: types.CallbackQuery):
    idx = int(callback.data.replace("pnav_", ""))
    u = get_user(str(callback.from_user.id))
    if 0 <= idx < len(u["paragraphs"]):
        u["curr_p"] = idx
        save_db(db)
        p_text = u["paragraphs"][idx]
        await safe_edit(
            callback.message,
            f"📑 *Абзац #{idx+1} из {len(u['paragraphs'])}:*\n\n{p_text}\n\n"
            f"📋 _Быстрое копирование:_\n```text\n{p_text}\n```",
            reply_markup=get_paragraph_kb(idx, len(u["paragraphs"]))
        )
    await callback.answer()


@dp.callback_query(F.data == "pnew")
async def ask_new_paragraph_text(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.split_text)
    await callback.message.answer("✍️ Вставь новый текст, который нужно разбить по абзацам:")
    await callback.answer()


@dp.callback_query(F.data.startswith("pdel_"))
async def delete_paragraph(callback: types.CallbackQuery):
    idx = int(callback.data.replace("pdel_", ""))
    u = get_user(str(callback.from_user.id))
    if 0 <= idx < len(u["paragraphs"]):
        u["paragraphs"].pop(idx)
        u["curr_p"] = max(0, idx - 1)
        save_db(db)
        if not u["paragraphs"]:
            await callback.message.edit_text("🗑 Все абзацы удалены.")
        else:
            new_idx = u["curr_p"]
            p_text = u["paragraphs"][new_idx]
            await safe_edit(
                callback.message,
                f"📑 *Абзац #{new_idx+1} из {len(u['paragraphs'])}:*\n\n{p_text}",
                reply_markup=get_paragraph_kb(new_idx, len(u["paragraphs"]))
            )
    await callback.answer("Абзац удален")


@dp.callback_query(F.data.startswith("pedit_"))
async def edit_paragraph_start(callback: types.CallbackQuery, state: FSMContext):
    idx = int(callback.data.replace("pedit_", ""))
    await state.update_data(edit_idx=idx)
    await state.set_state(BotStates.edit_paragraph)
    await safe_answer(callback.message, f"✏️ Отправь исправленный текст для *Абзаца #{idx+1}*:")
    await callback.answer()


@dp.message(BotStates.edit_paragraph)
async def edit_paragraph_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    idx = data.get("edit_idx", 0)
    u = get_user(str(message.from_user.id))
    if 0 <= idx < len(u["paragraphs"]) and message.text:
        u["paragraphs"][idx] = message.text
        u["curr_p"] = idx
        save_db(db)
    await state.clear()
    await message.answer("✅ Абзац обновлён!", reply_markup=main_kb())
    await show_paragraphs(message, state)


@dp.callback_query(F.data == "pmerge")
async def merge_paragraphs_all(callback: types.CallbackQuery):
    u = get_user(str(callback.from_user.id))
    full_text = "\n\n".join(u["paragraphs"])
    file_md = BufferedInputFile(full_text.encode("utf-8"), filename="merged_lesson.md")
    await callback.message.answer_document(file_md, caption="📄 Собранный .MD файл из всех текущих абзацев")
    if len(full_text) <= 3800:
        await safe_answer(callback.message, f"📋 *Быстрое копирование:*\n```text\n{full_text}\n```")
    await callback.answer()


# =====================================================================
# 📸 8. СКРИНШОТЫ И РАЗБОР БАГОВ (ФОТО + КАРТИНКИ)
# =====================================================================
@dp.message(F.photo)
async def handle_screenshot(message: types.Message):
    u = get_user(str(message.from_user.id))
    file_id = message.photo[-1].file_id
    caption = message.caption or f"Скриншот #{len(u['screenshots']) + 1} (без описания)"

    u["screenshots"].append({
        "file_id": file_id,
        "caption": caption,
        "date": datetime.now().strftime("%d.%m %H:%M")
    })
    u["history"].append({
        "role": "user",
        "text": f"[СКРИНШОТ #{len(u['screenshots'])}]: {caption}"
    })
    save_db(db)

    idx = len(u["screenshots"]) - 1
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛠 Промпт: Разбор бага на скрине", callback_data=f"scbug_{idx}")],
        [InlineKeyboardButton(text="🧩 Промпт: Собрать это в Latch", callback_data=f"sclatch_{idx}")],
        [InlineKeyboardButton(text="✏️ Изменить заметку к скрину", callback_data=f"scnote_{idx}")]
    ])
    await safe_answer(
        message,
        f"📸 *Скриншот #{idx + 1} сохранён в мультитул!*\n"
        f"📝 _Заметка:_ {caption}\n\n"
        f"Выбери действие для этого скриншота:",
        reply_markup=kb
    )


@dp.message(F.text == "📸 Скриншоты и баги")
async def show_screenshots_vault(message: types.Message):
    u = get_user(str(message.from_user.id))
    if not u["screenshots"]:
        await safe_answer(
            message,
            "📸 *База скриншотов пока пуста.*\n\n"
            "Просто отправь или перешли мне любую картинку / скриншот из Roblox Studio или Latch (можно с подписью, что именно не работает) — я сохраню её и помогу сгенерировать точный запрос на починку!"
        )
        return

    await safe_answer(message, f"📸 *Сохранено скриншотов: {len(u['screenshots'])}* (показываю последние 5):")
    for i, sc in enumerate(u["screenshots"][-5:], max(0, len(u["screenshots"]) - 5)):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🛠 Разбор бага", callback_data=f"scbug_{i}"),
                InlineKeyboardButton(text="🧩 Схема в Latch", callback_data=f"sclatch_{i}")
            ],
            [InlineKeyboardButton(text="✏️ Изменить заметку", callback_data=f"scnote_{i}")]
        ])
        await message.answer_photo(
            photo=sc["file_id"],
            caption=f"📸 Скриншот #{i+1} ({sc.get('date', '')})\n📝 {sc['caption']}",
            reply_markup=kb
        )


@dp.callback_query(F.data.startswith("scbug_"))
async def prompt_from_screen_bug(callback: types.CallbackQuery):
    idx = int(callback.data.replace("scbug_", ""))
    u = get_user(str(callback.from_user.id))
    if 0 <= idx < len(u["screenshots"]):
        sc = u["screenshots"][idx]
        prompt = (
            "Посмотри на прикрепленный скриншот из Roblox Studio / плагина Latch.\n"
            f"Описание проблемы: {sc['caption']}\n\n"
            "Проверь и укажи без воды:\n"
            "1. Есть ли ошибка в типах переменных (например, строка в кавычках вместо синего овала переменной или 0 вместо nil).\n"
            "2. Совпадают ли имена объектов в WaitForChild с деревом Explorer (регистр букв, пробелы).\n"
            "3. В правильном ли объекте лежит скрипт (script.Parent) и включены ли Anchored / CanCollide.\n"
            "4. Напиши точный пошаговый фикс в блоках Latch и проверочный код Luau."
        )
        await safe_answer(
            callback.message,
            f"🔥 *Скопируй этот промпт и отправь нейросети вместе со скриншотом #{idx+1}:*\n```text\n{prompt}\n```"
        )
    await callback.answer()


@dp.callback_query(F.data.startswith("sclatch_"))
async def prompt_from_screen_latch(callback: types.CallbackQuery):
    idx = int(callback.data.replace("sclatch_", ""))
    u = get_user(str(callback.from_user.id))
    if 0 <= idx < len(u["screenshots"]):
        sc = u["screenshots"][idx]
        prompt = (
            "Посмотри на скриншот палитры / блоков плагина Latch (visual Luau в Roblox Studio).\n"
            f"Задача: {sc['caption']}\n\n"
            "Распиши пошагово строго по категориям блоков со скриншота (Events, Control, Logic, Math, Variables, Tables, Instances, Text):\n"
            "1. Какой блок взять и куда вставить.\n"
            "2. Как достать нужные свойства без ошибок ('property of is a value').\n"
            "3. Какой итоговый код Luau должен появиться в правом окне предпросмотра перед нажатием 'Save to script'."
        )
        await safe_answer(
            callback.message,
            f"🧩 *Скопируй промпт для сборки в Latch по скриншоту #{idx+1}:*\n```text\n{prompt}\n```"
        )
    await callback.answer()


@dp.callback_query(F.data.startswith("scnote_"))
async def edit_screen_note_start(callback: types.CallbackQuery, state: FSMContext):
    idx = int(callback.data.replace("scnote_", ""))
    await state.update_data(sc_idx=idx)
    await state.set_state(BotStates.edit_screen_note)
    await callback.message.answer(f"✏️ Введи новое описание/заметку для скриншота #{idx+1}:")
    await callback.answer()


@dp.message(BotStates.edit_screen_note)
async def edit_screen_note_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    idx = data.get("sc_idx", 0)
    u = get_user(str(message.from_user.id))
    if 0 <= idx < len(u["screenshots"]) and message.text:
        u["screenshots"][idx]["caption"] = message.text
        save_db(db)
    await state.clear()
    await message.answer("✅ Заметка к скриншоту обновлена!", reply_markup=main_kb())


# =====================================================================
# 📥 9. ИМПОРТ И ЭКСПОРТ ФАЙЛОВ (.MD, .JSON, .TXT)
# =====================================================================
@dp.message(F.document)
async def load_document_file(message: types.Message):
    doc = message.document
    fname = (doc.file_name or "").lower()

    # Если картинку скинули файлом без сжатия
    if fname.endswith((".png", ".jpg", ".jpeg", ".webp")):
        u = get_user(str(message.from_user.id))
        caption = message.caption or f"Скриншот-файл {doc.file_name}"
        u["screenshots"].append({
            "file_id": doc.file_id,
            "caption": caption,
            "date": datetime.now().strftime("%d.%m %H:%M")
        })
        u["history"].append({"role": "user", "text": f"[СКРИНШОТ-ФАЙЛ]: {caption}"})
        save_db(db)
        await message.answer(f"📸 Изображение `{doc.file_name}` сохранено в историю!")
        return

    if not fname.endswith((".json", ".md", ".txt")):
        await message.answer("⚠️ Поддерживаются файлы `.md`, `.json`, `.txt` и изображения (`.png`, `.jpg`).")
        return

    file = await bot.get_file(doc.file_id)
    raw = (await bot.download_file(file.file_path)).read().decode("utf-8", errors="ignore")

    try:
        if fname.endswith(".json"):
            extracted = parse_json_content(raw)
            fmt_label = "JSON"
        else:
            extracted = parse_md_content(raw)
            fmt_label = "Markdown / TXT"

        if not extracted:
            await message.answer(f"⚠️ Файл прочитан, но внутри не найдено текстовых блоков.")
            return

        u = get_user(str(message.from_user.id))
        u["history"].extend(extracted)
        u["paragraphs"] = split_into_paragraphs(extracted[-1]["text"])
        u["curr_p"] = 0
        save_db(db)

        await safe_answer(
            message,
            f"✅ *Импорт {fmt_label} (`{doc.file_name}`) завершён!*\n"
            f"• Загружено плашек диалога: *{len(extracted)}* (всего в базе: {len(u['history'])})\n"
            f"• Последний блок автоматически разбит на *{len(u['paragraphs'])} абзацев*.\n\n"
            f"Жми `📑 Разбор по абзацам` или `🗂 Плашки диалога`!",
            reply_markup=main_kb()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка чтения файла {doc.file_name}: {e}")


@dp.message(F.text == "📥 Выгрузить (MD / JSON)")
async def export_all_menu(message: types.Message):
    u = get_user(str(message.from_user.id))
    if not u["history"] and not u["paragraphs"]:
        await message.answer("📭 Память пуста — сначала добавь сообщения или загрузи файл.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Скачать всю историю в .MD (Markdown)", callback_data="exp_md")],
        [InlineKeyboardButton(text="📦 Скачать полный бэкап в .JSON", callback_data="exp_json")],
        [InlineKeyboardButton(text="📑 Скачать только текущие абзацы (.MD)", callback_data="pmerge")]
    ])
    await safe_answer(
        message,
        f"📥 *Экспорт материалов из мультитула:*\n"
        f"Плашек в базе: *{len(u['history'])}* | Текущих абзацев: *{len(u['paragraphs'])}*\n"
        f"Выбери нужный формат файла:",
        reply_markup=kb
    )


@dp.callback_query(F.data == "exp_md")
async def export_md_cb(callback: types.CallbackQuery):
    u = get_user(str(callback.from_user.id))
    md_text = build_markdown_export(u["history"])
    md_file = BufferedInputFile(md_text.encode("utf-8"), filename="gamedev_chat_export.md")
    await callback.message.answer_document(
        md_file,
        caption="📝 Полный экспорт твоей сессии в формате Markdown (.md)"
    )
    await callback.answer()


@dp.callback_query(F.data == "exp_json")
async def export_json_cb(callback: types.CallbackQuery):
    u = get_user(str(callback.from_user.id))
    j_file = BufferedInputFile(
        json.dumps(u["history"], ensure_ascii=False, indent=2).encode("utf-8"),
        filename="context_backup.json"
    )
    await callback.message.answer_document(j_file, caption="📦 Полный JSON-архив твоей базы")
    await callback.answer()


# =====================================================================
# 💬 10. РУЧНОЕ ДОБАВЛЕНИЕ СООБЩЕНИЙ И ГЕНЕРАТОР ПРОМПТОВ
# =====================================================================
@dp.message(F.text == "👤 + Моё сообщение")
async def add_u_start(message: types.Message, state: FSMContext):
    await state.set_state(BotStates.add_user)
    await safe_answer(message, "👤 Вставь текст *твоего сообщения*:")


@dp.message(BotStates.add_user)
async def add_u_done(message: types.Message, state: FSMContext):
    u = get_user(str(message.from_user.id))
    if message.text:
        u["history"].append({"role": "user", "text": message.text})
        save_db(db)
    await state.clear()
    await message.answer(f"✅ Моё сообщение сохранено! (Плашек: {len(u['history'])})", reply_markup=main_kb())


@dp.message(F.text == "🤖 + Ответ нейросети")
async def add_ai_start(message: types.Message, state: FSMContext):
    await state.set_state(BotStates.add_ai)
    await safe_answer(message, "🤖 Вставь *ответ нейросети* (он также автоматически разобьётся на абзацы):")


@dp.message(BotStates.add_ai)
async def add_ai_done(message: types.Message, state: FSMContext):
    u = get_user(str(message.from_user.id))
    if message.text:
        u["history"].append({"role": "model", "text": message.text})
        u["paragraphs"] = split_into_paragraphs(message.text)
        u["curr_p"] = 0
        save_db(db)
    await state.clear()
    await safe_answer(
        message,
        f"✅ Ответ сохранён и разбит на *{len(u['paragraphs'])} абзацев*! Листай их через `📑 Разбор по абзацам`.",
        reply_markup=main_kb()
    )


@dp.message(F.text.in_(["📘 Промпт: Методичка", "🖥 Промпт: Презентация", "🧩 Промпт: Практика"]))
async def prompt_builder_start(message: types.Message, state: FSMContext):
    modes = {
        "📘 Промпт: Методичка": "method",
        "🖥 Промпт: Презентация": "pres",
        "🧩 Промпт: Практика": "raw_lesson"
    }
    await state.update_data(pmode=modes[message.text])
    await state.set_state(BotStates.prompt_task)
    await safe_answer(
        message,
        "🎯 *Напиши тему или задачу* (например: _«Урок 3 Тайкуна: Апгрейдер и покупка стен»_):"
    )


@dp.message(BotStates.prompt_task)
async def prompt_builder_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pmode = data.get("pmode", "raw_lesson")
    task_text = message.text or ""
    await state.clear()

    u = get_user(str(message.from_user.id))
    u["history"].append({"role": "user", "text": task_text})
    save_db(db)

    sys_text = SYSTEM_PROMPTS[pmode]
    context_tail = ""
    if len(u["history"]) > 1:
        lines = []
        for h in u["history"][:-1][-6:]:
            tag = "Я" if h["role"] == "user" else "ИИ"
            lines.append(f"[{tag}]: {h['text'][:700]}")
        context_tail = "\n\n=== КОНТЕКСТ КУРСА ===\n" + "\n---\n".join(lines)

    full_prompt = f"{sys_text}{context_tail}\n\n=== ТЕКУЩАЯ ЗАДАЧА ===\n{task_text}"

    if len(full_prompt) <= 3800:
        await safe_answer(
            message,
            f"🔥 *Скопируй одним нажатием и вставь в нейросеть:*\n```text\n{full_prompt}\n```",
            reply_markup=main_kb()
        )
    else:
        f_out = BufferedInputFile(full_prompt.encode("utf-8"), filename="smart_prompt.md")
        await message.answer_document(
            f_out,
            caption="🔥 Полный промпт с историей (.md) + ниже короткая версия для копирования:"
        )
        short_p = f"{sys_text}\n\n=== ТЕКУЩАЯ ЗАДАЧА ===\n{task_text}"
        await safe_answer(message, f"```text\n{short_p[:3800]}\n```", reply_markup=main_kb())


@dp.message(F.text == "🗂 Плашки диалога")
async def view_history_cards(message: types.Message):
    u = get_user(str(message.from_user.id))
    if not u["history"]:
        await message.answer("📭 В памяти пока нет диалогов. Закинь сюда файл .md или .json!")
        return
    total = len(u["history"])
    start_idx = max(0, total - 8)
    for i in range(start_idx, total):
        item = u["history"][i]
        icon = "👤 Я" if item["role"] == "user" else "🤖 ИИ"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📑 Разбить эту плашку на абзацы", callback_data=f"splitcard_{i}")]
        ])
        preview = item["text"][:350].replace("`", "'")
        await safe_answer(
            message,
            f"*Плашка #{i+1} из {total} [{icon}]*\n{preview}...",
            reply_markup=kb
        )


@dp.callback_query(F.data.startswith("splitcard_"))
async def split_specific_card(callback: types.CallbackQuery, state: FSMContext):
    idx = int(callback.data.replace("splitcard_", ""))
    u = get_user(str(callback.from_user.id))
    if 0 <= idx < len(u["history"]):
        u["paragraphs"] = split_into_paragraphs(u["history"][idx]["text"])
        u["curr_p"] = 0
        save_db(db)
        await show_paragraphs(callback.message, state)
    await callback.answer()


@dp.message(F.text == "🗑 Очистить сессию")
async def clear_all(message: types.Message, state: FSMContext):
    await state.clear()
    db[str(message.from_user.id)] = {"history": [], "paragraphs": [], "curr_p": 0, "screenshots": []}
    save_db(db)
    await safe_answer(
        message,
        "🧹 Рабочая сессия очищена (встроенная база скриптов `💻 Скриптинг` на месте!).",
        reply_markup=main_kb()
    )


# =====================================================================
# 🔌 11. АВТО-ПОДБОР РАБОЧЕГО КАНАЛА СВЯЗИ И ЗАПУСК
# =====================================================================
async def create_working_bot() -> Bot:
    for proxy in PROXY_CANDIDATES:
        label = proxy if proxy else "Прямое соединение (Облако / Без прокси)"
        print(f"🔄 Пробую подключиться к Telegram через: {label} ...")
        test_bot = None
        try:
            if proxy:
                session_client = AiohttpSession(proxy=proxy, timeout=10)
            else:
                session_client = AiohttpSession(timeout=10)
                session_client._connector_init["family"] = socket.AF_INET

            test_bot = Bot(token=BOT_TOKEN, session=session_client)
            me = await test_bot.get_me()
            print(f"✅ УСПЕХ! Бот @{me.username} подключился через: {label}")
            return test_bot
        except Exception as e:
            print(f"⚠️ Не подошло ({label}): {e}")
            if test_bot:
                try:
                    await test_bot.session.close()
                except Exception:
                    pass

    raise RuntimeError(
        "❌ Ни один способ подключения не сработал! Проверь правильность BOT_TOKEN."
    )


async def main():
    global bot
    bot = await create_working_bot()
    print("⚡ ИИ-Комбайн 3.0 готов к работе! Жми /start в Telegram.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
