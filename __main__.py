"""
voltapeak_loops
===============

Outil d'analyse en masse de fichiers de voltammétrie à vagues carrées
(SWV, Square Wave Voltammetry) produits par des appareils électrochimiques.

Pour chaque fichier ``.txt`` trouvé dans un dossier, le script :
    1. lit les deux colonnes (Potentiel, Courant) ;
    2. nettoie et trie les données, inverse le signe du courant ;
    3. lisse le signal par filtre Savitzky-Golay ;
    4. détecte le pic principal ;
    5. corrige la ligne de base (baseline) par la méthode asPLS Whittaker ;
    6. extrait le pic corrigé (tension, courant) ;
    7. exporte optionnellement un graphique PNG, un CSV ou un XLSX par fichier.

Les résultats de tous les fichiers sont agrégés dans un unique classeur Excel
hiérarchique (MultiIndex : Canal / Variante / Mesure), une ligne par itération.

Deux formats de noms de fichiers sont supportés (détection automatique) :

* **Format "loops"** : ``*_XX_SWV_CYY_loopZZ.txt``
    - ``XX`` = variante sur 2 chiffres (ex. fréquence)
    - ``CYY`` = identifiant de canal (ex. C09)
    - ``loopZZ`` = index d'itération (suffixe)

* **Format "dosage"** : ``ZZ_<concentration>_XX_SWV_CYY.txt``
    - ``ZZ`` = ordre dans la série de dosage (préfixe, sert au tri)
    - ``<concentration>`` = libellé de concentration (ex. ``0nm``, ``250nm``)
    - ``XX`` = variante sur 2 chiffres (réplica)
    - ``CYY`` = identifiant de canal

Pour le format "dosage", l'index de ligne du tableau Excel final affiche la
concentration uniquement, mais le tri est effectué selon ``ZZ`` pour
préserver l'ordre expérimental.

Point d'entrée
--------------
Lancer ``python -m voltapeak_loops`` (depuis le dossier parent du package)
ouvre une interface graphique Tkinter. Le traitement s'effectue par défaut
en parallèle sur tous les cœurs CPU disponibles via
``multiprocessing.Pool`` ; un mode séquentiel est sélectionnable dans la
GUI (utile pour le débogage).

Dépendances principales
-----------------------
numpy, pandas, scipy, matplotlib, pybaselines, tkinter (stdlib).
"""

import glob
import os
import platform
import re
import subprocess
import time
from multiprocessing import Pool, cpu_count, freeze_support
from tkinter import Button, Frame, IntVar, Label, Radiobutton, StringVar, Text, Tk, filedialog, messagebox, ttk

import matplotlib
from numpy.typing import NDArray

# Backend non-interactif : OBLIGATOIRE.
#   * En multi-process : les workers n'ont pas accès au thread Tk principal,
#     un backend GUI provoquerait un crash ou un fallback coûteux.
#   * En mono-process (séquentiel) : un backend GUI (TkAgg par défaut sous
#     Windows) accumule des handles GDI à chaque plt.figure() — même avec
#     plt.close() — et finit par lever « Fail to allocate bitmap » après
#     quelques dizaines de figures. 'Agg' n'utilise pas de handles GDI.
# Doit impérativement être appelé AVANT l'import de matplotlib.pyplot.
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402  (matplotlib.use doit précéder)
import numpy as np # type: ignore
import pandas as pd
from pybaselines.whittaker import aspls # type: ignore
from scipy.signal import savgol_filter # type: ignore


# Expressions régulières pour les deux formats supportés.
# Le format "loops" est testé en premier car il est plus restrictif (présence
# explicite du suffixe `_loopZZ`). Le format "dosage" sert ensuite de fallback.
RE_LOOPS = re.compile(r".*?_([0-9]{2})_SWV_(C[0-9]{2})_loop([0-9]+)\.txt$")
RE_DOSAGE = re.compile(r"^([0-9]+)_([^_]+)_([0-9]{2})_SWV_(C[0-9]{2})\.txt$")


