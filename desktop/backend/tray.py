"""Optional Windows notification-area controls for the desktop window."""

from threading import Lock, Thread

from backend.services.settings import load_preferences


class DesktopTray:
    def __init__(self, window, icon_path):
        import pystray
        from PIL import Image

        self.window = window
        self.lock = Lock()
        self.exiting = False
        with Image.open(icon_path) as image:
            icon_image = image.convert("RGBA")
        self.icon = pystray.Icon(
            "MarketAI", icon_image, "MarketAI",
            pystray.Menu(
                pystray.MenuItem("Abrir MarketAI", self.show, default=True),
                pystray.MenuItem("Encerrar MarketAI", self.quit),
            ),
        )
        window.events.minimized += self.minimize

    def start(self):
        Thread(target=self.icon.run, name="MarketAI-tray", daemon=True).start()

    def minimize(self):
        with self.lock:
            if self.icon.visible and not self.exiting and load_preferences()["minimize_to_tray"]:
                self.window.hide()

    def show(self):
        with self.lock:
            if not self.exiting:
                self.window.show()
                self.window.restore()

    def quit(self):
        with self.lock:
            self.exiting = True
        self.window.destroy()

    def stop(self):
        self.icon.stop()
