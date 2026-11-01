#!/usr/bin/env python3
"""
3D Model Generator for Taylor Wimpey 'The Blair 4 TK' (Scottish TK Range)
FLIPPED / LEFT-HAND SIDE SEMI-DETACHED CONFIGURATION
Exact user and blueprint compliance:
1. Normal open timber banister on stairs (NO weird full-height boxing on landing/stairs).
2. Under-stairs cupboard is boxed in under the stairs, with a full-size door in the kitchen.
3. Solid floor-to-ceiling partition wall from top of stairs to bedroom (NO drop-off down stairs).
4. Solar panels are on the REAR roof.
5. NO cube in the front of the house (foundation strictly flush under building).
6. Downstairs WC is longer along gable wall, with window, toilet under window, sink on living room side.
7. Downstairs WC does NOT jut into kitchen (flush transverse wall).
8. En-Suite: shower at the back, sink under front window W4, toilet beside sink far from door.
9. Upstairs Family Bathroom: bath on left side, sink under window W6, toilet to right of sink, door in landing hallway.
10. EV Wallbox charger to the right of front door.
"""

import math
import struct
import json
import os

class MeshGroup:
    def __init__(self, name, material_name):
        self.name = name
        self.material_name = material_name
        self.vertices = []
        self.normals = []
        self.texcoords = []
        self.faces = []

    def add_quad(self, p1, p2, p3, p4, normal=None, uv1=(0,0), uv2=(1,0), uv3=(1,1), uv4=(0,1)):
        if normal is None:
            v1 = (p2[0]-p1[0], p2[1]-p1[1], p2[2]-p1[2])
            v2 = (p4[0]-p1[0], p4[1]-p1[1], p4[2]-p1[2])
            nx = v1[1]*v2[2] - v1[2]*v2[1]
            ny = v1[2]*v2[0] - v1[0]*v2[2]
            nz = v1[0]*v2[1] - v1[1]*v2[0]
            l = math.sqrt(nx*nx + ny*ny + nz*nz)
            if l > 1e-6:
                normal = (nx/l, ny/l, nz/l)
            else:
                normal = (0.0, 0.0, 1.0)

        base_v = len(self.vertices)
        self.vertices.extend([p1, p2, p3, p4])
        self.normals.extend([normal]*4)
        self.texcoords.extend([uv1, uv2, uv3, uv4])

        self.faces.append([base_v, base_v+1, base_v+2])
        self.faces.append([base_v, base_v+2, base_v+3])

    def add_triangle(self, p1, p2, p3, normal=None, uv1=(0,0), uv2=(1,0), uv3=(0.5,1)):
        if normal is None:
            v1 = (p2[0]-p1[0], p2[1]-p1[1], p2[2]-p1[2])
            v2 = (p3[0]-p1[0], p3[1]-p1[1], p3[2]-p1[2])
            nx = v1[1]*v2[2] - v1[2]*v2[1]
            ny = v1[2]*v2[0] - v1[0]*v2[2]
            nz = v1[0]*v2[1] - v1[1]*v2[0]
            l = math.sqrt(nx*nx + ny*ny + nz*nz)
            if l > 1e-6:
                normal = (nx/l, ny/l, nz/l)
            else:
                normal = (0.0, 0.0, 1.0)

        base_v = len(self.vertices)
        self.vertices.extend([p1, p2, p3])
        self.normals.extend([normal]*3)
        self.texcoords.extend([uv1, uv2, uv3])
        self.faces.append([base_v, base_v+1, base_v+2])

    def add_box(self, x0, y0, z0, x1, y1, z1):
        # Bottom (-Z)
        self.add_quad((x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0), normal=(0, 0, -1))
        # Top (+Z)
        self.add_quad((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1), normal=(0, 0, 1))
        # Front (-Y)
        self.add_quad((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1), normal=(0, -1, 0))
        # Rear (+Y)
        self.add_quad((x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1), normal=(0, 1, 0))
        # Left (-X)
        self.add_quad((x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1), normal=(-1, 0, 0))
        # Right (+X)
        self.add_quad((x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1), normal=(1, 0, 0))

    def add_cylinder(self, x, y, z0, z1, radius, segments=12):
        for i in range(segments):
            a0 = 2 * math.pi * i / segments
            a1 = 2 * math.pi * (i + 1) / segments
            x0 = x + radius * math.cos(a0)
            y0 = y + radius * math.sin(a0)
            x1 = x + radius * math.cos(a1)
            y1 = y + radius * math.sin(a1)
            amid = 0.5 * (a0 + a1)
            n = (math.cos(amid), math.sin(amid), 0.0)
            self.add_quad((x0, y0, z0), (x1, y1, z0), (x1, y1, z1), (x0, y0, z1), normal=n)

    def add_cylinder_x(self, x0, x1, y, z, radius, segments=12):
        for i in range(segments):
            a0 = 2 * math.pi * i / segments
            a1 = 2 * math.pi * (i + 1) / segments
            y0 = y + radius * math.cos(a0)
            z0 = z + radius * math.sin(a0)
            y1 = y + radius * math.cos(a1)
            z1 = z + radius * math.sin(a1)
            amid = 0.5 * (a0 + a1)
            n = (0.0, math.cos(amid), math.sin(amid))
            self.add_quad((x0, y0, z0), (x1, y0, z0), (x1, y1, z1), (x0, y1, z1), normal=n)
        # End caps
        n_left = (-1.0, 0.0, 0.0)
        n_right = (1.0, 0.0, 0.0)
        for i in range(segments):
            a0 = 2 * math.pi * i / segments
            a1 = 2 * math.pi * (i + 1) / segments
            y0 = y + radius * math.cos(a0)
            z0 = z + radius * math.sin(a0)
            y1 = y + radius * math.cos(a1)
            z1 = z + radius * math.sin(a1)
            self.add_triangle((x0, y, z), (x0, y1, z1), (x0, y0, z0), normal=n_left)
            self.add_triangle((x1, y, z), (x1, y0, z0), (x1, y1, z1), normal=n_right)

    def add_angled_beam(self, p0, p1, width, thickness):
        """
        Creates a clean 6-sided angled rectangular beam connecting 3D points p0 and p1
        with specified cross-sectional width (in X) and thickness (perpendicular to pitch in YZ).
        """
        dy = p1[1] - p0[1]
        dz = p1[2] - p0[2]
        L_yz = math.sqrt(dy * dy + dz * dz)
        if L_yz < 1e-6:
            return
        uy = dy / L_yz
        uz = dz / L_yz
        # Normal perpendicular to slope in YZ plane pointing upward/outward
        ny = -uz
        nz = uy
        hw = width / 2.0
        hh = thickness / 2.0

        v0 = (p0[0] - hw, p0[1] - ny * hh, p0[2] - nz * hh)
        v1 = (p0[0] + hw, p0[1] - ny * hh, p0[2] - nz * hh)
        v2 = (p0[0] + hw, p0[1] + ny * hh, p0[2] + nz * hh)
        v3 = (p0[0] - hw, p0[1] + ny * hh, p0[2] + nz * hh)

        v4 = (p1[0] - hw, p1[1] - ny * hh, p1[2] - nz * hh)
        v5 = (p1[0] + hw, p1[1] - ny * hh, p1[2] - nz * hh)
        v6 = (p1[0] + hw, p1[1] + ny * hh, p1[2] + nz * hh)
        v7 = (p1[0] - hw, p1[1] + ny * hh, p1[2] + nz * hh)

        # 6 quad faces with outward-facing normals
        self.add_quad(v0, v1, v5, v4)  # Bottom face
        self.add_quad(v3, v7, v6, v2)  # Top face
        self.add_quad(v0, v4, v7, v3)  # Left face
        self.add_quad(v1, v2, v6, v5)  # Right face
        self.add_quad(v0, v3, v2, v1)  # Start cap
        self.add_quad(v4, v5, v6, v7)  # End cap

    def add_pipe(self, p0, p1, radius, segments=8):
        """
        Creates a clean 3D cylindrical pipe/conduit/cable connecting 3D points p0 and p1.
        """
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        dz = p1[2] - p0[2]
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length < 1e-6:
            return
        w = (dx / length, dy / length, dz / length)
        if abs(w[0]) < 0.85:
            up = (1.0, 0.0, 0.0)
        else:
            up = (0.0, 1.0, 0.0)
        ux = up[1] * w[2] - up[2] * w[1]
        uy = up[2] * w[0] - up[0] * w[2]
        uz = up[0] * w[1] - up[1] * w[0]
        lu = math.sqrt(ux * ux + uy * uy + uz * uz)
        ux, uy, uz = ux / lu, uy / lu, uz / lu
        vx = w[1] * uz - w[2] * uy
        vy = w[2] * ux - w[0] * uz
        vz = w[0] * uy - w[1] * ux

        ring0 = []
        ring1 = []
        for i in range(segments):
            angle = 2 * math.pi * i / segments
            ca = math.cos(angle) * radius
            sa = math.sin(angle) * radius
            ox = ca * ux + sa * vx
            oy = ca * uy + sa * vy
            oz = ca * uz + sa * vz
            ring0.append((p0[0] + ox, p0[1] + oy, p0[2] + oz))
            ring1.append((p1[0] + ox, p1[1] + oy, p1[2] + oz))

        for i in range(segments):
            i_next = (i + 1) % segments
            self.add_quad(ring0[i], ring0[i_next], ring1[i_next], ring1[i])

    def add_cylinder_y(self, x, y0, y1, z, radius, segments=12):
        for i in range(segments):
            a0 = 2 * math.pi * i / segments
            a1 = 2 * math.pi * (i + 1) / segments
            x0 = x + radius * math.cos(a0)
            z0 = z + radius * math.sin(a0)
            x1 = x + radius * math.cos(a1)
            z1 = z + radius * math.sin(a1)
            amid = 0.5 * (a0 + a1)
            n = (math.cos(amid), 0.0, math.sin(amid))
            self.add_quad((x0, y0, z0), (x0, y1, z0), (x1, y1, z1), (x1, y0, z1), normal=n)
        # End caps
        n_front = (0.0, -1.0, 0.0)
        n_rear = (0.0, 1.0, 0.0)
        for i in range(segments):
            a0 = 2 * math.pi * i / segments
            a1 = 2 * math.pi * (i + 1) / segments
            x0 = x + radius * math.cos(a0)
            z0 = z + radius * math.sin(a0)
            x1 = x + radius * math.cos(a1)
            z1 = z + radius * math.sin(a1)
            self.add_triangle((x, y0, z), (x0, y0, z0), (x1, y0, z1), normal=n_front)
            self.add_triangle((x, y1, z), (x1, y1, z1), (x0, y1, z0), normal=n_rear)

    def add_sphere(self, cx, cy, cz, radius, rings=8, sectors=12):
        """Creates a smooth UV sphere centered at (cx, cy, cz)."""
        grid = []
        for r in range(rings + 1):
            theta = math.pi * r / rings
            sin_t = math.sin(theta)
            cos_t = math.cos(theta)
            row = []
            for s in range(sectors):
                phi = 2 * math.pi * s / sectors
                vx = cx + radius * sin_t * math.cos(phi)
                vy = cy + radius * sin_t * math.sin(phi)
                vz = cz + radius * cos_t
                row.append((vx, vy, vz))
            grid.append(row)

        for r in range(rings):
            for s in range(sectors):
                s_next = (s + 1) % sectors
                p0 = grid[r][s]
                p1 = grid[r + 1][s]
                p2 = grid[r + 1][s_next]
                p3 = grid[r][s_next]
                if r == 0:
                    self.add_triangle(p0, p1, p2)
                elif r == rings - 1:
                    self.add_triangle(p0, p1, p3)
                else:
                    self.add_quad(p0, p1, p2, p3)




FONT_3D = {
    'A': ['0110', '1001', '1111', '1001', '1001'],
    'B': ['1110', '1001', '1110', '1001', '1110'],
    'C': ['0111', '1000', '1000', '1000', '0111'],
    'D': ['1110', '1001', '1001', '1001', '1110'],
    'E': ['1111', '1000', '1110', '1000', '1111'],
    'F': ['1111', '1000', '1110', '1000', '1000'],
    'G': ['0111', '1000', '1011', '1001', '0111'],
    'H': ['1001', '1001', '1111', '1001', '1001'],
    'I': ['111', '010', '010', '010', '111'],
    'K': ['1001', '1010', '1100', '1010', '1001'],
    'L': ['1000', '1000', '1000', '1000', '1111'],
    'M': ['10001', '11011', '10101', '10001', '10001'],
    'N': ['1001', '1101', '1011', '1001', '1001'],
    'O': ['0110', '1001', '1001', '1001', '0110'],
    'P': ['1110', '1001', '1110', '1000', '1000'],
    'R': ['1110', '1001', '1110', '1010', '1001'],
    'S': ['0111', '1000', '0110', '0001', '1110'],
    'T': ['11111', '00100', '00100', '00100', '00100'],
    'U': ['1001', '1001', '1001', '1001', '0110'],
    'Y': ['10001', '01010', '00100', '00100', '00100'],
    '1': ['010', '110', '010', '010', '111'],
    '2': ['1110', '0001', '0110', '1000', '1111'],
    '3': ['1110', '0001', '0110', '0001', '1110'],
    '(': ['01', '10', '10', '10', '01'],
    ')': ['10', '01', '01', '01', '10'],
    '-': ['000', '000', '111', '000', '000'],
    ' ': ['00', '00', '00', '00', '00'],
}