def open_folder(path):
    """Ouvre un dossier dans l'explorateur de fichiers natif du système d'exploitation.

    Supporte Windows (``os.startfile``), macOS (``open``) et Linux (``xdg-open``).

    Args:
        path (str): Chemin absolu du dossier à ouvrir.
    """
    if platform.system() == "Windows":
        os.startfile(path)
    elif platform.system() == "Darwin":  # macOS
        subprocess.call(["open", path])
    else:  # Linux
        subprocess.call(["xdg-open", path])

def readFile(filePath, sep, decimal) -> (pd.DataFrame|None):
    """Charge un fichier SWV texte et le convertit en DataFrame pandas.

    La première ligne du fichier (en-tête ou métadonnées de l'appareil) est
    ignorée. Seules les deux premières colonnes sont conservées : elles sont
    renommées ``Potential`` et ``Current``. L'encodage ``latin1`` est imposé
    pour tolérer les caractères accentués produits par certains appareils.

    Args:
        filePath (str): Chemin du fichier ``.txt`` à lire.
        sep (str): Séparateur de colonnes (``"\\t"``, ``","``, ``";"``, ``" "``).
        decimal (str): Séparateur décimal (``"."`` ou ``","``).

    Returns:
        pandas.DataFrame | None: DataFrame à deux colonnes
        ``Potential`` et ``Current``.
    """
    with open(filePath, encoding="latin1") as fileStream:
        dataFrame = pd.read_csv(fileStream, sep=sep, skiprows=1, usecols=[0, 1], names=["Potential", "Current"], decimal=decimal)
    return dataFrame

def processData(dataFrame) -> tuple:
    """Nettoie et prépare les données brutes pour l'analyse.

    Trois opérations sont effectuées :
        * suppression des lignes dont le courant est exactement nul
          (points parasites ou d'amorçage de la mesure) ;
        * tri croissant sur la colonne ``Potential`` pour garantir un axe X
          monotone requis par le lissage et la détection de pic ;
        * inversion du signe du courant (convention métier : les pics
          d'intérêt sont orientés vers le haut dans le signal traité).

    Args:
        dataFrame (pandas.DataFrame): DataFrame retourné par :func:`readFile`.

    Returns:
        tuple: ``(potentialValues, signalValues, cleaned_df)`` où
        ``potentialValues`` et ``signalValues`` sont des ``numpy.ndarray``
        et ``cleaned_df`` est le DataFrame nettoyé/trié.
    """
    dataFrame = dataFrame[dataFrame["Current"] != 0].sort_values("Potential").reset_index(drop=True)
    potentialValues = dataFrame["Potential"].values
    signalValues = -dataFrame["Current"].values  # Inversion du courant
    return potentialValues, signalValues, dataFrame

def smoothSignal(signalValues: NDArray[np.float64]) -> NDArray[np.float64]:
    """Applique un lissage Savitzky-Golay au signal.

    Les paramètres (fenêtre de 11 points, polynôme d'ordre 2) constituent un
    compromis éprouvé pour les signaux SWV : ils atténuent le bruit haute
    fréquence tout en préservant la forme et l'amplitude du pic.

    Args:
        signalValues (numpy.ndarray): Tableau 1D du signal (courant inversé).

    Returns:
        numpy.ndarray: Signal lissé, de même dimension que l'entrée.
    """
    return np.asarray(savgol_filter(signalValues, window_length=11, polyorder=2))

