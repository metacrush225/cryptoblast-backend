# CryptoBlast Backend

Backend de CryptoBlast, un service de suivi automatisé du marché des cryptomonnaies construit avec FastAPI.

L’API collecte les données de marché de Binance, calcule plusieurs indicateurs techniques et peut publier des alertes accompagnées d’un graphique dans un salon Discord.

> Les informations et signaux produits par CryptoBlast sont fournis à titre informatif. Ils ne constituent pas des conseils financiers.

## Fonctionnalités

- récupération du ticker Binance sur 24 heures ;
- récupération de chandeliers pour plusieurs intervalles ;
- calcul du RSI sur 14 périodes ;
- calcul des moyennes mobiles SMA 10 et SMA 30 ;
- historique des prix et indicateurs jusqu’à 1 000 points ;
- cache mémoire avec durée de vie configurable ;
- nouvelles tentatives automatiques en cas d’erreur réseau ou serveur ;
- génération de graphiques PNG ;
- alertes Discord en cas de survente ou de surachat ;
- endpoint sécurisé destiné à Google Cloud Scheduler ;
- validation des entrées et des réponses avec Pydantic ;
- documentation OpenAPI interactive.

## Stack technique

- Python 3.11
- FastAPI
- Pydantic
- HTTPX
- Binance REST API
- Discord REST API
- Google Cloud Run
- Google Cloud Scheduler
- Docker

## Architecture

```text
app/
├── main.py                 # Création de l’application et cycle de vie
├── config.py               # Configuration et variables d’environnement
├── cache.py                # Cache mémoire avec TTL
├── routers/                # Routes HTTP et validation des requêtes
├── services/               # Logique métier et orchestration
├── clients/                # Clients Binance et Discord
├── models/                 # Modèles métier
└── responses/              # Schémas Pydantic de sortie
```

### Responsabilités

- `main.py` assemble l’application, configure CORS et gère le cycle de vie du client HTTP partagé.
- `config.py` centralise les constantes et la configuration issue de l’environnement.
- `routers/` expose les endpoints, valide les entrées et traduit les erreurs en réponses HTTP.
- `services/` contient les calculs et la logique métier indépendamment du transport HTTP.
- `clients/` encapsule les échanges avec Binance et Discord.
- `cache.py` évite de répéter inutilement certains appels externes.

## Fonctionnement

### Données d’un symbole

Pour une requête telle que :

```http
GET /api/crypto/BTCUSDT
```

CryptoBlast :

1. normalise le symbole en majuscules ;
2. vérifie qu’il appartient à la liste des symboles autorisés ;
3. récupère le ticker sur 24 heures et 50 chandeliers horaires ;
4. consulte le cache avant d’appeler Binance ;
5. retente les erreurs réseau et serveur selon la configuration ;
6. calcule le RSI 14 ainsi que les SMA 10 et 30 ;
7. valide et renvoie le résultat avec Pydantic.

Le cache expire par défaut après 20 secondes. Il est propre à chaque processus et n’est donc pas partagé entre plusieurs instances de l’API.

### Historique

```http
GET /api/crypto/BTCUSDT/history?interval=1h&days=14
```

L’endpoint historique récupère les chandeliers correspondant à la période demandée et renvoie notamment :

- la date de chaque point ;
- le prix d’ouverture ;
- le prix de clôture ;
- la SMA 10 ;
- la SMA 30.

Les premières valeurs des moyennes mobiles sont `null` tant que le nombre de points disponible ne couvre pas entièrement leur fenêtre de calcul.

Les intervalles pris en charge vont de `1m` à `1d`, dans la limite de 1 000 points par requête.

### Alertes Discord

L’endpoint suivant est destiné à être appelé périodiquement par Google Cloud Scheduler :

```http
POST /api/alerts/scheduler-check
X-Scheduler-Token: votre-token
```

Lors de chaque vérification, CryptoBlast :

1. parcourt les symboles configurés ;
2. récupère leurs données de marché ;
3. calcule leur RSI ;
4. ignore les valeurs comprises entre les seuils configurés ;
5. génère un graphique avec le prix, les SMA 10 et 30 et le signal détecté ;
6. publie une alerte Discord pour les actifs en survente ou en surachat.

Un endpoint distinct permet de tester manuellement l’envoi d’alertes :

```http
POST /api/alerts/test
```

## Endpoints

