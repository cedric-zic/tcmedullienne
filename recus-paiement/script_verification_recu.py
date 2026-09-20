import sys
import getpass
import hashlib
import hmac
from datetime import datetime


def verifier_id(encrypted_id, nom, prenom, date_recu, cle):
    """
    Vérifie l'ID d'authenticité d'un reçu.

    L'ID est au format : AAAAMMJJ.TTTTTTTTTT.<signature>
    où la signature = HMAC-SHA256(nom|prénom|date|timestamp, clé) tronqué à 16 hex.

    La vérification échoue dès qu'un seul caractère de l'ID, du nom,
    du prénom ou de la date ne correspond pas.
    """
    parties = encrypted_id.strip().split(".")
    if len(parties) != 3:
        return None
    date_id, timestamp_id, signature_id = parties
    if date_id != date_recu:
        return None
    message = f"{nom.upper()}|{prenom.upper()}|{date_id}|{timestamp_id}".encode()
    signature_attendue = hmac.new(cle, message, hashlib.sha256).hexdigest()[:16]
    if not hmac.compare_digest(signature_attendue, signature_id):
        return None
    try:
        return int(timestamp_id)
    except ValueError:
        return None


def main():
    if len(sys.argv) != 2:
        print("Usage: python script_verification_recu.py <ID_Unique>")
        print("Exemple: python script_verification_recu.py 20260920.1758371234.a1b2c3d4e5f60789")
        print("La clé sera demandée de manière sécurisée (saisie masquée).")
        sys.exit(1)

    encrypted_id = sys.argv[1]

    # Saisie des informations génériques du reçu (visibles sur le document)
    nom = input("Nom de l'adhérent : ").strip()
    prenom = input("Prénom de l'adhérent : ").strip()
    date_saisie = input("Date du reçu (JJMMAAAA ou AAAAMMJJ) : ").strip()
    if len(date_saisie) == 8 and date_saisie[:2] in ("19", "20"):
        date_recu = date_saisie  # déjà au format AAAAMMJJ
    else:
        # JJMMAAAA -> AAAAMMJJ
        try:
            date_recu = datetime.strptime(date_saisie, "%d%m%Y").strftime("%Y%m%d")
        except ValueError:
            print("❌ Date invalide. Formats acceptés : JJMMAAAA ou AAAAMMJJ.")
            sys.exit(1)

    # Clé demandée de manière sécurisée (saisie masquée).
    # C'est le seul secret nécessaire : le script fonctionne sur n'importe quel
    # poste, sans fichier cles_authenticite.py local.
    cle_str = getpass.getpass("Entrez la clé: ")
    cle = hashlib.sha256(cle_str.encode()).digest()

    timestamp = verifier_id(encrypted_id, nom, prenom, date_recu, cle)
    if timestamp:
        date_creation = datetime.fromtimestamp(timestamp).strftime("%d/%m/%Y %H:%M:%S")
        print(f"✅ Identifiant valide. Le document est un original.")
        print(f"   Reçu généré le {date_creation} pour {prenom.upper()} {nom.upper()}.")
    else:
        print(f"❌ ID invalide. Le document ne semble pas être un original. "
              f"Vérifiez l'ID, le nom, le prénom et la date saisis.")


if __name__ == "__main__":
    main()
