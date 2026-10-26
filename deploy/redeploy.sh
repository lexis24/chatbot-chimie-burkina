#!/usr/bin/env bash
# Déploie (ou redéploie) une application Hakili Lab sur le serveur, dans un conteneur Docker.
#
# Usage, sur le serveur :
#   ~/chatchimie/redeploy.sh chatchimie 8002
#   ~/chatphysique/redeploy.sh chatphysique 8003
#
# Attend dans ~/<app>/ :
#   - <app>-backend.tar.gz : archive produite en local par deploy/preparer_archive.ps1
#     (dossier backend/ + frontend compilé dans frontend_dist/) ;
#   - container.env : variables d'environnement du conteneur (secrets compris), droits 600.
#
# Étapes : extraction -> construction de l'image -> arrêt de l'ancien conteneur (gardé de côté) ->
# démarrage du nouveau -> contrôle de santé. En cas d'échec, l'ancien conteneur est remis en
# service automatiquement. Ne touche à aucun autre conteneur du serveur. Aucun sudo nécessaire
# (l'utilisateur doit seulement appartenir au groupe docker).
set -euo pipefail

APP="${1:?Usage : redeploy.sh <app> <port> [mémoire max] (ex. chatchimie 8002 1g)}"
PORT="${2:?Usage : redeploy.sh <app> <port> [mémoire max] (ex. chatchimie 8002 1g)}"
# Plafond de mémoire du conteneur (sans swap supplémentaire) : sur un serveur partagé, si
# l'application le dépasse, c'est ELLE que Docker arrête — jamais les autres applications du serveur.
MEMORY="${3:-1g}"
BASE="$HOME/$APP"
ARCHIVE="$BASE/$APP-backend.tar.gz"
ENV_FILE="$BASE/container.env"
STAMP="$(date +%Y%m%d-%H%M%S)"
SRC="$BASE/src-$STAMP"
IMAGE="$APP:$STAMP"

say() { printf '\n== %s\n' "$*"; }
fail() { printf '\n[ERREUR] %s\n' "$*" >&2; exit 1; }

[[ "$APP" =~ ^[a-z0-9_-]+$ ]] || fail "nom d'application invalide : $APP"
[[ "$PORT" =~ ^[0-9]+$ ]] || fail "port invalide : $PORT"
[[ "$MEMORY" =~ ^[0-9]+[mg]$ ]] || fail "mémoire invalide : $MEMORY (ex. 1500m ou 2g)"

# Garde-fou : refuse de démarrer si le serveur n'a pas la mémoire disponible pour ce conteneur
# (ignoré lors d'un redéploiement : l'ancien conteneur libère la sienne en s'arrêtant).
need_mb=$(( ${MEMORY%[mg]} * $([[ "$MEMORY" == *g ]] && echo 1024 || echo 1) ))
avail_mb=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
if ! docker ps --format '{{.Names}}' | grep -qx "$APP" && [ "$avail_mb" -lt "$need_mb" ]; then
  fail "mémoire insuffisante : ${avail_mb} Mo disponibles, ${need_mb} Mo nécessaires pour $APP. Démarrer ce conteneur mettrait en danger les autres applications du serveur."
fi
[ -f "$ENV_FILE" ] || fail "$ENV_FILE introuvable (voir deploy/DEPLOIEMENT.md, étape 3)"
[ -f "$ARCHIVE" ] || fail "$ARCHIVE introuvable (voir deploy/DEPLOIEMENT.md, étape 2)"
chmod 600 "$ENV_FILE"
for var in ANTHROPIC_API_KEY DATABASE_URL VECTOR_TABLE_NAME JWT_SECRET; do
  grep -Eq "^${var}=.+" "$ENV_FILE" || fail "$var manquant ou vide dans $ENV_FILE"
done
grep -Eq '^APP_ENV=production$' "$ENV_FILE" || fail "APP_ENV=production manquant dans $ENV_FILE"

# Le port doit être libre, ou déjà occupé par CE conteneur (redéploiement).
if docker ps --format '{{.Names}} {{.Ports}}' | grep -E ":${PORT}->" | grep -vq "^${APP} "; then
  fail "le port $PORT est déjà utilisé par un autre conteneur : choisis un autre port"
fi

say "Extraction de l'archive dans $SRC"
mkdir -p "$SRC"
tar -xzf "$ARCHIVE" -C "$SRC"
[ -f "$SRC/Dockerfile" ] || fail "Dockerfile absent de l'archive"
[ -f "$SRC/frontend_dist/index.html" ] || fail "frontend_dist/index.html absent : l'archive a-t-elle été faite avec preparer_archive.ps1 ?"

say "Construction de l'image $IMAGE (plusieurs minutes la première fois)"
docker build -t "$IMAGE" "$SRC"

HAD_OLD=0
if docker ps -a --format '{{.Names}}' | grep -qx "$APP"; then
  say "Arrêt de l'ancien conteneur (gardé sous le nom $APP-old le temps du contrôle)"
  docker rm -f "$APP-old" >/dev/null 2>&1 || true
  docker stop "$APP" >/dev/null
  docker rename "$APP" "$APP-old"
  HAD_OLD=1
fi

say "Démarrage du nouveau conteneur sur le port $PORT"
docker run -d --name "$APP" --restart unless-stopped \
  --memory "$MEMORY" --memory-swap "$MEMORY" \
  --env-file "$ENV_FILE" -e PORT=8000 -p "$PORT:8000" "$IMAGE" >/dev/null

say "Contrôle de santé (jusqu'à 3 minutes : chargement du modèle, réveil de Neon)"
ok=0
for _ in $(seq 1 90); do
  if curl -fsS "http://127.0.0.1:$PORT/api/classes" >/dev/null 2>&1; then ok=1; break; fi
  if [ "$(docker inspect -f '{{.State.Running}}' "$APP" 2>/dev/null)" != "true" ]; then break; fi
  sleep 2
done

if [ "$ok" != 1 ]; then
  echo "[ERREUR] Le nouveau conteneur ne répond pas. Dernières lignes de son journal :"
  docker logs --tail 40 "$APP" 2>&1 || true
  docker rm -f "$APP" >/dev/null 2>&1 || true
  if [ "$HAD_OLD" = 1 ]; then
    docker rename "$APP-old" "$APP"
    docker start "$APP" >/dev/null
    fail "déploiement annulé : l'ancienne version est remise en service"
  fi
  fail "déploiement annulé (aucune version précédente à remettre en service)"
fi

docker rm -f "$APP-old" >/dev/null 2>&1 || true
say "Déployé. État de l'application :"
curl -fsS "http://127.0.0.1:$PORT/api/health" || true
echo

# Ménage : on garde les 2 dernières images et les 2 derniers dossiers source.
docker images "$APP" --format '{{.Tag}}' | sort -r | tail -n +3 | xargs -r -I{} docker rmi "$APP:{}" >/dev/null 2>&1 || true
ls -1d "$BASE"/src-* 2>/dev/null | sort -r | tail -n +3 | xargs -r rm -rf
say "Terminé : http://<adresse-du-serveur>:$PORT/"
