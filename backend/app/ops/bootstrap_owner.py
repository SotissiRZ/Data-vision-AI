from __future__ import annotations

import argparse
import getpass

from app.services.auth_service import bootstrap, owner_count
from app.services.metadata_store import init_metadata_store


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the first DataVision owner from the server console.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--display-name", default="Administrateur")
    parser.add_argument("--organization", default="DataVision Organisation")
    args = parser.parse_args()

    init_metadata_store()
    if owner_count() > 0:
        raise SystemExit("DataVision est déjà initialisé. Utilisez la connexion ou l'administration des membres.")
    password = getpass.getpass("Mot de passe administrateur (8 caractères minimum): ")
    confirmation = getpass.getpass("Confirmez le mot de passe: ")
    if password != confirmation:
        raise SystemExit("Les mots de passe ne correspondent pas.")
    out = bootstrap(args.email, password, args.display_name, args.organization)
    print(f"Premier propriétaire créé: {out['user']['email']}")
    print(f"Workspace principal: {out['workspace_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
