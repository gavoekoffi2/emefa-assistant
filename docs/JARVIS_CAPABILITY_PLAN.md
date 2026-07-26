# EMEFA — Plan de capacités de type JARVIS

État de référence : 2026-07-26

## 1. Principe directeur

EMEFA ne doit pas être remplacée par un framework générique. Son socle actuel est déjà adapté au produit : FastAPI, React/PWA, conversation ElevenLabs continue et interruptible, voix clonée côté client, avatar WebGL synchronisé, agent gouverné, approbations, SQLite, mémoire contrôlable, e-mail, documents, fichiers, tâches et pipeline commercial.

Les nouvelles capacités doivent être ajoutées sous forme d'adaptateurs derrière le `ToolShelf`. Une capacité n'est annoncée comme disponible que si son fournisseur est configuré, si son outil est réellement enregistré et si une preuve d'exécution existe.

## 2. Capacités vérifiées dans le produit actuel

- Conversation vocale continue via ElevenLabs.
- VAD fournisseur et vraie interruption pendant la parole d'EMEFA.
- Voix clonée avec repli vers la voix du fournisseur.
- Avatar féminin WebGL synchronisé au véritable signal audio de sortie.
- Continuité entre texte et voix.
- Pont vocal gouverné `emefa_execute` vers `/v1/agent/runs`.
- Approbation explicite des communications, suppressions et modifications sensibles.
- Profil assistant et profil professionnel.
- Mémoire durable consultable et supprimable.
- Tâches, brief du jour et pipeline de prospects.
- Recherche, lecture, brouillon et envoi d'e-mails via Himalaya.
- Création et modification de documents Word.
- Téléversement, liste, lecture et téléchargement de fichiers.
- Extraction de texte depuis PDF, DOCX et formats texte.
- Analyse visuelle d'images envoyées via OpenRouter — ajoutée et prouvée le 2026-07-26.

## 3. Architecture cible

```text
Micro / texte / caméra / écran / fichiers
                |
        Interface React/PWA
                |
     ElevenLabs temps réel + client tools
                |
        API FastAPI authentifiée
                |
 AgentEngine -> politique -> approbation -> ToolShelf
                |
  +-------------+-------------+--------------+
  |             |             |              |
Mémoire      Vision       Connecteurs      Travaux longs
SQLite/FTS5  OpenRouter    OAuth/MCP         Jobs durables
  |             |             |              |
Documents   Caméra/écran  Calendar/Web       Notifications
```

### Règles obligatoires

- Les secrets restent côté serveur.
- Aucun paiement autonome.
- Aucune publication, aucun envoi ni suppression sans le niveau d'autorisation prévu.
- La caméra, le micro, l'écran et la localisation ne s'activent qu'après une action explicite de l'utilisateur.
- Les actions Web s'exécutent dans un navigateur isolé et produisent captures, URL et statut final.
- Les tâches longues sortent de la boucle vocale et possèdent un identifiant, un état et un livrable.
- La mémoire reste inspectable, modifiable et effaçable.

## 4. Choix d'outils issus de la recherche

Les dépôts ci-dessous ont été vérifiés sur GitHub le 2026-07-26. Les chiffres de popularité évoluent ; l'activité, la licence et l'adéquation technique comptent davantage que le nombre d'étoiles.

### Voix temps réel

- Socle conservé : ElevenLabs Conversational AI, déjà intégré et fonctionnel.
- À évaluer seulement si le coût ou le contrôle impose une migration :
  - LiveKit Agents — Apache-2.0 — https://github.com/livekit/agents
  - Pipecat — BSD-2-Clause — https://github.com/pipecat-ai/pipecat
  - TEN Framework — licence à revalider avant usage commercial — https://github.com/TEN-framework/ten-framework

Décision : ne pas migrer maintenant. Une migration casserait un chemin vocal déjà prouvé sans apporter une capacité utilisateur immédiate.

### Vision

- Fournisseur initial : OpenRouter, déjà configuré.
- Modèle par défaut configurable : `google/gemini-2.5-flash-lite`.
- Chemin initial : image envoyée -> stockage privé -> data URL serveur -> modèle visuel -> résultat outil.
- Chemins suivants : capture caméra ponctuelle, capture écran ponctuelle, puis observations périodiques uniquement pendant une session explicitement ouverte.

