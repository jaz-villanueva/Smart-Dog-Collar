"""
Generate the carrier board for the Seeed XIAO nRF52840 Sense.

Run with KiCad's own Python, which provides the pcbnew module:

    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" generate_carrier.py

It writes dogmood_carrier.kicad_pcb next to this file. The board is described
here in code so that every coordinate is reviewable. All dimensions are in mm,
measured from the XIAO footprint's origin, with the USB connector at the top.

XIAO pad positions and names are taken from Seeed Studio's published KiCad
footprint and symbol "XIAO-nRF52840-SMD" (Seeed-Studio/OPL_Kicad_Library).
"""

from pathlib import Path

import pcbnew
from pcbnew import B_Cu, F_Cu, FromMM, VECTOR2I

OUT = Path(__file__).resolve().parent / "dogmood_carrier.kicad_pcb"

BOARD_THICKNESS = 0.8
EDGE = dict(left=-9.6, right=19.0, top=-21.5, bottom=0.4, radius=1.5)
ANTENNA_KEEPOUT_Y = -4.6   # no copper pour below this line: the XIAO's antenna is at that end

POWER_WIDTH, SIGNAL_WIDTH = 0.5, 0.3
VIA_SIZE, VIA_DRILL = 0.8, 0.4

board = pcbnew.CreateEmptyBoard()
board.GetDesignSettings().SetBoardThickness(FromMM(BOARD_THICKNESS))


def pt(x, y):
    return VECTOR2I(FromMM(x), FromMM(y))


def net(name):
    item = pcbnew.NETINFO_ITEM(board, name)
    board.Add(item)
    return item


GND, V3, SDA, SCL = net("GND"), net("+3V3"), net("SDA"), net("SCL")
BATP, VBAT = net("BAT_PLUS"), net("VBAT_SWITCHED")


def footprint(reference, value):
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference(reference)
    fp.SetValue(value)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    fp.SetPosition(pt(0, 0))
    board.Add(fp)
    return fp


def smd_pad(fp, number, x, y, width, height, pad_net=None):
    pad = pcbnew.PAD(fp)
    pad.SetNumber(str(number))
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetLayerSet(pad.SMDMask())
    pad.SetShape(F_Cu, pcbnew.PAD_SHAPE_ROUNDRECT)
    pad.SetRoundRectRadiusRatio(F_Cu, 0.25)
    pad.SetSize(F_Cu, VECTOR2I(FromMM(width), FromMM(height)))
    pad.SetPosition(pt(x, y))
    if pad_net:
        pad.SetNet(pad_net)
    fp.Add(pad)


def hole_pad(fp, number, x, y, width, height, drill, pad_net=None):
    pad = pcbnew.PAD(fp)
    pad.SetNumber(str(number))
    pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    pad.SetLayerSet(pad.PTHMask())
    pad.SetShape(F_Cu, pcbnew.PAD_SHAPE_CIRCLE if width == height else pcbnew.PAD_SHAPE_OVAL)
    pad.SetSize(F_Cu, VECTOR2I(FromMM(width), FromMM(height)))
    pad.SetDrillSize(VECTOR2I(FromMM(drill), FromMM(drill)))
    pad.SetPosition(pt(x, y))
    if pad_net:
        pad.SetNet(pad_net)
    fp.Add(pad)


def rectangle(parent, layer, x0, y0, x1, y1, width=0.05):
    shape = pcbnew.PCB_SHAPE(parent)
    shape.SetShape(pcbnew.SHAPE_T_RECT)
    shape.SetStart(pt(x0, y0))
    shape.SetEnd(pt(x1, y1))
    shape.SetLayer(layer)
    shape.SetWidth(FromMM(width))
    parent.Add(shape)


def track(points, layer, width, track_net):
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        segment = pcbnew.PCB_TRACK(board)
        segment.SetStart(pt(x0, y0))
        segment.SetEnd(pt(x1, y1))
        segment.SetWidth(FromMM(width))
        segment.SetLayer(layer)
        segment.SetNet(track_net)
        board.Add(segment)


def via(x, y, via_net):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pt(x, y))
    v.SetWidth(F_Cu, FromMM(VIA_SIZE))
    v.SetDrill(FromMM(VIA_DRILL))
    v.SetNet(via_net)
    board.Add(v)


