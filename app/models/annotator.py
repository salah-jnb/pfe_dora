import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
import time
import datetime
import threading
import shutil
import importlib.util
from pathlib import Path

# NOTE: Heavy libraries (cv2, torch, ultralytics) are imported lazily 
# inside the "Processor" thread to ensure the GUI starts immediately.

# ---------------------------------------------------------
# HELPER: LOGGING & VISUALS
# ---------------------------------------------------------
def init_log(filepath, system_name, model_name, device_info="Unknown"):
    """
    Initializes the main experiment log file with a standardized header.
    Why: Crucial for reproducibility and documenting the exact configuration of each run.
    """
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        script_name = os.path.basename(sys.argv[0])
        sep = "=" * 100
        header = (
            f"Annotation Run LOG\n{sep}\n"
            f"• Script:      {script_name}\n"
            f"• Date:        {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"• System:      {system_name}\n"
            f"• Model:       {model_name}\n"
            f"• Compute:     {device_info}\n"
            f"{sep}\n"
            f"{'TIME':<10} | {'VIDEO':<25} | {'DUR(s)':<8} | {'FPS':<6} | {'OBJS':<5} | {'RT':<5} | {'CLASSES'}\n"
            f"{'-'*100}\n"
        )
        with open(filepath, "w", encoding='utf-8') as f: f.write(header)
    except Exception as e:
        print(f"Log Init Error: {e}")

def log_result(filepath, video_name, proc_time, fps, total_objs, video_len_sec, class_counts):
    """
    Appends the inference statistics of a single processed video to the log.
    Why: Captures per-video performance metrics like Real-Time Factor (RT) and object distribution.
    """
    try:
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        rt = round(video_len_sec / proc_time, 2) if proc_time > 0 else 0
        dist = ", ".join([f"{k}:{v}" for k, v in class_counts.items()])
        line = f"{timestamp:<10} | {video_name:<25} | {proc_time:<8.2f} | {fps:<6.1f} | {total_objs:<5} | {rt:<5} | {dist}\n"
        with open(filepath, "a", encoding='utf-8') as f: f.write(line)
    except Exception as e:
        print(f"Log Result Error: {e}")

def log_summary(filepath, start_time, total_videos, fps_list):
    """
    Writes the final performance summary at the end of a batch run.
    """
    duration = datetime.datetime.now() - start_time
    total_seconds = duration.total_seconds()
    avg_fps = sum(fps_list) / len(fps_list) if fps_list else 0
    sep = "=" * 100
    summary = (
        f"\n{sep}\nSESSION SUMMARY\n{sep}\n"
        f"• Status:          COMPLETED\n"
        f"• Duration:        {int(total_seconds // 60)}m {int(total_seconds % 60)}s\n"
        f"• Videos Processed: {total_videos}\n"
        f"• Avg Speed:       {avg_fps:.2f} FPS\n{sep}\n"
    )
    try:
        with open(filepath, "a", encoding='utf-8') as f: f.write(summary)
    except Exception as e:
        print(f"Log Summary Error: {e}")

def transfer_logs(input_dir, output_dir, logger_func):
    """
    Copies logs from the previous processing stage (e.g., Reviewer) into the new Tracker directory.
    Why: Maintains an unbroken data lineage for the final evaluation script.
    """
    try:
        found_logs = [f for f in os.listdir(input_dir) if f.lower().endswith(".txt")]
        if not found_logs:
            return
        logger_func(f"Transferring {len(found_logs)} log files from input...")
        for log_file in found_logs:
            src = os.path.join(input_dir, log_file)
            dst = os.path.join(output_dir, log_file)
            if not os.path.exists(dst):
                shutil.copy2(src, dst)
    except Exception as e:
        logger_func(f"Warning: Log transfer failed: {e}")

