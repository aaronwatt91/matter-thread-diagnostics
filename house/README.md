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
6. **Clean Straight Staircase & Open Timber Banister (No Random Winders):**
   - 13 equal, plumb and level risers running straight up along the party wall from `Y = 1.60m` to arrive flush with the first floor landing at `Y = 4.30m, Z = 2.70m`.
   - All random, irregular winders and floating steps have been removed.
   - Features a bottom newel post, a top landing newel post, an angled timber handrail and baserail with 14 square baluster spindles, and a horizontal balustrade protecting the stairwell void along the landing.
7. **Giant Sealed Cube Removed & Solid Wall Beside Bedroom:**
   - The sealed, enclosed cube previously blocking the upper floor has been removed.
   - The space behind the en-suite is now an open, fitted wardrobe recess inside Master Bedroom 1 with matching carpet.
   - A full-height solid partition wall (`X = 4.45m, Y = 2.15m to 3.85m, Z = 2.70m to 5.10m`) safely encloses the bedroom and blocks any drop-off into the stairwell.
8. **Under-Stairs Cupboard Boxed In Under Stairs:**
   - Completely enclosed underneath the stairs, accessed via a full-size door in the kitchen (no door in hallway).
9. **Flush Foundation Slab & Level Floors:**
   - Ground floor finished flooring (wood in lounge/hall, tiles in kitchen/WC) is strictly level across all rooms at `Z = 0.015m`.
   - First floor finished flooring (bedroom carpets, bathroom tiles, landing) is strictly level across all rooms at `Z = 2.715m`.
   - Foundation slab is flush within house footprint with zero protruding cubes in the front garden.
10. **Sanitaryware & Layouts Compliant with Blueprints:**
    - Downstairs WC longer along gable wall, toilet under frosted window, sink on living room side, flush partition.
    - Master En-Suite with shower at back, sink under window W4, toilet beside sink far from door.
    - Family Bathroom with bath on left, sink under window W6, toilet to right, door opening from landing hallway.
11. **Separating Party Wall Straight and Planar Normal Brick Wall:**
    - The separating party wall (`Separating_Party_Wall`) is a single, perfectly straight, continuous vertical planar brick wall (`M_Party_Wall`) extending from the front of the house (`Y = 0.0m`) to the rear (`Y = 8.878m`), from foundation (`Z = 0.0m`) all the way up through the gable triangle to the roof ridge (`Z = 7.20m`).
12. **Curved Radius End on Kitchen Counter Unit:**
    - The end of the kitchen base cabinet and post-formed worktop facing the dining area features a smooth 280mm curved radius end unit with a matching rounded bullnose worktop overhang.
13. **Pitched Verge Bargeboards Fitting the Roof (No Flat Rectangle):**
    - The verge fascia boards on the left gable now follow the exact triangular pitch of the roof from front eave to ridge and down to rear eave, completely eliminating the old flat rectangular box.
14. **Solar PV Cabling from Roof to Meter Box:**
    - Weatherproof IP66 DC isolator switch mounted under the rear roof solar array (`Z = 6.36m`) with rotary switch knob.
    - Interconnecting DC string cables from solar panel junction boxes into isolator switch.
    - Weatherproof roof penetration cowl boot passing into the loft space.
    - Internal heavy-duty conduit running forward along the roof truss bottom chord to the party wall service zone.
    - Vertical conduit drop inside the party wall chase from loft (`Z = 5.25m`) into the ground floor entrance meter cupboard ceiling (`Z = 2.45m`).
    - Inside the meter cupboard: Solar AC Inverter / Generation Unit (`Z = 1.72m to 2.02m`) and Solar AC rotary isolator switch box (`Z = 1.72m to 1.88m`) mounted directly above the consumer unit, with twin DC cables entering the unit and AC supply connecting directly into a dedicated breaker in the consumer unit.
15. **Outside Utility Pylon & Grid Service Drop to Meter Box:**
    - Roadside wooden distribution pole / pylon (`X = 6.40m, Y = -7.20m, Z = 0.0m to 7.60m`) with galvanized weather cap.
    - Alternating steel climbing rungs up the side of the pole.
    - Steel distribution cross-arm at `Z = 7.20m` with diagonal steel support braces.
    - Three porcelain bell insulators on the cross-arm with overhead mains grid lines spanning along the road.
    - High-voltage yellow 230/400V hazard warning plate mounted at eye level.
    - Pole-mounted service fuse / junction box at `Z = 6.95m`.
    - Aerial Bundled Cable (ABC) service drop running in a realistic catenary sag curve across the driveway to a galvanized heavy-duty wall bracket at the front corner of the house (`Z = 5.00m`).
    - External heavy-duty black PVC service conduit running down the front house corner from `Z = 5.00m` to `Z = 1.10m` with pipe saddle clips.
    - 90-degree through-wall inspection elbow penetrating through the front wall into the entrance meter cupboard.
    - Inside the meter cupboard: 100A sealed main service cutout fuse head, 25mm² double-insulated meter tails (brown live and blue neutral) connecting into the smart digital meter, and Main Earth Terminal (MET) bonding.
16. **Snug Door Frames with 3.5mm Clearances to Walls:**
    - All interior door structural openings are fully framed with 22mm timber casing/linings and 45mm x 12mm architrave surround mouldings on both faces of the wall.
    - Door leaves are fitted inside the frame with realistic **3.5mm perimeter clearance gaps** (3.5mm gap to left jamb, 3.5mm gap to right jamb, 3.5mm gap to head casing, and 6.0mm threshold clearance to floor).
    - Fitted with dual chrome lever handles with circular rose escutcheons on both sides.
