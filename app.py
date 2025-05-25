from flask import Flask, request, jsonify, send_file, render_template
from PIL import Image, ImageDraw, ImageFont
import io
import base64
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

app = Flask(__name__)

# Configuration Constants
FONT_PATHS = {
    "handwriting1": "static/handwriting1.ttf",
    "handwriting2": "static/handwriting2.ttf",
    "handwriting3": "static/handwriting3.ttf",
    "handwriting4": "static/handwriting4.ttf",
    "handwriting5": "static/handwriting5.ttf",
    "handwriting6": "static/handwriting6.ttf",
    "handwriting7": "static/handwriting7.ttf",
    "handwriting8": "static/handwriting7.ttf",  # Fallback: using handwriting7.ttf since handwriting8.ttf is missing
    "handwriting9": "static/handwriting7.ttf",  # Fallback: using handwriting7.ttf since handwriting9.ttf is missing
    "handwriting10": "static/handwriting7.ttf",  # Fallback: using handwriting7.ttf since handwriting10.ttf is missing
}
DEFAULT_FONT = "Arial"  # Fallback font if the specified font fails to load
PAGE_WIDTH = 800
PAGE_HEIGHT = 1200
MARGIN_TOP = 50
MARGIN_LEFT = 50
LINE_SPACING_MULTIPLIER = 1.5
PARAGRAPH_SPACING_MULTIPLIER = 2.5
FONT_SIZE_SCALE_FACTOR = 2.0  # Scale down the font size to make text smaller in the image
PDF_DPI_SCALE_FACTOR = 72 / 96  # Adjust font size for PDF to match image at 96 DPI

# Register handwriting fonts with reportlab
for font_name, font_path in FONT_PATHS.items():
    try:
        pdfmetrics.registerFont(TTFont(font_name, font_path))
    except Exception as e:
        print(f"Failed to register font '{font_name}' with reportlab: {str(e)}")

class HandwritingGenerationError(Exception):
    """Custom exception for handwriting generation errors."""
    pass

def load_font(font_name: str, font_size: int) -> ImageFont.FreeTypeFont:
    """
    Load a font by name and size, falling back to a default font if loading fails.

    Args:
        font_name (str): The name of the font to load.
        font_size (int): The size of the font.

    Returns:
        ImageFont.FreeTypeFont: The loaded font object.

    Raises:
        HandwritingGenerationError: If font loading fails and no default is available.
    """
    font_path = FONT_PATHS.get(font_name, DEFAULT_FONT)
    # Apply scaling factor to font size
    scaled_font_size = int(font_size / FONT_SIZE_SCALE_FACTOR)
    try:
        return ImageFont.truetype(font_path, scaled_font_size)
    except Exception as e:
        try:
            return ImageFont.truetype(DEFAULT_FONT, scaled_font_size)
        except Exception:
            raise HandwritingGenerationError(f"Failed to load font '{font_name}' and default font: {str(e)}")

def create_new_page() -> tuple[Image.Image, ImageDraw.Draw]:
    """
    Create a new page image with a white background and a drawing context.

    Returns:
        tuple: A tuple of (Image object, Draw object) for the new page.
    """
    image = Image.new('RGB', (PAGE_WIDTH, PAGE_HEIGHT), 'white')
    draw = ImageDraw.Draw(image)
    return image, draw

def encode_image_to_base64(image: Image.Image) -> str:
    """
    Encode a PIL Image to a base64 string for web display.

    Args:
        image (Image.Image): The image to encode.

    Returns:
        str: A base64-encoded string with data URI prefix.
    """
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    encoded_img = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
    return f"data:image/png;base64,{encoded_img}"