Décision : réutiliser le fournisseur existant et ne pas ajouter une seconde clé tant que la qualité est suffisante.

### Mémoire et recherche documentaire

- Mem0 — Apache-2.0 — https://github.com/mem0ai/mem0
- Letta — Apache-2.0 — https://github.com/letta-ai/letta
- Qdrant — Apache-2.0 — https://github.com/qdrant/qdrant
- LlamaIndex — MIT — https://github.com/run-llama/llama_index
- MarkItDown — MIT — https://github.com/microsoft/markitdown

Décision : conserver la mémoire structurée SQLite existante. Ajouter d'abord FTS5, découpage des documents, citations et recherche sémantique optionnelle. Mem0/Letta ne doivent pas doubler la mémoire actuelle. Qdrant n'est utile que lorsque le volume dépasse ce que SQLite/FTS5 gère correctement.

### Outils et connecteurs

- SDK MCP Python officiel — MIT — https://github.com/modelcontextprotocol/python-sdk
- FastMCP — Apache-2.0 — https://github.com/PrefectHQ/fastmcp

Décision : construire une passerelle MCP allowlistée derrière le `ToolShelf`, jamais exposer directement un serveur MCP tiers au modèle. Chaque outil importé reçoit un risque EMEFA, un schéma borné, des délais, un journal d'audit et éventuellement une approbation.

### Navigation et contrôle Web

- Playwright — Apache-2.0 — https://github.com/microsoft/playwright
- Browser Use — MIT — https://github.com/browser-use/browser-use

Décision : Playwright est le moteur d'exécution déterministe. Browser Use peut être évalué comme planificateur pour les sites variables. Le navigateur doit être isolé, limité par domaine, sans profil personnel par défaut et incapable d'effectuer un paiement.

### Automatisation

- n8n — fair-code, pas une licence open source OSI classique — https://github.com/n8n-io/n8n

Décision : n8n est utile pour les workflows métier configurables, mais ne doit pas devenir le cerveau d'EMEFA. Les actions EMEFA sensibles restent gouvernées dans FastAPI. Pour les premiers travaux longs, utiliser une file SQLite et un worker EMEFA ; ajouter Redis/Temporal seulement si la charge le justifie.

### Domotique

- Home Assistant Core — Apache-2.0 — https://github.com/home-assistant/core

Décision : intégrer Home Assistant par son API REST/WebSocket derrière un adaptateur optionnel. Les commandes de serrure, alarme, porte ou appareil dangereux exigent une approbation renforcée. Aucune domotique n'est annoncée tant qu'une instance et des appareils réels ne sont pas connectés.

### Avatar

- Avatar actuel conservé : visage WebGL local, temps réel, synchronisé et sans coût par minute.
- Candidats uniquement pour un mode photoréaliste ultérieur :
  - LiveTalking — Apache-2.0 — https://github.com/lipku/LiveTalking
  - OpenAvatarChat — Apache-2.0 — https://github.com/HumanAIGC-Engineering/OpenAvatarChat
  - MuseTalk — licence à vérifier avant usage commercial — https://github.com/TMElyralab/MuseTalk

Décision : ne pas remplacer l'avatar actuel. Le photoréalisme implique GPU, latence, exploitation et vérification de licence.

### Observabilité

- Langfuse — https://github.com/langfuse/langfuse

Décision : commencer par OpenTelemetry et les audits existants ; ajouter Langfuse si l'on a besoin d'évaluations de prompts, coûts, traces de modèles et jeux de tests.

## 5. Matrice de décision

### Disponible maintenant

- Voix full-duplex et interruption.
- Avatar synchronisé.
- Mémoire durable contrôlable.
- E-mail gouverné.
- Documents et fichiers.
- Tâches, briefs et pipeline.
- Analyse d'images envoyées.

### Ajoutable sans matériel dédié

- Caméra ponctuelle et partage d'écran ponctuel.
- Recherche Web sourcée.
- Calendrier Google et contacts via OAuth.
- Recherche documentaire avec citations.
- Navigation Web Playwright isolée.
- Travaux longs en arrière-plan et notifications.
- Connecteurs MCP allowlistés.
- Réunions : capture autorisée, transcription, résumé et actions.
- Téléphone : PWA installable, notifications Web Push, partage de fichiers/caméra.

