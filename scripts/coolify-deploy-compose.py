#!/usr/bin/env python3
"""Déploie shelf.nu sur Coolify via un docker-compose custom.

La CLI communautaire `coolify` ne sait pas créer un service "Docker Compose
(Empty)" (elle exige un type one-click). On passe donc par l'API documentée
`POST /api/v1/services`, où `type` est facultatif et `docker_compose_raw`
(encodé en base64) contient le compose.

Exemples:
  # Création avec le fichier docker-compose.yaml
  ./scripts/coolify-deploy-compose.py --compose ./docker-compose.yaml --name shelf \\
      --domain shelf.example.com --project "Mon Projet"

  # Prévisualiser le payload sans rien créer
  ./scripts/coolify-deploy-compose.py --compose ./docker-compose.yaml --name shelf \\
      --domain shelf.example.com --project "Mon Projet" --dry-run

  # Mettre à jour le compose d'un service existant et redéployer
  ./scripts/coolify-deploy-compose.py --compose ./docker-compose.yaml --update <uuid> --deploy

Authentification:
  Priorité 1: variables d'environnement COOLIFY_URL et COOLIFY_TOKEN.
  Priorité 2: ~/.config/coolify/config.json (config de la CLI coolify),
  en prenant l'instance marquée default, ou l'unique instance utilisable.
  --context permet de choisir une instance précise dans config.json.
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request

CONFIG = os.path.expanduser("~/.config/coolify/config.json")


def load_context(name):
    """Charge une instance Coolify (fqdn + token) depuis la config de la CLI.

    Sans --context : instance marquée default dans config.json, ou l'unique
    instance utilisable. En cas d'ambiguïté, on refuse plutôt que de deviner.
    """
    with open(CONFIG) as f:
        cfg = json.load(f)
    inst = cfg["instances"]
    items = list(inst.values()) if isinstance(inst, dict) else inst
    usable = [v for v in items if (v.get("fqdn") or "").strip() and v.get("token")]
    names = [v.get("name") for v in usable]
    if name is not None:
        match = [v for v in usable if name.lower() in (v.get("name") or "").lower()]
        if not match:
            sys.exit(f"Contexte '{name}' introuvable ou sans token dans {CONFIG}. Dispo: {names}")
        chosen = match[0]
    else:
        defaults = [v for v in usable if v.get("default")]
        if defaults:
            chosen = defaults[0]
        elif len(usable) == 1:
            chosen = usable[0]
        else:
            sys.exit(f"Plusieurs instances dans {CONFIG}, précise --context. Dispo: {names}")
    return chosen["fqdn"].rstrip("/"), chosen["token"]


def api(fqdn, tok, method, path, body=None):
    """Appel API Coolify."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        fqdn + path, data=data, method=method,
        headers={"Authorization": "Bearer " + tok, "Accept": "application/json",
                 **({"Content-Type": "application/json"} if data else {})})
    try:
        r = urllib.request.urlopen(req, timeout=90)
        raw = r.read().decode()
        return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        sys.exit(f"API {method} {path} -> HTTP {e.code}: {e.read().decode()[:500]}")


def resolve(fqdn, tok, args):
    """Résout les UUID serveur, projet et environnement à partir de leurs noms."""
    _, servers = api(fqdn, tok, "GET", "/api/v1/servers")
    if args.server:
        srv = next((s for s in servers if args.server in (s.get("uuid"), s.get("name"))), None)
        if not srv:
            sys.exit(f"Serveur '{args.server}' introuvable. Dispo: {[s.get('name') for s in servers]}")
    elif len(servers) == 1:
        srv = servers[0]
    else:
        sys.exit(f"Plusieurs serveurs, précise --server: {[s.get('name') for s in servers]}")
    _, projects = api(fqdn, tok, "GET", "/api/v1/projects")
    proj = next((p for p in projects if args.project in (p.get("uuid"), p.get("name"))), None)
    if not proj:
        sys.exit(f"Projet '{args.project}' introuvable. Dispo: {[p.get('name') for p in projects]}")
    _, pdetail = api(fqdn, tok, "GET", f"/api/v1/projects/{proj['uuid']}")
    envs = pdetail.get("environments", [])
    env = next((e for e in envs if args.env in (e.get("uuid"), e.get("name"))), None)
    if not env:
        sys.exit(f"Environnement '{args.env}' introuvable. Dispo: {[e.get('name') for e in envs]}")
    return srv["uuid"], proj["uuid"], env["name"], env["uuid"]


