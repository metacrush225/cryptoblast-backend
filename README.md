# CryptoBlast Backend

## Pitch entretien

CryptoBlast est une API FastAPI qui sert des donnees de marche crypto
provenant de Binance. Elle recupere le ticker 24h et les chandeliers (klines),
calcule des indicateurs techniques simples (RSI et moyennes mobiles SMA 10/30),
puis renvoie des reponses validees par Pydantic. Un endpoint securise peut
declencher une verification de tous les symboles suivis et envoyer une alerte
Discord avec un graphique lorsqu'un RSI sort des seuils 30/70.

## Architecture

```text
app/main.py
  |-- lifespan: cree et ferme un httpx.AsyncClient partage
  |-- CORS et gestion des erreurs HTTP
  |-- routers: info, crypto, alerts
		 |-- services: calcul RSI/SMA, orchestration des alertes, graphiques
		 |-- clients: Binance REST et Discord REST
		 |-- models/responses: schemas Pydantic de sortie
```

Responsabilites principales :

- `main.py` assemble l'application et gere le cycle de vie des ressources.
- `config.py` centralise les variables d'environnement et les constantes.
- `routers/` gere HTTP, validation des entrees et codes/reponses fonctionnels.
- `services/` contient la logique metier, independante du wiring FastAPI.
- `clients/` encapsule les appels aux APIs externes.
- `cache.py` fournit un cache memoire TTL partage entre les requetes.

## Flux principal : donnees d'un symbole

Pour `GET /api/crypto/BTCUSDT` :

1. Le routeur normalise le symbole en majuscules et verifie qu'il est dans
	`VALID_SYMBOLS`.
2. La dependance `get_binance_client` injecte un `BinanceClient` qui reutilise
	le client HTTP cree au demarrage.
3. Le service demande a Binance le ticker 24h et 50 klines horaires.
4. Le client Binance consulte d'abord le cache. En cas de miss, il effectue
	l'appel REST, avec jusqu'a trois tentatives pour les erreurs reseau/5xx et
	un backoff exponentiel.
5. Le service calcule le RSI sur 14 periodes, la SMA 10 et la SMA 30.
6. `CryptoData` valide et structure le resultat, puis `ApiResponse` le renvoie.

Le cache dure par defaut 20 secondes. Il est local au processus : il n'est pas
partage entre plusieurs replicas de l'API.

## Flux historique

`GET /api/crypto/{symbol}/history?interval=1h&days=14` recupere le nombre de
points configure pour l'intervalle, extrait open/close/timestamp des klines,
puis calcule une SMA 10 et une SMA 30 glissantes. Les premieres valeurs sont
`null` tant que la fenetre n'est pas complete. Les intervalles supportes vont
de `1m` a `1d`, avec une limite maximale de 1000 points.

## Flux des alertes Discord

`POST /api/alerts/scheduler-check` est prevu pour un appel de Google Cloud
Scheduler. Il exige le header `X-Scheduler-Token` correspondant a
`ALERTS_SCHEDULER_TOKEN`, puis :

1. parcourt tous les symboles de `VALID_SYMBOLS` ;
2. recupere leurs donnees et leur RSI ;
3. ignore les RSI compris entre 30 et 70 ;
4. genere un PNG avec prix, SMA 10, SMA 30 et signal ;
5. envoie un embed Discord avec le graphique pour les symboles en survente ou
	surachat.

`POST /api/alerts/test` declenche le meme traitement sans le token, utile pour
tester la configuration. Les alertes sont des signaux techniques informatifs,
pas des conseils financiers.

## Endpoints a connaitre

| Methode | Endpoint | Role |
| --- | --- | --- |
| GET | `/` | Informations sur l'API |
| GET | `/health` | Etat de sante et configuration utile |
| GET | `/api/crypto` | Liste des symboles supportes |
| GET | `/api/crypto/{symbol}` | Ticker 24h, RSI et SMA |
| GET | `/api/crypto/{symbol}/history` | Historique et SMA par intervalle |
| GET | `/api/intervals` | Intervalles et couverture disponibles |
| POST | `/api/alerts/test` | Test manuel des alertes |
| POST | `/api/alerts/scheduler-check` | Verification securisee pour scheduler |

Documentation interactive : `http://localhost:8000/docs`.

## Configuration

Copier `env.example` vers `.env`, puis ajuster :

- `SYMBOLS` : paires Binance suivies, separees par des virgules ;
- `CORS_ORIGINS` : origines autorisees du frontend ;
- `CACHE_TTL_SECONDS`, `HTTP_TIMEOUT_SECONDS`, `MAX_RETRIES` et
  `RETRY_BACKOFF_BASE` : comportement reseau ;
- `RSI_OVERSOLD` et `RSI_OVERBOUGHT` : seuils d'alerte ;
- `DISCORD_BOT_TOKEN`, `DISCORD_ALERT_CHANNEL_ID` et
  `ALERTS_SCHEDULER_TOKEN` : activation et securisation des alertes.

## Lancer le projet

### En local

```powershell
\.venv\Scripts\activate.ps1
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Avec Docker

```powershell
docker build -t cryptoblast-backend .
docker run --rm --env-file .env -p 8000:8080 cryptoblast-backend
```

Le conteneur utilise Python 3.11, installe `requirements.txt` et expose le
port 8080. En local, Uvicorn ecoute par defaut sur le port 8000.

## Questions d'entretien possibles

**Pourquoi un client HTTP partage ?**

Pour reutiliser les connexions, limiter le cout des handshakes et fermer
proprement les ressources dans le `lifespan` FastAPI.

**Pourquoi encapsuler Binance dans un client ?**

Pour isoler le protocole externe du metier, centraliser le cache et les retries,
et faciliter les tests avec un faux client.

**Pourquoi utiliser RSI et SMA ?**

Le RSI mesure le momentum sur 14 periodes. La SMA lisse le prix et permet de
comparer la tendance courte (10) a la tendance plus longue (30). Ce sont des
indicateurs simples, donc ils ne constituent pas a eux seuls une strategie de
trading fiable.

**Que se passe-t-il si Binance est indisponible ?**

Le client retente les erreurs reseau et serveur avec backoff. Les erreurs 4xx
ne sont pas retentees. Le routeur transforme ensuite l'echec en reponse
fonctionnelle explicite au lieu de laisser fuiter une exception interne.

**Quelles limites vois-tu ?**

Le cache est seulement en memoire, les alertes sont declenchees par endpoint
plutot que par un scheduler interne, et il n'y a pas encore de suite de tests
visible dans le depot. En production, on pourrait ajouter Redis, des tests
unitaires/integration, de la metrique et une protection anti-duplication des
alertes.