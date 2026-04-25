# Feuille de route — voltapeak_loops

Ce document recense les évolutions envisagées pour le projet, classées
par horizon (court / moyen / long terme) et par criticité. Chaque
entrée précise la **motivation** (pourquoi c'est utile) et, lorsque
pertinent, une **piste technique** (comment s'y prendre).

La liste est volontairement ouverte : ce ne sont pas toutes des
promesses, mais un réservoir d'idées à prioriser selon les besoins
réels des utilisateurs.

---

## Vue d'ensemble

| Horizon | Objectif principal | Effort estimé |
|---|---|---|
| [Court terme](#court-terme--qualité-de-base-du-projet) | Industrialiser le projet (modules, tests, types) | quelques heures à 1 journée |
| [Moyen terme](#moyen-terme--robustesse-et-configurabilité) | Configurabilité, ergonomie GUI, robustesse | quelques jours |
| [Long terme](#long-terme--plate-forme-et-écosystème) | Distribution, écosystème, extensions métier | plusieurs semaines |
| [Pistes exploratoires](#pistes-exploratoires) | Optimisations ponctuelles et UX avancée | à évaluer au cas par cas |

---

## Court terme — qualité de base du projet

### 1. Extraire le code en modules

**Motivation.** Les ~600 lignes actuelles mélangent entrée/sortie,
algorithmes numériques, génération de graphiques, parallélisme et
interface graphique. Cette structure freine la réutilisation
(impossible d'importer la chaîne d'analyse sans lancer Tkinter) et
rend les tests difficiles.

**Piste technique.** Éclater en :
```
voltapeak_loops/
├── __init__.py
├── io.py          # readFile, exports CSV / XLSX
├── processing.py  # processData, smoothSignal, getPeakValue, calculateSignalBaseLine
├── plotting.py    # plotSignalAnalysis
├── pipeline.py    # processSignalFile, agrégation Excel hiérarchique
├── gui.py         # launch_gui
└── cli.py         # mode batch sans GUI
```

### 2. Tests unitaires et de non-régression

**Motivation.** Aucun test n'existe. Toute modification (correction
d'un libellé, refactor, mise à jour de dépendance) peut altérer
silencieusement les sorties numériques sans qu'on s'en aperçoive
avant la prochaine campagne.

**Piste technique.** `pytest` + un jeu de **fichiers SWV de référence**
avec sorties attendues :
- tests unitaires sur `processData`, `smoothSignal`, `getPeakValue`,
  `calculateSignalBaseLine` (valeurs numériques à ε près avec
  `numpy.testing.assert_allclose`) ;
- test bout-en-bout sur `processSignalFile` à partir d'une fixture ;
- test d'intégration sur l'agrégation Excel (lecture du XLSX,
  vérification du MultiIndex Canal / Fréquence / Mesure).

### 3. Compléter les annotations de type

**Motivation.** Pyright est déjà configuré (`[tool.pyright]` avec
`venvPath`/`venv` local), mais les fonctions ne sont annotées qu'en
surface — `processData(dataFrame) -> tuple`, `readFile(filePath, sep,
decimal)` sans typer les arguments. Pyright ne peut donc détecter
qu'une fraction des erreurs d'usage.

**Piste technique.** Préciser tous les paramètres et retours
(`np.ndarray`, `pd.DataFrame`, `Path`, `tuple[float, float]`) ; viser
un run `pyright .` sans warning. `mypy --strict` reste à arbitrer dans
un second temps.

### 4. Câbler `ruff` et `pyright` en pré-commit

**Motivation.** `ruff check`, `ruff format` et `pyright` sont
configurés et passent sans erreur sur la base de code actuelle. Mais
rien n'empêche aujourd'hui un commit de réintroduire une violation.
Un pré-commit verrouille la qualité avant la revue.

**Piste technique.** [`pre-commit`](https://pre-commit.com) avec les
hooks officiels Astral `ruff` et `ruff-format`, plus un hook local
`pyright`. Documenter `pre-commit install` dans le README.

---

## Moyen terme — robustesse et configurabilité

### 5. Exposer les paramètres d'algorithme

**Motivation.** Les valeurs `window_length=11`, `polyorder=2`,
`marginRatio=0.10`, `maxSlope=500`, `exclusionWidthRatio=0.03`,
`lambdaFactor=1e3` sont codées en dur. Un opérateur qui veut adapter
l'outil à un autre type d'expérience doit modifier le code source.

**Piste technique.** Deux options complémentaires :
- **GUI** : onglet « Paramètres avancés » avec champs éditables et
  valeurs par défaut raisonnables ;
- **Fichier** : `config.toml` à la racine du dossier d'entrée, chargé
  au démarrage via `tomllib` (stdlib depuis Python 3.11), permettant
  de versionner les paramètres avec les données.

Compléter par des **profils nommés** (un jeu complet de paramètres par
type d'expérience) sauvegardés dans `~/.voltapeak_loops/profiles/*.json`.

### 6. Validation amont du nommage et regex configurable

**Motivation.** Les fichiers ne respectant pas le motif
`*_XX_SWV_CYY_loopZZ.txt` sont **silencieusement ignorés** : un
opérateur peut découvrir trop tard que la moitié de ses fichiers n'a
pas été traitée. Et la regex elle-même est figée — un autre laboratoire
avec une convention proche doit modifier le code.

**Piste technique.** Avant le lancement, scanner le dossier et lister
dans le journal les fichiers conformes/rejetés avec la cause (regex,
encodage, colonnes manquantes). Exposer la regex dans le `config.toml`
de l'item 5, avec groupes nommés (`(?P<variante>…)`, `(?P<canal>…)`,
`(?P<loop>…)`), et fournir 2-3 patterns prêts à l'emploi.

### 7. Annulation et prévisualisation interactive

**Motivation.** Lancer l'analyse sur plusieurs centaines de fichiers
et s'apercevoir trop tard que les paramètres sont mauvais oblige à
fermer brutalement la fenêtre ou à attendre la fin. Et il n'existe
aucun moyen de valider visuellement le pipeline (lissage, baseline,
détection) **avant** de lancer un lot.

**Piste technique.** Bouton *Annuler* qui appelle `Pool.terminate()`
proprement (multi-thread) ou positionne un flag lu en début de boucle
(séquentiel). Bouton *Prévisualiser* embarquant un canvas matplotlib
(`FigureCanvasTkAgg`) qui exécute la chaîne sur un fichier choisi et
affiche les courbes superposées, optionnellement avec sliders sur
`lambdaFactor`, `exclusionWidthRatio`, `marginRatio`.

### 8. Journal persistant et rapport d'erreurs consolidé

**Motivation.** Le journal Tkinter disparaît à la fermeture de
l'application. En cas d'incident sur un lot, impossible de
reconstituer ce qui a échoué et pourquoi. Et `processSignalFile`
capture toutes les exceptions dans un dictionnaire `{"error": …}` qui
agrège tous les modes d'échec.

**Piste technique.** Écrire un `log.txt` dans le dossier
`<source> (results)` (niveaux INFO/WARNING/ERROR via `logging`
stdlib). Définir des exceptions typées `InvalidSWVFileError`,
`PeakNotFoundError`, `BaselineEstimationError` héritant d'un `SWVError`
racine, et n'attraper que celles-ci au niveau du worker. En fin de
traitement, produire un tableau récapitulatif des fichiers rejetés
avec leur cause.

### 9. Détection automatique des séparateurs

**Motivation.** Chaque utilisateur doit cocher manuellement le bon
séparateur de colonnes et le bon séparateur décimal. Source d'erreur
fréquente — un mauvais choix produit des colonnes vides sans message
explicite.

**Piste technique.** `csv.Sniffer` sur les premières lignes pour
détecter le séparateur ; tester le parse en `.` puis en `,` et retenir
celui qui produit majoritairement des floats. La GUI conserverait le
choix manuel comme override.

### 10. Gestion mémoire matplotlib sur gros lots

**Motivation.** Sur des dossiers de plusieurs milliers de fichiers,
le cycle `plt.figure()` / `plt.savefig()` / `plt.close()` peut
accumuler des objets internes matplotlib et finir par saturer la
mémoire — voire échouer avec « Fail to allocate bitmap » sur Windows
(une des raisons du backend `Agg` aujourd'hui).

**Piste technique.** Évaluer le passage de `pyplot` à l'API orientée
objet (`Figure(figsize=…)` directement). Insérer un `plt.close('all')`
périodique dans les workers (toutes les N itérations). Profiler la
consommation en mode séquentiel pour confirmer la fuite et calibrer
la fréquence du nettoyage.

---

## Long terme — plate-forme et écosystème

### 11. Packaging distribuable

**Motivation.** Les utilisateurs finaux (scientifiques) n'ont pas
tous un environnement Python fonctionnel. Leur demander d'installer
Python + 6 dépendances + comprendre les venv est un obstacle majeur
à l'adoption.

**Piste technique.**
- **Exécutable Windows** via PyInstaller (`--onefile --windowed
  --icon=logo.ico`) : un seul `.exe` double-cliquable. `freeze_support()`
  est déjà en place dans `main()`.
- **Installeur MSI** (Inno Setup ou WiX) pour déploiement standardisé.
- **Bundle macOS** : `pyinstaller --windowed` puis `dmgbuild`.
- **Signature de code** Windows (Authenticode) pour éviter les
  alertes SmartScreen.

### 12. Intégration continue (CI/CD)

**Motivation.** Aucun garde-fou ne vérifie aujourd'hui qu'un commit
ne casse pas le code. Une régression peut passer inaperçue jusqu'à
la prochaine campagne.

**Piste technique.** GitHub Actions (ou GitLab CI) :
- `ruff check` et `ruff format --check` ;
- `pyright` ;
- `pytest` ;
- build matriciel Windows / macOS / Linux de l'exécutable
  PyInstaller à chaque tag git.

### 13. Pinner les versions de dépendances

**Motivation.** `pyproject.toml` liste les dépendances **sans
contrainte de version**. Une mise à jour cassante (`numpy 2.0`,
`pandas 3.0`, `matplotlib 4.0`) pourrait casser silencieusement un
déploiement reproduit dans un nouveau venv plusieurs mois plus tard.

**Piste technique.** Une fois un set validé sur plusieurs campagnes,
figer via `pip freeze > requirements.lock.txt`, ou via PEP 735
(`[dependency-groups]` dans `pyproject.toml`), ou via l'écosystème
[`uv`](https://docs.astral.sh/uv/) avec son `uv.lock`.

### 14. Autres techniques électrochimiques

**Motivation.** L'outil est aujourd'hui spécifique SWV. Plusieurs
équipes utilisent aussi la voltammétrie cyclique (CV), différentielle
pulsée (DPV), chronoampérométrie. Ces techniques partagent une partie
du pipeline (lecture, lissage, baseline, agrégation) mais diffèrent
dans la détection (multi-pics, surface intégrée, plateau de courant).

**Piste technique.** Profil de traitement par technique, sélectionnable
dans la GUI ou inféré du nom de fichier (motif `_SWV_` / `_CV_` /
`_DPV_`). Les modules `processing.py` et `pipeline.py` (item 1)
deviennent paramétrables par technique ; la baseline asPLS reste la
même, seul le post-traitement diffère.

### 15. Algorithmes alternatifs de baseline

**Motivation.** asPLS n'est pas universel : certains signaux
particuliers sont mieux traités par arPLS, airPLS, drPLS, IModPoly
ou Rolling Ball. Offrir le choix améliorerait la qualité des
corrections sur les cas difficiles.

**Piste technique.** La bibliothèque `pybaselines` expose déjà la
plupart de ces algorithmes. Ajouter un sélecteur dans la GUI ;
optionnellement, un **mode comparaison** qui trace les baselines
concurrentes côte à côte sur le PNG pour aider au choix.

### 16. Détection multi-pics

**Motivation.** Certains SWV présentent plusieurs pics (mélange
d'espèces électroactives). L'outil n'en détecte aujourd'hui qu'un
seul, ce qui invalide l'analyse pour ces cas.

**Piste technique.** `scipy.signal.find_peaks` sur le signal corrigé
avec seuil de prominence ; ajustement gaussien ou lorentzien pour la
séparation/intégration. Nouvelles colonnes dans le récapitulatif
Excel pour le 2ème pic, 3ème pic… L'en-tête MultiIndex (Canal /
Fréquence / Mesure) accueille naturellement ce niveau supplémentaire.

### 17. Calibration et étalonnage

**Motivation.** Le résultat agrégé reste aujourd'hui en
(Tension, Courant). Pour un usage analytique, il faut convertir le
courant du pic en concentration via une courbe d'étalonnage —
opération aujourd'hui manuelle dans Excel.

**Piste technique.** Importer une courbe d'étalonnage
(CSV `concentration → courant_pic`) ; ajustement linéaire ou
polynomial ; nouvelles colonnes `Concentration` dans le classeur
agrégé. Possibilité de générer la courbe d'étalonnage *à partir*
d'une campagne de fichiers nommés différemment.

### 18. Intégration LIMS / base de données expérimentale

**Motivation.** Chaque campagne produit aujourd'hui un dossier
isolé. Pour comparer entre campagnes (suivi temporel d'une
électrode, dérive d'un appareil), il faut ré-ouvrir manuellement
chaque XLSX.

**Piste technique.** SQLite local (ou PostgreSQL pour
multi-utilisateur). Schéma `Run(date, opérateur, fréquence, …)`,
`File(run_id, base, électrode, pic_V, pic_A, hash_source)`. Interface
de requête simple (Streamlit ou notebook). Option d'export vers le
LIMS GROUPE TRACE quand celui-ci sera disponible.

---

## Pistes exploratoires

Idées à évaluer au cas par cas, sans priorité ferme.

### Profilage et optimisation

- **Benchmarker** `Pool.imap` vs
  `concurrent.futures.ProcessPoolExecutor` avec `chunksize` ajusté
  sur de gros lots (> 500 fichiers).
- **Cache d'exécution** : ne pas retraiter un fichier dont le hash
  SHA-256 n'a pas changé depuis la dernière exécution (utile en
  re-runs partiels).
- **Mode batch multi-dossiers** : sélectionner un dossier parent et
  traiter chaque sous-dossier comme une expérience indépendante (un
  XLSX agrégé par sous-dossier).
- **Lazy-loading de matplotlib** : l'import top-level est lent et
  inutile tant que l'utilisateur ne demande pas d'export PNG.
  Déplacer l'import dans `plotSignalAnalysis`. À mettre en balance
  avec `matplotlib.use('Agg')` qui doit précéder l'import de pyplot.

### Expérience utilisateur

- **Mémorisation inter-sessions** des choix utilisateur (dernier
  dossier, séparateurs, exports), en complément des profils de
  l'item 5.
- **Thème clair/sombre** via les thèmes `ttk` (`ttkthemes`).
- **Internationalisation** (FR/EN, voire DE) via `gettext` et
  détection de la locale système au premier lancement. Inclure les
  en-têtes de colonnes des sorties (`Voltage (V)` / `Current (A)`).
- **Glisser-déposer** du dossier d'entrée dans la fenêtre via
  `tkinterdnd2`.
- **Rapport PDF unifié** par campagne (ReportLab ou WeasyPrint) :
  page de garde, tableau des résultats, une page par électrode avec
  PNG + valeurs numériques. Plus pratique à archiver/partager qu'un
  XLSX + N PNG.

### Robustesse aux données

- **Validation de la longueur minimale** du signal avant lissage :
  `savgol_filter(window_length=11)` exige au moins 11 points. En
  deçà, lever une `InvalidSWVFileError` explicite plutôt qu'une
  exception bas-niveau scipy.
- **Mode dry-run** (case à cocher) : statistiques de ce qui serait
  fait (fichiers conformes, paramètres effectifs, dossier de sortie
  cible) sans aucun export sur disque.
- **Option « conserver le signe original du courant »** pour les
  mesures où l'inversion n'est pas souhaitée (CV anodique notamment).
- **Gestion des balayages aller-retour** (cyclic SWV) : l'inversion
  systématique du signe pourrait être mal adaptée si la première
  demi-vague est anodique.

---

## Contribuer à cette feuille de route

Les priorités évoluent avec les retours utilisateurs. Si une évolution
vous intéresse — ou si vous en voyez une qui manque — ouvrez une issue
ou contactez le mainteneur.
