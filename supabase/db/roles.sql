-- Aligne les mots de passe des rôles internes Supabase sur POSTGRES_PASSWORD.
 \set pgpass `echo "$POSTGRES_PASSWORD"`

 ALTER USER authenticator WITH PASSWORD :'pgpass';
 ALTER USER pgbouncer WITH PASSWORD :'pgpass';
 ALTER USER supabase_auth_admin WITH PASSWORD :'pgpass';
 ALTER USER supabase_functions_admin WITH PASSWORD :'pgpass';
 ALTER USER supabase_storage_admin WITH PASSWORD :'pgpass';
