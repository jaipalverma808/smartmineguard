"""
Generate official Haryana Mines & Geology emblem, HSIIDC logo, 
and realistic weighbridge CCTV camera snapshots for e-Rawana passes.
"""
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

BASE_DIR = Path(__file__).resolve().parent.parent
IMG_DIR = BASE_DIR / "static" / "images" / "weighbridge"
IMG_DIR.mkdir(parents=True, exist_ok=True)


def create_cctv_camera_image(filename, camera_name, vehicle_no, timestamp_str, weight_info, is_overhead=False):
    """Generates a realistic industrial weighbridge CCTV / surveillance camera snapshot."""
    width, height = 640, 360
    # CCTV monochrome/infrared surveillance aesthetic
    img = Image.new("RGB", (width, height), color=(26, 32, 38))
    draw = ImageDraw.Draw(img)

    # Draw weighbridge scale platform ground lines & environment
    # Background wall / shed
    draw.rectangle([0, 0, width, 180], fill=(20, 24, 28))
    # Concrete scale floor
    draw.polygon([(40, 360), (140, 180), (500, 180), (600, 360)], fill=(45, 52, 58))
    # Steel weighbridge deck
    draw.polygon([(80, 340), (160, 200), (480, 200), (560, 340)], fill=(32, 38, 44), outline=(70, 80, 90), width=2)
    # Yellow guide rails
    draw.line([(70, 340), (150, 200)], fill=(180, 160, 30), width=3)
    draw.line([(570, 340), (490, 200)], fill=(180, 160, 30), width=3)

    if not is_overhead:
        # Front Angle view of truck on scale
        # Truck cabin
        draw.rectangle([210, 130, 430, 270], fill=(55, 65, 75), outline=(90, 105, 120), width=2)
        # Windshield
        draw.polygon([(230, 145), (410, 145), (400, 200), (240, 200)], fill=(28, 42, 55), outline=(80, 95, 110))
        # Driver silhouette
        draw.ellipse([270, 160, 300, 190], fill=(15, 20, 25))
        # Headlights (halogen glow)
        draw.ellipse([220, 220, 255, 245], fill=(240, 235, 180))
        draw.ellipse([385, 220, 420, 245], fill=(240, 235, 180))
        # Front Grille
        for y in range(215, 260, 8):
            draw.line([(270, y), (370, y)], fill=(20, 25, 30), width=3)
        # Bumper
        draw.rectangle([195, 260, 445, 285], fill=(40, 45, 50), outline=(80, 90, 100))
        # License Plate
        draw.rectangle([280, 266, 360, 280], fill=(230, 210, 30), outline=(20, 20, 20), width=1)
        draw.text((285, 267), vehicle_no, fill=(10, 10, 10))
        # Front Tyres
        draw.rectangle([180, 250, 210, 325], fill=(20, 22, 25))
        draw.rectangle([430, 250, 460, 325], fill=(20, 22, 25))
    else:
        # Overhead rear cargo bed view showing loaded crushed stone minerals
        # Truck body
        draw.rectangle([180, 120, 460, 310], fill=(45, 52, 60), outline=(75, 85, 95), width=3)
        # Cargo bed cavity
        draw.rectangle([200, 135, 440, 290], fill=(60, 70, 80))
        # Crushed Blue Stone aggregate heap texture
        import random
        random.seed(42)
        stone_colors = [(70, 85, 105), (85, 100, 120), (55, 68, 85), (95, 110, 130), (45, 58, 72)]
        for _ in range(450):
            sx = random.randint(210, 430)
            sy = random.randint(145, 280)
            sr = random.randint(4, 11)
            sc = random.choice(stone_colors)
            draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=sc)
        # Mineral mound contour
        draw.polygon([(220, 215), (320, 170), (420, 215), (320, 260)], outline=(110, 125, 145), width=2)
        # Tailgate marker
        draw.rectangle([200, 285, 440, 305], fill=(80, 30, 30), outline=(130, 50, 50))
        # Reflective tape
        for x in range(210, 430, 35):
            draw.rectangle([x, 290, x + 18, 300], fill=(220, 200, 40))

    # CCTV Timestamp and OSD overlay (Top and Bottom)
    # Camera label top left
    draw.text((15, 12), f"REC [LIVE] {camera_name}", fill=(240, 60, 60))
    draw.text((15, 28), f"LOC: HSIIDC KHANAK MINES - WB#1", fill=(200, 220, 240))
    # Timestamp top right
    draw.text((450, 12), timestamp_str, fill=(240, 240, 240))
    # Vehicle and scale reading bottom
    draw.rectangle([10, 325, 630, 352], fill=(0, 0, 0))
    draw.text((18, 331), f"VEHICLE: {vehicle_no}   |   {weight_info}", fill=(100, 240, 140))
    draw.text((530, 331), "ANPR: VERIFIED", fill=(100, 240, 140))

    # Crosshairs in center
    cx, cy = width // 2, height // 2
    draw.line([(cx - 15, cy), (cx + 15, cy)], fill=(120, 160, 180), width=1)
    draw.line([(cx, cy - 15), (cx, cy + 15)], fill=(120, 160, 180), width=1)

    # Subtle scanline effect
    for y in range(0, height, 4):
        draw.line([(0, y), (width, y)], fill=(15, 18, 22))

    img.save(IMG_DIR / filename, quality=90)
    print(f"Generated CCTV asset: {IMG_DIR / filename}")


