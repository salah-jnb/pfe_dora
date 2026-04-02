# pfe_dora_ela

Backend FastAPI + frontend server-side pour annotation et correction de trajectoires video.

## Structure

- `app/models`: logique metier (`annotator.py`, `corrector.py`) et schemas
- `app/views`: routes API
- `app/services`: orchestration jobs et etat applicatif
- `app/templates`: pages front + JS/CSS
- `app/workspace_data`: uploads et outputs des jobs
- `weights`: modeles YOLO
- `scripts`: utilitaires setup/lancement

## Lancer le projet

1. Installer dependances:
   - `\.venv311\Scripts\python.exe -m pip install -r requirements.txt`
2. Demarrer API:
   - `\.venv311\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000`
3. Ouvrir:
   - `http://127.0.0.1:8000/front`

## Scripts utiles

- Setup complet: `scripts\setup.bat`
- Run backend: `scripts\run_project.bat`

## Documentation Architecture

- Voir `docs/ARCHITECTURE_MVT.md`
