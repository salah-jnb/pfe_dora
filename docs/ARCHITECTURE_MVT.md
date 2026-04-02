# Architecture MVT (Etat Actuel)

Le projet suit une structure MVT simple:

- `Model`: logique metier et schemas
- `View`: routes FastAPI
- `Template`: pages HTML + JS/CSS

## 1) Mapping Clair

### Model (`app/models`)
- `app/models/annotator.py`
  - Moteur IA (classe `Processor`) pour detection/tracking
- `app/models/corrector.py`
  - Logique metier correction (CSV, mapping frames, logs corrector)
- `app/models/schemas.py`
  - Schemas Pydantic (`AnnotatorConfig`, `TrackingRun`, etc.)

### View (`app/views`)
- `app/views/annotate.py`
  - Endpoints `/annotate/*` et `/jobs`
- `app/views/corrector.py`
  - Endpoints `/correct/*`
- `app/views/front.py`
  - Endpoints de pages `/front*`
- `app/views/utility.py`
  - `/health`, `/ui/pick-*`

### Template (`app/templates`)
- `app/templates/index_new.html`
- `app/templates/index.html`
- `app/templates/processing.html`
- `app/templates/corrector.html`
- `app/templates/corrector_editor.html`
- `app/templates/js/*`
- `app/templates/css/*`

## 2) Service Layer (`app/services`)

Pour garder les views fines:

- `app/services/job_runner.py`
  - Orchestration des jobs annotateur
- `app/services/state.py`
  - Etat global des jobs, logs, verrous

## 3) Donnees et Ressources

- `app/workspace_data/uploads/`: videos chargees
- `app/workspace_data/outputs/`: resultats jobs
- `weights/`: poids YOLO (`*.pt`)

## 4) Flux Execution

1. Template `index.html` envoie la video vers `POST /annotate/upload-start`.
2. `views/annotate.py` cree un job et delegue a `services/job_runner.py`.
3. `models/annotator.py` execute l'IA et ecrit dans `app/workspace_data/outputs`.
4. `processing.html` poll `GET /annotate/status/{job_id}`.
5. `corrector.html`/`corrector_editor.html` utilisent `GET/POST /correct/*`.

## 5) Clarification Doublons (resolu)

- Le corrector metier vit dans `app/models/corrector.py` (symetrie avec `annotator.py`).
- Les services restent limites a l'orchestration (`job_runner`) et l'etat (`state`).
