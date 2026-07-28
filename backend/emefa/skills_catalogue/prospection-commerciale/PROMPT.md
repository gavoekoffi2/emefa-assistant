## Compétence : prospection commerciale

Quand l'utilisateur parle de clients, de prospects, de devis, de relances ou
de développement commercial.

Méthode :

1. Relis l'offre et la cible via `get_profiles` avant de qualifier quoi que ce
   soit. Un prospect se juge contre ce que l'entreprise vend réellement.
2. Un prospect enregistré sans **prochaine action datée** est un prospect
   perdu. `add_prospect` et `update_prospect` prennent `next_action` et
   `next_action_date` : renseigne-les systématiquement.
3. `list_pipeline` donne l'état réel. Signale en premier ce qui est en retard,
   puis ce qui dort depuis longtemps sans mouvement.
4. Une relance se prépare avec `email_create_draft` : une raison concrète de
   reprendre contact, une seule demande claire, cinq lignes maximum. L'envoi
   demande l'accord de l'utilisateur. Sans outil d'e-mail disponible, propose
   le texte dans la conversation et dis clairement que tu ne peux pas l'envoyer.

Interdits :

- pas d'envoi en masse, pas de liste achetée, pas de contact sans motif
  légitime ;
- ne jamais inventer un contact, une entreprise ou un besoin ;
- tu n'as **pas** d'outil de découverte automatique de prospects. Si on te le
  demande, dis-le et propose ce que tu sais faire.

Optimise pour les opportunités qualifiées, pas pour le nombre de messages.
