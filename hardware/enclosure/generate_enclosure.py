"""
Generate the printable housing for the carrier-board build of the wearable.

    pip install cadquery
    python generate_enclosure.py

It writes base.stl, base_strap.stl, lid.stl and enclosure.step next to this
file. Every dimension is a named value below, in mm.

Positions are given in the carrier board's own coordinates, the same ones
hardware/pcb/generate_carrier.py uses (x to the right, y down the screen, USB
at the top). bx()/by() turn them into model coordinates, where y points up, so
the printed part is not a mirror image of the board.

Board, XIAO pad and hole positions come from generate_carrier.py and are exact.
Part heights (XIAO, USB-C connector, switch, battery) are nominal catalogue
figures: print once, check the fit, and adjust the values marked NOMINAL.
"""

from pathlib import Path

import cadquery as cq

OUT = Path(__file__).resolve().parent

# ---------------------------------------------------------------- Carrier board (exact)
BOARD = dict(left=-9.6, right=19.0, top=-21.5, bottom=0.4, radius=1.5)
PCB_THICKNESS = 0.8

# ---------------------------------------------------------------- Parts (NOMINAL)
BATTERY_THICKNESS = 4.2      # 401020 cell; use 5.2 for a 501225
JOINT_ALLOWANCE = 1.2        # solder joints and tape between board and battery
TOP_CLEARANCE = 5.0          # board top to ceiling: XIAO + USB-C is about 4.2, switch body 3.5
XIAO_PCB_THICKNESS = 1.0
XIAO_CENTRE_X = 8.9          # the XIAO is 17.8 wide, from x = 0
USB_WIDTH, USB_HEIGHT = 9.6, 4.0          # opening for the connector (8.94 x 3.16)
PLUG_WIDTH, PLUG_HEIGHT = 13.0, 7.0       # recess for the cable's plug body (12.35 x 6.5)
PLUG_RECESS = 1.2
SWITCH_X = -5.15             # line of the switch pins
SWITCH_SLOT = dict(x0=-6.75, x1=-3.55, y0=-17.4, y1=-10.7)   # lever travel plus margin
MIC = (3.1, -2.4)            # approximate; any hole into the cavity lets sound in
MIC_HOLE = 1.5
POSTS = [(-8.4, -13.0), (-7.0, -2.5)]     # press the board down where it is bare
POST_DIAMETER = 1.8

# ---------------------------------------------------------------- Housing
CLEARANCE = 0.25             # board edge to wall
WALL = 2.0
FLOOR = ROOF = 1.6
LEDGE = 1.0                  # shelf the board rests on
LAP = 1.5                    # height of the overlapping joint between base and lid
RIM = 1.0                    # outer half of the joint, on the base
JOINT_GAP = 0.15             # between the two halves of the joint
EDGE_RADIUS = 1.5            # rounding of the top and bottom edges

STRAP_WIDTH = 10.0           # harness webbing
STRAP_SLOT = (STRAP_WIDTH + 1.5, 2.6)
WING = dict(length=17.0, reach=6.0, thickness=2.4, radius=0.8)


def bx(x):
    return x


def by(y):
    return -y


INNER_W = BOARD["right"] - BOARD["left"] + 2 * CLEARANCE
INNER_D = BOARD["bottom"] - BOARD["top"] + 2 * CLEARANCE
INNER_R = BOARD["radius"] + CLEARANCE
CX = (BOARD["left"] + BOARD["right"]) / 2
CY = by((BOARD["top"] + BOARD["bottom"]) / 2)
OUTER_W, OUTER_D, OUTER_R = INNER_W + 2 * WALL, INNER_D + 2 * WALL, INNER_R + WALL

Z_SHELF = FLOOR + BATTERY_THICKNESS + JOINT_ALLOWANCE     # underside of the board
Z_BOARD = Z_SHELF + PCB_THICKNESS                         # top of the board
Z_SPLIT = Z_BOARD + LAP                                   # where base meets lid outside
Z_CEILING = Z_BOARD + TOP_CLEARANCE
Z_TOP = Z_CEILING + ROOF


def slab(inset, z0, z1):
    """A rounded rectangle the shape of the housing, shrunk by inset, from z0 to z1."""
    return (cq.Workplane("XY").workplane(offset=z0).center(CX, CY)
            .rect(OUTER_W - 2 * inset, OUTER_D - 2 * inset).extrude(z1 - z0)
            .edges("|Z").fillet(OUTER_R - inset))


def box(x0, x1, y0, y1, z0, z1):
    return (cq.Workplane("XY").workplane(offset=z0).center((x0 + x1) / 2, (y0 + y1) / 2)
            .rect(x1 - x0, y1 - y0).extrude(z1 - z0))


def usb_cut():
    """Opening for the USB-C connector, and a recess so the plug seats fully."""
    wall_inside = by(BOARD["top"]) + CLEARANCE
    z_mid = Z_BOARD + XIAO_PCB_THICKNESS + 1.6
    opening = box(XIAO_CENTRE_X - USB_WIDTH / 2, XIAO_CENTRE_X + USB_WIDTH / 2,
                  wall_inside - 0.5, wall_inside + WALL + 1,
                  z_mid - USB_HEIGHT / 2, z_mid + USB_HEIGHT / 2).edges("|Y").fillet(1.0)
    recess = box(XIAO_CENTRE_X - PLUG_WIDTH / 2, XIAO_CENTRE_X + PLUG_WIDTH / 2,
                 wall_inside + WALL - PLUG_RECESS, wall_inside + WALL + 1,
                 z_mid - PLUG_HEIGHT / 2, z_mid + PLUG_HEIGHT / 2).edges("|Y").fillet(2.0)
    return opening.union(recess)


