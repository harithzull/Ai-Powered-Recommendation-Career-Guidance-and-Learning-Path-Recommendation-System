# CareerCoach

A Django web application for career guidance, RIASEC assessment, career recommendations, skill gap analysis, roadmap tracking, and an optional AI chatbot.

## Requirements

- Python 3.12 or newer
- pip
- Git

## Setup

Clone the repository and enter the project folder:

```bash
git clone <your-repo-url>
cd <your-repo-folder>
```

Create and activate a virtual environment:

```bash
python -m venv .venv
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

On macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run database migrations:

```bash
python manage.py migrate
```

Create an admin user:

```bash
python manage.py createsuperuser
```

Start the development server:

```bash
python manage.py runserver
```

Open the app at:

```text
http://127.0.0.1:8000/
```

## Recommendation Data

The recommender import command expects these files inside a `data/` folder:

- `careers_clean (1).csv`
- `skills_clean (1).csv`
- `career_skills_clean (1).csv`

When the files are available, import the data:

```bash
python manage.py import_data
```

Then build skill vectors:

```bash
python manage.py build_skill_vectors
```

## Chatbot Setup

The chatbot uses Groq. Add your API key in `careercoach/settings.py`:

```python
GROQ_API_KEY = "your-api-key"
```

Without this key, the rest of the app can still run, but chatbot responses will be disabled.

## Useful Commands

Run tests:

```bash
python manage.py test
```

Run the server:

```bash
python manage.py runserver
```

## Notes

Local files such as `db.sqlite3`, cache files, logs, and virtual environments are ignored by Git.
