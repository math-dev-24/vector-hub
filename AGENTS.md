# Guide de reprise — Vector Hub

Ce fichier est destiné aux futurs agents qui interviennent sur ce dépôt. Lire
également `README.md` avant une modification importante.

## Finalité du projet

Application locale et mono-utilisateur pour nettoyer des PDF avant leur usage
dans un système RAG. Le flux attendu est :

1. importer un ou plusieurs PDF ;
2. extraire et corriger le texte page par page ;
3. supprimer les pages inutiles, y compris la première ;
4. générer des chunks pouvant traverser plusieurs pages ;
5. enrichir les chunks avec OpenAI, puis permettre leur édition manuelle ;
6. vectoriser les chunks explicitement ;
7. tester la recherche sémantique dans le laboratoire RAG ;
8. exporter les chunks nettoyés.

Les documents, métadonnées, jobs et embeddings restent dans SQLite en local.
Seuls les enrichissements et embeddings explicitement demandés utilisent
OpenAI. Ne jamais ajouter une synchronisation distante implicite.

## Architecture actuelle

- `main.py` : point d'entrée Flask.
- `app/__init__.py` : factory et assemblage des dépendances.
- `app/routes/` : contrôleurs HTTP, sans logique métier lourde.
- `models/` : modèles Pydantic et statuts métier.
- `services/` : extraction, OCR, chunking, enrichissement, vectorisation,
  recherche et orchestration des jobs.
- `repositories/` : accès SQLite et protocoles de persistance.
- `database/migrations/` : schéma SQL versionné, actuellement jusqu'à `006`.
- `workers/` : worker local séparé du processus Flask.
- `templates/`, `static/` : interface dense en Tailwind CSS v4.
- `tests/` : tests unitaires et tests des routes Flask.

Conserver cette séparation. Une route doit valider la requête, appeler un
service et produire une réponse. Les services ne doivent pas dépendre de
Flask. Les requêtes SQL restent dans les repositories.

## Commandes utiles

```powershell
uv sync
npm.cmd install
uv run python -m database migrate
npm.cmd run css:build
uv run flask --app main run --debug
```

Le worker doit être lancé dans un deuxième terminal :

```powershell
uv run python -m workers
```

Validation complète avant livraison :

```powershell
uv run python -m unittest discover -s tests -v
npm.cmd run css:build
git diff --check
```

Au moment de la rédaction, 17 tests passent. Ce nombre doit augmenter si une
fonctionnalité est ajoutée, et ne doit pas diminuer sans justification.

## Invariants métier importants

### Pages

- La page 1 peut être supprimée comme les autres.
- Le prétraitement est déterministe et prévisualisé dans `corrected_text` sans
  modifier `original_text`; seule l'action Enregistrer persiste l'aperçu.
- Les glyphes PDF privés connus (notamment `U+F02A`) sont convertis en puces
  Unicode standards uniquement dans la version corrigée.
- Après suppression, conserver la provenance vers le numéro de page PDF
  d'origine ; ne pas confondre numéro source et position d'affichage.
- Une correction de page rend les chunks existants obsolètes.
- Conserver le texte extrait et le texte corrigé séparément.
- L'OCR Tesseract ne cible actuellement que les pages sans texte corrigé.

### Chunks

- Un chunk peut contenir du texte issu de plusieurs pages.
- Chaque chunk conserve ses sources et son état de provenance.
- Une découpe manuelle produit une provenance `approximate`.
- Les champs manuellement édités ne doivent pas être écrasés silencieusement
  par une génération OpenAI.
- Toute modification du texte ou des métadonnées incluses dans l'entrée de
  l'embedding doit recalculer le hash et invalider le vecteur.

### Embeddings

- `chunk_embeddings.chunk_id` est unique.
- La revectorisation remplace l'ancien embedding via un upsert ; elle ne crée
  jamais un doublon.
- Cycle d'état attendu : `missing` → `ready`, ou `ready` → `outdated` après
  modification → `ready` après revectorisation.
- Le statut `ready` signifie « prêt à être testé dans le RAG ».
- La recherche cosinus est effectuée localement par
  `SQLiteVectorRepository.search()`.

