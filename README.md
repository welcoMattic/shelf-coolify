# shelf-coolify

Déploie [shelf.nu](https://github.com/shelf-nu/shelf.nu) (gestion d'inventaire open source) sur une instance [Coolify](https://coolify.io) auto-hébergée, sous forme d'un service "Docker Compose (Empty)", avec Supabase Cloud pour la base de données, l'authentification et le stockage.

## Architecture

> L'image officielle shelf.nu ne supporte **pas** Supabase self-hosted (position upstream).
> Ce dépôt suit donc le chemin supporté : application sur Coolify + projet Supabase Cloud (le free tier suffit).
> Les migrations Prisma sont appliquées automatiquement à chaque déploiement via le service one-shot `migrate` (vérifié : `npx prisma@6.19.3 migrate deploy` fonctionne dans l'image GHCR).

## Prérequis

- Une instance [Coolify](https://coolify.io) v4.x et un token API (permissions write + deploy)
- Un compte [Supabase](https://supabase.com) et un projet créé
- Un fournisseur SMTP (indispensable en production, voir "Les deux surfaces SMTP")
- Python 3 pour le script de déploiement (stdlib seule)

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

### 3. Créer le service sur Coolify

Avec le script (recommandé) :

```bash
# Prévisualiser ce qui va partir, sans rien créer
./scripts/coolify-deploy-compose.py \
  --compose ./shelf.yml \
  --name shelf \
  --domain shelf.example.com \
  --project "Mon Projet" \
  --dry-run

# Créer le service (sans déployer : les variables restent à renseigner)
./scripts/coolify-deploy-compose.py \
  --compose ./shelf.yml \
  --name shelf \
  --domain shelf.example.com \
  --project "Mon Projet"
```

Authentification du script :

- priorité aux variables d'environnement `COOLIFY_URL` et `COOLIFY_TOKEN` ;
- sinon lecture de `~/.config/coolify/config.json` (config de la CLI `coolify`) : instance marquée default, ou l'unique instance utilisable, avec `--context` pour en choisir une explicitement.

Sans le script : UI Coolify > + New > Docker Compose Empty, collez le contenu de `shelf.yml`, associez votre domaine au service `shelf` (port 8080).

Après création du service, quelle que soit la méthode :

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
- **Statut "unknown" juste après déploiement** : le healthcheck n'a pas encore réussi, attendez la grace period.
- **Ne retirez pas `SERVICE_FQDN_SHELF_8080`** du compose : c'est ce qui déclare le routage proxy Coolify. Le domaine épinglé se réconcilie au premier déploiement.
- **Mailer Supabase par défaut rate-limité** : configurez le SMTP côté Supabase (étape 1.8), sinon les OTP cessent d'arriver après quelques connexions.
- **`?pgbouncer=true` obligatoire** dans `DATABASE_URL` avec le pooler en mode Transaction.

## Mise à jour

- **Nouvelle version de shelf.nu** : un redéploiement Coolify re-pull `ghcr.io/shelf-nu/shelf.nu:latest`, et le service `migrate` applique les migrations éventuelles.
- **Modification du compose** :

  ```bash
  ./scripts/coolify-deploy-compose.py --compose ./shelf.yml --update <uuid-du-service> --deploy
  ```

## Ressources

- Documentation upstream : [shelf.nu docs](https://github.com/shelf-nu/shelf.nu/tree/main/apps/docs) (notamment `docker.md` et `supabase-setup.md`)
- Licence : [MIT](./LICENSE)
