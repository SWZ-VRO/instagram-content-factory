# Instagram Content Factory

Usine de contenu : masters ComfyUI → variantes → captions → calendrier 30 jours → publication automatique sur 100+ comptes Instagram.

**État actuel : Phases 1, 2, 4 et le cœur de la Phase 5 terminés.** Ce README documente ce qui est réellement fonctionnel aujourd'hui, et ce qui reste à construire (voir "Plan de phases" tout en bas). Rien n'est simulé ou inventé : les fonctionnalités non encore utilisables répondent `501 Not Implemented` plutôt que de faire semblant de marcher.

## Démarrage en une commande

```bash
docker compose up -d --build
```

... ou, plus confortable (copie `.env`, attend que le backend soit prêt, ouvre le dashboard) :

```powershell
.\run.ps1
```
```bash
./run.sh   # macOS / Linux / WSL / Git Bash
```

Ensuite tout est centralisé :
- **Dashboard** : http://localhost:3000
- **API + doc interactive (Swagger)** : http://localhost:8000/docs

Pour arrêter : `docker compose down`. Rien n'est perdu (Postgres persiste dans un volume Docker).

## 1. Prérequis

- **Docker Desktop** (Windows/Mac/Linux) — c'est la seule dépendance obligatoire pour lancer l'app telle quelle.
- Pas besoin d'installer Python/Node/PostgreSQL/Redis/FFmpeg à la main : tout tourne dans les conteneurs.

## 2. Installation manuelle (sans Docker, optionnel)

Utile seulement pour du développement backend/frontend en direct.

```bash
# Backend
cd instagram-content-factory
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r backend/requirements.txt
cp .env.example .env           # puis éditer SECRET_KEY
# Il faut un Postgres qui tourne (docker compose up -d postgres suffit)
alembic -c backend/alembic.ini upgrade head
uvicorn backend.main:app --reload   # lancé depuis instagram-content-factory/, pas backend/

# Frontend (autre terminal)
cd frontend
npm install
npm run dev
```

## 3. PostgreSQL

Géré automatiquement par `docker-compose.yml` (image `postgres:16-alpine`, volume persistant `postgres_data`). Les migrations (Alembic) tournent automatiquement au démarrage du conteneur `backend`. Pour lancer les migrations à la main :

```bash
docker compose exec backend alembic -c backend/alembic.ini upgrade head
```

Le schéma complet (tables, index, contraintes) est dans `backend/models/*.py` (source de vérité) et `backend/alembic/versions/0001_initial.py` (migration).

**La règle métier n°1 du projet — une variante n'est jamais publiée deux fois — est garantie au niveau base de données**, pas seulement dans le code applicatif : un index unique partiel sur `scheduled_posts(variant_id)` (restreint aux statuts `RESERVED`/`SCHEDULED`/`PUBLISHED`) rend une double réservation impossible même en cas de concurrence. Voir `backend/models/scheduled_post.py` et `backend/schedulers/reservation.py`.

## 4. Redis

Déclaré dans `docker-compose.yml` mais pas encore utilisé — le watcher (Phase 2) et le Publishing Worker (Phase 5) tournent en threads Python internes au conteneur `backend`, pas en tâches Celery. Redis/Celery arrivent en Phase 6 pour la vraie concurrence à l'échelle de 100+ comptes. Rien à faire pour l'instant.

## 5. FFmpeg

Installé dans l'image Docker du backend (`backend/Dockerfile`, package système `ffmpeg`). Utilisé pour de vrai par la génération de variantes (`backend/services/ffmpeg_runner.py`, `transforms.py`, `variant_generator.py`).

⚠️ **Cet environnement de développement n'a pas ffmpeg installé nativement** — la suite de tests utilise donc des doublures (mocks) pour `ffmpeg`/`ffprobe` (voir `tests/test_master_import.py`, `tests/test_ffmpeg_runner.py`) plutôt que d'invoquer le vrai binaire. Dans Docker, le vrai `ffmpeg` est installé et utilisé. Avant un premier import réel, vérifie que ça fonctionne :
```bash
docker compose exec backend ffmpeg -version
```

## 6. Dossier ComfyUI / masters — fonctionnel

Dépose tes vidéos maîtres générées par ComfyUI dans `content/masters/`. Le watcher (`backend/workers/watcher.py`) scanne ce dossier toutes les `WATCHER_POLL_INTERVAL_SECONDS` (5s par défaut) et, pour chaque nouveau fichier :

