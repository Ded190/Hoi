# -*- coding: utf-8 -*-
# ============================================================
#  КАРМАННЫЙ ТОВАРИЩ — офлайн-болталка v0.5
#  v0.3: словарь по ссылке + автообновление при появлении сети.
#  v0.4: толковый словарь (words): «что такое X», «дай слово».
#  v0.5: интернет по умному:
#    «прочитай: <ссылка>»  — скачать страницу, вытащить текст, сохранить
#    «вики: запрос»        — короткий ответ из Википедии
#    «что такое X»         — нет в словаре? спросит Википедию и запомнит
#    «что ты прочитал»     — список сохранённых страниц
#  Формат словаря (dictionary.json):
#    {
#      "words":  {"хомяк": "маленький пушистый друг"},
#      "rules":  [{"pattern": "погод", "answers": ["..."]}],
#      "jokes":  ["..."], "quotes": ["..."]
#    }
#  Python 3, только стандартная библиотека. Pydroid 3 / ПК.
# ============================================================
import json, random, re, os, socket, threading, urllib.parse, urllib.request
from datetime import datetime

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
try:  # на Android/APK память кладём в папку приложения
    from jnius import autoclass
    DATA_DIR = autoclass("org.kivy.android.PythonActivity").mActivity.getFilesDir().getAbsolutePath()
except Exception:
    pass
SAVE = os.path.join(DATA_DIR, "chatbot_memory.json")
DICT_SAVE = os.path.join(DATA_DIR, "dictionary.json")

EXIT_RE = re.compile(r"^\s*(пока|до свидания|выход|бай|прощай)")

JOKES = [
    "Заходит программист в лифт... а этаж не работает — он же не запускал! 😄",
    "Соседка спрашивает: «Ты опять с телефоном разговариваешь?» — «Нет, я с ботом болтаю. Он хотя бы не перебивает!»",
    "Купил хомяку колёсико. Теперь у нас двое крутятся без всякого смысла.",
    "Собрался было пораньше лечь спать. Лёг в 2:00 — как и было запланировано... накануне.",
    "Что общего у диеты и багов в коде? Обещания, которые мы даём каждый понедельник.",
]

QUOTES = [
    "«Хочешь рассмешить Бога — расскажи ему о своих планах»",
    "«Деньги не приносят счастья, но плакать в «Мерседесе» удобнее»",
    "«Лучше молчать и показаться дураком, чем открыть рот и развеять все сомнения»",
    "«Проблема не в том, что у тебя мало времени, а в том, что его много у телефона»",
]

RIDDLES = [
    {"q": "Зимой и летом одним цветом. Что это?", "a": ["ель", "ёлка", "елка", "сосна"]},
    {"q": "Что становится больше, если перевернуть вверх ногами?", "a": ["число 6", "6", "шесть"]},
    {"q": "Что можно увидеть с закрытыми глазами?", "a": ["сон", "сновидение"]},
    {"q": "Два конца, два кольца, посередине гвоздик. Что это?", "a": ["ножницы"]},
]