def getPeakValue(signalValues, potentialValues, marginRatio=0.10, maxSlope=None) -> tuple:
    """Localise le pic principal du signal dans la région centrale.

    Une marge (par défaut 10 % de part et d'autre) est exclue pour éviter
    qu'un maximum situé en bord de scan ne soit retenu par erreur. Si
    ``maxSlope`` est fourni, les points dont la pente locale (``dy/dx``)
    dépasse ce seuil sont ignorés : on préfère un sommet à faible pente,
    signature d'un vrai maximum local, plutôt qu'un point sur un front
    montant.

    Args:
        signalValues (numpy.ndarray): Signal dans lequel chercher le pic.
        potentialValues (numpy.ndarray): Abscisses (potentiels) associées.
        marginRatio (float): Fraction de points exclus à chaque bord.
        maxSlope (float | None): Pente absolue maximale tolérée pour qu'un
            point soit candidat au pic. ``None`` désactive ce filtre.

    Returns:
        tuple[float, float]: ``(xPeak, yPeak)`` — abscisse (potentiel, V)
        et ordonnée (courant, A) du pic détecté.
    """
    n = len(signalValues)
    margin = int(n * marginRatio)
    searchRegion = signalValues[margin:-margin]
    potentialsRegion = potentialValues[margin:-margin]

    if maxSlope is not None:
        # Sélection des points dont la pente absolue reste inférieure au
        # seuil : on écarte ainsi les points situés sur un front raide
        # (bord de scan) qui ne sont pas de vrais maxima locaux.
        slopes = np.gradient(searchRegion, potentialsRegion)
        validIndices = np.where(np.abs(slopes) < maxSlope)[0]
        if len(validIndices) == 0:
            return potentialValues[margin], signalValues[margin]
        bestIndex = validIndices[np.argmax(searchRegion[validIndices])]
        index = bestIndex + margin
    else:
        indexInRegion = np.argmax(searchRegion)
        index = indexInRegion + margin

    return potentialValues[index], signalValues[index]

def calculateSignalBaseLine(signalValues, potentialValues, xPeakVoltage, exclusionWidthRatio=0.03, lambdaFactor=1e3) -> tuple[np.ndarray, tuple[float, float]]:
    """Estime la ligne de base (baseline) par méthode asPLS Whittaker.

    Un vecteur de poids est construit :
        * 1.0 partout par défaut ;
        * 0.001 dans une fenêtre centrée sur le pic détecté et de largeur
          ``±exclusionWidthRatio · (V_max − V_min)``.

    La faible pondération dans cette zone empêche la baseline de « suivre »
    le pic sans pour autant l'annuler totalement, afin de préserver la
    continuité numérique de l'ajustement.

    Args:
        signalValues (numpy.ndarray): Signal lissé à corriger.
        potentialValues (numpy.ndarray): Potentiels associés.
        xPeakVoltage (float): Potentiel du pic (en V) à protéger.
        exclusionWidthRatio (float): Demi-largeur de la zone exclue
            exprimée en fraction de l'amplitude totale des potentiels.
        lambdaFactor (float): Facteur multiplicatif du paramètre de
            lissage Whittaker (``lam = lambdaFactor · n²``).

    Returns:
        tuple: ``(baselineValues, (exclusion_min, exclusion_max))`` — le
        vecteur baseline estimé et les bornes en potentiel de la zone
        pondérée.
    """
    n = len(signalValues)
    # Normalisation Whittaker : le paramètre de lissage doit croître avec
    # la taille de la série pour un effet de lissage comparable.
    lam = lambdaFactor * (n ** 2)
    exclusionWidth = exclusionWidthRatio * (potentialValues[-1] - potentialValues[0])
    weights = np.ones_like(potentialValues)
    exclusion_min = xPeakVoltage - exclusionWidth
    exclusion_max = xPeakVoltage + exclusionWidth
    # Poids très faible (et non zéro) autour du pic : conserve la continuité
    # numérique de l'ajustement tout en empêchant la baseline d'épouser le pic.
    weights[(potentialValues > exclusion_min) & (potentialValues < exclusion_max)] = 0.001
    baselineValues, _ = aspls(signalValues, lam=lam, diff_order=2, weights=weights, tol=1e-2, max_iter=25)  # pyright: ignore[reportGeneralTypeIssues]
    return baselineValues, (exclusion_min, exclusion_max)

