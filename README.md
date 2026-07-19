# EMEFA

EMEFA est une assistante personnelle vocale web/PWA, mobile-first, créée entièrement de zéro.

## Règle fondatrice

Ce dépôt ne contient aucun code provenant de PokeClaw ou de l’ancienne plateforme EMEFA. L’ancien projet est conservé séparément et ne fait pas partie de ce dépôt.

## Produit officiel

- `web/` — interface React/TypeScript installable en PWA sur téléphone et ordinateur ;
- `backend/` — API privée FastAPI, sessions, politiques d’action et passerelle vocale ;
- `docs/` — architecture et procédure de déploiement ;
- `android/` — prototype greenfield gelé, non déployé et non livré comme produit.

## Expérience vocale

EMEFA est une conversation vocale directe et interruptible, pas un chatbot à dictée :

1. le navigateur privé est activé une seule fois ;
2. un toucher ouvre une session audio persistante avec ElevenLabs Agents ;
3. l’utilisateur et EMEFA échangent oralement en temps réel ;
4. la détection de parole permet d’interrompre EMEFA au milieu d’une réponse ;
5. les transcriptions apparaissent progressivement dans l’interface ;
6. fermer la conversation coupe immédiatement le microphone, l’audio et la connexion.

Les clés DeepSeek et ElevenLabs restent exclusivement sur le serveur. Aucun paiement, suppression ou changement système autonome n’est autorisé sans politique et confirmation explicites.

## Démarrage local

### Backend

```bash
cp .env.example .env
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest
uvicorn emefa.main:app --reload
```

### Interface web

```bash
cd web
npm ci
npm test
npm run dev
```

## Construction et déploiement

```bash
npm --prefix web run build
docker compose -f docker-compose.prod.yml up -d --build
```

Les fichiers `.env`, bases locales, dépendances, builds et ressources de recherche ne sont jamais versionnés. Voir `docs/DEPLOIEMENT.md` pour l’exploitation du service.