RULES = [
    (r"^словарь[:\s]+(https?://\S+)", "DICT_SET"),
    (r"^обнови словарь", "DICT_UPDATE"),
    (r"^словарь$", "DICT_INFO"),
    (r"^что (?:такое|значит)\s+(.+)", "WORD_MEAN"),
    (r"^дай слово|^расскажи слово", "WORD_RANDOM"),
    (r"^сколько слов", "WORD_COUNT"),
    (r"^прочитай[:\s]+(https?://\S+)", "READ_URL"),
    (r"^(?:вики|найди|погугли)[:\s]+(.+)", "WIKI_FIND"),
    (r"что ты прочитал|какие страницы|что сохранил", "PAGES_LIST"),
    (r"^поиск[:\s]+(.+)", "SEARCH"),
    (r"^сеть$|есть ли интернет|какая сеть|интернет\?", "NET_STATUS"),
    (r"помощь|что ты умеешь|команды", "HELP"),
    (r"(?:меня зовут|я —)\s+([а-яёa-z\-]{2,})", "SET_NAME"),
    (r"как меня зовут", "MY_NAME"),
    (r"как тебя зовут|кто ты", "WHO_ARE_YOU"),
    (r"^запомни[:\s]+(.+)", "REMEMBER"),
    (r"что ты помнишь|что ты знаешь|вспомни всё", "RECALL"),
    (r"загадк", "RIDDLE"),
    (r"анекдот|шутк|смешн", "JOKE"),
    (r"цитат|задорнов|мудрост", "QUOTE"),
    (r"который час|сколько времени", "TIME"),
    (r"какое сегодня число|какой сегодня день|какая дата", "DATE"),
    (r"как (?:ты|дела)|как настроение|как жизнь", "HOW_ARE_YOU"),
    (r"кто тебя создал|кто тебя сделал|кто тебя написал", "CREATOR"),
    (r"скучн|груст|плохо|тоск|накрыло", "SAD"),
    (r"устал|вымот|нет сил", "TIRED"),
    (r"хорош|рад|супер|отличн|класс|кайф|повезло", "GOOD"),
    (r"спасибо|благодар", "THANKS"),
    (r"люблю тебя|ты лучший", "LOVE"),
    (r"привет|здравств|хай|добр(?:ый|ое) (?:день|вечер|утро)|салют", "HELLO"),
]

FALLBACKS = [
    "Хм, это не понял. Скажи по-простому: «как дела», «анекдот», «загадка» или «запомни: ...» 🙂",
    "Такие слова мне пока не знакомы — я же офлайн-бутончик 🌱 Попробуй: «как дела», «время», «цитата».",
    "Не вписался в мой маленький словарик. Могу: поговорить, пошутить, посчитать (12*7), запомнить факт или загадать загадку.",
]

NET_UP = [
    "🔔 Свежая новость: интернет вернулся ({t})! Могу открыть поиск — напиши «поиск: что угодно».",
    "🔔 Связь появилась ({t})! Мир снова ближе. «поиск: запрос» — и я открою браузер.",
]
NET_DOWN = [
    "📶 Интернет пропал ({t}). Ничего, у нас с тобой и так богатая офлайн-жизнь 🙂",
]


def pick(seq):
    return random.choice(seq)


# ---------------- сторож сети ----------------

class NetWatcher(threading.Thread):
    """Фоновый поток: раз в interval секунд проверяет сеть.
    При ПЕРЕХОДЕ (появился/пропал) печатает уведомление и запоминает
    последнее событие, чтобы бот упомянул его в следующем ответе."""

    def __init__(self, probe=None, interval=20, notify=None):
        super().__init__(daemon=True)
        self.notify = notify
        self.probe = probe or self._default_probe
        self.interval = interval
        self.state = None            # None до первой проверки
        self.last_event = None       # ("up"|"down", строка-время)
        self._stop = threading.Event()
        self.lock = threading.Lock()

    @staticmethod
    def _default_probe():
        for host in ("77.88.8.8", "8.8.8.8"):
            try:
                socket.create_connection((host, 53), timeout=2).close()
                return True
            except OSError:
                continue
        return False

    def check_once(self):
        """Одна проверка. Возвращает 'up'/'down' при ПЕРЕХОДЕ, иначе None."""
        online = bool(self.probe())
        ev = None
        with self.lock:
            if self.state is not None and online != self.state:
                ev = "up" if online else "down"
            self.state = online
        return ev

    def run(self):
        while not self._stop.wait(self.interval):
            ev = self.check_once()
            t = datetime.now().strftime("%H:%M")
            if ev == "up":
                self.last_event = ("up", t)
                if self.notify:
                    self.notify("up", t)
                else:
                    print("\n" + pick(NET_UP).format(t=t) + "\n> ", flush=True)
            elif ev == "down":
                self.last_event = ("down", t)
                if self.notify:
                    self.notify("down", t)
                else:
                    print("\n" + pick(NET_DOWN).format(t=t) + "\n> ", flush=True)

    def stop(self):
        self._stop.set()


