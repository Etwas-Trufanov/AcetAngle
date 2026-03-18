"""
AcetAngle Tkinter Client
=========================
GUI-клиент для загрузки рентгеновских снимков, отправки на анализ
и отображения результатов (landmarks, lines, angles) поверх изображения.

Запуск: python client_tkinter.py
Требует: SERVER_URL в .env (напр. http://localhost:8000)
"""

import asyncio
import base64
import io
import json
import math
import os
import sys
import threading
import tkinter as tk
import uuid
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from PIL import Image, ImageTk

from acetAuth import AcetAuth

# ======================================================================
# Главный класс приложения
# ======================================================================


class AcetAngleApp:
    """Основное окно приложения AcetAngle."""

    # Цветовая палитра для оверлеев
    COLOR_LANDMARK = "#4169E1"
    COLOR_LINE = "#FF4444"
    COLOR_ANGLE = "#00FF88"
    COLOR_COXAE_LEFT = "#FF69B4"
    COLOR_COXAE_RIGHT = "#00CED1"
    COLOR_LABEL_BG = "#333333"
    COLOR_CANVAS_BG = "#2b2b2b"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("AcetAngle — Анализ рентгеновских снимков")
        self.root.geometry("1400x900")
        self.root.minsize(1000, 700)

        self.auth = AcetAuth()

        # Состояние изображения
        self.current_image_pil: Optional[Image.Image] = None
        self.current_image_tk: Optional[ImageTk.PhotoImage] = None
        self.current_image_b64: Optional[str] = None
        self.current_filename: Optional[str] = None

        # Масштаб и смещение
        self.scale_factor: float = 1.0
        self.offset_x: int = 0
        self.offset_y: int = 0

        # Оверлеи
        self.overlay_ids: list = []
        self.analysis_result: Optional[dict] = None

        # ============================================================
        # Фоновый event-loop (ОДИН на всё время жизни приложения)
        # ============================================================
        self._async_loop = asyncio.new_event_loop()
        self._async_thread = threading.Thread(
            target=self._start_async_loop, daemon=True
        )
        self._async_thread.start()

        # --- Стили ---
        style = ttk.Style()
        style.configure("Title.TLabel", font=("Helvetica", 22, "bold"))
        style.configure("Header.TLabel", font=("Helvetica", 13, "bold"))
        style.configure("Info.TLabel", font=("Helvetica", 11))
        style.configure("Status.TLabel", font=("Helvetica", 10))

        self._show_login_screen()

    # ==================================================================
    # Фоновый event-loop — запуск и остановка
    # ==================================================================

    def _start_async_loop(self):
        """Запускается в фоновом потоке; крутит loop.run_forever()."""
        asyncio.set_event_loop(self._async_loop)
        self._async_loop.run_forever()

    def _shutdown_async_loop(self):
        """Останавливает фоновый loop (вызывать при выходе из приложения)."""
        self._async_loop.call_soon_threadsafe(self._async_loop.stop)

    # ==================================================================
    # Асинхронный хелпер
    # ==================================================================

    def _run_async(self, coro, on_success=None, on_error=None):
        """
        Планирует корутину в фоновом event-loop и вызывает колбэки в UI-потоке.

        Ключевое отличие от asyncio.run():
        - loop НЕ закрывается после каждого вызова → aiohttp не ругается
        - все корутины работают в одном loop → можно переиспользовать сессии
        """

        def _done_callback(future):
            try:
                result = future.result()
                if on_success:
                    self.root.after(0, lambda r=result: on_success(r))
            except Exception as exc:
                if on_error:
                    self.root.after(0, lambda e=exc: on_error(e))
                else:
                    self.root.after(
                        0, lambda e=exc: messagebox.showerror("Ошибка", str(e))
                    )

        future = asyncio.run_coroutine_threadsafe(coro, self._async_loop)
        future.add_done_callback(_done_callback)

    # ==================================================================
    # Экран входа
    # ==================================================================

    def _show_login_screen(self):
        self._clear_window()

        frame = ttk.Frame(self.root, padding=40)
        frame.place(relx=0.5, rely=0.5, anchor="center")

        ttk.Label(frame, text="🦴 AcetAngle", style="Title.TLabel").grid(
            row=0, column=0, columnspan=2, pady=(0, 25)
        )

        ttk.Label(frame, text="Логин:").grid(
            row=1, column=0, sticky="e", padx=5, pady=5
        )
        self.login_username = ttk.Entry(frame, width=30)
        self.login_username.grid(row=1, column=1, pady=5)

        ttk.Label(frame, text="Пароль:").grid(
            row=2, column=0, sticky="e", padx=5, pady=5
        )
        self.login_password = ttk.Entry(frame, width=30, show="•")
        self.login_password.grid(row=2, column=1, pady=5)

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frame, text="Войти", command=self._do_login, width=15).pack(
            side="left", padx=5
        )
        ttk.Button(
            btn_frame,
            text="Регистрация",
            command=self._show_register_screen,
            width=15,
        ).pack(side="left", padx=5)

        self.login_status = ttk.Label(frame, text="", foreground="red")
        self.login_status.grid(row=4, column=0, columnspan=2)

        self.login_password.bind("<Return>", lambda _: self._do_login())

    def _do_login(self):
        username = self.login_username.get().strip()
        password = self.login_password.get().strip()
        if not username or not password:
            self.login_status.config(text="Введите логин и пароль", foreground="red")
            return

        self.login_status.config(text="Вход…", foreground="blue")
        self._run_async(
            self.auth.auth_by_password(username, password),
            on_success=lambda _: self._show_main_screen(),
            on_error=lambda e: self.login_status.config(text=str(e), foreground="red"),
        )

    # ==================================================================
    # Экран регистрации
    # ==================================================================

    def _show_register_screen(self):
        self._clear_window()

        frame = ttk.Frame(self.root, padding=40)
        frame.place(relx=0.5, rely=0.5, anchor="center")

        ttk.Label(frame, text="Регистрация", style="Title.TLabel").grid(
            row=0, column=0, columnspan=2, pady=(0, 20)
        )

        labels = ["Логин:", "Пароль:", "Имя:", "Фамилия:"]
        keys = ["username", "password", "name", "surname"]
        self._reg = {}
        for i, (lbl, key) in enumerate(zip(labels, keys), start=1):
            ttk.Label(frame, text=lbl).grid(row=i, column=0, sticky="e", padx=5, pady=4)
            show = "•" if key == "password" else ""
            entry = ttk.Entry(frame, width=30, show=show)
            entry.grid(row=i, column=1, pady=4)
            self._reg[key] = entry

        self._reg_doctor = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Я врач", variable=self._reg_doctor).grid(
            row=len(labels) + 1, column=0, columnspan=2, pady=5
        )

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=len(labels) + 2, column=0, columnspan=2, pady=15)
        ttk.Button(
            btn_frame,
            text="Зарегистрироваться",
            command=self._do_register,
            width=20,
        ).pack(side="left", padx=5)
        ttk.Button(
            btn_frame, text="Назад", command=self._show_login_screen, width=10
        ).pack(side="left", padx=5)

        self.reg_status = ttk.Label(frame, text="", foreground="red")
        self.reg_status.grid(row=len(labels) + 3, column=0, columnspan=2)

    def _do_register(self):
        vals = {k: e.get().strip() for k, e in self._reg.items()}
        if not all(vals.values()):
            self.reg_status.config(text="Заполните все поля", foreground="red")
            return
        self.reg_status.config(text="Регистрация…", foreground="blue")
        self._run_async(
            self.auth.register(
                vals["username"],
                vals["password"],
                vals["name"],
                vals["surname"],
                self._reg_doctor.get(),
            ),
            on_success=lambda _: self._show_main_screen(),
            on_error=lambda e: self.reg_status.config(text=str(e), foreground="red"),
        )

    # ==================================================================
    # Главный экран
    # ==================================================================

    def _show_main_screen(self):
        self._clear_window()

        # --- Верхняя панель ---
        top = ttk.Frame(self.root, padding=5)
        top.pack(fill="x")

        ttk.Button(top, text="📁 Загрузить снимок", command=self._load_image).pack(
            side="left", padx=5
        )
        self.analyze_btn = ttk.Button(
            top, text="🔬 Анализировать", command=self._analyze, state="disabled"
        )
        self.analyze_btn.pack(side="left", padx=5)

        self.show_overlay_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            top,
            text="Показать разметку",
            variable=self.show_overlay_var,
            command=self._toggle_overlay,
        ).pack(side="left", padx=10)

        user_text = f"👤 {self.auth.name} {self.auth.surname}"
        if self.auth.isDoctor:
            user_text += " (врач)"
        ttk.Label(top, text=user_text, style="Info.TLabel").pack(side="right", padx=10)
        ttk.Button(top, text="Выход", command=self._logout).pack(side="right", padx=5)

        # --- Поле ввода промпта ---
        prompt_frame = ttk.Frame(self.root, padding=(5, 2))
        prompt_frame.pack(fill="x")
        ttk.Label(prompt_frame, text="Запрос:").pack(side="left", padx=5)
        self.prompt_entry = ttk.Entry(prompt_frame)
        self.prompt_entry.insert(
            0,
            "Проанализируй рентгеновский снимок тазобедренного сустава. "
            "Найди контрольные точки, проведи линии и определи углы для диагностики. Шеечно-диафизарный угол, Линия Хильгенрейнера (горизонтальная), Линия Перкина или Омбредана.",
        )
        self.prompt_entry.pack(side="left", fill="x", expand=True, padx=5)

        # --- Статусная строка ---
        self.status_var = tk.StringVar(value="Готов к работе")
        status_bar = ttk.Label(
            self.root, textvariable=self.status_var, relief="sunken", padding=3
        )
        status_bar.pack(fill="x", side="bottom")

        # --- Основной контент ---
        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=5, pady=5)

        # Канвас (слева)
        left = ttk.LabelFrame(paned, text="Снимок", padding=3)
        paned.add(left, weight=3)

        self.canvas = tk.Canvas(left, bg=self.COLOR_CANVAS_BG, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # Панель результатов (справа)
        right = ttk.LabelFrame(paned, text="Результаты", padding=3)
        paned.add(right, weight=1)

        self._results_canvas = tk.Canvas(right, highlightthickness=0)
        vsb = ttk.Scrollbar(
            right, orient="vertical", command=self._results_canvas.yview
        )
        self.results_frame = ttk.Frame(self._results_canvas)
        self.results_frame.bind(
            "<Configure>",
            lambda _: self._results_canvas.configure(
                scrollregion=self._results_canvas.bbox("all")
            ),
        )
        self._results_canvas.create_window(
            (0, 0), window=self.results_frame, anchor="nw"
        )
        self._results_canvas.configure(yscrollcommand=vsb.set)
        self._results_canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._show_empty_results()

    def _show_empty_results(self):
        for w in self.results_frame.winfo_children():
            w.destroy()
        ttk.Label(
            self.results_frame,
            text="Загрузите снимок и\nнажмите «Анализировать»",
            style="Info.TLabel",
            justify="center",
        ).pack(pady=60, padx=20)

    # ==================================================================
    # Работа с изображением
    # ==================================================================

    def _load_image(self):
        path = filedialog.askopenfilename(
            title="Выберите снимок",
            filetypes=[
                ("Изображения", "*.png *.jpg *.jpeg *.bmp *.tiff *.tif"),
                ("Все файлы", "*.*"),
            ],
        )
        if not path:
            return
        try:
            self.current_image_pil = Image.open(path).convert("RGB")
            self.current_filename = os.path.basename(path)

            buf = io.BytesIO()
            self.current_image_pil.save(buf, format="JPEG", quality=95)
            self.current_image_b64 = base64.b64encode(buf.getvalue()).decode()

            self.analysis_result = None
            self.overlay_ids.clear()
            self._show_empty_results()
            self._display_image()

            self.analyze_btn.config(state="normal")
            w, h = self.current_image_pil.size
            self.status_var.set(f"Загружено: {self.current_filename}  ({w}×{h})")
        except Exception as exc:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл:\n{exc}")

    def _display_image(self):
        if self.current_image_pil is None:
            return

        self.canvas.delete("all")
        self.overlay_ids.clear()

        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 2 or ch < 2:
            self.root.after(50, self._display_image)
            return

        iw, ih = self.current_image_pil.size
        self.scale_factor = min(cw / iw, ch / ih)
        nw = int(iw * self.scale_factor)
        nh = int(ih * self.scale_factor)
        self.offset_x = (cw - nw) // 2
        self.offset_y = (ch - nh) // 2

        resized = self.current_image_pil.resize((nw, nh), Image.LANCZOS)
        self.current_image_tk = ImageTk.PhotoImage(resized)
        self.canvas.create_image(
            self.offset_x,
            self.offset_y,
            anchor="nw",
            image=self.current_image_tk,
            tags="bg",
        )

        if self.analysis_result and self.show_overlay_var.get():
            self._draw_overlays(self.analysis_result)

    def _on_canvas_resize(self, _event):
        if self.current_image_pil:
            self._display_image()

    # ==================================================================
    # Анализ
    # ==================================================================

    def _analyze(self):
        if not self.current_image_b64:
            messagebox.showwarning("Внимание", "Сначала загрузите снимок")
            return

        self.analyze_btn.config(state="disabled")
        self.status_var.set("⏳ Идёт анализ… (может занять до нескольких минут)")

        prompt = self.prompt_entry.get().strip() or "Проанализируй снимок."
        chat_id = f"analysis_{uuid.uuid4().hex[:8]}"

        self._run_async(
            self.auth.send_message(
                message_text=prompt,
                chat_id=chat_id,
                call_type=0,
                filename=self.current_filename or "image.jpg",
                image=self.current_image_b64,
            ),
            on_success=self._on_analysis_ok,
            on_error=self._on_analysis_err,
        )

    def _on_analysis_ok(self, result: dict):
        self.analyze_btn.config(state="normal")
        self.status_var.set("✅ Анализ завершён")

        analysis = result.get("analysis_data")

        if not analysis:
            msg = result.get("message_text", "")
            if isinstance(msg, dict):
                analysis = msg
            elif isinstance(msg, str):
                try:
                    analysis = json.loads(msg)
                except (json.JSONDecodeError, TypeError):
                    pass

        if analysis and isinstance(analysis, dict):
            self.analysis_result = analysis
            self._display_results(analysis)
            self._draw_overlays(analysis)
        else:
            self._show_text_result(result.get("message_text", "Нет данных"))

    def _on_analysis_err(self, err):
        self.analyze_btn.config(state="normal")
        self.status_var.set("❌ Ошибка анализа")
        messagebox.showerror("Ошибка", str(err))

    # ==================================================================
    # Отображение результатов (правая панель)
    # ==================================================================

    def _display_results(self, data: dict):
        for w in self.results_frame.winfo_children():
            w.destroy()

        ttk.Label(self.results_frame, text="📋 Результаты", style="Header.TLabel").pack(
            anchor="w", pady=(5, 10), padx=5
        )

        diagnosis = data.get("type_of_diagnosis", "—")
        self._result_row("Диагноз:", diagnosis)

        confidence = data.get("accurate_diagnosis", "—")
        self._result_row("Уверенность:", str(confidence))

        ttk.Separator(self.results_frame, orient="horizontal").pack(
            fill="x", padx=5, pady=8
        )
        ttk.Label(self.results_frame, text="📝 Описание:", style="Header.TLabel").pack(
            anchor="w", padx=5, pady=(5, 2)
        )
        desc = data.get("description", "—")
        txt = tk.Text(
            self.results_frame,
            wrap="word",
            height=8,
            font=("Helvetica", 10),
            bg="#f5f5f5",
            relief="flat",
            padx=5,
            pady=5,
        )
        txt.insert("1.0", desc)
        txt.config(state="disabled")
        txt.pack(fill="x", padx=10, pady=2)

        if data.get("has_coxae_angulus") and data.get("coxae_angulus"):
            ttk.Separator(self.results_frame, orient="horizontal").pack(
                fill="x", padx=5, pady=8
            )
            ttk.Label(
                self.results_frame, text="📐 Углы (coxae):", style="Header.TLabel"
            ).pack(anchor="w", padx=5, pady=(5, 2))
            for side, label in [("left", "Левый"), ("right", "Правый")]:
                ad = data["coxae_angulus"].get(side, {})
                if ad:
                    self._result_row(f"  {label}:", f"вершина {ad.get('vertex', [])}")

        landmarks = data.get("landmarks", [])
        lines = data.get("lines", [])
        angles = data.get("angles", [])

        ttk.Separator(self.results_frame, orient="horizontal").pack(
            fill="x", padx=5, pady=8
        )
        ttk.Label(self.results_frame, text="📊 Разметка:", style="Header.TLabel").pack(
            anchor="w", padx=5, pady=(5, 2)
        )
        self._result_row("  Точки:", str(len(landmarks)))
        self._result_row("  Линии:", str(len(lines)))
        self._result_row("  Углы:", str(len(angles)))

        if landmarks:
            ttk.Separator(self.results_frame, orient="horizontal").pack(
                fill="x", padx=5, pady=8
            )
            ttk.Label(
                self.results_frame,
                text="🔵 Контрольные точки:",
                style="Header.TLabel",
            ).pack(anchor="w", padx=5, pady=(5, 2))
            for lm in landmarks:
                self._result_row(
                    f"  • {lm.get('label', '?')}",
                    f"({lm.get('x', 0)}, {lm.get('y', 0)})",
                )

        if lines:
            ttk.Separator(self.results_frame, orient="horizontal").pack(
                fill="x", padx=5, pady=8
            )
            ttk.Label(self.results_frame, text="🔴 Линии:", style="Header.TLabel").pack(
                anchor="w", padx=5, pady=(5, 2)
            )
            for ln in lines:
                self._result_row(
                    f"  • {ln.get('label', '?')}",
                    f"{ln.get('start', [])} → {ln.get('end', [])}",
                )

        if angles:
            ttk.Separator(self.results_frame, orient="horizontal").pack(
                fill="x", padx=5, pady=8
            )
            ttk.Label(self.results_frame, text="🟢 Углы:", style="Header.TLabel").pack(
                anchor="w", padx=5, pady=(5, 2)
            )
            for ang in angles:
                self._result_row(f"  • {ang.get('label', '?')}", "")

    def _result_row(self, title: str, value: str):
        f = ttk.Frame(self.results_frame)
        f.pack(anchor="w", fill="x", padx=10, pady=1)
        ttk.Label(
            f, text=title, style="Info.TLabel", font=("Helvetica", 10, "bold")
        ).pack(side="left")
        ttk.Label(f, text=value, style="Info.TLabel", wraplength=300).pack(
            side="left", padx=4
        )

    def _show_text_result(self, text):
        for w in self.results_frame.winfo_children():
            w.destroy()
        ttk.Label(self.results_frame, text="Ответ:", style="Header.TLabel").pack(
            anchor="w", padx=5, pady=5
        )
        t = tk.Text(self.results_frame, wrap="word", height=20, font=("Helvetica", 10))
        t.insert("1.0", str(text))
        t.config(state="disabled")
        t.pack(fill="both", expand=True, padx=5, pady=5)

    # ==================================================================
    # Рисование оверлеев
    # ==================================================================

    def _pt(self, x, y):
        return (
            self.offset_x + x * self.scale_factor,
            self.offset_y + y * self.scale_factor,
        )

    def _add(self, item_id):
        self.overlay_ids.append(item_id)

    def _draw_overlays(self, data: dict):
        for oid in self.overlay_ids:
            self.canvas.delete(oid)
        self.overlay_ids.clear()

        if not self.show_overlay_var.get():
            return

        for line in data.get("lines", []):
            self._draw_line(line)
        for angle in data.get("angles", []):
            self._draw_angle(angle)
        for lm in data.get("landmarks", []):
            self._draw_landmark(lm)

        if data.get("has_coxae_angulus") and data.get("coxae_angulus"):
            coxae = data["coxae_angulus"]
            for side, color in [
                ("left", self.COLOR_COXAE_LEFT),
                ("right", self.COLOR_COXAE_RIGHT),
            ]:
                ad = coxae.get(side)
                if ad and ad.get("vertex"):
                    self._draw_coxae(ad, color, side)

    def _draw_landmark(self, lm: dict):
        x, y = lm.get("x", 0), lm.get("y", 0)
        r = max(lm.get("radius", 5) * self.scale_factor, 3)
        label = lm.get("label", "")
        cx, cy = self._pt(x, y)

        self._add(
            self.canvas.create_oval(
                cx - r,
                cy - r,
                cx + r,
                cy + r,
                fill=self.COLOR_LANDMARK,
                outline="white",
                width=2,
                tags="overlay",
            )
        )
        if label:
            tid = self.canvas.create_text(
                cx + r + 4,
                cy - r - 2,
                text=label,
                fill="white",
                font=("Helvetica", 9, "bold"),
                anchor="sw",
                tags="overlay",
            )
            self._add(tid)
            self._add_label_bg(tid)

    def _draw_line(self, ln: dict):
        s = ln.get("start", [0, 0])
        e = ln.get("end", [0, 0])
        label = ln.get("label", "")
        sx, sy = self._pt(s[0], s[1])
        ex, ey = self._pt(e[0], e[1])

        self._add(
            self.canvas.create_line(
                sx,
                sy,
                ex,
                ey,
                fill=self.COLOR_LINE,
                width=2,
                dash=(6, 3),
                tags="overlay",
            )
        )
        for px, py in [(sx, sy), (ex, ey)]:
            self._add(
                self.canvas.create_oval(
                    px - 3,
                    py - 3,
                    px + 3,
                    py + 3,
                    fill=self.COLOR_LINE,
                    outline="white",
                    width=1,
                    tags="overlay",
                )
            )
        if label:
            mx, my = (sx + ex) / 2, (sy + ey) / 2
            tid = self.canvas.create_text(
                mx,
                my - 10,
                text=label,
                fill="#FFFF00",
                font=("Helvetica", 9),
                tags="overlay",
            )
            self._add(tid)
            self._add_label_bg(tid)

    def _draw_angle(self, ang: dict):
        vertex = ang.get("vertex", [0, 0])
        arm1 = ang.get("arm1", [0, 0])
        arm2 = ang.get("arm2", [0, 0])
        label = ang.get("label", "")

        vx, vy = self._pt(vertex[0], vertex[1])
        a1x, a1y = self._pt(arm1[0], arm1[1])
        a2x, a2y = self._pt(arm2[0], arm2[1])

        for ax, ay in [(a1x, a1y), (a2x, a2y)]:
            self._add(
                self.canvas.create_line(
                    vx,
                    vy,
                    ax,
                    ay,
                    fill=self.COLOR_ANGLE,
                    width=2,
                    tags="overlay",
                )
            )

        arc_r = 25
        deg1 = math.degrees(math.atan2(-(a1y - vy), a1x - vx))
        deg2 = math.degrees(math.atan2(-(a2y - vy), a2x - vx))
        extent = deg2 - deg1
        if extent > 180:
            extent -= 360
        elif extent < -180:
            extent += 360

        self._add(
            self.canvas.create_arc(
                vx - arc_r,
                vy - arc_r,
                vx + arc_r,
                vy + arc_r,
                start=deg1,
                extent=extent,
                outline=self.COLOR_ANGLE,
                width=2,
                style="arc",
                tags="overlay",
            )
        )
        self._add(
            self.canvas.create_oval(
                vx - 4,
                vy - 4,
                vx + 4,
                vy + 4,
                fill=self.COLOR_ANGLE,
                outline="white",
                width=1,
                tags="overlay",
            )
        )
        if label:
            tid = self.canvas.create_text(
                vx + arc_r + 5,
                vy + arc_r + 5,
                text=label,
                fill=self.COLOR_ANGLE,
                font=("Helvetica", 9, "bold"),
                anchor="nw",
                tags="overlay",
            )
            self._add(tid)
            self._add_label_bg(tid)

    def _draw_coxae(self, ad: dict, color: str, side: str):
        vertex = ad.get("vertex", [0, 0])
        arm1 = ad.get("arm1", [0, 0])
        arm2 = ad.get("arm2", [0, 0])

        vx, vy = self._pt(vertex[0], vertex[1])
        a1x, a1y = self._pt(arm1[0], arm1[1])
        a2x, a2y = self._pt(arm2[0], arm2[1])

        for ax, ay in [(a1x, a1y), (a2x, a2y)]:
            self._add(
                self.canvas.create_line(
                    vx,
                    vy,
                    ax,
                    ay,
                    fill=color,
                    width=3,
                    dash=(8, 4),
                    tags="overlay",
                )
            )

        arc_r = 35
        deg1 = math.degrees(math.atan2(-(a1y - vy), a1x - vx))
        deg2 = math.degrees(math.atan2(-(a2y - vy), a2x - vx))
        extent = deg2 - deg1
        if extent > 180:
            extent -= 360
        elif extent < -180:
            extent += 360

        self._add(
            self.canvas.create_arc(
                vx - arc_r,
                vy - arc_r,
                vx + arc_r,
                vy + arc_r,
                start=deg1,
                extent=extent,
                outline=color,
                width=2,
                style="arc",
                tags="overlay",
            )
        )
        tid = self.canvas.create_text(
            vx,
            vy - 18,
            text=f"Coxae ({side})",
            fill=color,
            font=("Helvetica", 10, "bold"),
            tags="overlay",
        )
        self._add(tid)
        self._add_label_bg(tid)

    def _add_label_bg(self, text_id):
        bbox = self.canvas.bbox(text_id)
        if bbox:
            bg = self.canvas.create_rectangle(
                bbox[0] - 2,
                bbox[1] - 1,
                bbox[2] + 2,
                bbox[3] + 1,
                fill=self.COLOR_LABEL_BG,
                outline="",
                tags="overlay",
            )
            self._add(bg)
            self.canvas.tag_raise(text_id, bg)

    def _toggle_overlay(self):
        if self.analysis_result:
            if self.show_overlay_var.get():
                self._draw_overlays(self.analysis_result)
            else:
                for oid in self.overlay_ids:
                    self.canvas.delete(oid)
                self.overlay_ids.clear()

    # ==================================================================
    # Утилиты
    # ==================================================================

    def _clear_window(self):
        for w in self.root.winfo_children():
            w.destroy()

    def _logout(self):
        self.auth = AcetAuth()
        self.current_image_pil = None
        self.current_image_tk = None
        self.current_image_b64 = None
        self.analysis_result = None
        self.overlay_ids.clear()
        self._show_login_screen()


# ======================================================================
# Точка входа
# ======================================================================


def main():
    root = tk.Tk()
    app = AcetAngleApp(root)

    # Корректная остановка фонового loop при закрытии окна
    def on_closing():
        app._shutdown_async_loop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
