# Protocole TARS Local Executor pour EMEFA

Statut : architecture de sécurité approuvée pour implémentation progressive. Ce document ne prétend pas qu'EMEFA contrôle déjà un ordinateur local.

## 1. Séparation des rôles

- **EMEFA/JARVIS** comprend la demande, utilise la mémoire, construit un plan et applique les politiques.
- **TARS Local Executor** observe ou agit uniquement sur l'ordinateur appairé et uniquement dans les limites autorisées.
- Le modèle de langage ne reçoit jamais une session shell arbitraire ni un contrôle administrateur permanent.

## 2. Installation et appairage

1. L'utilisateur installe l'agent signé sur son ordinateur Windows.
2. L'agent crée localement une paire de clés Ed25519 ; la clé privée ne quitte jamais l'ordinateur.
3. EMEFA affiche un code d'appairage à usage unique, valable cinq minutes.
4. L'agent initie lui-même une connexion TLS sortante vers EMEFA. Aucun port entrant n'est ouvert sur l'ordinateur.
5. EMEFA enregistre la clé publique, le nom choisi pour l'appareil et les capacités explicitement autorisées.
6. Une révocation depuis EMEFA ou depuis l'icône locale invalide immédiatement l'appareil.

## 3. Niveaux de capacité

### Niveau 0 — Désactivé

Aucune observation et aucune action.

### Niveau 1 — Observer

- capturer l'écran à la demande ;
- lire l'arbre d'accessibilité de la fenêtre choisie ;
- rapporter les applications visibles ;
- aucune saisie, aucun clic.

### Niveau 2 — Assister

- proposer une cible de clic ou un texte à saisir ;
- afficher localement un aperçu surligné ;
- exécuter seulement après confirmation locale.

### Niveau 3 — Exécuter des actions bornées

- cliquer ou saisir dans une application autorisée ;
- naviguer dans un navigateur isolé ;
- ouvrir une application autorisée ;
- toujours respecter les politiques de risque et fournir une preuve avant/après.

Les niveaux sont définis par appareil et par capacité. Ils ne sont jamais augmentés silencieusement.

## 4. Catalogue initial des capacités

- `screen.capture` — capture ponctuelle de la fenêtre ou de l'écran choisi.
- `accessibility.read` — lecture de l'arbre accessible de la fenêtre choisie.
- `browser.open` — ouverture d'une URL HTTPS.
- `browser.inspect` — lecture DOM/accessibilité sans mutation.
- `browser.click` — clic sur un élément identifié, pas sur des coordonnées seules.
- `browser.type` — saisie dans un champ non sensible identifié.
- `app.open` — ouverture d'une application figurant dans une liste blanche.
- `file.read` — lecture d'un fichier explicitement choisi ou situé dans un dossier autorisé.
- `file.write` — écriture d'un livrable dans un dossier autorisé, avec confirmation si remplacement.

Absents de la première version : shell arbitraire, PowerShell arbitraire, installation de logiciel, privilèges administrateur, lecture du presse-papiers en continu, contrôle caché.

## 5. Contrat d'action

Chaque ordre est une enveloppe signée contenant au minimum :

```json
{
  "action_id": "uuid",
  "device_id": "uuid",
  "capability": "browser.click",
  "issued_at": "ISO-8601",
  "expires_at": "ISO-8601",
  "risk": "personal",
  "target": {
    "application": "chrome",
    "window_title": "titre attendu",
    "selector": "rôle/nom accessible attendu"
  },
  "arguments": {},
  "preconditions": [],
  "approval_id": "uuid-ou-null",
  "nonce": "valeur unique"
}
```

L'agent rejette l'ordre si la signature, l'échéance, le nonce, l'appareil, la capacité, la permission, l'approbation ou les préconditions ne correspondent pas.

## 6. Politique de confirmation

### Lecture personnelle

Une confirmation d'ouverture de session peut couvrir temporairement les captures ponctuelles et la lecture de la fenêtre choisie. L'indicateur local reste visible.

### Mutation réversible

Chaque lot cohérent affiche : action, application, cible et effet attendu. L'utilisateur peut autoriser une fois ou pour la session.

### Action conséquente

Toujours une confirmation immédiate et spécifique pour :

- envoyer ou publier ;
- acheter, réserver ou payer ;
- supprimer ou remplacer ;
- accepter des conditions ;
- saisir des données sensibles ;
- modifier des permissions, comptes ou paramètres de sécurité.

Le mot de passe, le code 2FA et les données bancaires restent saisis par l'utilisateur. L'agent ne les lit pas et ne les journalise pas.

## 7. Cibles et fiabilité

Ordre de préférence :

1. DOM ou arbre d'accessibilité avec rôle et nom ;
2. API officielle de l'application ;
3. sélecteur visuel avec score de confiance et aperçu ;
4. coordonnées absolues uniquement en dernier recours et avec nouvelle confirmation.

Avant mutation, l'agent vérifie la fenêtre, le domaine, l'élément et les préconditions. Après mutation, il vérifie l'état attendu au lieu de déclarer arbitrairement le succès.

## 8. Preuves et audit

Chaque action produit :

- état `received`, `approved`, `running`, `succeeded`, `failed`, `cancelled` ou `expired` ;
- horodatage et durée ;
- application et domaine ciblés ;
- captures avant/après expurgées lorsque cela est autorisé ;
- résultat structuré et message d'erreur réel ;
- empreintes SHA-256 des preuves ;
- aucune clé, aucun mot de passe et aucun contenu de champ sensible.

## 9. Contrôles locaux obligatoires

- icône permanente dans la zone de notification ;
- bannière visible pendant observation ou contrôle ;
- bouton `STOP` local toujours disponible ;
- raccourci clavier d'arrêt d'urgence ;
- arrêt automatique à la fermeture de session ou après inactivité ;
- journal local consultable ;
- désinstallation et révocation simples ;
- mise à jour signée uniquement.

## 10. Transport

- canal WebSocket TLS sortant avec reprise contrôlée ;
- messages signés, nonces uniques et échéances courtes ;
- authentification de l'appareil par clé ;
- rotation et révocation des clés ;
- aucune commande reçue directement d'Internet sans validation du serveur EMEFA et de la politique locale.

## 11. Phases d'implémentation

1. **Vision Web** — partage volontaire et captures ponctuelles dans EMEFA.
2. **Agent local en lecture seule** — appairage, bannière, arrêt, capture et accessibilité.
3. **Navigateur isolé assisté** — inspecter, proposer, confirmer, cliquer/saisir.
4. **Applications autorisées** — ouverture et actions bornées.
5. **Travaux longs** — file persistante, sous-tâches, reprise et livrables.
6. **Validation de sécurité Windows** — signature, installateur, mises à jour et test d'intrusion avant activation générale.

## 12. Critère d'annonce publique

EMEFA pourra être annoncée comme capable de contrôler l'ordinateur seulement lorsqu'un test réel aura prouvé : appairage, observation, clic/saisie bornés, confirmation, bouton d'arrêt, preuve avant/après, refus des zones sensibles et révocation de l'appareil.
