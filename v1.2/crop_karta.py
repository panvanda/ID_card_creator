#! /usr/bin/env python
import cv2
import os
import tkinter as tk
from tkinter import scrolledtext
from tkinter import ttk
from threading import Thread
from PIL import Image, ImageDraw, ImageFont, ImageTk
import numpy as np
import os, json

def load_json(file_name):
    base_dir = os.path.dirname(os.path.abspath(__file__))  # složka se skriptem
    file_path = os.path.join(base_dir, file_name)
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


# === Načtení konfigurace ===
CONFIG = load_json("config.json")
DEPARTMENTS = load_json("departments.json")
POSITIONS = load_json("positions.json")
TEMPLATES_JSON = load_json("templates.json")

# === Cesty ===
source_drive = CONFIG["source_drive"]
output_crop = CONFIG["output_crop"]
output_idcards = CONFIG["output_idcards"]
template_dir = CONFIG["template_dir"]
font_path = CONFIG["font_path"]

# === TEMPLATES s plnými cestami ===
TEMPLATES = {category: os.path.join(template_dir, filename)
             for category, filename in TEMPLATES_JSON.items()}

def get_template_for_position(position):
    for category, positions in POSITIONS.items():
        if position in positions:
            return TEMPLATES.get(category, list(TEMPLATES.values())[0])
    return list(TEMPLATES.values())[0]

# === Ořez obličeje ===
def crop_face_square(img):
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

# === Vytvoření ID karty ===
def create_id_card(photo, name, surname, department, position, personal_number, template_file):
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

# === Okno pro zadání údajů s náhledem ===
class DataEntryWindow(tk.Toplevel):
    def __init__(self, master, cropped_img, on_submit):
        super().__init__(master)
        self.cropped_img = cropped_img
        self.on_submit = on_submit
        self.title("Údaje pro ID kartu")

        main_x, main_y, main_w = master.winfo_x(), master.winfo_y(), master.winfo_width()
        self.geometry(f"700x300+{main_x + main_w + 20}+{main_y}")

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        # formulář vlevo
        form_frame = tk.Frame(self)
        form_frame.grid(row=0, column=0, padx=12, pady=12, sticky="n")

        self.entry_name = tk.Entry(form_frame)
        self.entry_surname = tk.Entry(form_frame)
        self.entry_personal = tk.Entry(form_frame)

        self.combo_department = ttk.Combobox(form_frame, values=DEPARTMENTS, state="readonly")
        self.combo_department.set(DEPARTMENTS[0])

        self.combo_position_category = ttk.Combobox(form_frame, values=list(POSITIONS.keys()), state="readonly")
        self.combo_position_category.bind("<<ComboboxSelected>>", self.update_positions)
        self.combo_position_category.set(list(POSITIONS.keys())[0])

        self.combo_position = ttk.Combobox(form_frame, state="readonly")
        self.update_positions()

        rows = [
            ("Jméno", self.entry_name),
            ("Příjmení", self.entry_surname),
            ("Oddělení", self.combo_department),
            ("Kategorie pozice", self.combo_position_category),
            ("Pracovní pozice", self.combo_position),
            ("Osobní číslo", self.entry_personal),
        ]
        for i, (label_text, widget) in enumerate(rows):
            tk.Label(form_frame, text=label_text).grid(row=i, column=0, sticky="e", padx=(0, 6), pady=3)
            widget.grid(row=i, column=1, pady=3)

        btns = tk.Frame(form_frame)
        btns.grid(row=len(rows), column=0, columnspan=2, pady=(10, 0))
        tk.Button(btns, text="Uložit a pokračovat", command=self.submit).pack(side="left", padx=(0, 6))
        tk.Button(btns, text="Přeskočit fotku", command=self.skip).pack(side="left")

        # náhled vpravo
        self.preview_label = tk.Label(self)
        self.preview_label.grid(row=0, column=1, padx=12, pady=12, sticky="n")

        # bindowání
        self.entry_name.bind("<KeyRelease>", self.update_preview)
        self.entry_surname.bind("<KeyRelease>", self.update_preview)
        self.entry_personal.bind("<KeyRelease>", self.update_preview)
        self.combo_department.bind("<<ComboboxSelected>>", self.update_preview)
        self.combo_position.bind("<<ComboboxSelected>>", self.update_preview)

        self.entry_name.focus_set()
        self.update_preview()

    def update_positions(self, event=None):
        category = self.combo_position_category.get()
        if category in POSITIONS:
            self.combo_position["values"] = POSITIONS[category]
            self.combo_position.set(POSITIONS[category][0])
        self.update_preview()

    def update_preview(self, event=None):
        name = self.entry_name.get().strip()
        surname = self.entry_surname.get().strip()
        department = self.combo_department.get().strip()
        position = self.combo_position.get().strip()
        personal_number = self.entry_personal.get().strip()
        template_file = get_template_for_position(position)

        try:
            card_img = create_id_card(self.cropped_img, name, surname, department, position, personal_number, template_file)
            card_rgb = cv2.cvtColor(card_img, cv2.COLOR_BGR2RGB)
            pil_preview = Image.fromarray(card_rgb)
            pil_preview = pil_preview.resize((300, 190))
            self.tk_preview = ImageTk.PhotoImage(pil_preview)
            self.preview_label.config(image=self.tk_preview)
        except Exception as e:
            print("Preview error:", e)

    def submit(self):
        data = {
            "name": self.entry_name.get().strip(),
            "surname": self.entry_surname.get().strip(),
            "department": self.combo_department.get().strip(),
            "position": self.combo_position.get().strip(),
            "personal_number": self.entry_personal.get().strip(),
        }
        self.on_submit(data)
        self.destroy()

    def skip(self):
        self.on_submit(None)
        self.destroy()

