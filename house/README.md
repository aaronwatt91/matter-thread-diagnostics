# Taylor Wimpey 'The Blair 4 TK' House - 3D Architectural Model
## Configuration: Flipped / Left-Hand Semi-Detached House (Exact Blueprint Scale)

Built directly from the official **Taylor Wimpey West Scotland `BLAIR 4 TK` (Scottish TK Range 2016)** architectural blueprint drawings (`BLR - 4 TK/02.01`), configured as the **Left-Hand Semi-Detached version** and tailored to your property.

---

## 🛠️ Complete Summary of Implemented Features

1. **Combi Boiler in the Kitchen:**
   - Mounted in the **right-hand corner of the gable counter wall** (where the cooker hood and hob are located).
   - Features a clean white enameled boiler casing, digital blue LCD control panel, round pressure gauge, vertical flue duct exiting through the ceiling, and a 5-pipe copper manifold underneath.
2. **Entrance Hall Meter Cupboard:**
   - A thin, floor-to-ceiling service cupboard (`Z = 0.0m to 2.45m`) positioned along the party wall inside the entrance hall.
   - Fitted with a **full-size interior door facing directly towards the living room door** (`X = 3.45m`).
   - Houses the **dual-RCD electrical consumer unit** (fuse box with breaker switches) and the **digital smart electricity meter** with 25mm meter tails.
3. **Peugeot e-2008 Electric SUV on Driveway (Plugged In):**
   - Positioned reversed into the private driveway in front of the house (`X = 4.30m, Y = -5.35m to -1.05m`).
   - Detailed model of the Peugeot e-2008 in **Vertigo Blue Metallic** with two-tone **Black Diamond roof**, sculpted bodywork, LED headlights, vertical "3-claw" DRL fangs, rear 3D claw taillights, 18" aero alloy wheels, tinted cabin glass, and rear roof spoiler.
   - The charging flap on the rear-left quarter panel is open with a Type 2 connector gun plugged in.
   - A realistic heavy-duty flexible EV charging cable swoops down in a catenary curve from the **wallbox EV charger** on the front wall and plugs directly into the car.
4. **Solar Panels on REAR Roof (3x2 Grid with 5 Panels):**
   - 5 photovoltaic solar panels arranged on the rear roof pitch:
     - **Top row (closer to ridge):** 3 panels.
     - **Bottom row (under top row):** 2 panels.
     - The **6th position on the bottom row is empty**, forming the exact requested layout.
5. **Bedrooms Labeled by Size:**
   - **Master Bedroom (Largest):** Front-left bedroom (`3.36m x 3.60m`), labeled as `Carpet_Master_Bedroom_Largest` with a 3D raised floor plaque: `"MASTER BEDROOM (LARGEST)"`.
   - **Guestroom (Second Smallest):** Rear-left bedroom 2 (`2.91m x 2.90m`), labeled as `Carpet_Guestroom_Bed2_Second_Smallest` with a 3D raised floor plaque: `"GUESTROOM (BED 2)"`.
   - **Nursery (Smallest):** Rear-right bedroom 3 (`2.23m x 2.58m`), labeled as `Carpet_Nursery_Bed3_Smallest` with a 3D raised floor plaque: `"NURSERY (SMALLEST)"`.
6. **Realistic Open Timber Banister on Stair Flight:**
   - Sloping angled extruded handrail and baserail with 14 evenly spaced vertical square baluster spindles (30mm x 30mm) along the rake.
7. **Boxed-In Top of Stairs with Solid Wall Beside Bedroom (No Drop-Off):**
   - Full floor-to-ceiling solid partition wall (`Z = 2.70m to 5.10m`) enclosing the stairwell beside Master Bedroom 1 with zero drop-off.
8. **Under-Stairs Cupboard Boxed In Under Stairs:**
   - Completely enclosed underneath the stairs, accessed via a full-size door in the kitchen (no door in hallway).
9. **Flush Foundation Slab:**
   - Zero protruding cubes or blocks in the front garden.
10. **Sanitaryware & Layouts Compliant with Blueprints:**
    - Downstairs WC longer along gable wall, toilet under frosted window, sink on living room side, flush partition.
    - Master En-Suite with shower at back, sink under window W4, toilet beside sink far from door.
    - Family Bathroom with bath on left, sink under window W6, toilet to right, door opening from landing hallway.

---

## 📁 Files Included

| File | Format | Description |
| :--- | :--- | :--- |
| `Taylor_Wimpey_Blair.glb` | **glTF 2.0 Binary** *(Recommended)* | Complete PBR materials, transparent tinted glass, and 47 distinct named object groups. |
| `Taylor_Wimpey_Blair.obj` | **Wavefront OBJ** | Universal mesh format with 47 individual named objects. |
| `Taylor_Wimpey_Blair.mtl` | **Material Library** | PBR materials including Vertigo Blue metallic paint, rubber tires, LED lighting, slate plaques, and copper piping. |
| `setup_blender_scene.py` | **Blender Python Script** | Automates loading the model into Blender, sorting objects into 5 Outliner collections, setting up daylight and 4 preset cameras (including front perspective, rear solar, Peugeot driveway charging, and overhead bedroom cutaway). |

---

## 🚀 How to Open in Blender

1. Open **Blender**.
2. Press `X` then `Enter` to delete the default cube.
3. Drag and drop `Taylor_Wimpey_Blair.glb` directly from Finder into the Blender 3D viewport (or use `File > Import > glTF 2.0 (.glb)`).
4. In the top-right corner of the 3D viewport, click the **Material Preview** or **Rendered** sphere icon to view all colors and materials.
