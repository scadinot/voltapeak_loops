# Feuille de route — `voltapeak_loops`

Ce document trace les axes d'évolution du projet. Il est organisé en **jalons** (versions successives envisagées) et en **backlog** (idées non priorisées).

## Légende

| Marqueur | Signification                   |
|----------|---------------------------------|
| `[ ]`    | À faire                         |
| `[~]`    | En cours                        |
| **P0**   | Priorité haute (court terme)    |
| **P1**   | Priorité moyenne (moyen terme)  |
| **P2**   | Priorité basse (long terme)     |

---

## Jalon 1 — Qualité et maintenabilité (court terme, **P0**)

L'objectif de ce jalon est de rendre le projet **industrialisable** : dépendances déclarées, tests en place, code modularisé.

- `[ ]` **Modulariser** le script unique en un package :
    - `io.py` — lecture des fichiers SWV ;
    - `signal.py` — lissage, détection de pic, correction de baseline ;
    - `pipeline.py` — orchestration d'un fichier et du lot ;
    - `gui.py` — interface Tkinter ;
    - `__main__.py` — point d'entrée.
- `[ ]` **Nettoyer** :
    - homogénéiser la casse (`camelCase` vs `snake_case` — choisir une convention).
- `[~]` **Pyright / annotations de type** — Pyright configuré dans `pyproject.toml` (`[tool.pyright]` avec `venvPath`/`venv` local). Annotations à compléter fonction par fonction pour viser un run sans warning. `mypy --strict` reste à arbitrer.
- `[ ]` **Tests unitaires** (`pytest`) :
    - `processData` — vérifier le tri, la suppression des zéros, l'inversion du signe ;
    - `smoothSignal` — invariants de longueur et d'amplitude ;
    - `getPeakValue` — pic gaussien synthétique à position connue ;
    - `calculateSignalBaseLine` — baseline linéaire synthétique restituée à ε près ;
    - `processSignalFile` — test d'intégration sur un fichier fixture.
