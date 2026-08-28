# shelf-coolify

Déploie [shelf.nu](https://github.com/shelf-nu/shelf.nu) (gestion d'inventaire open source) sur une instance [Coolify](https://coolify.io) auto-hébergée, en liant directement ce repo public (build pack Docker Compose), avec Supabase Cloud pour la base de données, l'authentification et le stockage.

## Architecture

> L'image officielle shelf.nu ne supporte **pas** Supabase self-hosted (position upstream).
> Ce dépôt suit donc le chemin supporté : application sur Coolify + projet Supabase Cloud (le free tier suffit).
> Les migrations Prisma sont appliquées automatiquement à chaque déploiement via le service one-shot `migrate` (vérifié : `npx prisma@6.19.3 migrate deploy` fonctionne dans l'image GHCR).

## Prérequis

- Une instance [Coolify](https://coolify.io) v4.x et un token API (permissions write + deploy)
- Un compte [Supabase](https://supabase.com) et un projet créé
- Un fournisseur SMTP (indispensable en production, voir "Les deux surfaces SMTP")
- Python 3 pour le script de déploiement (stdlib seule, optionnel : seulement pour l'option B)

## Étapes de déploiement

### 1. Configurer le projet Supabase

Dans le tableau de bord Supabase de votre projet :

1. **Connection pooling** : Project Settings > Database > Connection pooling, mode **Transaction**, puis Save.

2. **Connection strings Prisma** : bouton Connect > ORM > Prisma, copiez :
   - **DATABASE_URL** : via le pooler (port 6543), avec le paramètre `?pgbouncer=true`
   - **DIRECT_URL** : connexion directe pour les migrations (port 5432)

3. **Clés API** : Project Settings > API keys, copiez :
   - **SUPABASE_URL** : URL du projet (ex : `https://votre-projet.supabase.co`)
   - **SUPABASE_ANON_PUBLIC** : la clé anon (publique)
   - **SUPABASE_SERVICE_ROLE** : la clé service role

4. **URL Configuration** : Authentication > URL Configuration :
   - **Site URL** : `https://shelf.example.com` (votre futur domaine)
   - **Redirect URLs** : ajouter `https://shelf.example.com/reset-password`

5. **Longueur des OTP** : Authentication > Sign In / Providers > Email > OTP Settings :
   - **OTP Length** : `6`. Le défaut Supabase est passé à 8 et **casse le login shelf** (l'app n'accepte que des codes à 6 chiffres).

6. **Templates email OTP** : Authentication > Email Templates. Shelf utilise des OTP, pas des magic links : remplacez le contenu des templates "Confirm signup", "Magic Link" et "Reset Password" :

   <details>
   <summary>Templates "Confirm signup" et "Magic Link"</summary>

   ```html
   <p>To authenticate, please use the following One Time Password (OTP):</p>
   <h2><b>{{ .Token }}</b></h2>
   <p>Don't share this OTP with anyone.</p>
   ```

   </details>

   <details>
   <summary>Template "Reset Password"</summary>

   ```html
   <h2>Reset Password</h2>
   <p>To reset your password, please use the following (OTP):</p>
   <h2><b>{{ .Token }}</b></h2>
   <p>Don't share this OTP with anyone.</p>
   ```

   </details>

7. **Buckets Storage** : Storage > Buckets, créez les 4 buckets suivants :

   | Bucket | Visibilité | Policy INSERT/UPDATE/DELETE |
   |--------|------------|------------------------------|
   | `profile-pictures` | Public | `(bucket_id = 'profile-pictures'::text) AND (false)` |
   | `assets` | Privé | `(bucket_id = 'assets'::text) AND (false)` |
   | `kits` | Privé | `(bucket_id = 'kits'::text) AND (false)` |
   | `files` | Public | `(bucket_id = 'files'::text) AND (false)` |

   Pour chaque bucket, créez la policy ci-dessus pour les opérations INSERT, UPDATE et DELETE, ciblant les rôles `authenticated` et `anon`. Cela bloque l'écriture directe depuis le navigateur ; le serveur shelf passe par la clé service role.

8. **SMTP Supabase** : Authentication > Emails > SMTP, configurez un SMTP custom.
   Sans cela, le mailer par défaut de Supabase est limité à quelques emails par heure : les OTP de connexion cesseront d'arriver très vite.

### 2. Les deux surfaces SMTP

Il y a **deux configurations SMTP distinctes** dans ce déploiement :

- **SMTP côté Supabase** (Authentication > Emails > SMTP) : envoie les **emails d'OTP de connexion** (shelf déclenche `auth.signInWithOtp`, c'est le mailer Supabase qui envoie). Indispensable en production.
- **SMTP côté shelf** (variables `SMTP_*` du service) : envoie les **emails applicatifs** (invitations, réservations, onboarding).

Les deux peuvent pointer vers le même fournisseur.

### 3. Déployer sur Coolify

#### Option A (recommandée) : Lier le repo public (1 clic)

1. UI Coolify > + New > Public Repository
2. URL du repo : `https://github.com/welcoMattic/shelf-coolify`, branche `main`
3. Build pack : **Docker Compose** (le compose est à `/docker-compose.yaml`, l'emplacement par défaut)
4. Créer, puis renseigner les variables de `.env.example` dans Environment Variables, associer le domaine au service shelf (port 8080), et Deploy.

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

Note : chaque mise à jour du repo se redéploie depuis l'UI (bouton Deploy), qui re-pull le repo et l'image.

#### Option B : le script API (service "Docker Compose (Empty)")

Avec le script :

```bash
# Prévisualiser ce qui va partir, sans rien créer
./scripts/coolify-deploy-compose.py \
  --compose ./docker-compose.yaml \
  --name shelf \
  --domain shelf.example.com \
  --project "Mon Projet" \
  --dry-run

# Créer le service (sans déployer : les variables restent à renseigner)
./scripts/coolify-deploy-compose.py \
  --compose ./docker-compose.yaml \
  --name shelf \
  --domain shelf.example.com \
  --project "Mon Projet"
```

Authentification du script :

- priorité aux variables d'environnement `COOLIFY_URL` et `COOLIFY_TOKEN` ;
- sinon lecture de `~/.config/coolify/config.json` (config de la CLI `coolify`) : instance marquée default, ou l'unique instance utilisable, avec `--context` pour en choisir une explicitement.

Sans le script : UI Coolify > + New > Docker Compose Empty, collez le contenu de `docker-compose.yaml`, associez votre domaine au service `shelf` (port 8080).

Note : cette option copie le compose dans Coolify au lieu de suivre le repo. Les mises à jour du compose passent alors par `--update`.

Après création, quelle que soit l'option :

1. Service > Environment Variables : renseignez les variables listées dans `.env.example` avec les vraies valeurs copiées depuis Supabase. Les secrets `SESSION_SECRET`, `INVITE_TOKEN_SECRET` et `FINGERPRINT` sont générés par Coolify au premier déploiement (magic vars `SERVICE_BASE64_64_*`), rien à faire pour eux.
2. Déployez : bouton Deploy, ou `coolify deploy uuid <uuid-du-service>`.

### 4. Vérifier

```bash
coolify resource list
curl -sS -o /dev/null -w "%{http_code}\n" https://shelf.example.com
```

- Le healthcheck a une grace period de 90 s : laissez-lui le temps avant de conclure.
- Attendu : HTTP `200` et un statut `running (healthy)` dans Coolify.
- Créez le premier compte sur `https://shelf.example.com`, puis passez `DISABLE_SIGNUP` à `true` dans l'UI Coolify et redéployez pour fermer les inscriptions publiques.

## Pièges connus

- **OTP à 8 chiffres** : le défaut Supabase casse le login shelf. OTP Length = 6 (étape 1.5).
- **Le conteneur `migrate` s'affiche "exited"** : normal, c'est un job one-shot qui se termine après avoir appliqué les migrations.
- **Déploiement en échec tant que les variables sont vides** : si vous déployez avant d'avoir renseigné `DATABASE_URL`/`DIRECT_URL`, `migrate` sort en exit 1 (erreur de validation Prisma) et le déploiement est marqué failed. Renseignez les variables puis redéployez.
- **Statut "unknown" juste après déploiement** : le healthcheck n'a pas encore réussi, attendez la grace period.
- **Ne retirez pas `SERVICE_FQDN_SHELF_8080`** du compose : c'est ce qui déclare le routage proxy Coolify. Le domaine épinglé se réconcilie au premier déploiement.
- **Mailer Supabase par défaut rate-limité** : configurez le SMTP côté Supabase (étape 1.8), sinon les OTP cessent d'arriver après quelques connexions.
- **`?pgbouncer=true` obligatoire** dans `DATABASE_URL` avec le pooler en mode Transaction.

## Mise à jour

- **Option A (repo lié)** : chaque mise à jour (ce dépôt ou `shelf.nu:latest`) se redéploie depuis l'UI Coolify (bouton Deploy), qui re-pull le repo et l'image. Le service `migrate` applique alors les migrations éventuelles.
- **Option B (script)** : une nouvelle version de shelf.nu ou une modification du compose se déploie via :

  ```bash
  ./scripts/coolify-deploy-compose.py --compose ./docker-compose.yaml --update <uuid-du-service> --deploy
  ```

## Ressources

- Documentation upstream : [shelf.nu docs](https://github.com/shelf-nu/shelf.nu/tree/main/apps/docs) (notamment `docker.md` et `supabase-setup.md`)
- Licence : [MIT](./LICENSE)
