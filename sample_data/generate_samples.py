"""
Quick synthetic quote-slip generator so the pipeline is testable today
without needing real photographed quotes yet. These are plain typed text on
a white background, deliberately boring.

Swap these for actual messy handwritten photos (or at least scanned/skewed
ones) well before the live demo — Gemma reading genuinely messy handwriting
live is the actual wow moment. These are just for unblocking dev work now.

Usage:
    pip install Pillow   (already in requirements.txt)
    python sample_data/generate_samples.py
"""

import os
from PIL import Image, ImageDraw

OUT_DIR = os.path.dirname(__file__)

# Matches the suppliers seeded in db/seed_data.py so retrieve() actually
# finds a history hit during testing.
QUOTES = [
    {
        "filename": "quote1_balaji.png",
        "lines": [
            "Balaji Building Materials",
            "Cement - 50 bags",
            "Rate: Rs. 420/bag",
            "Payment: 15 days credit",
            "Delivery: 2 days",
        ],
    },
    {
        "filename": "quote2_krishna.png",
        "lines": [
            "Krishna Cement Suppliers",
            "Cement - 50 bags",
            "Rate: Rs. 390/bag",
            "Payment: Cash on delivery",
            "Delivery: 4 days",
        ],
    },
    {
        "filename": "quote3_newblr.png",
        "lines": [
            "New Bengaluru Traders",
            "Cement - 50 bags",
            "Rate: Rs. 405/bag",
            "Payment: 7 days credit",
            "Delivery: 3 days",
        ],
    },
]


def generate():
    for q in QUOTES:
        img = Image.new("RGB", (500, 300), color="white")
        draw = ImageDraw.Draw(img)
        y = 30
        for line in q["lines"]:
            draw.text((30, y), line, fill="black")
            y += 40
        path = os.path.join(OUT_DIR, q["filename"])
        img.save(path)
        print(f"Wrote {path}")


if __name__ == "__main__":
    generate()
