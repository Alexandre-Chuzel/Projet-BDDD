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

`c003_catalogue` ajoute `authors`, `books`, `book_authors` et `book_copies`,
avec leurs clés étrangères, contraintes et index. Elle ne modifie pas les
comptes. Son annulation supprime le catalogue et ses exemplaires.

`l004_loans` ajoute les emprunts, leurs dates de clôture et un index unique
qui interdit deux emprunts en cours sur le même exemplaire. Son annulation
supprime les emprunts ; les comptes et le catalogue sont conservés.

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

La liste noire autorise la connexion, la consultation et le retour des livres,
mais interdit les nouveaux emprunts. Un compte possédant un emprunt en cours
ne peut pas être désactivé.

## Catalogue

Les routes de consultation exigent une connexion. Les routes de création,
modification, suppression et gestion des exemplaires exigent le rôle `ADMIN`.

- `GET /authors` et `GET /authors/{author_id}` : consultation des auteurs.
  La liste accepte `name`, `offset` et `limit`.
- `POST /authors`, `PUT /authors/{author_id}` et `DELETE /authors/{author_id}` :
  gestion des auteurs. Un auteur associé à un livre ne peut pas être supprimé.
- `GET /books` : catalogue, avec les filtres cumulables `title`, `author` et
  `genre`, ainsi que `offset` et `limit`. La recherche ne distingue pas la casse.
- `GET /books/{book_id}` : informations du livre et de ses auteurs.
- `POST /books` et `PUT /books/{book_id}` : gestion d'une édition, avec au
  moins un identifiant dans `author_ids`.
- `DELETE /books/{book_id}` et `POST /books/{book_id}/restore` : désactivation
  et réactivation. Les exemplaires et les liens vers les auteurs sont conservés.
- `GET /books/{book_id}/copies` : liste administrateur des exemplaires,
  avec `offset` et `limit`.
- `POST /books/{book_id}/copies` : ajout d'un exemplaire avec `inventory_code`
  et éventuellement `service_status` (par défaut `IN_SERVICE`).
- `PATCH /books/{book_id}/copies/{copy_id}` : modification de l'état de service.
- `DELETE /books/{book_id}/copies/{copy_id}` : retrait logique avec l'état `WITHDRAWN`.

Les états sont `IN_SERVICE`, `DAMAGED`, `LOST` et `WITHDRAWN`. Un numéro
d'inventaire est normalisé en majuscules et reste réservé après retrait.
L'ISBN est facultatif ; les formats ISBN-10 et ISBN-13 sont validés et stockés
en ISBN-13 pour identifier une édition de manière unique.

Un utilisateur voit `is_available`. Un administrateur reçoit aussi `total_stock`
et `available_stock`, et peut consulter les livres désactivés avec
`include_inactive=true`. Un livre désactivé est masqué aux utilisateurs.

Les quantités sont calculées depuis les exemplaires : les exemplaires retirés
ne comptent plus dans le total ; seuls ceux en service sans emprunt en cours sont disponibles.
Les exemplaires perdus ou abîmés restent dans l'inventaire, sans être disponibles.
La désactivation d'un livre ayant un emprunt en cours est refusée, tout comme
le retrait ou le changement d'état d'un exemplaire prêté.

Exemple de création d'un livre après création de son auteur :

```json
{
  "title": "Les Misérables",
  "genre": "Roman",
  "author_ids": [1],
  "publication_date": "1862-01-01"
}
```

Puis ajouter les exemplaires avec `POST /books/{book_id}/copies`, par exemple
`{"inventory_code": "EX-001"}`. Une fiche sans exemplaire est indisponible.

## Emprunts et retours

- `POST /loans` avec `{"book_id": 1}` : emprunt par le compte connecté.
  L'API choisit un exemplaire en service et disponible. Un livre désactivé
  ou sans exemplaire disponible renvoie 409 ; la liste noire renvoie 403.
