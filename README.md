# SkillBuild Backend

Django REST API backend for the SkillBuild platform.

## Tech Stack
- Python 3.11+
- Django 5.2
- Django REST Framework
- PostgreSQL
- LangChain + Groq

## Setup

1. Clone the repo
   ```bash
   git clone https://github.com/YOUR_USERNAME/SkillBuild-Backend.git
   cd SkillBuild-Backend/skillbuild_backend
   ```

2. Create and activate a virtual environment
   ```bash
   python -m venv venv
   venv\Scripts\activate        # Windows
   source venv/bin/activate     # macOS/Linux
   ```

3. Install dependencies
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables
   ```bash
   cp .env.example .env
   # Edit .env with your actual values
   ```

5. Run migrations
   ```bash
   python manage.py migrate
   ```

6. Create a superuser
   ```bash
   python manage.py createsuperuser
   ```

7. Start the dev server
   ```bash
   python manage.py runserver
   ```

## API Endpoints

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/api/core/health/` | Health check |
| GET/POST | `/admin/` | Django admin |