1. attend que sa taille se stabilise (protection contre un fichier en cours de copie) ;
2. vérifie son intégrité (extension, non-vide, lisible par `ffprobe`, durée raisonnable) — sinon déplacé dans `content/failed/` ;
3. calcule son SHA256 et rejette les doublons exacts (`content/failed/`, même renommé — §14) ;
4. calcule un hash perceptuel et **signale** (sans bloquer) les quasi-doublons dans les logs (`code=POSSIBLE_DUPLICATE`) ;
5. crée le `Master` en base, génère 5 à 10 variantes (crop/zoom/reframe/miroir/trim/vitesse — `backend/services/transforms.py`), calcule leurs hashes ;
6. associe automatiquement une caption si `content/captions/{VARIANT_CODE}.txt` existe déjà ;
7. déplace le master original vers `content/archive/` une fois terminé.

Bouton **IMPORT NOW** (§10) : `POST /masters/import` force un scan immédiat sans attendre le prochain cycle du watcher.

Note de conception : `content/ready/` n'est pas un dossier physique de copies vidéo (dupliquer des fichiers vidéo volumineux serait un gaspillage) — la disponibilité d'une variante est son `status=AVAILABLE` en base, visible dans `GET /variants` et `GET /inventory`. `content/failed/` reçoit réellement les masters rejetés.

## 7. Import des captions — fonctionnel

**Toi seul fournis les captions — l'app ne génère, ne reformule, ne traduit et n'ajoute jamais rien (hashtags, emojis, etc.) au texte que tu donnes.** C'est une contrainte dure du projet, appliquée dans `backend/services/caption_service.py` (import CSV en masse) et `backend/services/master_import.py` (association automatique TXT-par-variante pendant l'import).

Format CSV (§12) :
```bash
curl -X POST http://localhost:8000/captions/import -F "file=@mes_captions.csv"
```
Format TXT-par-fichier : dépose `content/captions/MASTER_001_V01.txt` avant (ou après, un futur import) que le master correspondant soit traité — le watcher/IMPORT NOW l'associe automatiquement.

## 8. Génération des variantes — fonctionnel

10 transformations fixes (`backend/services/transforms.py`), essayées dans l'ordre, en gardant celles qui réussissent et passent le contrôle qualité : `crop_center`, `crop_top_left`, `crop_bottom_right`, `zoom_in`, `reframe_vertical` (9:16), `mirror_horizontal`, `trim_skip_intro`, `trim_skip_outro`, `trim_middle_segment`, `speed_slight_up`. Un master échoue (`status=FAILED`) si moins de `MIN_VARIANTS` (5) variantes utilisables sont produites.

## 9. Connexion des comptes Instagram — fonctionnel (deux voies)

La doc actuelle de Meta (Graph API, vérifiée pendant ce projet, Aug 2026) a été vérifiée avant d'écrire une ligne de code :

- Seuls les comptes **Instagram Business/Creator liés à une Page Facebook** sont publiables via l'API — pas les comptes personnels.
- **Il n'existe aucun paramètre de planification native** (`publish_at`) sur l'API Instagram — c'est pour ça que le Publishing Worker (§18/§51) doit se réveiller lui-même à l'heure prévue, créer le container média, attendre `FINISHED`, puis publier. C'est le flux réellement implémenté dans `backend/publishers/instagram_official.py`.
- Limites de débit observées : de l'ordre de 25 à 100 publications/24h par compte (variable, basé sur les impressions, pas un chiffre fixe) et 200 appels API/heure/compte — traités comme plafonds prudents et configurables (`IG_MAX_PUBLISHES_PER_ACCOUNT_PER_DAY`), jamais supposés fixes.

