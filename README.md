# shelf-coolify

Déploie [shelf.nu](https://github.com/shelf-nu/shelf.nu) (gestion d'inventaire open source) sur une instance [Coolify](https://coolify.io) auto-hébergée en liant directement ce repo public (build pack Docker Compose). La stack est 100 % auto-hébergée : shelf.nu + Supabase OSS (Postgres, GoTrue, PostgREST, Storage, imgproxy, Kong) dans un seul `docker-compose.yaml`. Aucun compte Supabase Cloud requis.

## Architecture

| Service | Rôle |
|---------|------|
| shelf | Application principale (port 8080) |
| supabase-db | PostgreSQL avec extensions Supabase (pgsodium, etc.) |
| supabase-auth | GoTrue self-hosted : authentification par OTP email |
| supabase-rest | PostgREST : API REST auto-générée sur PostgreSQL (requis par Storage) |
| supabase-storage | Storage API : gestion des uploads, servi via Kong |
| imgproxy | Transformation d'images à la volée pour Storage |
| supabase-kong | Kong : reverse proxy unifié pour auth/rest/storage, expose l'API Supabase (port 8000) |
| migrate | Job one-shot : applique les migrations Prisma de shelf à chaque déploiement |
| create-buckets | Job one-shot : crée les 4 buckets attendus par shelf (idempotent) |

Les clés JWT anon/service sont générées automatiquement par Coolify via les magic vars `SERVICE_SUPABASEANON_KEY` et `SERVICE_SUPABASESERVICE_KEY`, signées avec la variable `SERVICE_PASSWORD_JWT`. Les migrations Prisma sont appliquées automatiquement par le service `migrate`, et les buckets Storage sont créés par le service `create-buckets`. Les OTP sont à 6 chiffres par défaut et les templates email OTP sont intégrés : aucune configuration Supabase manuelle n'est nécessaire.

## Prérequis

- Une instance [Coolify](https://coolify.io) v4.x
- Un fournisseur SMTP (indispensable en production pour l'envoi d'emails, voir "Les deux surfaces SMTP")

## Déploiement (1 clic)

### Option A (recommandée) : Lier le repo public

1. UI Coolify > + New > Public Repository
2. URL du repo : `https://github.com/welcoMattic/shelf-coolify`, branche `main`
3. Build pack : **Docker Compose** (le compose est à `/docker-compose.yaml`, l'emplacement par défaut)
4. Créer, puis Deploy.

Équivalent CLI :

```bash
coolify app create public \
  --server-uuid <uuid-serveur> \
  --project-uuid <uuid-projet> \
  --environment-name production \
  --git-repository "https://github.com/welcoMattic/shelf-coolify" \
  --git-branch main \
  --build-pack dockercompose \
  --ports-exposes 8080 \
  --name shelf
```

Après création, les variables listées dans `.env.example` peuvent être renseignées dans l'UI (Service > Environment Variables). Toutes sont optionnelles pour le boot. Les secrets (`SESSION_SECRET`, `INVITE_TOKEN_SECRET`, `FINGERPRINT`, `SERVICE_PASSWORD_POSTGRES`, `SERVICE_PASSWORD_JWT`, `SERVICE_SUPABASEANON_KEY`, `SERVICE_SUPABASESERVICE_KEY`) sont auto-générés par Coolify via les magic vars, rien à fournir.

### Domaines

DEUX domaines sont à prévoir :

| Service | Port | Usage |
|---------|------|-------|
| shelf | 8080 | Interface web de shelf.nu |
| supabase-kong | 8000 | API Supabase (utilisée par le navigateur) |

Les domaines se posent dans l'UI (Settings > Domains) après le premier déploiement, ou via PATCH :

```bash
curl -X PATCH https://<votre-coolify>/api/v1/applications/<uuid> \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"docker_compose_domains": {
    "shelf": {"name": "shelf", "domain": "https://shelf.example.com"},
    "supabase-kong": {"name": "supabase-kong", "domain": "https://supabase.example.com"}
  }}'
```

Les magic vars `SERVICE_URL_SHELF` et `SERVICE_URL_SUPABASE_KONG` se réconcilient sur ces domaines au déploiement suivant.

Note : le premier déploiement est requis avant le PATCH pour que Coolify connaisse les services du compose.

## Les deux surfaces SMTP

Il n'y a plus qu'une seule configuration SMTP, partagée par les deux surfaces :

- **SMTP côté GoTrue** : envoie les emails d'OTP de connexion (shelf déclenche `auth.signInWithOtp`, c'est le mailer GoTrue qui envoie).
- **SMTP côté shelf** : envoie les emails applicatifs (invitations, réservations).

Les MÊMES variables `SMTP_*` (voir `.env.example`) sont utilisées pour les deux. Sans SMTP, la stack démarre mais aucun email ne part (donc pas de connexion par OTP).

## Vérifier

```bash
coolify resource list
curl -sS -o /dev/null -w "%{http_code}\n" https://shelf.example.com
```

- Le healthcheck a une grace period de 90 s : laissez-lui le temps avant de conclure.
- Attendu : HTTP `200` et un statut `running (healthy)` dans Coolify pour tous les services.
- Créez le premier compte sur `https://shelf.example.com`, puis passez `DISABLE_SIGNUP` à `true` dans l'UI Coolify et redéployez pour fermer les inscriptions publiques.

## Pièges connus

- **Les conteneurs `migrate` et `create-buckets` s'affichent "exited"** : normal, ce sont des jobs one-shot qui se terminent après avoir fait leur travail.
- **Statut "unknown" juste après déploiement** : le healthcheck n'a pas encore réussi, attendez la grace period.
- **Ne retirez pas `SERVICE_FQDN_SHELF_8080` ou `SERVICE_FQDN_SUPABASE_KONG_8000`** du compose : c'est ce qui déclare le routage proxy Coolify. Les domaines épinglés se réconcilient au premier déploiement.
- **L'init de la base (mots de passe des rôles, secret JWT) ne joue qu'au premier boot d'un volume vierge**, en superuser via initdb (supautils interdit de modifier les rôles réservés ensuite). Pour repartir de zéro (effacer toutes les données), supprimez les volumes `supabase-db-data`, `supabase-db-config` et `supabase-storage-data` avant de redéployer.
- **Les templates email sont chargés depuis raw.githubusercontent.com** : si vous forkez ce repo, adaptez les URLs `GOTRUE_MAILER_TEMPLATES_*` dans le compose pour pointer vers votre fork.

## Mise à jour

- Option A (repo lié) : chaque mise à jour (ce dépôt ou `shelf.nu:latest`) se redéploie depuis l'UI Coolify (bouton Deploy), qui re-pull le repo et l'image. Le service `migrate` applique alors les migrations Prisma éventuelles, et `create-buckets` recrée les buckets si nécessaire.
- Équivalent CLI : `coolify deploy uuid <uuid-du-service>`.

## Ressources

- Documentation upstream : [shelf.nu docs](https://github.com/shelf-nu/shelf.nu/tree/main/apps/docs) (notamment `docker.md` et `supabase-setup.md`)
- Supabase self-hosting : [https://supabase.com/docs/guides/self-hosting/docker](https://supabase.com/docs/guides/self-hosting/docker)
- Template Supabase de Coolify : [coollabsio/coolify](https://github.com/coollabsio/coolify/blob/main/templates/compose/supabase.yaml)
- Licence : [MIT](./LICENSE)