# === Hlavní GUI ===
class CropApp:
    def __init__(self, root):
        self.root = root
        root.title("ID Foto - Zpracování")
        root.geometry("500x500+100+100")

        self.text = scrolledtext.ScrolledText(root, state='disabled', font=('Consolas', 10))
        self.text.pack(expand=True, fill='both', padx=10, pady=(10, 0))

        # progress bar
        self.progress = ttk.Progressbar(root, orient="horizontal", mode="determinate", length=400)
        self.progress.pack(pady=8)

        # status bar
        self.status_label = tk.Label(root, text="Připraveno", fg="green", font=("Segoe UI", 11))
        self.status_label.pack(pady=(0, 10))

        bottom_frame = tk.Frame(root)
        bottom_frame.pack(fill='x', pady=10)
        self.button = tk.Button(bottom_frame, text="Zavřít", command=root.destroy)
        self.button.pack(pady=5)

        thread = Thread(target=self.run_processing, daemon=True)
        thread.start()

    def log(self, message):
        self.text.config(state='normal')
        self.text.insert('end', message + '\n')
        self.text.yview('end')
        self.text.config(state='disabled')

    def set_status(self, text, color, font=("Segoe UI", 11)):
        self.status_label.config(text=text, fg=color, font=font)

    def run_processing(self):
        try:
            self.process_images()
        except Exception as e:
            self.set_status("Chyba", "red")
            self.log(f"[CHYBA] {e}")

    def process_images(self):
        os.makedirs(output_crop, exist_ok=True)
        os.makedirs(output_idcards, exist_ok=True)

        files = [f for f in os.listdir(source_drive) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
        total = len(files)
        self.progress["maximum"] = total

        for i, filename in enumerate(files, 1):
            self.set_status("Zpracovávám…", "blue")
            full_src = os.path.join(source_drive, filename)
            img = cv2.imread(full_src)
            if img is None:
                self.log(f"[WARN] Nelze načíst: {filename}")
                continue
            cropped = crop_face_square(img)
            if cropped is None:
                self.log(f"[INFO] Obličej nenalezen: {filename}")
                continue

            result_ready = {"data": None}
            def on_submit(data): result_ready["data"] = data
            self.root.after(0, lambda: DataEntryWindow(self.root, cropped, on_submit))
            self.root.wait_window(self.root.winfo_children()[-1])
            data = result_ready["data"]

            if data is None:
                self.log(f"[SKIP] Přeskočeno: {filename}")
                continue

            crop_path = os.path.join(output_crop, filename)
            cv2.imwrite(crop_path, cropped)
            template_file = get_template_for_position(data["position"])
            id_card = create_id_card(
                cropped, data["name"], data["surname"],
                data["department"], data["position"], data["personal_number"],
                template_file
            )
            card_filename = os.path.splitext(filename)[0] + "_ID.png"
            card_path = os.path.join(output_idcards, card_filename)
            cv2.imwrite(card_path, id_card)
            self.log(f"[OK] Zpracováno: {filename}")

            self.progress["value"] = i

        # finální stav
        self.set_status("Všechny fotky zpracovány", "green", font=("Segoe UI", 11, "bold"))

# === Spuštění ===
if __name__ == "__main__":
    root = tk.Tk()
    app = CropApp(root)
    root.mainloop()