def plotSignalAnalysis(potentialValues, signalValues, signalSmoothed, baseline, signalCorrected, xCorrectedVoltage, yCorrectedCurrent, fileName, outputFolder) -> None:
    """Génère et sauvegarde un graphique synthétique de l'analyse.

    Le PNG produit (300 dpi) superpose le signal brut, le signal lissé, la
    baseline estimée, le signal corrigé et la position du pic détecté.

    Args:
        potentialValues (numpy.ndarray): Axe des potentiels (V).
        signalValues (numpy.ndarray): Signal brut (courant inversé).
        signalSmoothed (numpy.ndarray): Signal après lissage Savitzky-Golay.
        baseline (numpy.ndarray): Ligne de base estimée par asPLS.
        signalCorrected (numpy.ndarray): Signal lissé moins baseline.
        xCorrectedVoltage (float): Potentiel du pic corrigé (V).
        yCorrectedCurrent (float): Courant du pic corrigé (A).
        fileName (str): Nom du fichier d'entrée (sert à nommer le PNG).
        outputFolder (str): Dossier de destination du PNG.
    """
    plt.figure(figsize=(10, 6))
    plt.plot(potentialValues, signalValues, label="Signal brut", alpha=0.5)
    plt.plot(potentialValues, signalSmoothed, label="Signal lissé", linewidth=2)
    plt.plot(potentialValues, baseline, label="Baseline estimée (asPLS)", linestyle='--')
    plt.plot(potentialValues, signalCorrected, label="Signal corrigé", linewidth=3)
    plt.plot(xCorrectedVoltage, yCorrectedCurrent, 'mo', label=f"Pic corrigé à {xCorrectedVoltage:.3f} V ({yCorrectedCurrent*1e3:.3f} mA)")
    plt.axvline(xCorrectedVoltage, color='magenta', linestyle=':', linewidth=1)
    plt.xlabel("Potentiel (V)")
    plt.ylabel("Courant (A)")
    plt.title(f"Correction de baseline : {fileName}")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    outputPath = os.path.join(outputFolder, fileName.replace(".txt", ".png"))
    plt.savefig(outputPath, dpi=300, bbox_inches='tight')
    plt.close()

def parseFileName(fileName) -> dict | None:
    """Extrait les métadonnées d'un nom de fichier SWV.

    Tente d'abord le format "loops" (suffixe ``_loopZZ``), puis le format
    "dosage" (préfixe ``ZZ_<concentration>_``).

    Args:
        fileName (str): Nom du fichier (basename, sans chemin).

    Returns:
        dict | None: Dictionnaire contenant :
            * ``'format'`` : ``'loops'`` ou ``'dosage'``
            * ``'iteration_key'`` : clé numérique pour le tri (int)
            * ``'iteration_label'`` : libellé affiché en index Excel (str)
            * ``'variante'`` : variante sur 2 chiffres (str)
            * ``'canal'`` : identifiant canal (str, ex. ``'C09'``)

        Retourne ``None`` si aucun format ne correspond.
    """
    # Format "loops" : *_XX_SWV_CYY_loopZZ.txt
    m = RE_LOOPS.match(fileName)
    if m:
        variante, canal, loop = m.group(1), m.group(2), m.group(3)
        return {
            'format': 'loops',
            'iteration_key': int(loop),
            'iteration_label': f"loop{loop}",
            'variante': variante,
            'canal': canal,
        }

    # Format "dosage" : ZZ_<concentration>_XX_SWV_CYY.txt
    m = RE_DOSAGE.match(fileName)
    if m:
        ordre, concentration, variante, canal = m.group(1), m.group(2), m.group(3), m.group(4)
        return {
            'format': 'dosage',
            'iteration_key': int(ordre),
            'iteration_label': concentration,  # affichage : concentration uniquement
            'variante': variante,
            'canal': canal,
        }

    return None

def processFileWrapper(args):
    """Adaptateur pour ``multiprocessing.Pool.imap``.

    ``Pool.imap`` ne prend qu'un argument par appel : on emballe donc tous
    les paramètres de :func:`processSignalFile` dans un tuple puis on les
    redéploie ici via ``*args``.

    Args:
        args (tuple): Arguments positionnels de :func:`processSignalFile`.

    Returns:
        dict | None: Résultat renvoyé par :func:`processSignalFile`.
    """
    return processSignalFile(*args)

