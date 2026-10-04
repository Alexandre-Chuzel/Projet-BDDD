"""Promotion locale d'un compte existant pour créer le premier administrateur."""
import argparse

from sqlalchemy import func, select

from database import SessionLocal
from models import User


def main():
    parser = argparse.ArgumentParser(description='Créer le premier administrateur à partir d’un compte actif.')
    parser.add_argument('email', help='Email du compte inscrit à promouvoir')
    args = parser.parse_args()
    with SessionLocal() as db:
        # Même verrou que les routes qui protègent le dernier administrateur.
        db.scalars(select(User.id).order_by(User.id).with_for_update()).all()
        existing_admin = db.scalar(select(User.id).where(User.role == 'ADMIN', User.is_active == True))
        if existing_admin is not None:
            parser.error('Un administrateur actif existe déjà. Utiliser ensuite les routes administrateur.')
        user = db.scalar(select(User).where(func.lower(User.email) == args.email.strip().lower()))
        if user is None or not user.is_active:
            parser.error('Inscrire un compte actif avec cet email avant de le promouvoir.')
        user.role = 'ADMIN'
        db.commit()
        print('Premier administrateur créé ; le mot de passe du compte est conservé.')


if __name__ == '__main__':
    main()
