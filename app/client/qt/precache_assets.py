"""Optional developer utility for warming the unique fixed-catalog artwork cache."""
from pathlib import Path
from PySide6.QtWidgets import QApplication
from app.shared.card_catalog import CardCatalog
from .assets import AssetManager


def main():
    app = QApplication.instance() or QApplication([])
    catalog = CardCatalog(Path(__file__).resolve().parents[2] / "shared" / "card_catalog.json")
    manager = AssetManager(catalog)
    manager.prefetch(catalog.catalog)
    print(f"scheduled {len(set(catalog.base_card_id(i) for i in catalog.catalog))} unique cards")
    return app.exec()


if __name__ == "__main__":
    main()
