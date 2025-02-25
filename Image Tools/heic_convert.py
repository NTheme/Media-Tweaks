from PIL import Image
import pillow_heif
import os
from pathlib import Path

path = "D:\\Newfolder\\"

pillow_heif.register_heif_opener()

for name in os.listdir(path):
  if name != "adjusted":
    img = Image.open(path + name)
    new_name = path + "adjusted\\" + Path(name).stem + ".jpg"
    print(new_name)
    img.save(new_name, format('jpeg'))
    