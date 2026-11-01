"""
Blender Automation Script for Taylor Wimpey 'The Blair 4 TK' House
Configuration: Flipped / Left-Hand Semi-Detached House (Blueprint Accurate)
----------------------------------------------------------------------------
Instructions:
1. Open Blender.
2. Switch to the 'Scripting' workspace (top tab in Blender).
3. Click 'Open', select this script ('setup_blender_scene.py').
4. Click 'Run Script' (or press Alt+P).
"""

import bpy
import os

def setup_blair_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

    script_dir = os.path.dirname(os.path.realpath(__file__)) if "__file__" in locals() else os.getcwd()
    glb_path = os.path.join(script_dir, "Taylor_Wimpey_Blair.glb")
    obj_path = os.path.join(script_dir, "Taylor_Wimpey_Blair.obj")

    if os.path.exists(glb_path):
        bpy.ops.import_scene.gltf(filepath=glb_path)
        print(f"Successfully imported {glb_path}")
    elif os.path.exists(obj_path):
        bpy.ops.wm.obj_import(filepath=obj_path)
        print(f"Successfully imported {obj_path}")
    else:
        print("Error: Could not locate Taylor_Wimpey_Blair.glb or .obj")
        return

    collections_map = {
        "01_Architecture_Exterior": [
            "Exterior_Walls", "Separating_Party_Wall", "Roof_Main", "Roof_Ridge_Tiles",
            "Fascia_and_Soffits", "Rainwater_Gutters", "Roof_Solar_Panels", "Solar_PV_Cabling",
            "Utility_Pylon_Grid", "Utility_Pole_Fittings", "Utility_Insulators", "Utility_Warning_Plate",
            "Gas_Storage_Tank", "Gas_Tank_Fittings", "Gas_Supply_Pipes", "Gas_Warning_Sign",
            "EV_Charger", "Windows_Frames", "Windows_Glass", "Front_Entrance_Door", "Rear_French_Doors",
            "Exterior_Hardware_Chrome", "Driveway"
        ],
        "02_Vehicle_Peugeot_e2008": [
            "Car_Peugeot_e2008_Body", "Car_Peugeot_e2008_Trim", "Car_Peugeot_e2008_Glass",
            "Car_Peugeot_e2008_Wheels", "Car_Peugeot_e2008_Tires", "Car_Peugeot_e2008_Lights",
            "Car_Peugeot_e2008_Taillights", "EV_Charging_Cable"
        ],
        "03_Interior_Ground_Floor": [
            "Ground_Floor_Slab", "Ground_Floor_Wood_Floor", "Ground_Floor_Tile_Floor",
            "Interior_Walls_Ground", "Staircase", "Entrance_Meter_Box", "Entrance_Meter_Fittings"
        ],
        "04_Interior_First_Floor": [
            "First_Floor_Structure", "Landing_Carpet",
            "Carpet_Master_Bedroom_Largest", "Carpet_Guestroom_Bed2_Second_Smallest", "Carpet_Nursery_Bed3_Smallest",
            "Room_Labels_3D_Base", "Room_Labels_3D_Text",
            "First_Floor_Tiles", "First_Floor_Ceiling", "Interior_Walls_First", "Interior_Doors"
        ],
        "05_Kitchen_and_Bathrooms": [
            "Kitchen_Cabinets", "Kitchen_Worktop", "Kitchen_Sink_Hob",
            "Kitchen_Combi_Boiler", "Kitchen_Boiler_Fittings", "Kitchen_Boiler_Pipes",
            "Sanitaryware"
        ],
        "06_Landscape_and_Garden": [
            "Landscape_Grass", "Landscape_Paving", "Landscape_Fencing",
            "Landscape_Bushes", "Landscape_Bushes_Dark",
            "Landscape_Trees_Trunk", "Landscape_Trees_Foliage"
        ]
    }

    scene_collection = bpy.context.scene.collection

    for col_name, obj_names in collections_map.items():
        col = bpy.data.collections.new(col_name)
        scene_collection.children.link(col)
        for obj_name in obj_names:
            obj = bpy.data.objects.get(obj_name)
            if obj:
                col.objects.link(obj)
                if obj.name in scene_collection.objects:
                    scene_collection.objects.unlink(obj)

    # Sunlight
    sun_data = bpy.data.lights.new(name="Sun_Daylight", type='SUN')
    sun_data.energy = 4.0
    sun_data.color = (1.0, 0.96, 0.90)
    sun_data.angle = 0.015
    sun_obj = bpy.data.objects.new(name="Sun_Daylight", object_data=sun_data)
    sun_obj.rotation_euler = (0.785, 0.25, -0.65)
    scene_collection.objects.link(sun_obj)

    # Preset Cameras
    cam_front_data = bpy.data.cameras.new(name="Cam_Front_Perspective")
    cam_front_data.lens = 30
    cam_front_obj = bpy.data.objects.new(name="Camera_Exterior_Front", object_data=cam_front_data)
    cam_front_obj.location = (-6.5, -9.0, 4.5)
    cam_front_obj.rotation_euler = (1.18, 0.0, -0.60)
    scene_collection.objects.link(cam_front_obj)

    cam_rear_data = bpy.data.cameras.new(name="Cam_Rear_Solar_Panels")
    cam_rear_data.lens = 30
    cam_rear_obj = bpy.data.objects.new(name="Camera_Exterior_Rear", object_data=cam_rear_data)
    cam_rear_obj.location = (-5.5, 17.0, 6.0)
    cam_rear_obj.rotation_euler = (1.20, 0.0, -2.50)
    scene_collection.objects.link(cam_rear_obj)

    cam_car_data = bpy.data.cameras.new(name="Cam_Peugeot_e2008_Charging")
    cam_car_data.lens = 35
    cam_car_obj = bpy.data.objects.new(name="Camera_Peugeot_Driveway", object_data=cam_car_data)
    cam_car_obj.location = (8.5, -6.5, 2.8)
    cam_car_obj.rotation_euler = (1.25, 0.0, 1.05)
    scene_collection.objects.link(cam_car_obj)

    cam_pylon_data = bpy.data.cameras.new(name="Cam_Utility_Pylon_Grid")
    cam_pylon_data.lens = 28
    cam_pylon_obj = bpy.data.objects.new(name="Camera_Utility_Pylon_and_Service_Drop", object_data=cam_pylon_data)
    cam_pylon_obj.location = (11.0, -12.0, 5.5)
    cam_pylon_obj.rotation_euler = (1.22, 0.0, 0.85)
    scene_collection.objects.link(cam_pylon_obj)

    cam_bed_data = bpy.data.cameras.new(name="Cam_Bedrooms_Overhead")
    cam_bed_data.lens = 28
    cam_bed_obj = bpy.data.objects.new(name="Camera_First_Floor_Bedrooms", object_data=cam_bed_data)
    cam_bed_obj.location = (2.81, 4.44, 9.5)
    cam_bed_obj.rotation_euler = (0.0, 0.0, 0.0)
    scene_collection.objects.link(cam_bed_obj)

    cam_land_data = bpy.data.cameras.new(name="Cam_Landscape_Garden_Overview")
    cam_land_data.lens = 24
    cam_land_obj = bpy.data.objects.new(name="Camera_Landscape_Overview", object_data=cam_land_data)
    cam_land_obj.location = (-12.0, -14.0, 9.0)
    cam_land_obj.rotation_euler = (1.15, 0.0, -0.72)
    scene_collection.objects.link(cam_land_obj)

    cam_gas_data = bpy.data.cameras.new(name="Cam_Gas_Tank_Side")
    cam_gas_data.lens = 32
    cam_gas_obj = bpy.data.objects.new(name="Camera_Gas_Tank_and_Boiler", object_data=cam_gas_data)
    cam_gas_obj.location = (-6.5, 6.0, 3.2)
    cam_gas_obj.rotation_euler = (1.25, 0.0, -1.35)
    scene_collection.objects.link(cam_gas_obj)

    bpy.context.scene.camera = cam_front_obj

    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.length_unit = 'METERS'

    print("Taylor Wimpey 'The Blair 4 TK' (Left-Hand) scene setup complete!")

if __name__ == "__main__":
    setup_blair_scene()
