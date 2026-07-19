# Architecture EMEFA Greenfield

Date : 2026-07-18

## Principes

- Aucun code hérité de PokeClaw ou de l’ancienne plateforme.
- Application web React/TypeScript mobile-first et installable en PWA.
- Backend FastAPI neuf, API versionnée `/v1`.
- Session web dans un cookie `HttpOnly`, `Secure` et `SameSite=Strict`.
- clés DeepSeek et ElevenLabs uniquement côté serveur ; URL de conversation éphémère délivrée aux navigateurs authentifiés.
- Conversation vocale temps réel démarrée explicitement par l’utilisateur ; aucun microphone actif hors session.
- Outils déclarés dans un registre fermé.
- Exécution bornée en étapes et en durée.
- Toute action externe sensible requiert confirmation.
- Finance et modifications système interdites en V1.

## Frontières

### Application web

Responsabilités :

- interface de conversation vocale responsive ;
- session audio persistante via ElevenLabs Agents après consentement explicite ;
- transcription progressive et interruption de la réponse par la parole ;
- affichage des réponses, confirmations et erreurs ;
- installation PWA optionnelle ;
- aucune clé ou jeton sensible stocké dans JavaScript.

### Backend

Responsabilités :

- activation et session du navigateur ;
- orchestration LLM bornée ;
- politique de risque ;
- mémoire et audit ;
- fournisseurs cloud ;
- registre d’outils autorisés.

## Contrats V1

- `GET /health` — santé publique sans secret.
- `POST /v1/web/session` — activation initiale et cookie de session.
- `GET /v1/web/session` — état de la session.
- `DELETE /v1/web/session` — révocation et déconnexion.
- `POST /v1/agent/runs` — requête textuelle ou transcription.
- `POST /v1/agent/runs/{id}/confirm` — confirmation liée à une action exacte.
- `GET /v1/realtime/session` — URL ElevenLabs éphémère pour un navigateur privé authentifié.

## Risque

- `read` : exécution automatique possible.
- `personal` : exécution automatique si permission accordée.
- `write` : confirmation selon portée.
- `communicate` : confirmation obligatoire.
- `destructive` : confirmation renforcée.
- `financial` : interdit V1.
- `system` : interdit V1.

## Critère de V1 utilisable

La web app déployée en HTTPS peut être ouverte sur téléphone et ordinateur, activée, ouvrir une conversation audio temps réel après consentement, afficher les transcriptions progressives, accepter l’interruption vocale et se déconnecter en révoquant la session. Les tests backend et frontend doivent être verts.
