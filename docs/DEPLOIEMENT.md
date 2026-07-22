# Déploiement EMEFA Web

## Accès

- Application : https://emefa.76.13.129.252.sslip.io
- Santé du service : https://emefa.76.13.129.252.sslip.io/health
- Déploiement : conteneur Docker `emefa-web`, réseau Traefik `web`
- Données : volume Docker persistant `emefa_emefa_data`

## Activation privée

Le code d’activation réel est conservé uniquement dans le fichier `.env` protégé (`chmod 600`). Il ne doit pas être ajouté à Git.

Trois navigateurs au maximum peuvent être activés. La déconnexion révoque le navigateur et libère sa place.

## Activer la conversation vocale temps réel

1. Ouvrir `/root/projets/emefa/.env` sur le serveur.
2. Renseigner `EMEFA_ELEVENLABS_API_KEY` et `EMEFA_ELEVENLABS_AGENT_ID` sans guillemets.
3. La clé ne doit jamais être envoyée au navigateur : `/v1/realtime/session` génère une URL de conversation éphémère après vérification du navigateur privé.
4. La conversation utilise ElevenLabs Agents en continu : détection de parole, synthèse vocale et interruption pendant la réponse.

## Activer le moteur agent (DeepSeek ou OpenRouter)

Deux options — la clé ne doit jamais être commitée dans le dépôt ni exposée au navigateur.

**Option A — DeepSeek direct :**

1. Dans le même fichier `.env`, renseigner `EMEFA_DEEPSEEK_API_KEY` sans guillemets.
2. Conserver `EMEFA_DEEPSEEK_MODEL=deepseek-v4-flash`.

**Option B — OpenRouter (recommandé si vous avez une clé `sk-or-…`) :**

1. Dans le même fichier `.env`, renseigner `EMEFA_OPENROUTER_API_KEY` sans guillemets.
2. Optionnel : choisir le modèle avec `EMEFA_OPENROUTER_MODEL` (défaut : `deepseek/deepseek-chat`, économique et compatible avec les appels d'outils). Vérifier le nom exact sur openrouter.ai/models si le modèle par défaut renvoie une erreur.
3. Si les deux clés sont présentes, DeepSeek direct est prioritaire.

## Activer la boîte mail gouvernée (Himalaya)

EMEFA lit, recherche, prépare des brouillons et envoie des e-mails via le CLI
`himalaya` connecté au compte configuré (par ex. graphistegpt). Chaque **envoi**
demande votre approbation explicite avant de partir.

1. Installer et configurer `himalaya` pour le compte voulu sur le serveur.
2. Dans `.env`, renseigner :
   - `EMEFA_EMAIL_ACCOUNT` (nom du compte himalaya, ex. `graphistegpt`)
   - `EMEFA_HIMALAYA_BINARY` (optionnel, défaut `himalaya`)
   - `EMEFA_HIMALAYA_CONFIG` (optionnel, chemin du fichier de config himalaya)
3. Redémarrer le service. Les compétences `email_send`, `email_search`,
   `email_read` et `email_create_draft` n'apparaissent dans
   `/v1/system/status` que si `EMEFA_EMAIL_ACCOUNT` est présent. Sur le **canal
   vocal**, seuls l'envoi et le brouillon sont disponibles (la lecture/recherche
   de la boîte est réservée au canal texte authentifié — moindre privilège).
4. Test : demandez par écrit ou à la voix « Envoie un e-mail de test à … » —
   la carte d'approbation doit apparaître avant tout envoi.

## Activer le brief matinal proactif (optionnel)

1. Dans `.env`, définir `EMEFA_BRIEF_HOUR` (heure locale du serveur, ex. `7`).
   Sans cette variable, aucun travail proactif ne s'exécute.
2. Optionnel : `EMEFA_BRIEF_EMAIL_TO=votre@adresse` pour recevoir le brief par
   e-mail chaque matin (nécessite la boîte mail configurée ci-dessus). **Cette
   variable vaut approbation permanente et cadrée** pour ce seul envoi
   quotidien — aucune autre communication n'est couverte. Retirez-la pour
   révoquer.
3. Le brief du jour apparaît aussi dans l'interface (bandeau « Votre brief du
   jour est prêt ») et via `GET /v1/briefings/today`.

## Brancher la voix sur le cerveau EMEFA (Custom LLM)

Une fois le moteur agent activé ci-dessus, la voix peut utiliser le même cerveau
et le même contexte métier que le texte :

1. Dans `.env`, définir `EMEFA_VOICE_LLM_TOKEN` avec un secret long et aléatoire
   (ex. `openssl rand -hex 32`).
2. Dans le dashboard ElevenLabs → votre agent → **LLM** : choisir **Custom LLM**,
   renseigner l'URL `https://<votre-domaine>/v1/voice-llm/chat/completions`
   et, comme clé API, la valeur exacte de `EMEFA_VOICE_LLM_TOKEN`.
3. Garder la persona ElevenLabs courte : chaque tour vocal passe désormais par
   le moteur gouverné d'EMEFA — profil, mémoire, tâches, pipeline et e-mail y
   sont accessibles à la voix. Les actions à conséquence (envoi d'e-mail,
   effacements) ne s'exécutent jamais depuis la voix seule : EMEFA annonce
   oralement qu'une approbation attend à l'écran, et reprend une fois votre
   décision prise.
