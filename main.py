# -*- coding: utf-8 -*-
# ============================================================
#  КАРМАННЫЙ ТОВАРИЩ — чат-интерфейс (Kivy) v0.1
#  Файлы проекта: main.py (этот) + bot_core.py (логика бота v0.5)
#  Сборка: buildozer.spec + .github/workflows/build.yml → APK
# ============================================================
import os, re, json, threading
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.graphics import Color, RoundedRectangle

Window.soft_input_mode = "below_target"   # клавиатура не закрывает поле ввода

import bot_core

BG = (0.078, 0.102, 0.133, 1)      # фон: тёмно-синий
PANEL = (0.11, 0.145, 0.188, 1)    # шапка и панель ввода
ME = (0.23, 0.48, 0.84, 1)         # пузырь моих сообщений
BOT = (0.17, 0.21, 0.26, 1)        # пузырь бота
TEXT = (0.91, 0.93, 0.96, 1)
MUTED = (0.62, 0.68, 0.76, 1)

# Kivy не рисует цветные эмодзи — убираем их из ответов, чтобы не были квадратами
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\u2b50\u2b55\u274c\u2705\u26d4\u2049\u203c\u3030\u303d\u3297\u3299\ufe0f\u200d]"
)


def strip_emoji(s):
    s = EMOJI_RE.sub("", s)
    return re.sub(r" {2,}", " ", s).strip()


def rounded(widget, color, radius=12):
    """Просто фон со скруглением для любого виджета."""
    with widget.canvas.before:
        Color(*color)
        widget._bg = RoundedRectangle(radius=[dp(radius)], pos=widget.pos, size=widget.size)
    widget.bind(pos=lambda i, v: setattr(widget._bg, "pos", v),
                size=lambda i, v: setattr(widget._bg, "size", v))


class Bubble(Label):
    def __init__(self, text, mine=False, system=False, **kw):
        super().__init__(**kw)
        self.mine, self.system = mine, system
        self.markup = False
        self.halign = "center" if system else ("right" if mine else "left")
        self.valign = "middle"
        self.size_hint_y = None
        self.padding = [dp(12), dp(9)]
        self.font_size = sp(15)
        self.color = MUTED if system else TEXT
        self.text = strip_emoji(text)
        self._bg_color = MUTED[:3] + (0.14,) if system else (ME if mine else BOT)
        rounded(self, self._bg_color, radius=16)
        self.bind(texture_size=self._upd_h, width=self._upd_tw)
        self._upd_h()

    def _upd_tw(self, *a):
        self.text_size = (self.width - dp(24), None)

    def _upd_h(self, *a):
        self.height = max(dp(42), self.texture_size[1] + dp(18))


