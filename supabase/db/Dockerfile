FROM supabase/postgres:15.8.1.085
# Scripts d'init exécutés en superuser au premier boot du volume (initdb),
# comme dans le template Supabase de Coolify. Les bind mounts de fichiers
# n'étant pas disponibles dans le build pack, ils sont bakés dans l'image.
COPY roles.sql /docker-entrypoint-initdb.d/init-scripts/99-roles.sql
COPY jwt.sql /docker-entrypoint-initdb.d/init-scripts/99-jwt.sql
