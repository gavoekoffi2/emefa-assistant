# Frontière proxy et limitation de débit

En production, `docker-compose.prod.yml` **ne publie aucun port hôte** pour EMEFA. Le conteneur rejoint seulement le réseau Docker externe `web`; le routeur Traefik est l’unique ingress et transmet l’adresse client à Uvicorn. Cette topologie est une condition de sécurité : ne jamais ajouter `ports:` au service `emefa` et ne pas connecter à `web` un conteneur non maîtrisé.

Uvicorn accepte les en-têtes forwarded afin de conserver l’IP client réelle derrière le proxy. Ce choix n’affaiblit pas le rate-limit même en cas de nombreuses adresses : `FailureLimiter` applique en plus du seau par IP un plafond global borné. Un test de release vérifie simultanément l’absence de port publié, l’activation Traefik et ce plafond global.

Si l’ingress change ou si un port hôte est publié, remplacer immédiatement `--forwarded-allow-ips "*"` par le CIDR/adresse fixe du proxy avant déploiement. L’adresse du conteneur Traefik n’est pas figée dans le compose actuel ; la coder en dur aujourd’hui casserait soit l’IP client, soit le routage après recréation du réseau.