def processSignalFile(filePath, outputFolder, sep, decimal, export_processed, export_graph) -> dict | None:
    """Traite un unique fichier SWV de bout en bout (fonction métier centrale).

    Enchaîne : lecture → extraction des métadonnées par regex (deux formats
    supportés, voir :func:`parseFileName`) → nettoyage → lissage
    Savitzky-Golay → détection de pic → correction de baseline asPLS →
    extraction du pic corrigé → exports optionnels.

    Args:
        filePath (str): Chemin absolu du fichier ``.txt`` à traiter.
        outputFolder (str): Dossier où écrire les exports.
        sep (str): Séparateur de colonnes.
        decimal (str): Séparateur décimal.
        export_processed (int): 0 = aucun export, 1 = CSV, 2 = Excel.
        export_graph (int): 0 = aucun graphique, 1 = PNG.

    Returns:
        dict | None: Dictionnaire contenant :
            * ``'iteration_key'`` → clé numérique pour le tri (int),
            * ``'iteration_label'`` → libellé d'itération affiché (str),
            * ``"{canal} - {variante} - Tension (V)"`` → tension du pic,
            * ``"{canal} - {variante} - Courant (A)"`` → courant du pic.

        Retourne ``None`` si le nom ne correspond à aucun format reconnu.
        En cas d'exception, retourne ``{"error": "..."}`` pour affichage.
    """
    try:
        fileName = os.path.basename(filePath)
        dataFrame = readFile(filePath, sep=sep, decimal=decimal)
        if dataFrame is None:
            return None

        meta = parseFileName(fileName)
        if meta is None:
            return None

        variante = meta['variante']
        canal = meta['canal']

        potentialValues, signalValues, cleaned_df = processData(dataFrame)
        signalSmoothed = smoothSignal(signalValues)
        xPeakVoltage, _ = getPeakValue(signalSmoothed, potentialValues, marginRatio=0.10, maxSlope=500)
        baseline, _ = calculateSignalBaseLine(signalSmoothed, potentialValues, xPeakVoltage, exclusionWidthRatio=0.03, lambdaFactor=1e3)
        signalCorrected = signalSmoothed - baseline
        xCorrectedVoltage, yCorrectedCurrent = getPeakValue(signalCorrected, potentialValues, marginRatio=0.10, maxSlope=500)

        if export_graph == 1:
            plotSignalAnalysis(potentialValues, signalValues, signalSmoothed, baseline, signalCorrected, xCorrectedVoltage, yCorrectedCurrent, fileName, outputFolder)

        if export_processed == 1:
            cleaned_df.to_csv(os.path.join(outputFolder, fileName.replace(".txt", ".csv")), index=False)
        elif export_processed == 2:
            cleaned_df.to_excel(os.path.join(outputFolder, fileName.replace(".txt", ".xlsx")), index=False)

        return {
            'iteration_key': meta['iteration_key'],
            'iteration_label': meta['iteration_label'],
            f"{canal} - {variante} - Tension (V)": xCorrectedVoltage,
            f"{canal} - {variante} - Courant (A)": yCorrectedCurrent,
        }

    except Exception as exception:
        print(f"Erreur lors de la lecture de {filePath} : {exception}")
        return {"error": f"Erreur dans le fichier {filePath} : {str(exception)}"}

def main():
    """Point d'entrée du programme.

    ``freeze_support()`` est requis pour permettre un éventuel packaging
    PyInstaller sous Windows : il évite la ré-exécution récursive du
    point d'entrée dans les processus enfants du ``multiprocessing.Pool``.
    """
    freeze_support()
    launch_gui()

