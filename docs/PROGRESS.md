# Avancement

Une section par phase : ce qui est fait, ce qui est mesuré, où c'est vérifié, ce qui reste.

## P0 : Squelette (terminée le 2026-10-28)

### Fait
- Outillage : `pyproject.toml` (uv, Python 3.12) et `uv.lock`, ruff, pytest, Makefile, `.gitignore`,
  `.gitattributes`, `.env.example`.
- README minimal (avertissement « NetCo fictive, données synthétiques » en première section), `docs/LIMITS.md`,
  `docs/NEXT.md`.
- `docker-compose.yml` : Camunda **8.10** dans sa configuration légère officielle (`camunda/camunda:8.10.7`, soit
  Zeebe, Operate, Tasklist et Admin ; `camunda/connectors-bundle:8.10.2`), plus vcsim (`vmware/vcsim:v0.56.2`).
  La version et le fichier ont été vérifiés dans la documentation et l'archive officielles de Camunda le
  2026-10-28. Les écarts sont listés en tête du fichier.
- `src/stack/health.py` : sonde, depuis l'hôte, des 6 points d'accès (REST, management, Operate, Tasklist,
  Connectors, vcsim). `make up` attend qu'ils répondent tous.
- CI GitHub Actions : un job `lint-test` (`make lint test`) et un job `stack` (`make up`, puis arrêt de la pile).
- Les cibles des phases suivantes (`seed`, `deploy-bpmn`, `workers`, `e2e`, `eval`, `metrics`, `readme`) existent
  et échouent avec un message explicite (« arrives in phase Px »).

### Mesuré (une seule exécution, à titre indicatif)
- Tests unitaires : 8/8 passent.
- `make up` sur le PC de Seif (Windows 10, Docker Desktop 28.5.1) : 140 s au premier lancement, téléchargement des
  images compris, puis 20 s avec les images en cache.
- Mémoire au repos : orchestration environ 620 Mo (limite 1 Go), connectors environ 390 Mo (limite 512 Mo), vcsim
  environ 15 Mo.
- GitHub Actions : 10 s pour le job `lint-test` ; 52 s pour le job `stack`, dont 42 s pour `make up`, images
  téléchargées comprises.

### Vérifié où
CI de référence : [run 40690470381](https://github.com/26sneakysnake/infra-request-orchestrator/actions/runs/40690470381)
sur le commit `ecf3b63`. Le premier run (commit `efa6970`) a échoué avant toute exécution : `astral-sh/setup-uv@v10`
n'existe pas comme étiquette. Corrigé en épinglant `v10.3.2`.

| Vérification | PC de Seif (Windows) | GitHub Actions (Linux) |
|---|---|---|
| `make lint test` | vert | vert |
| `make up` : les 6 points d'accès répondent | vert | vert (la sonde sort en erreur sinon) |
| `/v2/topology` : 1 broker en 8.10.7, partition `healthy` | vérifié avec curl | non vérifié |
| Operate et Tasklist servent leur page (HTTP 200) | vérifié avec curl | non vérifié |
| Connexion `demo/demo` à l'API REST (recherche de définitions de processus) | vérifiée avec curl | non vérifiée |
| `make down`, puis relance à froid | vert | `docker compose down -v` en fin de job |

Non vérifié : la connexion interactive à Operate dans un navigateur. Je n'ai testé que les réponses HTTP.

### Reste
- Rien pour P0.
- À surveiller : GitHub annonce que `ubuntu-latest` passe à Ubuntu 26 à partir du 19 octobre 2026. Si le job
  `stack` casse, épingler `ubuntu-24.04`.
- `CONTEXT.md` reste local, ignoré par git, à la demande de Seif. `CLAUDE.md` y fait référence.
- Prochaine phase : P1, seulement avec l'accord de Seif.
