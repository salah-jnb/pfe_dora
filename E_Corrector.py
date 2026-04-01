import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import cv2
import pandas as pd
import os
import glob
import time
import datetime
import shutil
import sys
import copy
from PIL import Image, ImageTk

# High DPI Fix
try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except:
    pass

# =========================================================
# CONFIGURATION
# =========================================================
class Config:
    """
    Centralizes all global settings, colors, and classes for the annotation tool.
    Why: Allows quick adjustments to the UI and target classes without modifying core logic.
    """
    APP_TITLE = "Corrector"
    CLASSES = ['person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck']
    
    BG_COLOR = "#1e1e1e"
    FG_COLOR = "white"
    
    BOX_CURR = "#00ffff"       # Cyan for current frame
    BOX_SEL_COLOR = "#ff00ff"  # Magenta (Violet) for selected box
    BOX_PREV = "#ff9900"       # Orange for previous frame
    
    BTN_ACCEPT_BG = "#C8E6C9"  
    BTN_REJECT_BG = "#FFCDD2"  
    BTN_NAV_BG    = "#E0E0E0"  
    BTN_ACTION_BG = "#BBDEFB"  
    BTN_WARN_BG   = "#FFF9C4"  
    BTN_PREDICT   = "#D1C4E9"  
    
    FONT_BOLD = ("Segoe UI", 10, "bold")
    EXTENSIONS = ('.jpg', '.jpeg', '.png')

