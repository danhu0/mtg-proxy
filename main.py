import os
import re
import sys
import requests
from pathlib import Path
import time

import os
import re
import sys
import requests
from pathlib import Path

from PIL import Image
from pathlib import Path
import math
from difflib import SequenceMatcher

# reads the card names
txt_file = Path(sys.argv[1]).resolve()
with open(txt_file, "r", encoding="utf-8") as f:
    card_names = [line.strip() for line in f if line.strip()]

headers = {
        "User-Agent": "MyMTGScript/1.0 (contact@example.com)",
        "Accept": "application/json;q=0.9,*/*;q=0.8"
    }

'''
UTILITY FUNCTIONS
'''
# Minimum similarity (0-1) between the requested name and a fuzzy-matched
# name before we trust the match. Below this, Scryfall likely resolved to an
# unrelated card, so we reject rather than silently proxy the wrong card.
FUZZY_ACCEPT_THRESHOLD = 0.6


def _name_similarity(requested, matched):
    """Similarity of the requested name to the matched card name (0-1).

    DFC/adventure names come back as "Front // Back"; we score against the
    best-matching individual face as well as the full name so a request for
    one face isn't unfairly penalized.
    """
    requested = requested.casefold().strip()
    candidates = [matched.casefold().strip()]
    candidates += [part.strip() for part in matched.casefold().split("//")]

    return max(
        SequenceMatcher(None, requested, cand).ratio()
        for cand in candidates
    )


def card_lookup(card_name):
    card_name = re.sub(r"^\d+\s+", "", card_name.strip())

    # try exact match first
    response = requests.get(
        "https://api.scryfall.com/cards/named",
        params={"exact": card_name},
        headers=headers,
        timeout=30
    )

    time.sleep(0.1)

    used_fuzzy = False

    # if exact lookup fails, try fuzzy matching
    if response.status_code == 404:
        print(f"Exact match failed for '{card_name}', trying fuzzy...")
        used_fuzzy = True
        response = requests.get(
            "https://api.scryfall.com/cards/named",
            params={"fuzzy": card_name},
            headers=headers,
            timeout=30
        )
        time.sleep(0.1)

    if response.status_code != 200:
        print(f"Card not found: {card_name}")
        print(response.text)
        sys.exit(1)

    result = response.json()
    matched_name = result["name"]

    # A fuzzy match can silently resolve to an unrelated card. Verify the
    # result actually resembles what was requested before trusting it.
    if used_fuzzy:
        similarity = _name_similarity(card_name, matched_name)
        if similarity < FUZZY_ACCEPT_THRESHOLD:
            print(
                f"Rejected fuzzy match for '{card_name}': resolved to "
                f"'{matched_name}' (similarity {similarity:.2f} < "
                f"{FUZZY_ACCEPT_THRESHOLD}). Check the spelling in your "
                f"decklist."
            )
            sys.exit(1)
        print(
            f"Fuzzy-matched '{card_name}' -> '{matched_name}' "
            f"(similarity {similarity:.2f})"
        )
    else:
        print(f"Matched: {matched_name}")

    return result