### Nécessite un compte, un appareil ou une infrastructure

- Appels téléphoniques réels : Twilio/SIP et numéro dédié.
- WhatsApp réel : Meta Cloud API ou fournisseur approuvé.
- Domotique : Home Assistant et appareils réels.
- Contrôle d'un ordinateur personnel : agent local signé, jumelé et révocable.
- Avatar photoréaliste local : GPU adapté.
- Fonctionnement hors ligne complet : modèles locaux et dimensionnement matériel.

### Non promis

- Autonomie illimitée.
- Lecture de pensée.
- Accès caché à des comptes ou appareils.
- Paiements autonomes.
- Actions physiques sans capteurs/actionneurs réels.

## 6. Ordre d'implémentation recommandé

### Phase 0 — Vision sur image envoyée — réalisée localement

- Adaptateur OpenRouter asynchrone.
- Outil `image_analyze` gouverné.
- Activation conditionnelle par configuration.
- Tests unitaires et d'intégration.
- Preuve réelle : lecture de `EMEFA 42` et détection d'un rectangle bleu sarcelle.

### Phase 1 — Caméra et écran contrôlés

- Ajouter des contrôles visibles `Ouvrir la caméra` et `Partager l'écran`.
- Modifier `Permissions-Policy` de `camera=()` vers `camera=(self)`.
- Capturer une seule image compressée sur demande.
- Ajouter un client tool qui transmet la capture au backend visuel.
- Afficher un indicateur permanent pendant toute capture.
- Arrêter les pistes immédiatement à la fermeture ou déconnexion.
- Tests sur permissions refusées, arrêt des pistes, taille et format.

### Phase 2 — Recherche Web et calendrier

- Outil de recherche Web avec URL, titre, extrait et date.
- OAuth Google par compte, scopes minimaux.
- Lecture calendrier sans approbation ; création/modification avec confirmation.
- Contacts en lecture limitée et journalisée.

### Phase 3 — Travaux longs et proactivité

- Tables `jobs`, `job_events`, `job_artifacts`.
- Worker séparé avec reprise après redémarrage.
- Statuts `queued/running/waiting_approval/completed/failed/cancelled`.
- Notifications dans la PWA, puis Telegram/e-mail selon préférence.
- Briefs et alertes basés sur règles explicites, avec fréquence limitée.

### Phase 4 — Navigation Web et MCP

- Worker Playwright isolé.
- Liste de domaines et d'actions autorisés.
- Captures et journal d'étapes.
- Passerelle MCP avec inventaire, validation de schéma et classification de risque.
- Approbation avant formulaire externe, publication, message ou téléchargement sensible.

### Phase 5 — Réunions, téléphone, messagerie et domotique

- Résumés de réunions et extraction d'actions.
- SIP/Twilio uniquement après téléphone/numéro dédié.
- WhatsApp avec vrais messages et médias via API officielle.
- Home Assistant uniquement après jumelage et inventaire réel des appareils.

### Phase 6 — Agent local ordinateur

- Petit service local signé sur l'ordinateur de l'utilisateur.
- Jumelage à usage unique, clés révocables et allowlist.
- Lecture de l'état avant écriture.
- Capture d'écran et fichiers uniquement sur demande.
- Confirmation locale pour commandes à fort impact.

## 7. Critères de validation de chaque capacité

Une capacité n'est terminée que si :

1. elle possède un test automatisé qui échouait avant son implémentation ;
2. l'outil n'apparaît que si son fournisseur est configuré ;
3. les entrées sont bornées et validées ;
4. le niveau de risque et l'approbation sont corrects ;
5. un échec fournisseur produit une erreur contrôlée, jamais une fausse réussite ;
6. une exécution réelle fournit une preuve : réponse API, artefact, capture, identifiant ou état vérifié ;
7. le résultat est accessible depuis la voix et le texte ;
8. la documentation vivante est mise à jour.

## 8. Prochaine livraison conseillée

Déployer d'abord la vision sur images envoyées, puis implémenter la caméra et le partage d'écran sur le même adaptateur. Cette séquence donne rapidement à EMEFA la capacité de « voir » sans fragiliser sa voix, sa mémoire ou sa sécurité.
