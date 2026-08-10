from pathlib import Path

from PySide6.QtCore import QObject, Signal, QStandardPaths, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest

from app.shared.card_catalog import CardCatalog
from .providers import ScryfallProvider


class AssetManager(QObject):
    image_ready = Signal(str, str, QPixmap)
    image_failed = Signal(str, str)

    def __init__(self, catalog, cache_dir=None, provider=None, network=None, parent=None):
        super().__init__(parent)
        self.catalog = catalog
        self.cache_dir = Path(cache_dir) if cache_dir else Path(QStandardPaths.writableLocation(QStandardPaths.CacheLocation)) / "MTGNP" / "cards"
        self.memory = {}
        self._pending = {}
        self._failed = set()
        self.network = network or QNetworkAccessManager(self)
        self.provider = provider or ScryfallProvider(self.network, self)
        self.provider.resolved.connect(self._download)
        self.provider.failed.connect(self._failed_image)

    def key(self, card_id, variant="art"):
        return CardCatalog.base_card_id(card_id), variant

    def request(self, card_id, variant="art"):
        base, variant = self.key(card_id, variant)
        key = (base, variant)
        if key in self.memory:
            self.image_ready.emit(base, variant, self.memory[key]); return
        path = self._path(base, variant)
        if path.exists():
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                self.memory[key] = pixmap; self.image_ready.emit(base, variant, pixmap); return
            path.unlink(missing_ok=True)
        if key in self._pending or key in self._failed: return
        self._pending[key] = True
        data = self.catalog.get_card_data(base) or {}
        name = data.get("name", base.replace("_", " ").title())
        self.provider.resolve(base, name, variant)

    def _path(self, base, variant):
        directory = self.cache_dir / variant
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{base}.png"

    def _download(self, base, variant, url):
        reply = self.network.get(QNetworkRequest(QUrl(url)))
        reply.finished.connect(lambda: self._on_download(reply, base, variant))

    def _on_download(self, reply, base, variant):
        key = (base, variant); self._pending.pop(key, None)
        pixmap = QPixmap(); pixmap.loadFromData(bytes(reply.readAll()))
        if reply.error() or pixmap.isNull(): self._failed_image(base, variant)
        else:
            self.memory[key] = pixmap
            try: pixmap.save(str(self._path(base, variant)))
            except OSError: pass
            self.image_ready.emit(base, variant, pixmap)
        reply.deleteLater()

    def _failed_image(self, base, variant):
        self._pending.pop((base, variant), None); self._failed.add((base, variant)); self.image_failed.emit(base, variant)

    def prefetch(self, card_ids, variant="art"):
        for card_id in {CardCatalog.base_card_id(item) for item in card_ids}: self.request(card_id, variant)
