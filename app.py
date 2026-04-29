from flask import Flask, request, jsonify
from PIL import Image, ImageOps
import io
import base64
import requests
import numpy as np

app = Flask(__name__)

def download_image(url):
    r = requests.get(url, stream=True, allow_redirects=True)
    return Image.open(io.BytesIO(r.content))

def remove_black_bg(logo):
    logo = logo.convert("RGBA")
    data = np.array(logo)
    r, g, b, a = data[:,:,0], data[:,:,1], data[:,:,2], data[:,:,3]
    data[:,:,3] = np.where((r < 40) & (g < 40) & (b < 40), 0, 255)
    result = Image.fromarray(data)
    bbox = result.getbbox()
    return result.crop(bbox) if bbox else result

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})

@app.route('/brand', methods=['POST'])
def brand_image():
    try:
        data = request.get_json()
        raw_img = ImageOps.exif_transpose(download_image(data['raw_url'])).convert("RGBA")
        logo = remove_black_bg(download_image(data['logo_url']))
        raw_w, raw_h = raw_img.size
        if raw_w > raw_h:
            raw_img = raw_img.rotate(90, expand=True)
            raw_w, raw_h = raw_img.size
        logo_w = int(raw_w * 0.28)
        logo_h = int(logo.height * (logo_w / logo.width))
        logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
        pos_x = (raw_w - logo_w) // 2
        pos_y = int(raw_h * 0.04)
        raw_img.paste(logo, (pos_x, pos_y), logo)
        output = io.BytesIO()
        raw_img.convert("RGB").save(output, format="JPEG", quality=95)
        result_b64 = base64.b64encode(output.getvalue()).decode("utf-8")
        return jsonify({"success": True, "branded_image": result_b64})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