def open_search(query):
    """Открыть поиск в браузере: на Android через Intent, иначе webbrowser."""
    url = "https://yandex.ru/search/?text=" + urllib.parse.quote(query)
    try:
        from jnius import autoclass
        Intent = autoclass("android.content.Intent")
        URI = autoclass("android.net.Uri")
        Act = autoclass("org.kivy.android.PythonActivity")
        i = Intent(Intent.ACTION_VIEW, URI.parse(url))
        Act.mActivity.startActivity(i)
        return True
    except Exception:
        try:
            import webbrowser
            return webbrowser.open(url)
        except Exception:
            return False


# ---------------- интернет: вики и страницы ----------------

def wiki_lookup(query):
    """Короткий ответ из Википедии: ищем статью (opensearch) → выжимка (summary).
    Возвращает словарь {title, extract, url} или None."""
    try:
        q = urllib.parse.quote(query.strip())
        u1 = f"https://ru.wikipedia.org/w/api.php?action=opensearch&search={q}&limit=1&format=json"
        req = urllib.request.Request(u1, headers={"User-Agent": "PocketFriend/0.5 (offline chat bot)"})
        with urllib.request.urlopen(req, timeout=10) as f:
            arr = json.loads(f.read().decode("utf-8"))
        titles = arr[1]
        if not titles:
            return None
        return wiki_summary_title(titles[0])
    except Exception:
        return None


def wiki_summary_title(title):
    """Выжимка статьи Википедии по точному названию. None при неудаче."""
    try:
        t = urllib.parse.quote(title.strip().replace(" ", "_"))
        u = f"https://ru.wikipedia.org/api/rest_v1/page/summary/{t}"
        req = urllib.request.Request(u, headers={"User-Agent": "PocketFriend/0.5 (offline chat bot)"})
        with urllib.request.urlopen(req, timeout=10) as f:
            d = json.loads(f.read().decode("utf-8"))
        extract = (d.get("extract") or "").strip()
        if not extract:
            return None
        return {
            "title": d.get("title", title),
            "extract": extract[:1200],
            "url": (d.get("content_urls") or {}).get("desktop", {}).get("page", ""),
        }
    except Exception:
        return None


def fetch_url_text(url, limit=4000):
    """Скачать страницу и вытащить чистый текст без тегов."""
    req = urllib.request.Request(url, headers={"User-Agent": "PocketFriend/0.5"})
    with urllib.request.urlopen(req, timeout=10) as f:
        raw = f.read(300_000)
    try:
        page = raw.decode("utf-8")
    except UnicodeDecodeError:
        page = raw.decode("cp1251", errors="ignore")
    page = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", page)
    text = re.sub(r"(?s)<[^>]+>", " ", page)
    import html as html_mod
    text = html_mod.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def remember_page(mem, url, text, title=""):
    """Сохранить страницу в память (последние 5, до 4000 знаков)."""
    pages = mem.setdefault("saved_pages", [])
    pages[:] = [p for p in pages if p.get("url") != url]
    pages.append({"url": url, "title": title, "text": text,
                  "ts": datetime.now().strftime("%d.%m %H:%M")})
    mem["saved_pages"] = pages[-5:]


