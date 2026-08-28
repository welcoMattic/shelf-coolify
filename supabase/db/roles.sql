-- Aligne les mots de passe des rôles internes Supabase sur POSTGRES_PASSWORD.
 \set pgpass `echo "$POSTGRES_PASSWORD"`

 ALTER USER authenticator WITH PASSWORD :'pgpass';
 ALTER USER pgbouncer WITH PASSWORD :'pgpass';
 ALTER USER supabase_auth_admin WITH PASSWORD :'pgpass';
 ALTER USER supabase_storage_admin WITH PASSWORD :'pgpass';

-- GoTrue (supabase_auth_admin) doit pouvoir recréer ces fonctions lors de
-- ses migrations ; l'image les crée avec postgres comme propriétaire.
ALTER FUNCTION auth.uid() OWNER TO supabase_auth_admin;
ALTER FUNCTION auth.role() OWNER TO supabase_auth_admin;
ALTER FUNCTION auth.email() OWNER TO supabase_auth_admin;
