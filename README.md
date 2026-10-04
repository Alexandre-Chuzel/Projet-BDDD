# Projet 5BDDD — Bibliothèque

API de gestion d'une bibliothèque avec Oracle, FastAPI, SQLAlchemy, Alembic
et Pydantic. Les utilisateurs recherchent, empruntent et rendent des livres ;
les administrateurs gèrent le catalogue et les comptes.

- [Besoin et règles métier](docs/besoin.md)
- [MCD et modèle relationnel](docs/modelisation.md)

## Installation

Activer un environnement virtuel Python 3.11 ou supérieur, puis installer les
dépendances. Pour inclure les outils de test :

```powershell
python -m pip install -r requirements-dev.txt
```

Pour une installation sans les outils de test, utiliser `requirements.txt`.
Copier `.env.exemple` vers `.env` si ce fichier n'existe pas, renseigner la
connexion Oracle et définir `SECRET_KEY` avec une clé aléatoire d'au moins
32 octets. La commande de génération figure dans `.env.exemple`.

## Base de données et démarrage

```powershell
python -m alembic current
python -m alembic upgrade head
python -m uvicorn main:app --reload
```

Swagger est disponible sur `http://127.0.0.1:8000/docs`.
Le démarrage de l'API ne crée ni ne modifie les tables : seul Alembic gère le schéma.

La migration `b001_initial_users` crée `users` sur une base vide, avant la
révision `a37a2056e593` qui rend le mot de passe obligatoire. Une base déjà
marquée `a37a2056e593` conserve sa révision et ses données ; la migration de
création n'y est pas rejouée. La révision historique conserve son opération
Oracle et utilise le mode batch pour les tests SQLite.

Si `users` existe sans révision Alembic, vérifier le schéma et les données avant
de reprendre l'historique. Ne pas lancer une initialisation ni un `stamp`
sans cette vérification. Un `downgrade base` supprime la table des utilisateurs.

## API disponible

- `POST /users` : inscription avec `name`, `email` et `password`.
- `POST /login` : formulaire OAuth2 ; le champ `username` contient l'email.
- `GET /private` : vérification d'un accès authentifié.
- `GET`, `PUT`, `DELETE /users/{user_id}` : accès au compte de l'utilisateur connecté.

Les mots de passe sont hachés avec Argon2. Les tokens JWT expirent après
15 minutes et identifient le compte par son ID. Un compte supprimé ne peut
plus utiliser son token. Les emails sont normalisés ; les doublons renvoient
une erreur 409.

Le socle utilise encore le champ `name` et une suppression physique des comptes.
Les rôles administrateur, la suppression logique, le catalogue et les emprunts
seront ajoutés avec leurs migrations. La liste globale des utilisateurs est
désactivée jusqu'à l'ajout des droits administrateur.

## Tests

```powershell
python -m pytest -q
```

Les tests API utilisent une base SQLite temporaire et une clé de test ; ils
n'accèdent pas à la base Oracle du projet. Les tests de migration vérifient
l'initialisation, la conservation des données et le SQL généré pour Oracle.
Les vérifications sur Oracle réel restent nécessaires pour valider les
particularités du moteur et les futurs emprunts concurrents.

## Docker

```powershell
docker build -t bibliotheque-api .
docker run --rm --env-file .env -p 8000:8000 bibliotheque-api
```

La connexion Oracle dans le conteneur doit utiliser une adresse accessible
depuis Docker ; pour un port Oracle publié sur la machine hôte avec Docker
Desktop, utiliser `DATABASE_HOST=host.docker.internal`. Appliquer les migrations
avant de démarrer l'API ; l'image ne les exécute pas automatiquement.