# ---------------------------------------------------------
# PROCESSOR (WORKER THREAD)
# ---------------------------------------------------------
class Processor(threading.Thread):
    """
    Handles the heavy machine learning inference in a separate thread.
    Why: Prevents the Tkinter main loop from freezing while PyTorch calculates bounding boxes.
    """
    def __init__(self, job_list, common_cfg, update_callback, log_callback, finish_callback):
        super().__init__()
        self.jobs = job_list          
        self.common = common_cfg      
        self.update_cb = update_callback
        self.log_cb = log_callback
        self.finish_cb = finish_callback
        self.running = True  
        self.paused = False  
        self.device = "cpu" # Default fallback device

    def stop(self):
        """Safely signals the thread to terminate its loop."""
        self.running = False

    def toggle_pause(self):
        """Pauses or resumes the inference loop."""
        self.paused = not self.paused
        return self.paused

    def calc_iou(self, boxA, boxB):
        """
        Calculates Intersection over Union (IoU) between two bounding boxes.
        Why: Used for smart ID matching when a tracker drops an ID briefly and picks it up again.
        """
        xA = max(boxA[0], boxB[0]); yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2]); yB = min(boxA[3], boxB[3])
        interArea = max(0, xB - xA) * max(0, yB - yA)
        if interArea == 0: return 0
        boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
        boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
        return interArea / float(boxAArea + boxBArea - interArea + 1e-6)

    def run(self):
        """
        Main execution method for the thread. Loads models and processes the video batch.
        """
        self.log_cb("Initializing AI Engines (this might take a moment)...")
        if not self.running: return

        try:
            global cv2, YOLO, pd, torch, np
            import cv2
            import numpy as np
            import pandas as pd
            import torch
            from ultralytics import YOLO
            
            try:
                np.float = float
                np.int = int
                np.bool = np.bool_
            except: pass

        except ImportError as e:
            self.log_cb(f"CRITICAL ERROR: Missing Library -> {e}")
            self.finish_cb(success=False)
            return

        self.log_cb("Checking Tracking Modules...")
        self.DeepOcSort = None
        self.StrongSort = None
        self.BotSort = None
        self.ByteTrack = None
        self.BOXMOT_OK = False

        try:
            try:
                from boxmot import DeepOcSort, StrongSort, BotSort, ByteTrack
                self.DeepOcSort, self.StrongSort, self.BotSort, self.ByteTrack = DeepOcSort, StrongSort, BotSort, ByteTrack
            except ImportError:
                from boxmot import DeepOCSORT as DeepOcSort
                from boxmot import StrongSORT as StrongSort
                from boxmot import BoTSORT as BotSort
                from boxmot import ByteTrack
                self.DeepOcSort, self.StrongSort, self.BotSort, self.ByteTrack = DeepOcSort, StrongSort, BotSort, ByteTrack
            
            self.BOXMOT_OK = True
            self.log_cb("BoxMOT Trackers loaded successfully.")
        except Exception as e:
            self.log_cb(f"BoxMOT not found or error ({e}). Only System A available.")

        if not self.running: return

        self.log_cb(f"Loading YOLO Model: {self.common['model']}...")
        try:
            if torch.cuda.is_available():
                self.device = 0  # Utilizes the primary NVIDIA GPU
                device_str = f"GPU: {torch.cuda.get_device_name(0)}"
            else:
                self.device = "cpu"
                device_str = "CPU"

            yolo_model = YOLO(self.common['model']).to(self.device)

            print(f"[INFO] Backend: {device_str} selected for tracking.")
        except Exception as e:
            self.log_cb(f"Error loading YOLO: {e}")
            self.finish_cb(success=False)
            return

        input_dir = self.common['input_dir']
        try:
            files = [f for f in os.listdir(input_dir) if f.lower().endswith(('.mp4', '.avi', '.mov'))]
        except Exception as e:
            self.log_cb(f"Error reading input directory: {e}")
            self.finish_cb(success=False)
            return

        total_ops = len(files) * len(self.jobs)
        current_op = 0

        for job_idx, job in enumerate(self.jobs):
            if not self.running: break
            
            system_name = job['name']
            sys_type = job['sys_type']
            output_dir = job['output_dir']
            current_track_step = job['step'] 
            
            self.log_cb(f"\n>>> BATCH {job_idx+1}/{len(self.jobs)}: {system_name} (Step: {current_track_step})")
            tracker_instance = self._init_tracker(sys_type)
            
            if not tracker_instance and "System A" not in sys_type:
                self.log_cb(f"Skipping {system_name} (Tracker init failed).")
                current_op += len(files)
                self.update_cb((current_op / total_ops) * 100)
                continue

            os.makedirs(output_dir, exist_ok=True)
            transfer_logs(input_dir, output_dir, self.log_cb)

            log_file = os.path.join(output_dir, "experiment_log.txt")
            init_log(log_file, system_name, self.common['model'], device_str)
            
            session_start = datetime.datetime.now()
            fps_stats = []

            for i, filename in enumerate(files):
                if not self.running: 
                    self.log_cb(">>> ABORTED BY USER.")
                    break
                
                vid_path = os.path.join(input_dir, filename)
                base_name = os.path.splitext(filename)[0]
                
                curr_out_dir = os.path.join(output_dir, base_name)
                os.makedirs(os.path.join(curr_out_dir, 'trajectories'), exist_ok=True)
                os.makedirs(os.path.join(curr_out_dir, 'raw_frames'), exist_ok=True) 
                
                self.log_cb(f"[{system_name}] Processing {filename}...")
                
                if "System A" in sys_type:
                    fps = self._process_video(yolo_model, None, vid_path, curr_out_dir, log_file, True, current_track_step)
                else:
                    if hasattr(tracker_instance, 'reset'): tracker_instance.reset()
                    fps = self._process_video(yolo_model, tracker_instance, vid_path, curr_out_dir, log_file, False, current_track_step)
                
                if fps > 0: fps_stats.append(fps)
                current_op += 1
                self.update_cb((current_op / total_ops) * 100)

            if self.running:
                log_summary(log_file, session_start, len(files), fps_stats)
                self.log_cb(f">>> FINISHED BATCH: {system_name}")

        if self.running:
            self.log_cb("\nALL BATCHES COMPLETED SUCCESSFULLY.")
            self.finish_cb(success=True)
        else:
            self.log_cb("\nPROCESS CANCELLED.")
            self.finish_cb(success=False)

    def _init_tracker(self, sys_type):
        """
        Initializes the specific BoxMOT tracker algorithm chosen for the batch.
        Why: Configures embedding and matching thresholds based on the tracker's underlying architecture.
        """
        if "System A" in sys_type: return None 
        if not self.BOXMOT_OK: return None
            
        try:
            # DUMMY REID WEIGHTS: Prevents BoxMOT crashes.
            # We load a default model but disable its execution for pure motion-based trackers.
            reid_weights = Path('osnet_x0_25_msmt17.pt')
            device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
            
            if "DeepOCSORT" in sys_type:
                # embedding_off=True completely blocks ReID utilization
                return self.DeepOcSort(reid_weights=reid_weights, device=device, half=False, per_class=False, det_thresh=0.20, max_age=30, embedding_off=True)
            elif "StrongSORT" in sys_type:
                # StrongSORT strictly requires ReID, so it remains active here
                return self.StrongSort(reid_weights=reid_weights, device=device, half=False, per_class=False, det_thresh=0.20, max_age=30)
            elif "BoT-SORT" in sys_type:
                # with_reid=False completely blocks ReID utilization
                return self.BotSort(reid_weights=reid_weights, device=device, half=False, per_class=False, det_thresh=0.20, track_high_thresh=0.25, track_low_thresh=0.1, with_reid=False)
        except Exception as e:
            self.log_cb(f"Tracker Init Error: {e}")
            return None

    def _process_video(self, model, tracker, vid_path, out_folder, log_path, is_native, track_step):
        """
        Executes the frame-by-frame inference loop on a single video file.
        Why: Extracts bounding boxes, applies tracking logic, and saves the resulting trajectories to CSV.
        """
        cap = cv2.VideoCapture(vid_path)
        fps_v = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        traj = []
        counts = {}
        seen = set()
        idx = 0
        start = time.time()

        target_fps = self.common['target_fps']
        if target_fps == "Original":
            save_step = 1
        else:
            save_step = max(1, round(fps_v / int(target_fps)))
        conf = self.common['conf']
        target_classes = [0, 1, 2, 3, 5, 7] 
        
        global_classes = {} 
        id_map = {}         
        last_boxes = []     
        SMART_MATCH_IOU = 0.3 
        
        while cap.isOpened() and self.running:
            while self.paused and self.running:
                time.sleep(0.1)

            ret, frame = cap.read()
            if not ret: break
            
            if idx % track_step == 0:
                boxes, ids, clss = [], [], []
                
                if is_native:
                    res = model.track(frame, persist=True, classes=target_classes, tracker="bytetrack.yaml", verbose=False, conf=conf, device=self.device)
                    if res[0].boxes.id is not None:
                        boxes = res[0].boxes.xyxy.cpu().numpy()
                        ids = res[0].boxes.id.cpu().numpy().astype(int)
                        clss = res[0].boxes.cls.cpu().numpy().astype(int)
                else:
                    res = model.predict(frame, classes=target_classes, verbose=False, conf=conf, device=self.device)
                    if res[0].boxes:
                        dets = res[0].boxes.data.cpu().numpy()
                        if dets.shape[1] > 6: dets = dets[:, :6] 
                        
                        tracks = tracker.update(dets, frame)
                        if len(tracks) > 0:
                            boxes = tracks[:, :4]
                            ids = tracks[:, 4].astype(int)
                            clss = tracks[:, 6].astype(int)
                
                if len(boxes) > 0:
                    current_boxes = []
                    
                    for b, c, t in zip(boxes, clss, ids):
                        t = int(t)
                        yolo_cname = model.names[int(c)]
                        global_id = t
                        
                        if t in id_map:
                            global_id = id_map[t]
                        else:
                            best_iou = 0
                            best_old_id = None
                            for old_obj in last_boxes:
                                if (idx - old_obj['last_seen']) <= (track_step * 5):
                                    iou = self.calc_iou(b, old_obj['box'])
                                    if iou > best_iou:
                                        best_iou = iou
                                        best_old_id = old_obj['id']
                            
                            if best_iou > SMART_MATCH_IOU:
                                global_id = best_old_id
                                id_map[t] = global_id 
                            else:
                                id_map[t] = t 
                        
                        if global_id in global_classes:
                            final_cname = global_classes[global_id]
                        else:
                            global_classes[global_id] = yolo_cname
                            final_cname = yolo_cname
                            
                        current_boxes.append({'id': global_id, 'box': b, 'last_seen': idx})
                        
                        if global_id not in seen:
                            seen.add(global_id)
                            counts[final_cname] = counts.get(final_cname, 0) + 1
                            
                        if idx % save_step == 0:
                            x, y, w, h = b[0], b[1], b[2]-b[0], b[3]-b[1]
                            traj.append([idx, final_cname, global_id, x+w/2, y+h/2, x, y, w, h])
                        
                    for old_obj in last_boxes:
                        if not any(cb['id'] == old_obj['id'] for cb in current_boxes):
                            if (idx - old_obj['last_seen']) <= (track_step * 3):
                                current_boxes.append(old_obj)
                    last_boxes = current_boxes
                    
                    if idx % save_step == 0:
                        cv2.imwrite(os.path.join(out_folder, 'raw_frames', f"frame_{idx:05d}.png"), frame)
            idx += 1
        
        cap.release()
        proc_t = time.time() - start
        proc_fps = idx / proc_t if proc_t > 0 else 0
        
        if traj:
            pd.DataFrame(traj, columns=['frame', 'class', 'id', 'x_center', 'y_center', 'x', 'y', 'w', 'h']).to_csv(os.path.join(out_folder, 'trajectories', f"{os.path.basename(vid_path)}.csv"), index=False)
        
        video_len_sec = total_frames / fps_v if fps_v > 0 else 0
        log_result(log_path, os.path.basename(vid_path), proc_t, proc_fps, len(seen), video_len_sec, counts)
        return proc_fps