def text(content, x, y, layer, size=0.8, angle=0):
    item = pcbnew.PCB_TEXT(board)
    item.SetText(content)
    item.SetPosition(pt(x, y))
    item.SetLayer(layer)
    item.SetTextSize(VECTOR2I(FromMM(size), FromMM(size)))
    item.SetTextThickness(FromMM(size * 0.15))
    item.SetTextAngle(pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
    if layer in (pcbnew.B_SilkS, pcbnew.B_Fab):
        item.SetMirrored(True)
    board.Add(item)


# ---------------------------------------------------------------- 3D models
# Simplified block models so the 3D view shows the assembled unit. They are
# for illustration: sizes are nominal and part positions on the XIAO are
# approximate. Each box is (x0, y0, x1, y1, z0, z1, colour) in board
# coordinates, with z measured up from the top surface of the carrier.
MODELS = Path(__file__).resolve().parent / "models"
BLACK, SILVER, GOLD = (0.08, 0.08, 0.09), (0.50, 0.51, 0.53), (0.83, 0.66, 0.22)
DARK, RED, YELLOW, BLUE = (0.2, 0.2, 0.22), (0.75, 0.1, 0.1), (0.9, 0.72, 0.15), (0.25, 0.4, 0.6)
BOX_FACES = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
             (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]


def add_model(fp, name, boxes):
    """Write boxes as a VRML file and attach it to the footprint."""
    unit = 2.54  # KiCad reads VRML in units of 0.1 inch
    shapes = []
    for x0, y0, x1, y1, z0, z1, (r, g, b) in boxes:
        # board y points down the screen; model y points up
        corners = [(x0, -y1, z0), (x1, -y1, z0), (x1, -y0, z0), (x0, -y0, z0),
                   (x0, -y1, z1), (x1, -y1, z1), (x1, -y0, z1), (x0, -y0, z1)]
        points = ", ".join(f"{x / unit:.4f} {y / unit:.4f} {z / unit:.4f}" for x, y, z in corners)
        faces = ", ".join(f"{i} {j} {k} -1" for i, j, k in BOX_FACES)
        shapes.append(
            "Shape { appearance Appearance { material Material { "
            f"diffuseColor {r} {g} {b} specularColor 0.3 0.3 0.3 shininess 0.4 }} }} "
            f"geometry IndexedFaceSet {{ solid FALSE coord Coordinate {{ point [ {points} ] }} "
            f"coordIndex [ {faces} ] }} }}")
    MODELS.mkdir(exist_ok=True)
    lines = ["#VRML V2.0 utf8", *shapes, ""]
    (MODELS / f"{name}.wrl").write_text(chr(10).join(lines), encoding="utf-8")

    model = pcbnew.FP_3DMODEL()
    model.m_Filename = "${KIPRJMOD}/models/" + f"{name}.wrl"
    fp.Models().push_back(model)


# ---------------------------------------------------------------- XIAO (U1)
# Soldered flat onto the carrier by its 14 edge pads. Pads 19 and 20 are the
# battery pads on the XIAO's underside; here they are plated holes, so they
# can be soldered from the back of the carrier with an ordinary iron.
xiao = footprint("U1", "XIAO nRF52840 Sense")
XIAO_NETS = {5: SDA, 6: SCL, 12: V3, 13: GND}
LEFT_X, RIGHT_X, FIRST_Y, PITCH = 0.835, 17.0, -18.12, 2.54
for i in range(7):
    smd_pad(xiao, i + 1, LEFT_X, FIRST_Y + i * PITCH, 2.75, 2.0, XIAO_NETS.get(i + 1))    # D0..D6
    smd_pad(xiao, 14 - i, RIGHT_X, FIRST_Y + i * PITCH, 2.75, 2.0, XIAO_NETS.get(14 - i))  # VBUS..D7
VBAT_PAD, GND_PAD = (4.445, -10.8135), (4.445, -12.7185)
hole_pad(xiao, 19, *VBAT_PAD, 2.4, 1.3, 0.8, VBAT)
hole_pad(xiao, 20, *GND_PAD, 2.4, 1.3, 0.8, GND)
rectangle(xiao, pcbnew.F_Fab, 0, -21.05, 17.8, -0.1, 0.1)
rectangle(xiao, pcbnew.F_CrtYd, -0.8, -21.3, 18.6, 0.15)
add_model(xiao, "xiao_nrf52840_sense", [
    (0, -21.05, 17.8, -0.1, 0, 1.0, BLACK),            # the XIAO's own circuit board
    (4.4, -22.4, 13.4, -15.1, 1.0, 4.2, SILVER),       # USB-C connector
    (2.6, -14.4, 15.2, -4.4, 1.0, 2.7, SILVER),        # shield can over the radio
    (11.0, -3.0, 15.4, -1.4, 1.0, 1.7, BLUE),          # antenna
    (1.6, -3.6, 4.6, -1.2, 1.0, 2.0, GOLD),            # microphone
    (6.0, -3.5, 8.6, -1.1, 1.0, 1.8, DARK),            # motion sensor
    (14.6, -17.6, 16.6, -15.8, 1.0, 1.9, DARK),        # reset button
])

# ---------------------------------------------------------------- Switch (SW1)
# SS12D00-type slide switch, three pins in a row. Middle pin is the common.
switch = footprint("SW1", "SS12D00 slide switch")
SW_X, SW_Y = -5.15, (-16.6, -14.06, -11.52)
hole_pad(switch, 1, SW_X, SW_Y[0], 1.8, 1.8, 0.9, VBAT)
hole_pad(switch, 2, SW_X, SW_Y[1], 1.8, 1.8, 0.9, BATP)
hole_pad(switch, 3, SW_X, SW_Y[2], 1.8, 1.8, 0.9)
rectangle(switch, pcbnew.F_Fab, -7.0, -18.3, -3.3, -9.8, 0.1)
rectangle(switch, pcbnew.F_CrtYd, -7.2, -18.45, -3.1, -9.65)
add_model(switch, "ss12d00_switch", [
    (-7.0, -18.3, -3.3, -9.8, 0, 3.5, SILVER),         # body
    (-5.9, -17.0, -4.4, -15.0, 3.5, 6.5, BLACK),       # lever, at the ON end
])

# ---------------------------------------------------------------- Battery (J1)
battery = footprint("J1", "LiPo battery wires")
BAT_PLUS, BAT_MINUS = (-7.6, -7.6), (-4.2, -7.6)
hole_pad(battery, 1, *BAT_PLUS, 1.9, 1.9, 1.0, BATP)
hole_pad(battery, 2, *BAT_MINUS, 1.9, 1.9, 1.0, GND)
rectangle(battery, pcbnew.F_CrtYd, -8.8, -8.8, -3.0, -6.4)
UNDER = -BOARD_THICKNESS  # the battery lies against the back of the carrier
add_model(battery, "lipo_401020", [
    (-1.0, -16.5, 19.0, -6.5, UNDER - 4.3, UNDER - 0.3, SILVER),     # cell, 20 x 10 x 4
    (-1.0, -16.5, 2.0, -6.5, UNDER - 4.35, UNDER - 0.25, YELLOW),    # tape over its protection circuit
    (-7.9, -7.0, -1.0, -6.4, UNDER - 1.4, UNDER - 0.8, RED),         # + lead
    (-7.9, -7.6, -7.3, -6.4, UNDER - 1.4, UNDER - 0.8, RED),
    (-4.5, -8.6, -1.0, -8.0, UNDER - 1.4, UNDER - 0.8, BLACK),       # - lead
    (-4.5, -8.6, -3.9, -7.6, UNDER - 1.4, UNDER - 0.8, BLACK),
])

# ---------------------------------------------------------------- Expansion (J2)
# Optional I2C port for a future sensor. Leave unpopulated otherwise.
expansion = footprint("J2", "I2C expansion pads")
EXP_Y = -19.9
EXP = {"GND": (-8.15, GND), "3V3": (-6.15, V3), "SCL": (-4.15, SCL), "SDA": (-2.15, SDA)}
for number, (x, pad_net) in enumerate(EXP.values(), start=1):
    hole_pad(expansion, number, x, EXP_Y, 1.4, 1.4, 0.7, pad_net)
rectangle(expansion, pcbnew.F_CrtYd, -9.05, -20.8, -1.25, -19.0)

# ---------------------------------------------------------------- Tracks
# Battery + to the switch's common pin (front)
track([BAT_PLUS, (BAT_PLUS[0], SW_Y[1]), (SW_X, SW_Y[1])], F_Cu, POWER_WIDTH, BATP)
# Switch output to the XIAO's battery pad (back, under the XIAO)
track([(SW_X, SW_Y[0]), (2.2, SW_Y[0]), (2.2, VBAT_PAD[1]), VBAT_PAD], B_Cu, POWER_WIDTH, VBAT)
# I2C from the XIAO's D4/D5 pads up the gap beside the XIAO (front)
D4_Y, D5_Y = FIRST_Y + 4 * PITCH, FIRST_Y + 5 * PITCH
track([(LEFT_X, D4_Y), (-1.5, D4_Y), (-1.5, -19.25), (EXP["SDA"][0], EXP_Y)], F_Cu, SIGNAL_WIDTH, SDA)
track([(LEFT_X, D5_Y), (-2.3, D5_Y), (-2.3, -18.0), (-2.9, -18.6), (EXP["SCL"][0], -18.6),
       (EXP["SCL"][0], EXP_Y)], F_Cu, SIGNAL_WIDTH, SCL)
# 3.3 V from the XIAO's right side, through a via, across the back
V3_Y = FIRST_Y + 2 * PITCH
track([(RIGHT_X, V3_Y), (13.2, V3_Y)], F_Cu, 0.4, V3)
via(13.2, V3_Y, V3)
track([(13.2, V3_Y), (13.2, -18.3), (EXP["3V3"][0], -18.3), (EXP["3V3"][0], EXP_Y)], B_Cu, 0.4, V3)
# Ground from the XIAO's GND pad into the ground plane on the back
GND_Y = FIRST_Y + PITCH
track([(RIGHT_X, GND_Y), (14.4, GND_Y)], F_Cu, POWER_WIDTH, GND)
via(14.4, GND_Y, GND)

# ---------------------------------------------------------------- Ground plane
zone = pcbnew.ZONE(board)
zone.SetLayer(B_Cu)
zone.SetNet(GND)
zone.SetZoneName("GND")
zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
zone.SetMinThickness(FromMM(0.25))
outline = zone.Outline()
outline.NewOutline()
for x, y in [(EDGE["left"], EDGE["top"]), (EDGE["right"], EDGE["top"]),
             (EDGE["right"], ANTENNA_KEEPOUT_Y), (EDGE["left"], ANTENNA_KEEPOUT_Y)]:
    outline.Append(FromMM(x), FromMM(y))
board.Add(zone)

# ---------------------------------------------------------------- Board outline
def edge_line(x0, y0, x1, y1):
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
    shape.SetStart(pt(x0, y0))
    shape.SetEnd(pt(x1, y1))
    shape.SetLayer(pcbnew.Edge_Cuts)
    shape.SetWidth(FromMM(0.1))
    board.Add(shape)


def edge_arc(start, mid, end):
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_ARC)
    shape.SetArcGeometry(pt(*start), pt(*mid), pt(*end))
    shape.SetLayer(pcbnew.Edge_Cuts)
    shape.SetWidth(FromMM(0.1))
    board.Add(shape)


