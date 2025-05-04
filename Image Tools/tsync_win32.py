import os
from win32com.propsys import propsys, pscon
import sync_tags
from PIL import Image, ExifTags
from win32_setctime import setctime
import pathlib
from pillow_heif import register_heif_opener
import shutil

register_heif_opener()

source = ""
path = "/home/ntheme/Data1/Temp/jj/"

RESULT = "adjusted/"
SOURCES = ["crt", "mod", "tak", "med"]


class Metainfo:
    path: str
    name: str
    type: str
    data: datetime.datetime = datetime.datetime.now()
    read: bool = False

    def __init__(self, path, name, source):
        self.path = path
        self.name = name
        self.type = pathlib.Path(name).suffix

        try:
            if source == "crt":
                self.data = datetime.datetime.fromtimestamp(int(os.path.getctime(path + name)))
            if source == "mod":
                self.data = datetime.datetime.fromtimestamp(int(os.path.getmtime(path + name)))
            if source == "tak":
                image = Image.open(path + name)
                ctime = image.getexif().get(ExifTags.Base.DateTime)
                print(image.getexif())
                self.data = datetime.datetime.strptime(ctime, "%Y:%m:%d %H:%M:%S")
                image.close()
            if source == "med":
                properties = propsys.SHGetPropertyStoreFromParsingName(path + name)
                ctime = properties.GetValue(pscon.PKEY_Media_DateEncoded).GetValue()
                self.data = datetime.datetime.fromtimestamp(ctime.timestamp())
        except Exception as e:
            print(e)
        else:
            self.read = True
            print("--Metainfo is read")


def renameObject(metainfo: Metainfo) -> None:
    stamp = metainfo.data
    new_name = metainfo.data.strftime("%Y%m%d_%H%M%S") + metainfo.type
    print(f'--Out: {new_name}')
    try:
        shutil.copy(metainfo.path + metainfo.name, metainfo.path + RESULT + new_name)
        print("SUCCESS!")
    except Exception as e:
        print(e)
    print()


def fix_time(filepath):
    new_time = datetime.datetime(int(filepath[0:4]), int(filepath[4:6]), int(filepath[6:8]), int(filepath[9:11]),
                                 int(filepath[11:13]), int(filepath[13:15])).timestamp()
    os.utime(filepath, times=(new_time, new_time))
    setctime(filepath, new_time)


while not os.path.isdir(path):
    print("Path (\\): ", end="")
    path = str(input())
pathlib.Path(path + RESULT).mkdir(parents=True, exist_ok=True)

while source not in SOURCES:
    print("Source (crt, mod, tak, med): ", end="")
    source = str(input())

for name in os.listdir(path):
    if name != "adjusted":
        print(f'File {name}')
        metainfo = Metainfo(path, name, source)
        if metainfo.read:
            renameObject(metainfo)