# ---------------------------------------------------------
# GUI CLASS
# ---------------------------------------------------------
class AnnotatorGUI:
    """
    Main application interface for selecting datasets, models, and tracker configurations.
    """
    def __init__(self, root):
        self.root = root
        self.root.title("Auto Annotator")
        self.root.geometry("950x850")
        
        self.in_dir = tk.StringVar(value=r"C:\Daten\AA-Bachlorarbeit\Anno\Videos\D_Reviewed")
        self.model_var = tk.StringVar(value="yolo11l.pt")
        self.conf_thresh = tk.DoubleVar(value=0.23)
        self.fps_var = tk.StringVar(value="Original")
        self.progress_val = tk.DoubleVar(value=0.0)
        
        self.systems = [
            {"name": "Run 1: ByteTrack  (Baseline)", "sys_type": "System A", "var": tk.BooleanVar(value=True), "path": tk.StringVar(), "step": tk.IntVar(value=1)},
            {"name": "Run 2: DeepOCSORT (Motion+)",  "sys_type": "DeepOCSORT", "var": tk.BooleanVar(value=False), "path": tk.StringVar(), "step": tk.IntVar(value=1)},
            {"name": "Run 3: StrongSORT (ReID)",     "sys_type": "StrongSORT", "var": tk.BooleanVar(value=False), "path": tk.StringVar(), "step": tk.IntVar(value=1)},
            {"name": "Run 4: BoT-SORT   (Hybrid)",   "sys_type": "BoT-SORT", "var": tk.BooleanVar(value=False), "path": tk.StringVar(), "step": tk.IntVar(value=1)},
        ]
        
        self.processor = None
        self.setup_ui()

    def setup_ui(self):
        main = ttk.Frame(self.root, padding=20)
        main.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main, text="Auto Annotator", font=("Segoe UI", 16, "bold")).pack(pady=(0, 20))
        
        common_frame = ttk.LabelFrame(main, text="Global Settings", padding=10)
        common_frame.pack(fill=tk.X, pady=5)
        
        r1 = ttk.Frame(common_frame); r1.pack(fill=tk.X, pady=2)
        ttk.Label(r1, text="Input Videos:", width=15).pack(side=tk.LEFT)
        ttk.Entry(r1, textvariable=self.in_dir).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(r1, text="...", width=3, command=lambda: self.browse(self.in_dir)).pack(side=tk.RIGHT)
        
        r2 = ttk.Frame(common_frame); r2.pack(fill=tk.X, pady=5)
        ttk.Label(r2, text="YOLO Model:", width=15).pack(side=tk.LEFT)
        ttk.Combobox(r2, textvariable=self.model_var, values=["yolo11n.pt", "yolo11l.pt", "yolo11x.pt", "yolo12x.pt"], width=15).pack(side=tk.LEFT)
        
        ttk.Label(r2, text="Confidence:", width=10).pack(side=tk.LEFT, padx=(20, 0))
        ttk.Scale(r2, from_=0.1, to=0.9, variable=self.conf_thresh).pack(side=tk.LEFT, fill=tk.X, expand=True)
        lbl_conf = ttk.Label(r2, text="0.23"); lbl_conf.pack(side=tk.RIGHT)
        self.conf_thresh.trace_add("write", lambda *a: lbl_conf.config(text=f"{self.conf_thresh.get():.2f}"))

        r3 = ttk.Frame(common_frame); r3.pack(fill=tk.X, pady=2)
        ttk.Label(r3, text="FPS:", width=15).pack(side=tk.LEFT)
        ttk.Combobox(r3, textvariable=self.fps_var, values=["5", "10", "20", "Original"], state="readonly", width=15).pack(side=tk.LEFT)
        ttk.Label(r3, text="Frames per second extracted for annotation").pack(side=tk.LEFT, padx=(10, 0))

        job_frame = ttk.LabelFrame(main, text="Batch Jobs Configuration Set Output Path", padding=10)
        job_frame.pack(fill=tk.X, pady=15)
        
        for sys_dict in self.systems:
            self.create_system_row(job_frame, sys_dict)

        self.progress = ttk.Progressbar(main, variable=self.progress_val, maximum=100)
        self.progress.pack(fill=tk.X, pady=(20, 5))
        
        self.log_text = tk.Text(main, height=12, state="disabled", bg="#f0f0f0", font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=10)
        
        self.btn_start = tk.Button(btn_frame, text="START BATCH RUN", bg="#C8E6C9", font=("Segoe UI", 11, "bold"), command=self.start_batch)
        self.btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        
        self.btn_pause = tk.Button(btn_frame, text="PAUSE", bg="#FFE0B2", font=("Segoe UI", 11, "bold"), state="disabled", command=self.toggle_pause_batch)
        self.btn_pause.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        self.btn_cancel = tk.Button(btn_frame, text="STOP / CANCEL", bg="#FFCDD2", font=("Segoe UI", 11, "bold"), state="disabled", command=self.cancel_batch)
        self.btn_cancel.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

    def create_system_row(self, parent, sys_dict):
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=5)
        
        chk = ttk.Checkbutton(row, text=sys_dict['name'], variable=sys_dict['var'], command=lambda: self.toggle_entry(sys_dict), width=28)
        chk.pack(side=tk.LEFT)
        
        ttk.Label(row, text="Step:").pack(side=tk.LEFT, padx=(5, 2))
        step_spin = ttk.Spinbox(row, from_=1, to=10, textvariable=sys_dict['step'], width=3, state="normal" if sys_dict['var'].get() else "disabled")
        step_spin.pack(side=tk.LEFT, padx=(0, 10))
        sys_dict['step_widget'] = step_spin
        
        entry = ttk.Entry(row, textvariable=sys_dict['path'], state="normal" if sys_dict['var'].get() else "disabled")
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        sys_dict['entry_widget'] = entry 
        
        btn = ttk.Button(row, text="Output...", command=lambda: self.browse(sys_dict['path']))
        btn.pack(side=tk.RIGHT)
        sys_dict['btn_widget'] = btn

    def toggle_entry(self, sys_dict):
        state = "normal" if sys_dict['var'].get() else "disabled"
        sys_dict['entry_widget'].config(state=state)
        sys_dict['btn_widget'].config(state=state)
        sys_dict['step_widget'].config(state=state)

    def browse(self, var):
        d = filedialog.askdirectory()
        if d: var.set(d)

    def log(self, msg):
        def _update():
            self.log_text.config(state="normal")
            self.log_text.insert(tk.END, f">> {msg}\n")
            self.log_text.see(tk.END)
            self.log_text.config(state="disabled")
        self.root.after(0, _update)

    def update_progress(self, val):
        self.root.after(0, lambda: self.progress_val.set(val))

    def process_finished(self, success=True):
        def _finish():
            self.btn_start.config(state="normal", text="START BATCH RUN")
            self.btn_pause.config(state="disabled", text="PAUSE")
            self.btn_cancel.config(state="disabled")
            if success:
                messagebox.showinfo("Done", "Batch Processing Completed!")
            else:
                messagebox.showwarning("Stopped", "Process stopped or failed.")
        self.root.after(0, _finish)

    def cancel_batch(self):
        if self.processor and self.processor.is_alive():
            self.log(">>> CANCELLING PROCESS... PLEASE WAIT.")
            self.processor.stop()
            if self.processor.paused: 
                self.processor.toggle_pause() 
            self.btn_cancel.config(state="disabled")

    def toggle_pause_batch(self):
        if self.processor and self.processor.is_alive():
            is_paused = self.processor.toggle_pause()
            if is_paused:
                self.btn_pause.config(text="RESUME", bg="#90CAF9")
                self.log(">>> PAUSED.")
            else:
                self.btn_pause.config(text="PAUSE", bg="#FFE0B2")
                self.log(">>> RESUMED.")

    def start_batch(self):
        if not os.path.exists(self.in_dir.get()): return messagebox.showerror("Error", "Input Directory invalid.")
        
        active_jobs = []
        for s in self.systems:
            if s['var'].get():
                path = s['path'].get()
                if not path:
                    return messagebox.showerror("Error", f"Please select an Output Path for {s['name']}")
                active_jobs.append({
                    'name': s['name'], 
                    'sys_type': s['sys_type'], 
                    'output_dir': path,
                    'step': s['step'].get() 
                })
        
        if not active_jobs: return messagebox.showerror("Error", "No Systems selected!")

        common_cfg = {
            'input_dir': self.in_dir.get(),
            'model': self.model_var.get(),
            'conf': self.conf_thresh.get(),
            'target_fps': self.fps_var.get(),
        }

        self.btn_start.config(state="disabled", text="RUNNING...")
        self.btn_pause.config(state="normal", text="PAUSE", bg="#FFE0B2")
        self.btn_cancel.config(state="normal")
        
        self.log(f"Starting Batch with {len(active_jobs)} Systems...")
        
        self.processor = Processor(active_jobs, common_cfg, self.update_progress, self.log, self.process_finished)
        self.processor.start()

if __name__ == "__main__":
    root = tk.Tk()
    try: from ctypes import windll; windll.shcore.SetProcessDpiAwareness(1)
    except: pass
    app = AnnotatorGUI(root)
    root.mainloop()