- `[~]` **Linter / formateur** — `ruff` configuré (`[tool.ruff]` dans `pyproject.toml`, règles `E`/`F`/`W`/`I`, `line-length=120`) et passe sans erreur. `black` non adopté — à arbitrer (`ruff format` couvre déjà l'essentiel). Câblage pré-commit restant à faire.

---

## Jalon 2 — Flexibilité des paramètres (moyen terme, **P1**)

Aujourd'hui les paramètres algorithmiques sont codés en dur. Les rendre configurables permettra d'adapter l'outil à des montages différents sans modifier le code.

- `[ ]` Ajouter un panneau « Paramètres avancés » dans la GUI, exposant :
    - `window_length` (lissage) ;
    - `polyorder` (lissage) ;
    - `marginRatio` (recherche de pic) ;
    - `maxSlope` (recherche de pic) ;
    - `exclusionWidthRatio` (baseline) ;
    - `lambdaFactor` (baseline).
- `[ ]` **Persistance** des derniers paramètres utilisés dans un fichier JSON (`~/.pybaseline_config.json`).
- `[ ]` **Profils d'analyse nommés** : sauvegarder/charger un jeu complet de paramètres pour chaque type d'expérience.
- `[ ]` **Validation du nommage** en amont : afficher dans le journal, *avant* lancement, la liste des fichiers qui ne respectent pas le motif `*_XX_SWV_CYY_loopZZ.txt`.
- `[ ]` **Regex configurable** pour l'extraction des métadonnées (permet d'accueillir d'autres conventions de nommage interne).

---

## Jalon 3 — Ergonomie GUI (moyen terme, **P1**)

- `[ ]` **Annulation en cours de traitement** — bouton *Annuler* qui appelle `Pool.terminate()` proprement.
- `[ ]` **Prévisualisation d'un fichier** avant le lancement global : matplotlib embarqué (`FigureCanvasTkAgg`) pour valider visuellement lissage / baseline sur un échantillon.
- `[ ]` **Mémorisation inter-sessions** des choix utilisateur (dernier dossier, séparateurs, exports) — en complément de la configuration du Jalon 2.
- `[ ]` **Thème clair/sombre** via les thèmes `ttk` (`ttkthemes`).
- `[ ]` **Internationalisation** (FR/EN) via `gettext`.
- `[ ]` **Glisser-déposer** du dossier d'entrée dans la fenêtre (`tkinterdnd2`).

---

## Jalon 4 — Robustesse et performance (moyen terme, **P1**)

- `[ ]` **Journal persistant** — en complément de la zone d'affichage, écrire un `log.txt` dans le dossier de résultats (niveau INFO/WARNING/ERROR).
- `[ ]` **Rapport d'erreurs consolidé** — tableau en fin de traitement listant les fichiers rejetés et leur cause (regex non matchée, décodage impossible, colonne manquante, etc.).
- `[ ]` **Gestion mémoire matplotlib** sur gros lots : `plt.close('all')` périodique dans les workers, évaluer `matplotlib.pyplot` vs API orientée objet `Figure`.
- `[ ]` **Mode « dry-run »** (case à cocher) : statistiques de ce qui serait fait, sans aucun export sur disque.
- `[ ]` **Cache d'exécution** — si un fichier n'a pas été modifié depuis le dernier run, le sauter (hash + timestamp).

---

## Jalon 5 — Packaging et distribution (long terme, **P2**)

L'appel à `freeze_support()` est déjà en place ; le packaging PyInstaller devrait être direct.

- `[ ]` **Exécutable Windows autonome** via PyInstaller : `--onefile --noconsole --icon=logo.ico`.
- `[ ]` **Installeur MSI** (Inno Setup, WiX) pour déploiement GROUPE TRACE.
- `[ ]` **Bundle macOS** (`pyinstaller --windowed` puis `dmgbuild`).
- `[ ]` **Pipeline CI** (GitHub Actions ou GitLab CI) : lint + tests + build matriciel Windows/macOS/Linux.
- `[ ]` **Publication interne** : `pip install -e .` depuis le dépôt privé, éventuelle mise à disposition d'un dépôt PyPI interne.
- `[ ]` **Signature de code** Windows (Authenticode) pour éviter les alertes SmartScreen.
- `[ ]` **Pinner les versions de dépendances** — une fois un set validé, figer via `pip freeze > requirements.lock.txt` ou via PEP 735 (`[dependency-groups]` dans `pyproject.toml`), pour que chaque venv local ou CI soit reproductible bit-à-bit.

---

## Jalon 6 — Extensions métier (long terme, **P2**)

- `[ ]` **Autres techniques électrochimiques** — ajouter des profils de traitement dédiés :
    - voltammétrie cyclique (CV) ;
    - voltammétrie différentielle pulsée (DPV) ;
    - chronoampérométrie.
- `[ ]` **Algorithmes de baseline alternatifs** (sélectionnables dans la GUI) : ALS, arPLS, IModPoly, Rolling Ball — déjà disponibles dans `pybaselines`.
- `[ ]` **Détection multi-pics** avec `scipy.signal.find_peaks` (plusieurs pics par scan).
- `[ ]` **Export HTML interactif** (Plotly) pour inspection post-mortem partageable par e-mail.
- `[ ]` **Intégration LIMS** / base de données des expériences — écrire les résultats agrégés dans une table SQL plutôt que dans un XLSX.
- `[ ]` **Calibration / étalonnage** — relier la hauteur/position du pic à une concentration via une courbe d'étalonnage importée.

---

## Backlog — idées à évaluer (non priorisées)

- **Interface en ligne de commande** parallèle à la GUI : `python -m voltapeak_loops --input <dir> --output <dir> --config profile.json`, pour scripting et intégration dans des pipelines automatiques.
- **Mode batch multi-dossiers** — sélectionner un dossier parent et traiter chaque sous-dossier comme une expérience indépendante (un XLSX par sous-dossier).
- **Détection automatique du séparateur** et du séparateur décimal via `csv.Sniffer`.
- **Journalisation structurée** (`logging` stdlib) avec niveaux et rotation de fichiers.
- **Documentation générée** (Sphinx ou MkDocs) à partir des docstrings français.
- **Internationalisation du nommage** des sorties (colonnes `Voltage (V)` / `Current (A)` sélectionnables).
- **Passage à `concurrent.futures.ProcessPoolExecutor`** (plus moderne que `multiprocessing.Pool`, mêmes performances).
- **Option « conserver le signe original du courant »** (pour les métiers où l'inversion n'est pas souhaitée).

---

## Cadence de mise à jour

Cette feuille de route est **indicative**. Les priorités peuvent être ajustées selon les besoins terrain des équipes GROUPE TRACE. Toute demande de nouvelle fonctionnalité est la bienvenue — créer une issue ou ouvrir une discussion sur le dépôt interne.
