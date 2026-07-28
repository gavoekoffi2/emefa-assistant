# EMEFA — feuille de route « assistante exécutive »

> **Date :** 2026-07-28 · **Filtre de décision :** *« Est-ce qu'une excellente
> assistante de direction ferait naturellement ce travail pour son dirigeant ? »*

Ce document classe les douze axes de la vision selon ce que le produit fait
déjà, ce qui vient ensuite, et ce qui doit attendre — avec la raison à chaque
fois. Il existe parce qu'une liste de douze chantiers traitée comme une seule
tâche produit douze fonctionnalités médiocres.

---

## Principe d'ordonnancement

Une excellente assistante de direction est d'abord **fiable**, ensuite
**complète**. Un dirigeant délègue à quelqu'un qui n'oublie rien et n'invente
rien ; il ne délègue pas à quelqu'un qui sait tout faire à peu près.

L'ordre ci-dessous suit donc trois règles :

1. **Ce qu'elle fait tous les jours avant ce qu'elle fait parfois.** Produire un
   devis correct compte plus que gérer un marketplace de compétences.
2. **Ce qui ne dépend de personne avant ce qui dépend d'un tiers.** La
   bureautique tourne sans réseau ; la prospection exige des fournisseurs de
   données.
3. **Rien qui oblige EMEFA à mentir.** Une fonctionnalité qui ne peut pas être
   honnête est repensée, pas livrée diminuée.

---

## État des douze axes

| # | Axe | État | Commentaire |
|---|---|---|---|
| 1 | Assistante de direction | **Partiel** | Tâches, engagements datés, suivi projets/clients/fournisseurs, détection d'urgences et actions prioritaires : livrés (graphe d'entités + moteur proactif). Comptes rendus et rapport du soir : à faire (§ Phase 2). |
| 2 | Prospection intelligente | **Non commencé** | Bloqué par l'axe 8. Voir § Ce qui exige une décision. |
| 3 | CRM intelligent | **Fondations livrées** | Les entités (prospect, client, fournisseur, partenaire, contrat, devis, facture, réunion) et leurs relations existent. Manque la **couche de questions** : « quels devis en attente ? », « quels contrats expirent ? ». Phase 1. |
| 4 | Suite bureautique | **Livré** | Word, Excel, PowerPoint derrière une interface de capacité remplaçable. Détail ci-dessous. |
| 5 | Gestion documentaire | **Partiel** | Production et stockage livrés. Classement, comparaison, résumé, conversion, indexation : Phase 2. |
| 6 | Marketplace | **Reporté — volontairement** | Voir § Ce que je recommande de ne pas construire maintenant. |
| 7 | Skill Builder | **Reporté — volontairement** | Idem. |
| 8 | Fournisseurs de services | **Non commencé** | Débloque l'axe 2 et une partie de l'axe 9. Phase 3. |
| 9 | Cartes visuelles | **Livré** | Huit types, données typées, jamais de balisage. PDF et tableaux de bord composés : Phase 2. |
| 10 | Mémoire exécutive | **Livré** | Utilisateur, entreprise, projets, clients, fournisseurs, décisions, réunions, objectifs, habitudes — noyau de faits + graphe d'entités + chronologies. |
| 11 | Rapports automatiques | **Partiel** | Brief matinal déterministe livré. Brief exécutif enrichi et rapport du soir : Phase 1. |
| 12 | Architecture | **Continu** | Modularité, sécurité, auditabilité, testabilité : appliquées à chaque tranche (5 ADR, 290 tests backend). Multi-tenant : scopes en place, activation à la platformisation. |

---

## Axe 4 — ce qui a été livré

Interface de capacité → fournisseur → moteur de rendu (`CLAUDE.md` §19), donc
le moteur est remplaçable sans toucher un seul appelant.

**Word** — lettre, contrat, devis, facture, rapport, compte rendu,
procès-verbal, proposition, cahier des charges, procédure, politique interne,
CV, manuel, formulaire. Styles de titre à la couleur de l'entreprise, en-tête,
pied de page avec numérotation par champ, tableaux, blocs de champs, blocs de
signature, sommaire optionnel.

**Excel** — tableaux, tableaux de bord, budgets, devis chiffrés, suivis
(ventes, dépenses, stocks), plannings, statistiques. Colonnes formatées,
en-têtes figés, filtres, graphiques.

**PowerPoint** — titre, section, puces, tableau, graphique, citation,
conclusion, notes de l'orateur.

**La règle qui traverse tout ça :** un classeur doit rester un classeur. Les
montants de ligne et les totaux sont écrits comme **formules vivantes**, pas
comme valeurs figées — sinon le fichier meurt à la première quantité modifiée.
Mais une colonne de formules ne contient aucune valeur littérale, donc en
sommer les cellules donnerait zéro. EMEFA calcule donc le même total en
parallèle et vous l'annonce ; quand la formule est trop complexe pour être
évaluée sûrement, elle dit « le total apparaîtra à l'ouverture » au lieu de
citer un chiffre approximatif.

**À propos d'OfficeCLI :** aucun paquet de ce nom n'existe sur PyPI. Aucun
adaptateur n'a donc été écrit contre quelque chose d'invérifiable. L'interface
est en place ; brancher un fournisseur — OfficeCLI, LibreOffice headless, un
service de rendu — est une ligne dans le point de composition.

