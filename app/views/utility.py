import datetime

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/ui/pick-folder", summary="Open native folder picker on server host")
def ui_pick_folder(title: str = "Select folder"):
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(title=title) or ""
        root.destroy()
        return {"path": selected}
    except Exception as e:
        raise HTTPException(500, f"Folder picker error: {e}")


@router.get("/ui/pick-video", summary="Open native video picker on server host")
def ui_pick_video(title: str = "Select video"):
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilename(
            title=title,
            filetypes=[
                ("Video files", "*.mp4 *.avi *.mov *.mkv *.m4v"),
                ("All files", "*.*"),
            ],
        ) or ""
        root.destroy()
        return {"path": selected}
    except Exception as e:
        raise HTTPException(500, f"Video picker error: {e}")


@router.get("/health", summary="API health check")
def health():
    return {"status": "ok", "time": datetime.datetime.now().isoformat()}
