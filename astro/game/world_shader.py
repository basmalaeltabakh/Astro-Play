"""One shared lit shader for the 3D worlds: sun shadows when enabled (ASTRO_SHADOWS=1, experimental)."""
from ursina.shaders import basic_lighting_shader, lit_with_shadows_shader

from .. import config

LIT = lit_with_shadows_shader if config.SHADOWS else basic_lighting_shader
