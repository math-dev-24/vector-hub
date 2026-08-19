# Migrations SQLite

Ajouter les évolutions de schéma sous la forme `002_description.sql`,
`003_description.sql`, etc. Le runner exécute chaque version une seule fois et
enregistre son application dans la table `schema_migrations`.
