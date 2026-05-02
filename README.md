# ANU CS Assignment Analyse Helper

A buildathon prototype for ANU computer science students. The app estimates assignment workload from:

- completed ANU COMP courses and marks
- local course descriptions and learning outcomes
- an uploaded assignment brief in TXT or PDF format
- DeepSeek, when `DEEPSEEK_API_KEY` is configured

The output is an English assignment readiness report with total hours, phase-by-phase workload, likely covered knowledge, missing knowledge, difficulty, confidence, risks, and assumptions.

## Run

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

Open:

```txt
http://localhost:8787
```

## Configuration

Create `.env` from `.env.example`:

```env
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_MODEL=deepseek-v4-flash
PORT=8787
```

If `DEEPSEEK_API_KEY` is missing, the app still runs with a deterministic demo estimate so the UI can be tested without API cost.

## Deploy

Use a Python web service host such as Render or Railway.

Recommended Render settings:

- Build command: `python3 -m pip install -r requirements.txt`
- Start command: `python3 app.py`
- Environment variables:
  - `DEEPSEEK_API_KEY`
  - `DEEPSEEK_MODEL=deepseek-v4-flash`
  - `PORT` is usually set by the platform

Do not commit `.env`. Add the API key through the hosting platform's environment variable settings.

## Data

The app reads:

- `data/anu_comp_course_workload_data_2025_clean.jsonl`
- `data/anu_grading_scale.jsonl`

Courses are searched locally by code, title, description, and learning outcomes. Marks are expected to be `0-100` and are mapped to ANU grade bands.

## Notes

- PDF support uses `pypdf` and works best with text-based PDFs.
- Scanned/image-only PDFs are not OCRed.
- History and student background are stored in browser `localStorage`.
