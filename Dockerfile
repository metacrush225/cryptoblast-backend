# 1) Choix de l'image Python légère
FROM python:3.11-slim

# 2) Définit le dossier de travail
WORKDIR /app

# 3) Copie du requirements et installation (le layer se mettra en cache tant que requirements.txt ne change pas)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4) Copie du code de l’API
COPY . .

# 5) Expose le port sur lequel tourne Uvicorn
EXPOSE 8000

# 6) Commande de démarrage
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