def launch_gui():
    """Construit et lance l'interface graphique Tkinter.

    L'interface offre :
        * la sélection du dossier d'entrée ;
        * le choix du séparateur de colonnes et du séparateur décimal ;
        * les options d'export des fichiers traités (CSV / Excel) ;
        * les options d'export des graphiques (PNG) ;
        * une barre de progression et un journal en temps réel ;
        * le lancement de l'analyse et l'ouverture du dossier de résultats.

    Deux callbacks sont imbriqués (closures sur les variables Tkinter) :

        * ``select_folder`` : ouvre un dialogue de sélection de dossier et
          mémorise le dernier chemin utilisé pour la prochaine ouverture ;
        * ``run_analysis`` : valide les paramètres, prépare le dossier de
          sortie, orchestre le ``multiprocessing.Pool`` et agrège les
          résultats dans un classeur Excel hiérarchique.
    """

    last_dir = os.path.expanduser('~')

    def select_folder():
        """Ouvre un dialogue de sélection de dossier et mémorise le choix."""
        nonlocal last_dir
        path = filedialog.askdirectory(
            initialdir=last_dir,
            title="Sélectionnez le dossier contenant les fichiers .txt"
        )
        if path:
            folder_path.set(path)
            last_dir = path

    def run_analysis():
        """Orchestre l'analyse de tous les fichiers du dossier sélectionné."""

        progress_bar["value"] = 0
        progress_bar["maximum"] = 1  # Optionnel, ça force l'affichage à vide
        root.update_idletasks()

        export_processed = export_processed_var.get()
        export_graph = export_graph_var.get()

        log_box.config(state="normal")
        log_box.delete("1.0", "end")
        log_box.config(state="disabled")
        inputFolder = folder_path.get()
        if not inputFolder or not os.path.isdir(inputFolder):
            messagebox.showerror("Erreur", "Veuillez sélectionner un dossier valide.")
            return

        sep_label = sep_var.get()
        sep_map = {"Tabulation": "\t", "Virgule": ",", "Point-virgule": ";", "Espace": " "}
        sep = sep_map.get(sep_label, "\t")
        decimal_label = decimal_var.get()
        decimal_map = {"Point": ".", "Virgule": ","}
        decimal = decimal_map.get(decimal_label, ".")

        folderName = os.path.basename(os.path.normpath(inputFolder))
        # Convention : le dossier de sortie est créé à côté du dossier
        # source sous la forme "<nom> (results)".
        outputFolder = os.path.join(os.path.dirname(inputFolder), folderName + " (results)")
        os.makedirs(outputFolder, exist_ok=True)

        # Nettoyage du dossier de sortie
        log_box.config(state="normal")
        log_box.insert("end", "Nettoyage du dossier de sortie...\n")
        log_box.config(state="disabled")
        for file in glob.glob(os.path.join(outputFolder, "*")):
            if file.endswith((".png", ".csv", ".xlsx")):
                os.remove(file)

        filePaths = sorted(glob.glob(os.path.join(inputFolder, "*.txt")))
        fileProcessingArgs = [(filePath, outputFolder, sep, decimal, export_processed, export_graph) for filePath in filePaths]

        results = []
        start_time = time.time()

        progress_bar["maximum"] = len(filePaths)
        progress_bar["value"] = 0

        def iter_results():
            """Itère sur les résultats selon le mode sélectionné (parallèle ou séquentiel).

            Le ``with Pool(...)`` est encapsulé ici afin que son scope se ferme
            proprement quand le générateur est épuisé, sans dupliquer le corps
            de boucle appelant (log_box, progress_bar, gestion d'erreur).
            """
            if multi_thread_option.get() == 1:
                # Mode parallèle : un processus par cœur ; imap permet d'itérer les
                # résultats au fur et à mesure pour rafraîchir logs + barre de progression.
                with Pool(processes=cpu_count()) as pool:
                    yield from pool.imap(processFileWrapper, fileProcessingArgs)
            else:
                # Mode séquentiel : traitement fichier par fichier dans le processus principal.
                for args in fileProcessingArgs:
                    yield processFileWrapper(args)

        for i, (filePath, result) in enumerate(zip(filePaths, iter_results())):
            log_box.config(state="normal")
            if result:
                if "error" in result:
                    log_box.insert("end", f"Erreur : {result['error']}\n", ("error",))
                else:
                    results.append(result)
                    log_box.insert("end", f"Traitement : {os.path.basename(filePath)}\n")
            else:
                log_box.insert("end", f"Fichier ignoré ou invalide : {os.path.basename(filePath)}\n")

            log_box.update_idletasks()
            log_box.see("end")
            log_box.tag_config("error", foreground="red")
            log_box.config(state="disabled")
            progress_bar["value"] = i + 1
            root.update_idletasks()

        # Organisation finale : table pivotée par itération et colonnes multi-analyses
        if results:
            df = pd.DataFrame(results)

            # Regroupement par itération : chaque combinaison (canal, variante)
            # devient une colonne distincte ; l'itération devient l'index de
            # ligne du tableau final.
            #
            # On agrège sur 'iteration_label' (le libellé affiché : "loop3" ou
            # "0nm" selon le format), mais on conserve 'iteration_key' (le
            # numéro brut) pour effectuer le tri numérique correct.
            #
            # `first()` est utilisé car chaque (iteration, canal, variante)
            # n'apparaît qu'une fois ; c'est juste un moyen d'aplatir la
            # structure en un tableau pivot.
            df_grouped = df.groupby('iteration_label', sort=False).first()

            # Tri par la clé numérique de l'itération (loop0, loop1... ou 1, 2, 3...)
            df_grouped = df_grouped.sort_values('iteration_key')

            # La colonne 'iteration_key' n'a plus besoin d'apparaître dans
            # le résultat final : elle a servi uniquement au tri.
            df_grouped = df_grouped.drop(columns=['iteration_key'])

            # Tri des colonnes (canal, variante, Tension avant Courant)
            def key_col(col):
                m = re.match(r'C(\d{2}) - (\d{2}) - (Tension \(V\)|Courant \(A\))', col)
                if m:
                    canal, variante, mesure = m.groups()
                    return (int(canal), int(variante), 0 if "Tension" in mesure else 1)
                return (999, 999, 999)

            mesure_cols_triees = sorted(list(df_grouped.columns), key=key_col)
            df_grouped = df_grouped[mesure_cols_triees]

            # Construction d'un en-tête Excel hiérarchique à trois niveaux :
            #   Canal (C00..C99) > Variante (fréquence ou réplica) > Mesure (Tension/Courant).
            # Rend le classeur de sortie bien plus lisible qu'une colonne plate.
            new_cols = []
            for col in df_grouped.columns:
                m = re.match(r'(C\d{2}) - (\d{2}) - (Tension \(V\)|Courant \(A\))', col)
                if m:
                    canal, variante, mesure = m.groups()
                    new_cols.append((canal, variante, mesure))
                else:
                    new_cols.append(("", "", col))
            df_grouped.columns = pd.MultiIndex.from_tuples(new_cols, names=["Canal", "Variante", "Mesure"])

            excel_path = os.path.join(outputFolder, folderName + ".xlsx")
            df_grouped.to_excel(excel_path, index=True, index_label="Itération")

            log_box.config(state="normal")
            duration = time.time() - start_time
            summary = f"\nTraitement terminé avec succès.\nFichiers traités : {len(results)} / {len(filePaths)}\nTemps écoulé : {duration:.2f} secondes.\n\n"
            log_box.insert("end", summary)
            log_box.update_idletasks()
            log_box.see("end")
            log_box.config(state="disabled")
            messagebox.showinfo("Succès", "Traitement terminé avec succès.")
            result_button.config(state="normal")

    root = Tk()
    root.resizable(True, True)

    root.title("Analyse de fichiers SWV")
    root.geometry("700x400")
    root.minsize(600, 400)

    folder_path = StringVar()
    sep_options = ["Tabulation", "Virgule", "Point-virgule", "Espace"]
    decimal_options = ["Point", "Virgule"]

    sep_var = StringVar(value="Tabulation")
    decimal_var = StringVar(value="Point")
    export_processed_var = IntVar(value=0)
    export_graph_var = IntVar(value=0)
    multi_thread_option = IntVar(value=1)  # 1 = activé par défaut (comportement historique).

    main_frame = Frame(root, padx=10, pady=10)
    main_frame.grid(row=0, column=0, sticky="nsew")
    main_frame.grid_columnconfigure(1, weight=1)
    root.grid_rowconfigure(0, weight=1)
    root.grid_columnconfigure(0, weight=1)

    Label(main_frame, text="Dossier d'entrée :").grid(row=0, column=0, sticky="w")
    Label(main_frame, textvariable=folder_path, relief="sunken", anchor="w", width=50).grid(row=0, column=1, padx=5, sticky="ew")
    Button(main_frame, text="Parcourir", command=select_folder).grid(row=0, column=2, padx=5)

    settings_frame = ttk.LabelFrame(main_frame, text="Paramètres de lecture")
    settings_frame.grid(row=1, column=0, columnspan=3, pady=(10, 5), sticky="ew")

    Label(settings_frame, text="Séparateur de colonnes :").grid(row=0, column=0, sticky="w")
    sep_radio_frame = Frame(settings_frame)
    sep_radio_frame.grid(row=0, column=1, columnspan=4, sticky="w")
    for i, txt in enumerate(sep_options):
        ttk.Radiobutton(sep_radio_frame, text=txt, variable=sep_var, value=txt).grid(row=0, column=i, sticky="w", padx=(0, 10))

    Label(settings_frame, text="Séparateur décimal :").grid(row=1, column=0, sticky="w")
    dec_radio_frame = Frame(settings_frame)
    dec_radio_frame.grid(row=1, column=1, columnspan=4, sticky="w")
    for i, txt in enumerate(decimal_options):
        ttk.Radiobutton(dec_radio_frame, text=txt, variable=decimal_var, value=txt).grid(row=0, column=i, sticky="w", padx=(0, 10))

    Label(settings_frame, text="Export des fichiers traités :").grid(row=2, column=0, sticky="w", pady=(5, 0))
    export_radio_frame = Frame(settings_frame)
    export_radio_frame.grid(row=2, column=1, columnspan=4, sticky="w")
    Radiobutton(export_radio_frame, text="Ne pas exporter", variable=export_processed_var, value=0).pack(side="left", padx=(0, 10))
    Radiobutton(export_radio_frame, text="Exporter au format .CSV", variable=export_processed_var, value=1).pack(side="left", padx=(0, 10))
    Radiobutton(export_radio_frame, text="Exporter au format Excel", variable=export_processed_var, value=2).pack(side="left")

    Label(settings_frame, text="Export des graphiques :").grid(row=3, column=0, sticky="w", pady=(5, 0))
    export_radio_frame = Frame(settings_frame)
    export_radio_frame.grid(row=3, column=1, columnspan=4, sticky="w")
    Radiobutton(export_radio_frame, text="Ne pas exporter", variable=export_graph_var, value=0).pack(side="left", padx=(0, 10))
    Radiobutton(export_radio_frame, text="Exporter au format .png", variable=export_graph_var, value=1).pack(side="left", padx=(0, 10))

    Label(settings_frame, text="Mode de traitement :").grid(row=4, column=0, sticky="w", pady=(5, 0))
    multi_thread_radio_frame = Frame(settings_frame)
    multi_thread_radio_frame.grid(row=4, column=1, columnspan=4, sticky="w")
    Radiobutton(multi_thread_radio_frame, text="Activer le multi-thread (un processus par cœur)", variable=multi_thread_option, value=1).pack(side="left", padx=(0, 10))
    Radiobutton(multi_thread_radio_frame, text="Désactiver (traitement séquentiel)", variable=multi_thread_option, value=0).pack(side="left")

    progress_frame = ttk.LabelFrame(main_frame, text="Progression du traitement")
    progress_frame.grid(row=2, column=0, columnspan=3, sticky="ew", padx=2, pady=(5, 5))
    progress_bar = ttk.Progressbar(progress_frame, orient="horizontal", mode="determinate")
    progress_bar.pack(fill="x", padx=5, pady=5)

    log_frame = ttk.LabelFrame(main_frame, text="Journal de traitement")
    log_frame.grid(row=3, column=0, columnspan=3, sticky="nsew", padx=2, pady=(0, 5))
    main_frame.grid_rowconfigure(3, weight=1)
    log_box = Text(log_frame, relief="sunken", wrap="word", height=10, bg="white")
    log_box.pack(expand=True, fill="both", padx=5, pady=5)
    log_box.config(state="disabled")

    action_frame = Frame(main_frame)
    action_frame.grid(row=4, column=0, columnspan=3, sticky="ew")
    Button(action_frame, text="Lancer l'analyse", command=run_analysis).pack(side="right", padx=5, pady=5)
    result_button = Button(action_frame, text="Ouvrir le dossier de résultats", state="disabled", command=lambda: open_folder(folder_path.get() + " (results)"))
    result_button.pack(side="right", padx=5, pady=5)

    root.mainloop()

if __name__ == '__main__':
    main()
