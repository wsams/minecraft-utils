import argparse
from PIL import Image
import numpy as np
import os
import json
import re
from datetime import datetime

# Functions

def load_block_color_map(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
        return {tuple(map(int, key.strip("[]").split(", "))): value for key, value in data.items()}

def parse_image_filename(image_path):
    base_name, ext = os.path.splitext(os.path.basename(image_path))
    ext = ext.lstrip(".")
    return base_name, ext

def is_filename_valid(filename, patterns, excluded_substrings):
    # Check if filename ends with .png and is not grass_block_snow.png
    if not filename.endswith(".png") or filename == "grass_block_snow.png":
        return False
    
    # Check if filename matches any of the provided patterns
    if any(pattern.search(filename) for pattern in patterns):
        return False
    
    # Check if filename contains any of the excluded substrings
    if any(excluded in filename for excluded in excluded_substrings):
        return False
    
    return True

def list_png_files(directory="textures/block", colors={}, patterns=[], excluded_substrings=[]):
    """
    List all PNG files in the specified directory, extract the base name without the extension,
    apply filters, and print each base name with its average color.
    """
    # Check if the directory exists
    if not os.path.exists(directory):
        print(f"The directory {directory} does not exist.")
        return
    

    # Iterate over all files in the directory
    for filename in os.listdir(directory):
        if is_filename_valid(filename, patterns, excluded_substrings):
            # Extract the base name without the extension and calculate average color
            base_name = os.path.splitext(filename)[0]
            color = calculate_average_color(f"{directory}/{filename}")
            colors[color] = base_name
            
            # Print the base name and color
            # print(f"{base_name}: {color}")

    return colors

def calculate_average_color(image_path):
    img = Image.open(image_path).convert("RGB")
    pixels = list(img.getdata())
    num_pixels = len(pixels)
    total_r, total_g, total_b = 0, 0, 0
    for r, g, b in pixels:
        total_r += r
        total_g += g
        total_b += b
    return (total_r // num_pixels, total_g // num_pixels, total_b // num_pixels)

def find_closest_color(r, g, b):
    """
    Find the closest color in the `colors_to_blocks` dictionary to the given RGB color.
    """
    closest_color = None
    min_distance = float("inf")
    
    for color in colors_to_blocks.keys():
        distance = ((color[0] - r) ** 2 + (color[1] - g) ** 2 + (color[2] - b) ** 2) ** 0.5
        if distance < min_distance:
            min_distance = distance
            closest_color = color
    
    return closest_color

def convert_image_to_mcfunction(image_path, num_colors, offset=5000, max_dimension=200, min_z=100, is_horizontal=False):
    # Load the image
    img = Image.open(image_path)

    original_width, original_height = img.size
    scaling_factor = min(max_dimension / original_width, max_dimension / original_height)
    width = int(original_width * scaling_factor)
    height = int(original_height * scaling_factor)
    
    # Resize the image
    img = img.resize((width, height), Image.Resampling.LANCZOS)
    
    # Reduce the color palette
    img = img.quantize(colors=num_colors)
    
    # Convert image to RGB mode to fetch RGB values
    img = img.convert("RGBA")

    resized_width, resized_height = img.size

    # Generate Minecraft commands
    commands = []
    # z is the base height of where we want the image to start when rendering vertically (the bottom row will be at this height)
    # for y in range(resized_height):
    for y in range(resized_height - 1, -1, -1):
        for x in range(resized_width):
            r, g, b, a = img.getpixel((x, y))
            if a == 0:
                # handle transparent blocks
                block = "minecraft:air"
            else:
                block = colors_to_blocks.get(find_closest_color(r, g, b), "minecraft:glass")
            # x_use = x + offset
            if is_horizontal:
                # y_use = y + offset
                # commands.append(f"fill {x_use} ~ {y_use} {x_use} ~ {y_use} {block}")
                commands.append(f"fill ~{x} ~ ~{y} ~{x} ~ ~{y} {block}")
            else:
                z_use = min_z + (resized_height - 1 - y)
                # y_use = ~ means image faces north/south
                # commands.append(f"fill {x_use} {z_use} ~ {x_use} {z_use} ~ {block}")
                commands.append(f"fill ~{x} {z_use} ~ ~{x} {z_use} ~ {block}")
    
    filename = f"{image_base_name}.mcfunction"
    with open(filename, "w") as file:
        file.write("\n".join(commands))
    
    print(f"Generated Minecraft function file: {image_base_name}.mcfunction")

# Input

parser = argparse.ArgumentParser(description="Process an image for Minecraft.")
parser.add_argument("image", type=str, help="Path to the image file, e.g., foo.jpg")
parser.add_argument("--generate-json", action="store_true", help="Generate JSON output instead of converting to .mcfunction (you must pass an image - fix this input bug - the image will not be used)")
args = parser.parse_args()

# Assuming the patterns are defined as follows:
stage_pattern = re.compile(r"_stage\d+")
side_pattern = re.compile(r"_side\d+")
line_pattern = re.compile(r"_line\d+")
powder_pattern = re.compile(r".*powder.*")
ends_in_num_pattern = re.compile(r"_\d+\.png$")

# List of excluded substrings and patterns for filename checking
excluded_substrings = ['_top', '_bottom', '_side', '_lit', '_on', '_dot', '_overlay', 'cracked', '_compost', '_ready',
                        '_dead', '_empty', '_occupied', '_base', 'grass', '_block_snow', '_powder', 'structure_',
                        'suspicious_gravel', 'repeating_', 'command_', 'gravel', 'sand', '_north', '_south', '_east',
                        '_west', '_active', '_inactive', '_off', 'water', 'rail', 'egg', 'torch', 'leaves', 'plant',
                        'stem', 'mushroom', 'roots', 'vine', 'coral', 'blossom', 'repeater', 'candle', 'tulip', 'rose',
                        'lever', 'lightning_rod', 'kelp', 'iron_bars', 'flower_pot', 'fern', 'debug', 'dandelion', 'fungus',
                        'cornflower', 'cobweb', 'chain', '_inner', 'brewing_stand', '_tip', 'beacon', 'anvil', 'daisy',
                        '_back', 'sprouts', 'lily_pad', 'lily_of_the_valley', 'lava', '_bud', 'ladder', 'lantern',
                        '_lock', 'item_frame', 'end_rod', 'conduit', 'sapling', 'tripwire', '_front', 'glass', 'trapdoor',
                        'door', 'button', 'pressure_plate', 'sign', 'frame', 'stalk', 'campfire', 'particle', 'pivot',
                        'round', 'moist', 'propagule', '_saw', '_outside', '_inside', 'calibrated', '_middle', '_frustum',
                        '_behive_end', '_singleleaf', 'allium', 'poppy', 'blue_orchid', 'azure_bluet', 'oxeye_daisy',
                        'sunflower', 'comparator', 'hopper', 'observer', 'piston', 'dispenser', 'dropper', 'furnace',
                        'sugar_cane', 'glow_lichen', 'glow_ink', 'glow_berries', 'glow_squid', 'glow_item_frame', 'snow',
                        'hanging', 'chorus_flower', 'frogspawn', 'pickle', 'fence', 'gate', 'pink_pedals', 'mangrove_propagule']

if args.image and not args.generate_json:
    # Configuration

    image_base_name, image_ext = parse_image_filename(args.image)
    image_path = f"{image_base_name}.{image_ext}"  # Replace with your image path
    # Unused
    offset = 5000
    # If you have an image that is 5000x1000, this will scale the image so that neither the width
    # nor the height is greater than 100. The result here would be 100x20.
    max_dimension = 100
    # This is the minimum height any block will be placed.
    min_z = 100
    # If you want to look down from the sky and see your photo printed on the ground, set this to True
    # If you want your print to stand like a cardboard cutout, set this to False
    is_horizontal = False
    colors_to_blocks = load_block_color_map("blockcolormap.json")
    # By default we use the number of colors in the block color map but you can reduce the number
    # num_colors = 256  # Number of colors for reduced palette
    num_colors = len(list(colors_to_blocks))

    convert_image_to_mcfunction(image_path, num_colors, offset, max_dimension)

if args.generate_json:
    # This will create a dictionary of colors to blocks that can be copied into `blockcolormap.json`
    # textures/block is a directory within the assets folder of the Minecraft game
    colors = list_png_files("textures/block", patterns=[stage_pattern, side_pattern, line_pattern, ends_in_num_pattern, powder_pattern], excluded_substrings=excluded_substrings)

    print("{")
    filtered_colors = {color: block_name for color, block_name in colors.items() if "glass" not in block_name and "stained" not in block_name}
    total_items = len(filtered_colors)
    count = 1
    for color, block_name in filtered_colors.items():
        r, g, b = color
        if count == total_items:
            comma = ""
        else:
            comma = ","

        if block_name.startswith("minecraft:"):
            print(f"    \"[{r}, {g}, {b}]\": \"{block_name}\"{comma}")
        else:
            print(f"    \"[{r}, {g}, {b}]\": \"minecraft:{block_name}\"{comma}")
        
        count += 1
    print("}")