class ChatApp(App):
    title = "Карманный Товарищ"

    def build(self):
        Window.clearcolor = BG
        self.mem = bot_core.load_mem()
        self.state = {"riddle": None, "custom_rules": [], "custom_answers": {},
                      "dict_words": {},
                      "ask_name": self.mem["name"] is None and self.mem["meetings"] == 0}
        try:
            with open(bot_core.DICT_SAVE, "r", encoding="utf-8") as f:
                bot_core.apply_dict(self.state, json.load(f))
        except Exception:
            pass

        root = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))

        # --- шапка ---
        head = BoxLayout(size_hint_y=None, height=dp(48), padding=[dp(12), 0], spacing=dp(8))
        rounded(head, PANEL)
        head.add_widget(Label(text="Карманный Товарищ", bold=True, font_size=sp(17),
                              color=TEXT, size_hint_x=1))
        self.net_label = Label(text="…", font_size=sp(13), color=MUTED, size_hint_x=None,
                               width=dp(90), halign="right")
        self.net_label.bind(size=lambda i, s: setattr(i, "text_size", s))
        head.add_widget(self.net_label)
        root.add_widget(head)

        # --- лента сообщений ---
        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(2))
        self.grid = GridLayout(cols=1, size_hint_y=None, spacing=dp(8), padding=[dp(2), dp(6)])
        self.grid.bind(minimum_height=self.grid.setter("height"))
        self.scroll.add_widget(self.grid)
        root.add_widget(self.scroll)

        # --- панель ввода ---
        bar = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(8))
        rounded(bar, PANEL)
        self.inp = TextInput(multiline=False, hint_text="Напиши что-нибудь…",
                             font_size=sp(15), foreground_color=TEXT,
                             background_color=BG, cursor_color=ACCENT,
                             padding=[dp(14), dp(14), dp(10), dp(14)])
        self.inp.bind(on_text_validate=self.send)
        bar.add_widget(self.inp)
        btn = Button(text="OK", font_size=sp(16), bold=True, size_hint_x=None, width=dp(64),
                     background_normal="", background_down="",
                     background_color=ME, color=TEXT)
        btn.bind(on_press=self.send)
        bar.add_widget(btn)
        root.add_widget(bar)

        # --- старт: приветствие и сторож сети ---
        self.watcher = bot_core.NetWatcher(interval=20, notify=self.on_net_event)
        self.state["watcher"] = self.watcher
        self.watcher.start()
        Clock.schedule_interval(self.tick_status, 5)
        Clock.schedule_once(lambda dt: self.add_bubble(bot_core.greet(self.mem)), 0.1)
        return root

    # ---------- сообщения ----------

    def add_bubble(self, text, mine=False, system=False):
        b = Bubble(text, mine=mine, system=system)
        row = BoxLayout(size_hint_y=None, height=b.height, spacing=dp(4))
        if system:
            row.add_widget(b)
        elif mine:
            row.add_widget(Widget(size_hint_x=0.2))
            row.add_widget(b)
        else:
            row.add_widget(b)
            row.add_widget(Widget(size_hint_x=0.2))
        b.bind(height=row.setter("height"))
        self.grid.add_widget(row)
        Clock.schedule_once(self.scroll_end, 0.05)

    def scroll_end(self, *a):
        self.scroll.scroll_y = 0

    def on_net_event(self, kind, t):
        msg = bot_core.NET_UP if kind == "up" else bot_core.NET_DOWN
        line = strip_emoji(__import__("random").choice(msg).format(t=t))
        Clock.schedule_once(lambda dt: self.add_bubble(line, system=True), 0)
        self.tick_status(0)

    def tick_status(self, dt):
        s = self.state["watcher"].state if self.state.get("watcher") else None
        self.net_label.text = "…" if s is None else ("сеть есть" if s else "офлайн")

    def send(self, *a):
        text = self.inp.text.strip()
        if not text:
            return
        self.inp.text = ""
        self.inp.focus = True
        self.add_bubble(text, mine=True)
        threading.Thread(target=self.worker, args=(text,), daemon=True).start()

    def worker(self, text):
        reply = bot_core.handle_message(text, self.mem, self.state)
        # знакомство с именем (как в консольной версии)
        if self.state.get("ask_name") and not any(re.search(p, text.lower()) for p, _ in bot_core.RULES):
            words = re.findall(r"[а-яёa-z\-]{2,}", text.lower())
            if 1 <= len(words) <= 2:
                self.mem["name"] = words[0].capitalize()
                self.state["ask_name"] = False
                bot_core.save_mem(self.mem)
                reply = f"Приятно, {self.mem['name']}! Запомнил на века. Скажи «помощь» — узнаешь мои умения."
            else:
                reply += "\nА между делом — как тебя зовут?"
        bot_core.save_mem(self.mem)
        Clock.schedule_once(lambda dt: self.add_bubble(reply), 0)

    def on_stop(self):
        try:
            self.watcher.stop()
        except Exception:
            pass
        self.mem["meetings"] += 1
        from datetime import datetime
        self.mem["last_seen"] = datetime.now().strftime("%d.%m.%Y %H:%M")
        bot_core.save_mem(self.mem)


if __name__ == "__main__":
    ChatApp().run()
