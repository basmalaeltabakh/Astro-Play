"""Astro Play entry point.  Run:  python main.py"""
import sys

from ursina import Ursina, Text, application, window

from astro import config
from astro.assistant import SpaceAssistant
from astro.db import Database
from astro.game.app import Game


def main():
    Text.default_resolution = 1080 * Text.size      # crisp text
    app = Ursina(title="Astro Play", borderless=False, development_mode=False, size=(1280, 720))
    db = Database(config.DB_PATH)
    assistant = SpaceAssistant(use_chroma="--no-chroma" not in sys.argv)
    Game(db, assistant)
    app.run()


if __name__ == "__main__":
    main()