def create_haryana_emblem(filename="haryana_govt_logo.png"):
    """Generates an official-looking Haryana Government / Dept of Mines & Geology circular emblem."""
    size = 240
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    # Double green circle
    draw.ellipse([8, 8, size - 8, size - 8], outline=(15, 56, 38), width=5)
    draw.ellipse([16, 16, size - 16, size - 16], outline=(15, 56, 38), width=2)

    # Wheat stalks / laurel wreath arcs
    draw.arc([24, 24, size - 24, size - 24], start=45, end=315, fill=(15, 56, 38), width=4)

    # Central emblem: Rising sun behind mountains
    cx, cy = size // 2, size // 2
    for angle in range(0, 180, 20):
        import math
        rad = math.radians(angle)
        x1 = cx + int(45 * math.cos(rad))
        y1 = cy - int(45 * math.sin(rad))
        x2 = cx + int(65 * math.cos(rad))
        y2 = cy - int(65 * math.sin(rad))
        draw.line([(x1, y1), (x2, y2)], fill=(210, 150, 20), width=3)

    # Mountains
    draw.polygon([(cx - 55, cy + 25), (cx - 20, cy - 15), (cx + 15, cy + 25)], fill=(15, 56, 38))
    draw.polygon([(cx - 15, cy + 25), (cx + 25, cy - 22), (cx + 60, cy + 25)], fill=(25, 75, 50))

    # Water ripples below
    for y in range(cy + 32, cy + 50, 6):
        draw.line([(cx - 45, y), (cx + 45, y)], fill=(15, 56, 38), width=2)

    # Text
    draw.text((size // 2 - 58, 22), "GOVT. OF HARYANA", fill=(15, 56, 38))
    draw.text((size // 2 - 68, size - 36), "MINES & GEOLOGY", fill=(15, 56, 38))

    img.save(IMG_DIR / filename)
    print(f"Generated Haryana Emblem: {IMG_DIR / filename}")


def create_hsiidc_logo(filename="hsiidc_logo.png"):
    """Generates the HSIIDC geometric hexagon cluster corporate logo."""
    size = 200
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = size // 2, size // 2 - 15
    import math
    for r in range(12, 55, 14):
        num_dots = int(r * 0.4) + 4
        for i in range(num_dots):
            theta = (2 * math.pi * i) / num_dots
            dx = cx + int(r * math.cos(theta))
            dy = cy + int(r * math.sin(theta))
            draw.ellipse([dx - 3, dy - 3, dx + 3, dy + 3], fill=(15, 56, 38))

    draw.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=(15, 56, 38))
    draw.text((cx - 24, size - 35), "HSIIDC", fill=(15, 56, 38))

    img.save(IMG_DIR / filename)
    print(f"Generated HSIIDC Logo: {IMG_DIR / filename}")


if __name__ == "__main__":
    create_cctv_camera_image("cctv_anpr_front.jpg", "CAM-01 [ANPR FRONT]", "HR-46-D-2823", "2026-09-11 21:24:46", "GROSS: 42,260 KG", is_overhead=False)
    create_cctv_camera_image("cctv_bed_overhead.jpg", "CAM-02 [BED OVERHEAD]", "HR-46-D-2823", "2026-09-11 21:24:46", "NET: 30,390 KG (30.39 MT)", is_overhead=True)
    create_haryana_emblem("haryana_govt_logo.png")
    create_hsiidc_logo("hsiidc_logo.png")
