# EMEFA — Version 1 (MVP Premium) — Rapport de livraison

> **Date :** 2026-07-28 · **Destinataire :** premier utilisateur réel (entrepreneur)
> **Objectif de la phase :** non pas ajouter des fonctionnalités, mais faire des
> fonctionnalités existantes **une seule assistante**, utilisable tous les jours.
> **Décisions d'architecture :** `docs/adr/ADR-002-executive-domain-model.md`
> **Journal technique :** `docs/IMPLEMENTATION_STATUS.md`

---

## 1. Le test que chaque décision a dû passer

> « Est-ce qu'une excellente assistante exécutive ferait naturellement cette tâche pour son
> dirigeant ? »

Trois conséquences concrètes de ce filtre :

- **Rien n'est demandé deux fois.** L'entretien d'accueil lit le profil qu'il alimente : ce
  qu'EMEFA apprend au détour d'une conversation compte comme progression, et un champ connu
  ne peut plus être redemandé.
- **Rien n'est affirmé sans être vérifié.** Les briefings, les relances, les échéances de
  contrat sont **calculés** à partir de la base, jamais rédigés par le modèle. Une assistante
  ne dit pas « votre contrat expire bientôt » à l'intuition.
- **Rien n'est envoyé sans accord.** Un scénario complet prépare tout — document, devis,
  tâche de relance, e-mail — puis s'arrête et propose. C'est exactement ce que ferait une
  assistante : « c'est prêt, je l'envoie ? »

---

## 2. Fonctionnalités finalisées

### 2.1 Entretien d'accueil intelligent

Une véritable conversation, jamais un formulaire. Cinq sujets — profil personnel, entreprise,
activité, objectifs, préférences de travail — couvrant 31 informations.

- La carte d'accueil affiche la prochaine question naturelle ; y répondre se fait **en parlant
  ou en écrivant à EMEFA**, comme n'importe quel échange.
- Tant que l'entretien n'est pas terminé, EMEFA reçoit un briefing interne : ce qui est déjà
  connu, ce qui reste à apprendre, la progression. Elle enchaîne naturellement et n'insiste
  jamais si le dirigeant préfère passer à autre chose.
- Chaque information apprise enrichit immédiatement la mémoire exécutive et devient visible
  dans le centre de configuration.
- Un sujet peut être mis de côté puis repris ; l'entretien peut être rouvert à tout moment.

### 2.2 Centre de configuration