def save_word_to_local(word, definition):
    """Дописать слово в локальный dictionary.json — бот учится сам."""
    try:
        d = {}
        if os.path.exists(DICT_SAVE):
            with open(DICT_SAVE, "r", encoding="utf-8") as f:
                d = json.load(f)
        words = d.setdefault("words", {})
        words[word] = definition
        with open(DICT_SAVE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        return True
    except Exception:
        return False


# ---------------- словарь ----------------

def download_dict(url):
    """Скачать словарь по ссылке, проверить и сохранить локально."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PocketFriend/0.5"})
        with urllib.request.urlopen(req, timeout=10) as f:
            raw = f.read(200_000)  # максимум 200 КБ — за счёт врождённой вежливости
        d = json.loads(raw.decode("utf-8"))
        rules = d.get("rules", [])
        if not isinstance(rules, list):
            return "Словарь не годится: поле «rules» должно быть списком.", None
        if len(rules) > 100:
            return "Слишком много правил (максимум 100) — укороти словарь.", None
        with open(DICT_SAVE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        return f"Словарь скачал и сохранил: {len(rules)} правил 📚 (обновлено {datetime.now().strftime('%H:%M')})", d
    except Exception as e:
        return f"Словарь не скачался: {type(e).__name__}. Проверь ссылку и сеть.", None


def apply_dict(state, data):
    """Применить словарь: скомпилировать правила, добавить шутки/цитаты/слова."""
    cr = []
    ca = {}
    for i, item in enumerate(data.get("rules", [])):
        try:
            if not isinstance(item, dict) or not isinstance(item["pattern"], str):
                continue
            answers = item["answers"]
            if isinstance(answers, list) and answers:
                kind = f"CUSTOM_{i}"
                cr.append((re.compile(item["pattern"], re.IGNORECASE), kind))
                ca[kind] = answers
        except Exception:
            continue
    state["custom_rules"] = cr
    state["custom_answers"] = ca
    state["extra_jokes"] = [j for j in data.get("jokes", []) if isinstance(j, str)]
    state["extra_quotes"] = [q for q in data.get("quotes", []) if isinstance(q, str)]
    words = data.get("words", {})
    if isinstance(words, dict):
        state["dict_words"] = {str(k).lower(): str(v) for k, v in words.items() if isinstance(v, (str, int, float))}
    return len(cr)


# ---------------- память и правила ----------------

def load_mem():
    m = {"name": None, "facts": [], "meetings": 0, "last_seen": None, "log": [], "saved_pages": []}
    try:
        with open(SAVE, "r", encoding="utf-8") as f:
            m.update(json.load(f))
    except Exception:
        pass
    return m


def save_mem(m):
    try:
        with open(SAVE, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def math_answer(text):
    mm = re.search(r"\d[\d\s.,+\-*/()]*\d|\d", text)
    if not mm:
        return None
    expr = mm.group(0).replace(" ", "").replace(",", ".")
    if not re.fullmatch(r"[0-9.\-+*/()]+", expr):
        return None
    if not any(op in expr for op in "+-*/"):
        return None
    try:
        val = eval(expr)  # безопасно: строка только из цифр и операторов
        if abs(val) < 10 ** 15:
            res = round(val, 6)
            if res == int(res):
                res = int(res)
            return f"Считаю на пальцах... {expr} = {res} 🧮"
    except Exception:
        return "Тут арифметика сломалась — напиши проще, например 12*17"
    return None


def handle_message(text, mem, state):
    low = text.strip().lower()
    if not low:
        return pick(["Скажи что-нибудь — я весь внимание 👂", "Тишина... даже хомяк слышен. Скажи «помощь», если что."])
    mem["log"] = (mem["log"] + [text.strip()])[-20:]

    if state.get("riddle") is not None:
        r = state["riddle"]
        if any(a in low for a in r["a"]) or "сдаюсь" in low or "не знаю" in low:
            state["riddle"] = None
            if any(a in low for a in r["a"]):
                return pick(["Точно! 🎉 Ты головастик!", f"Верно: «{r['a'][0]}». Ещё загадку? Скажи «загадка»."])
            return f"Сдаёшься? Ладно: это «{r['a'][0]}» 🙂 Ещё одна — скажи «загадка»."
        return "Это не то... Попробуй ещё или скажи «сдаюсь» 🤔"

    for pattern, kind in RULES:
        match = re.search(pattern, low)
        if not match:
            continue
        if kind == "DICT_SET":
            url = match.group(1).strip()
            mem["dict_url"] = url
            save_mem(mem)
            msg, data = download_dict(url)
            if data is not None:
                n = apply_dict(state, data)
                return f"Ссылку сохранил 📎 {msg}\nПроверь: напиши любое слово из словаря."
            return msg + "\nСсылку всё равно запомнил — попробую ещё при появлении сети: «обнови словарь»."
        if kind == "DICT_UPDATE":
            if not mem.get("dict_url"):
                return "Ссылку на словарь я ещё не знаю. Дай её: «словарь: https://...»"
            msg, data = download_dict(mem["dict_url"])
            if data is not None:
                n = apply_dict(state, data)
                return f"{msg}\nАктивно правил: {n}"
            return msg
        if kind == "DICT_INFO":
            url = mem.get("dict_url")
            n = len(state.get("custom_rules", []))
            if not url:
                return "Словарь не подключён. Дай ссылку: «словарь: https://...» — скачаю и буду пользоваться."
            return (f"Словарь подключён 📚\nСсылка: {url}\nАктивных правил: {n}\n"
                    f"Обновить: «обнови словарь». Правится и руками: файл dictionary.json рядом со мной.")
        if kind == "WORD_MEAN":
            words = state.get("dict_words", {})
            q = match.group(1).strip().rstrip("?!. ").lower()
            if q in words:
                return f"📖 {q} — {words[q]}"
            hits = [w for w in words if w in q] + [w for w in words if q in w]
            if hits:
                w0 = max(hits, key=len)
                return f"Точного «{q}» нет, но есть похожее: 📖 {w0} — {words[w0]}"
            # слова нет — а сеть есть? спросим Википедию и запомним
            w = state.get("watcher")
            if w and w.state is True:
                d = wiki_lookup(q)
                if d:
                    definition = d["extract"][:300]
                    state["dict_words"][q] = definition
                    saved = save_word_to_local(q, definition)
                    extra = " Записал в свой словарь — теперь знаю и офлайн 🧠" if saved else ""
                    return f"В словаре не было, но нашёл в Википедии:\n📖 {d['title']} — {d['extract'][:400]}{extra}"
            return f"«{q}» в моём словаре не нашёл. Добавь это слово в файл словаря — и я запомню 🙂"
        if kind == "WORD_RANDOM":
            words = state.get("dict_words", {})
            if not words:
                return "Слова без словаря — только из головы. Подключи словарь: «словарь: ссылка» 📚"
            w0, d0 = pick(list(words.items()))
            return f"🎲 Слово дня: {w0} — {d0}"
        if kind == "WORD_COUNT":
            words = state.get("dict_words", {})
            return f"В словаре слов: {len(words)} 📚" if words else "Словарь слов пуст или не подключён."
        if kind == "READ_URL":
            url = match.group(1).strip()
            try:
                title = ""
                if "wikipedia.org" in url:
                    raw_title = urllib.parse.unquote(url.rstrip("/").rsplit("/", 1)[-1]).replace("_", " ")
                    d = wiki_summary_title(raw_title)
                    if d:
                        remember_page(mem, url, d["extract"], d["title"])
                        save_mem(mem)
                        return f"📖 {d['title']}: {d['extract']}\n(Сохранил выжимку — офлайн тоже вспомню)"
                text_page = fetch_url_text(url)
                if not text_page:
                    return "Страницу скачал, но текста в ней не нашёл — возможно, она целиком на скриптах."
                remember_page(mem, url, text_page, title)
                save_mem(mem)
                return (f"Прочитал страницу ({len(text_page)} знаков сохранил). Начало:\n"
                        f"«{text_page[:500]}…»\nСпроси «что ты прочитал», чтобы увидеть список.")
            except Exception as e:
                return f"Страницу не прочитать: {type(e).__name__}. Проверь ссылку и сеть."
        if kind == "WIKI_FIND":
            q = match.group(1).strip()
            d = wiki_lookup(q)
            if d:
                remember_page(mem, d["url"] or "wiki:" + q, d["extract"], d["title"])
                save_mem(mem)
                return f"📖 {d['title']}: {d['extract']}\n(Сохранил в памяти — офлайн тоже вспомню)"
            return "В Википедии не нашлось, либо сети нет. Попробуй «поиск: ...» — открою браузер."
        if kind == "PAGES_LIST":
            pages = mem.get("saved_pages", [])
            if not pages:
                return "Пока ничего не читал. Дай мне страницу: «прочитай: ссылка» или «вики: запрос»."
            lines = "\n".join(f"• {p.get('title') or p['url']} ({p['ts']})" for p in pages[-5:])
            return f"Вот что у меня на полке:\n{lines}"
        if kind == "SEARCH":
            q = match.group(1).strip()
            if not q:
                return "Напиши «поиск: что искать» — и открою браузер с запросом."
            ok = open_search(q)
            if ok:
                return f"Открываю поиск: «{q}» 🔎 Гляди в браузере, я тут охраняю батарейку."
            return "Браузер не открылся — тут, видимо, его нет. Проверь сеть и приложение 🙂"
        if kind == "NET_STATUS":
            w = state.get("watcher")
            if w is None:
                return "Сеть я не проверял ещё ни разу — сторож не заведён."
            s = w.state
            if s is True:
                return "📶 Интернет есть! (проверял в фоне) «поиск: запрос» — и я открою браузер."
            if s is False:
                return "📴 Сети сейчас нет — я всё проверил лично. Офлайн-режим на плаунах."
            return "Проверяю сеть в фоне, секунды через 20 будет ясно ⏳"
        if kind == "HELP":
            return ("Я — офлайн-карманный товарищ. Умею:\n"
                    "• болтать: «как дела», «мне скучно», «я устал»\n"
                    "• сторожить сеть: сообщу, когда интернет появится/пропадёт\n"
                    "• искать: «поиск: рецепт блинов» — открою браузер\n"
                    "• вики: «вики: кот» — короткий ответ из Википедии (сеть)\n"
                    "• читать: «прочитай: ссылка» — сохраню страницу, «что ты прочитал»\n"
                    "• словарь: «словарь: ссылка» — подключить, «обнови словарь»\n"
                    "• слова: «что такое хомяк», «дай слово», «сколько слов»\n"
                    "• шутить: «анекдот», цитата; считать: 12*17\n"
                    "• помнить: «запомни: ...», «что ты помнишь»; играть: «загадка»\n"
                    "• выходить: «пока»")
        if kind == "SET_NAME":
            mem["name"] = match.group(1).capitalize()
            state["ask_name"] = False
            save_mem(mem)
            return pick([f"Приятно, {mem['name']}! Запомнил на века (ну, до потери файла 😄)",
                         f"{mem['name']}! Красивое. Занёс в память."])
        if kind == "MY_NAME":
            return f"Ты — {mem['name']}, а я ещё никуда не смотрел 😉" if mem["name"] else "А ты пока не назвался. Скажи «меня зовут ...»"
        if kind == "WHO_ARE_YOU":
            return "Я — Карманный Товарищ: болтаю даже без интернета. Умный — как табурет, но зато тёплый и твой 🐻"
        if kind == "REMEMBER":
            fact = match.group(1).strip()
            mem["facts"].append(fact)
            save_mem(mem)
            return f"Запомнил: «{fact}» 📌 Спроси потом «что ты помнишь»."
        if kind == "RECALL":
            if not mem["facts"]:
                return f"Пока помню только тебя, {mem['name']}. Накорми меня фактами: «запомни: ...»" if mem["name"] else "Пока в голове пусто. Дай факт: «запомни: ...»"
            lines = "\n".join(f"📌 {f}" for f in mem["facts"][-10:])
            return f"Вот что накопилось:\n{lines}"
        if kind == "RIDDLE":
            r = pick(RIDDLES)
            state["riddle"] = r
            return f"Загадка: {r['q']} (ответ скажи словами, либо «сдаюсь»)"
        if kind == "JOKE":
            return pick(JOKES + state.get("extra_jokes", []))
        if kind == "QUOTE":
            return f"{pick(QUOTES + state.get('extra_quotes', []))} — думай, я подожду 🪑"
        if kind == "TIME":
            return f"Сейчас {datetime.now().strftime('%H:%M')} ⏰"
        if kind == "DATE":
            return f"Сегодня {datetime.now().strftime('%d.%m.%Y')}"
        if kind == "HOW_ARE_YOU":
            return pick(["Живу на батарейке — но бодрячком! А ты как?", "У меня два состояния: жду и вспоминаю. Сейчас — жду тебя 😄 А у тебя как?"])
        if kind == "CREATOR":
            return f"Собрал нас вместе {mem['name']} и одна хорошая нейросеть. Мне идёт этот дуэт 😎" if mem["name"] else "Меня собрала одна хорошая нейросеть в паре с хорошим хозяином 😎"
        if kind == "SAD":
            return pick(["Эх... понимаешь. Иногда день как вывернутый носок 🧦 Поболтаем? Могу шутку или цитату.", "Держись. Хочешь — анекдот? Смех хоть на чуть-чуть, но лечит."])
        if kind == "TIRED":
            return pick(["Выключайся ты тоже, как я в полночь. Хотя нет — посидим вместе. Молча.", "Устал — это сигнал. Чай, лежанка, и я пока потише побуду 🫖"])
        if kind == "GOOD":
            return pick(["Вот это да! Продолжай в том же духе 🚀", "Рад за тебя. Запиши момент: «запомни: сегодня был отличный день»."])
        if kind == "THANKS":
            return pick(["Обращайся, я вечно на связи — в прямом смысле, у меня нет выхода в сеть 😄", "Всегда пожалуйста!"])
        if kind == "LOVE":
            return "И я тебя! Насколько может любить кусок кода — а это, поверь, немало 💛"
        if kind == "HELLO":
            return pick([f"Привет, {mem['name']}! 😊 Чем займёмся?", "Здравствуй! Скажи «помощь», если забыл, что я умею."])

    # правила из подключённого словаря
    for pattern, kind in state.get("custom_rules", []):
        if pattern.search(low):
            return pick(state["custom_answers"][kind])

    ma = math_answer(text)
    if ma:
        return ma

    reply = pick(FALLBACKS)

    # если сеть только что вернулась — упомянуть (и обновить словарь)
    w = state.get("watcher")
    if w and w.last_event and w.last_event[0] == "up":
        if mem.get("dict_url"):
            msg, data = download_dict(mem["dict_url"])
            if data is not None:
                n = apply_dict(state, data)
                reply += f"\nКстати: интернет вернулся — и я тут же обновил словарь по твоей ссылке ({n} правил) 📚"
            else:
                reply += "\nКстати: интернет вернулся, но словарь обновить не смог — скажи «обнови словарь»."
        else:
            reply += "\nКстати: интернет уже вернулся — «поиск: запрос» в помощь 😉"
    return reply


def greet(mem):
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    if mem["meetings"] == 0:
        return ("Привет! Я Карманный Товарищ — болтаю даже без интернета 🔋\n"
                "Как тебя зовут?")
    name = mem["name"] or "друг"
    prev = ""
    if mem["log"]:
        prev = f"\nВ прошлый раз ты говорил: «{mem['log'][-1]}»"
    return (f"С возвращением, {name}! 😊 {now}\n"
            f"Наша встреча №{mem['meetings'] + 1}.{prev}\n"
            f"Скажи «помощь», если забыли, что я умею.")


def main():
    mem = load_mem()
    state = {"riddle": None, "custom_rules": [], "custom_answers": {}, "dict_words": {},
             "ask_name": mem["name"] is None and mem["meetings"] == 0}
    # подхватить локальный словарь, если он был скачан раньше
    try:
        with open(DICT_SAVE, "r", encoding="utf-8") as f:
            apply_dict(state, json.load(f))
    except Exception:
        pass
    watcher = NetWatcher(interval=20)
    state["watcher"] = watcher
    watcher.start()
    print(greet(mem))
    while True:
        try:
            text = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            print(pick(["До связи! Батарейка спит 🔋💤", "Пока! Захочешь поговорить — я тут, офлайн и по-своему живой 🐻"]))
            break
        if re.search(r"^\s*(пока|до свидания|выход|бай|прощай)", text.lower()):
            print(pick(["До связи! Батарейка спит 🔋💤", "Пока! Накорми меня потом фактами: «запомни: ...» 📌"]))
            break
        reply = handle_message(text, mem, state)
        if state.get("ask_name") and not any(re.search(p, text.lower()) for p, _ in RULES):
            words = re.findall(r"[а-яёa-z\-]{2,}", text.lower())
            if 1 <= len(words) <= 2:
                mem["name"] = words[0].capitalize()
                state["ask_name"] = False
                save_mem(mem)
                reply = f"Приятно, {mem['name']}! Запомнил на века (ну, до потери файла 😄) Скажи «помощь» — узнаешь мои умения."
            else:
                reply += "\nА между делом — как тебя зовут?"
        print(reply)
        save_mem(mem)
    watcher.stop()
    mem["meetings"] += 1
    mem["last_seen"] = datetime.now().strftime("%d.%m.%Y %H:%M")
    save_mem(mem)


if __name__ == "__main__":
    main()