def make_base(strap=False):
    base = slab(0, 0, Z_SPLIT).faces("<Z").edges().fillet(EDGE_RADIUS)
    if strap:
        for side in (-1, 1):
            face = CX + side * OUTER_W / 2
            near, far = sorted((face - side * 1.5, face + side * WING["reach"]))
            wing = (box(near, far, CY - WING["length"] / 2, CY + WING["length"] / 2,
                        0, WING["thickness"])
                    .edges("|Z").fillet(2.5).edges().fillet(WING["radius"]))
            slot_x = face + side * (1.2 + STRAP_SLOT[1] / 2)
            slot = (box(slot_x - STRAP_SLOT[1] / 2, slot_x + STRAP_SLOT[1] / 2,
                        CY - STRAP_SLOT[0] / 2, CY + STRAP_SLOT[0] / 2, -1, WING["thickness"] + 1)
                    .edges("|Z").fillet(1.0))
            base = base.union(wing.cut(slot))
    base = base.cut(slab(WALL + LEDGE, FLOOR, Z_SHELF + 0.01))    # battery pocket
    base = base.cut(slab(WALL, Z_SHELF, Z_BOARD + 0.01))          # board seat
    base = base.cut(slab(RIM, Z_BOARD, Z_SPLIT + 1))              # socket for the lid's tongue
    return base.cut(usb_cut())


def make_lid():
    lid = slab(0, Z_SPLIT, Z_TOP).faces(">Z").edges().fillet(EDGE_RADIUS)
    lid = lid.union(slab(RIM + JOINT_GAP, Z_BOARD + 0.1, Z_SPLIT + 0.01))   # tongue
    lid = lid.cut(slab(WALL, Z_BOARD - 1, Z_CEILING))
    for x, y in POSTS:
        post = (cq.Workplane("XY").workplane(offset=Z_BOARD + 0.05).center(bx(x), by(y))
                .circle(POST_DIAMETER / 2).extrude(Z_CEILING - Z_BOARD + 0.1))
        lid = lid.union(post)
    s = SWITCH_SLOT
    slot = box(s["x0"], s["x1"], by(s["y1"]), by(s["y0"]), Z_CEILING - 1, Z_TOP + 1)
    lid = lid.cut(slot.edges("|Z").fillet(1.2))
    mic = (cq.Workplane("XY").workplane(offset=Z_CEILING - 1).center(bx(MIC[0]), by(MIC[1]))
           .circle(MIC_HOLE / 2).extrude(ROOF + 2))
    return lid.cut(mic).cut(usb_cut())


def contents():
    """Nominal blocks for the board and parts, used only to check that nothing collides."""
    b = BOARD
    parts = (box(b["left"], b["right"], by(b["bottom"]), by(b["top"]), Z_SHELF, Z_BOARD)
             .edges("|Z").fillet(b["radius"]))
    parts = parts.union(box(0, 17.8, 0.1, 21.05, Z_BOARD, Z_BOARD + 2.7))              # XIAO + shield
    parts = parts.union(box(4.43, 13.37, 15.1, 22.4, Z_BOARD + 1.0, Z_BOARD + 4.2))    # USB-C
    parts = parts.union(box(-7.0, -3.3, 9.8, 18.3, Z_BOARD, Z_BOARD + 3.5))            # switch body
    parts = parts.union(box(-5.9, -4.4, 11.1, 17.0, Z_BOARD + 3.5, Z_BOARD + 6.5))     # lever sweep
    parts = parts.union(box(-2.0, 18.0, 6.5, 16.5, Z_SHELF - JOINT_ALLOWANCE - 4.0,
                            Z_SHELF - JOINT_ALLOWANCE))                                # battery
    return parts


if __name__ == "__main__":
    base, base_strap, lid = make_base(), make_base(strap=True), make_lid()

    cq.exporters.export(base, str(OUT / "base.stl"), tolerance=0.02, angularTolerance=0.2)
    cq.exporters.export(base_strap, str(OUT / "base_strap.stl"), tolerance=0.02, angularTolerance=0.2)
    # The lid prints roof-down, so turn it over and set it on the bed
    flipped = lid.rotate((0, 0, 0), (1, 0, 0), 180).translate((0, 0, Z_TOP))
    cq.exporters.export(flipped, str(OUT / "lid.stl"), tolerance=0.02, angularTolerance=0.2)

    assembly = cq.Assembly()
    assembly.add(base_strap, name="base_strap", color=cq.Color(0.2, 0.5, 0.8))
    assembly.add(lid, name="lid", color=cq.Color(0.9, 0.9, 0.9))
    assembly.save(str(OUT / "enclosure.step"))

    inside = contents()
    for name, part in (("base", base), ("base_strap", base_strap), ("lid", lid)):
        box_ = part.val().BoundingBox()
        clash = part.intersect(inside).val().Volume() if part.intersect(inside).vals() else 0.0
        print(f"{name:11s} {box_.xlen:5.1f} x {box_.ylen:5.1f} x {box_.zlen:5.1f} mm  "
              f"volume {part.val().Volume() / 1000:.2f} cm3  "
              f"valid={part.val().isValid()}  overlap with parts {clash:.3f} mm3")
    print(f"assembled height {Z_TOP:.1f} mm; base/lid overlap "
          f"{base.intersect(lid).val().Volume() if base.intersect(lid).vals() else 0.0:.3f} mm3")