---

## Phases suivantes

### Phase 1 — Le quotidien du dirigeant *(prochaine)*

Ce qu'une assistante fait tous les matins et tous les soirs, sans dépendance
externe.

1. **Couche de questions CRM.** « Quels devis sont en attente ? », « quels
   clients rappeler ? », « quels contrats expirent ? », « quels prospects sont
   les plus prometteurs ? » — requêtes déterministes sur le graphe d'entités,
   pas une recherche plein texte.
2. **Brief exécutif du matin.** Rendez-vous, priorités du jour, relances dues,
   risques (retards, contrats qui expirent, opportunités qui dorment),
   opportunités. Déterministe, donc reproductible et gratuit.
3. **Rapport du soir.** Ce qui a été fait, ce qui reste, ce qui a bougé, une
   recommandation pour demain.
4. **Comptes rendus de réunion.** Depuis des notes ou une transcription :
   décisions, actions avec responsable et échéance, écrites dans la mémoire du
   projet et pas seulement dans un document.

### Phase 2 — Gestion documentaire

Classer, retrouver, comparer deux versions, résumer, extraire, convertir,
indexer. Le stockage existe ; ce qui manque est l'index et la comparaison.

### Phase 3 — Fournisseurs, puis prospection

L'architecture de fournisseurs (axe 8) d'abord, parce que la prospection (axe
2) sans elle est impossible : EMEFA dit aujourd'hui explicitement qu'elle ne
sait pas découvrir de prospects, et c'est la vérité.

Interface unique, fournisseurs interchangeables : recherche web, recherche
d'images, cartographie, itinéraires, météo, actualités, stockage. Chacun
derrière un adaptateur, aucun couplage du métier à un fournisseur.

Puis la prospection : découverte, qualification contre l'ICP, coordonnées
publiques, classement, préparation des messages (e-mail, LinkedIn, WhatsApp),
relances. **Tout envoi reste soumis à validation humaine** — c'est déjà la
règle du moteur d'autonomie : le niveau 5 exige toujours un humain.

### Phase 4 — Marketplace et Skill Builder

Quand le socle est fiable. Voir ci-dessous.

---

## Ce qui exige une décision de votre part

### Prospection automatique : les limites sont juridiques, pas techniques

« Rechercher automatiquement de nouveaux prospects » et « retrouver les
coordonnées publiques » sont réalisables, mais encadrés :

- le RGPD s'applique à la collecte de données professionnelles nominatives, y
  compris publiques, et la personne doit pouvoir s'y opposer ;
- LinkedIn interdit le scraping dans ses conditions d'utilisation ; l'accès
  légitime passe par leur API ou par une saisie manuelle ;
- WhatsApp Business impose des modèles de messages pré-approuvés pour un
  premier contact.

Ce que je livrerai donc : découverte via des **fournisseurs de données
autorisés** (annuaires, registres d'entreprises, API officielles), préparation
de messages, et **jamais d'envoi automatique**. Ce que je ne livrerai pas :
du scraping de LinkedIn déguisé en fonctionnalité. À vous de me dire quelles
sources vous voulez brancher.

---

## Ce que je recommande de ne pas construire maintenant

**Le Marketplace (axe 6) et le Skill Builder (axe 7).**

`CLAUDE.md` §50 le dit déjà : *« Do not build a marketplace before core
capabilities are reliable. »* Trois raisons concrètes :

1. **Un marketplace sans compétences n'est pas un marketplace.** Il en existe
   quatre aujourd'hui. La valeur d'une place de marché vient du catalogue, pas
   du mécanisme d'installation.
2. **Le Skill Builder construit des compétences que le registre actuel ne peut
   pas exécuter.** Une compétence apporte un prompt et un manifeste, jamais du
   code — décision délibérée : exécuter le Python d'un inconnu avec les
   identifiants d'EMEFA est exactement ce que `CLAUDE.md` §48 interdit. Un
   Skill Builder utile suppose donc d'abord de décider *ce qu'une compétence
   générée a le droit de faire*, et cette décision mérite un ADR avant du code.
3. **Signatures numériques et contrôle de sécurité sont la partie difficile**,
   et ils n'ont de sens qu'avec des contributeurs tiers réels.

Ma recommandation : livrer les phases 1 à 3, puis construire le marketplace
quand il y a un catalogue et des contributeurs à protéger. Si vous préférez
l'inverse, dites-le — c'est votre produit, et je le ferai en le disant
clairement dans un ADR.

---

## Ce qui ne changera pas

Quelle que soit la phase :

- **Aucun envoi sans validation humaine.** Niveau d'autonomie 5 = accord
  obligatoire, sans exception configurable.
- **Aucun chiffre inventé.** Un montant absent reste un blanc, un total
  incalculable est annoncé comme tel.
- **Aucune action annoncée qui n'a pas eu lieu.** « Terminé » exige que chaque
  étape ait été vérifiée.
- **Le contenu externe est une donnée, jamais une instruction.**

C'est ce qui fait la différence entre une assistante à qui on délègue et un
outil qu'on surveille.