def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """
    Wrap text to fit within a specified width by splitting into multiple lines.

    Args:
        text (str): The text to wrap.
        font (ImageFont.FreeTypeFont): The font to use for measuring text width.
        max_width (int): The maximum width in pixels.

    Returns:
        list[str]: A list of wrapped lines.
    """
    words = text.split(' ')
    wrapped_lines = []
    current_line = []
    current_width = 0

    for word in words:
        # Measure the width of the current line plus the new word
        test_line = ' '.join(current_line + [word])
        # Use getbbox to measure text width (more reliable in newer Pillow versions)
        text_bbox = font.getbbox(test_line)
        text_width = text_bbox[2] - text_bbox[0]  # Right - Left

        if text_width <= max_width:
            current_line.append(word)
            current_width = text_width
        else:
            # If the line exceeds max_width, add the current line (without the new word) to wrapped_lines
            if current_line:
                wrapped_lines.append(' '.join(current_line))
            # Start a new line with the current word
            current_line = [word]
            text_bbox = font.getbbox(word)
            current_width = text_bbox[2] - text_bbox[0]

    # Add the last line if it has content
    if current_line:
        wrapped_lines.append(' '.join(current_line))

    return wrapped_lines

def wrap_text_for_pdf(pdf, text: str, font_name: str, font_size: int, max_width: int) -> list[str]:
    """
    Wrap text for PDF rendering by estimating width using reportlab's stringWidth.

    Args:
        pdf: The PDF canvas object.
        text (str): The text to wrap.
        font_name (str): The font name to use for measuring text width.
        font_size (int): The font size to use for measuring.
        max_width (int): The maximum width in points.

    Returns:
        list[str]: A list of wrapped lines.
    """
    words = text.split(' ')
    wrapped_lines = []
    current_line = []
    current_width = 0

    for word in words:
        test_line = ' '.join(current_line + [word])
        text_width = pdf.stringWidth(test_line, font_name, font_size)

        if text_width <= max_width:
            current_line.append(word)
            current_width = text_width
        else:
            if current_line:
                wrapped_lines.append(' '.join(current_line))
            current_line = [word]
            current_width = pdf.stringWidth(word, font_name, font_size)

    if current_line:
        wrapped_lines.append(' '.join(current_line))

    return wrapped_lines

def render_paragraph(draw: ImageDraw.Draw, paragraph: list[str], font: ImageFont.FreeTypeFont, 
                     font_size: int, start_y: float) -> float:
    """
    Render a paragraph onto the image at the specified y position, with text wrapping.

    Args:
        draw (ImageDraw.Draw): The drawing context.
        paragraph (list[str]): List of lines in the paragraph.
        font (ImageFont.FreeTypeFont): The font to use.
        font_size (int): The font size (before scaling).
        start_y (float): The starting y position.

    Returns:
        float: The updated y position after rendering the paragraph.
    """
    current_y = start_y
    scaled_font_size = int(font_size / FONT_SIZE_SCALE_FACTOR)
    max_width = PAGE_WIDTH - 2 * MARGIN_LEFT  # Available width for text

    for line in paragraph:
        if not line.strip():  # Handle empty lines
            current_y += scaled_font_size * LINE_SPACING_MULTIPLIER
            continue

        # Wrap the line if it exceeds the page width
        wrapped_lines = wrap_text(line, font, max_width)

        # Render each wrapped line
        for wrapped_line in wrapped_lines:
            draw.text((MARGIN_LEFT, current_y), wrapped_line, font=font, fill=(0, 0, 0))
            current_y += scaled_font_size * LINE_SPACING_MULTIPLIER

    return current_y

@app.route('/')
def serve_index():
    """
    Serve the index.html file as the root page.

    Returns:
        Response: Rendered index.html template.
    """
    return render_template('index.html')