4. Rollback immédiat possible : re-sélectionner le LLM ElevenLabs d'origine dans
   le dashboard, sans redéploiement.

Puis recréer seulement le service EMEFA :

```bash
cd /root/projets/emefa
docker compose -f docker-compose.prod.yml up -d --force-recreate emefa
```

5. Vérifier :

```bash
curl -fsS https://emefa.76.13.129.252.sslip.io/health
```

Sans clé, l’application reste accessible et activable, mais affiche que le moteur de langage n’est pas encore configuré.

## Connecteur e-mail provisoire et MCP Google Workspace

Pour les essais, EMEFA peut utiliser le compte Himalaya `graphistegpt` via quatre
compétences gouvernées : recherche, lecture en aperçu, création de brouillon et
envoi. L’envoi est classé `communicate` et ne s’exécute qu’après approbation
explicite portant sur le destinataire, l’objet et le corps exacts.

Configuration du conteneur :

```dotenv
EMEFA_EMAIL_ACCOUNT=graphistegpt
EMEFA_HIMALAYA_BINARY=/usr/local/bin/himalaya
EMEFA_HIMALAYA_CONFIG=/run/secrets/himalaya/config.toml
```

Le binaire et le dossier de configuration sont montés en lecture seule. Les
identifiants ne doivent jamais être copiés dans le dépôt ni exposés à l’API.

Pour l’intégration Google Workspace définitive, le candidat retenu est
[`taylorwilsdon/google_workspace_mcp`](https://github.com/taylorwilsdon/google_workspace_mcp) :
serveur MCP MIT actif couvrant Gmail, Calendar, Drive, Docs, Sheets, Slides,
Forms, Tasks, Contacts et Chat, avec OAuth 2.1. Il remplacera l’adaptateur
Himalaya derrière l’interface `EmailProvider`; il ne doit pas être ajouté au MCP
global de Hermes comme substitut à l’intégration autonome d’EMEFA.

## Coût IA

Tarifs officiels DeepSeek consultés lors du déploiement :

- `deepseek-v4-flash` : 0,14 USD par million de tokens d’entrée hors cache ;
- entrée en cache : 0,0028 USD par million de tokens ;
- sortie : 0,28 USD par million de tokens.

La facturation dépend uniquement des tokens consommés. Source : https://api-docs.deepseek.com/quick_start/pricing

## Validation de staging (smoke-test)

Après chaque déploiement, exécuter le smoke-test automatisé contre l'instance
cible. Il ne dépend d'aucune installation (Python 3 standard uniquement),
n'envoie jamais de vrai e-mail et n'exécute aucune action destructive.

```bash
python3 scripts/staging_smoke_test.py \
  --base-url https://emefa.76.13.129.252.sslip.io \
  --enrollment-code "<code privé d'activation>"
```

Le code peut aussi provenir de `EMEFA_ENROLLMENT_CODE` ou d'une saisie masquée
en terminal interactif ; il n'est jamais affiché. Ajouter `--no-writes` pour un
passage strictement en lecture seule.

Le script affiche `PASS` / `FAIL` / `SKIP` par étape et **renvoie un code de
sortie ≠ 0 si une étape critique échoue**. Ce qu'il couvre automatiquement :

1. démarrage et `/health` ;
2. activation d'une session privée puis état système (`brain_configured`,
   `voice_configured`, compétences, `schema_version`) ;
3. lecture du profil assistante et du profil métier ;
4. mémoire : lecture, export, et cycle create/read/forget sur une donnée témoin
   (`ZZ-SMOKE…`) — **uniquement si le cerveau LLM est configuré**, sinon `SKIP` ;
5. joignabilité de l'endpoint de brief du jour ;
6. mécanisme d'approbation : liste, puis round-trip testé **par le REFUS** d'un
   envoi d'e-mail (jamais d'approbation, donc aucun envoi réel) — `SKIP` sans
   cerveau/boîte mail ;
7. pipeline commercial : lecture, ajout d'un prospect témoin puis nettoyage —
   `SKIP` sans cerveau.

Les données de test utilisent le préfixe identifiable `ZZ-SMOKE` et sont
nettoyées automatiquement quand c'est possible ; la session de test est
révoquée en fin de course pour libérer sa place navigateur.

### Reste OBLIGATOIREMENT manuel avant de valider le staging

Le smoke-test ne peut pas se substituer à ces vérifications, qui restent à faire
à la main :

- **Document Word (DOCX)** : ouvrir et inspecter un document généré (structure,
  mise en forme, rendu visuel).
- **E-mail réel (Himalaya)** : envoi approuvé + réception effective sur une vraie
  boîte (le smoke-test s'arrête volontairement au refus d'envoi).
- **Chaîne vocale complète** : micro → ElevenLabs → Custom LLM → EMEFA, avec
  réponse parlée cohérente et contexte métier.
- **Interruption (barge-in) et latence** : couper EMEFA pendant sa réponse
  vocale, et mesurer le temps jusqu'au premier son et la latence bout-en-bout.

## Exploitation

```bash
# État
docker compose -f docker-compose.prod.yml ps

# Journaux
docker logs --tail 100 emefa-web

# Redéploiement
docker compose -f docker-compose.prod.yml up -d --build
```

Le conteneur utilise `restart: unless-stopped` et redémarre automatiquement après un redémarrage du VPS.