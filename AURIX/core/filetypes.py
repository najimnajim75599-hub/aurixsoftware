"""File type groups and the words people use for them ("slides", "photo")."""
GROUPS = {
    "Images": {"png", "jpg", "jpeg", "gif", "bmp", "svg", "webp", "ico", "tif", "tiff"},
    "Documents": {"pdf", "doc", "docx", "txt", "md", "rtf", "odt"},
    "Presentations": {"ppt", "pptx", "odp", "key"},
    "Spreadsheets": {"xls", "xlsx", "csv", "ods"},
    "Code": {"py", "js", "ts", "html", "css", "json", "java", "c", "cpp", "cs", "go", "rs", "php", "sql", "sh"},
    "Audio/Video": {"mp3", "wav", "flac", "m4a", "mp4", "mkv", "avi", "mov", "webm"},
    "Archives": {"zip", "rar", "7z", "tar", "gz"},
}
ALL_KNOWN = set().union(*GROUPS.values())
GROUP_NAMES = list(GROUPS) + ["Other"]

WORD_TO_GROUP = {
    "image": "Images", "images": "Images", "photo": "Images", "photos": "Images",
    "picture": "Images", "pictures": "Images",
    "presentation": "Presentations", "presentations": "Presentations",
    "slides": "Presentations", "slide": "Presentations", "deck": "Presentations",
    "document": "Documents", "documents": "Documents", "report": "Documents", "paper": "Documents",
    "spreadsheet": "Spreadsheets", "spreadsheets": "Spreadsheets", "excel": "Spreadsheets",
    "video": "Audio/Video", "videos": "Audio/Video", "music": "Audio/Video",
    "audio": "Audio/Video", "song": "Audio/Video",
    "code": "Code", "script": "Code",
}


def group_of(extension: str) -> str:
    ext = extension.lower().lstrip(".")
    for name, exts in GROUPS.items():
        if ext in exts:
            return name
    return "Other"


def extensions_for_word(word: str) -> set:
    group = WORD_TO_GROUP.get(word.lower())
    if group:
        return set(GROUPS[group])
    if word.lower() in ALL_KNOWN:
        return {word.lower()}
    return set()