- `POST /loans/{loan_id}/return` : retour de son propre emprunt.
  Un emprunt appartenant à un autre compte renvoie 403 ; un emprunt déjà
  clôturé renvoie 409. L'exemplaire redevient disponible.
- `GET /loans/me` : historique personnel, avec `active_only`, `offset` et `limit`.
- `GET /loans` : historique administrateur, avec les mêmes paramètres et
  les filtres facultatifs `user_id` et `book_id`.
- `GET /loans/{loan_id}` : détail d'un emprunt personnel, ou de tout emprunt
  pour un administrateur.

Chaque prêt concerne un exemplaire identifié par son numéro d'inventaire.
Plusieurs exemplaires d'un livre permettent plusieurs prêts simultanés.
Le retour conserve l'emprunt dans l'historique, avec sa date et son auteur.
Les dates sont stockées et renvoyées en UTC, sans indication de fuseau.

Les emprunts et retours verrouillent le compte, le livre puis l'exemplaire
dans leur transaction. L'index unique protège aussi la base contre deux
emprunts en cours sur le même exemplaire. La disponibilité est recalculée
depuis les exemplaires et les emprunts à chaque consultation.

## Supervision administrateur

- `POST /admin/loans` avec `{"user_id": 2, "book_id": 1}` : enregistrer
  un emprunt pour un compte actif. Les contrôles de liste noire, de livre actif
  et de disponibilité s'appliquent également. L'emprunt apparaît dans
  l'historique du bénéficiaire.
- `POST /admin/loans/{loan_id}/close` avec `{"copy_status": "IN_SERVICE"}` :
  enregistrer un retour en bon état pour le compte concerné.
- La même route avec `{"copy_status": "DAMAGED"}` enregistre un retour abîmé ;
  l'emprunt est clôturé avec `RETURNED`, mais l'exemplaire reste indisponible.
- Avec `{"copy_status": "LOST"}`, elle clôture pour perte avec le motif `LOST`.
  L'exemplaire reste dans le stock total et ne peut plus être emprunté.

Ces routes sont réservées aux administrateurs. La clôture conserve leur
identifiant dans `closed_by_id`. Elle reste possible pour un bénéficiaire sur
liste noire ou désactivé, mais un emprunt déjà clôturé est refusé avec 409.
Un retour personnel continue à passer par `/loans/{loan_id}/return`.

Après réparation ou récupération, l'administrateur remet l'exemplaire en
service avec `PATCH /books/{book_id}/copies/{copy_id}` et
`{"service_status": "IN_SERVICE"}`. L'ancien emprunt reste clôturé ; un nouveau
prêt crée une nouvelle entrée dans l'historique.

La clôture et le changement d'état sont enregistrés dans une même transaction.
Le schéma de `l004_loans` contient déjà les informations nécessaires à cette
supervision ; aucune migration supplémentaire n'est nécessaire.

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
Un test manuel vérifie les emprunts concurrents sur la base Oracle configurée :

```powershell
python tests/oracle_concurrency.py
```

Il crée des données dédiées, lance deux demandes simultanées pour un seul
exemplaire et attend un succès 201 et un refus 409. Il vérifie aussi la
contrainte unique, deux clôtures simultanées (retour personnel et retour abîmé
administrateur, avec un succès 200 et un refus 409), puis le réemprunt.
Ses données sont supprimées
dans un bloc `finally`. Les migrations doivent avoir été appliquées avant
son lancement.

## Docker

```powershell
docker build -t bibliotheque-api .
docker run --rm --env-file .env -p 8000:8000 bibliotheque-api
```

La connexion Oracle dans le conteneur doit utiliser une adresse accessible
depuis Docker ; pour un port Oracle publié sur la machine hôte avec Docker
Desktop, utiliser `DATABASE_HOST=host.docker.internal`. Appliquer les migrations
avant de démarrer l'API ; l'image ne les exécute pas automatiquement.
