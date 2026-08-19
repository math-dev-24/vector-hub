# OCR Pipe

Pipeline Flask permettant d'extraire, corriger, découper, enrichir et
vectoriser des documents PDF pour un usage RAG.

## Démarrage

```powershell
uv sync
npm.cmd install
npm.cmd run css:build
uv run flask --app main run --debug
```

Un worker local embarqué démarre automatiquement à la première requête. Pour
isoler les traitements dans un processus dédié, désactiver ce worker et lancer
un second terminal :

```powershell
$env:OCR_PIPE_AUTO_WORKER = "0"
uv run python -m workers
```

Pour compiler Tailwind pendant le développement :

```powershell
npm.cmd run css:watch
```

## Configuration OpenAI

Les actions de génération des métadonnées et de vectorisation sont toujours
déclenchées manuellement depuis l'interface.

```powershell
$env:OPENAI_API_KEY = "..."
$env:OPENAI_METADATA_MODEL = "gpt-5-mini"
$env:OPENAI_CORRECTION_MODEL = "gpt-5.4-nano"
$env:OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
$env:FLASK_SECRET_KEY = "une-valeur-secrete"
```

## Publication vers une base vectorielle distante

SQLite reste la source locale de vérité. Le port de publication accepte des
adaptateurs Pinecone et Qdrant, sélectionnés au démarrage.

Pinecone (index dense existant, embeddings produits par OCR Pipe) :

```powershell
$env:REMOTE_VECTOR_PROVIDER = "pinecone"
$env:PINECONE_API_KEY = "..."
$env:PINECONE_INDEX_HOST = "https://votre-index.svc.pinecone.io"
$env:PINECONE_NAMESPACE = "ocr-pipe-experiments-v1"
```

Qdrant :

```powershell
$env:REMOTE_VECTOR_PROVIDER = "qdrant"
$env:QDRANT_URL = "https://votre-instance-qdrant"
$env:QDRANT_API_KEY = "..."
$env:QDRANT_COLLECTION = "ocr-pipe-experiments-v1"
```

La collection Qdrant est créée au premier envoi. L'index Pinecone doit déjà
exister avec la dimension du modèle OpenAI utilisé. Les publications sont des
upserts idempotents et leur hash est suivi séparément pour chaque fournisseur,
index et namespace ; une modification ne déclenche jamais de synchronisation
distante implicite.

La base SQLite est créée dans `data/ocr_pipe.db`. Les changements de schéma
sont versionnés dans `database/migrations/` et appliqués automatiquement au
démarrage. Les anciens JSON présents dans `DATA/extracted/` ou
`data/extracted/` sont importés automatiquement s'ils existent encore.

```powershell
uv run python -m database migrate
uv run python -m database status
```

Les traitements passent par une file de jobs persistante. La page `/activity`
affiche les jobs, erreurs, métriques et événements du pipeline. Au démarrage,
le worker remet automatiquement dans la file les jobs interrompus. Pour ne
traiter qu'un seul job (utile pour les scripts et les tests) :

```powershell
uv run python -m workers --once
```

## OCR et recherche RAG locale

L'OCR est optionnel et s'exécute localement avec Tesseract. Si l'exécutable
`tesseract` est disponible dans le `PATH`, l'interface propose d'OCRiser les
pages sans texte. Les variables `OCR_LANGUAGE` (défaut `fra+eng`) et `OCR_DPI`
(défaut `300`) permettent de régler le traitement.

Les embeddings sont conservés dans SQLite. La page `/rag` permet de tester une
requête contre tous les documents ou un document précis. Seul le calcul de
l'embedding de la requête utilise OpenAI ; la recherche cosinus et les données
restent locales.

## Organisation

- `app/routes/` : contrôleurs HTTP Flask ;
- `models/` : modèles métier Pydantic ;
- `services/` : extraction, chunking, enrichissement et vectorisation ;
- `repositories/` : persistance SQLite ;
- `database/migrations/` : migrations SQL versionnées ;
- `templates/` et `static/` : interface Tailwind CSS.