L, R, T, B, RAD = EDGE["left"], EDGE["right"], EDGE["top"], EDGE["bottom"], EDGE["radius"]
K = RAD * (1 - 0.5 ** 0.5)  # offset of an arc's midpoint from its corner
edge_line(L + RAD, T, R - RAD, T)
edge_line(R, T + RAD, R, B - RAD)
edge_line(R - RAD, B, L + RAD, B)
edge_line(L, B - RAD, L, T + RAD)
edge_arc((L, T + RAD), (L + K, T + K), (L + RAD, T))
edge_arc((R - RAD, T), (R - K, T + K), (R, T + RAD))
edge_arc((R, B - RAD), (R - K, B - K), (R - RAD, B))
edge_arc((L + RAD, B), (L + K, B - K), (L, B - RAD))

# ---------------------------------------------------------------- Labels
text("+", BAT_PLUS[0], -5.6, pcbnew.F_SilkS, 1.2)
text("-", BAT_MINUS[0], -5.6, pcbnew.F_SilkS, 1.2)
text("ON", -8.6, SW_Y[0], pcbnew.F_SilkS, 0.8, 90)
text("OFF", -8.6, SW_Y[2] - 0.3, pcbnew.F_SilkS, 0.8, 90)
text("BAT+", BAT_PLUS[0], -5.6, pcbnew.B_SilkS, 0.8)
text("BAT-", BAT_MINUS[0] + 0.5, -5.6, pcbnew.B_SilkS, 0.8)
for name, (x, _) in EXP.items():
    text(name[-1] if name[0] == "S" else name[0], x, -18.45, pcbnew.B_SilkS, 0.8)  # G 3 L A
text("G=GND 3=3V3 L=SCL A=SDA", 8.0, -8.0, pcbnew.B_SilkS, 0.8)
text("DogMood carrier v1", 9.5, -3.3, pcbnew.B_SilkS, 0.9)
text("XIAO nRF52840 Sense", 9.5, -1.7, pcbnew.B_SilkS, 0.8)
text("XIAO: USB at this end", 8.9, -20.3, pcbnew.F_Fab, 0.8)

# The ground plane is filled afterwards by kicad-cli (see README.md in this folder)
pcbnew.SaveBoard(str(OUT), board)
print("wrote", OUT)
