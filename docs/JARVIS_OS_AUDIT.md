# Audit comparatif Jarvis-OS → EMEFA

Date de l’audit : 26 juillet 2026
Référence auditée : `Grominet95/jarvis-OS`, commit `bf9fd0b`
Méthode : lecture statique du dépôt public et comparaison avec les capacités déjà vérifiées d’EMEFA.

## 1. Contrainte de licence

Jarvis-OS déclare `AGPL-3.0-or-later` dans son `pyproject.toml` et son README. Cette licence impose des obligations fortes lorsque du code dérivé est exploité via un réseau.

Décision appliquée : **aucun fichier, extrait, classe, nom interne ou structure de code de Jarvis-OS n’a été copié dans EMEFA**. Les apports ci-dessous sont une implémentation indépendante, écrite selon les conventions et l’architecture existantes d’EMEFA. Jarvis-OS a servi uniquement de référence fonctionnelle pour identifier des idées générales.

## 2. Architecture observée

Jarvis-OS est un assistant Python/FastAPI 3.11–3.13 structuré en couches :

- noyau de contrats, événements, permissions, configuration et approbations ;
- fournisseurs LLM, audio, vision et mémoire ;
- capacités/outils et registre de skills ;
- moteur d’agent, missions, tâches de fond, budget et proactivité ;
- interfaces HTTP, voix LiveKit et canaux de messagerie ;
- composition des dépendances au démarrage.

La séparation de couches est contrôlée par `import-linter`. Le dépôt annonce également Ruff, mypy, pytest et un snapshot des routes comme garde-fous CI.

## 3. Fonctions réellement présentes dans l’arborescence

L’audit a confirmé des modules dédiés aux familles suivantes :

- voix temps réel LiveKit ;
- mémoire SQLite, ingestion de faits, recherche, miroir Markdown et consolidation ;
- missions planifiées avec workers et vérification ;
- outils Gmail, Calendar, Spotify, Notion, météo, navigateur, filesystem, CLI, vision et mémoire ;
- suivi de budget et d’utilisation ;
- tâches de fond, routines, notifications et briefing ;
- initiatives proactives et centre de commande ;
- canaux Telegram, WhatsApp, Slack, Signal et Discord ;
- vision locale (OpenCV, YOLO) et matériel optionnel.

Les dépendances sont lourdes et très larges : Anthropic, OpenAI, Google GenAI, Ollama, LiveKit et plusieurs plugins, Faster Whisper, Piper TTS, RealtimeSTT, OpenCV, Ultralytics, Google APIs, FastEmbed, yt-dlp, sounddevice et bibliothèques USB. Importer cet ensemble tel quel aurait augmenté le poids, la surface d’attaque et les risques de régression d’EMEFA.

## 4. Comparaison avec EMEFA

### Déjà disponible dans EMEFA

- conversation vocale temps réel et interruption ;
- transcription et synthèse vocale ;
- agent outillé avec politiques de risque ;
- approbation explicite avant les actions sensibles ;
- mémoire durable et profil professionnel ;
- tâches, prospects et relances ;
- fichiers, lecture PDF/DOCX, analyse d’images et documents persistants ;
- e-mail avec préparation puis approbation ;
- brief quotidien ;
- interface 3D EMEFA et espace Livrables ;
- authentification par appareil, session Web, limites de tentatives et audit.

### Manques utiles retenus

1. Une vue agrégée des objectifs, tâches, prospects, routines et approbations.
2. Des initiatives persistantes avec priorité, risque, prochaine action et état.
3. Des routines manuelles, quotidiennes ou hebdomadaires.
4. Un historique auditable des exécutions de routines.
5. La présence de ces initiatives dans le contexte de l’assistante et dans ses outils vocaux.

### Fonctions volontairement non importées

- mission engine autonome avec exécution de code ou Docker : trop risqué pour une assistante métier en production sans projet de sandbox séparé ;
- Skill Lab auto-génératif : élargit la surface d’exécution et exige une gouvernance propre ;
- vision locale YOLO/face recognition : doublon coûteux par rapport au flux visuel actuel ;
- pile audio locale Whisper/Piper/LiveKit : EMEFA dispose déjà d’une voix validée et interruptible ;
- matériel USB/macropad, Spotify, domotique et nombreux canaux : hors priorité métier actuelle ;
- collecteurs météo/actualité généralisés : à ajouter seulement avec des sources et besoins validés ;
- copie du budget tracker : le suivi des coûts doit être branché sur les réponses d’usage réelles des fournisseurs EMEFA avant d’afficher des montants fiables.

## 5. Intégration clean-room réalisée

EMEFA dispose maintenant d’un **Centre de pilotage** indépendant comprenant :

- migration SQLite version 10 ;
- dépôt d’initiatives ;
- dépôt de routines et journal d’exécution ;
- planificateur asynchrone des routines ;
- endpoints authentifiés `/v1/command-center/*` ;
- outils d’agent pour créer/lister/mettre à jour les initiatives et créer/lister les routines ;
- ajout des initiatives actives au contexte de l’assistante ;
- interface « Pilotage » avec métriques, initiatives et routines ;
- exécution immédiate depuis l’interface ;
- conservation du mécanisme d’approbation existant pour toute action sensible issue d’une routine.

## 6. Vérifications

- tests backend : `120 passed` ;
- compilation TypeScript/Vite : réussie ;
- aucune dépendance Jarvis-OS ajoutée à EMEFA ;
- aucun code AGPL incorporé ;
- aucune modification du cœur de la voix ou du rendu 3D ;
- les actions sensibles restent bloquées jusqu’à approbation humaine.