17. **Peugeot e-2008 Triangular Windscreen Trim Styling:**
    - Aerodynamic gloss black triangular trim panels (A-pillar base sails / quarter cheater panels) seamlessly linking the front windscreen lower corners to the bonnet crease and door mirror mounts on both sides.
    - Black ceramic wiper cowl lower windscreen accent trim.
18. **White Pebble Dash Finish on External Walls & Party Wall:**
    - The entire exterior facade of the house (`Exterior_Walls`) and the full separating party wall (`Separating_Party_Wall`) are rendered in authentic **White Pebble Dash** (Scottish wet dash / roughcast aggregate).
    - Formatted with a high-roughness mineral aggregate finish (`roughness: 0.92`, `Kd: [0.92, 0.92, 0.90]`) representing crisp off-white / light cream stone chippings.
19. **External Bulk LPG Gas Storage Tank & Service Pipework into Boiler:**
    - Positioned on the left side garden adjacent to the kitchen combi boiler (`X = -1.30m, Y = 7.15m to 8.65m`).
    - Mounted on a reinforced concrete plinth pad (`0.10m` thick).
    - Heavy-duty cylindrical LPG bulk vessel with hemispherical dished end caps, finished in weatherproof off-white protective enamel (`M_Gas_Tank`).
    - Dual steel saddle cradle legs securing the vessel to the plinth.
    - Top inspection bonnet dome shroud, pressure regulator, magnetic contents level dial, safety relief valve, and yellow hazard plaque: `"LPG - HIGHLY FLAMMABLE"`.
    - Continuous high-visibility yellow external gas supply pipe (`M_Gas_Pipe_Yellow`) running from the tank regulator across the plinth, rising up the gable wall with pipe saddles and an external emergency 1/4-turn isolation tap, passing through the 301mm gable wall sleeve directly into the kitchen combi boiler copper gas manifold.
20. **Complete Landscaped Garden, Green Grass, Bushes & Trees:**
    - **Lush Green Lawn (`Landscape_Grass`):** Expansive ground terrain covering the front garden, side passage, rear back garden, and roadside grass verge with crisp cutouts around the driveway and house footprint.
    - **Stone Paving & Patio (`Landscape_Paving`):** Front entrance flagstone walkway, side garden stepping stones to the gas tank, and a spacious rear dining patio terrace outside the French patio doors.
    - **Perimeter Fencing (`Landscape_Fencing`):** 1.8m timber featherboard privacy fencing enclosing the rear and side gardens with sturdy fence posts every 1.8m.
    - **Landscaped Shrubs & Bushes (`Landscape_Bushes`):** Neatly trimmed front garden boundary hedge rows, foundation flowering shrubs under the lounge front window, driveway border shrubs, and rear garden shrub beds.
    - **Mature Garden Trees (`Landscape_Trees`):** 4 realistic landscaped trees with natural branching trunks (`M_Tree_Bark`) and layered foliage canopies (`M_Tree_Leaves`):
      1. Front garden ornamental tree (flowering / silver birch at `X = -3.20m, Y = -4.50m`).
      2. Left side screening tree (`X = -4.50m, Y = 3.50m`).
      3. Rear back-left mature feature tree (`X = -3.80m, Y = 13.00m`).
      4. Rear back-right mature feature tree (`X = 3.60m, Y = 13.20m`).
21. **Roof Aligned to External Walls & Corner Downpipes:**
    - **Roof Aligned to External Walls:** Left gable roof verge overhang reduced to a snug 50mm dry-verge trim, perfectly aligning the roof and bargeboards with the external gable wall (`X = 0.0m`). Front and rear eaves soffit boxes close flush against the front and rear external walls (`Y = 0.0m` and `Y = D`), eliminating any detached gaps.
    - **Drain Pipes Connected to House Corners:** Rainwater downpipes are connected directly to all four corners of the house via swan-neck offset bends from the eaves gutters. Each downpipe runs vertically down the corner of the white pebble dash wall, clamped with mounting pipe saddles every 1.2m, and terminates in an angled drain shoe discharging into a ground drainage gully.

---

## 📁 Files Included

| File | Format | Description |
| :--- | :--- | :--- |
| `Taylor_Wimpey_Blair.glb` | **glTF 2.0 Binary** *(Recommended)* | Complete PBR materials, transparent tinted glass, and 63 distinct named object groups. |
| `Taylor_Wimpey_Blair.obj` | **Wavefront OBJ** | Universal mesh format with 63 individual named objects. |
| `Taylor_Wimpey_Blair.mtl` | **Material Library** | PBR materials including White Pebble Dash, Vertigo Blue metallic paint, lush grass, foliage, tree bark, LPG tank enamel, and warning signs. |
| `setup_blender_scene.py` | **Blender Python Script** | Automates loading the model into Blender, sorting objects into 6 Outliner collections, setting up daylight and 7 preset cameras (including front perspective, rear solar, Peugeot driveway charging, utility pylon & service drop, gas tank & boiler, landscape garden overview, and overhead bedroom cutaway). |

---

## 🚀 How to Open in Blender

1. Open **Blender**.
2. Press `X` then `Enter` to delete the default cube.
3. Drag and drop `Taylor_Wimpey_Blair.glb` directly from Finder into the Blender 3D viewport (or use `File > Import > glTF 2.0 (.glb)`).
4. In the top-right corner of the 3D viewport, click the **Material Preview** or **Rendered** sphere icon to view all colors and materials.