### Suppressions

- Supprimer un document doit supprimer pages, chunks, embeddings, jobs liés et
  fichier source selon le comportement défini par le service.
- Respecter les clés étrangères et cascades SQLite.
- Ne jamais supprimer directement des fichiers ou la base pendant les tests
  manuels sans vérifier précisément la cible.

### Jobs

- Les routes HTTP mettent les traitements longs en file ; elles ne les
  exécutent pas dans Flask.
- En usage local standard, un thread worker embarqué démarre à la première
  requête HTTP. `VECTOR_HUB_AUTO_WORKER=0` permet de le désactiver au profit du
  processus `python -m workers`.
- `workers` revendique atomiquement les jobs persistés.
- L'annulation d'un job actif est coopérative aux points de progression.
- Un job interrompu est remis en attente au démarrage du worker.
- Les erreurs exposées dans l'interface doivent être utiles sans révéler de
  secrets ou la clé OpenAI.

## Base de données et migrations

Ne jamais modifier une migration déjà appliquée. Ajouter un nouveau fichier
numéroté, par exemple `006_description.sql`. Le runner vérifie les checksums et
applique les migrations dans l'ordre.

Après toute évolution de schéma :

1. ajouter la migration ;
2. mettre à jour modèles et repositories ;
3. tester une base neuve et la base locale migrée ;
4. mettre à jour l'assertion des versions dans `tests/test_pipeline.py` ;
5. lancer la suite complète.

La base réelle est `data/vector_hub.db`. Le contenu de `data/` est ignoré par
Git, à l'exception de son `.gitignore`.

## OpenAI, OCR et confidentialité

- Ne jamais lire, afficher, journaliser ou committer `.env`.
- `OPENAI_API_KEY` est nécessaire uniquement pour métadonnées, embeddings et
  requêtes du laboratoire RAG.
- La pré-correction des pages utilise par défaut le modèle léger
  `gpt-5.4-nano`, configurable via `OPENAI_CORRECTION_MODEL`.
- Les actions OpenAI doivent rester explicites dans l'interface.
- Tesseract est optionnel et local. S'il n'est pas dans le `PATH`, afficher le
  service comme indisponible sans faire échouer le reste de l'application.
- Langues OCR : `OCR_LANGUAGE`, défaut `fra+eng` ; résolution : `OCR_DPI`,
  défaut `300`.

## Interface

L'utilisateur préfère une interface dense, informative et peu décorative :

- icônes dans les boutons quand elles améliorent la lecture ;
- listes compactes de documents avec statuts et corbeille ;
- progression et logs visibles ;
- onglets Pages et Chunks sur la vue document ;
- statuts de chunks en français : prêt pour le RAG, à vectoriser, vecteur
  obsolète, erreur ;
- bouton IA compact sur chaque chunk ;
- actions globales sur l'index et actions propres au document dans sa vue.

Après une modification de classes Tailwind, toujours reconstruire
`static/css/main.css` avec `npm.cmd run css:build`.

## Points encore améliorables

- Comptabiliser précisément appels, tokens, durée et coût estimé par job.
- Ajouter une stratégie OCR pour pages faiblement extraites, pas uniquement
  vides, avec prétraitement rotation/contraste.
- Ajouter une analyse vision optionnelle pour tableaux, graphiques et schémas ;
  Tesseract n'en extrait que le texte visible.
- Ajouter pagination et filtres lorsque le nombre de documents/chunks augmente.
- Remplacer la recherche cosinus chargée en mémoire par une base vectorielle si
  le volume dépasse ce que SQLite peut traiter confortablement.
- Ajouter des sauvegardes/restaurations locales contrôlées de la base et des
  PDF sources.

## Méthode de modification recommandée

Avant de coder, inspecter les statuts et les invariants existants. Préserver les
changements utilisateur non liés. Ajouter ou adapter les tests en même temps
que l'implémentation. Vérifier les migrations, les cascades de suppression, le
cycle d'invalidation des embeddings et les deux processus Flask/worker avant de
considérer une tâche terminée.