# =========================================================
# HELPER LOGIC
# =========================================================
def log_to_file(filepath, message):
    """Logs session events with timestamps."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "a", encoding='utf-8') as f:
            if "\n" in message: f.write(f"{message}\n")
            else: f.write(f"[{timestamp}] {message}\n")
    except: pass

def transfer_logs(src_dir, dst_dir):
    """Copies log files to maintain a continuous tracking history."""
    try:
        os.makedirs(dst_dir, exist_ok=True)
        logs = glob.glob(os.path.join(src_dir, "*.txt"))
        for log in logs:
            dst_path = os.path.join(dst_dir, os.path.basename(log))
            shutil.copy2(log, dst_path)
    except: pass

# =========================================================
# 1. LAUNCHER
# =========================================================
class LauncherGUI:
    """
    Initial configuration window to select input and output directories.
    Why: Dynamically scans for available video segments and their processing status before loading the heavy editor.
    """
    def __init__(self, root):
        self.root = root
        self.root.title(Config.APP_TITLE)
        self.root.geometry("850x650")
        
        default_in = r"C:\Daten\AA-Bachlorarbeit\Anno\Videos\F_GroundTruth"
        default_out = r"C:\Daten\AA-Bachlorarbeit\Anno\Videos\F_GroundTruth"
        
        self.input_dir = tk.StringVar(value=default_in)
        self.output_dir = tk.StringVar(value=default_out)
        self.setup_ui()
        self.refresh_list()

    def setup_ui(self):
        main = ttk.Frame(self.root, padding=20)
        main.pack(fill=tk.BOTH, expand=True)
        ttk.Label(main, text=Config.APP_TITLE, font=("Segoe UI", 16, "bold")).pack(pady=(0, 20))

        p_frame = ttk.LabelFrame(main, text="Directories", padding=10)
        p_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(p_frame, text="Input Dir (From Auto Annotator):").pack(anchor=tk.W)
        r1 = ttk.Frame(p_frame); r1.pack(fill=tk.X, pady=2)
        ttk.Entry(r1, textvariable=self.input_dir).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(r1, text="Browse...", width=10, command=lambda: self.browse(self.input_dir, refresh=True)).pack(side=tk.RIGHT)
        
        ttk.Label(p_frame, text="Output Dir (Final Results):").pack(anchor=tk.W, pady=(5, 0))
        r2 = ttk.Frame(p_frame); r2.pack(fill=tk.X, pady=2)
        ttk.Entry(r2, textvariable=self.output_dir).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(r2, text="Browse...", width=10, command=lambda: self.browse(self.output_dir)).pack(side=tk.RIGHT)

        l_frame = ttk.LabelFrame(main, text="Available Segments", padding=10)
        l_frame.pack(fill=tk.BOTH, expand=True)
        
        self.listbox = tk.Listbox(l_frame, font=("Consolas", 10), selectmode=tk.SINGLE, height=15)
        scroll = ttk.Scrollbar(l_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.bind("<Double-Button-1>", self.on_select)

        ttk.Button(main, text="START EDITING SELECTED", command=self.on_select).pack(fill=tk.X, ipady=10, pady=10)

    def browse(self, var, refresh=False):
        d = filedialog.askdirectory()
        if d: 
            var.set(d)
            if refresh: self.refresh_list()

    def refresh_list(self):
        self.listbox.delete(0, tk.END)
        self.folder_map = {}
        base = self.input_dir.get(); out_base = self.output_dir.get()
        if not os.path.exists(base): return

        try:
            subdirs = [f.path for f in os.scandir(base) if f.is_dir()]
            subdirs.sort()
            for p in subdirs:
                name = os.path.basename(p)
                final_csv = os.path.join(out_base, name, "trajectories", f"{name}_corrected.csv")
                status = "[DONE]" if os.path.exists(final_csv) else "[TODO]"
                display = f"{status}  {name}"
                self.folder_map[display] = p
                idx = self.listbox.size()
                self.listbox.insert(tk.END, display)
                self.listbox.itemconfig(idx, {'fg': 'green' if "[DONE]" in display else 'red'})
        except Exception as e: print(f"Error scanning: {e}")

    def on_select(self, event=None):
        sel = self.listbox.curselection()
        if not sel: return
        name = self.listbox.get(sel[0])
        src_path = self.folder_map[name]
        self.root.withdraw()
        self.start_editor(src_path)

    def start_editor(self, src_folder):
        vid_name = os.path.basename(src_folder)
        src_traj_dir = os.path.join(src_folder, "trajectories")
        
        img_dir = os.path.join(src_folder, "raw_frames")
        if not os.path.exists(img_dir): img_dir = os.path.join(src_folder, "annotated_frames")
        
        dst_base = self.output_dir.get()
        dst_folder = os.path.join(dst_base, vid_name)
        dst_traj_dir = os.path.join(dst_folder, "trajectories")
        os.makedirs(dst_traj_dir, exist_ok=True)
        
        # 1. Fetch logs from the segment folder
        transfer_logs(src_folder, dst_folder)
        
        # 2. Fetch global logs (experiment_log.txt, etc.) from the parent directory
        src_parent = os.path.dirname(src_folder)
        transfer_logs(src_parent, dst_base)

        csv_corrected = os.path.join(dst_traj_dir, f"{vid_name}_corrected.csv")
        csv_original_copy = os.path.join(dst_traj_dir, f"{vid_name}_original.csv")
        
        csv_to_load = None
        if os.path.exists(csv_corrected):
            csv_to_load = csv_corrected
        else:
            src_csvs = glob.glob(os.path.join(src_traj_dir, "*.csv"))
            if not src_csvs:
                messagebox.showerror("Error", "No trajectory CSV found in input source!")
                self.root.deiconify(); return
            
            src_csv = src_csvs[0]
            # If source and destination are identical, load directly to avoid SameFileError.
            if os.path.abspath(src_csv) == os.path.abspath(csv_original_copy):
                csv_to_load = src_csv
            else:
                shutil.copy2(src_csv, csv_original_copy)
                csv_to_load = csv_original_copy 

        log_file = os.path.join(dst_folder, f"{vid_name}_correction_log.txt")

        ed_root = tk.Toplevel(self.root)
        try: from ctypes import windll; windll.shcore.SetProcessDpiAwareness(1)
        except: pass
        
        def on_close():
            ed_root.destroy()
            self.refresh_list()
            self.root.deiconify()

        AnnotationEditor(ed_root, csv_to_load, img_dir, csv_corrected, log_file, on_close)

# =========================================================
# 2. EDITOR GUI
# =========================================================
class AnnotationEditor:
    """
    The main correction interface for visual inspection and modification of bounding boxes.
    Why: Replaces manual JSON/CSV editing with a visual, intuitive drag-and-drop workflow to establish Ground Truth.
    """
    def __init__(self, root, csv_in, img_dir, csv_out, log, callback):
        self.root = root
        self.callback = callback
        self.img_dir = img_dir
        self.csv_out = csv_out
        self.log = log
        
        self.script_name = os.path.basename(sys.argv[0])
        self.start_time = time.time()
        
        self.stats = {
            'added': 0, 'deleted_global': 0, 'deleted_local': 0,
            'cleared_frames': 0, 'class_changed': 0, 'merged': 0, 'renamed': 0
        }
        self.modified_frames = set()
        
        self.dead_ids = set()
        self._is_syncing = False # Prevents infinite loops when syncing tables
        
        self.write_session_header(csv_in)

        self.root.title(f"{Config.APP_TITLE} | Editing: {os.path.basename(csv_in)}")
        self.root.geometry("1600x900")
        self.root.configure(bg=Config.BG_COLOR)
        
        try:
            self.df = pd.read_csv(csv_in)
            if 'id' in self.df.columns: self.df['id'] = self.df['id'].fillna(-1).astype(int)
            self.enforce_unique_ids()
        except Exception as e:
            messagebox.showerror("Error", f"Could not load CSV:\n{e}")
            self.callback(); return
        
        if not os.path.exists(img_dir):
            messagebox.showerror("Error", f"Image directory not found: {img_dir}")
            self.callback(); return
            
        self.frame_files = sorted([f for f in os.listdir(img_dir) if f.lower().endswith(Config.EXTENSIONS)])
        
        if not self.frame_files:
            messagebox.showerror("Error", "No Images (JPG/PNG) found in input folder!")
            self.callback(); return

        self.curr_idx = 0
        self.scale = 1.0; self.ox = 0; self.oy = 0
        self.orig_size = (0,0)
        
        self.drawing = False
        self.start_xy = (0,0)
        self.draw_mode_id = None 
        self.drag_mode = None
        self.selected_id = None
        self.drag_orig_box = None
        self.right_click_moved = False 
        
        self.tk_img_curr = None
        self.tk_img_prev = None
        
        self.show_prev_frame = False
        
        self.setup_ui()
        self.load_frame()
        self.root.protocol("WM_DELETE_WINDOW", self.on_quit_ask)

    def enforce_unique_ids(self):
        """Removes duplicate bounding boxes for the same ID in a single frame to prevent data corruption."""
        original_count = len(self.df)
        self.df = self.df.drop_duplicates(subset=['frame', 'id'], keep='last')
        cleaned_count = len(self.df)
        if original_count != cleaned_count:
            print(f"Cleaned up {original_count - cleaned_count} duplicate boxes.")

    def write_session_header(self, source_file):
        sep = "="*60
        header = f"\n{sep}\nCORRECTION SESSION START\n{sep}\n• Script:      {self.script_name}\n• Date:        {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n• Base File:   {os.path.basename(source_file)}\n{sep}\n"
        log_to_file(self.log, header)

    def setup_ui(self):
        h = tk.Frame(self.root, bg=Config.BG_COLOR, pady=5); h.pack(fill=tk.X)
        self.lbl_info = tk.Label(h, text="Loading...", font=("Segoe UI", 14, "bold"), bg=Config.BG_COLOR, fg="white")
        self.lbl_info.pack(side=tk.LEFT, padx=10)
        
        tk.Button(h, text="TOGGLE DUAL-VIEW (V)", font=("Consolas", 10, "bold"), bg="#555555", fg="white", command=self.toggle_dual_view).pack(side=tk.LEFT, padx=10)
        tk.Button(h, text="PREDICT VECTOR (O)", font=("Consolas", 10, "bold"), bg=Config.BTN_PREDICT, fg="black", command=self.predict_vector).pack(side=tk.LEFT, padx=20)
        tk.Button(h, text="UNDO (STRG+Z)", font=("Consolas", 10, "bold"), bg="#ffeb3b", fg="black", command=self.act_undo).pack(side=tk.LEFT, padx=0)
        
        self.lbl_mode = tk.Label(h, text="MODE: SELECT / NEW OBJECT", font=("Consolas", 12, "bold"), bg="#333333", fg="#00ff00", padx=10)
        self.lbl_mode.pack(side=tk.RIGHT, padx=10)

        content = tk.Frame(self.root, bg=Config.BG_COLOR); content.pack(fill=tk.BOTH, expand=True)
        
        f_left_container = tk.Frame(content, bg=Config.BG_COLOR, width=220)
        f_left_container.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        f_left_container.pack_propagate(False) 
        f_left = tk.LabelFrame(f_left_container, text="GLOBAL IDs (All Frames)", bg=Config.BG_COLOR, fg="white", font=Config.FONT_BOLD)
        f_left.pack(fill=tk.BOTH, expand=True)
        
        self.tree_global = ttk.Treeview(f_left, columns=('ID', 'Class'), show='headings')
        self.tree_global.heading('ID', text='ID'); self.tree_global.column('ID', width=40, anchor='center')
        self.tree_global.heading('Class', text='Class'); self.tree_global.column('Class', width=100)
        self.tree_global.pack(fill=tk.BOTH, expand=True)
        self.tree_global.bind("<Button-3>", self.menu_global)
        self.tree_global.bind("<ButtonRelease-1>", self.on_global_select)
        
        tk.Button(f_left, text="+ NEW ID MODE", bg=Config.BTN_ACTION_BG, font=Config.FONT_BOLD, command=self.set_mode_new).pack(fill=tk.X, pady=5)

        self.canv_container = tk.Frame(content, bg=Config.BG_COLOR)
        self.canv_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.canv_prev = tk.Canvas(self.canv_container, bg="#111", highlightthickness=1, highlightbackground="#555")
        self.canv_prev.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        tk.Label(self.canv_prev, text="PREVIOUS FRAME", bg="black", fg="orange").place(x=5, y=5)

        self.canv_curr = tk.Canvas(self.canv_container, bg="#000", highlightthickness=2, highlightbackground="#00ffff")
        self.canv_curr.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        tk.Label(self.canv_curr, text="CURRENT FRAME (EDIT)", bg="black", fg="cyan").place(x=5, y=5)
        
        self.canv_curr.bind("<Button-1>", self.on_left_down)
        self.canv_curr.bind("<B1-Motion>", self.on_left_drag)
        self.canv_curr.bind("<ButtonRelease-1>", self.on_left_up)
        
        self.canv_curr.bind("<Button-3>", self.on_right_down)
        self.canv_curr.bind("<B3-Motion>", self.on_right_drag)
        self.canv_curr.bind("<ButtonRelease-3>", self.on_right_up)
        
        self.canv_prev.pack_forget()

        f_right_container = tk.Frame(content, bg=Config.BG_COLOR, width=200)
        f_right_container.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)
        f_right_container.pack_propagate(False)
        
        f_right_bot = tk.LabelFrame(f_right_container, text="MISSING (From Prev Frame)", bg=Config.BG_COLOR, fg="#ff5252", font=Config.FONT_BOLD)
        f_right_bot.pack(side=tk.BOTTOM, fill=tk.X, expand=False, pady=(2, 0))
        
        self.tree_missing = ttk.Treeview(f_right_bot, columns=('ID', 'Class'), show='headings', height=2)
        self.tree_missing.heading('ID', text='ID'); self.tree_missing.column('ID', width=40, anchor='center')
        self.tree_missing.heading('Class', text='Class'); self.tree_missing.column('Class', width=100)
        self.tree_missing.pack(fill=tk.BOTH, expand=True)
        self.tree_missing.bind("<Button-3>", self.menu_missing)
        self.tree_missing.bind("<ButtonRelease-1>", self.on_missing_select)

        f_right_top = tk.LabelFrame(f_right_container, text="LOCAL IDs (Current)", bg=Config.BG_COLOR, fg="white", font=Config.FONT_BOLD)
        f_right_top.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 2))
        
        self.tree_local = ttk.Treeview(f_right_top, columns=('ID', 'Class'), show='headings')
        self.tree_local.heading('ID', text='ID'); self.tree_local.column('ID', width=40, anchor='center')
        self.tree_local.heading('Class', text='Class'); self.tree_local.column('Class', width=100)
        self.tree_local.tag_configure('new', foreground='#00ff00')
        
        scroll_local = ttk.Scrollbar(f_right_top, orient=tk.VERTICAL, command=self.tree_local.yview)
        self.tree_local.configure(yscrollcommand=scroll_local.set)
        scroll_local.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_local.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.tree_local.bind("<Button-3>", self.menu_local)
        self.tree_local.bind("<ButtonRelease-1>", self.on_local_select)

        ft = tk.Frame(self.root, bg=Config.BG_COLOR, pady=10); ft.pack(fill=tk.X, side=tk.BOTTOM)
        for i in range(9): ft.columnconfigure(i, weight=1)
        cfg = {'height': 2, 'font': Config.FONT_BOLD, 'bd': 0}

        tk.Button(ft, text="|<< FIRST", bg=Config.BTN_NAV_BG, command=self.nav_first, **cfg).grid(row=0, column=0, sticky="ew", padx=2)
        tk.Button(ft, text="< PREV", bg=Config.BTN_NAV_BG, command=self.nav_prev, **cfg).grid(row=0, column=1, sticky="ew", padx=2)
        tk.Button(ft, text="NEXT >", bg=Config.BTN_NAV_BG, command=self.nav_next, **cfg).grid(row=0, column=2, sticky="ew", padx=2)
        tk.Button(ft, text="LAST >>|", bg=Config.BTN_NAV_BG, command=self.nav_last, **cfg).grid(row=0, column=3, sticky="ew", padx=2)
        
        tk.Frame(ft, bg=Config.BG_COLOR, width=30).grid(row=0, column=4)
        
        tk.Button(ft, text="REJECT FRAME (D)", bg=Config.BTN_REJECT_BG, command=self.act_reject, **cfg).grid(row=0, column=5, sticky="ew", padx=5)
        tk.Button(ft, text="ACCEPT FRAME (A)", bg=Config.BTN_ACCEPT_BG, command=self.act_accept, **cfg).grid(row=0, column=6, sticky="ew", padx=5)
        tk.Button(ft, text="SAVE & EXPORT FRAMES", bg=Config.BTN_ACTION_BG, command=self.act_save, **cfg).grid(row=0, column=7, sticky="ew", padx=10)
        tk.Button(ft, text="QUIT", bg=Config.BTN_WARN_BG, command=self.on_quit_ask, **cfg).grid(row=0, column=8, sticky="ew", padx=2)

        self.root.bind("<v>", lambda e: self.toggle_dual_view())
        self.root.bind("<a>", lambda e: self.act_accept())
        self.root.bind("<d>", lambda e: self.act_reject())
        self.root.bind("<o>", lambda e: self.predict_vector()) 
        self.root.bind("<k>", lambda e: self.act_kill_id()) 
        self.root.bind("<Delete>", lambda e: self.act_del_local(self.selected_id) if self.selected_id is not None else None)
        self.root.bind("<Left>", lambda e: self.nav_prev())
        self.root.bind("<Right>", lambda e: self.nav_next())
        self.root.bind("<Control-z>", lambda e: self.act_undo())
        
        self.root.bind("<Configure>", self.on_resize)
        self._resize_timer = None

    def is_validated(self):
        if self.df.empty: return False
        return not self.df[self.df['frame'] == self.curr_frame_num].empty

    def toggle_dual_view(self):
        self.show_prev_frame = not self.show_prev_frame
        if self.show_prev_frame:
            self.canv_prev.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, before=self.canv_curr)
        else:
            self.canv_prev.pack_forget()
        self.draw_canvases()

    def on_resize(self, event):
        if self._resize_timer is not None:
            self.root.after_cancel(self._resize_timer)
        self._resize_timer = self.root.after(100, self.draw_canvases)

    def load_frame(self):
        if not self.frame_files: return
        fname = self.frame_files[self.curr_idx]
        
        try: self.curr_frame_num = int(fname.split('_')[1].split('.')[0])
        except: self.curr_frame_num = self.curr_idx
        
        status = " [VALIDATED]" if self.is_validated() else ""
        self.lbl_info.config(text=f"Frame {self.curr_frame_num} ({self.curr_idx+1}/{len(self.frame_files)}){status}")
        
        self.draw_canvases()
        self.update_tables()

    def draw_canvases(self):
        if not self.frame_files: return
        
        curr_fname = self.frame_files[self.curr_idx]
        curr_path = os.path.join(self.img_dir, curr_fname)
        img_curr = cv2.imread(curr_path)
        if img_curr is not None:
            self.orig_size = (img_curr.shape[1], img_curr.shape[0])
            self.render_image(self.canv_curr, img_curr, self.curr_frame_num, is_active=True)

        if self.show_prev_frame:
            if self.curr_idx > 0:
                prev_fname = self.frame_files[self.curr_idx - 1]
                prev_path = os.path.join(self.img_dir, prev_fname)
                try: prev_fnum = int(prev_fname.split('_')[1].split('.')[0])
                except: prev_fnum = self.curr_idx - 1
                
                img_prev = cv2.imread(prev_path)
                if img_prev is not None:
                    self.render_image(self.canv_prev, img_prev, prev_fnum, is_active=False)
            else:
                self.canv_prev.delete("all")
                self.canv_prev.create_text(250, 250, text="START OF VIDEO", fill="grey", font=("Arial", 20))

    def render_image(self, canvas, img_bgr, frame_num, is_active):
        h, w = img_bgr.shape[:2]
        cw, ch = canvas.winfo_width(), canvas.winfo_height()
        if cw < 10: cw, ch = 600, 500
        
        scale = min(cw/w, ch/h)
        ox = (cw - w*scale)//2
        oy = (ch - h*scale)//2
        
        if is_active:
            self.scale = scale; self.ox = ox; self.oy = oy
            
        img_rs = cv2.resize(img_bgr, (int(w*scale), int(h*scale)))
        tk_img = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(img_rs, cv2.COLOR_BGR2RGB)))
        
        canvas.delete("all")
        canvas.create_image(cw//2, ch//2, anchor=tk.CENTER, image=tk_img)
        
        if is_active: self.tk_img_curr = tk_img
        else: self.tk_img_prev = tk_img
        
        self.enforce_unique_ids()
        
        data = self.df[self.df['frame'] == frame_num]
        for _, row in data.iterrows():
            x, y, bw, bh = row['x'], row['y'], row['w'], row['h']
            sx, sy = int(x*scale)+ox, int(y*scale)+oy
            sw, sh = int(bw*scale), int(bh*scale)
            oid = int(row['id'])
            
            if is_active:
                col = Config.BOX_SEL_COLOR if oid == self.selected_id else Config.BOX_CURR
                line_w = 3 if oid == self.selected_id else 2
            else:
                col = Config.BOX_PREV
                line_w = 2
                
            canvas.create_rectangle(sx, sy, sx+sw, sy+sh, outline=col, width=line_w, tags="overlay")
            label = f"{row['class']} {oid}"
            canvas.create_text(sx+2, max(sy-10, 10), text=label, fill=col, anchor=tk.SW, font=("Arial", 10, "bold"), tags="overlay")

    def _sync_tree_selection(self):
        """Highlights the currently selected ID in all three tables without triggering loops."""
        if self.selected_id is None: return
        self._is_syncing = True
        for tree in (self.tree_global, self.tree_local, self.tree_missing):
            for child in tree.get_children():
                if int(tree.item(child)['values'][0]) == self.selected_id:
                    tree.selection_set(child)
                    tree.see(child)
                else:
                    tree.selection_remove(child)
        self._is_syncing = False

    def update_tables(self):
        self.enforce_unique_ids()
        
        # Global
        for i in self.tree_global.get_children(): self.tree_global.delete(i)
        uniq = self.df[['id', 'class']].drop_duplicates().sort_values('id')
        for _, r in uniq.iterrows():
            self.tree_global.insert("", tk.END, values=(r['id'], r['class']))
        
        # Detect new IDs for Green Highlighting
        prev_ids = set()
        if self.curr_idx > 0:
            try: prev_fnum = int(self.frame_files[self.curr_idx - 1].split('_')[1].split('.')[0])
            except: prev_fnum = self.curr_idx - 1
            prev_ids = set(self.df[self.df['frame'] == prev_fnum]['id'].unique())

        # Local
        for i in self.tree_local.get_children(): self.tree_local.delete(i)
        loc = self.df[self.df['frame'] == self.curr_frame_num].sort_values('id')
        curr_ids = set()
        for _, r in loc.iterrows():
            oid = r['id']
            tag = ('new',) if oid not in prev_ids else ()
            self.tree_local.insert("", tk.END, values=(oid, r['class']), tags=tag)
            curr_ids.add(oid)
            
        # Missing
        for i in self.tree_missing.get_children(): self.tree_missing.delete(i)
        missing_count = 0
        if self.curr_idx > 0:
            try: prev_fnum = int(self.frame_files[self.curr_idx - 1].split('_')[1].split('.')[0])
            except: prev_fnum = self.curr_idx - 1
            
            prev_data = self.df[self.df['frame'] == prev_fnum].sort_values('id')
            for _, r in prev_data.iterrows():
                oid = r['id']
                if oid not in curr_ids and oid not in self.dead_ids:
                    self.tree_missing.insert("", tk.END, values=(oid, r['class']))
                    missing_count += 1
                    
        new_height = max(2, min(missing_count, 12))
        self.tree_missing.config(height=new_height)
        
        # Make sure our new highlights stay intact after refresh
        self._sync_tree_selection()

    def get_img_coords(self, x, y):
        ix = max(0, min((x - self.ox) / self.scale, self.orig_size[0]))
        iy = max(0, min((y - self.oy) / self.scale, self.orig_size[1]))
        return ix, iy

    def find_hit(self, x, y):
        ix, iy = self.get_img_coords(x, y)
        loc_df = self.df[self.df['frame'] == self.curr_frame_num]
        sorted_rows = loc_df.assign(area=loc_df['w']*loc_df['h']).sort_values('area')
        for _, r in sorted_rows.iterrows():
            if r['x'] <= ix <= r['x']+r['w'] and r['y'] <= iy <= r['y']+r['h']:
                return r
        return None

    # --- LEFT CLICK = CREATE NEW BOX ---
    def on_left_down(self, e):
        self.canv_curr.focus_set()
        self.drag_start_screen = (e.x, e.y)
        self.drag_mode = 'create'

    def on_left_drag(self, e):
        if self.drag_mode == 'create':
            self.canv_curr.delete("temp")
            self.canv_curr.create_rectangle(self.drag_start_screen[0], self.drag_start_screen[1], e.x, e.y, outline="magenta", dash=(2,2), tags="temp")

    def on_left_up(self, e):
        if self.drag_mode == 'create':
            self.canv_curr.delete("temp")
            x1, y1 = self.get_img_coords(self.drag_start_screen[0], self.drag_start_screen[1])
            x2, y2 = self.get_img_coords(e.x, e.y)
            rx1, ry1 = min(x1,x2), min(y1,y2)
            rw, rh = abs(x2-x1), abs(y2-y1)
            
            if rw < 5 or rh < 5: 
                self.drag_mode = None
                return

            def on_class_select(selected_cls):
                target_id = None
                if self.draw_mode_id is not None:
                    target_id = self.draw_mode_id
                    self.df = self.df[~((self.df['frame'] == self.curr_frame_num) & (self.df['id'] == target_id))]
                else:
                    max_id = self.df['id'].max() if not self.df.empty else 0
                    target_id = max_id + 1

                new_row = {
                    'frame': self.curr_frame_num, 'class': selected_cls, 'id': target_id,
                    'x': rx1, 'y': ry1, 'w': rw, 'h': rh,
                    'x_center': rx1+rw/2, 'y_center': ry1+rh/2
                }
                self.df = pd.concat([self.df, pd.DataFrame([new_row])], ignore_index=True)
                self.stats['added'] += 1
                self.modified_frames.add(self.curr_frame_num)
                self.selected_id = target_id
                
                # Instantly switch tracking mode to the newly drawn ID
                self.draw_mode_id = target_id
                self.lbl_mode.config(text=f"MODE: RE-DRAW ID {target_id} ({selected_cls})", fg="#ff9900")
                self._sync_tree_selection()
                
                self.load_frame()

            if self.draw_mode_id is not None:
                cls_series = self.df[self.df['id'] == self.draw_mode_id]['class']
                on_class_select(cls_series.iloc[0] if not cls_series.empty else "car")
            else:
                self.open_class_picker(e.x_root, e.y_root, on_class_select)
        
        self.drag_mode = None

    # --- RIGHT CLICK = MOVE BOX, STICKY SELECT, OR MENU ---
    def on_right_down(self, e):
        self.canv_curr.focus_set()
        hit = self.find_hit(e.x, e.y)
        self.drag_start_screen = (e.x, e.y)
        self.right_click_moved = False
        
        if hit is not None:
            self.selected_id = int(hit['id'])
            
            # THE STICKY FEATURE: Set the drawing mode to the clicked ID instantly
            self.draw_mode_id = self.selected_id
            self.lbl_mode.config(text=f"MODE: RE-DRAW ID {self.draw_mode_id} ({hit['class']})", fg="#ff9900")
            
            # Sync the table highlights
            self._sync_tree_selection()

            self.drag_mode = 'move'
            self.drag_orig_box = (hit['x'], hit['y'], hit['w'], hit['h'])
            self.draw_canvases() # Refresh canvas without reloading tables to prevent UI freezes
        else:
            self.drag_mode = None

    def on_right_drag(self, e):
        if self.drag_mode == 'move' and self.selected_id is not None:
            self.right_click_moved = True 
            dx_img = (e.x - self.drag_start_screen[0]) / self.scale
            dy_img = (e.y - self.drag_start_screen[1]) / self.scale
            
            idx = self.df[(self.df['frame'] == self.curr_frame_num) & (self.df['id'] == self.selected_id)].index
            if not idx.empty:
                new_x = max(0, min(self.drag_orig_box[0] + dx_img, self.orig_size[0] - self.drag_orig_box[2]))
                new_y = max(0, min(self.drag_orig_box[1] + dy_img, self.orig_size[1] - self.drag_orig_box[3]))
                
                self.df.loc[idx, 'x'] = new_x
                self.df.loc[idx, 'y'] = new_y
                self.df.loc[idx, 'x_center'] = new_x + self.drag_orig_box[2]/2
                self.df.loc[idx, 'y_center'] = new_y + self.drag_orig_box[3]/2
            
            self.draw_canvases() # Refresh canvas without reloading tables to prevent UI freezes

    def on_right_up(self, e):
        if self.drag_mode == 'move':
            self.modified_frames.add(self.curr_frame_num)
            self.update_tables() # Update tables only once the drag is complete
        
        if not self.right_click_moved and self.selected_id is not None:
            self.menu_all(e, self.selected_id)
            
        self.drag_mode = None

    def open_class_picker(self, x, y, callback):
        win = tk.Toplevel(self.root)
        win.overrideredirect(True); win.attributes('-topmost', True)
        
        tk.Label(win, text="Select Class:", bg="#333", fg="white").pack(fill=tk.X)
        frame = tk.Frame(win); frame.pack()
        row, col = 0, 0
        for c in Config.CLASSES:
            tk.Button(frame, text=c.upper(), width=10, command=lambda _c=c: [callback(_c), win.destroy()]).grid(row=row, column=col, padx=2, pady=2)
            col += 1
            if col > 1: col=0; row+=1
            
        win.update_idletasks()
        if x + win.winfo_width() > self.root.winfo_screenwidth(): x -= win.winfo_width()
        if y + win.winfo_height() > self.root.winfo_screenheight(): y -= win.winfo_height()
        win.geometry(f"+{x}+{y}")
        tk.Button(win, text="CANCEL", bg="#ffcccc", command=win.destroy).pack(fill=tk.X)

    def set_mode_new(self):
        self.draw_mode_id = None
        for item in self.tree_global.selection(): self.tree_global.selection_remove(item)
        for item in self.tree_missing.selection(): self.tree_missing.selection_remove(item)
        self.lbl_mode.config(text="MODE: NEW OBJECT", fg="#00ff00")

    def on_global_select(self, event):
        sel = self.tree_global.selection()
        if sel:
            val = self.tree_global.item(sel[0])['values']
            new_id = int(val[0])
            
            self.selected_id = new_id
            self.draw_mode_id = self.selected_id
            cls = val[1]
            self.lbl_mode.config(text=f"MODE: RE-DRAW ID {self.draw_mode_id} ({cls})", fg="#00aaff")
            self._sync_tree_selection()
            self.load_frame()

    def on_local_select(self, event):
        sel = self.tree_local.selection()
        if sel:
            val = self.tree_local.item(sel[0])['values']
            new_id = int(val[0])
            
            self.selected_id = new_id
            self.draw_mode_id = self.selected_id 
            cls = val[1]
            self.lbl_mode.config(text=f"MODE: RE-DRAW ID {self.draw_mode_id} ({cls})", fg="#ff9900")
            self._sync_tree_selection()
            self.load_frame()
            
    def on_missing_select(self, event):
        sel = self.tree_missing.selection()
        if not sel: return
        val = self.tree_missing.item(sel[0])['values']
        target_id = int(val[0])
        target_class = val[1]
        
        if self.curr_idx > 0:
            try: prev_fnum = int(self.frame_files[self.curr_idx - 1].split('_')[1].split('.')[0])
            except: prev_fnum = self.curr_idx - 1
            
            older_df = self.df[(self.df['frame'] == prev_fnum) & (self.df['id'] == target_id)]
            if not older_df.empty:
                last_row = older_df.iloc[-1] 
                nx, ny, nw, nh = last_row['x'], last_row['y'], last_row['w'], last_row['h']
                
                if self.curr_idx > 1:
                    try: last_last_fnum = int(self.frame_files[self.curr_idx - 2].split('_')[1].split('.')[0])
                    except: last_last_fnum = self.curr_idx - 2
                    
                    ll_df = self.df[(self.df['frame'] == last_last_fnum) & (self.df['id'] == target_id)]
                    if not ll_df.empty:
                        ll_row = ll_df.iloc[-1]
                        dt_hist = prev_fnum - last_last_fnum
                        if dt_hist == 0: dt_hist = 1
                        dt_pred = self.curr_frame_num - prev_fnum
                        
                        vx = (nx - ll_row['x']) / dt_hist
                        vy = (ny - ll_row['y']) / dt_hist
                        
                        vx = max(-100, min(100, vx))
                        vy = max(-100, min(100, vy))
                        
                        nx += vx * dt_pred
                        ny += vy * dt_pred
                
                nx = max(0, min(nx, self.orig_size[0] - nw))
                ny = max(0, min(ny, self.orig_size[1] - nh))
                
                new_row = {
                    'frame': self.curr_frame_num, 'class': target_class, 'id': target_id,
                    'x': nx, 'y': ny, 'w': nw, 'h': nh,
                    'x_center': nx+nw/2, 'y_center': ny+nh/2
                }
                self.df = pd.concat([self.df, pd.DataFrame([new_row])], ignore_index=True)
                self.stats['added'] += 1
                self.modified_frames.add(self.curr_frame_num)
                
                self.selected_id = target_id
                self.draw_mode_id = target_id
                self.lbl_mode.config(text=f"MODE: DRAW ID {self.draw_mode_id} ({target_class})", fg="#00aaff")
                self._sync_tree_selection()
                
                log_to_file(self.log, f"AUTO-PASTED missing ID {target_id} from frame {prev_fnum}")
                self.load_frame()

    def predict_vector(self):
        """
        Calculates motion vectors from previous frames and projects boxes into the current frame.
        Why: Massively accelerates annotation by auto-filling missing detections based on object inertia.
        """
        if self.curr_idx == 0: return
        
        try: prev_fnum = int(self.frame_files[self.curr_idx - 1].split('_')[1].split('.')[0])
        except: prev_fnum = self.curr_idx - 1
        
        last_last_fnum = None
        if self.curr_idx > 1:
            try: last_last_fnum = int(self.frame_files[self.curr_idx - 2].split('_')[1].split('.')[0])
            except: last_last_fnum = self.curr_idx - 2
        
        curr_data = self.df[self.df['frame'] == self.curr_frame_num]
        prev_data = self.df[self.df['frame'] == prev_fnum]
        
        dt_pred = self.curr_frame_num - prev_fnum
        if dt_pred == 0: dt_pred = 1 
        
        count = 0
        new_rows = []
        
        for _, obj_last in prev_data.iterrows():
            oid = obj_last['id']
            if oid in self.dead_ids: continue
            if not curr_data[curr_data['id'] == oid].empty: continue 
            
            nx, ny, nw, nh = obj_last['x'], obj_last['y'], obj_last['w'], obj_last['h']
            
            if last_last_fnum is not None:
                obj_older = self.df[(self.df['frame'] == last_last_fnum) & (self.df['id'] == oid)]
                if not obj_older.empty:
                    r_older = obj_older.iloc[-1]
                    dt_hist = prev_fnum - last_last_fnum
                    if dt_hist == 0: dt_hist = 1
                    
                    vx = (obj_last['x'] - r_older['x']) / dt_hist
                    vy = (obj_last['y'] - r_older['y']) / dt_hist
                    
                    vx = max(-100, min(100, vx))
                    vy = max(-100, min(100, vy))
                    
                    nx += vx * dt_pred
                    ny += vy * dt_pred
            
            nx = max(0, min(nx, self.orig_size[0] - nw))
            ny = max(0, min(ny, self.orig_size[1] - nh))
            
            new_rows.append({
                'frame': self.curr_frame_num, 'class': obj_last['class'], 'id': oid,
                'x': nx, 'y': ny, 'w': nw, 'h': nh,
                'x_center': nx+nw/2, 'y_center': ny+nh/2
            })
            count += 1
            
        if new_rows:
            self.df = pd.concat([self.df, pd.DataFrame(new_rows)], ignore_index=True)
            self.stats['added'] += count
            self.modified_frames.add(self.curr_frame_num)
            log_to_file(self.log, f"PREDICTED {count} objects on frame {self.curr_frame_num}")
            self.load_frame()

    def menu_canvas(self, e):
        hit = self.find_hit(e.x, e.y)
        if hit is not None:
            self.selected_id = int(hit['id'])
            self.load_frame() 
            self.menu_all(e, self.selected_id)

    def menu_global(self, event):
        item = self.tree_global.identify_row(event.y)
        if not item: return
        self.tree_global.selection_set(item)
        vals = self.tree_global.item(item)['values']
        gid, gcls = int(vals[0]), vals[1]
        self.menu_all(event, gid, is_global=True)

    def menu_local(self, event):
        item = self.tree_local.identify_row(event.y)
        if not item: return
        self.tree_local.selection_set(item)
        vals = self.tree_local.item(item)['values']
        self.selected_id = int(vals[0])
        self.load_frame()
        self.menu_all(event, self.selected_id, is_global=False)

    def menu_missing(self, event):
        item = self.tree_missing.identify_row(event.y)
        if not item: return
        vals = self.tree_missing.item(item)['values']
        gid = int(vals[0])
        self.menu_all(event, gid, is_global=True)

    def menu_all(self, e, lid, is_global=False):
        m = tk.Menu(self.root, tearoff=0)
        
        # 4. PULLBACK FEATURE
        m.add_command(label="PULLBACK (Copy to Previous Frame)", foreground="blue", command=lambda: self.act_pullback(lid))
        m.add_separator()
        
        m.add_command(label="MANAGE / MERGE...", command=lambda: self.act_manage_id(lid))
        m.add_command(label="CHANGE CLASS", command=lambda: self.act_change_class(lid))
        m.add_separator()
        m.add_command(label="DELETE (Frame)", command=lambda: self.act_del_local(lid))
        m.add_command(label="DELETE (Global)", foreground="red", command=lambda: self.act_del_global(lid))
        m.add_separator()
        
        # 3. STATIONARY & EXITED
        m.add_command(label="STATIONARY (Apply to All Frames)", foreground="orange", command=lambda: self.act_stationary(lid))
        m.add_command(label="MARK AS EXITED (K)", foreground="orange", command=lambda: self.act_kill_id(lid))
        
        mx, my = e.x_root, e.y_root
        if mx + 150 > self.root.winfo_screenwidth(): mx -= 150
        m.tk_popup(mx, my)

    def act_stationary(self, oid):
        """
        Applies the current bounding box to all frames in the segment.
        Why: Extremely efficient for fixing static objects (like parked cars) across the entire video.
        """
        self.df_backup = self.df.copy() # Create backup for Undo functionality
        curr_df = self.df[(self.df['frame'] == self.curr_frame_num) & (self.df['id'] == oid)]
        if curr_df.empty: return
        row = curr_df.iloc[-1].copy()

        all_frames = []
        for fname in self.frame_files:
            try: fnum = int(fname.split('_')[1].split('.')[0])
            except: continue
            all_frames.append(fnum)

        self.df = self.df[self.df['id'] != oid]

        new_rows = []
        for fnum in all_frames:
            new_row = row.copy()
            new_row['frame'] = fnum
            new_rows.append(new_row)

        self.df = pd.concat([self.df, pd.DataFrame(new_rows)], ignore_index=True)
        self.modified_frames.update(all_frames)
        self.stats['added'] += len(all_frames)
        log_to_file(self.log, f"STATIONARY applied to ID {oid} across all {len(all_frames)} frames")
        self.load_frame()

    def act_pullback(self, oid):
        """
        Uses reverse vector calculation to project an object into the previous frame.
        Why: Solves early-frame tracking failures by pulling successful later-frame detections backwards.
        """
        if self.curr_idx == 0: return

        try: prev_fnum = int(self.frame_files[self.curr_idx - 1].split('_')[1].split('.')[0])
        except: prev_fnum = self.curr_idx - 1

        curr_df = self.df[(self.df['frame'] == self.curr_frame_num) & (self.df['id'] == oid)]
        if curr_df.empty: return
        row = curr_df.iloc[-1].copy()
        
        nx, ny, nw, nh = row['x'], row['y'], row['w'], row['h']
        
        future_df = self.df[(self.df['frame'] > self.curr_frame_num) & (self.df['id'] == oid)].sort_values('frame')
        past_df = self.df[(self.df['frame'] < prev_fnum) & (self.df['id'] == oid)].sort_values('frame')
        
        vx, vy = 0.0, 0.0
        
        if not future_df.empty:
            next_row = future_df.iloc[0]
            dt = next_row['frame'] - self.curr_frame_num
            if dt != 0:
                vx = (next_row['x'] - row['x']) / dt
                vy = (next_row['y'] - row['y']) / dt
                
        elif not past_df.empty:
            past_row = past_df.iloc[-1]
            dt = self.curr_frame_num - past_row['frame']
            if dt != 0:
                vx = (row['x'] - past_row['x']) / dt
                vy = (row['y'] - past_row['y']) / dt
                
        vx = max(-100.0, min(100.0, float(vx)))
        vy = max(-100.0, min(100.0, float(vy)))
        
        dt_pullback = self.curr_frame_num - prev_fnum
        if dt_pullback == 0: dt_pullback = 1
        
        nx -= vx * dt_pullback
        ny -= vy * dt_pullback
        
        nx = max(0, min(nx, self.orig_size[0] - nw))
        ny = max(0, min(ny, self.orig_size[1] - nh))
        
        row['x'] = nx
        row['y'] = ny
        row['x_center'] = nx + nw / 2
        row['y_center'] = ny + nh / 2
        row['frame'] = prev_fnum

        self.df = self.df[~((self.df['frame'] == prev_fnum) & (self.df['id'] == oid))]

        self.df = pd.concat([self.df, pd.DataFrame([row])], ignore_index=True)
        self.modified_frames.add(prev_fnum)
        self.stats['added'] += 1
        log_to_file(self.log, f"SMART PULLBACK applied ID {oid} to prev frame {prev_fnum} (Vector: vx={vx:.1f}, vy={vy:.1f})")
        self.load_frame()

    def act_manage_id(self, current_id):
        x, y = self.root.winfo_pointerx(), self.root.winfo_pointery()
        win = tk.Toplevel(self.root)
        win.title(f"Merge ID {current_id} into...")
        if x + 250 > self.root.winfo_screenwidth(): x -= 250
        win.geometry(f"250x350+{x}+{y}")
        
        tree = ttk.Treeview(win, columns=('ID', 'Class'), show='headings')
        tree.heading('ID', text='ID'); tree.column('ID', width=50, anchor='center')
        tree.heading('Class', text='Class'); tree.column('Class', width=100)
        
        scroll = ttk.Scrollbar(win, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        
        tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        uniq = self.df[self.df['id'] != current_id][['id', 'class']].drop_duplicates().sort_values('id')
        for _, r in uniq.iterrows():
            tree.insert("", tk.END, values=(r['id'], r['class']))
            
        def do_merge():
            sel = tree.selection()
            if not sel: return
            tid = int(tree.item(sel[0])['values'][0])
            t_cls = tree.item(sel[0])['values'][1]
            
            self.df.loc[self.df['id'] == current_id, 'class'] = t_cls
            self.df.loc[self.df['id'] == current_id, 'id'] = tid
            self.stats['merged'] += 1
            log_to_file(self.log, f"MERGED {current_id} -> {tid}")
            win.destroy(); self.load_frame()
            
        ttk.Button(win, text="MERGE SELECTED", command=do_merge).pack(fill=tk.X, pady=2)
        
        def do_new():
            max_id = self.df['id'].max() if not self.df.empty else 0
            new_id = max_id + 1
            self.df.loc[self.df['id'] == current_id, 'id'] = new_id
            self.stats['renamed'] += 1
            win.destroy(); self.load_frame()
            
        tk.Button(win, text="CREATE NEW ID (Auto)", bg="#C8E6C9", command=do_new).pack(fill=tk.X, pady=5)

    def act_change_class(self, oid):
        win = tk.Toplevel(self.root)
        win.title("Select Class")
        def set_c(c):
            self.df.loc[self.df['id'] == oid, 'class'] = c
            self.stats['class_changed'] += 1
            log_to_file(self.log, f"CHANGED CLASS ID {oid} to {c}")
            win.destroy()
            self.load_frame()
        for c in Config.CLASSES:
            ttk.Button(win, text=c, command=lambda x=c: set_c(x)).pack(fill=tk.X)

    def act_del_global(self, oid):
        if messagebox.askyesno("Confirm", f"Delete ID {oid} EVERYWHERE?"):
            self.df = self.df[self.df['id'] != oid]
            self.stats['deleted_global'] += 1
            log_to_file(self.log, f"DELETED GLOBAL {oid}")
            self.load_frame()

    def act_del_local(self, oid):
        if oid is None: return
        self.df = self.df[~((self.df['frame'] == self.curr_frame_num) & (self.df['id'] == oid))]
        self.stats['deleted_local'] += 1
        self.modified_frames.add(self.curr_frame_num)
        self.load_frame()
        
    def act_kill_id(self, oid=None):
        if oid is None: oid = self.selected_id
        if oid is None: return
        
        self.dead_ids.add(oid)
        self.df = self.df[~((self.df['frame'] >= self.curr_frame_num) & (self.df['id'] == oid))]
        self.stats['deleted_local'] += 1
        self.modified_frames.add(self.curr_frame_num)
        log_to_file(self.log, f"ID {oid} marked as EXITED (Removed from current & future frames)")
        self.load_frame()

    # --- NAVIGATION ---
    def nav_first(self): self.curr_idx = 0; self.load_frame()
    
    def act_undo(self):
        if hasattr(self, 'df_backup') and self.df_backup is not None:
            self.df = self.df_backup.copy()
            self.df_backup = None # Consume the backup
            log_to_file(self.log, "UNDO: Reverted last major action (e.g. Stationary)")
            self.load_frame()
            messagebox.showinfo("Undo", "Action successfully reverted!")
        else:
            messagebox.showwarning("Undo", "There is currently nothing to undo.")
            
    def nav_prev(self): 
        if self.curr_idx > 0: self.curr_idx -= 1; self.load_frame()
    def nav_next(self): 
        if self.curr_idx < len(self.frame_files)-1: self.curr_idx += 1; self.load_frame()
    def nav_last(self): self.curr_idx = len(self.frame_files)-1; self.load_frame()

    def act_accept(self): 
        self.nav_next()
        
    def act_reject(self):
        self.df = self.df[self.df['frame'] != self.curr_frame_num]
        self.stats['cleared_frames'] += 1
        self.modified_frames.add(self.curr_frame_num)
        log_to_file(self.log, f"CLEARED FRAME {self.curr_frame_num}")
        self.load_frame()

    def act_save(self):
        self.enforce_unique_ids() 
        self.df.to_csv(self.csv_out, index=False)
        
        # --- EXPORT FINAL FRAMES & LOGS ---
        export_dir = os.path.join(os.path.dirname(self.csv_out), "..", "annotated_frames")
        os.makedirs(export_dir, exist_ok=True)
        
        base_vid_folder = os.path.dirname(os.path.dirname(self.csv_out))
        transfer_logs(base_vid_folder, export_dir)
        
        export_win = tk.Toplevel(self.root)
        export_win.title("Exporting Frames")
        export_win.geometry("350x120")
        tk.Label(export_win, text="Drawing final boxes on images...\nPlease wait a moment.", font=("Arial", 12), pady=20).pack()
        self.root.update()
        
        for fname in self.frame_files:
            try: fnum = int(fname.split('_')[1].split('.')[0])
            except: continue
            
            img_path = os.path.join(self.img_dir, fname)
            img = cv2.imread(img_path)
            if img is None: continue
            
            data = self.df[self.df['frame'] == fnum]
            for _, row in data.iterrows():
                x, y, w, h = int(row['x']), int(row['y']), int(row['w']), int(row['h'])
                oid = int(row['id'])
                cname = row['class']
                
                cv2.rectangle(img, (x, y), (x+w, y+h), (0, 255, 255), 2)
                cv2.putText(img, f"{cname} {oid}", (x, max(y-5, 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            
            out_path = os.path.join(export_dir, fname)
            cv2.imwrite(out_path, img)
            
        export_win.destroy()

        duration = time.time() - self.start_time
        sep = "="*60
        summary = f"""
{sep}
Video correction DATA SUMMARY
{sep}
• Duration:         {int(duration//60)}m {int(duration%60)}s
• Unique Frames:    {len(self.modified_frames)} modified
• New Objects:      {self.stats['added']} (False Negatives fixed)
• Deleted IDs:      {self.stats['deleted_global']} (Global Tracks)
• Deleted Objects:  {self.stats['deleted_local']} (Single Frame FPs)
• Cleared Frames:   {self.stats['cleared_frames']} (Rejected frames)
• Merges:           {self.stats['merged']} (ID Switches fixed)
• Class Corrected:  {self.stats['class_changed']}
{sep}
"""
        log_to_file(self.log, summary)
        messagebox.showinfo("Saved", f"Correction saved to CSV and annotated images exported to:\n{export_dir}")
        self.callback()

    def on_quit_ask(self):
        if messagebox.askyesno("Quit", "Discard unsaved changes?"):
            self.callback()

if __name__ == "__main__":
    root = tk.Tk()
    try: from ctypes import windll; windll.shcore.SetProcessDpiAwareness(1)
    except: pass
    app = LauncherGUI(root)
    root.mainloop()