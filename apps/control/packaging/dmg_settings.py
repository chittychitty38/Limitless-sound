# dmgbuild settings for the Mac disk image. Used by CI:
#   dmgbuild -s packaging/dmg_settings.py -D app="dist/Limitless Control.app" "Limitless Control" out.dmg
import os.path

app = defines["app"]  # noqa: F821 (provided by dmgbuild)
icons = os.path.join("packaging", "icons")

format = "UDZO"
files = [app]
symlinks = {"Applications": "/Applications"}
icon = os.path.join(icons, "icon.icns")
background = os.path.join(icons, "dmg-background.png")
window_rect = ((200, 140), (640, 400))
default_view = "icon-view"
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
icon_size = 112
text_size = 13
icon_locations = {
    os.path.basename(app): (170, 210),
    "Applications": (470, 210),
}
