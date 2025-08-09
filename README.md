# Activer le .venv
.\.venv\Scripts\activate.ps1

# Debug via uvicorn
uvicorn main:app --host 0.0.0.0 --port 8000

# Pour build
docker build -t cryptoblast-backend .

# Pour tester en local
docker run --rm -p 8000:8000 cryptoblast-backend