def main():
    ap = argparse.ArgumentParser(description="Déploie un docker-compose custom sur Coolify.")
    ap.add_argument("--compose", required=True, help="Chemin du fichier docker-compose (ex: ./docker-compose.yaml)")
    ap.add_argument("--name", help="Nom du service (requis en création)")
    ap.add_argument("--update", metavar="UUID", help="UUID d'un service existant à mettre à jour (PATCH)")
    ap.add_argument("--domain", help="FQDN à épingler, ex: shelf.example.com")
    ap.add_argument("--service-key", help="Clé du service (dans le compose) qui reçoit le domaine (défaut: --name)")
    ap.add_argument("--context", default=None, help="Contexte dans config.json (défaut: instance default, ou l'unique instance)")
    ap.add_argument("--project", required=True, help="Nom ou UUID du projet Coolify")
    ap.add_argument("--env", default="production", help="Nom ou UUID de l'environnement (défaut: production)")
    ap.add_argument("--server", help="Nom ou UUID du serveur (auto si un seul)")
    ap.add_argument("--deploy", action="store_true", help="Déployer immédiatement")
    ap.add_argument("--dry-run", action="store_true", help="Résout tout et affiche le payload, sans muter")
    args = ap.parse_args()

    if not args.update and not args.name:
        ap.error("--name est requis en création (ou utilise --update <uuid>)")

    with open(args.compose, "rb") as f:
        compose = f.read()
    has_build = any(line.split("#", 1)[0].strip().startswith("build:")
                    for line in compose.decode(errors="replace").splitlines())
    if has_build:
        print("AVERTISSEMENT: le compose contient une clé 'build:' (service Empty = pull-only).")

    b64 = base64.b64encode(compose).decode()

    env_url, env_tok = os.environ.get("COOLIFY_URL"), os.environ.get("COOLIFY_TOKEN")
    if env_url and env_tok:
        fqdn, tok = env_url.rstrip("/"), env_tok
    else:
        fqdn, tok = load_context(args.context)

    if args.update:
        payload = {"docker_compose_raw": b64, "instant_deploy": bool(args.deploy)}
        path, method = f"/api/v1/services/{args.update}", "PATCH"
        print(f"MODE   : update service {args.update}")
    else:
        srv, proj, env_name, env_uuid = resolve(fqdn, tok, args)
        payload = {"name": args.name, "project_uuid": proj, "environment_name": env_name,
                   "environment_uuid": env_uuid, "server_uuid": srv,
                   "docker_compose_raw": b64, "instant_deploy": bool(args.deploy)}
        if args.domain:
            key = args.service_key or args.name
            host = args.domain
            for pre in ("https://", "http://"):
                if host.startswith(pre):
                    host = host[len(pre):]
            payload["urls"] = [{"name": key, "url": f"https://{host.strip('/')}"}]
        path, method = "/api/v1/services", "POST"
        print(f"MODE   : create '{args.name}'  server={srv}  project={proj}  env={env_name}")

    if args.domain:
        print(f"DOMAIN : https://{args.domain}")
    print(f"DEPLOY : {bool(args.deploy)}")

    if args.dry_run:
        preview = {k: (f"<base64 {len(v)} chars>" if k == "docker_compose_raw" else v) for k, v in payload.items()}
        print("DRY-RUN payload:")
        print(json.dumps(preview, indent=2, ensure_ascii=False))
        return

    status, resp = api(fqdn, tok, method, path, payload)
    print(f"OK HTTP {status}: {json.dumps(resp, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