Un seul endroit qui montre **tout** ce qu'EMEFA sait, groupé comme l'entretien lui-même
(les groupes viennent du serveur, l'interface ne peut donc pas dériver).

- Modifier, compléter, corriger champ par champ ; effacer un groupe entier.
- Consulter et supprimer chaque souvenir durable.
- Voir l'avancement de l'entretien sujet par sujet et le reprendre.
- Importer les pages publiques du site de l'entreprise pour préremplir le contexte.
- Ajuster l'identité de l'assistante (nom, style d'interaction).

Aucune donnée importante n'est cachée : le schéma exposé par l'API est exactement l'ensemble
des champs modifiables, et un test le vérifie.

### 2.3 Briefing exécutif du matin

Composé à la demande dans l'interface, et automatiquement à l'heure configurée
(`EMEFA_BRIEF_HOUR`), avec envoi par e-mail sous approbation permanente
(`EMEFA_BRIEF_EMAIL_TO`).

Contenu : priorités du jour · tâches classées (en retard, aujourd'hui, à venir, sans
échéance) · actions attendues d'autres personnes issues des réunions · clients à relancer ·
devis en attente de réponse · contrats à échéance · projets bloqués ou en retard ·
opportunités chiffrées · risques · recommandations.

Les recommandations sont dérivées des faits listés juste au-dessus — jamais inventées.
Chaque section est activable ou désactivable par l'utilisateur.

### 2.4 Rapport du soir

Même contrat, en fin de journée (`EMEFA_EVENING_HOUR`) : résumé de la journée · tâches
terminées · tâches restantes · blocages · recommandations · priorités du lendemain.

Les priorités de demain combinent les tâches en retard, celles du jour non terminées, les
échéances de demain et les relances commerciales dues.

### 2.5 CRM conversationnel

Cinq entités liées — contacts, projets, devis, contrats, échanges — qui forment la mémoire
relationnelle. Les questions du brief de mission sont des lectures directes :

| Question posée à EMEFA | Ce qu'elle lit |
|---|---|
| Quels clients dois-je relancer ? | contacts actifs silencieux au-delà de leur seuil |
| Quels devis attendent une réponse ? | devis envoyés/relancés dont l'échéance est passée |
| Quels contrats expirent bientôt ? | contrats actifs dans leur fenêtre de préavis |
| Quels projets sont bloqués ? | projets bloqués, en santé critique ou en retard |
| Où en est le projet X ? | le projet, son client, ses devis, ses contrats, son historique et ses signaux d'alerte |

L'espace « Clients » montre les mêmes informations visuellement, et chaque ligne peut être
corrigée ou supprimée. Chaque entrée propose une action qui **repasse par EMEFA** plutôt que
de dupliquer son raisonnement dans l'interface.

### 2.6 Réunions

Notes dictées ou collées → EMEFA produit, en une seule opération vérifiée :

1. un compte rendu Word professionnel ;
2. les décisions ;
3. les actions, avec responsable et échéance ;
4. une tâche réelle pour chaque action qui incombe au dirigeant ;
5. la mise à jour de la prochaine étape du projet concerné ;
6. une entrée dans l'historique de la relation client.

Les actions confiées à d'autres personnes restent visibles dans une liste de relance. Si un
projet ou un client cité n'existe pas, c'est signalé — pas silencieusement ignoré.

### 2.7 Suite bureautique

Architecture indépendante du moteur : les appelants décrivent un document, un classeur ou une
présentation ; un adaptateur les rend. Changer de moteur (OfficeCLI, service externe) demande
un nouvel adaptateur, pas une modification des appelants.

- **Word** : titres, sous-titre daté, listes à puces, listes numérotées, tableaux, pied de
  page. Relisible par EMEFA avant révision, donc jamais réécrit à l'aveugle.
- **Excel** : les **formules restent vivantes** (`=B2*C2` est écrite comme formule, pas comme
  résultat), lignes de totaux `SUM` générées, en-têtes figés, filtres, largeurs ajustées.
- **PowerPoint** : diapositive de couverture, puces, notes de l'orateur.

Tous les fichiers restent modifiables et téléchargeables depuis l'espace Livrables.

### 2.8 Workflows exécutifs

« Prépare une proposition commerciale » déclenche **un seul outil** qui exécute la chaîne
complète : retrouver le client (ou le créer) → récupérer l'historique et les anciens devis →
générer le document chiffré → enregistrer le devis avec sa date de réponse attendue → créer
la tâche de relance → préparer l'e-mail → **proposer** l'envoi.

Chaque étape est rapportée avec son statut réel (`done` / `skipped` / `failed`), donc EMEFA
peut dire ce qu'elle a fait *et* ce qu'elle n'a pas pu faire. Même logique pour la relance
client. Rien n'est envoyé : l'envoi reste une action soumise à approbation explicite.

### 2.9 Cohérence de l'expérience

- Un seul panneau ouvert à la fois ; l'ancienne barre latérale décorative est devenue une
  vraie navigation.
- Toutes les surfaces partagent la même mémoire : le CRM alimente le briefing, la réunion
  alimente le CRM et les tâches, le workflow alimente le CRM, les documents et les tâches.
- Le contexte injecté à EMEFA inclut désormais le portefeuille suivi et l'état de l'entretien,
  encadrés par la protection anti-injection existante (ces données ne sont jamais des
  instructions).

---

## 3. Vérifications réellement exécutées

| Vérification | Commande | Résultat |
|---|---|---|
| Tests backend | `python -m pytest -q` | **164 passés** |
| Lint web | `npm run lint` | propre |
| Tests web | `npm test` | **67 passés** |
| Build production | `npm run build` | réussi |

35 tests backend ont été ajoutés pendant cette phase, et 7 tests web (dont 2 remplacent
celles de l’ancien panneau de profil). Ils vérifient des
effets réels, pas des intentions : formules Excel réellement stockées comme formules,
structure Word réellement présente, réunion créant réellement une tâche et déplaçant
réellement un projet, briefing ne contenant que des faits stockés, workflow n'atteignant
jamais une action de communication.

Trois attentes de tests préexistantes ont été modifiées **délibérément et explicitement** :
les assertions sur les paragraphes Word (les documents portent désormais une ligne de
sous-titre datée), les assertions de version de schéma (10 → 15), et un test de routine qui
dépendait d'une date en dur — rendu indépendant du calendrier.

---

## 4. Limites restantes

Honnêtement listées, par ordre d'impact pour le premier utilisateur.

1. **Pas d'agenda.** Aucune connexion calendrier. Le briefing parle de tâches, d'échéances et
   de relances, jamais de rendez-vous. C'est la limite la plus visible au quotidien.
2. **Pas de lecture proactive de la boîte mail.** EMEFA peut chercher, lire, rédiger et
   envoyer (sous approbation) quand la boîte est connectée, mais rien ne remonte
   automatiquement dans le briefing.
3. **~40 outils sur une seule étagère plate.** Cela peut dégrader la sélection d'outil sur les
   modèles plus petits. C'est le premier chantier V2.
4. **Résolution de noms tolérante mais silencieuse.** « Horizon » trouve le premier Horizon.
   S'il en existe deux, l'ambiguïté n'est pas signalée.
5. **Canal vocal légèrement plus restreint.** Le pont ElevenLabs partage son secret ; il tourne
   donc sans les outils de lecture de boîte mail. Les actions sensibles préparées à la voix
   remontent bien dans la carte d'approbation.
6. **Factures et devis comptables non intégrés.** Les devis sont suivis comme des affaires,
   pas générés dans un format comptable ni reliés à un système de facturation.
7. **Pas de découverte automatique de prospects.** Assumé : la prospection non contrôlée est
   explicitement exclue. EMEFA suit ce qu'on lui confie.
8. **Instance mono-utilisateur.** Les colonnes de cloisonnement existent partout, mais
   l'authentification reste le code d'activation + jeton d'appareil.
9. **Bundle web ~1,2 Mo** (three.js est déjà séparé). Perfectible sur réseau lent.
10. **Pas encore d'évaluations automatiques d'agent** (choix d'outil, résistance à
    l'injection, multilingue). Les tests couvrent le déterministe, pas le probabiliste.

---

## 5. Recommandations pour la Version 2

Par ordre de valeur décroissante pour un dirigeant.

1. **Agenda (Google/Microsoft, lecture puis écriture sous approbation).** C'est ce qui manque
   le plus pour que le briefing du matin soit *le* réflexe quotidien. Préparer aussi la
   réunion : ordre du jour à partir du CRM, compte rendu automatiquement relié à l'événement.
2. **Groupement progressif des compétences.** Exposer des groupes (`crm`, `bureautique`,
   `réunions`, `workflows`) et ne détailler les outils qu'après sélection. Mesurer avant/après
   avec des évaluations de choix d'outil — ne pas décider « c'est mieux » à l'impression.
3. **Évaluations d'agent.** Cas de test sur : sélection d'outil, respect des permissions,
   résistance à l'injection via contenus externes, honnêteté (ne pas annoncer une action non
   exécutée), qualité multilingue. C'est ce qui permettra d'améliorer les prompts sans
   régression invisible.
4. **Boîte mail proactive.** Faire remonter dans le briefing les messages nécessitant une
   réponse, en respectant strictement la frontière « contenu externe = données, jamais
   instructions ».
5. **Ambiguïté explicite.** Quand une recherche de nom correspond à plusieurs entités, poser
   la question au lieu de choisir.
6. **Devis et factures.** Passer du suivi d'affaire à la production de documents conformes,
   avec numérotation, TVA et lien vers un système comptable.
7. **Migration du pipeline hérité vers le CRM.** `prospects` et `contacts` coexistent
   volontairement. Une migration progressive, avec conservation puis retrait, unifierait le
   suivi commercial.
8. **Travaux longs durables.** Jobs reprenables, annulables et auditables pour les workflows
   qui dépasseront une requête HTTP.
9. **Voix : mesurer avant de migrer.** La ligne de base ElevenLabs (temps jusqu'au premier
   audio, latence bout en bout, interruption, coût par minute) n'existe toujours pas. Aucune
   décision LiveKit ne devrait être prise avant.
10. **Multi-tenant.** Comptes réels, isolation vérifiée par des tests, avant toute
    commercialisation à plusieurs entreprises.

---

## 6. Ce que le premier utilisateur peut faire dès aujourd'hui

Une journée type, entièrement supportée :

1. **Le matin** — ouvrir « Journée » : priorités, retards, clients à relancer, devis sans
   réponse, contrats qui arrivent à terme, projets bloqués, et trois à six recommandations.
2. **Après un appel** — « note que j'ai eu Ama au téléphone, elle veut une proposition pour
   la refonte » : le contact est mis à jour, l'échange est daté, elle ne sera pas relancée
   pour rien.
3. **Dans la foulée** — « prépare une proposition commerciale pour Ama, 1,5 million » :
   document Word chiffré, devis enregistré, tâche de relance à sept jours, e-mail prêt,
   attente de son accord pour l'envoi.
4. **Après une réunion** — dicter ses notes : compte rendu Word, décisions, actions attribuées,
   tâches créées pour ce qui lui incombe, projet mis à jour.
5. **Pendant la journée** — « où en est le projet Refonte ? » : client, devis liés, contrats
   liés, historique, blocages.
6. **Le soir** — ouvrir « Rapport du soir » : ce qui est fait, ce qui reste, ce qui bloque, et
   par quoi commencer demain.
7. **À tout moment** — ouvrir « Configuration » pour voir, corriger ou effacer tout ce
   qu'EMEFA sait de lui.
