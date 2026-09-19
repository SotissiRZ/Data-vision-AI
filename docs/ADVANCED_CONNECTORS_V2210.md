# DataVision v2.21.0 — Connecteurs avancés

## Catalogue

| Type | Backend | Port | Sources |
|---|---|---:|---|
| PostgreSQL | psycopg / SQLAlchemy | 5432 | table, query |
| MySQL | PyMySQL / SQLAlchemy | 3306 | table, query |
| MariaDB | PyMySQL / SQLAlchemy | 3306 | table, query |
| SQLite | sqlite3 / SQLAlchemy | local | table, query |
| SQL Server | pymssql / SQLAlchemy | 1433 | table, query |
| Oracle | python-oracledb / SQLAlchemy | 1521 | table, query |
| Redshift | redshift_connector / SQLAlchemy | 5439 | table, query |
| Snowflake | Snowflake Python connector | 443 | table, query |
| Databricks SQL | Databricks SQL connector | 443 | table, query |
| BigQuery | Google Cloud BigQuery client | 443 | table, query |
| MongoDB | PyMongo | 27017 | collection |

## Fail-closed

Les SDK sont chargés au moment de l'utilisation.

Si un driver manque :

```text
test connector
  ↓
driver_missing
  ↓
aucun succès fictif
```

Le frontend affiche aussi l'état du driver dans le formulaire de création.

## Paramètres

### Snowflake

- Hôte/compte : account identifier ;
- Base : database ;
- utilisateur ;
- secret : password/token ;
- options : warehouse, schema, role.

### Databricks

- Hôte : server hostname ;
- secret : personal access token ;
- `options.http_path` obligatoire ;
- catalog/schema optionnels.

### BigQuery

- Base/Projet : GCP project ID ;
- secret vide : Application Default Credentials ;
- secret fourni : JSON de service account ;
- options : dataset, location.

### MongoDB

- Hôte, port, base ;
- username/password optionnels selon configuration ;
- options : auth_source, replica_set, tls ;
- source_kind : collection.

### SQLite

Le fichier doit déjà exister dans :

```text
DATA_ROOT/connectors/sqlite
```

Les chemins sortant de ce répertoire sont rejetés.

## Refresh

Le moteur historique DataVision reste responsable :
- watermark ;
- schema drift ;
- immutabilité des versions ;
- freshness SLA ;
- scheduled refresh ;
- observabilité.

Le support incrémental dépend également du type de colonne/clé utilisée par la
source distante. Une clé numérique ou ordonnable est recommandée.

## Lecture seule

Les sources SQL de type `query` n'acceptent qu'une requête SELECT/CTE unique.
Les mots-clés de mutation et d'administration sont rejetés.

## Limites v2.21

Cette version ne revendique pas encore :
- OAuth interactif BigQuery/Snowflake/Databricks depuis l'UI ;
- AWS IAM federation Redshift ;
- MongoDB Atlas Search ;
- CDC/log-based replication ;
- pushdown automatique de toutes les transformations DataVision ;
- édition visuelle d'un filtre MongoDB complexe.

Ces fonctions restent des extensions futures plutôt que des succès simulés.
