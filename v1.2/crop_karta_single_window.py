#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Jedno-oknová verze nástroje pro tvorbu ID karet.
Náhled ID karty je nyní zobrazen v reálné velikosti šablony.
"""
import os
import json
import cv2
import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext
from PIL import Image, ImageDraw, ImageFont, ImageTk
import numpy as np


def load_json(file_name):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, file_name)
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


CONFIG = load_json("config.json")
DEPARTMENTS = load_json("departments.json")
POSITIONS = load_json("positions.json")
TEMPLATES_JSON = load_json("templates.json")

source_drive   = CONFIG["source_drive"]
output_crop    = CONFIG["output_crop"]
output_idcards = CONFIG["output_idcards"]
template_dir   = CONFIG["template_dir"]
font_path      = CONFIG["font_path"]

TEMPLATES = {category: os.path.join(template_dir, filename)
             for category, filename in TEMPLATES_JSON.items()}


def get_template_for_position(position: str) -> str:
    for category, positions in POSITIONS.items():
        if position in positions:
            if category in TEMPLATES:
                return TEMPLATES[category]
    return next(iter(TEMPLATES.values()))


def crop_face_square(img: np.ndarray) -> np.ndarray | None:
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
    if len(faces) == 0:
        return None
    (x, y, w, h) = faces[0]
    margin_x = int(w * 0.6)
    top_margin_y = int(h * 0.8)
    bottom_margin_y = int(h * 1.3)

    x1 = max(x - margin_x, 0)
    y1 = max(y - top_margin_y, 0)
    x2 = min(x + w + margin_x, img.shape[1])
    y2 = min(y + h + bottom_margin_y, img.shape[0])

    cropped = img[y1:y2, x1:x2]
    ch, cw = cropped.shape[:2]
    side = min(ch, cw)
    start_x = (cw - side) // 2
    start_y = (ch - side) // 2
    cropped_square = cropped[start_y:start_y + side, start_x:start_x + side]
    return cv2.resize(cropped_square, (125, 125), interpolation=cv2.INTER_AREA)


def create_id_card(photo: np.ndarray,
                   name: str,
                   surname: str,
                   department: str,
                   position: str,
                   personal_number: str,
                   template_file: str) -> np.ndarray:
    template = cv2.imread(template_file)
    if template is None:
        raise FileNotFoundError(f"Šablona nenalezena: {template_file}")

    template[55:55+125, 15:15+125] = photo

    upscale = 2
    template_big = cv2.resize(template, (template.shape[1]*upscale, template.shape[0]*upscale), interpolation=cv2.INTER_LINEAR)
    template_pil = Image.fromarray(cv2.cvtColor(template_big, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(template_pil)

    font_big = ImageFont.truetype(font_path, 22*upscale)
    font_small = ImageFont.truetype(font_path, 16*upscale)

    draw.text((15*upscale, 8*upscale), f"{name} {surname}", font=font_big, fill=(0, 0, 0))
    draw.text((15*upscale, 33*upscale), f"{department}", font=font_small, fill=(0, 0, 0))
    draw.text((180*upscale, 70*upscale), f"{position}", font=font_small, fill=(0, 0, 0))
    draw.text((180*upscale, 90*upscale), "Os.č.:", font=font_small, fill=(0, 0, 0))
    draw.text((235*upscale, 90*upscale), f"{personal_number}", font=font_small, fill=(0, 0, 0))

    template_final = template_pil.resize((template.shape[1], template.shape[0]), Image.LANCZOS)
    return cv2.cvtColor(np.array(template_final), cv2.COLOR_RGB2BGR)


class SingleWindowApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("ID Foto – Jedno okno")
        root.geometry("1050x650+120+80")

        self.files: list[str] = []
        self.index: int = -1
        self.current_img_bgr: np.ndarray | None = None
        self.current_crop_bgr: np.ndarray | None = None
        self.tk_preview_card = None

        self._build_layout()

        os.makedirs(output_crop, exist_ok=True)
        os.makedirs(output_idcards, exist_ok=True)
        self.load_files()

    def _build_layout(self):
        self.pw = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        self.pw.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(self.pw, padding=(8, 8))
        self.pw.add(left_frame, weight=1)

        tk.Label(left_frame, text="Soubory ve zdroji", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.listbox = tk.Listbox(left_frame, height=25)
        self.listbox.pack(fill=tk.BOTH, expand=True, pady=(4, 8))
        self.listbox.bind("<<ListboxSelect>>", self.on_select_file)

        btns_left = ttk.Frame(left_frame)
        btns_left.pack(fill=tk.X)
        ttk.Button(btns_left, text="Načíst znovu", command=self.load_files).pack(side=tk.LEFT)
        ttk.Button(btns_left, text="Předchozí", command=self.prev_file).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(btns_left, text="Další", command=self.next_file).pack(side=tk.LEFT, padx=(6, 0))

        mid_frame = ttk.Frame(self.pw, padding=(8, 8))
        self.pw.add(mid_frame, weight=2)

        tk.Label(mid_frame, text="Náhled ID karty", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.lbl_card = tk.Label(mid_frame, relief="groove", bg="#f2f2f2")
        self.lbl_card.pack(pady=(2, 8), expand=True)

        right_frame = ttk.Frame(self.pw, padding=(8, 8))
        self.pw.add(right_frame, weight=1)

        tk.Label(right_frame, text="Údaje", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")

        self.entry_name = ttk.Entry(right_frame)
        self.entry_surname = ttk.Entry(right_frame)
        self.entry_personal = ttk.Entry(right_frame)

        self.combo_department = ttk.Combobox(right_frame, values=DEPARTMENTS, state="readonly")
        if DEPARTMENTS:
            self.combo_department.set(DEPARTMENTS[0])

        self.combo_position_category = ttk.Combobox(right_frame, values=list(POSITIONS.keys()), state="readonly")
        categories = list(POSITIONS.keys())
        if categories:
            self.combo_position_category.set(categories[0])

        self.combo_position = ttk.Combobox(right_frame, state="readonly")
        self.update_positions()

        labels = [
            ("Jméno", self.entry_name),
            ("Příjmení", self.entry_surname),
            ("Oddělení", self.combo_department),
            ("Kategorie pozice", self.combo_position_category),
            ("Pracovní pozice", self.combo_position),
            ("Osobní číslo", self.entry_personal),
        ]
        for i, (text, widget) in enumerate(labels, start=1):
            ttk.Label(right_frame, text=text).grid(row=i, column=0, sticky="e", padx=(0, 6), pady=4)
            widget.grid(row=i, column=1, sticky="we", pady=4)

        right_frame.columnconfigure(1, weight=1)

        self.entry_name.bind("<KeyRelease>", self.update_card_preview)
        self.entry_surname.bind("<KeyRelease>", self.update_card_preview)
        self.entry_personal.bind("<KeyRelease>", self.update_card_preview)
        self.combo_department.bind("<<ComboboxSelected>>", self.update_card_preview)
        self.combo_position.bind("<<ComboboxSelected>>", self.update_card_preview)
        self.combo_position_category.bind("<<ComboboxSelected>>", self.on_category_change)

        btns_right = ttk.Frame(right_frame)
        btns_right.grid(row=len(labels) + 1, column=0, columnspan=2, pady=(10, 0), sticky="we")
        ttk.Button(btns_right, text="Uložit tuto fotku", command=self.save_current).pack(side=tk.LEFT)
        ttk.Button(btns_right, text="Přeskočit", command=self.skip_current).pack(side=tk.LEFT, padx=(6, 0))

        bottom = ttk.Frame(self.root, padding=(8, 4))
        bottom.pack(fill=tk.X)

        self.progress = ttk.Progressbar(bottom, orient="horizontal", mode="determinate")
        self.progress.pack(fill=tk.X)
        self.status_label = ttk.Label(bottom, text="Připraveno", foreground="green")
        self.status_label.pack(anchor="w", pady=(3, 0))

        self.log_box = scrolledtext.ScrolledText(self.root, height=8, state="disabled", font=("Consolas", 10))
        self.log_box.pack(fill=tk.BOTH, expand=False, padx=8, pady=(0, 8))

    def log(self, msg: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.yview("end")
        self.log_box.configure(state="disabled")

    def set_status(self, text: str, color: str = "black"):
        self.status_label.configure(text=text, foreground=color)

    def load_files(self):
        try:
            files = [f for f in os.listdir(source_drive) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
        except FileNotFoundError:
            files = []
        self.files = sorted(files)
        self.listbox.delete(0, tk.END)
        for f in self.files:
            self.listbox.insert(tk.END, f)
        self.progress["maximum"] = len(self.files)
        self.progress["value"] = 0
        self.index = -1
        if self.files:
            self.index = 0
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(0)
            self.listbox.activate(0)
            self.load_current_image()
        self.set_status("Načteno %d souborů" % len(self.files), "blue")

    def on_select_file(self, event=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        self.index = int(sel[0])
        self.load_current_image()

    def prev_file(self):
        if not self.files:
            return
        self.index = (self.index - 1) % len(self.files)
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(self.index)
        self.listbox.activate(self.index)
        self.load_current_image()

    def next_file(self):
        if not self.files:
            return
        self.index = (self.index + 1) % len(self.files)
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(self.index)
        self.listbox.activate(self.index)
        self.load_current_image()

    def load_current_image(self):
        if self.index < 0 or self.index >= len(self.files):
            return
        filename = self.files[self.index]
        full_path = os.path.join(source_drive, filename)
        img = cv2.imread(full_path)
        if img is None:
            self.log(f"[WARN] Nelze načíst: {filename}")
            self.set_status("Chyba načtení", "red")
            self.current_img_bgr = None
            self.current_crop_bgr = None
            self.update_card_preview()
            return
        self.current_img_bgr = img

        crop = crop_face_square(img)
        self.current_crop_bgr = crop
        if crop is None:
            self.log(f"[INFO] Obličej nenalezen: {filename}")
            self.set_status("Obličej nenalezen", "orange")
        else:
            self.set_status("Zpracováno – ořez připraven", "green")
        self.update_card_preview()

    def _to_tk(self, bgr: np.ndarray) -> ImageTk.PhotoImage:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        return ImageTk.PhotoImage(img)

    def on_category_change(self, event=None):
        self.update_positions()
        self.update_card_preview()

    def update_positions(self):
        category = self.combo_position_category.get()
        values = POSITIONS.get(category, [])
        self.combo_position["values"] = values
        if values:
            self.combo_position.set(values[0])
        else:
            self.combo_position.set("")

    def gather_form(self) -> dict:
        return {
            "name": self.entry_name.get().strip(),
            "surname": self.entry_surname.get().strip(),
            "department": self.combo_department.get().strip(),
            "position": self.combo_position.get().strip(),
            "personal_number": self.entry_personal.get().strip(),
        }

    def update_card_preview(self, event=None):
        data = self.gather_form()
        if self.current_crop_bgr is None:
            self.lbl_card.config(image="", text="Bez náhledu")
            self.tk_preview_card = None
            return
        try:
            template_file = get_template_for_position(data["position"])
            card_bgr = create_id_card(self.current_crop_bgr,
                                      data["name"], data["surname"],
                                      data["department"], data["position"], data["personal_number"],
                                      template_file)
            tkimg = self._to_tk(card_bgr)
            self.tk_preview_card = tkimg
            self.lbl_card.config(image=tkimg)
        except Exception as e:
            self.log(f"[Preview error] {e}")

    def save_current(self):
        if self.index < 0 or self.index >= len(self.files):
            return
        if self.current_crop_bgr is None:
            self.log("[SKIP] Ořez neexistuje – nelze uložit.")
            return
        data = self.gather_form()
        filename = self.files[self.index]

        crop_path = os.path.join(output_crop, filename)
        cv2.imwrite(crop_path, self.current_crop_bgr)

        template_file = get_template_for_position(data["position"])
        card_bgr = create_id_card(self.current_crop_bgr,
                                  data["name"], data["surname"],
                                  data["department"], data["position"], data["personal_number"],
                                  template_file)
        card_filename = os.path.splitext(filename)[0] + "_ID.png"
        card_path = os.path.join(output_idcards, card_filename)
        cv2.imwrite(card_path, card_bgr)

        self.log(f"[OK] Uloženo: {filename}")
        self.progress["value"] = min(len(self.files), self.index)
        self.set_status("Uloženo", "green")
        self.next_file()

    def skip_current(self):
        if self.index < 0 or self.index >= len(self.files):
            return
        filename = self.files[self.index]
        self.log(f"[SKIP] Přeskočeno: {filename}")
        self.progress["value"] = min(len(self.files), self.index)
        self.next_file()


if __name__ == "__main__":
    root = tk.Tk()
    app = SingleWindowApp(root)
    root.mainloop()