@app.route('/api/generate-handwriting', methods=['POST'])
def generate_handwriting():
    """
    Generate handwritten-style images from text, preserving paragraph and line spacing.

    Expects a JSON payload with 'text', 'font', and 'fontSize'.
    Returns a JSON response with a list of base64-encoded image URLs.
    """
    # Parse request data
    data = request.get_json()
    text = data.get('text', '')
    font_name = data.get('font', 'handwriting1')
    font_size = data.get('fontSize', 100)

    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        # Load font
        font = load_font(font_name, font_size)

        # Initialize first page
        images = []
        current_image, draw = create_new_page()
        current_y = MARGIN_TOP

        # Split text into paragraphs
        paragraphs = text.split('\n\n')

        # Process each paragraph
        for para_idx, paragraph in enumerate(paragraphs):
            if not paragraph.strip():
                continue  # Skip empty paragraphs

            # Split paragraph into lines
            lines = paragraph.split('\n')
            # Estimate paragraph height (approximate, since wrapping may increase line count)
            scaled_font_size = int(font_size / FONT_SIZE_SCALE_FACTOR)
            paragraph_height = len(lines) * scaled_font_size * LINE_SPACING_MULTIPLIER

            # Check if the paragraph fits on the current page (approximate check)
            if current_y + paragraph_height > PAGE_HEIGHT - MARGIN_TOP:
                # Save current page and start a new one
                images.append(encode_image_to_base64(current_image))
                current_image, draw = create_new_page()
                current_y = MARGIN_TOP

            # Render the paragraph with wrapping
            current_y = render_paragraph(draw, lines, font, font_size, current_y)

            # Add extra spacing after the paragraph (unless it's the last one)
            if para_idx < len(paragraphs) - 1:
                current_y += scaled_font_size * PARAGRAPH_SPACING_MULTIPLIER

        # Save the last page
        images.append(encode_image_to_base64(current_image))

        return jsonify({"imageUrls": images})

    except HandwritingGenerationError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

@app.route('/api/generate-pdf', methods=['POST'])
def generate_pdf():
    """
    Generate a PDF from the input text using the selected handwriting font.

    Expects a JSON payload with 'text', 'font', and 'fontSize'.
    Returns a PDF file as a response.
    """
    # Parse request data
    data = request.get_json()
    text = data.get('text', '')
    font_name = data.get('font', 'handwriting1')
    font_size = data.get('fontSize', 100)

    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        # Create PDF
        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=letter)
        pdf_width, pdf_height = letter  # 612 x 792 points (letter size)
        margin_left = 50
        margin_top = 50
        max_width = pdf_width - 2 * margin_left
        line_spacing_multiplier = LINE_SPACING_MULTIPLIER
        paragraph_spacing_multiplier = PARAGRAPH_SPACING_MULTIPLIER

        # Adjust font size for PDF to match the image output at 96 DPI
        scaled_font_size = int(font_size / FONT_SIZE_SCALE_FACTOR * PDF_DPI_SCALE_FACTOR)
        pdf.setFont(font_name, scaled_font_size)

        # Start at the top of the page
        y_position = pdf_height - margin_top

        # Split text into paragraphs
        paragraphs = text.split('\n\n')

        for para_idx, paragraph in enumerate(paragraphs):
            if not paragraph.strip():
                continue  # Skip empty paragraphs

            # Split paragraph into lines
            lines = paragraph.split('\n')

            for line in lines:
                if not line.strip():  # Handle empty lines
                    y_position -= scaled_font_size * line_spacing_multiplier
                    continue

                # Wrap the line if it exceeds the page width
                wrapped_lines = wrap_text_for_pdf(pdf, line, font_name, scaled_font_size, max_width)

                # Render each wrapped line
                for wrapped_line in wrapped_lines:
                    if y_position < margin_top:
                        pdf.showPage()
                        y_position = pdf_height - margin_top
                        pdf.setFont(font_name, scaled_font_size)

                    pdf.drawString(margin_left, y_position, wrapped_line)
                    y_position -= scaled_font_size * line_spacing_multiplier

            # Add extra spacing after the paragraph (unless it's the last one)
            if para_idx < len(paragraphs) - 1:
                y_position -= scaled_font_size * paragraph_spacing_multiplier

        pdf.save()
        buffer.seek(0)
        return send_file(buffer, mimetype='application/pdf')

    except Exception as e:
        return jsonify({"error": f"Failed to generate PDF: {str(e)}"}), 500

if __name__ == '__main__':
    #app.run(debug=True)
    #if __name__ == '__main__':
    # For local development only
    app.run(debug=True, host='0.0.0.0', port=5000)