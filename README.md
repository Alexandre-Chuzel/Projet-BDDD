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
révision `a37a2056e593` qui rend le mot de passe obligatoire.
`u002_user_management` ajoute les rôles, la liste noire, le téléphone et
la suppression logique. Une base déjà marquée `a37a2056e593` reçoit uniquement
cette nouvelle migration ; la création de table n'est pas rejouée.

Les noms existants sont conservés dans `first_name`, les mots de passe hachés
dans `password_hash`. Le nom de famille des anciens comptes reste vide jusqu'à
sa mise à jour. Les anciens comptes deviennent des utilisateurs actifs ordinaires.

Si `users` existe sans révision Alembic, vérifier le schéma et les données avant
de reprendre l'historique. Ne pas lancer une initialisation ni un `stamp`
sans cette vérification. Un `downgrade base` supprime la table des utilisateurs.

## API disponible

- `POST /users` : inscription avec `first_name`, `last_name`, `email`, `password`
  et éventuellement `phone`. Le rôle est toujours `USER`.
- `POST /login` : formulaire OAuth2 ; le champ `username` contient l'email.
- `GET /private` : vérification d'un accès authentifié.
- `GET /users/me` : consultation du compte connecté.
- `GET /users/{user_id}` : consultation de son compte, ou de tout compte pour un administrateur.
- `GET /users` : liste administrateur, avec pagination `offset` / `limit` et
  `include_inactive=true` pour inclure les comptes désactivés.
- `POST /admin/users` : création d'un compte par un administrateur, avec rôle `USER` ou `ADMIN`.
- `PUT /users/{user_id}` : modification administrateur de l'identité et,
  facultativement, du mot de passe et du rôle.
- `PATCH /users/{user_id}/blacklist` : mise à jour administrateur avec
  `{"is_blacklisted": true}` ou `false`.
- `DELETE /users/{user_id}` : désactivation administrateur ; les données restent en base.
- `POST /users/{user_id}/restore` : réactivation administrateur.

Les mots de passe sont hachés avec Argon2. Les tokens JWT expirent après
15 minutes et identifient le compte par son ID. L'état et le rôle du compte
sont relus en base à chaque requête : un compte désactivé est refusé, et un
administrateur rétrogradé perd ses droits avec son token existant. La réactivation
permet à nouveau l'accès, y compris avec un token encore valide.
Les emails restent réservés après désactivation ; les doublons renvoient une erreur 409.

La liste noire autorise la connexion et la consultation. Son contrôle lors
d'un emprunt sera ajouté avec la gestion des emprunts, ainsi que l'interdiction
de désactiver un compte possédant des emprunts en cours. Le catalogue et les
emprunts ne sont pas encore implémentés.

## Premier administrateur

Inscrire un compte avec `POST /users`, puis promouvoir ce compte depuis le
terminal local :

```powershell
python create_admin.py alice@example.com
```

Remplacer l'email par celui du compte inscrit. La commande conserve le mot
de passe et refuse de fonctionner si un administrateur actif existe déjà.
Ensuite, seuls les administrateurs gèrent les rôles depuis l'API.
Le dernier administrateur actif ne peut pas être supprimé ou rétrogradé.
Les opérations de gestion correspondantes verrouillent les comptes avant
le contrôle et la modification, pour sérialiser les demandes concurrentes.

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
