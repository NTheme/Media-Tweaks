# --========================================-- #
#   * Author  : NTheme - All rights reserved
#   * Created : 15 May 2025, 1:21 AM
#   * File    : resave.py
#   * Project : Image Tools
# --========================================-- #

from PIL import Image

DEFAULT_SRC = "/home/ntheme/Data1/Temp/Sorting/Camera/"
DEFAULT_DST = "adjusted/"

NAME = "20250104_193619.jpg"

img = Image.open(DEFAULT_SRC + NAME)

img.save(DEFAULT_SRC + DEFAULT_DST + NAME, format="JPEG", quality=95, optimize=True)