| Méthode | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/` | Informations générales sur l’API |
| `GET` | `/health` | État de santé du service |
| `GET` | `/api/crypto` | Liste des symboles pris en charge |
| `GET` | `/api/crypto/{symbol}` | Ticker, RSI et moyennes mobiles |
| `GET` | `/api/crypto/{symbol}/history` | Historique et moyennes mobiles |
| `GET` | `/api/intervals` | Intervalles et couvertures disponibles |
| `POST` | `/api/alerts/test` | Déclenchement manuel des alertes |
| `POST` | `/api/alerts/scheduler-check` | Vérification sécurisée pour le scheduler |

Une fois le serveur lancé, la documentation interactive est disponible à l’adresse suivante :

```text
http://localhost:8000/docs
```

## Installation locale

### Prérequis

- Python 3.11 ou une version compatible ;
- `pip` ;
- un environnement virtuel Python ;
- un accès réseau à l’API Binance.

### Préparation

Créez et activez un environnement virtuel :

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Installez ensuite les dépendances :

```powershell
pip install -r requirements.txt
```

Copiez le fichier de configuration d’exemple :

```powershell
Copy-Item env.example .env
```

Renseignez les variables nécessaires dans `.env`, puis démarrez l’API :

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Configuration

| Variable | Rôle |
| --- | --- |
| `SYMBOLS` | Paires Binance surveillées, séparées par des virgules |
| `CORS_ORIGINS` | Origines autorisées à appeler l’API |
| `CACHE_TTL_SECONDS` | Durée de conservation des données en cache |
| `HTTP_TIMEOUT_SECONDS` | Délai maximal des appels HTTP externes |
| `MAX_RETRIES` | Nombre maximal de nouvelles tentatives |
| `RETRY_BACKOFF_BASE` | Base du délai exponentiel entre les tentatives |
| `RSI_OVERSOLD` | Seuil de survente du RSI |
| `RSI_OVERBOUGHT` | Seuil de surachat du RSI |
| `DISCORD_BOT_TOKEN` | Jeton du bot Discord |
| `DISCORD_ALERT_CHANNEL_ID` | Identifiant du salon recevant les alertes |
| `ALERTS_SCHEDULER_TOKEN` | Jeton protégeant l’endpoint du scheduler |

Ne publiez jamais le fichier `.env`, les jetons Discord ou le jeton du scheduler dans le dépôt.

## Docker

Construisez l’image :

```powershell
docker build -t cryptoblast-backend .
```

Lancez ensuite le conteneur :

```powershell
docker run --rm --env-file .env -p 8000:8080 cryptoblast-backend
```

Le service reste accessible depuis la machine hôte à l’adresse :

```text
http://localhost:8000
```

Le conteneur utilise Python 3.11 et expose l’application sur le port `8080`.

## Résilience et gestion des erreurs

Le client Binance applique jusqu’à trois tentatives avec un délai exponentiel pour les erreurs réseau et les réponses serveur `5xx`.

Les erreurs client `4xx` ne sont pas retentées. Elles sont converties en réponses explicites afin d’éviter d’exposer des exceptions internes aux consommateurs de l’API.

Le client HTTP est créé au démarrage de l’application et partagé entre les requêtes. Cela permet de réutiliser les connexions et de libérer proprement les ressources lors de l’arrêt du service.

## Limites actuelles

- Le cache est conservé uniquement en mémoire.
- Son contenu n’est pas partagé entre plusieurs instances Cloud Run.
- Le déclenchement périodique dépend d’un scheduler externe.
- L’anti-duplication des alertes reste à renforcer.
- La couverture automatisée du projet doit encore être enrichie.

## Feuille de route

- ajouter des tests unitaires et d’intégration ;
- éviter les alertes répétées pour un même signal ;
- ajouter des métriques et une meilleure observabilité ;
- utiliser Redis si plusieurs instances doivent partager le même cache ;
- enrichir l’analyse avec le volume, le MACD et les bandes de Bollinger ;
- afficher les analyses et graphiques directement dans le frontend CryptoBlast.

## Déploiement

Le backend est conçu pour être conteneurisé puis déployé sur Google Cloud Run. Google Cloud Scheduler peut appeler périodiquement l’endpoint sécurisé afin de lancer l’analyse des symboles configurés.

Avant un déploiement public, vérifiez notamment :

- les origines CORS autorisées ;
- la présence des secrets dans l’environnement d’exécution ;
- la valeur de `ALERTS_SCHEDULER_TOKEN` ;
- les délais et tentatives des appels externes ;
- la configuration du salon Discord.
