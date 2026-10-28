# Déployer Prof Karim (chimie) et Prof Aïcha (physique) sur le VPS

Déploiement de test par `http://IP:port`, une application par conteneur Docker, sur le VPS
`167.233.234.219` (déjà utilisé par d'autres applications : n'en arrêtez, ne modifiez et ne supprimez
aucune). Aucun sudo n'est nécessaire : il suffit d'appartenir au groupe `docker`.

| Application | Dossier sur le serveur | Conteneur | Port |
|---|---|---|---|
| Chimie (Prof Karim) | `~/chatchimie/` | `chatchimie` | 8002 |
| Physique (Prof Aïcha) | `~/chatphysique/` | `chatphysique` | 8003 |

Remplacez `UTILISATEUR` par votre compte SSH sur le serveur.

## Principe

- En local, `preparer_archive.ps1` compile le frontend et crée une archive : le dossier `backend\`
  (sans `venv`, `.env`, caches, tests) + le frontend compilé dans `frontend_dist\`, servi par le
  backend lui-même (même adresse, pas de CORS).
- Sur le serveur, `redeploy.sh` construit l'image Docker (`backend/Dockerfile`), remplace le conteneur
  et vérifie qu'il répond ; en cas d'échec, l'ancienne version est remise en service.
- Les secrets ne sont que dans `~/<app>/container.env` sur le serveur (droits 600) : jamais dans
  l'image, jamais dans git.

## 1. Vérifier le serveur (une fois, lecture seule)

```bash
ssh UTILISATEUR@167.233.234.219
docker ps --format '{{.Names}}\t{{.Ports}}'   # conteneurs existants et ports pris
ss -ltn | grep -E ':(8002|8003)\b' || echo "ports 8002 et 8003 libres"
free -h                                       # mémoire : prévoir ~1 Go disponible par application
df -h ~                                       # disque : prévoir ~4 Go par application (images)
which curl tar                                # utilisés par redeploy.sh
exit
```

Si 8002 ou 8003 est pris, choisissez un autre port libre (et utilisez-le partout ci-dessous).

## 2. Préparer en local (PowerShell, dans `chatbot-chimie-burkina`)

```powershell
cd E:\Dossier_Alex\Hakili_AI_Lab\chatbot_PC\chatbot-chimie-burkina

# Chimie
.\deploy\preparer_archive.ps1 -App chatchimie -AvecSecrets
# Physique (même script, autre projet)
.\deploy\preparer_archive.ps1 -App chatphysique -Projet ..\chatbot-physique-burkina -AvecSecrets
```

Résultat dans `deploy\out\` (ignoré par git) : `<app>-backend.tar.gz` et `<app>.container.env`.
`-AvecSecrets` lit `backend\.env` de chaque projet (sinon la variable Windows `ANTHROPIC_API_KEY`
pour la clé) et génère un `JWT_SECRET` neuf : **seulement pour le premier déploiement**. Pour les
mises à jour suivantes, relancez le script **sans** `-AvecSecrets`.

## 3. Envoyer sur le serveur

```powershell
ssh UTILISATEUR@167.233.234.219 "mkdir -p ~/chatchimie ~/chatphysique"

scp deploy\out\chatchimie-backend.tar.gz deploy\redeploy.sh UTILISATEUR@167.233.234.219:~/chatchimie/
scp deploy\out\chatchimie.container.env UTILISATEUR@167.233.234.219:~/chatchimie/container.env

scp deploy\out\chatphysique-backend.tar.gz deploy\redeploy.sh UTILISATEUR@167.233.234.219:~/chatphysique/
scp deploy\out\chatphysique.container.env UTILISATEUR@167.233.234.219:~/chatphysique/container.env

# Les fichiers de secrets n'ont plus rien à faire sur ce PC :
Remove-Item deploy\out\chatchimie.container.env, deploy\out\chatphysique.container.env
```

## 4. Déployer (sur le serveur)

```bash
ssh UTILISATEUR@167.233.234.219
chmod 600 ~/chatchimie/container.env ~/chatphysique/container.env
chmod +x ~/chatchimie/redeploy.sh ~/chatphysique/redeploy.sh

