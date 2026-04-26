# voltapeak_loops

Outil graphique (Tkinter) de traitement en masse de fichiers de **voltammétrie à vagues carrées (SWV)** avec correction automatique de ligne de base par l'algorithme **asPLS Whittaker**, parallélisé sur tous les cœurs CPU et agrégation des résultats dans un classeur Excel hiérarchique.

---

## Table des matières

- [Contexte métier](#contexte-métier)
- [Fonctionnalités](#fonctionnalités)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Format des fichiers d'entrée](#format-des-fichiers-dentrée)
- [Utilisation — interface graphique](#utilisation--interface-graphique)
- [Résultats produits](#résultats-produits)
- [Chaîne de traitement par fichier](#chaîne-de-traitement-par-fichier)
- [Paramètres algorithmiques](#paramètres-algorithmiques)
- [Architecture logicielle](#architecture-logicielle)
- [Performance et multiprocessing](#performance-et-multiprocessing)
- [Dépannage (FAQ)](#dépannage-faq)
- [Licence et auteur](#licence-et-auteur)

---

## Contexte métier

La **voltammétrie à vagues carrées** (Square Wave Voltammetry, SWV) est une technique électrochimique qui mesure le courant traversant une électrode en fonction d'un potentiel imposé. Le signal obtenu présente typiquement un **pic** caractéristique de l'espèce analysée, superposé à une **ligne de base** (baseline) dérivant doucement avec le potentiel.

Pour exploiter le pic, il faut :

1. **lisser** le signal (bruit de mesure) ;
2. **estimer puis soustraire** la ligne de base ;
3. **relever** les coordonnées (tension, courant) du pic corrigé.

Ce script automatise ces étapes sur un lot de fichiers. Il s'appuie sur :

- **Savitzky–Golay** pour le lissage (convolution polynomiale locale) ;
- **asPLS Whittaker** (asymmetric Penalized Least Squares — implémenté par la bibliothèque [`pybaselines`](https://pybaselines.readthedocs.io/)) pour l'estimation robuste de la baseline, avec une pondération réduite autour du pic pour éviter que la baseline ne « suive » le pic et ne s'annule.

---

## Fonctionnalités

- Interface graphique simple (Tkinter), sans installation serveur.
- Traitement parallèle de tous les fichiers du dossier sélectionné (`multiprocessing.Pool` sur l'ensemble des cœurs disponibles), **basculable en mode séquentiel** depuis la GUI (utile pour le débogage).
- Paramètres de lecture CSV configurables : séparateur de colonnes (tabulation, virgule, point-virgule, espace) et séparateur décimal (point ou virgule).
- Lissage Savitzky-Golay (fenêtre 11, ordre 2).
- Détection du pic dans la région centrale du scan, avec filtre de pente.
- Correction de baseline **asPLS Whittaker** avec zone d'exclusion centrée sur le pic.
- **Deux formats de noms de fichiers** supportés (détection automatique fichier par fichier) : *loops* (suffixe `_loopZZ`) et *dosage* (préfixe d'ordre + concentration). Cf. [Format des fichiers d'entrée](#format-des-fichiers-dentrée).
- **Export global** : un classeur Excel `.xlsx` agrégeant les pics corrigés de tous les fichiers, avec en-tête hiérarchique à trois niveaux (Canal / Variante / Mesure) et une ligne par itération (loop) ou par concentration selon le format.
- **Exports optionnels par fichier** : graphique PNG 300 dpi, CSV ou XLSX nettoyé.
- Journal de traitement et barre de progression en temps réel.
- Bouton « Ouvrir le dossier de résultats » en fin de traitement.
- Multiplateforme : Windows, macOS, Linux.

---

## Prérequis

- **Python ≥ 3.10** (la syntaxe `tuple[...]` des annotations de type l'impose).
- **Système d'exploitation** : Windows 10/11, macOS ≥ 11, ou distribution Linux récente.
- **Tkinter** (inclus dans la distribution standard de Python sous Windows et macOS ; installable via `apt install python3-tk` sous Debian/Ubuntu si absent).

Bibliothèques Python requises :

| Paquet         | Rôle                                                       |
|----------------|------------------------------------------------------------|
| `numpy`        | Calculs vectoriels (signal, pondérations).                 |
| `pandas`       | Lecture des fichiers, pivot, export Excel.                 |
| `scipy`        | Filtre Savitzky-Golay (`scipy.signal.savgol_filter`).      |
| `matplotlib`   | Tracé des graphiques PNG.                                  |
| `pybaselines`  | Algorithme asPLS Whittaker (`pybaselines.whittaker.aspls`).|
| `openpyxl`     | Écriture des fichiers Excel (dépendance indirecte).        |

Installation des dépendances :

```bash
pip install numpy pandas scipy matplotlib pybaselines openpyxl
```

---

## Installation

```bash
# 1. Récupérer le dépôt
git clone <url-du-depot> voltapeak_loops
cd voltapeak_loops

# 2. (Recommandé) Créer un environnement virtuel
python -m venv .venv
# Windows :
.venv\Scripts\activate
# macOS / Linux :
source .venv/bin/activate

# 3. Installer les dépendances — deux options au choix :

# 3.A (recommandé) : versions figées et testées
pip install -r requirements.txt

# 3.B (fallback explicite, sans requirements.txt)
# pip install numpy pandas scipy matplotlib pybaselines openpyxl

# 4. Lancer l'application — depuis le dossier *parent* du projet
cd ..
python -m voltapeak_loops
```

> **Quand utiliser laquelle ?**
> - **3.A** — voie standard. Le `requirements.txt` épingle les versions exactes (`~=`) sur lesquelles l'outil a été validé : pas de mauvaise surprise sur une version récente cassante.
> - **3.B** — fallback de dépannage si `requirements.txt` n'est pas exploitable (par exemple, environnement réseau restreint avec un miroir PyPI partiel).

### Intégration IDE (VS Code / Pylance / Pyright)

Le projet déclare dans [`pyrightconfig.json`](pyrightconfig.json) les clefs `venvPath = "."` et `venv = ".venv"` : **Pylance et `pyright` CLI lisent automatiquement le `.venv` créé ci-dessus**, sans configuration supplémentaire.

Un fichier [`.vscode/settings.json`](.vscode/settings.json) pointe également l'extension Python de VS Code vers `${workspaceFolder}/.venv/Scripts/python.exe` (chemin relatif portable). Si VS Code ne détecte pas l'environnement à l'ouverture du dossier, forcer la sélection via `Ctrl+Shift+P` → **Python: Select Interpreter** → `.venv/Scripts/python.exe`.

---

## Format des fichiers d'entrée

### Nommage

L'outil reconnaît **deux formats** de noms de fichiers, détectés automatiquement fichier par fichier (le format `loops` est testé en premier car plus restrictif ; `dosage` sert ensuite de fallback).

#### Format `loops` — itérations sur une même condition

```
<n'importe-quoi>_XX_SWV_CYY_loopZZ.txt
```

| Groupe      | Signification                                        | Exemple |
|-------------|------------------------------------------------------|---------|
| `XX`        | Variante sur 2 chiffres (souvent une fréquence Hz)   | `05`    |
| `CYY`       | Identifiant de canal (C + 2 chiffres)                | `C03`   |
| `loopZZ`    | Numéro d'itération (1 chiffre ou plus)               | `loop7` |

Exemples valides :

```
echantillon_A_05_SWV_C00_loop1.txt
run2_15_SWV_C12_loop10.txt
i-t 3-CypA_01_SWV_C09_loop37.txt
```

#### Format `dosage` — série de concentrations

```
ZZ_<concentration>_XX_SWV_CYY.txt
```

| Groupe          | Signification                                                         | Exemple    |
|-----------------|-----------------------------------------------------------------------|------------|
| `ZZ`            | Préfixe numérique servant au tri (ordre expérimental)                 | `10`       |
| `<concentration>` | Libellé de concentration (forme libre, ne contient pas `_`)         | `250nm`    |
| `XX`            | Variante sur 2 chiffres (souvent un réplica)                          | `01`       |
| `CYY`           | Identifiant de canal (C + 2 chiffres)                                 | `C05`      |

Exemples valides :

```
01_0nm_01_SWV_C05.txt
10_250nm_01_SWV_C05.txt
13_1000nm_02_SWV_C05.txt
```

Le tri des lignes du tableau Excel final s'effectue selon le préfixe `ZZ` (numérique), **pas** selon l'ordre alphabétique du libellé de concentration : `0nm, 0.1nm, 0.25nm, …, 1000nm` apparaissent dans l'ordre expérimental.

#### Règles d'inclusion

> ⚠️ Tout fichier ne respectant **aucun** des deux motifs est **silencieusement ignoré**. Pensez à vérifier le nommage si aucun résultat n'apparaît pour certains fichiers.

> ❌ Un dossier qui mélange les deux formats (par ex. fichiers `*_loopZZ.txt` côte à côte avec `ZZ_<conc>_*.txt`) **provoque l'annulation de l'export Excel** : le journal affiche un message d'erreur explicite et aucun classeur agrégé n'est produit. Séparer les deux types de fichiers dans des dossiers distincts.

### Contenu

- **Encodage** : `latin1` (tolère les caractères accentués générés par les appareils).
- **Première ligne** : ignorée (en-tête de l'appareil).
- **Colonnes exploitées** : les **deux premières**, interprétées respectivement comme `Potential` (V) et `Current` (A). Les colonnes suivantes, s'il y en a, sont ignorées.
- **Séparateur de colonnes** : au choix dans la GUI (tabulation par défaut).
- **Séparateur décimal** : au choix dans la GUI (point par défaut).

---

## Utilisation — interface graphique

Lancer l'application depuis le dossier *parent* du projet :

```bash
python -m voltapeak_loops
```

La fenêtre comporte cinq zones :

1. **Dossier d'entrée** — bouton *Parcourir* pour sélectionner le dossier contenant les fichiers `.txt` à traiter. Le dernier dossier ouvert est mémorisé pour les sélections suivantes (au sein de la même session).
2. **Paramètres de lecture** :
   - *Séparateur de colonnes* : `Tabulation` (défaut), `Virgule`, `Point-virgule`, `Espace`.
   - *Séparateur décimal* : `Point` (défaut) ou `Virgule`.
   - *Export des fichiers traités* : `Ne pas exporter` (défaut), `.CSV`, ou `Excel`.
   - *Export des graphiques* : `Ne pas exporter` (défaut) ou `.png`.
   - *Mode de traitement* : `Activer le multi-thread (un processus par cœur)` (défaut) ou `Désactiver (traitement séquentiel)`. Cf. [Performance et multiprocessing](#performance-et-multiprocessing) pour savoir quand basculer en séquentiel.
3. **Progression du traitement** — barre de progression se remplissant au fil de l'avancement.
4. **Journal de traitement** — zone de texte affichant, fichier par fichier, le statut (traité, ignoré, en erreur), ainsi qu'un récapitulatif final (nombre de fichiers traités, durée totale).
5. **Actions** :
   - *Lancer l'analyse* : démarre le traitement parallèle ;
   - *Ouvrir le dossier de résultats* : s'active en fin de traitement et ouvre l'explorateur de fichiers natif sur le dossier de sortie.

---

## Résultats produits

À côté du dossier source, un dossier nommé `<nom-du-dossier-source> (results)` est créé (ou nettoyé s'il existe déjà). Il contient :

### Classeur Excel agrégé — toujours produit

Fichier : `<nom-du-dossier-source>.xlsx`.

Structure hiérarchique (en-tête sur trois niveaux) :

| *Index*   | Canal `C00`         |                     | Canal `C01`         |                     | … |
|-----------|---------------------|---------------------|---------------------|---------------------|---|
|           | Variante `05`       |                     | Variante `05`       |                     |   |
|           | Tension (V)         | Courant (A)         | Tension (V)         | Courant (A)         |   |
| *L₁*      | *v₁*                | *c₁*                | *v₁'*               | *c₁'*               |   |
| *L₂*      | *v₂*                | *c₂*                | *v₂'*               | *c₂'*               |   |
| …         | …                   | …                   | …                   | …                   |   |

- **Chaque ligne** = une itération (loop) ou une concentration, selon le format détecté.
- **Le libellé d'index varie selon le format** :
  - format `loops` → en-tête de colonne `Itération`, valeurs `loop0, loop1, loop2, …` ;
  - format `dosage` → en-tête de colonne `Concentration`, valeurs `0nm, 0.1nm, 250nm, …` (triées dans l'ordre expérimental, cf. [Format `dosage`](#format-dosage--série-de-concentrations)).
- **Chaque bloc de deux colonnes** = un couple (canal, variante), avec tension et courant du pic corrigé. Selon le format, *variante* représente une fréquence (loops) ou un réplica (dosage).
- Les colonnes sont triées naturellement par canal (`C00 → C99`), puis par variante, puis Tension avant Courant.

### Graphique PNG par fichier — optionnel

Si *Export des graphiques = .png* est sélectionné, un fichier `.png` (300 dpi) est produit pour chaque fichier d'entrée, superposant :

- signal brut (courant inversé) ;
- signal lissé (Savitzky-Golay) ;
- baseline estimée (asPLS) ;
- signal corrigé (lissé − baseline) ;
- position du pic corrigé (marqueur magenta).

### CSV ou XLSX nettoyé par fichier — optionnel

Si *Export des fichiers traités ≠ Ne pas exporter*, un fichier `.csv` ou `.xlsx` est produit pour chaque fichier d'entrée contenant les colonnes `Potential` / `Current` après nettoyage (lignes à courant nul retirées, tri croissant sur le potentiel).

---

## Chaîne de traitement par fichier

```
┌──────────────────────────┐
│ Fichier *.txt (entrée)   │
└────────────┬─────────────┘
             │ readFile()       séparateur & décimale configurables
             ▼
┌──────────────────────────┐
│ DataFrame brut           │
└────────────┬─────────────┘
             │ processData()    courant=0 supprimé, tri sur potentiel, -I
             ▼
┌──────────────────────────┐
│ Signal nettoyé           │
└────────────┬─────────────┘
             │ smoothSignal()   Savitzky-Golay (w=11, ordre=2)
             ▼
┌──────────────────────────┐
│ Signal lissé             │
└────────────┬─────────────┘
             │ getPeakValue()   pic dans la zone centrale, filtre de pente
             ▼
┌──────────────────────────┐
│ (x_pic, y_pic) provisoires│
└────────────┬─────────────┘
             │ calculateSignalBaseLine()  asPLS avec exclusion ±3% autour du pic
             ▼
┌──────────────────────────┐
│ Baseline estimée         │
└────────────┬─────────────┘
             │ signal_corrigé = signal_lissé - baseline
             ▼
┌──────────────────────────┐
│ Signal corrigé           │
└────────────┬─────────────┘
             │ getPeakValue()   pic final
             ▼
┌──────────────────────────┐
│ (x_pic, y_pic) corrigés  │
└────────────┬─────────────┘
             │ exports optionnels (PNG / CSV / XLSX)
             ▼
┌──────────────────────────┐
│ dict de résultat         │  → agrégé dans le classeur Excel global
└──────────────────────────┘
```

---

## Paramètres algorithmiques

Les constantes ci-dessous sont actuellement **codées en dur** dans le script. Un panneau « Paramètres avancés » est prévu dans la [feuille de route](ROADMAP.md).

| Paramètre                | Valeur     | Rôle                                                                                         |
|--------------------------|------------|----------------------------------------------------------------------------------------------|
| `window_length`          | `11`       | Largeur de la fenêtre Savitzky-Golay (nombre impair de points).                              |
| `polyorder`              | `2`        | Ordre du polynôme ajusté localement par Savitzky-Golay.                                      |
| `marginRatio`            | `0.10`     | Fraction de points exclus aux deux bords lors de la recherche du pic.                        |
| `maxSlope`               | `500`      | Pente absolue maximale tolérée pour un candidat-pic (filtre les fronts montants de bord).    |
| `exclusionWidthRatio`    | `0.03`     | Demi-largeur (fraction de l'amplitude des potentiels) de la zone protégée autour du pic.     |
| `lambdaFactor`           | `1e3`      | Facteur multiplicatif du paramètre de lissage Whittaker : `lam = lambdaFactor · n²`.         |
| `aspls.diff_order`       | `2`        | Ordre de différence dans l'ajustement Whittaker.                                             |
| `aspls.tol`              | `1e-2`     | Tolérance de convergence.                                                                    |
| `aspls.max_iter`         | `25`       | Nombre maximum d'itérations de réajustement des poids.                                       |

---

## Architecture logicielle

Le projet est un package Python à deux fichiers :

| Fichier | Rôle |
|---------|------|
| [`__init__.py`](__init__.py) | Métadonnées du package (`__version__`) — marque le dossier comme package Python et permet `python -m voltapeak_loops`. |
| [`__main__.py`](__main__.py) | Code applicatif complet (toutes les fonctions du pipeline + GUI Tkinter + entry point `main()`). |

Le chaînage des appels est le suivant :

```
main()
 └── launch_gui()                    Tkinter — construit et affiche la fenêtre
      ├── select_folder()            callback du bouton Parcourir
      └── run_analysis()             callback du bouton Lancer l'analyse
           └── iter_results()        générateur — choisit le mode au runtime
                ├── (multi-thread)   Pool(cpu_count()).imap(processFileWrapper, …)
                └── (séquentiel)     boucle for args : processFileWrapper(args)
                     └── processSignalFile()     traitement d'un fichier
                          ├── readFile()
                          ├── processData()
                          ├── smoothSignal()
                          ├── getPeakValue()            (signal lissé)
                          ├── calculateSignalBaseLine()
                          ├── getPeakValue()            (signal corrigé)
                          └── plotSignalAnalysis()      (optionnel)

           └── agrégation pandas → MultiIndex → export .xlsx
```

---

## Performance et multiprocessing

- Par défaut, le script utilise `multiprocessing.Pool(processes=cpu_count())` : **tous les cœurs CPU** sont sollicités.
- `Pool.imap` (et non `Pool.map`) est volontairement choisi : les résultats sont **restitués au fil de l'eau**, ce qui permet de rafraîchir la barre de progression et le journal pendant le traitement plutôt qu'en fin de lot.
- Le backend matplotlib `'Agg'` (non-interactif) est **obligatoire** : les processus enfants du pool n'ont pas accès au thread Tk de la fenêtre principale.

### Mode séquentiel (option *Désactiver*)

L'option *Mode de traitement → Désactiver (traitement séquentiel)* exécute la chaîne complète **dans le processus principal**, fichier après fichier. À utiliser quand :

- vous **déboguez** le pipeline : les `print`, exceptions et messages d'erreur des workers sont parfois absorbés par le pool et difficiles à tracer ; en mode séquentiel ils remontent directement dans la console.
- l'**export PNG matplotlib** se comporte mal sur votre installation (anciens drivers graphiques, conflits de backend). Le mono-processus est plus stable.
- vous tournez sur un environnement **contraint** (machine virtuelle à 1 vCPU, sandbox CI) où le `Pool` apporte un surcoût sans gain réel.
- vous voulez observer les graphiques **dans l'ordre des fichiers** (en parallèle, l'ordre d'arrivée des résultats est non déterministe).

Sinon, laissez le multi-thread activé : le gain est typiquement de l'ordre du nombre de cœurs sur les lots de plusieurs dizaines de fichiers.

### Limitations

- Les gros volumes (plusieurs milliers de fichiers) peuvent saturer la mémoire de processus en raison du cycle matplotlib (`plt.figure` / `plt.close` à chaque appel) — envisager `plt.close('all')` périodique si besoin.
- Le débit utile est souvent limité par les entrées/sorties disque (lecture `.txt`, écriture PNG) plutôt que par le CPU.
- `freeze_support()` est appelé dans `main()` pour permettre un éventuel packaging PyInstaller sous Windows.

---

## Dépannage (FAQ)

**Q. Certains fichiers sont ignorés sans message d'erreur.**
Vérifier que leur nom respecte exactement **l'un** des deux motifs supportés : `*_XX_SWV_CYY_loopZZ.txt` (format `loops`) **ou** `ZZ_<concentration>_XX_SWV_CYY.txt` (format `dosage`). Variante et canal sont **obligatoirement** sur deux chiffres dans les deux cas. Tout nom ne correspondant à aucun des deux est filtré silencieusement par les regex. Cf. [Format des fichiers d'entrée](#format-des-fichiers-dentrée) pour la liste des champs et exemples.

**Q. L'analyse s'arrête avec « le dossier mélange plusieurs formats de fichiers ».**
Un même dossier ne peut pas contenir à la fois des fichiers `*_loopZZ.txt` et des fichiers `ZZ_<conc>_*.txt` : l'export Excel agrégé serait incohérent (mélange `loop0, loop1, 0nm, 250nm…`). Déplacer les deux types dans des dossiers distincts et relancer l'analyse séparément.

**Q. Erreur « UnicodeDecodeError » à la lecture.**
Le script force l'encodage `latin1`. Si vos fichiers sont en UTF-8 avec BOM ou autre encodage exotique, adapter le paramètre `encoding` dans [`readFile`](__main__.py).

**Q. Les colonnes du CSV ne sont pas lues correctement.**
Vérifier dans la GUI le choix du *Séparateur de colonnes* et du *Séparateur décimal*. La plupart des appareils européens produisent de la tabulation avec décimale virgule.

**Q. Le pic détecté est manifestement faux.**
Trois causes possibles :
1. Le signal est trop bruité → augmenter `window_length` dans `smoothSignal`.
2. Le pic se trouve dans les 10 % de bord du scan → réduire `marginRatio` dans `getPeakValue`.
3. La baseline « avale » le pic → élargir `exclusionWidthRatio` dans `calculateSignalBaseLine`.

**Q. Les graphiques PNG ne sont pas générés.**
Vérifier que l'option *Export des graphiques* est bien positionnée sur `.png` dans la GUI (elle est par défaut sur *Ne pas exporter*).

**Q. Le bouton « Ouvrir le dossier de résultats » reste grisé.**
Il s'active uniquement après un traitement terminé avec succès (au moins un fichier valide traité).

**Q. L'application fige pendant le traitement d'un gros dossier.**
La fenêtre Tkinter est rafraîchie après chaque fichier traité : si l'un de vos fichiers est très volumineux, attendre quelques secondes. Un bouton *Annuler* est prévu dans la [feuille de route](ROADMAP.md).

**Q. Pylance souligne en rouge les imports (`matplotlib`, `numpy`, `pandas`, `pybaselines`, `scipy`) avec l'erreur `reportMissingImports`, alors que le script s'exécute correctement.**
Pylance (ou `pyright` CLI) n'a pas trouvé l'interpréteur Python contenant les dépendances. Deux causes classiques :
1. Le `.venv` du projet n'existe pas → le créer et y installer les dépendances (cf. [Installation](#installation)). `pyrightconfig.json` déclare déjà `venvPath = "."` / `venv = ".venv"` : une fois le venv en place, Pyright le détecte automatiquement.
2. Sous Windows, VS Code utilise par défaut l'alias du Microsoft Store comme `python.exe`, qui ne résout aucun import → ouvrir la palette de commandes (`Ctrl+Shift+P`), choisir *Python: Select Interpreter* et sélectionner `.venv/Scripts/python.exe` (ou à défaut un Python complet installé depuis [python.org](https://python.org)).

---

## Licence et auteur

- **Auteur** : GROUPE TRACE.
- **Licence** : à préciser — usage interne par défaut.

Pour toute contribution ou question, se reporter au canal interne GROUPE TRACE.