def download_image(name):
    name = re.sub(r"^\d+\s+", "", name.strip())

    card_json = card_lookup(name)

    # Create downloads directory
    os.makedirs("downloads", exist_ok=True)

    # Handle double-faced cards
    if card_json.get("card_faces"):
        faces = card_json["card_faces"]

        # Some DFCs (e.g. "Stormshriek Feral // Flush Out") don't carry
        # per-face PNGs. In that case the PNG lives on the top-level card,
        # which represents a single physical card showing both faces, so we
        # save it once instead of per face.
        faces_have_png = any(
            face.get("image_uris", {}).get("png") for face in faces
        )

        if not faces_have_png:
            top_image_uris = card_json.get("image_uris") or {}
            top_png = top_image_uris.get("png")

            if not top_png:
                print(f"  No image available: {name}")
                return

            safe_name = re.sub(r'[<>:"/\\|?*]', "_", card_json["name"])
            output_file = os.path.join("downloads", f"{safe_name}.png")

            image_response = requests.get(top_png, headers=headers, timeout=30)
            image_response.raise_for_status()

            with open(output_file, "wb") as image_file:
                image_file.write(image_response.content)

            print(f"  Saved {output_file}")
            return

        for i, face in enumerate(faces):
            image_uris = face.get("image_uris")

            if not image_uris or "png" not in image_uris:
                print(f"  No image available for {face.get('name', name)}")
                continue

            image_url = image_uris["png"]

            # Use the face's actual name in the filename
            face_name = face.get("name", f"{name} - Face {i + 1}")
            safe_name = re.sub(r'[<>:"/\\|?*]', "_", face_name)
            output_file = os.path.join("downloads", f"{safe_name}.png")

            image_response = requests.get(
                image_url,
                headers=headers,
                timeout=30
            )
            image_response.raise_for_status()

            with open(output_file, "wb") as image_file:
                image_file.write(image_response.content)

            print(f"  Saved {output_file}")

    else:
        # Handle ordinary single-faced cards
        image_uris = card_json.get("image_uris")

        if not image_uris or "png" not in image_uris:
            print(f"  No image available: {name}")
            return

        image_url = image_uris["png"]

        safe_name = re.sub(r'[<>:"/\\|?*]', "_", name.strip())
        output_file = os.path.join("downloads", f"{safe_name}.png")

        image_response = requests.get(
            image_url,
            headers=headers,
            timeout=30
        )
        image_response.raise_for_status()

        with open(output_file, "wb") as image_file:
            image_file.write(image_response.content)

        print(f"  Saved {output_file}")

def arrange_cards(image_dir, target_dir):
    image_dir = Path(image_dir)
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    # Standard US Letter page at 300 DPI
    DPI = 300
    PAGE_W = int(8.5 * DPI)   # 2550 pixels
    PAGE_H = int(11 * DPI)    # 3300 pixels

    # Page margins and spacing between cards, in inches
    MARGIN = int(0.25 * DPI)
    GAP = int(0.10 * DPI)

    # Card image dimensions are approximately 744 x 1040
    CARD_W = 744
    CARD_H = 1040

    # Calculate maximum card dimensions that fit a 3x3 grid
    available_w = PAGE_W - 2 * MARGIN - 2 * GAP
    available_h = PAGE_H - 2 * MARGIN - 2 * GAP

    max_card_w = available_w // 3
    max_card_h = available_h // 3

    # Preserve the original aspect ratio
    scale = min(max_card_w / CARD_W, max_card_h / CARD_H)
    card_w = round(CARD_W * scale)
    card_h = round(CARD_H * scale)

    # Collect and sort PNG images
    image_paths = sorted(
        image_dir.glob("*.png"),
        key=lambda p: p.name.lower()
    )

    if not image_paths:
        print(f"No PNG images found in {image_dir}")
        return

    cards_per_page = 9
    num_pages = math.ceil(len(image_paths) / cards_per_page)

    for page_num in range(num_pages):
        page = Image.new("RGB", (PAGE_W, PAGE_H), "white")

        batch = image_paths[
            page_num * cards_per_page:
            (page_num + 1) * cards_per_page
        ]

        # Center the entire grid on the page
        grid_w = 3 * card_w + 2 * GAP
        grid_h = 3 * card_h + 2 * GAP

        start_x = (PAGE_W - grid_w) // 2
        start_y = (PAGE_H - grid_h) // 2

        for i, image_path in enumerate(batch):
            with Image.open(image_path) as img:
                img = img.convert("RGB")

                # Handle slight differences in source image dimensions
                img.thumbnail((card_w, card_h), Image.Resampling.LANCZOS)

                # Center each image within its card-sized cell
                col = i % 3
                row = i // 3

                x = start_x + col * (card_w + GAP)
                y = start_y + row * (card_h + GAP)

                x += (card_w - img.width) // 2
                y += (card_h - img.height) // 2

                page.paste(img, (x, y))

        # Save each page as a print-ready PDF
        output_file = target_dir / f"{page_num + 1}.pdf"

        page.save(
            output_file,
            "PDF",
            resolution=DPI
        )

        print(f"Saved {output_file}")

'''
MAIN LOOP
'''
# delete existing files
for folder in ["downloads", "ready_pages"]:
    if os.path.exists(folder):
        for file in os.listdir(folder):
            path = os.path.join(folder, file)
            if os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                import shutil
                shutil.rmtree(path)
    else:
        os.makedirs(folder)

# download all of the images
for name in card_names:
    download_image(name)
    time.sleep(0.1)
arrange_cards("downloads", "ready_pages")
