"""Settings menu definition.

Each entry picks a template (screen layout):
- ``range``:   value shown as solid blocks; scrolling changes it live.
- ``options``: scroll through choices; click saves.
- ``confirm``: Yes/No; click on Yes runs ``action``.
"""

SETTINGS = [
    {"label": "LCD Brightness", "key": "lcd_brightness", "template": "range", "min": 1, "max": 16},
    {"label": "LCD Contrast", "key": "lcd_contrast", "template": "range", "min": 0, "max": 16},
    {
        "label": "Record Mode",
        "key": "record_mode",
        "template": "options",
        "options": [("auto", "Auto"), ("standalone", "Standalone"), ("lanc", "LANC")],
    },
    {"label": "Factory Reset", "template": "confirm", "action": "factory_reset"},
]
