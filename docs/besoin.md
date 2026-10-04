# Besoin fonctionnel

## Objectif

Créer une API de bibliothèque pour gérer un catalogue, ses exemplaires et les
emprunts des utilisateurs. La base cible est Oracle ; l'API utilise FastAPI,
SQLAlchemy, Alembic et Pydantic, avec Swagger pour documenter les routes.

## Priorité 1

### Utilisateur

- S'inscrire puis s'authentifier avec son email et son mot de passe.
- Rechercher des livres par titre, auteur ou genre.
- Consulter les informations d'un livre et sa disponibilité.
- Emprunter un exemplaire disponible d'un livre.
- Retourner l'exemplaire correspondant à l'un de ses emprunts en cours.
- Consulter ses emprunts en cours et son historique personnel.

L'inscription et la connexion sont accessibles sans authentification.
Les autres fonctionnalités exigent une authentification.

### Administrateur

L'administrateur possède également les fonctions de l'utilisateur et peut :

- Ajouter, modifier, supprimer et lister les utilisateurs.
- Placer un utilisateur sur liste noire ou le retirer de cette liste.
- Ajouter, modifier, supprimer et lister les livres et leurs auteurs.
- Gérer les exemplaires : ajout, retrait, déclaration de dommage et remise en service.
- Consulter les emprunts en cours et les historiques de tous les utilisateurs.
- Consulter les quantités totale et disponible de chaque livre et les états de ses exemplaires.

### Informations du catalogue et des utilisateurs

Un utilisateur possède un prénom, un nom, un email et un téléphone facultatif.
Un livre possède un titre, un ou plusieurs auteurs, une date de publication,
une description, un genre, un éditeur et un ISBN facultatif. La date de publication
peut être absente. Les données facultatives sont validées lorsqu'elles sont
renseignées. Chaque exemplaire possède un numéro d'inventaire unique.

## Priorité 2

L'administrateur peut enregistrer un emprunt pour un utilisateur, enregistrer
son retour, y compris en état abîmé, et clôturer un emprunt pour perte. Les
contrôles de disponibilité et de liste noire s'appliquent également aux emprunts
enregistrés par l'administrateur. L'auteur de chaque clôture est conservé.
La consultation globale des emprunts appartient à la priorité 1.

## Règles métier

1. Un livre représente une édition. Plusieurs exemplaires physiques peuvent
   appartenir au même livre ; un emprunt concerne un seul exemplaire identifié.
2. Un exemplaire est disponible si son livre est actif, s'il est en service
   et s'il n'a aucun emprunt en cours.
3. La quantité totale compte les exemplaires non retirés. La quantité disponible
   compte uniquement les exemplaires en service sans emprunt en cours.
4. Un emprunt est en cours tant que sa date de clôture est vide. Une clôture
   possède une date, un motif (`RETURNED` ou `LOST`) et l'utilisateur qui l'a
   enregistrée. Sa date ne peut pas précéder le début de l'emprunt.
5. Un exemplaire ne peut pas avoir plusieurs emprunts en cours. Deux demandes
   simultanées sur le dernier exemplaire disponible permettent au plus un emprunt.
   Les contrôles et l'enregistrement se font dans une même transaction.
6. Un utilisateur retourne uniquement un exemplaire correspondant à l'un de
   ses emprunts en cours. Un second retour est refusé et ne modifie pas le stock.
7. Un retour en bon état remet l'exemplaire à disposition. Un exemplaire retourné
   abîmé reste indisponible jusqu'à sa remise en service par l'administrateur.
8. La clôture pour perte est réservée à l'administrateur et ne constitue pas
   un retour. L'exemplaire reste indisponible. S'il est retrouvé, il peut être
   remis en service sans rouvrir l'ancien emprunt.
9. Un exemplaire prêté ne peut pas être retiré. Un exemplaire retiré est conservé
   pour l'historique et exclu des quantités du stock.
10. La liste noire interdit les nouveaux emprunts, mais autorise la connexion,
    la consultation et les retours.
11. La suppression d'un utilisateur ou d'un livre est refusée tant qu'il possède
    des emprunts en cours. La suppression est logique pour conserver les
    historiques. Un compte supprimé ne peut plus se connecter ni utiliser un
    ancien token ; un livre supprimé est retiré du catalogue utilisable.
12. Les mots de passe sont hachés et ne sont jamais renvoyés par l'API.
    L'inscription crée toujours un utilisateur ordinaire.
13. Un utilisateur ne peut pas consulter l'historique ou gérer le compte d'un
    autre utilisateur. Les fonctions de gestion sont réservées à l'administrateur.
14. Le dernier administrateur actif ne peut pas être supprimé ou rétrogradé.
15. Plusieurs emprunts du même titre par un utilisateur sont permis s'il reste
    des exemplaires. Aucune échéance ni limite du nombre d'emprunts n'est imposée.
16. Un livre possède au moins un auteur. La suppression de sa dernière association
    avec un auteur est refusée. Un auteur référencé ne peut pas être supprimé physiquement.
17. Les numéros d'inventaire sont uniques et ne sont pas réutilisés après retrait.
    L'ISBN, lorsqu'il est renseigné, est normalisé et unique par édition.
18. Le livre d'un exemplaire déjà associé à un emprunt ne peut pas être modifié,
    afin de préserver la cohérence de l'historique.

## Exemples de validation à réaliser

- Deux exemplaires disponibles permettent deux emprunts ; le troisième est refusé.
- Un retour rend exactement un exemplaire disponible.
- Un livre avec trois exemplaires, dont un prêté et un abîmé, a un stock total
  de 3 et un stock disponible de 1.
- Deux emprunts concurrents du dernier exemplaire donnent un succès et un refus.
- Un double retour et le retour de l'emprunt d'un autre utilisateur sont refusés.
- Un retour abîmé clôture l'emprunt sans augmenter le stock disponible.
- Une perte clôture l'emprunt avec le bon motif sans rendre l'exemplaire disponible.
- Un utilisateur sur liste noire peut rendre un exemplaire, mais pas en emprunter.
- Le retrait d'un exemplaire prêté et la suppression d'un compte ou d'un livre
  avec un emprunt actif sont refusés.
- Les suppressions logiques et les retraits conservent l'historique.
- Un utilisateur ordinaire ne voit pas les quantités et ne peut pas appeler
  les fonctions administrateur.
- La suppression ou rétrogradation du dernier administrateur actif est refusée,
  y compris lors de demandes concurrentes.
- Plusieurs auteurs peuvent être associés à un livre ; retirer son dernier auteur est refusé.
- Une erreur pendant un emprunt, un retour ou une clôture pour perte annule toute la transaction.