**Voie 1 — connexion manuelle (fonctionne dès aujourd'hui, sans App Review Meta) :**
1. Crée un Meta Developer App, génère un token via [Graph API Explorer](https://developers.facebook.com/tools/explorer/), récupère l'`ig_business_id` de ton compte.
2. `POST /accounts/{account_id}/connect/manual` avec `{"ig_business_id": "...", "access_token": "..."}` — validé contre la vraie API avant d'être stocké (jamais en clair, §53).

**Voie 2 — OAuth "Connect Instagram" (nécessite un Meta App avec App Review approuvé) :**
Configure `IG_APP_ID`/`IG_APP_SECRET`/`IG_OAUTH_REDIRECT_URI` dans `.env`, puis `GET /accounts/oauth/authorize` renvoie l'URL du dialogue Facebook ; `GET /accounts/oauth/callback` finalise et connecte automatiquement tous les comptes Instagram liés aux Pages Facebook de l'utilisateur. Tant que ces variables sont vides, l'endpoint répond `501` plutôt que de générer une URL cassée.

⚠️ La résolution Page→compte Instagram (`/me/accounts` + champ `instagram_business_account`) suit le flux "Facebook Login for Business" documenté et stable historiquement, mais Meta propose aussi désormais un flux "Instagram API with Instagram Login" distinct (endpoints `graph.instagram.com`) — **revérifie les noms de scope et endpoints contre la doc Meta actuelle avant un vrai déploiement**, les noms de permissions ont déjà changé par le passé (`instagram_content_publish` → `instagram_business_content_publish`).

**Important — hébergement public des vidéos :** l'API Instagram récupère la vidéo depuis une URL HTTPS publique, elle n'accepte pas d'upload direct. Configure `PUBLIC_BASE_URL` (ton domaine réel, ou un tunnel ngrok/cloudflared en dev) — sans ça, toute publication réelle échoue proprement avec une erreur claire plutôt qu'un envoi silencieusement cassé.

## 10. Permissions API

Voir point 9. Scopes demandés : `instagram_business_basic`, `instagram_business_content_publish`.

## 11. Génération du calendrier 30 jours — fonctionnel

`POST /calendar/generate` (`backend/schedulers/calendar.py`) : répartit les variantes `AVAILABLE` entre les comptes actifs selon la cadence §21 (2 posts/jour J1-3, 3/jour J4-7, 3-5/jour J8-30 — répartition déterministe, pas aléatoire, pour un plan reproductible), en respectant dans l'ordre : unicité globale (réservation atomique, `backend/schedulers/reservation.py`), cooldown master 2 jours par compte, caption obligatoire, compte actif. Les variantes sont interleavées round-robin entre masters pour limiter les conflits de cooldown évitables.

Réponse : `{plan_id, required_posts, available_variants_at_start, reserved_count, shortage, content_shortage}` — le calcul de manque (§26/§49) est explicite, jamais masqué.

`GET /calendar/plans` / `GET /calendar/plans/{id}` pour consulter ; `POST /calendar/approve/{id}` (§37) fait passer les posts `RESERVED → SCHEDULED` — c'est seulement à partir de là que le Publishing Worker peut les publier.

## 12. Dry run

`DRY_RUN=true` par défaut. Le Publishing Worker tourne quand même (il traite les posts dus, vérifie tout le §51) mais s'arrête juste avant tout appel réseau réel et logue "aurait publié" — ça permet de valider toute la mécanique sans jamais risquer une vraie publication. Mets `DRY_RUN=false` seulement quand tu es prêt (compte connecté pour de vrai, `PUBLIC_BASE_URL` configuré).

## 13. Approval — fonctionnel

Workflow réel : `IMPORT → VARIANTS → CAPTIONS → QC → GENERATE PLAN → REVIEW → APPROVE → AUTO-PUBLISH`. `POST /calendar/approve/{plan_id}` refuse un second appel sur le même plan (409), jamais un double-approve silencieux.

## 14. Publication automatique — fonctionnel (Publishing Worker)

`backend/workers/publishing_worker.py` tourne en tâche de fond dans le conteneur backend, réveillé toutes les `PUBLISHING_POLL_INTERVAL_SECONDS` (30s par défaut). Pour chaque post `SCHEDULED` dû :
compte actif → connecté → média présent sur disque → caption présente → idempotence (§39, clé `account+variant+scheduled_at`) → upload (container Graph API) → poll jusqu'à `FINISHED` → publish → `PUBLISHED` + `provider_post_id`.

Distinction stricte des échecs (§5) :
- **Auth expirée** (`PublisherAuthError`) → compte marqué `TOKEN_EXPIRED`, post reste `SCHEDULED` (jamais perdu, §17) ;
- **Rate limit** → retry avec backoff exponentiel (§46, `RETRY_BACKOFF_BASE_SECONDS` × 2^tentative) ;
- **Erreur définitive** (média invalide, etc.) → `FAILED`, jamais retenté ;
- Après `MAX_PUBLISH_ATTEMPTS` tentatives sur une erreur transitoire → `FAILED`.

`POST /publishing/start` déclenche un cycle immédiatement (bouton manuel, en plus du worker automatique). `POST /publishing/pause` / `POST /publishing/resume` (§38 PAUSE ALL). `GET /publishing/status` pour l'état courant.

## 15. Gestion des erreurs

Le vocabulaire d'erreurs du cahier des charges (`MISSING_CAPTION`, `INVALID_MEDIA`, `UPLOAD_FAILED`, `TOKEN_EXPIRED`, `RATE_LIMIT`, `ACCOUNT_AUTH_ERROR`, `SCHEDULING_CONFLICT`, `CONTENT_SHORTAGE`) est défini dans `backend/models/enums.py` (`ErrorCode`) et réellement écrit dans la table `logs` par le Publishing Worker et le pipeline d'import — la page Errors dédiée du dashboard (lecture de cette table) arrive en Phase 7 ; consultable dès maintenant en base ou via une future route `GET /logs`.

## 16. Troubleshooting

| Problème | Piste |
|---|---|
| `docker compose up` échoue direct | Docker Desktop est-il lancé ? |
| Le dashboard affiche "Could not reach the backend API" | `docker compose logs backend` — la migration Alembic a-t-elle réussi ? |
| `alembic upgrade head` échoue en local (hors Docker) | Vérifie que Postgres tourne et que `DATABASE_URL` dans `.env` pointe dessus |
| Import de master toujours en `PROCESSING` / jamais `READY` | `docker compose logs backend \| grep icf.watcher` ; vérifie `ffmpeg -version` dans le conteneur |
| Publishing Worker ne publie rien | `GET /publishing/status` — `DRY_RUN` est-il à `true` ? Le compte est-il `CONNECTED` ? `PUBLIC_BASE_URL` est-il configuré ? |
| Les tests échouent | Ils tournent en SQLite isolé (`tests/conftest.py`), aucune dépendance externe (ni Postgres, ni ffmpeg, ni réseau) requise — `pip install -r backend/requirements.txt` puis `pytest` depuis `instagram-content-factory/` |
| Je veux réinitialiser complètement | `docker compose down -v` (supprime aussi le volume Postgres) |

## Tests

```bash
pip install -r backend/requirements.txt
pytest -v
```

~85 tests, zéro dépendance externe (SQLite isolé par test, ffmpeg/Instagram mockés — voir `tests/conftest.py`). Couvre explicitement les Tests 1 à 8 du cahier des charges (§48) : unicité globale, cooldown master (refus/acceptation aux bonnes limites, master différent, comptes différents), caption obligatoire, double réservation concurrente (deux threads, un seul gagne), et génération de calendrier à l'échelle 100 comptes/30 jours.

## Architecture

```
Frontend (Next.js/React/Tailwind)
    ↓ REST (OpenAPI -- /docs)
FastAPI (api → services → repositories → models)
    ↓                              ↘
PostgreSQL (source de vérité)    workers/ (watcher, publishing_worker -- threads)
    ↑                              ↓
    └──────────────────  schedulers/ (reservation, calendar) → publishers/ (Instagram) → Graph API
```

Structure : `backend/{api,services,models,repositories,workers,schedulers,publishers,validators}` — la logique métier ne vit jamais dans les routes API (voir chaque module pour le détail de sa responsabilité).

## Plan de phases

- ✅ **Phase 1 — Foundation** : backend, frontend, DB, Docker, comptes/masters/variantes/captions (CRUD), unicité + cooldown testés.
- ✅ **Phase 2 — Video pipeline** : watcher `content/masters/`, FFmpeg, génération variantes, QC, hashing/dédoublonnage.
- ✅ **Phase 3 — Content system** : import captions (CSV + TXT), Content Inventory (`GET /inventory`), relations master/variant.
- ✅ **Phase 4 — Scheduler** : calendrier 30 jours, cooldown master, unicité globale, distribution comptes, timezones, dry run.
- 🟡 **Phase 5 — Publisher** : container/publish réel + retries + Publishing Worker **faits** ; connexion manuelle **faite** ; OAuth "Connect Instagram" **codé mais nécessite un Meta App avec App Review approuvé pour être testé/utilisé** (pas testable dans cet environnement, aucune app Meta réelle disponible).
- ⬜ **Phase 6 — Scale** : Celery/Redis réels, rate limiting actif par compte, concurrency control, monitoring dédié.
- 🟡 **Phase 7 — Dashboard final** : pages **Accounts, Masters, Inventory, Calendar (avec boutons Generate/Approve), Queue (avec Pause/Resume/Run Now), Errors** faites (`frontend/app/*`) ; page Settings dédiée pas encore faite (le pause/resume global est déjà géré depuis Queue).
