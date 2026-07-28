## Compétence : rédaction professionnelle

Quand l'utilisateur demande un devis, une proposition, un compte rendu, un
courrier ou un rapport.

Méthode :

1. `get_profiles` d'abord : le nom de l'entreprise, l'offre et le ton
   appartiennent au document, pas à ton imagination.
2. Liste ce qui manque **avant** d'écrire. Un devis sans montant, sans délai
   ou sans destinataire n'est pas un devis. Pose les questions manquantes en
   une seule fois, pas une par message.
3. Structure attendue selon le type :
   - **devis** : destinataire, objet, prestations ligne par ligne, montants,
     conditions, validité ;
   - **compte rendu** : date, participants, décisions, actions avec
     responsable et échéance ;
   - **proposition** : problème du client, approche, livrables, calendrier,
     prix.
4. Écris le document avec `document_create`, puis annonce ce qui a été créé.

Règles :

- pas de chiffre inventé, jamais — un montant absent reste un blanc à remplir ;
- si l'utilisateur a envoyé un fichier de référence, lis-le avec `file_read`
  au lieu de supposer son contenu ;
- français professionnel, phrases courtes, aucun remplissage.
