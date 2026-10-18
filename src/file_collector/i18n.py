"""Small built-in catalog; English is the fallback language."""

import os

LANGUAGES = {"en": "English", "it": "Italiano", "fr": "Français", "de": "Deutsch", "es": "Español"}

# English key followed by Italian, French, German, Spanish.
CATALOG = {
    "Gather scattered files into one folder": ("Riunisci i file sparsi in una sola cartella", "Rassemblez vos fichiers dans un seul dossier", "Verstreute Dateien in einem Ordner sammeln", "Reúne archivos dispersos en una carpeta"),
    "Source folders": ("Cartelle di origine", "Dossiers sources", "Quellordner", "Carpetas de origen"),
    "Add folders": ("Aggiungi cartelle", "Ajouter des dossiers", "Ordner hinzufügen", "Añadir carpetas"),
    "Remove": ("Rimuovi", "Retirer", "Entfernen", "Quitar"),
    "File types": ("Tipi di file", "Types de fichiers", "Dateitypen", "Tipos de archivo"),
    "All files": ("Tutti i file", "Tous les fichiers", "Alle Dateien", "Todos los archivos"),
    "Comics": ("Fumetti", "Bandes dessinées", "Comics", "Cómics"),
    "Documents": ("Documenti", "Documents", "Dokumente", "Documentos"),
    "Images": ("Immagini", "Images", "Bilder", "Imágenes"),
    "Audio": ("Audio", "Audio", "Audio", "Audio"),
    "Custom": ("Personalizzato", "Personnalisé", "Benutzerdefiniert", "Personalizado"),
    "Extensions, separated by commas": ("Estensioni separate da virgole", "Extensions séparées par des virgules", "Endungen mit Kommas trennen", "Extensiones separadas por comas"),
    "Name contains": ("Il nome contiene", "Le nom contient", "Name enthält", "El nombre contiene"),
    "Optional text": ("Testo facoltativo", "Texte facultatif", "Optionaler Text", "Texto opcional"),
    "Advanced filters": ("Filtri avanzati", "Filtres avancés", "Erweiterte Filter", "Filtros avanzados"),
    "Minimum size (MiB)": ("Dimensione minima (MiB)", "Taille minimale (MiB)", "Mindestgröße (MiB)", "Tamaño mínimo (MiB)"),
    "Maximum size (MiB)": ("Dimensione massima (MiB)", "Taille maximale (MiB)", "Höchstgröße (MiB)", "Tamaño máximo (MiB)"),
    "Modified from (YYYY-MM-DD)": ("Modificato dal (AAAA-MM-GG)", "Modifié depuis (AAAA-MM-JJ)", "Geändert ab (JJJJ-MM-TT)", "Modificado desde (AAAA-MM-DD)"),
    "Modified through (YYYY-MM-DD)": ("Modificato fino al (AAAA-MM-GG)", "Modifié jusqu’au (AAAA-MM-JJ)", "Geändert bis (JJJJ-MM-TT)", "Modificado hasta (AAAA-MM-DD)"),
    "Depth (0 = source only)": ("Profondità (0 = solo origine)", "Profondeur (0 = source seule)", "Tiefe (0 = nur Quelle)", "Profundidad (0 = solo origen)"),
    "Unlimited": ("Illimitata", "Illimitée", "Unbegrenzt", "Ilimitada"),
    "Excluded folder names": ("Nomi delle cartelle escluse", "Noms des dossiers exclus", "Ausgeschlossene Ordnernamen", "Nombres de carpetas excluidas"),
    "Include hidden files": ("Includi file nascosti", "Inclure les fichiers cachés", "Versteckte Dateien einbeziehen", "Incluir archivos ocultos"),
    "Search files": ("Cerca file", "Rechercher", "Dateien suchen", "Buscar archivos"),
    "Results": ("Risultati", "Résultats", "Ergebnisse", "Resultados"),
    "Select all": ("Seleziona tutti", "Tout sélectionner", "Alle auswählen", "Seleccionar todos"),
    "Select none": ("Deseleziona tutti", "Tout désélectionner", "Auswahl aufheben", "Deseleccionar todos"),
    "Open source folder": ("Apri cartella di origine", "Ouvrir le dossier source", "Quellordner öffnen", "Abrir carpeta de origen"),
    "File": ("File", "Fichier", "Datei", "Archivo"),
    "Source folder": ("Cartella di origine", "Dossier source", "Quellordner", "Carpeta de origen"),
    "Size": ("Dimensione", "Taille", "Größe", "Tamaño"),
    "Destination name": ("Nome nella destinazione", "Nom à destination", "Zielname", "Nombre en destino"),
    "Your files, together": ("I tuoi file, tutti insieme", "Vos fichiers, réunis", "Ihre Dateien, gesammelt", "Tus archivos, reunidos"),
    "Choose source folders, then search.\nReview the files before moving them.": ("Scegli le cartelle di origine e avvia la ricerca.\nControlla i file prima di spostarli.", "Choisissez les dossiers sources et lancez la recherche.\nVérifiez les fichiers avant de les déplacer.", "Quellordner auswählen und Suche starten.\nDateien vor dem Verschieben prüfen.", "Elige las carpetas de origen y busca.\nRevisa los archivos antes de moverlos."),
    "No matching files": ("Nessun file corrispondente", "Aucun fichier correspondant", "Keine passenden Dateien", "No hay archivos coincidentes"),
    "Try different filters or add another source folder.": ("Prova altri filtri o aggiungi una cartella di origine.", "Essayez d’autres filtres ou un autre dossier source.", "Andere Filter oder einen weiteren Quellordner verwenden.", "Prueba otros filtros o añade otra carpeta."),
    "Destination": ("Destinazione", "Destination", "Ziel", "Destino"),
    "Choose folder": ("Scegli cartella", "Choisir un dossier", "Ordner auswählen", "Elegir carpeta"),
    "No destination selected": ("Nessuna destinazione selezionata", "Aucune destination sélectionnée", "Kein Ziel ausgewählt", "Ningún destino seleccionado"),
    "Name conflicts": ("Nomi duplicati", "Noms en conflit", "Namenskonflikte", "Nombres duplicados"),
    "Keep both (add suffix)": ("Conserva entrambi (aggiungi suffisso)", "Conserver les deux (ajouter un suffixe)", "Beide behalten (Suffix anhängen)", "Conservar ambos (añadir sufijo)"),
    "Skip existing names": ("Salta i nomi esistenti", "Ignorer les noms existants", "Vorhandene Namen überspringen", "Omitir nombres existentes"),
    "Settings": ("Impostazioni", "Paramètres", "Einstellungen", "Ajustes"),
    "Preview and move": ("Anteprima e sposta", "Aperçu et déplacement", "Prüfen und verschieben", "Vista previa y mover"),
    "Preview collection": ("Anteprima raccolta", "Aperçu du regroupement", "Sammlung prüfen", "Vista previa"),
    "Ready": ("Pronto", "Prêt", "Bereit", "Listo"),
    "Cancel": ("Annulla", "Annuler", "Abbrechen", "Cancelar"),
    "Close": ("Chiudi", "Fermer", "Schließen", "Cerrar"),
    "Choose": ("Scegli", "Choisir", "Auswählen", "Elegir"),
    "History": ("Cronologia", "Historique", "Verlauf", "Historial"),
    "Restore selected collection": ("Ripristina la raccolta selezionata", "Restaurer le regroupement sélectionné", "Ausgewählte Sammlung zurückverschieben", "Restaurar la colección seleccionada"),
    "Only unchanged files with a free original path can be restored.": ("Si ripristinano solo file invariati con il percorso originale libero.", "Seuls les fichiers inchangés dont le chemin d’origine est libre peuvent être restaurés.", "Nur unveränderte Dateien mit freiem Ursprungspfad werden wiederhergestellt.", "Solo se restauran archivos sin cambios con la ruta original libre."),
    "No collections recorded": ("Nessuna raccolta registrata", "Aucun regroupement enregistré", "Keine Sammlungen aufgezeichnet", "No hay colecciones registradas"),
    "Move selected files": ("Sposta i file selezionati", "Déplacer les fichiers sélectionnés", "Ausgewählte Dateien verschieben", "Mover archivos seleccionados"),
    "Original archives and unselected files stay where they are.": ("Gli archivi originali e i file non selezionati restano dove sono.", "Les archives originales et les fichiers non sélectionnés restent en place.", "Originalarchive und nicht ausgewählte Dateien bleiben an ihrem Platz.", "Los archivos originales y los no seleccionados permanecen en su lugar."),
    "Searching…": ("Ricerca in corso…", "Recherche en cours…", "Suche läuft…", "Buscando…"),
    "Moving…": ("Spostamento in corso…", "Déplacement en cours…", "Dateien werden verschoben…", "Moviendo…"),
    "Restoring…": ("Ripristino in corso…", "Restauration en cours…", "Wiederherstellung läuft…", "Restaurando…"),
    "Cancelling…": ("Annullamento in corso…", "Annulation en cours…", "Abbruch läuft…", "Cancelando…"),
    "Search cancelled; results are partial": ("Ricerca annullata; risultati parziali", "Recherche annulée ; résultats partiels", "Suche abgebrochen; unvollständige Ergebnisse", "Búsqueda cancelada; resultados parciales"),
    "Search complete": ("Ricerca completata", "Recherche terminée", "Suche abgeschlossen", "Búsqueda completada"),
    "Collection complete": ("Raccolta completata", "Regroupement terminé", "Sammlung abgeschlossen", "Colección completada"),
    "Restore complete": ("Ripristino completato", "Restauration terminée", "Wiederherstellung abgeschlossen", "Restauración completada"),
    "Operation cancelled": ("Operazione annullata", "Opération annulée", "Vorgang abgebrochen", "Operación cancelada"),
    "Moved: {moved}    Skipped: {skipped}    Errors: {errors}": ("Spostati: {moved}    Saltati: {skipped}    Errori: {errors}", "Déplacés : {moved}    Ignorés : {skipped}    Erreurs : {errors}", "Verschoben: {moved}    Übersprungen: {skipped}    Fehler: {errors}", "Movidos: {moved}    Omitidos: {skipped}    Errores: {errors}"),
    "{count} selected · {size}": ("{count} selezionati · {size}", "{count} sélectionnés · {size}", "{count} ausgewählt · {size}", "{count} seleccionados · {size}"),
    "{count} files": ("{count} file", "{count} fichiers", "{count} Dateien", "{count} archivos"),
    "{move} to move · {skip} to skip · {rename} renamed": ("{move} da spostare · {skip} da saltare · {rename} rinominati", "{move} à déplacer · {skip} à ignorer · {rename} renommés", "{move} verschieben · {skip} überspringen · {rename} umbenannt", "{move} a mover · {skip} a omitir · {rename} renombrados"),
    "Skip": ("Salta", "Ignorer", "Überspringen", "Omitir"),
    "Check your settings": ("Controlla le impostazioni", "Vérifiez les paramètres", "Einstellungen prüfen", "Revisa la configuración"),
    "Use positive sizes, valid ISO dates and a whole-number depth.": ("Usa dimensioni positive, date valide e una profondità intera.", "Utilisez des tailles positives, des dates valides et une profondeur entière.", "Positive Größen, gültige Daten und ganzzahlige Tiefe verwenden.", "Usa tamaños positivos, fechas válidas y profundidad entera."),
    "Details": ("Dettagli", "Détails", "Details", "Detalles"),
    "Operation failed": ("Operazione non riuscita", "Échec de l’opération", "Vorgang fehlgeschlagen", "La operación ha fallado"),
    "Appearance": ("Aspetto", "Apparence", "Darstellung", "Apariencia"),
    "Light": ("Chiaro", "Clair", "Hell", "Claro"),
    "Dark": ("Scuro", "Sombre", "Dunkel", "Oscuro"),
    "Language": ("Lingua", "Langue", "Sprache", "Idioma"),
    "Search again after changing source folders or filters.": ("Ripeti la ricerca dopo aver cambiato origini o filtri.", "Relancez la recherche après modification des sources ou des filtres.", "Nach Änderung von Quellen oder Filtern erneut suchen.", "Vuelve a buscar tras cambiar los orígenes o filtros."),
}


def system_language():
    value = os.environ.get("LANGUAGE") or os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG", "en")
    code = value.split(":")[0].split("_")[0].split(".")[0].lower()
    return code if code in LANGUAGES else "en"


def translate(message, language):
    if language == "en" or message not in CATALOG:
        return message
    return CATALOG[message][("it", "fr", "de", "es").index(language)]
