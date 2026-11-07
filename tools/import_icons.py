"""Import pinned Lucide line icons as Android vector resources (ISC license)."""
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET

NAMES = "arrow-down-up upload download circle-play skip-back skip-forward volume-2 volume-1 clock log-in refresh-cw plus pencil trash check chevron-right file-text copy sun moon".split()
DEST = Path(__file__).resolve().parents[1] / "pc-phone-remote-android/app/src/main/res/drawable"
REVISION = "66d8f9fc394b8530377e5f6112f0b8908ba01280"


def path_data(node):
    tag = node.tag.split("}")[-1]
    a = node.attrib
    if tag == "path":
        return a["d"]
    if tag == "line":
        return f'M{a["x1"]},{a["y1"]} L{a["x2"]},{a["y2"]}'
    if tag in {"polyline", "polygon"}:
        return "M" + a["points"] + (" Z" if tag == "polygon" else "")
    if tag == "circle":
        x, y, r = (float(a[key]) for key in ("cx", "cy", "r"))
        return f"M{x-r},{y} a{r},{r} 0 1,0 {r*2},0 a{r},{r} 0 1,0 {-r*2},0"
    if tag == "rect":
        x, y, w, h = (float(a.get(key, "0")) for key in ("x", "y", "width", "height"))
        r = float(a.get("rx", "0"))
        return f"M{x+r},{y} H{x+w-r} Q{x+w},{y} {x+w},{y+r} V{y+h-r} Q{x+w},{y+h} {x+w-r},{y+h} H{x+r} Q{x},{y+h} {x},{y+h-r} V{y+r} Q{x},{y} {x+r},{y} Z"
    raise ValueError(tag)


for name in NAMES:
    with urllib.request.urlopen(f"https://raw.githubusercontent.com/lucide-icons/lucide/{REVISION}/icons/{name}.svg", timeout=20) as response:
        svg = ET.fromstring(response.read())
    paths = [path_data(child) for child in svg]
    xml = '<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="24dp" android:height="24dp" android:viewportWidth="24" android:viewportHeight="24">\n'
    for path in paths:
        xml += f'    <path android:fillColor="@android:color/transparent" android:strokeColor="#FFFFFFFF" android:strokeWidth="1.8" android:strokeLineCap="round" android:strokeLineJoin="round" android:pathData="{path}" />\n'
    xml += "</vector>\n"
    (DEST / ("ic_" + name.replace("-", "_") + ".xml")).write_text(xml, encoding="utf-8")
with urllib.request.urlopen(f"https://raw.githubusercontent.com/lucide-icons/lucide/{REVISION}/LICENSE", timeout=20) as response:
    (DEST.parents[4] / "LUCIDE-LICENSE.txt").write_bytes(response.read())
print(f"Imported {len(NAMES)} Lucide icons")
