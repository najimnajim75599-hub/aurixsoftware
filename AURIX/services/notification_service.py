from PySide6.QtCore import QObject, Signal


class NotificationService(QObject):
    """One place for user messages; the main window shows them in the status bar."""
    message = Signal(str, str)  # text, kind ('info' | 'success' | 'error')

    def info(self, text): self.message.emit(text, "info")
    def success(self, text): self.message.emit(text, "success")
    def error(self, text): self.message.emit(text, "error")