~/chatchimie/redeploy.sh chatchimie 8002
~/chatphysique/redeploy.sh chatphysique 8003
```

Chaque conteneur est plafonné en mémoire (3e argument, `1g` par défaut — `chatmaths-backend`, même pile, occupe ~650 Mo au repos — ex. `redeploy.sh chatchimie
8002 1500m`) : s'il dépasse, c'est lui que Docker arrête, jamais les autres applications. Le script refuse
de démarrer si le serveur n'a pas cette mémoire disponible (`free -h`, colonne `available`).

Le premier build prend 5 à 15 minutes par application (torch CPU + modèle d'embeddings). Le script
se termine par `Déployé` et affiche l'état (`/api/health`), ou par `[ERREUR] ...` avec les dernières
lignes du journal du conteneur.

## 5. Tester

- Navigateur : http://167.233.234.219:8002 (chimie) et http://167.233.234.219:8003 (physique).
- Si la page ne s'ouvre pas depuis votre PC alors que `curl http://127.0.0.1:8002/api/classes`
  répond sur le serveur, c'est le **pare-feu** du serveur : demandez à son administrateur d'ouvrir les
  ports 8002 et 8003 (impossible sans sudo).
- En `http://IP:port`, le micro (dictée vocale) et l'installation de l'application (PWA) ne sont
  pas disponibles : les navigateurs les réservent au HTTPS (domaine + certificat, étape ultérieure).

## Mises à jour

```powershell
# En local (sans -AvecSecrets : on garde le container.env du serveur)
.\deploy\preparer_archive.ps1 -App chatchimie
scp deploy\out\chatchimie-backend.tar.gz UTILISATEUR@167.233.234.219:~/chatchimie/
ssh UTILISATEUR@167.233.234.219 "~/chatchimie/redeploy.sh chatchimie 8002"
```

## Comptes partagés avec les maths

Avec `ACCOUNTS_DATABASE_URL` dans `container.env`, la chimie et la physique utilisent les comptes de
l'application des maths : un élève se connecte partout avec le même nom et le même mot de passe
(une connexion par application). Les comptes restent dans la base des maths (schéma `app`), l'activité
de chaque matière dans son schéma (`app_chimie`, `app_physique`) de cette même base, et l'index du cours
dans la base de la matière (`DATABASE_URL`).

- Préparation de la base des maths (une fois, déjà faite) : `deploy/comptes_partages.py`.
- Les rôles `chatchimie_app` / `chatphysique_app` lisent, créent et modifient les comptes, sans jamais
  pouvoir en supprimer, ni lire les conversations des maths.
- Un élève dont la classe n'est pas au programme (6ème, 5ème) ou qui n'en a pas choisit librement
  son niveau ; sa classe dans le compte n'est pas modifiée.
- Reprise de l'activité d'une ancienne base propre : `deploy/rattacher_activite.py`.

Retirer la ligne `ACCOUNTS_DATABASE_URL` puis redéployer revient aux comptes propres à l'application.

L'index vectoriel n'est pas dans l'image (il est dans Neon) : une mise à jour ne demande pas de
réindexer, sauf si les PDF de `data/documents` ont changé (`ingest_documents.py`, en local).

## Commandes utiles (sur le serveur)

```bash
docker logs --tail 100 -f chatchimie          # journal en direct (Ctrl+C pour sortir)
docker restart chatchimie                     # redémarrer
docker stats --no-stream chatchimie chatphysique   # mémoire / CPU
curl -s http://127.0.0.1:8002/api/health      # état : base, index, Claude
```

## En cas de problème

- `[ERREUR] ... manquant ou vide dans container.env` : compléter le fichier (voir
  `deploy/container.env.example`).
- `JWT_SECRET doit être défini explicitement quand APP_ENV=production` : `JWT_SECRET` absent.
- `PoolTimeout` / `failed to resolve host` dans le journal : le serveur n'atteint pas Neon
  (DNS ou port 5432 sortant) — vérifier depuis le serveur :
  `getent hosts neon.tech` et `timeout 5 bash -c '</dev/tcp/neon.tech/443' && echo ok`.
- Revenir à la version précédente : relancer `redeploy.sh` avec l'archive précédente, ou
  `docker images chatchimie` puis `docker run` sur le tag voulu (les 2 dernières images sont gardées).
