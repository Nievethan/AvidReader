# AvidReader Capstone Project

Welcome to the AvidReader repository! This project consists of a Python backend and a Flutter frontend. Follow the instructions below to get your local development environment set up and properly contribute code.

## 🛠 Prerequisites

Ensure you have the following installed on your machine:

* **Git**: For version control.
* **Docker & Docker Compose**: To run the full stack via the provided `docker-compose.yml` file.


* **Python 3.11**: If running the backend locally (matches the Dockerfile; 3.14 cannot build the pinned pydantic).


* **Flutter SDK**: If running the frontend locally, as indicated by the `pubspec.yaml` file.



## 🚀 Setup Instructions

**1. Clone the Repository**

```bash
git clone https://github.com/Nievethan/AvidReader.git
cd AvidReader

```

**2. Run with Docker (Recommended)**
Since the project root contains a `docker-compose.yml` and the backend contains a `Dockerfile`, you can spin up the entire environment at once:

```bash
docker compose up --build

```

This starts the backend and Qdrant (vector database). Add `--profile full` to also start Neo4j. For real AI answers, put Cloudflare Workers AI credentials in `backend/.env` (see `backend/.env.example`); without them the backend runs with offline fallbacks.

**3. Manual Local Setup (Alternative)**
If you need to run the services individually without Docker:

* **Backend Setup:**
Dependencies are listed in `backend/requirements.txt` (FastAPI, SQLAlchemy, PyMuPDF, EbookLib, qdrant-client, httpx, ...). Without Docker, Qdrant runs embedded under `backend/data/qdrant`. Full backend docs, including the RAG pipeline, endpoints and the evaluation script, are in [`backend/README.md`](backend/README.md).


```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # add Cloudflare credentials for real AI answers
uvicorn app.main:app --reload

```


* **Frontend Setup:**
Navigate to the frontend directory containing the `pubspec.yaml` file.


```bash
cd frontend
flutter pub get
flutter run

```



---

## 🌿 Git Branching Workflow (CRITICAL)

**🛑 DO NOT COMMIT DIRECTLY TO `main`!**
To ensure we don't overwrite each other's work or break the codebase, you must create a new branch before making any changes.

**1. Pull the latest code:**
Always start by ensuring your local version of `main` is up to date.

```bash
git checkout main
git pull origin main

```

**2. Create a new branch:**
Create your own branch to work on before writing any code. Use a descriptive name (e.g., `feature/login-screen` or `bugfix/api-route`).

```bash
git checkout -b feature/your-feature-name

```

**3. Make changes and commit:**

```bash
git add .
git commit -m "Brief description of the changes"

```

**4. Push and create a Pull Request:**

```bash
git push origin feature/your-feature-name

```

Once pushed, go to the repository on GitHub and open a Pull Request against the `main` branch. Let the group know your PR is ready for review.