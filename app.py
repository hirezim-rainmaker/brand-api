from flask import Flask, request, jsonify, send_file
from PIL import Image, ImageOps
import io
import base64
import numpy as np

app = Flask(__name__)

def remove_black_background(logo_img):
    """Remove black background from logo"""
    logo_rgba = logo_img.convert("RGBA")
    data = np.array(logo_rgba)
    r, g, b, a = data[:,:,0], data[:,:,1], data[:,:,2], data[:,:,3]
    black_mask = (r < 40) & (g < 40) & (b < 40)
    data[:,:,3] = np.where(black_mask, 0, 255)
    return Image.fromarray(data)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})

@app.route('/brand', methods=['POST'])
def brand_image():
    try:
        data = request.get_json()

        # Decode raw image
        raw_bytes = base64.b64decode(data['raw_image'])
        raw_img = Image.open(io.BytesIO(raw_bytes))

        # Auto-fix EXIF rotation
        raw_img = ImageOps.exif_transpose(raw_img).convert("RGBA")

        # Decode logo
        logo_bytes = base64.b64decode(data['logo'])
        logo_img = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")

        # Remove black background if present
        logo_img = remove_black_background(logo_img)

        # Crop tight around logo
        bbox = logo_img.getbbox()
        if bbox:
            logo_img = logo_img.crop(bbox)

        # Resize logo to 28% of image width
        raw_w, raw_h = raw_img.size
        logo_w = int(raw_w * 0.28)
        ratio = logo_w / logo_img.width
        logo_h = int(logo_img.height * ratio)
        logo_resized = logo_img.resize((logo_w, logo_h), Image.LANCZOS)

        # Place top-center with 4% padding from top
        pos_x = (raw_w - logo_w) // 2
        pos_y = int(raw_h * 0.04)

        # Composite
        raw_img.paste(logo_resized, (pos_x, pos_y), logo_resized)

        # Save to bytes
        output = io.BytesIO()
        raw_img.convert("RGB").save(output, format="JPEG", quality=95)
        output.seek(0)

        result_b64 = base64.b64encode(output.read()).decode("utf-8")

        return jsonify({
            "success": True,
            "branded_image": result_b64
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