class ModelBuilder:
    def __init__(self):
        self.groups = []

    def create_group(self, name, material_name):
        mg = MeshGroup(name, material_name)
        self.groups.append(mg)
        return mg

    def add_3d_text_plaque(self, plaque_grp, text_grp, text, cx, cy, z_base, plaque_w=1.20, plaque_d=0.28, scale=0.030, text_h=0.008):
        # Base slate plaque
        plaque_grp.add_box(cx - plaque_w/2.0, cy - plaque_d/2.0, z_base,
                           cx + plaque_w/2.0, cy + plaque_d/2.0, z_base + 0.007)
        # 3D Raised Lettering
        char_data = []
        total_w = 0.0
        for ch in text.upper():
            grid = FONT_3D.get(ch, FONT_3D[' '])
            cw = len(grid[0]) * scale + scale * 0.8
            char_data.append((grid, cw))
            total_w += cw
        
        start_x = cx - total_w / 2.0
        cur_x = start_x
        z_t0 = z_base + 0.007
        z_t1 = z_t0 + text_h
        for grid, cw in char_data:
            for r_idx, row in enumerate(grid):
                y0 = cy + (2.0 - r_idx) * scale
                y1 = y0 + scale * 0.90
                for c_idx, val in enumerate(row):
                    if val == '1':
                        x0 = cur_x + c_idx * scale
                        x1 = x0 + scale * 0.90
                        text_grp.add_box(x0, y0, z_t0, x1, y1, z_t1)
            cur_x += cw

    def build_blair_house(self):
        # EXACT BLUEPRINT DIMENSIONS (Taylor Wimpey Blair 4 TK)
        # Left-Hand Side Semi-Detached House:
        # Width (X) = 5.620 m (5620 mm)
        # Depth (Y) = 8.878 m (8878 mm)
        # Wall thicknesses:
        # Front wall: 0.302 m (302 mm)
        # Rear wall: 0.302 m (302 mm)
        # Left wall (Gable external wall): 0.301 m (301 mm)
        # Right wall (Separating / Party wall): 0.280 m
        
        W = 5.620
        D = 8.878
        t_front = 0.302
        t_rear = 0.302
        t_left = 0.301
        t_right = 0.280
        
        h_g = 2.45
        h_f1 = 2.70
        h_eaves = 5.10
        h_ridge = 7.20
        y_ridge = D / 2.0 # 4.439 m

        # -------------------------------------------------------------
        # 1. GROUND FLOOR FOUNDATION SLAB & FINISHES (STRICTLY FLUSH)
        # -------------------------------------------------------------
        g_slab = self.create_group("Ground_Floor_Slab", "M_Concrete")
        # Strictly within house footprint only: zero extension forward in front of house!
        g_slab.add_box(0.00, 0.00, -0.20, W, D, 0.00)

        # Ground Floor Finishes:
        # Lounge & Hall: Warm Oak Wood Laminate
        g_wood = self.create_group("Ground_Floor_Wood_Floor", "M_Flooring_Wood")
        g_wood.add_box(t_left, t_front, 0.00, 3.45, 4.40, 0.015)
        g_wood.add_box(3.45, t_front, 0.00, W-t_right, 4.40, 0.015)

        # Kitchen, Dining & Downstairs WC: Modern Porcelain Floor Tiles
        g_tiles = self.create_group("Ground_Floor_Tile_Floor", "M_Flooring_Tiles")
        g_tiles.add_box(t_left, 4.40, 0.00, 1.55, 6.25, 0.015) # Downstairs WC
        g_tiles.add_box(1.55, 4.40, 0.00, W-t_right, 6.25, 0.015) # Central lobby
        g_tiles.add_box(t_left, 6.25, 0.00, W-t_right, D-t_rear, 0.015) # Kitchen / Dining

        # -------------------------------------------------------------
        # 2. EXTERIOR WALLS (Left-Hand Semi-Detached)
        # -------------------------------------------------------------
        ext = self.create_group("Exterior_Walls", "M_Exterior_BrickRender")

        # --- FRONT WALL (Y = 0 to t_front, X = 0 to W, Z = 0 to 5.10) ---
        ext.add_box(0.0, 0.0, 0.0, 1.05, t_front, 0.85)
        ext.add_box(1.05, 0.0, 0.0, 2.86, t_front, 0.85)  # under lounge window
        ext.add_box(2.86, 0.0, 0.0, 4.05, t_front, h_g)   # pier between window and door
        ext.add_box(4.96, 0.0, 0.0, W - t_right, t_front, h_g)      # right pier (where EV charger mounts)
        ext.add_box(0.0, 0.0, 0.85, 1.05, t_front, h_g)   # left corner pier
        ext.add_box(1.05, 0.0, 2.20, 2.86, t_front, h_g)  # lintel above lounge window
        ext.add_box(4.05, 0.0, 2.15, 4.96, t_front, h_g)  # lintel above front door

        # Intermediate floor band on front wall:
        ext.add_box(0.0, 0.0, h_g, W - t_right, t_front, h_f1)

        # First floor front:
        ext.add_box(0.0, 0.0, h_f1, 1.25, t_front, h_eaves)
        ext.add_box(1.25, 0.0, h_f1, 2.70, t_front, 3.55) # under Bed 1 window
        ext.add_box(1.25, 0.0, 4.75, 2.70, t_front, h_eaves) # above Bed 1 window
        ext.add_box(2.70, 0.0, h_f1, 4.05, t_front, h_eaves) # middle pier
        ext.add_box(4.05, 0.0, h_f1, 4.96, t_front, 3.70) # under en-suite window W4
        ext.add_box(4.05, 0.0, 4.60, 4.96, t_front, h_eaves) # above en-suite window W4
        ext.add_box(4.96, 0.0, h_f1, W - t_right, t_front, h_eaves) # right corner pier

        # --- REAR WALL (Y = D-t_rear to D, X = 0 to W, Z = 0 to 5.10) ---
        ext.add_box(0.0, D-t_rear, 0.0, 0.90, D, h_g)      # left corner
        ext.add_box(0.90, D-t_rear, 0.0, 2.15, D, 1.00)    # below kitchen window W2
        ext.add_box(0.90, D-t_rear, 2.10, 2.15, D, h_g)    # above kitchen window W2
        ext.add_box(2.15, D-t_rear, 0.0, 3.30, D, h_g)    # middle pier
        ext.add_box(3.30, D-t_rear, 2.15, 4.80, D, h_g)    # above French doors
        ext.add_box(4.80, D-t_rear, 0.0, W - t_right, D, h_g)       # right corner pier

        # Intermediate floor band on rear wall:
        ext.add_box(0.0, D-t_rear, h_g, W - t_right, D, h_f1)

        # First floor rear:
        ext.add_box(0.0, D-t_rear, h_f1, 1.10, D, h_eaves)
        ext.add_box(1.10, D-t_rear, h_f1, 2.45, D, 3.55)   # below Bed 2 window W7
        ext.add_box(1.10, D-t_rear, 4.75, 2.45, D, h_eaves)# above Bed 2 window
        ext.add_box(2.45, D-t_rear, h_f1, 3.80, D, h_eaves)# middle pier
        ext.add_box(3.80, D-t_rear, h_f1, 4.75, D, 3.55)   # below Bed 3 window W8
        ext.add_box(3.80, D-t_rear, 4.75, 4.75, D, h_eaves)# above Bed 3 window
        ext.add_box(4.75, D-t_rear, h_f1, W - t_right, D, h_eaves)  # right corner pier

        # --- LEFT SIDE WALL (EXPOSED GABLE WALL) ---
        # Ground Floor: Window for Downstairs WC (Y in [5.10, 5.80], Z in [1.10, 1.95])
        ext.add_box(0.0, t_front, 0.0, t_left, 5.10, h_f1)
        ext.add_box(0.0, 5.10, 0.0, t_left, 5.80, 1.10)     # below WC window
        ext.add_box(0.0, 5.10, 1.95, t_left, 5.80, h_f1)    # lintel above WC window
        ext.add_box(0.0, 5.80, 0.0, t_left, D-t_rear, h_f1)

        # First Floor: Window W6-1040DP for Family Bathroom (Y in [4.40, 5.45], Z in [3.80, 4.70])
        ext.add_box(0.0, t_front, h_f1, t_left, 4.40, h_eaves)
        ext.add_box(0.0, 4.40, h_f1, t_left, 5.45, 3.80)     # below bathroom window W6
        ext.add_box(0.0, 4.40, 4.70, t_left, 5.45, h_eaves) # lintel above bathroom window W6
        ext.add_box(0.0, 5.45, h_f1, t_left, D-t_rear, h_eaves)

        # LEFT GABLE TRIANGLE (Exposed Gable at X = 0 to t_left, Z = 5.10 to 7.20m at Y = y_ridge)
        p_l_front_eave = (0.0, 0.0, h_eaves)
        p_l_rear_eave  = (0.0, D, h_eaves)
        p_l_ridge      = (0.0, y_ridge, h_ridge)
        ext.add_triangle(p_l_rear_eave, p_l_front_eave, p_l_ridge, normal=(-1, 0, 0))
        p_l_front_eave_in = (t_left, t_front, h_eaves)
        p_l_rear_eave_in  = (t_left, D-t_rear, h_eaves)
        p_l_ridge_in      = (t_left, y_ridge, h_ridge)
        ext.add_triangle(p_l_front_eave_in, p_l_rear_eave_in, p_l_ridge_in, normal=(1, 0, 0))

        # --- RIGHT SIDE WALL (SEPARATING / PARTY WALL - NORMAL STRAIGHT BRICK WALL) ---
        party_wall = self.create_group("Separating_Party_Wall", "M_Party_Wall")
        # Solid brick party wall spanning the full depth of the house (Y = 0.0 to D):
        party_wall.add_box(W - t_right, 0.0, 0.0, W, D, h_eaves)

        # Gable Triangle at right side (X in [W - t_right, W], Z from h_eaves to h_ridge at y_ridge)
        p_r_front_eave = (W, 0.0, h_eaves)
        p_r_rear_eave  = (W, D, h_eaves)
        p_r_ridge      = (W, y_ridge, h_ridge)
        # Outer Face at X = W (Normal pointing outwards +X):
        party_wall.add_triangle(p_r_front_eave, p_r_rear_eave, p_r_ridge, normal=(1, 0, 0))

        p_r_front_eave_in = (W - t_right, 0.0, h_eaves)
        p_r_rear_eave_in  = (W - t_right, D, h_eaves)
        p_r_ridge_in      = (W - t_right, y_ridge, h_ridge)
        # Inner Face at X = W - t_right (Normal pointing inwards -X):
        party_wall.add_triangle(p_r_rear_eave_in, p_r_front_eave_in, p_r_ridge_in, normal=(-1, 0, 0))

        # Top sloped roof pitch caps closing the gable triangle under the roof tiles:
        # Front pitch cap (sloping from front eave to ridge):
        party_wall.add_quad(p_r_front_eave_in, p_r_front_eave, p_r_ridge, p_r_ridge_in)
        # Rear pitch cap (sloping from ridge to rear eave):
        party_wall.add_quad(p_r_ridge_in, p_r_ridge, p_r_rear_eave, p_r_rear_eave_in)

        # -------------------------------------------------------------
        # 3. INTERIOR PARTITION WALLS - GROUND FLOOR
        # -------------------------------------------------------------
        int_g = self.create_group("Interior_Walls_Ground", "M_Interior_Walls")

        # 1. Hall / Lounge dividing wall (X = 3.40 to 3.50, Y in [t_front, 4.40])
        # Door D2 from Hall to Lounge: Y in [1.40, 2.24], Z in [0.00, 2.10]
        int_g.add_box(3.40, t_front, 0.0, 3.50, 1.40, h_g)
        int_g.add_box(3.40, 1.40, 2.10, 3.50, 2.24, h_g)
        int_g.add_box(3.40, 2.24, 0.0, 3.50, 4.40, h_g)

        # 2. Back of Lounge wall (Y = 4.35 to 4.45, X in [t_left, 3.50])
        int_g.add_box(t_left, 4.35, 0.0, 3.50, 4.45, h_g)

        # 3. Downstairs WC Partition (Longer along gable wall: Y = 4.45 to 6.25):
        # Inner wall facing central lobby (X = 1.45 to 1.55, Y in [4.45, 6.25]):
        # Door D3 into WC from lobby: Y in [4.60, 5.44], Z in [0.00, 2.10]
        int_g.add_box(1.45, 4.45, 0.0, 1.55, 4.60, h_g)
        int_g.add_box(1.45, 4.60, 2.10, 1.55, 5.44, h_g) # D3 lintel
        int_g.add_box(1.45, 5.44, 0.0, 1.55, 6.25, h_g)

        # 4. Transverse Partition separating Front/Middle from Rear Kitchen/Dining (Y = 6.20 to 6.30):
        # COMPLETELY FLUSH WALL! Downstairs WC does NOT jut into kitchen!
        int_g.add_box(t_left, 6.20, 0.0, 3.40, 6.30, h_g)
        # Doorway D4 from Lobby into Kitchen/Dining: X in [3.40, 4.25], Z in [0.00, 2.10]
        int_g.add_box(3.40, 6.20, 2.10, 4.25, 6.30, h_g)
        # Partition with under-stairs cupboard door in KITCHEN:
        int_g.add_box(4.25, 6.20, 0.0, 4.35, 6.30, h_g)
        int_g.add_box(4.35, 6.20, 2.05, 5.19, 6.30, h_g) # Cupboard door lintel
        int_g.add_box(5.19, 6.20, 0.0, W-t_right, 6.30, h_g)

        # 5. UNDER-STAIRS CUPBOARD IS BOXED IN (A wall that goes from the cupboard door right under stairs):
        # Wall extending from the kitchen cupboard door frame (X = 4.35 to 4.45) forward under stairs from Y = 6.20 to Y = 3.60:
        int_g.add_box(4.35, 3.60, 0.0, 4.45, 6.20, h_g)
        # Sloping boxed-in wall closing the cupboard right under the flight of stairs:
        int_g.add_box(4.35, 3.50, 0.0, W-t_right, 3.60, 1.60)
        # Hallway side is boxed in smoothly under stairs stringer (NO door in hallway):
        int_g.add_box(3.50, 4.35, 0.0, 4.35, 4.45, h_g)

        # 6. ENTRANCE HALL METER CUPBOARD (Thin floor-to-ceiling cupboard with full-size door facing living room door):
        # Positioned along the party wall inside the entrance hall (X = 4.90 to 5.34, Y = 0.40 to 1.35):
        # Front partition facing living room door D2 at X = 3.45:
        int_g.add_box(4.90, 0.40, 0.0, 5.00, 0.48, h_g)      # right jamb
        int_g.add_box(4.90, 0.48, 2.10, 5.00, 1.28, h_g)     # door lintel
        int_g.add_box(4.90, 1.28, 0.0, 5.00, 1.35, h_g)      # left jamb
        # Cupboard side return wall at Y = 1.35 closing cupboard towards the stairs:
        int_g.add_box(4.90, 1.35, 0.0, W-t_right, 1.45, h_g)
        # Cupboard front return against front wall:
        int_g.add_box(4.90, t_front, 0.0, W-t_right, 0.40, h_g)

        # Inside the Entrance Cupboard: Consumer Unit & Electric Meter Box
        meter_box = self.create_group("Entrance_Meter_Box", "M_PVC_White")
        meter_fittings = self.create_group("Entrance_Meter_Fittings", "M_Chrome")
        # Dual-RCD Consumer unit with breaker switches on party wall:
        meter_box.add_box(5.24, 0.65, 1.35, 5.33, 1.05, 1.65)
        meter_fittings.add_box(5.23, 0.70, 1.42, 5.24, 1.00, 1.55) # breaker switch strip
        # Smart Digital Electricity Meter:
        meter_box.add_box(5.24, 0.72, 0.95, 5.33, 0.98, 1.25)
        meter_fittings.add_box(5.23, 0.76, 1.10, 5.24, 0.94, 1.20) # digital LCD display
        # Heavy-duty 25mm meter tails (cables):
        meter_fittings.add_cylinder(5.26, 0.80, 0.78, 0.95, 0.015)
        meter_fittings.add_cylinder(5.26, 0.85, 0.78, 0.95, 0.015)

        # -------------------------------------------------------------
        # 4. FIRST FLOOR STRUCTURE & CEILING
        # -------------------------------------------------------------
        f_struct = self.create_group("First_Floor_Structure", "M_Wood_Structure")
        # Floor joists and deck covering the entire house except the stair flight opening
        f_struct.add_box(t_left, t_front, h_g, 3.45, 3.85, h_f1)           # Under Master Bed 1 front
        f_struct.add_box(3.45, 2.15, h_g, 4.35, 3.85, h_f1)               # Under Master Bed 1 wardrobe recess
        f_struct.add_box(3.45, t_front, h_g, W-t_right, 2.15, h_f1)        # Under En-Suite
        f_struct.add_box(t_left, 3.85, h_g, 4.45, 4.30, h_f1)             # Under Landing walkway
        f_struct.add_box(t_left, 4.30, h_g, W-t_right, D-t_rear, h_f1)    # Under rear Bedrooms 2 & 3

        # -------------------------------------------------------------
        # 4B. FIRST FLOOR BEDROOM CARPETS & LABELS
        # -------------------------------------------------------------
        # Dedicated carpet groups labeled by bedroom (STRICTLY LEVEL at Z = h_f1 to h_f1+0.015):
        c_landing = self.create_group("Landing_Carpet", "M_Flooring_Carpet")
        c_landing.add_box(2.14, 3.85, h_f1, 4.45, 6.05, h_f1+0.015)

        c_master = self.create_group("Carpet_Master_Bedroom_Largest", "M_Flooring_Carpet")
        c_master.add_box(t_left, t_front, h_f1, 3.45, 3.85, h_f1+0.015)
        c_master.add_box(3.45, 2.15, h_f1, 4.35, 3.85, h_f1+0.015) # Wardrobe recess

        c_guest = self.create_group("Carpet_Guestroom_Bed2_Second_Smallest", "M_Flooring_Carpet")
        c_guest.add_box(t_left, 6.05, h_f1, 3.20, D-t_rear, h_f1+0.015)

        c_nursery = self.create_group("Carpet_Nursery_Bed3_Smallest", "M_Flooring_Carpet")
        c_nursery.add_box(3.30, 6.05, h_f1, W-t_right, D-t_rear, h_f1+0.015)

        # 3D Raised Identification Plaques in each bedroom:
        lbl_base = self.create_group("Room_Labels_3D_Base", "M_Plaque")
        lbl_text = self.create_group("Room_Labels_3D_Text", "M_Plaque_Text")
        # 1. Largest Bedroom: Master Bedroom (front-left):
        self.add_3d_text_plaque(lbl_base, lbl_text, "MASTER BEDROOM (LARGEST)",
                                cx=1.90, cy=2.10, z_base=h_f1+0.015, plaque_w=1.45, plaque_d=0.28, scale=0.030)
        # 2. Second Smallest Bedroom: Guestroom (rear-left Bed 2):
        self.add_3d_text_plaque(lbl_base, lbl_text, "GUESTROOM (BED 2)",
                                cx=1.75, cy=7.30, z_base=h_f1+0.015, plaque_w=1.15, plaque_d=0.28, scale=0.030)
        # 3. Smallest Bedroom: Nursery (rear-right Bed 3):
        self.add_3d_text_plaque(lbl_base, lbl_text, "NURSERY (SMALLEST)",
                                cx=4.30, cy=7.30, z_base=h_f1+0.015, plaque_w=1.15, plaque_d=0.28, scale=0.030)

        # Tiles for Bathrooms (STRICTLY LEVEL at Z = h_f1 to h_f1+0.015):
        f_tiles = self.create_group("First_Floor_Tiles", "M_Flooring_Tiles")
        f_tiles.add_box(3.45, t_front, h_f1, W-t_right, 2.15, h_f1+0.015) # En-Suite
        f_tiles.add_box(t_left, 3.85, h_f1, 2.14, 6.05, h_f1+0.015)       # Family Bathroom

        # Top Ceiling
        ceiling = self.create_group("First_Floor_Ceiling", "M_Interior_Ceiling")
        ceiling.add_box(t_left, t_front, 5.00, W-t_right, D-t_rear, h_eaves)

        # -------------------------------------------------------------
        # 5. INTERIOR PARTITION WALLS - FIRST FLOOR (SOLID WALLS TO CEILING)
        # -------------------------------------------------------------
        int_f = self.create_group("Interior_Walls_First", "M_Interior_Walls")

        # 1. Master Bed 1 / En-Suite wall (X = 3.45 to 3.55, Y in [t_front, 2.15]):
        # Door D12 into En-Suite: Y in [1.25, 2.05], Z in [h_f1, h_f1+2.10]
        int_f.add_box(3.45, t_front, h_f1, 3.55, 1.25, h_eaves)
        int_f.add_box(3.45, 1.25, h_f1+2.10, 3.55, 2.05, h_eaves)
        int_f.add_box(3.45, 2.05, h_f1, 3.55, 2.15, h_eaves)

        # 2. Back wall of En-Suite (Y = 2.05 to 2.15, X in [3.45, W-t_right]) floor to ceiling:
        int_f.add_box(3.45, 2.05, h_f1, W-t_right, 2.15, h_eaves)

        # 3. SOLID WALL BESIDE BEDROOM (BLOCKS OFF THE DROP DOWN STAIRS! NO GIANT CUBE):
        # A. Solid partition wall separating Master Bed 1 from the stairwell:
        # Runs along X = 4.35 to 4.45 from Y = 2.15 to Y = 3.85, extending floor-to-ceiling (h_f1 to h_eaves)!
        int_f.add_box(4.35, 2.15, h_f1, 4.45, 3.85, h_eaves)

        # B. Transverse wall dividing Master Bed 1 from Landing (Y = 3.85 to 3.95, X in [t_left, 4.45]):
        # Door D8 into Master Bedroom: X in [2.30, 3.14], Z in [h_f1, h_f1+2.10]
        int_f.add_box(t_left, 3.85, h_f1, 2.30, 3.95, h_eaves)
        int_f.add_box(2.30, 3.85, h_f1+2.10, 3.14, 3.95, h_eaves) # D8 lintel
        int_f.add_box(3.14, 3.85, h_f1, 4.45, 3.95, h_eaves)

        # 4. Family Bathroom Inner Wall (Facing Landing Hallway at X = 2.09 to 2.19, Y in [3.85, 6.05]):
        # Door D9 opens directly from the Landing hallway:
        int_f.add_box(2.09, 3.85, h_f1, 2.19, 4.80, h_eaves)
        int_f.add_box(2.09, 4.80, h_f1+2.10, 2.19, 5.64, h_eaves) # D9 lintel
        int_f.add_box(2.09, 5.64, h_f1, 2.19, 6.05, h_eaves)

        # 5. Wall dividing Family Bathroom / Landing from Bedrooms 2 & 3 (Y = 6.00 to 6.10):
        int_f.add_box(t_left, 6.00, h_f1, 2.19, 6.10, h_eaves)
        int_f.add_box(2.19, 6.00, h_f1, 2.30, 6.10, h_eaves)
        int_f.add_box(2.30, 6.00, h_f1+2.10, 3.14, 6.10, h_eaves) # D10 lintel
        int_f.add_box(3.14, 6.00, h_f1, 3.40, 6.10, h_eaves)
        int_f.add_box(3.40, 6.00, h_f1+2.10, 4.24, 6.10, h_eaves) # D11 lintel
        int_f.add_box(4.24, 6.00, h_f1, W-t_right, 6.10, h_eaves)

        # 6. Dividing wall between Bedroom 2 and Bedroom 3 (X = 3.20 to 3.30, Y in [6.10, D-t_rear]):
        int_f.add_box(3.20, 6.10, h_f1, 3.30, D-t_rear, h_eaves)

        # -------------------------------------------------------------
        # 6. STAIRCASE & REALISTIC OPEN TIMBER BANISTER
        # -------------------------------------------------------------
        # 6. STAIRCASE & REALISTIC OPEN TIMBER BANISTER (CLEAN STRAIGHT FLIGHT)
        # -------------------------------------------------------------
        stairs = self.create_group("Staircase", "M_Staircase_Timber")
        num_risers = 13
        stair_x0 = 4.45
        stair_x1 = W - t_right
        stair_y0 = 1.60
        stair_y1 = 4.30
        run_step = (stair_y1 - stair_y0) / num_risers
        rise_step = (h_f1 - 0.0) / num_risers

        # 13 clean, plumb and level steps ascending straight to first floor landing:
        for i in range(num_risers):
            s_z0 = i * rise_step
            s_z1 = (i + 1) * rise_step
            sy0 = stair_y0 + i * run_step
            sy1 = stair_y0 + (i + 1) * run_step
            # Tread nosing and step
            stairs.add_box(stair_x0, sy0, s_z1 - 0.03, stair_x1, sy1 + 0.02, s_z1)
            stairs.add_box(stair_x0, sy0, s_z0, stair_x1, sy0 + 0.03, s_z1)

        # REALISTIC OPEN TIMBER BANISTER ON FLIGHT:
        # 1. Bottom newel post (at foot of stairs in ground floor hallway):
        # 80mm x 80mm post from floor Z = 0.0 to 1.02m, with pyramid cap to 1.06m
        stairs.add_box(stair_x0 - 0.04, stair_y0 - 0.04, 0.0, stair_x0 + 0.04, stair_y0 + 0.04, 1.02)
        stairs.add_box(stair_x0 - 0.048, stair_y0 - 0.048, 1.02, stair_x0 + 0.048, stair_y0 + 0.048, 1.06)

        # 2. Top flight newel post (at top of stairs on first floor landing):
        stairs.add_box(stair_x0 - 0.04, stair_y1 - 0.04, h_f1, stair_x0 + 0.04, stair_y1 + 0.04, h_f1 + 1.02)
        stairs.add_box(stair_x0 - 0.048, stair_y1 - 0.048, h_f1 + 1.02, stair_x0 + 0.048, stair_y1 + 0.048, h_f1 + 1.06)

        # 3. Sloping Handrail (True angled beam along the pitch connecting bottom and top newel posts):
        handrail_h = 0.90
        p_hr_start = (stair_x0, stair_y0, handrail_h)
        p_hr_end = (stair_x0, stair_y1, h_f1 + handrail_h)
        stairs.add_angled_beam(p_hr_start, p_hr_end, width=0.055, thickness=0.045)

        # 4. Sloping Base Rail (True angled beam along stringer):
        p_br_start = (stair_x0, stair_y0, 0.06)
        p_br_end = (stair_x0, stair_y1, h_f1 + 0.06)
        stairs.add_angled_beam(p_br_start, p_br_end, width=0.045, thickness=0.025)

        # 5. Clean baluster spindles (Square 30mm x 30mm upright timber spindles along flight):
        num_spindles = 14
        for s in range(num_spindles):
            t = (s + 0.5) / float(num_spindles)
            spy = stair_y0 + t * (stair_y1 - stair_y0)
            sp_pitch_z = t * h_f1
            sp_bottom_z = sp_pitch_z + 0.06 + 0.02
            sp_top_z = sp_pitch_z + handrail_h - 0.025
            stairs.add_box(stair_x0 - 0.015, spy - 0.015, sp_bottom_z, stair_x0 + 0.015, spy + 0.015, sp_top_z)

        # 6. Horizontal Landing Balustrade Guarding the Stairwell (between Bedroom 1 wall at Y=3.85 and top newel at Y=4.30):
        stairs.add_box(stair_x0 - 0.025, 3.85, h_f1 + 0.86, stair_x0 + 0.025, 4.30, h_f1 + 0.91) # horizontal handrail
        stairs.add_box(stair_x0 - 0.020, 3.85, h_f1 + 0.04, stair_x0 + 0.020, 4.30, h_f1 + 0.07) # horizontal baserail
        for ly in [3.96, 4.07, 4.18]:
            stairs.add_box(stair_x0 - 0.015, ly - 0.015, h_f1 + 0.07, stair_x0 + 0.015, ly + 0.015, h_f1 + 0.86)

        # -------------------------------------------------------------
        # 7. ROOF STRUCTURE & 5 SOLAR PANELS ON REAR ROOF
        # -------------------------------------------------------------
        roof = self.create_group("Roof_Main", "M_Roof_Tiles")
        overhang_x_left = 0.05  # Snugly aligned with external gable wall at X = 0.0m
        overhang_y = 0.22       # Standard 220mm UK eaves overhang for fascia & soffit box

        # Front Pitch (from Y = -overhang_y to y_ridge, sloping up Z = 5.00 to 7.20)
        p_f_bl = (-overhang_x_left, -overhang_y, h_eaves - 0.05)
        p_f_br = (W, -overhang_y, h_eaves - 0.05)
        p_f_tr = (W, y_ridge, h_ridge + 0.05)
        p_f_tl = (-overhang_x_left, y_ridge, h_ridge + 0.05)
        roof.add_quad(p_f_bl, p_f_br, p_f_tr, p_f_tl)
        roof.add_quad(p_f_tl, p_f_tr, (W, y_ridge, h_ridge), (-overhang_x_left, y_ridge, h_ridge))

        # Rear Pitch (from Y = y_ridge to D + overhang_y, sloping down Z = 7.20 to 5.00)
        p_r_tl = (-overhang_x_left, y_ridge, h_ridge + 0.05)
        p_r_tr = (W, y_ridge, h_ridge + 0.05)
        p_r_br = (W, D + overhang_y, h_eaves - 0.05)
        p_r_bl = (-overhang_x_left, D + overhang_y, h_eaves - 0.05)
        roof.add_quad(p_r_tl, p_r_tr, p_r_br, p_r_bl)

        # Ridge Tile Caps
        ridge = self.create_group("Roof_Ridge_Tiles", "M_Ridge_Tiles")
        ridge_w = 0.22
        ridge_h = 0.12
        ridge.add_box(-overhang_x_left - 0.02, y_ridge - ridge_w/2, h_ridge,
                      W, y_ridge + ridge_w/2, h_ridge + ridge_h)

        # Fascia Boards, Soffits & Verge Bargeboards
        fascia = self.create_group("Fascia_and_Soffits", "M_PVC_White")
        # 1. Horizontal eaves fascia boards along front and rear:
        fascia.add_box(-overhang_x_left - 0.02, -overhang_y - 0.025, h_eaves - 0.18, W, -overhang_y, h_eaves + 0.04)
        fascia.add_box(-overhang_x_left - 0.02, D + overhang_y, h_eaves - 0.18, W, D + overhang_y + 0.025, h_eaves + 0.04)

        # 2. Sloping pitched verge bargeboards along left gable (aligned to external gable wall):
        p_bb_front = (-overhang_x_left - 0.01, -overhang_y, h_eaves - 0.05)
        p_bb_ridge = (-overhang_x_left - 0.01, y_ridge, h_ridge + 0.05)
        p_bb_rear  = (-overhang_x_left - 0.01, D + overhang_y, h_eaves - 0.05)
        fascia.add_angled_beam(p_bb_front, p_bb_ridge, width=0.03, thickness=0.18)
        fascia.add_angled_beam(p_bb_ridge, p_bb_rear, width=0.03, thickness=0.18)

        # 3. Horizontal soffits closing eaves flush against front and rear external walls:
        fascia.add_box(-overhang_x_left, -overhang_y, h_eaves - 0.18, W, 0.00, h_eaves - 0.16)
        fascia.add_box(-overhang_x_left, D, h_eaves - 0.18, W, D + overhang_y, h_eaves - 0.16)

        # 4. Rainwater Gutters & Downpipes Connected to House Corners:
        gutters = self.create_group("Rainwater_Gutters", "M_Gutters")
        # Continuous horizontal eaves gutters:
        gutters.add_box(-overhang_x_left - 0.04, -overhang_y - 0.12, h_eaves - 0.06,
                        W + 0.02, -overhang_y - 0.02, h_eaves + 0.04)
        gutters.add_box(-overhang_x_left - 0.04, D + overhang_y + 0.02, h_eaves - 0.06,
                        W + 0.02, D + overhang_y + 0.12, h_eaves + 0.04)

        # Helper to construct downpipes with swan-neck offset bends connected directly to corners:
        def add_corner_downpipe(corner_x, corner_y, gutter_y, is_rear=False):
            # A. Gutter Outlet Drop:
            gutters.add_cylinder(corner_x, gutter_y, h_eaves - 0.12, h_eaves - 0.05, 0.040, segments=10)
            # B. Swan-Neck Offset Bend (connecting gutter outlet back to corner of external wall):
            p_gutter = (corner_x, gutter_y, h_eaves - 0.12)
            p_wall_top = (corner_x, corner_y, h_eaves - 0.32)
            gutters.add_pipe(p_gutter, p_wall_top, radius=0.036, segments=10)
            # C. Main Vertical Downpipe Running Straight Down House Corner:
            gutters.add_pipe(p_wall_top, (corner_x, corner_y, 0.14), radius=0.036, segments=10)
            # D. Pipe Mounting Brackets / Clips to Pebble Dash Wall every 1.2m:
            y_clip_dir = 1.0 if not is_rear else -1.0
            for bz in [1.0, 2.2, 3.4, 4.4]:
                gutters.add_box(corner_x - 0.050, corner_y - 0.015, bz - 0.015,
                                corner_x + 0.050, corner_y + y_clip_dir * 0.040, bz + 0.015)
            # E. Bottom Drain Shoe discharging into ground drainage gully:
            p_shoe_end = (corner_x, corner_y - y_clip_dir * 0.07, 0.04)
            gutters.add_pipe((corner_x, corner_y, 0.14), p_shoe_end, radius=0.036, segments=10)
            # Ground drainage gully grating:
            gutters.add_box(corner_x - 0.09, p_shoe_end[1] - 0.08, 0.00,
                            corner_x + 0.09, p_shoe_end[1] + 0.08, 0.025)

        # Corner 1: Front-Left Corner (Downpipe on front wall at left corner):
        add_corner_downpipe(corner_x=0.08, corner_y=-0.04, gutter_y=-overhang_y - 0.07, is_rear=False)
        # Corner 2: Front-Right Corner (Downpipe on front wall at right corner):
        add_corner_downpipe(corner_x=W - 0.08, corner_y=-0.04, gutter_y=-overhang_y - 0.07, is_rear=False)
        # Corner 3: Rear-Left Corner (Downpipe on rear wall at left corner):
        add_corner_downpipe(corner_x=0.08, corner_y=D + 0.04, gutter_y=D + overhang_y + 0.07, is_rear=True)
        # Corner 4: Rear-Right Corner (Downpipe on rear wall at right corner):
        add_corner_downpipe(corner_x=W - 0.08, corner_y=D + 0.04, gutter_y=D + overhang_y + 0.07, is_rear=True)

        # 5 SOLAR PANELS ON THE REAR ROOF PITCH:
        # User specification: Grid of 4, then on the top row an extra to make 5:
        # Top row of 3 panels, bottom row of 2 panels, where 6th panel would go is empty!
        solar = self.create_group("Roof_Solar_Panels", "M_Solar_Panels")
        panel_w = 1.05
        panel_gap_x = 0.08
        start_px = 1.15

        def get_rear_roof_z(y):
            t = (y - y_ridge) / ((D + overhang_y) - y_ridge)
            return (h_ridge + 0.05) - t * ((h_ridge + 0.05) - (h_eaves - 0.05))

        # Two rows along the roof pitch:
        # Top row (Row 0, closer to the ridge):
        # Bottom row (Row 1, below row 0, closer to eaves):
        row_y_spans = [
            (5.00, 6.60),  # Top row (Y = 5.00 to 6.60)
            (6.75, 8.35)   # Bottom row (Y = 6.75 to 8.35)
        ]

        # Active grid positions: (row, col)
        # Top row has 3 panels: cols 0, 1, 2
        # Bottom row has 2 panels: cols 0, 1
        # Position (row=1, col=2) is EMPTY (where 6th panel would go)
        panel_positions = [
            (0, 0), (0, 1), (0, 2),  # Top row: 3 panels
            (1, 0), (1, 1)           # Bottom row: 2 panels (col 2 empty)
        ]

        for row_idx, col_idx in panel_positions:
            y_r0, y_r1 = row_y_spans[row_idx]
            z_r0 = get_rear_roof_z(y_r0) + 0.05
            z_r1 = get_rear_roof_z(y_r1) + 0.05
            px0 = start_px + col_idx * (panel_w + panel_gap_x)
            px1 = px0 + panel_w

            # Top photovoltaic cell surface
            solar.add_quad((px0, y_r0, z_r0), (px1, y_r0, z_r0), (px1, y_r1, z_r1), (px0, y_r1, z_r1))
            # Aluminum frame sides (top, bottom, left, right)
            solar.add_quad((px0, y_r0, z_r0-0.04), (px1, y_r0, z_r0-0.04), (px1, y_r0, z_r0), (px0, y_r0, z_r0))
            solar.add_quad((px1, y_r1, z_r1-0.04), (px0, y_r1, z_r1-0.04), (px0, y_r1, z_r1), (px1, y_r1, z_r1))
            solar.add_quad((px0, y_r1, z_r1-0.04), (px0, y_r0, z_r0-0.04), (px0, y_r0, z_r0), (px0, y_r1, z_r1))
            solar.add_quad((px1, y_r0, z_r0-0.04), (px1, y_r1, z_r1-0.04), (px1, y_r1, z_r1), (px1, y_r0, z_r0))

        # -------------------------------------------------------------
        # 7B. SOLAR PV CABLING & SERVICE RUN (Roof into Meter Box)
        # -------------------------------------------------------------
        solar_cables = self.create_group("Solar_PV_Cabling", "M_EV_Cable")
        # 1. Weatherproof IP66 DC Isolator Switch Box mounted under solar array:
        z_iso = get_rear_roof_z(6.20) + 0.04
        solar_cables.add_box(4.00, 6.12, z_iso, 4.20, 6.28, z_iso + 0.12)
        # Rotary red/yellow switch knob:
        solar_cables.add_cylinder(4.10, 6.20, z_iso + 0.12, z_iso + 0.15, 0.025)

        # 2. String cables running from underside of panels into isolator switch:
        solar_cables.add_pipe((2.50, 5.80, get_rear_roof_z(5.80) + 0.02), (4.00, 6.20, z_iso + 0.06), radius=0.010)
        solar_cables.add_pipe((2.50, 7.50, get_rear_roof_z(7.50) + 0.02), (4.00, 6.20, z_iso + 0.06), radius=0.010)

        # 3. Weatherproof roof penetration cowl passing into loft:
        z_cowl = get_rear_roof_z(5.80) + 0.04
        solar_cables.add_box(4.08, 5.72, z_cowl, 4.22, 5.88, z_cowl + 0.10)
        solar_cables.add_pipe((4.10, 6.12, z_iso + 0.06), (4.15, 5.80, z_cowl + 0.05), radius=0.012)

        # 4. Conduit penetrating into loft space down to truss tie level (Z = 5.25m):
        solar_cables.add_pipe((4.15, 5.80, z_cowl), (4.15, 5.80, 5.25), radius=0.014)

        # 5. Heavy-duty loft conduit run along roof trusses forward to party wall service zone:
        solar_cables.add_pipe((4.15, 5.80, 5.25), (5.26, 1.10, 5.25), radius=0.014)

        # 6. Vertical conduit drop inside party wall chase from loft (Z = 5.25m) to entrance cupboard (Z = 2.45m):
        solar_cables.add_pipe((5.26, 1.10, 5.25), (5.26, 1.10, 2.45), radius=0.014)

        # 7. Inside Entrance Cupboard: Solar AC Inverter / Generation Unit & AC Isolator:
        # Solar generation box mounted on party wall above consumer unit:
        solar_cables.add_box(5.24, 0.65, 1.72, 5.33, 0.95, 2.02)
        # Solar AC rotary isolator switch box:
        solar_cables.add_box(5.24, 1.00, 1.72, 5.33, 1.15, 1.88)

        # DC cables dropping from cupboard ceiling into top of solar inverter:
        solar_cables.add_pipe((5.26, 1.10, 2.45), (5.28, 0.85, 2.02), radius=0.010)
        # AC interconnecting cable from solar inverter into AC isolator:
        solar_cables.add_pipe((5.28, 0.95, 1.80), (5.28, 1.00, 1.80), radius=0.009)
        # AC supply cable from solar isolator down into main consumer unit:
        solar_cables.add_pipe((5.28, 1.05, 1.72), (5.28, 0.95, 1.65), radius=0.009)

        # -------------------------------------------------------------
        # 8. EV CHARGER (Mounted on Front Wall to the RIGHT of Front Door)
        # -------------------------------------------------------------
        ev_charger = self.create_group("EV_Charger", "M_EV_Charger")
        ev_x0 = 5.08
        ev_x1 = 5.30
        ev_z0 = 1.05
        ev_z1 = 1.40
        ev_charger.add_box(ev_x0, -0.14, ev_z0, ev_x1, 0.00, ev_z1)
        ev_charger.add_cylinder((ev_x0 + ev_x1)/2, -0.15, ev_z0 + 0.08, ev_z0 + 0.18, 0.035)

        # -------------------------------------------------------------
        # 9. WINDOWS & GLASS
        # -------------------------------------------------------------
        win_frame = self.create_group("Windows_Frames", "M_PVC_White")
        win_glass = self.create_group("Windows_Glass", "M_Glass")

        def add_window_unit(x0, x1, y, z0, z1, orientation="front", mullions=1):
            fw = 0.06
            fd = 0.07
            sill_proj = 0.08
            sill_thick = 0.05

            if orientation == "front":
                win_frame.add_box(x0, y-fd/2, z0, x1, y+fd/2, z0+fw)
                win_frame.add_box(x0, y-fd/2, z1-fw, x1, y+fd/2, z1)
                win_frame.add_box(x0, y-fd/2, z0, x0+fw, y+fd/2, z1)
                win_frame.add_box(x1-fw, y-fd/2, z0, x1, y+fd/2, z1)
                win_frame.add_box(x0-0.05, y-fd/2-sill_proj, z0-sill_thick, x1+0.05, y+fd/2, z0)
                if mullions > 0:
                    span = (x1 - x0) / (mullions + 1)
                    for m in range(1, mullions + 1):
                        mx = x0 + m * span
                        win_frame.add_box(mx-fw/2, y-fd/2, z0, mx+fw/2, y+fd/2, z1)
                win_glass.add_box(x0+fw, y-0.005, z0+fw, x1-fw, y+0.005, z1-fw)

            elif orientation == "rear":
                win_frame.add_box(x0, y-fd/2, z0, x1, y+fd/2, z0+fw)
                win_frame.add_box(x0, y-fd/2, z1-fw, x1, y+fd/2, z1)
                win_frame.add_box(x0, y-fd/2, z0, x0+fw, y+fd/2, z1)
                win_frame.add_box(x1-fw, y-fd/2, z0, x1, y+fd/2, z1)
                win_frame.add_box(x0-0.05, y-fd/2, z0-sill_thick, x1+0.05, y+fd/2+sill_proj, z0)
                if mullions > 0:
                    span = (x1 - x0) / (mullions + 1)
                    for m in range(1, mullions + 1):
                        mx = x0 + m * span
                        win_frame.add_box(mx-fw/2, y-fd/2, z0, mx+fw/2, y+fd/2, z1)
                win_glass.add_box(x0+fw, y-0.005, z0+fw, x1-fw, y+0.005, z1-fw)

            elif orientation == "side_left":
                x = t_left / 2
                win_frame.add_box(x-fd/2, x0, z0, x+fd/2, x1, z0+fw)
                win_frame.add_box(x-fd/2, x0, z1-fw, x+fd/2, x1, z1)
                win_frame.add_box(x-fd/2, x0, z0, x+fd/2, x0+fw, z1)
                win_frame.add_box(x-fd/2, x1-fw, z0, x+fd/2, x1, z1)
                win_frame.add_box(x-fd/2-sill_proj, x0-0.05, z0-sill_thick, x+fd/2, x1+0.05, z0)
                win_glass.add_box(x-0.005, x0+fw, z0+fw, x+0.005, x1-fw, z1-fw)

        # 1. Front Lounge Window W1(TV)-1490DP (3-pane casement on Left)
        add_window_unit(1.05, 2.86, t_front/2, 0.85, 2.20, orientation="front", mullions=2)
        # 2. Front Bed 1 Window W5(TV)-1190DP (Master Bedroom on Left)
        add_window_unit(1.25, 2.70, t_front/2, 3.55, 4.75, orientation="front", mullions=1)
        # 3. Front En-Suite Window W4-1040DP (En-Suite on Right)
        add_window_unit(4.05, 4.96, t_front/2, 3.70, 4.60, orientation="front", mullions=0)

        # 4. Rear Kitchen Window W2-1040DP (Kitchen on Left)
        add_window_unit(0.90, 2.15, D-t_rear/2, 1.00, 2.10, orientation="rear", mullions=1)
        # 5. Rear Bed 2 Window W7(TV)-1190DP (Bedroom 2 on Left)
        add_window_unit(1.10, 2.45, D-t_rear/2, 3.55, 4.75, orientation="rear", mullions=1)
        # 6. Rear Bed 3 Window W8(TV)-1190DP (Bedroom 3 on Right)
        add_window_unit(3.80, 4.75, D-t_rear/2, 3.55, 4.75, orientation="rear", mullions=1)

        # 7. Left Side Downstairs WC Window (on Gable Wall at ground level):
        add_window_unit(5.10, 5.80, 0, 1.10, 1.95, orientation="side_left", mullions=0)
        # 8. Left Side Family Bathroom Window W6-1040DP (on Gable Wall at first floor):
        add_window_unit(4.40, 5.45, 0, 3.80, 4.70, orientation="side_left", mullions=0)

        # -------------------------------------------------------------
        # 10. EXTERIOR DOORS
        # -------------------------------------------------------------
        door_front = self.create_group("Front_Entrance_Door", "M_Front_Door")
        door_chrome = self.create_group("Exterior_Hardware_Chrome", "M_Chrome")
        
        # FRONT DOOR (on Right, NO CANOPY): X in [4.05, 4.96]
        f_dx0, f_dx1 = 4.05, 4.96
        f_fw = 0.07
        win_frame.add_box(f_dx0, 0.10, 0.0, f_dx1, 0.20, f_fw)
        win_frame.add_box(f_dx0, 0.10, 2.15-f_fw, f_dx1, 0.20, 2.15)
        win_frame.add_box(f_dx0, 0.10, 0.0, f_dx0+f_fw, 0.20, 2.15)
        win_frame.add_box(f_dx1-f_fw, 0.10, 0.0, f_dx1, 0.20, 2.15)
        door_front.add_box(f_dx0+f_fw, 0.12, 0.02, f_dx1-f_fw, 0.18, 2.15-f_fw)
        win_glass.add_box(f_dx0+0.55, 0.14, 0.60, f_dx0+0.75, 0.16, 1.80)
        door_chrome.add_box(f_dx0+0.18, 0.08, 0.90, f_dx0+0.21, 0.12, 1.30)
        door_chrome.add_box(f_dx0+0.40, 0.10, 0.70, f_dx0+0.70, 0.11, 0.78)

        # REAR FRENCH PATIO DOORS (Dining Area on Right): X in [3.30, 4.80]
        french_doors = self.create_group("Rear_French_Doors", "M_PVC_White")
        r_dx0, r_dx1 = 3.30, 4.80
        french_doors.add_box(r_dx0, D-0.20, 0.0, r_dx1, D-0.10, 0.05)
        french_doors.add_box(r_dx0, D-0.20, 2.15-0.06, r_dx1, D-0.10, 2.15)
        french_doors.add_box(r_dx0, D-0.20, 0.0, r_dx0+0.06, D-0.10, 2.15)
        french_doors.add_box(r_dx1-0.06, D-0.20, 0.0, r_dx1, D-0.10, 2.15)
        mid_x = (r_dx0 + r_dx1) / 2
        french_doors.add_box(mid_x-0.06, D-0.20, 0.0, mid_x+0.06, D-0.10, 2.15)
        win_glass.add_box(r_dx0+0.10, D-0.16, 0.15, mid_x-0.08, D-0.14, 2.05)
        win_glass.add_box(mid_x+0.08, D-0.16, 0.15, r_dx1-0.10, D-0.14, 2.05)
        door_chrome.add_box(mid_x-0.04, D-0.24, 1.00, mid_x-0.02, D-0.18, 1.08)
        door_chrome.add_box(mid_x+0.02, D-0.24, 1.00, mid_x+0.04, D-0.18, 1.08)

        # -------------------------------------------------------------
        # 11. INTERIOR DOORS & FRAMES (Snug 3.5mm Clearances to Walls)
        # -------------------------------------------------------------
        int_doors = self.create_group("Interior_Doors", "M_Interior_Doors")

        def add_interior_door(x_span, y_span, z_floor, h_open=2.10, axis="X"):
            """
            Builds a realistic UK internal door set:
            - Full timber lining/casing (22mm thick) filling the structural opening
            - Architrave surrounds (45mm wide x 12mm thick) on both sides of the wall
            - Door leaf (35mm thick) fitted with realistic 3.5mm perimeter clearance gap:
              * 3.5mm gap to left jamb
              * 3.5mm gap to right jamb
              * 3.5mm gap to head casing
              * 6.0mm threshold clearance to floor
            - Dual chrome lever handles with rose escutcheons
            """
            t_c = 0.022      # 22mm timber casing / lining thickness
            gap_s = 0.0035   # 3.5mm side clearance gap
            gap_t = 0.0035   # 3.5mm top head clearance gap
            gap_b = 0.0060   # 6.0mm floor clearance gap
            door_th = 0.035  # 35mm interior door leaf thickness
            w_arch = 0.045   # 45mm architrave width
            t_arch = 0.012   # 12mm architrave projection

            if axis == "X":
                x0, x1 = x_span
                y0, y1 = y_span
                ymid = 0.5 * (y0 + y1)
                z_top = z_floor + h_open

                # 1. Door Lining / Casing (fills structural wall opening):
                # Left jamb:
                int_doors.add_box(x0, y0, z_floor, x0 + t_c, y1, z_top)
                # Right jamb:
                int_doors.add_box(x1 - t_c, y0, z_floor, x1, y1, z_top)
                # Head casing:
                int_doors.add_box(x0 + t_c, y0, z_top - t_c, x1 - t_c, y1, z_top)

                # 2. Architrave Trims (both wall faces):
                for y_face, y_sign in [(y0, -1), (y1, 1)]:
                    ya0 = y_face if y_sign > 0 else y_face - t_arch
                    ya1 = y_face + t_arch if y_sign > 0 else y_face
                    # Left vertical trim:
                    int_doors.add_box(x0 - w_arch, ya0, z_floor, x0, ya1, z_top + w_arch)
                    # Right vertical trim:
                    int_doors.add_box(x1, ya0, z_floor, x1 + w_arch, ya1, z_top + w_arch)
                    # Top horizontal trim:
                    int_doors.add_box(x0 - w_arch, ya0, z_top, x1 + w_arch, ya1, z_top + w_arch)

                # 3. Door Leaf with slight 3.5mm gaps:
                dx0 = x0 + t_c + gap_s
                dx1 = x1 - t_c - gap_s
                dz0 = z_floor + gap_b
                dz1 = z_top - t_c - gap_t
                dy0 = ymid - door_th / 2.0
                dy1 = ymid + door_th / 2.0
                int_doors.add_box(dx0, dy0, dz0, dx1, dy1, dz1)

                # 4. Chrome Lever Handles & Escutcheons (both sides):
                hx = dx1 - 0.08
                hz = z_floor + 1.00
                door_chrome.add_cylinder(hx, dy0 - 0.005, hz - 0.025, hz + 0.025, 0.025)
                door_chrome.add_cylinder(hx, dy1 + 0.005, hz - 0.025, hz + 0.025, 0.025)
                door_chrome.add_box(hx - 0.015, dy0 - 0.06, hz - 0.010, hx + 0.09, dy0, hz + 0.010)
                door_chrome.add_box(hx - 0.015, dy1, hz - 0.010, hx + 0.09, dy1 + 0.06, hz + 0.010)

            else:  # axis == "Y"
                x0, x1 = x_span
                y0, y1 = y_span
                xmid = 0.5 * (x0 + x1)
                z_top = z_floor + h_open

                # 1. Door Lining / Casing:
                # Front jamb:
                int_doors.add_box(x0, y0, z_floor, x1, y0 + t_c, z_top)
                # Rear jamb:
                int_doors.add_box(x0, y1 - t_c, z_floor, x1, y1, z_top)
                # Head casing:
                int_doors.add_box(x0, y0 + t_c, z_top - t_c, x1, y1 - t_c, z_top)

                # 2. Architrave Trims (both wall faces):
                for x_face, x_sign in [(x0, -1), (x1, 1)]:
                    xa0 = x_face if x_sign > 0 else x_face - t_arch
                    xa1 = x_face + t_arch if x_sign > 0 else x_face
                    # Front vertical trim:
                    int_doors.add_box(xa0, y0 - w_arch, z_floor, xa1, y0, z_top + w_arch)
                    # Rear vertical trim:
                    int_doors.add_box(xa0, y1, z_floor, xa1, y1 + w_arch, z_top + w_arch)
                    # Top horizontal trim:
                    int_doors.add_box(xa0, y0 - w_arch, z_top, xa1, y1 + w_arch, z_top + w_arch)

                # 3. Door Leaf with slight 3.5mm gaps:
                dy0 = y0 + t_c + gap_s
                dy1 = y1 - t_c - gap_s
                dz0 = z_floor + gap_b
                dz1 = z_top - t_c - gap_t
                dx0 = xmid - door_th / 2.0
                dx1 = xmid + door_th / 2.0
                int_doors.add_box(dx0, dy0, dz0, dx1, dy1, dz1)

                # 4. Chrome Lever Handles & Escutcheons:
                hy = dy1 - 0.08
                hz = z_floor + 1.00
                door_chrome.add_cylinder(dx0 - 0.005, hy, hz - 0.025, hz + 0.025, 0.025)
                door_chrome.add_cylinder(dx1 + 0.005, hy, hz - 0.025, hz + 0.025, 0.025)
                door_chrome.add_box(dx0 - 0.06, hy - 0.015, hz - 0.010, dx0, hy + 0.09, hz + 0.010)
                door_chrome.add_box(dx1, hy - 0.015, hz - 0.010, dx1 + 0.06, hy + 0.09, hz + 0.010)

        # Ground Floor:
        # D2: Hall to Lounge (Opening Y in [1.40, 2.24], X in [3.40, 3.50])
        add_interior_door(x_span=(3.40, 3.50), y_span=(1.40, 2.24), z_floor=0.0, h_open=2.10, axis="Y")
        # D3: Hall Lobby to Downstairs WC (Opening Y in [4.60, 5.44], X in [1.45, 1.55])
        add_interior_door(x_span=(1.45, 1.55), y_span=(4.60, 5.44), z_floor=0.0, h_open=2.10, axis="Y")
        # D4: Hall Lobby to Kitchen/Dining (Opening X in [3.40, 4.25], Y in [6.20, 6.30])
        add_interior_door(x_span=(3.40, 4.25), y_span=(6.20, 6.30), z_floor=0.0, h_open=2.10, axis="X")
        # D_ST: Full Size Door in Kitchen to Cupboard Under Stairs (Opening X in [4.35, 5.19], Y in [6.20, 6.30])
        add_interior_door(x_span=(4.35, 5.19), y_span=(6.20, 6.30), z_floor=0.0, h_open=2.05, axis="X")
        # D_METER: Entrance Hall Cupboard Door (Opening Y in [0.48, 1.28], X in [4.90, 5.00])
        add_interior_door(x_span=(4.90, 5.00), y_span=(0.48, 1.28), z_floor=0.0, h_open=2.10, axis="Y")

        # First Floor:
        # D8: Landing to Master Bed 1 (Opening X in [2.30, 3.14], Y in [3.85, 3.95])
        add_interior_door(x_span=(2.30, 3.14), y_span=(3.85, 3.95), z_floor=h_f1, h_open=2.10, axis="X")
        # D12: Master Bed 1 to En-Suite (Opening Y in [1.25, 2.05], X in [3.45, 3.55])
        add_interior_door(x_span=(3.45, 3.55), y_span=(1.25, 2.05), z_floor=h_f1, h_open=2.10, axis="Y")
        # D9: Landing Hallway to Family Bathroom (Opening Y in [4.80, 5.64], X in [2.09, 2.19])
        add_interior_door(x_span=(2.09, 2.19), y_span=(4.80, 5.64), z_floor=h_f1, h_open=2.10, axis="Y")
        # D10: Landing to Bed 2 Guestroom (Opening X in [2.30, 3.14], Y in [6.00, 6.10])
        add_interior_door(x_span=(2.30, 3.14), y_span=(6.00, 6.10), z_floor=h_f1, h_open=2.10, axis="X")
        # D11: Landing to Bed 3 Nursery (Opening X in [3.40, 4.24], Y in [6.00, 6.10])
        add_interior_door(x_span=(3.40, 4.24), y_span=(6.00, 6.10), z_floor=h_f1, h_open=2.10, axis="X")

        # -------------------------------------------------------------
        # 12. FITTED KITCHEN (Clean Continuous L-Shape Counter)
        # -------------------------------------------------------------
        k_base = self.create_group("Kitchen_Cabinets", "M_Kitchen_Cabinets")
        k_top  = self.create_group("Kitchen_Worktop", "M_Kitchen_Worktop")
        k_sink = self.create_group("Kitchen_Sink_Hob", "M_Chrome")

        # Run 1: Along REAR WALL under Kitchen Window W2 (Curved non-square end unit):
        y_rear_wall = D - t_rear
        y_front_edge = y_rear_wall - 0.60
        r_end = 0.28   # 280mm radius curved radius corner
        x_end_base = 2.65
        xc_base = x_end_base - r_end
        yc_base = y_front_edge + r_end

        # Straight counter base run from gable wall to start of curve:
        k_base.add_box(t_left, y_front_edge, 0.0, xc_base, y_rear_wall, 0.87)
        # Rear rectangular portion of end unit behind the curve:
        k_base.add_box(xc_base, yc_base, 0.0, x_end_base, y_rear_wall, 0.87)

        # Smooth curved radius front-outer corner for base cabinet:
        segs = 8
        for i in range(segs):
            th0 = -math.pi/2.0 + (math.pi/2.0) * (i / float(segs))
            th1 = -math.pi/2.0 + (math.pi/2.0) * ((i + 1) / float(segs))
            p0 = (xc_base + r_end * math.cos(th0), yc_base + r_end * math.sin(th0))
            p1 = (xc_base + r_end * math.cos(th1), yc_base + r_end * math.sin(th1))
            # Curved vertical door/plinth panel
            k_base.add_quad((p0[0], p0[1], 0.0), (p1[0], p1[1], 0.0), (p1[0], p1[1], 0.87), (p0[0], p0[1], 0.87))
            # Top cap
            k_base.add_triangle((xc_base, yc_base, 0.87), (p0[0], p0[1], 0.87), (p1[0], p1[1], 0.87))
            # Bottom cap
            k_base.add_triangle((xc_base, yc_base, 0.0), (p1[0], p1[1], 0.0), (p0[0], p0[1], 0.0))

        # Matching Post-Formed Bullnose Worktop (with 20mm overhang and matching curved radius):
        r_top = r_end + 0.02
        y_front_top = y_front_edge - 0.02
        x_end_top = x_end_base + 0.02
        xc_top = xc_base
        yc_top = yc_base

        k_top.add_box(t_left, y_front_top, 0.87, xc_top, y_rear_wall, 0.91)
        k_top.add_box(xc_top, yc_top, 0.87, x_end_top, y_rear_wall, 0.91)

        for i in range(segs):
            th0 = -math.pi/2.0 + (math.pi/2.0) * (i / float(segs))
            th1 = -math.pi/2.0 + (math.pi/2.0) * ((i + 1) / float(segs))
            p0_top = (xc_top + r_top * math.cos(th0), yc_top + r_top * math.sin(th0))
            p1_top = (xc_top + r_top * math.cos(th1), yc_top + r_top * math.sin(th1))
            # Curved vertical bullnose worktop rim
            k_top.add_quad((p0_top[0], p0_top[1], 0.87), (p1_top[0], p1_top[1], 0.87),
                           (p1_top[0], p1_top[1], 0.91), (p0_top[0], p0_top[1], 0.91))
            # Top surface of worktop
            k_top.add_triangle((xc_top, yc_top, 0.91), (p0_top[0], p0_top[1], 0.91), (p1_top[0], p1_top[1], 0.91))
            # Underside of worktop
            k_top.add_triangle((xc_top, yc_top, 0.87), (p1_top[0], p1_top[1], 0.87), (p0_top[0], p0_top[1], 0.87))

        # Run 2: Return along LEFT GABLE WALL from partition to rear counter:
        k_base.add_box(t_left, 6.30, 0.0, t_left+0.60, D-t_rear-0.60, 0.87)
        k_top.add_box(t_left, 6.28, 0.87, t_left+0.62, D-t_rear-0.60, 0.91)

        # Stainless Steel Sink under Rear Window W2:
        k_sink.add_box(1.20, D-t_rear-0.52, 0.912, 1.85, D-t_rear-0.08, 0.92)
        k_sink.add_cylinder(1.52, D-t_rear-0.12, 0.92, 1.15, 0.02)

        # Ceramic Hob along Gable Wall Counter (Y in [6.85, 7.50], X in [t_left+0.05, t_left+0.55]):
        k_sink.add_box(t_left+0.07, 6.85, 0.915, t_left+0.53, 7.50, 0.925)
        # Recirculating Cooker Hood above Hob:
        k_sink.add_box(t_left+0.05, 6.85, 1.60, t_left+0.55, 7.50, 1.80)
        k_sink.add_box(t_left+0.18, 7.05, 1.80, t_left+0.42, 7.30, 2.25)

        # Wall Cabinets on Gable Wall (Y in [7.55, D-t_rear-0.60], X in [t_left, t_left+0.35], Z in [1.50, 2.15]):
        k_base.add_box(t_left, 7.55, 1.50, t_left+0.35, D-t_rear-0.60, 2.15)

        # -------------------------------------------------------------
        # 12B. COMBI BOILER (In Kitchen on Extractor Wall in Right Corner)
        # -------------------------------------------------------------
        boiler = self.create_group("Kitchen_Combi_Boiler", "M_PVC_White")
        boiler_chrome = self.create_group("Kitchen_Boiler_Fittings", "M_Chrome")
        boiler_pipes = self.create_group("Kitchen_Boiler_Pipes", "M_Copper_Pipes")
        
        # Mounted on left gable wall (X = t_left) in the right corner (Y = 8.12 to 8.52):
        b_x0 = t_left
        b_x1 = t_left + 0.33
        b_y0 = D - t_rear - 0.46
        b_y1 = D - t_rear - 0.06
        b_z0 = 1.35
        b_z1 = 2.10
        # White enamel boiler casing:
        boiler.add_box(b_x0, b_y0, b_z0, b_x1, b_y1, b_z1)
        # Beveled control fascia:
        boiler.add_box(b_x1, b_y0 + 0.04, b_z0 + 0.05, b_x1 + 0.015, b_y1 - 0.04, b_z0 + 0.28)
        # Digital LCD display & pressure gauge:
        boiler_chrome.add_box(b_x1 + 0.015, b_y0 + 0.08, b_z0 + 0.12, b_x1 + 0.02, b_y0 + 0.22, b_z0 + 0.22)
        boiler_chrome.add_cylinder(b_x1 + 0.016, b_y0 + 0.30, b_z0 + 0.14, b_z0 + 0.20, 0.025)
        # Vertical stainless flue duct exiting through ceiling:
        boiler_chrome.add_cylinder(b_x0 + 0.165, (b_y0 + b_y1)/2.0, b_z1, h_g, 0.055)
        # 5 Copper connection pipes descending towards worktop:
        for py in [b_y0 + 0.06, b_y0 + 0.13, b_y0 + 0.20, b_y0 + 0.27, b_y0 + 0.34]:
            boiler_pipes.add_cylinder(b_x0 + 0.15, py, 0.92, b_z0, 0.012)

        # -------------------------------------------------------------
        # 13. SANITARYWARE & BATHROOM FIXTURES
        # -------------------------------------------------------------
        sanitary = self.create_group("Sanitaryware", "M_Porcelain_White")

        # --- 1. DOWNSTAIRS WC (Longer along gable wall) ---
        # Toilet placed against left gable wall, directly under the window:
        toilet_wc_y = 5.45
        sanitary.add_box(t_left, toilet_wc_y - 0.20, 0.40, t_left + 0.20, toilet_wc_y + 0.20, 0.82) # cistern
        sanitary.add_box(t_left + 0.18, toilet_wc_y - 0.18, 0.0, t_left + 0.58, toilet_wc_y + 0.18, 0.42) # bowl
        # Sink against the living room dividing wall (Y = 4.45, X = 0.50 to 0.95):
        sanitary.add_box(0.50, 4.45, 0.80, 0.95, 4.75, 0.86)
        sanitary.add_box(0.65, 4.45, 0.0, 0.80, 4.65, 0.80)

        # --- 2. MASTER EN-SUITE ---
        # Shower is at the BACK of the en-suite (along the back wall Y = 1.25 to 2.05, X = 4.45 to W-t_right):
        sanitary.add_box(4.45, 1.25, h_f1, W-t_right, 2.05, h_f1+0.12) # shower tray
        win_glass.add_box(4.44, 1.25, h_f1+0.12, 4.46, 2.05, h_f1+1.95) # glass enclosure
        door_chrome.add_cylinder(4.90, 2.00, h_f1+0.90, h_f1+1.90, 0.02) # riser rail
        # Sink under front window W4:
        sanitary.add_box(4.15, t_front, h_f1+0.80, 4.65, t_front+0.35, h_f1+0.86)
        sanitary.add_box(4.32, t_front, h_f1, 4.48, t_front+0.25, h_f1+0.80)
        # Toilet beside the sink, far from the door (in front-right corner):
        sanitary.add_box(4.85, t_front, h_f1+0.40, 5.25, t_front+0.20, h_f1+0.82)
        sanitary.add_box(4.87, t_front+0.18, h_f1, 5.23, t_front+0.58, h_f1+0.42)

        # --- 3. UPSTAIRS FAMILY BATHROOM ---
        # Left side (front-facing wall of bathroom at Y = 3.98): Full bathtub!
        sanitary.add_box(t_left+0.05, 3.98, h_f1, 2.05, 4.68, h_f1+0.55) # bathtub
        # Sink under the window W6 (gable wall at X = t_left, Y = 4.80 to 5.20):
        sanitary.add_box(t_left, 4.80, h_f1+0.80, t_left+0.38, 5.25, h_f1+0.86)
        sanitary.add_box(t_left, 4.95, h_f1, t_left+0.28, 5.10, h_f1+0.80)
        # Toilet to the right of the sink (along gable wall towards Y = 5.75):
        sanitary.add_box(t_left, 5.55, h_f1+0.40, t_left+0.20, 5.95, h_f1+0.82)
        sanitary.add_box(t_left+0.18, 5.57, h_f1, t_left+0.58, 5.93, h_f1+0.42)

        # -------------------------------------------------------------
        # 14. DRIVEWAY & PEUGEOT e-2008 ELECTRIC SUV (PLUGGED INTO EV CHARGER)
        # -------------------------------------------------------------
        drive = self.create_group("Driveway", "M_Driveway")
        drive.add_box(2.70, -6.50, -0.15, 5.80, 0.00, 0.00)
        drive.add_box(2.60, -6.50, -0.15, 2.70, 0.00, 0.06) # curb

        car_body   = self.create_group("Car_Peugeot_e2008_Body", "M_Car_Paint")
        car_trim   = self.create_group("Car_Peugeot_e2008_Trim", "M_Car_Trim_Black")
        car_glass  = self.create_group("Car_Peugeot_e2008_Glass", "M_Car_Glass")
        car_wheels = self.create_group("Car_Peugeot_e2008_Wheels", "M_Car_Wheels")
        car_tires  = self.create_group("Car_Peugeot_e2008_Tires", "M_Car_Tires")
        car_lights = self.create_group("Car_Peugeot_e2008_Lights", "M_Car_Lights_Front")
        car_tails  = self.create_group("Car_Peugeot_e2008_Taillights", "M_Car_Lights_Rear")
        ev_cable   = self.create_group("EV_Charging_Cable", "M_EV_Cable")

        # Dimensions & Coordinates for Peugeot e-2008:
        # Centered at car_x = 4.30 on driveway
        # Parked reversed in: rear towards house (Y = -1.05), front towards road (Y = -5.35)
        car_x = 4.30
        car_y_center = -3.20
        car_len = 4.30
        car_w = 1.78
        hw = car_w / 2.0 # 0.89
        
        # 1. Wheels & Tires:
        # Wheel radius 0.33m, track width 1.54m, wheelbase 2.60m
        y_rear_axle = car_y_center + 1.30  # -1.90
        y_front_axle = car_y_center - 1.30 # -4.50
        wheel_r = 0.33
        for wy in [y_rear_axle, y_front_axle]:
            # Left wheel (outer edge at car_x + 0.88, inner edge at car_x + 0.66):
            car_tires.add_cylinder_x(car_x + 0.66, car_x + 0.88, wy, wheel_r, wheel_r)
            car_wheels.add_cylinder_x(car_x + 0.68, car_x + 0.89, wy, wheel_r, wheel_r * 0.72)
            car_wheels.add_cylinder_x(car_x + 0.87, car_x + 0.90, wy, wheel_r, 0.06)
            # Right wheel (outer edge at car_x - 0.88, inner edge at car_x - 0.66):
            car_tires.add_cylinder_x(car_x - 0.88, car_x - 0.66, wy, wheel_r, wheel_r)
            car_wheels.add_cylinder_x(car_x - 0.89, car_x - 0.68, wy, wheel_r, wheel_r * 0.72)
            car_wheels.add_cylinder_x(car_x - 0.90, car_x - 0.87, wy, wheel_r, 0.06)

        # 2. Lower Matte Black Protective Claddings:
        car_trim.add_box(car_x - hw + 0.08, -5.20, 0.17, car_x + hw - 0.08, -1.10, 0.34)
        # Wheel arch trims (black plastic flares over 4 wheels):
        car_trim.add_box(car_x + hw - 0.04, y_rear_axle - 0.42, 0.25, car_x + hw + 0.02, y_rear_axle + 0.42, 0.52)
        car_trim.add_box(car_x - hw - 0.02, y_rear_axle - 0.42, 0.25, car_x - hw + 0.04, y_rear_axle + 0.42, 0.52)
        car_trim.add_box(car_x + hw - 0.04, y_front_axle - 0.42, 0.25, car_x + hw + 0.02, y_front_axle + 0.42, 0.52)
        car_trim.add_box(car_x - hw - 0.02, y_front_axle - 0.42, 0.25, car_x - hw + 0.04, y_front_axle + 0.42, 0.52)
        # Rocker side sills between wheels:
        car_trim.add_box(car_x + hw - 0.03, y_front_axle + 0.42, 0.18, car_x + hw + 0.01, y_rear_axle - 0.42, 0.36)
        car_trim.add_box(car_x - hw - 0.01, y_front_axle + 0.42, 0.18, car_x - hw + 0.03, y_rear_axle - 0.42, 0.36)

        # 3. Main Sculpted Bodywork (Peugeot Vertigo Blue Metallic):
        car_body.add_box(car_x - hw + 0.03, -5.15, 0.34, car_x + hw - 0.03, -1.15, 0.88)
        # Sculpted side flanks with triangular door styling:
        car_body.add_box(car_x + hw - 0.05, -4.10, 0.45, car_x + hw, -1.75, 0.88)
        car_body.add_box(car_x - hw, -4.10, 0.45, car_x - hw + 0.05, -1.75, 0.88)
        # Sculpted Hood (sloping from nose to windshield base):
        car_body.add_quad(
            (car_x - hw + 0.10, -5.15, 0.72),
            (car_x + hw - 0.10, -5.15, 0.72),
            (car_x + hw - 0.08, -4.10, 0.92),
            (car_x - hw + 0.08, -4.10, 0.92)
        )
        car_body.add_box(car_x - hw + 0.08, -5.15, 0.70, car_x + hw - 0.08, -4.10, 0.85)

        # Front Bumper & Fascia:
        car_body.add_box(car_x - hw + 0.05, -5.35, 0.32, car_x + hw - 0.05, -5.15, 0.74)
        car_trim.add_box(car_x - 0.55, -5.36, 0.18, car_x + 0.55, -5.20, 0.32) # lower chin
        # Front Grille:
        car_trim.add_box(car_x - 0.45, -5.36, 0.40, car_x + 0.45, -5.33, 0.68)
        car_wheels.add_cylinder(car_x, -5.365, 0.52, 0.56, 0.04) # Peugeot crest

        # Rear Tailgate & Bumper:
        car_body.add_box(car_x - hw + 0.05, -1.15, 0.38, car_x + hw - 0.05, -1.02, 0.90)
        car_trim.add_box(car_x - hw + 0.04, -1.05, 0.20, car_x + hw - 0.04, -0.88, 0.55)
        # Tailgate horizontal gloss black bar connecting taillights:
        car_trim.add_box(car_x - 0.80, -1.04, 0.90, car_x + 0.80, -1.01, 1.02)
        car_wheels.add_box(car_x - 0.15, -1.005, 0.95, car_x + 0.15, -1.00, 0.98) # PEUGEOT chrome lettering

        # 4. Two-Tone Black Diamond Roof, Pillars & Spoiler:
        car_trim.add_box(car_x - 0.68, -3.40, 1.48, car_x + 0.68, -1.45, 1.54)
        car_trim.add_box(car_x - 0.70, -1.45, 1.51, car_x + 0.70, -1.10, 1.56) # rear roof spoiler
        # Pillars:
        car_trim.add_box(car_x - 0.74, -4.10, 0.92, car_x - 0.68, -3.40, 1.48) # A-pillar left
        car_trim.add_box(car_x + 0.68, -4.10, 0.92, car_x + 0.74, -3.40, 1.48) # A-pillar right
        car_trim.add_box(car_x - 0.76, -2.85, 0.88, car_x - 0.70, -2.75, 1.48) # B-pillar left
        car_trim.add_box(car_x + 0.70, -2.85, 0.88, car_x + 0.76, -2.75, 1.48) # B-pillar right
        car_trim.add_box(car_x - 0.76, -1.65, 0.88, car_x - 0.68, -1.42, 1.48) # C-pillar left
        car_trim.add_box(car_x + 0.68, -1.65, 0.88, car_x + 0.76, -1.42, 1.48) # C-pillar right

        # 5. Cabin Glass:
        # Windshield:
        car_glass.add_quad(
            (car_x - 0.68, -4.10, 0.93),
            (car_x + 0.68, -4.10, 0.93),
            (car_x + 0.66, -3.40, 1.47),
            (car_x - 0.66, -3.40, 1.47)
        )
        # Rear Windscreen:
        car_glass.add_quad(
            (car_x - 0.66, -1.42, 1.47),
            (car_x + 0.66, -1.42, 1.47),
            (car_x + 0.72, -1.13, 1.05),
            (car_x - 0.72, -1.13, 1.05)
        )
        # Side Windows:
        car_glass.add_box(car_x + 0.72, -3.35, 0.96, car_x + 0.74, -2.85, 1.44) # front left
        car_glass.add_box(car_x + 0.72, -2.75, 0.96, car_x + 0.74, -2.15, 1.44) # rear left
        car_glass.add_box(car_x + 0.70, -2.10, 1.02, car_x + 0.73, -1.60, 1.40) # quarter left
        car_glass.add_box(car_x - 0.74, -3.35, 0.96, car_x - 0.72, -2.85, 1.44) # front right
        car_glass.add_box(car_x - 0.74, -2.75, 0.96, car_x - 0.72, -2.15, 1.44) # rear right
        car_glass.add_box(car_x - 0.73, -2.10, 1.02, car_x - 0.70, -1.60, 1.40) # quarter right

        # 5B. Triangular Front Cowl & Windscreen Trim Panels (Peugeot signature styling):
        # Left side triangular cheater panel and A-pillar base:
        car_trim.add_triangle(
            (car_x - 0.70, -3.65, 1.25),
            (car_x - 0.88, -3.98, 0.90),
            (car_x - 0.68, -4.12, 0.93)
        )
        car_trim.add_triangle(
            (car_x - 0.78, -4.26, 0.88),
            (car_x - 0.88, -3.98, 0.90),
            (car_x - 0.68, -4.12, 0.93)
        )
        car_trim.add_triangle(
            (car_x - 0.88, -3.98, 0.90),
            (car_x - 0.88, -3.42, 0.98),
            (car_x - 0.74, -3.42, 1.12)
        )

        # Right side triangular cheater panel and A-pillar base:
        car_trim.add_triangle(
            (car_x + 0.68, -4.12, 0.93),
            (car_x + 0.88, -3.98, 0.90),
            (car_x + 0.70, -3.65, 1.25)
        )
        car_trim.add_triangle(
            (car_x + 0.68, -4.12, 0.93),
            (car_x + 0.88, -3.98, 0.90),
            (car_x + 0.78, -4.26, 0.88)
        )
        car_trim.add_triangle(
            (car_x + 0.74, -3.42, 1.12),
            (car_x + 0.88, -3.42, 0.98),
            (car_x + 0.88, -3.98, 0.90)
        )
        # Windscreen lower wiper cowl black trim bar:
        car_trim.add_quad(
            (car_x - 0.68, -4.22, 0.90),
            (car_x + 0.68, -4.22, 0.90),
            (car_x + 0.68, -4.10, 0.93),
            (car_x - 0.68, -4.10, 0.93)
        )

        # 6. Peugeot Signature Lighting:
        car_lights.add_box(car_x + 0.45, -5.30, 0.65, car_x + 0.78, -5.10, 0.76)
        car_lights.add_box(car_x - 0.78, -5.30, 0.65, car_x - 0.45, -5.10, 0.76)
        # Vertical 3-Claw LED DRL Fangs on bumper:
        car_lights.add_box(car_x + 0.76, -5.34, 0.35, car_x + 0.81, -5.25, 0.70)
        car_lights.add_box(car_x - 0.81, -5.34, 0.35, car_x - 0.76, -5.25, 0.70)
        # Rear 3-Claw LED Taillights:
        for c in range(3):
            claw_x_l = car_x + 0.50 + c * 0.08
            car_tails.add_box(claw_x_l, -1.025, 0.92, claw_x_l + 0.05, -1.01, 1.00)
            claw_x_r = car_x - 0.74 + c * 0.08
            car_tails.add_box(claw_x_r, -1.025, 0.92, claw_x_r + 0.05, -1.01, 1.00)

        # 7. Aerodynamic Wing Mirrors:
        car_trim.add_box(car_x + hw, -3.45, 0.98, car_x + hw + 0.18, -3.28, 1.10)
        car_trim.add_box(car_x - hw - 0.18, -3.45, 0.98, car_x - hw, -3.28, 1.10)

        # 8. EV Charging Connection:
        port_x = car_x + hw - 0.02 # 5.17
        port_y = -1.65
        port_z = 0.85
        car_trim.add_box(port_x - 0.05, port_y - 0.09, port_z - 0.09, port_x + 0.02, port_y + 0.09, port_z + 0.09)
        ev_cable.add_box(port_x + 0.01, port_y - 0.035, port_z - 0.035, port_x + 0.15, port_y + 0.035, port_z + 0.035)
        ev_cable.add_cylinder(port_x + 0.10, port_y, port_z - 0.10, port_z, 0.02)
        # Smooth Catenary EV Charging Cable from Wallbox to Car:
        p_wb = (5.19, -0.05, 1.12)
        p_car = (port_x + 0.10, port_y, port_z - 0.08)
        n_segs = 16
        prev_p = p_wb
        for s in range(1, n_segs + 1):
            t = s / float(n_segs)
            cx = p_wb[0] + t * (p_car[0] - p_wb[0])
            cy = p_wb[1] + t * (p_car[1] - p_wb[1])
            lin_z = p_wb[2] + t * (p_car[2] - p_wb[2])
            sag = 0.38 * 4.0 * t * (1.0 - t)
            cz = lin_z - sag
            curr_p = (cx, cy, cz)
            ev_cable.add_angled_beam(prev_p, curr_p, width=0.03, thickness=0.03)
            prev_p = curr_p

        # -------------------------------------------------------------
        # 16. OUTSIDE UTILITY PYLON & GRID SERVICE DROP TO METER BOX
        # -------------------------------------------------------------
        pylon = self.create_group("Utility_Pylon_Grid", "M_Utility_Pole")
        pylon_fittings = self.create_group("Utility_Pole_Fittings", "M_Chrome")
        pylon_insulators = self.create_group("Utility_Insulators", "M_Porcelain_White")
        pylon_warning = self.create_group("Utility_Warning_Plate", "M_Warning_Yellow")

        # 1. Roadside Distribution Pole / Pylon (X = 6.40m, Y = -7.20m, Z = 0.00m to 7.60m):
        px, py = 6.40, -7.20
        pylon.add_cylinder(px, py, 0.00, 7.60, 0.12, segments=16)
        # Galvanized weather cap on top:
        pylon_fittings.add_cylinder(px, py, 7.60, 7.68, 0.135, segments=16)

        # 2. Alternating Steel Climbing Rungs (Steps):
        for idx, rz in enumerate([2.2, 2.7, 3.2, 3.7, 4.2, 4.7, 5.2, 5.7, 6.2, 6.7]):
            sign = 1 if (idx % 2 == 0) else -1
            pylon_fittings.add_box(px + sign * 0.11, py - 0.02, rz, px + sign * 0.28, py + 0.02, rz + 0.03)

        # 3. Steel Distribution Cross-Arm at Z = 7.20m:
        pylon_fittings.add_box(px - 0.70, py - 0.05, 7.18, px + 0.70, py + 0.05, 7.25)
        # Steel diagonal support braces:
        pylon_fittings.add_pipe((px - 0.50, py, 7.18), (px, py, 6.60), radius=0.018)
        pylon_fittings.add_pipe((px + 0.50, py, 7.18), (px, py, 6.60), radius=0.018)

        # 4. Porcelain Bell Insulators on Cross-Arm:
        for ix in [px - 0.55, px, px + 0.55]:
            pylon_insulators.add_cylinder(ix, py, 7.25, 7.42, 0.065, segments=12)
            pylon_fittings.add_cylinder(ix, py, 7.42, 7.48, 0.015, segments=8)

        # 5. High-Voltage Overhead Distribution Lines (along street):
        ev_cable.add_pipe((px - 0.55, -11.0, 7.46), (px - 0.55, -7.20, 7.46), radius=0.012)
        ev_cable.add_pipe((px - 0.55, -7.20, 7.46), (px - 0.55, -3.5, 7.46), radius=0.012)
        ev_cable.add_pipe((px + 0.55, -11.0, 7.46), (px + 0.55, -7.20, 7.46), radius=0.012)
        ev_cable.add_pipe((px + 0.55, -7.20, 7.46), (px + 0.55, -3.5, 7.46), radius=0.012)

        # 6. Yellow 230/400V Hazard Warning Plate on Pole:
        pylon_warning.add_box(px - 0.12, py - 0.13, 2.20, px + 0.12, py - 0.12, 2.52)

        # 7. Pole-Mounted Distribution Cutout / Junction Box:
        pylon.add_box(px - 0.12, py + 0.11, 6.80, px + 0.12, py + 0.25, 7.10)

        # 8. Overhead Service Drop (Aerial Bundled Cable - ABC) with Catenary Sag:
        # Runs from pylon distribution box (6.40, -6.95, 6.95) to front house corner (5.32, 0.02, 5.00):
        p_pole = (px, py + 0.25, 6.95)
        p_house = (5.32, 0.02, 5.00)
        n_spans = 18
        prev_pt = p_pole
        for s in range(1, n_spans + 1):
            t = s / float(n_spans)
            cx = p_pole[0] + t * (p_house[0] - p_pole[0])
            cy = p_pole[1] + t * (p_house[1] - p_pole[1])
            cz_lin = p_pole[2] + t * (p_house[2] - p_pole[2])
            sag = 0.45 * 4.0 * t * (1.0 - t)
            cz = cz_lin - sag
            curr_pt = (cx, cy, cz)
            pylon.add_pipe(prev_pt, curr_pt, radius=0.016)
            prev_pt = curr_pt

        # 9. Galvanized Heavy-Duty House Wall Anchor Bracket:
        pylon_fittings.add_box(5.26, -0.02, 4.90, 5.38, 0.03, 5.08)

        # 10. External Heavy-Duty PVC Service Conduit running down Front Corner of House:
        pylon.add_pipe((5.32, -0.04, 5.00), (5.32, -0.04, 1.10), radius=0.022)
        # Wall saddles securing conduit to brickwork:
        for sz in [1.5, 2.3, 3.1, 3.9, 4.7]:
            pylon_fittings.add_box(5.28, -0.05, sz - 0.02, 5.36, -0.01, sz + 0.02)

        # 11. 90-Degree Through-Wall Inspection Elbow into Entrance Meter Cupboard:
        pylon.add_pipe((5.32, -0.04, 1.10), (5.26, 0.55, 1.10), radius=0.022)

        # 12. Inside Entrance Meter Cupboard: Main 100A Service Cutout Head:
        pylon.add_box(5.24, 0.52, 0.72, 5.33, 0.68, 0.95)
        # Sealed 100A fuse carrier:
        pylon_fittings.add_cylinder(5.26, 0.60, 0.76, 0.90, 0.025)

        # 13. Heavy-Duty 25mm² Double-Insulated Meter Tails from Cutout into Digital Smart Meter:
        pylon.add_pipe((5.27, 0.58, 0.95), (5.27, 0.74, 0.95), radius=0.012)
        pylon.add_pipe((5.29, 0.62, 0.95), (5.29, 0.78, 0.95), radius=0.012)
        # Main Earth Terminal (MET) with 16mm² earthing cable:
        pylon_fittings.add_box(5.24, 0.44, 0.85, 5.33, 0.50, 0.92)
        pylon.add_pipe((5.27, 0.50, 0.88), (5.27, 0.54, 0.88), radius=0.008)

        # -------------------------------------------------------------
        # 17. EXTERNAL BULK LPG GAS TANK & PIPES TO COMBI BOILER
        # -------------------------------------------------------------
        gas_tank = self.create_group("Gas_Storage_Tank", "M_Gas_Tank")
        gas_fittings = self.create_group("Gas_Tank_Fittings", "M_Chrome")
        gas_pipes = self.create_group("Gas_Supply_Pipes", "M_Gas_Pipe_Yellow")
        gas_warning = self.create_group("Gas_Warning_Sign", "M_Warning_Yellow")

        # 1. Reinforced Concrete Plinth Pad on Left Side Garden:
        gas_tank.add_box(-1.95, 7.15, 0.00, -0.65, 8.65, 0.10)

        # 2. Bulk LPG Horizontal Cylindrical Vessel (centered at X = -1.30m, Z = 0.58m):
        gt_x = -1.30
        gt_z = 0.58
        gt_r = 0.40
        gas_tank.add_cylinder_y(gt_x, 7.40, 8.40, gt_z, gt_r, segments=16)
        # Hemispherical dished end caps:
        gas_tank.add_sphere(gt_x, 7.40, gt_z, gt_r, rings=8, sectors=16)
        gas_tank.add_sphere(gt_x, 8.40, gt_z, gt_r, rings=8, sectors=16)

        # 3. Heavy-Duty Steel Saddle Cradle Legs:
        for cy in [7.60, 8.20]:
            gas_fittings.add_box(gt_x - 0.35, cy - 0.05, 0.10, gt_x + 0.35, cy + 0.05, 0.28)
            gas_fittings.add_box(gt_x - 0.38, cy - 0.06, 0.10, gt_x + 0.38, cy + 0.06, 0.13)

        # 4. Top Inspection Shroud / Dome Shroud:
        gas_tank.add_cylinder(gt_x, 7.90, gt_z + gt_r, gt_z + gt_r + 0.08, 0.15, segments=12)
        gas_tank.add_sphere(gt_x, 7.90, gt_z + gt_r + 0.08, 0.15, rings=6, sectors=12)

        # 5. Pressure Regulator & Contents Level Gauge:
        gas_fittings.add_cylinder(gt_x, 7.82, 1.00, 1.06, 0.035)
        gas_fittings.add_cylinder(gt_x, 8.00, 0.98, 1.05, 0.065)
        gas_pipes.add_box(gt_x - 0.08, 8.02, 1.05, gt_x + 0.08, 8.08, 1.09)

        # 6. High Visibility LPG Hazard Warning Sign:
        gas_warning.add_box(gt_x + gt_r - 0.01, 7.75, gt_z - 0.08, gt_x + gt_r + 0.005, 8.05, gt_z + 0.12)

        # 7. High-Visibility Yellow External Gas Supply Pipe Run to Boiler:
        # Drops from tank regulator down to plinth support level:
        gas_pipes.add_pipe((gt_x, 8.00, 0.98), (gt_x, 8.00, 0.22), radius=0.014)
        # Runs across garden towards the left gable wall:
        gas_pipes.add_pipe((gt_x, 8.00, 0.22), (-0.08, 8.32, 0.22), radius=0.014)
        # Rises up the external white pebble dash gable wall:
        gas_pipes.add_pipe((-0.08, 8.32, 0.22), (-0.08, 8.32, 1.05), radius=0.014)
        # Wall mounting pipe saddles:
        for pz in [0.45, 0.80]:
            gas_fittings.add_box(-0.11, 8.29, pz - 0.015, -0.05, 8.35, pz + 0.015)
        # External emergency gas isolation cock with yellow handle:
        gas_fittings.add_cylinder(-0.08, 8.32, 1.02, 1.08, 0.022)
        gas_pipes.add_box(-0.09, 8.32, 1.04, -0.03, 8.42, 1.07)
        # Passes through the 301mm external gable wall into the kitchen:
        gas_pipes.add_pipe((-0.08, 8.32, 1.05), (t_left, 8.32, 1.05), radius=0.014)
        # Inside the kitchen: connects up directly into the combi boiler copper gas manifold:
        boiler_pipes.add_pipe((t_left, 8.32, 1.05), (b_x0 + 0.15, 8.32, 1.05), radius=0.012)
        boiler_pipes.add_pipe((b_x0 + 0.15, 8.32, 1.05), (b_x0 + 0.15, 8.32, b_z0), radius=0.012)

        # -------------------------------------------------------------
        # 18. LANDSCAPE: GREEN LAWN, PATHS, FENCING, BUSHES & TREES
        # -------------------------------------------------------------
        grass = self.create_group("Landscape_Grass", "M_Grass_Green")
        paving = self.create_group("Landscape_Paving", "M_Paving_Stone")
        fence = self.create_group("Landscape_Fencing", "M_Wood_Structure")
        bushes = self.create_group("Landscape_Bushes", "M_Foliage_Green")
        bushes_dark = self.create_group("Landscape_Bushes_Dark", "M_Foliage_Dark")
        tree_trunk = self.create_group("Landscape_Trees_Trunk", "M_Tree_Bark")
        tree_foliage = self.create_group("Landscape_Trees_Foliage", "M_Tree_Leaves")

        # 1. Lush Green Lawn Terrain (Ground Plane with clean cutouts around driveway and house):
        # Front garden lawn (left of driveway):
        grass.add_box(-6.00, -7.50, -0.02, 3.20, -0.10, 0.01)
        # Side garden lawn (along left gable wall):
        grass.add_box(-6.00, -0.10, -0.02, -0.10, D + 0.10, 0.01)
        # Rear garden lawn (spacious private backyard):
        grass.add_box(-6.00, D + 0.10, -0.02, W + 0.10, 15.20, 0.01)
        # Front street roadside verge (right of driveway around utility pole):
        grass.add_box(5.80, -8.50, -0.02, 7.50, -0.20, 0.01)

        # 2. Paved Pathways & Dining Terrace:
        # Front Entrance Walkway:
        paving.add_box(3.20, -2.20, 0.01, 5.00, 0.05, 0.025)
        # Rear Patio Terrace (outside French patio doors):
        paving.add_box(2.80, D - 0.05, 0.01, 5.30, D + 2.40, 0.035)
        # Side stepping flagstones:
        for sy in [1.2, 2.3, 3.4, 4.5, 5.6, 6.7]:
            paving.add_box(-0.75, sy - 0.22, 0.01, -0.30, sy + 0.22, 0.025)

        # 3. Timber Perimeter Privacy Fencing (1.8m height):
        # Left boundary fence (X = -6.00m, Y in [0.0m, 15.20m]):
        fence.add_box(-6.04, 0.00, 0.05, -5.96, 15.20, 1.80)
        # Rear boundary fence (Y = 15.20m, X in [-6.00m, W]):
        fence.add_box(-6.00, 15.16, 0.05, W, 15.24, 1.80)
        # Party line rear divider fence (X = W = 5.62m, Y in [D, 15.20m]):
        fence.add_box(W - 0.04, D, 0.05, W + 0.04, 15.20, 1.80)
        # Fence posts every 1.8m:
        for py in [0.0, 1.8, 3.6, 5.4, 7.2, 9.0, 10.8, 12.6, 14.4, 15.2]:
            fence.add_box(-6.06, py - 0.05, 0.0, -5.94, py + 0.05, 1.88)
        for px in [-4.2, -2.4, -0.6, 1.2, 3.0, 4.8, W]:
            fence.add_box(px - 0.05, 15.14, 0.0, px + 0.05, 15.26, 1.88)

        # 4. Landscaped Shrubs & Bushes:
        # A. Front Boundary Hedge / Shrubs (neat row along front lawn border at Y = -7.20m):
        for bx in [-5.4, -4.6, -3.8, -3.0, -2.2, -1.4, -0.6, 0.2, 1.0, 1.8, 2.6]:
            bushes.add_sphere(bx, -7.20, 0.35, radius=0.38, rings=6, sectors=10)
            bushes_dark.add_sphere(bx + 0.12, -7.05, 0.28, radius=0.28, rings=5, sectors=8)

        # B. Front Lounge Foundation Shrubs (under window W1):
        for bx in [0.60, 1.30, 2.00, 2.70]:
            bushes.add_sphere(bx, -0.50, 0.28, radius=0.32, rings=6, sectors=10)
            bushes_dark.add_sphere(bx - 0.10, -0.42, 0.22, radius=0.24, rings=5, sectors=8)

        # C. Driveway Lawn Divider Hedge (along X = 3.10m):
        for by in [-6.4, -5.6, -4.8, -4.0, -3.2, -2.4]:
            bushes.add_sphere(3.10, by, 0.32, radius=0.34, rings=6, sectors=10)

        # D. Rear Garden Landscaped Shrub Beds (along patio and corner fences):
        for bx, by, br in [
            (-5.2, 2.0, 0.45), (-5.2, 4.0, 0.50), (-5.2, 6.0, 0.42),
            (-5.2, 10.5, 0.55), (-5.2, 12.0, 0.48),
            (2.2, D + 1.2, 0.42), (2.4, D + 2.0, 0.38),
            (5.4, D + 3.2, 0.46), (5.4, D + 4.5, 0.50),
            (-1.0, 14.4, 0.52), (0.5, 14.5, 0.48), (2.0, 14.4, 0.50)
        ]:
            bushes.add_sphere(bx, by, br * 0.90, radius=br, rings=6, sectors=10)
            bushes_dark.add_sphere(bx + 0.15, by - 0.12, br * 0.75, radius=br * 0.80, rings=5, sectors=8)

        # 5. Landscaped Trees:
        def add_garden_tree(tx, ty, trunk_h, crown_r, foliage_grp):
            # Tapered vertical trunk:
            tree_trunk.add_cylinder(tx, ty, 0.0, trunk_h, radius=0.10, segments=10)
            # 3 Natural spreading main limbs:
            for angle, l_len, l_z in [(0.3, 0.70, trunk_h + 0.6), (2.4, 0.75, trunk_h + 0.7), (4.5, 0.65, trunk_h + 0.55)]:
                lx = tx + l_len * math.cos(angle)
                ly = ty + l_len * math.sin(angle)
                tree_trunk.add_pipe((tx, ty, trunk_h * 0.85), (lx, ly, l_z), radius=0.045)
                # Foliage cluster at limb tip:
                foliage_grp.add_sphere(lx, ly, l_z + 0.20, radius=crown_r * 0.55, rings=6, sectors=10)
            # Central full foliage canopy:
            foliage_grp.add_sphere(tx, ty, trunk_h + crown_r * 0.50, radius=crown_r, rings=8, sectors=12)
            foliage_grp.add_sphere(tx + 0.20, ty - 0.15, trunk_h + crown_r * 0.75, radius=crown_r * 0.75, rings=7, sectors=10)
            foliage_grp.add_sphere(tx - 0.25, ty + 0.20, trunk_h + crown_r * 0.40, radius=crown_r * 0.80, rings=7, sectors=10)

        # Tree 1: Front Garden Ornamental Tree (Flowering / Silver Birch):
        add_garden_tree(tx=-3.20, ty=-4.50, trunk_h=2.40, crown_r=1.25, foliage_grp=tree_foliage)

        # Tree 2: Left Side Screening Tree:
        add_garden_tree(tx=-4.50, ty=3.50, trunk_h=2.60, crown_r=1.35, foliage_grp=tree_foliage)

        # Tree 3: Rear Garden Mature Feature Tree (Back Left):
        add_garden_tree(tx=-3.80, ty=13.00, trunk_h=3.20, crown_r=1.65, foliage_grp=tree_foliage)

        # Tree 4: Rear Garden Mature Feature Tree (Back Right):
        add_garden_tree(tx=3.60, ty=13.20, trunk_h=3.00, crown_r=1.55, foliage_grp=tree_foliage)

        print(f"Blair 4 TK Model built successfully with {len(self.groups)} distinct object groups.")

    def export_obj_mtl(self, obj_filename, mtl_filename):
        mtl_base = os.path.basename(mtl_filename)
        
        with open(mtl_filename, 'w') as f:
            f.write("# Material Library for Taylor Wimpey 'The Blair 4 TK' House\n")
            f.write("# Units: Metric (Meters), Scale: 1 unit = 1 meter\n\n")

            materials = {
                "M_Concrete": {"Kd": (0.60, 0.60, 0.60), "Ks": (0.1, 0.1, 0.1), "Ns": 10},
                "M_Exterior_BrickRender": {"Kd": (0.92, 0.92, 0.90), "Ks": (0.04, 0.04, 0.04), "Ns": 5},
                "M_Party_Wall": {"Kd": (0.92, 0.92, 0.90), "Ks": (0.04, 0.04, 0.04), "Ns": 5},
                "M_Roof_Tiles": {"Kd": (0.22, 0.23, 0.25), "Ks": (0.2, 0.2, 0.2), "Ns": 30},
                "M_Ridge_Tiles": {"Kd": (0.18, 0.19, 0.20), "Ks": (0.2, 0.2, 0.2), "Ns": 35},
                "M_Solar_Panels": {"Kd": (0.08, 0.10, 0.15), "Ks": (0.9, 0.9, 0.95), "Ns": 100},
                "M_EV_Charger": {"Kd": (0.18, 0.19, 0.20), "Ks": (0.4, 0.4, 0.4), "Ns": 50},
                "M_PVC_White": {"Kd": (0.94, 0.94, 0.94), "Ks": (0.4, 0.4, 0.4), "Ns": 60},
                "M_Glass": {"Kd": (0.80, 0.90, 0.95), "Ks": (0.9, 0.9, 0.9), "Ns": 120, "d": 0.28},
                "M_Front_Door": {"Kd": (0.14, 0.17, 0.20), "Ks": (0.3, 0.3, 0.3), "Ns": 40},
                "M_Gutters": {"Kd": (0.10, 0.10, 0.11), "Ks": (0.3, 0.3, 0.3), "Ns": 50},
                "M_Interior_Walls": {"Kd": (0.92, 0.91, 0.88), "Ks": (0.05, 0.05, 0.05), "Ns": 5},
                "M_Interior_Ceiling": {"Kd": (0.96, 0.96, 0.96), "Ks": (0.02, 0.02, 0.02), "Ns": 5},
                "M_Wood_Structure": {"Kd": (0.65, 0.52, 0.38), "Ks": (0.1, 0.1, 0.1), "Ns": 10},
                "M_Flooring_Wood": {"Kd": (0.68, 0.50, 0.34), "Ks": (0.3, 0.25, 0.2), "Ns": 40},
                "M_Flooring_Tiles": {"Kd": (0.76, 0.75, 0.73), "Ks": (0.3, 0.3, 0.3), "Ns": 50},
                "M_Flooring_Carpet": {"Kd": (0.72, 0.69, 0.64), "Ks": (0.05, 0.05, 0.05), "Ns": 5},
                "M_Interior_Doors": {"Kd": (0.91, 0.91, 0.90), "Ks": (0.2, 0.2, 0.2), "Ns": 30},
                "M_Staircase_Timber": {"Kd": (0.62, 0.46, 0.30), "Ks": (0.25, 0.2, 0.15), "Ns": 35},
                "M_Kitchen_Cabinets": {"Kd": (0.83, 0.83, 0.82), "Ks": (0.2, 0.2, 0.2), "Ns": 30},
                "M_Kitchen_Worktop": {"Kd": (0.88, 0.88, 0.87), "Ks": (0.4, 0.4, 0.4), "Ns": 70},
                "M_Kitchen_Sink_Hob": {"Kd": (0.80, 0.80, 0.80), "Ks": (0.9, 0.9, 0.9), "Ns": 90},
                "M_Chrome": {"Kd": (0.85, 0.85, 0.85), "Ks": (0.95, 0.95, 0.95), "Ns": 100},
                "M_Porcelain_White": {"Kd": (0.98, 0.98, 0.98), "Ks": (0.8, 0.8, 0.8), "Ns": 95},
                "M_Copper_Pipes": {"Kd": (0.85, 0.45, 0.25), "Ks": (0.90, 0.70, 0.50), "Ns": 90},
                "M_Driveway": {"Kd": (0.26, 0.26, 0.28), "Ks": (0.10, 0.10, 0.10), "Ns": 10},
                "M_Car_Paint": {"Kd": (0.05, 0.35, 0.88), "Ks": (0.90, 0.90, 0.95), "Ns": 120},
                "M_Car_Trim_Black": {"Kd": (0.08, 0.08, 0.08), "Ks": (0.50, 0.50, 0.50), "Ns": 40},
                "M_Car_Glass": {"Kd": (0.10, 0.12, 0.14), "Ks": (0.95, 0.95, 0.95), "Ns": 120, "d": 0.40},
                "M_Car_Wheels": {"Kd": (0.80, 0.80, 0.82), "Ks": (0.85, 0.85, 0.85), "Ns": 85},
                "M_Car_Tires": {"Kd": (0.12, 0.12, 0.12), "Ks": (0.10, 0.10, 0.10), "Ns": 15},
                "M_Car_Lights_Front": {"Kd": (0.95, 0.98, 1.00), "Ks": (0.95, 0.95, 0.95), "Ns": 100},
                "M_Car_Lights_Rear": {"Kd": (0.85, 0.05, 0.05), "Ks": (0.80, 0.20, 0.20), "Ns": 70},
                "M_EV_Cable": {"Kd": (0.08, 0.08, 0.08), "Ks": (0.20, 0.20, 0.20), "Ns": 25},
                "M_Utility_Pole": {"Kd": (0.28, 0.22, 0.16), "Ks": (0.05, 0.05, 0.05), "Ns": 10},
                "M_Warning_Yellow": {"Kd": (0.95, 0.80, 0.05), "Ks": (0.20, 0.20, 0.20), "Ns": 30},
                "M_Plaque": {"Kd": (0.18, 0.20, 0.22), "Ks": (0.30, 0.30, 0.30), "Ns": 30},
                "M_Plaque_Text": {"Kd": (0.95, 0.95, 0.95), "Ks": (0.50, 0.50, 0.50), "Ns": 50},
                "M_Gas_Tank": {"Kd": (0.88, 0.90, 0.88), "Ks": (0.50, 0.50, 0.50), "Ns": 40},
                "M_Gas_Pipe_Yellow": {"Kd": (0.92, 0.75, 0.08), "Ks": (0.25, 0.25, 0.25), "Ns": 25},
                "M_Grass_Green": {"Kd": (0.24, 0.52, 0.18), "Ks": (0.05, 0.05, 0.05), "Ns": 5},
                "M_Paving_Stone": {"Kd": (0.68, 0.67, 0.64), "Ks": (0.15, 0.15, 0.15), "Ns": 15},
                "M_Foliage_Green": {"Kd": (0.18, 0.44, 0.15), "Ks": (0.08, 0.08, 0.08), "Ns": 10},
                "M_Foliage_Dark": {"Kd": (0.12, 0.32, 0.10), "Ks": (0.08, 0.08, 0.08), "Ns": 10},
                "M_Tree_Bark": {"Kd": (0.35, 0.25, 0.18), "Ks": (0.05, 0.05, 0.05), "Ns": 5},
                "M_Tree_Leaves": {"Kd": (0.20, 0.48, 0.16), "Ks": (0.10, 0.10, 0.10), "Ns": 15}
            }

            for mat_name, props in materials.items():
                f.write(f"newmtl {mat_name}\n")
                f.write("Ka 1.000 1.000 1.000\n")
                f.write(f"Kd {props['Kd'][0]:.4f} {props['Kd'][1]:.4f} {props['Kd'][2]:.4f}\n")
                f.write(f"Ks {props['Ks'][0]:.4f} {props['Ks'][1]:.4f} {props['Ks'][2]:.4f}\n")
                f.write(f"Ns {props['Ns']:.1f}\n")
                f.write(f"d {props.get('d', 1.0):.2f}\n")
                f.write(f"illum {4 if 'd' in props else 2}\n\n")

        with open(obj_filename, 'w') as f:
            f.write("# Taylor Wimpey 'The Blair 4 TK' House - Blueprint Accurate Flipped Model\n")
            f.write(f"mtllib {mtl_base}\n\n")

            vert_offset = 1
            tex_offset = 1
            norm_offset = 1

            for grp in self.groups:
                if not grp.vertices or not grp.faces:
                    continue

                f.write(f"o {grp.name}\n")
                f.write(f"g {grp.name}\n")
                f.write(f"usemtl {grp.material_name}\n")
                f.write("s 1\n")

                for v in grp.vertices:
                    f.write(f"v {v[0]:.4f} {v[1]:.4f} {v[2]:.4f}\n")

                for vt in grp.texcoords:
                    f.write(f"vt {vt[0]:.4f} {vt[1]:.4f}\n")

                for vn in grp.normals:
                    f.write(f"vn {vn[0]:.4f} {vn[1]:.4f} {vn[2]:.4f}\n")

                for face in grp.faces:
                    f_str = " ".join([f"{idx + vert_offset}/{idx + tex_offset}/{idx + norm_offset}" for idx in face])
                    f.write(f"f {f_str}\n")

                vert_offset += len(grp.vertices)
                tex_offset += len(grp.texcoords)
                norm_offset += len(grp.normals)
                f.write("\n")

        print(f"Exported OBJ: {obj_filename}")
        print(f"Exported MTL: {mtl_filename}")

    def export_glb(self, glb_filename):
        materials_pbr = {
            "M_Concrete": {"baseColor": [0.60, 0.60, 0.60, 1.0], "roughness": 0.8, "metallic": 0.0},
            "M_Exterior_BrickRender": {"baseColor": [0.92, 0.92, 0.90, 1.0], "roughness": 0.92, "metallic": 0.0},
            "M_Party_Wall": {"baseColor": [0.92, 0.92, 0.90, 1.0], "roughness": 0.92, "metallic": 0.0},
            "M_Roof_Tiles": {"baseColor": [0.22, 0.23, 0.25, 1.0], "roughness": 0.75, "metallic": 0.0},
            "M_Ridge_Tiles": {"baseColor": [0.18, 0.19, 0.20, 1.0], "roughness": 0.70, "metallic": 0.0},
            "M_Solar_Panels": {"baseColor": [0.08, 0.10, 0.15, 1.0], "roughness": 0.15, "metallic": 0.85},
            "M_EV_Charger": {"baseColor": [0.18, 0.19, 0.20, 1.0], "roughness": 0.40, "metallic": 0.1},
            "M_PVC_White": {"baseColor": [0.94, 0.94, 0.94, 1.0], "roughness": 0.30, "metallic": 0.0},
            "M_Glass": {"baseColor": [0.80, 0.90, 0.95, 0.30], "roughness": 0.05, "metallic": 0.1, "alphaMode": "BLEND"},
            "M_Front_Door": {"baseColor": [0.14, 0.17, 0.20, 1.0], "roughness": 0.40, "metallic": 0.0},
            "M_Gutters": {"baseColor": [0.10, 0.10, 0.11, 1.0], "roughness": 0.35, "metallic": 0.1},
            "M_Interior_Walls": {"baseColor": [0.92, 0.91, 0.88, 1.0], "roughness": 0.90, "metallic": 0.0},
            "M_Interior_Ceiling": {"baseColor": [0.96, 0.96, 0.96, 1.0], "roughness": 0.95, "metallic": 0.0},
            "M_Wood_Structure": {"baseColor": [0.65, 0.52, 0.38, 1.0], "roughness": 0.70, "metallic": 0.0},
            "M_Flooring_Wood": {"baseColor": [0.68, 0.50, 0.34, 1.0], "roughness": 0.45, "metallic": 0.0},
            "M_Flooring_Tiles": {"baseColor": [0.76, 0.75, 0.73, 1.0], "roughness": 0.40, "metallic": 0.0},
            "M_Flooring_Carpet": {"baseColor": [0.72, 0.69, 0.64, 1.0], "roughness": 0.95, "metallic": 0.0},
            "M_Interior_Doors": {"baseColor": [0.91, 0.91, 0.90, 1.0], "roughness": 0.45, "metallic": 0.0},
            "M_Staircase_Timber": {"baseColor": [0.62, 0.46, 0.30, 1.0], "roughness": 0.50, "metallic": 0.0},
            "M_Kitchen_Cabinets": {"baseColor": [0.83, 0.83, 0.82, 1.0], "roughness": 0.40, "metallic": 0.0},
            "M_Kitchen_Worktop": {"baseColor": [0.88, 0.88, 0.87, 1.0], "roughness": 0.25, "metallic": 0.0},
            "M_Kitchen_Sink_Hob": {"baseColor": [0.80, 0.80, 0.80, 1.0], "roughness": 0.20, "metallic": 0.85},
            "M_Chrome": {"baseColor": [0.85, 0.85, 0.85, 1.0], "roughness": 0.15, "metallic": 0.95},
            "M_Porcelain_White": {"baseColor": [0.98, 0.98, 0.98, 1.0], "roughness": 0.10, "metallic": 0.0},
            "M_Copper_Pipes": {"baseColor": [0.85, 0.45, 0.25, 1.0], "roughness": 0.20, "metallic": 0.90},
            "M_Driveway": {"baseColor": [0.26, 0.26, 0.28, 1.0], "roughness": 0.90, "metallic": 0.0},
            "M_Car_Paint": {"baseColor": [0.05, 0.35, 0.88, 1.0], "roughness": 0.20, "metallic": 0.85},
            "M_Car_Trim_Black": {"baseColor": [0.08, 0.08, 0.08, 1.0], "roughness": 0.25, "metallic": 0.20},
            "M_Car_Glass": {"baseColor": [0.10, 0.12, 0.14, 0.40], "roughness": 0.05, "metallic": 0.10, "alphaMode": "BLEND"},
            "M_Car_Wheels": {"baseColor": [0.80, 0.80, 0.82, 1.0], "roughness": 0.25, "metallic": 0.85},
            "M_Car_Tires": {"baseColor": [0.12, 0.12, 0.12, 1.0], "roughness": 0.85, "metallic": 0.0},
            "M_Car_Lights_Front": {"baseColor": [0.95, 0.98, 1.00, 1.0], "roughness": 0.10, "metallic": 0.10},
            "M_Car_Lights_Rear": {"baseColor": [0.85, 0.05, 0.05, 1.0], "roughness": 0.20, "metallic": 0.10},
            "M_EV_Cable": {"baseColor": [0.08, 0.08, 0.08, 1.0], "roughness": 0.50, "metallic": 0.05},
            "M_Utility_Pole": {"baseColor": [0.28, 0.22, 0.16, 1.0], "roughness": 0.85, "metallic": 0.0},
            "M_Warning_Yellow": {"baseColor": [0.95, 0.80, 0.05, 1.0], "roughness": 0.50, "metallic": 0.10},
            "M_Plaque": {"baseColor": [0.18, 0.20, 0.22, 1.0], "roughness": 0.60, "metallic": 0.10},
            "M_Plaque_Text": {"baseColor": [0.95, 0.95, 0.95, 1.0], "roughness": 0.30, "metallic": 0.10},
            "M_Gas_Tank": {"baseColor": [0.88, 0.90, 0.88, 1.0], "roughness": 0.30, "metallic": 0.15},
            "M_Gas_Pipe_Yellow": {"baseColor": [0.92, 0.75, 0.08, 1.0], "roughness": 0.40, "metallic": 0.05},
            "M_Grass_Green": {"baseColor": [0.24, 0.52, 0.18, 1.0], "roughness": 0.90, "metallic": 0.0},
            "M_Paving_Stone": {"baseColor": [0.68, 0.67, 0.64, 1.0], "roughness": 0.80, "metallic": 0.0},
            "M_Foliage_Green": {"baseColor": [0.18, 0.44, 0.15, 1.0], "roughness": 0.85, "metallic": 0.0},
            "M_Foliage_Dark": {"baseColor": [0.12, 0.32, 0.10, 1.0], "roughness": 0.85, "metallic": 0.0},
            "M_Tree_Bark": {"baseColor": [0.35, 0.25, 0.18, 1.0], "roughness": 0.90, "metallic": 0.0},
            "M_Tree_Leaves": {"baseColor": [0.20, 0.48, 0.16, 1.0], "roughness": 0.80, "metallic": 0.0}
        }

        mat_list = []
        mat_map = {}
        for name, p in materials_pbr.items():
            mat_idx = len(mat_list)
            mat_map[name] = mat_idx
            m_def = {
                "name": name,
                "pbrMetallicRoughness": {
                    "baseColorFactor": p["baseColor"],
                    "metallicFactor": p["metallic"],
                    "roughnessFactor": p["roughness"]
                }
            }
            if "alphaMode" in p:
                m_def["alphaMode"] = p["alphaMode"]
            mat_list.append(m_def)

        bin_data = bytearray()
        buffer_views = []
        accessors = []
        meshes = []
        nodes = []

        for grp in self.groups:
            if not grp.vertices or not grp.faces:
                continue

            v_bytes = bytearray()
            n_bytes = bytearray()
            t_bytes = bytearray()
            min_pos = [1e9, 1e9, 1e9]
            max_pos = [-1e9, -1e9, -1e9]

            for v in grp.vertices:
                gx, gy, gz = v[0], v[2], -v[1]
                v_bytes.extend(struct.pack('<fff', gx, gy, gz))
                min_pos = [min(min_pos[0], gx), min(min_pos[1], gy), min(min_pos[2], gz)]
                max_pos = [max(max_pos[0], gx), max(max_pos[1], gy), max(max_pos[2], gz)]

            for n in grp.normals:
                gnx, gny, gnz = n[0], n[2], -n[1]
                n_bytes.extend(struct.pack('<fff', gnx, gny, gnz))

            for vt in grp.texcoords:
                t_bytes.extend(struct.pack('<ff', vt[0], 1.0 - vt[1]))

            i_bytes = bytearray()
            for face in grp.faces:
                i_bytes.extend(struct.pack('<III', face[0], face[1], face[2]))

            def align4(b):
                while len(b) % 4 != 0:
                    b.append(0)

            align4(bin_data)
            v_offset = len(bin_data)
            bin_data.extend(v_bytes)
            v_bv_idx = len(buffer_views)
            buffer_views.append({"buffer": 0, "byteOffset": v_offset, "byteLength": len(v_bytes), "target": 34962})
            v_acc_idx = len(accessors)
            accessors.append({"bufferView": v_bv_idx, "byteOffset": 0, "componentType": 5126, "count": len(grp.vertices), "type": "VEC3", "min": min_pos, "max": max_pos})

            align4(bin_data)
            n_offset = len(bin_data)
            bin_data.extend(n_bytes)
            n_bv_idx = len(buffer_views)
            buffer_views.append({"buffer": 0, "byteOffset": n_offset, "byteLength": len(n_bytes), "target": 34962})
            n_acc_idx = len(accessors)
            accessors.append({"bufferView": n_bv_idx, "byteOffset": 0, "componentType": 5126, "count": len(grp.normals), "type": "VEC3"})

            align4(bin_data)
            t_offset = len(bin_data)
            bin_data.extend(t_bytes)
            t_bv_idx = len(buffer_views)
            buffer_views.append({"buffer": 0, "byteOffset": t_offset, "byteLength": len(t_bytes), "target": 34962})
            t_acc_idx = len(accessors)
            accessors.append({"bufferView": t_bv_idx, "byteOffset": 0, "componentType": 5126, "count": len(grp.texcoords), "type": "VEC2"})

            align4(bin_data)
            i_offset = len(bin_data)
            bin_data.extend(i_bytes)
            i_bv_idx = len(buffer_views)
            buffer_views.append({"buffer": 0, "byteOffset": i_offset, "byteLength": len(i_bytes), "target": 34963})
            i_acc_idx = len(accessors)
            accessors.append({"bufferView": i_bv_idx, "byteOffset": 0, "componentType": 5125, "count": len(grp.faces) * 3, "type": "SCALAR"})

            mesh_idx = len(meshes)
            meshes.append({
                "name": grp.name,
                "primitives": [{
                    "attributes": {
                        "POSITION": v_acc_idx,
                        "NORMAL": n_acc_idx,
                        "TEXCOORD_0": t_acc_idx
                    },
                    "indices": i_acc_idx,
                    "material": mat_map.get(grp.material_name, 0)
                }]
            })

            node_idx = len(nodes)
            nodes.append({
                "name": grp.name,
                "mesh": mesh_idx
            })

        align4(bin_data)

        gltf_dict = {
            "asset": {"version": "2.0", "generator": "Taylor Wimpey Blair 4 TK (Left-Hand) 3D Generator"},
            "scene": 0,
            "scenes": [{"name": "Taylor_Wimpey_Blair_LeftHand", "nodes": list(range(len(nodes)))}],
            "nodes": nodes,
            "meshes": meshes,
            "materials": mat_list,
            "accessors": accessors,
            "bufferViews": buffer_views,
            "buffers": [{"byteLength": len(bin_data)}]
        }

        json_str = json.dumps(gltf_dict, separators=(',', ':'))
        while len(json_str) % 4 != 0:
            json_str += ' '
        json_bytes = json_str.encode('utf-8')

        total_length = 12 + (8 + len(json_bytes)) + (8 + len(bin_data))
        glb_header = struct.pack('<4sII', b'glTF', 2, total_length)
        chunk0_header = struct.pack('<II', len(json_bytes), 0x4E4F534A)
        chunk1_header = struct.pack('<II', len(bin_data), 0x004E4942)

        with open(glb_filename, 'wb') as f:
            f.write(glb_header)
            f.write(chunk0_header)
            f.write(json_bytes)
            f.write(chunk1_header)
            f.write(bin_data)

        print(f"Exported GLB: {glb_filename} ({len(bin_data) // 1024} KB)")


if __name__ == "__main__":
    builder = ModelBuilder()
    builder.build_blair_house()
    builder.export_obj_mtl("Taylor_Wimpey_Blair.obj", "Taylor_Wimpey_Blair.mtl")
    builder.export_glb("Taylor_Wimpey_Blair.glb")
