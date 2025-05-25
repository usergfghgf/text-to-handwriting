from flask import Flask, request, jsonify, send_file
import google.generativeai as genai
from fpdf import FPDF
import re
import requests
import json
import os
from io import BytesIO

app = Flask(__name__)

# Replace with your Google Generative AI API key
GEN_API_KEY = "Api_key"
genai.configure(api_key=GEN_API_KEY)

def clean_text(text):
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"_([^_]*)_", r"\1", text)
    return text.strip()

def generate_content(text, task):
    try:
        model = genai.GenerativeModel("gemini-1.5-pro")
        response = model.generate_content(f"{task}\n{text}")
        return clean_text(response.text)
    except Exception as e:
        return f"Error: {str(e)}"

@app.route('/generate_notes', methods=['POST'])
def generate_notes():
    data = request.json
    text = data.get('text', '')
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    content = generate_content(text, "Generate highly detailed and structured notes. Ensure the notes cover all key points, explanations, diagrams, examples, and contextual information. Break down complex concepts into simple, easy-to-understand sections. Include definitions and bullet points where necessary. Add relevant examples, use cases, and practical applications to enhance understanding. Maintain clarity, conciseness, and logical flow. If the text contains technical terms, provide explanations and possible real-world connections. Ensure the notes are well-organized and formatted for efficient studying. Do not include any concluding statements, learning tips, additional practice advice, or references to external resources. Keep the notes strictly factual and content-focused. Don't give any intro and outro.")
    return jsonify({'content': content})

@app.route('/generate_questions', methods=['POST'])
def generate_questions():
    data = request.json
    text = data.get('text', '')
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    content = generate_content(text, "Generate minimum 20 well structured multiple-choice questions and provide answer key in last with only option number not full answer. Don't give any intro and outro.")
    return jsonify({'content': content})

@app.route('/generate_summary', methods=['POST'])
def generate_summary():
    data = request.json
    text = data.get('text', '')
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    content = generate_content(text, "Summarize in a clear, concise, and structured manner using bullet points. Capture only the key ideas, main arguments, and important details while eliminating redundant or less significant information. Ensure the summary retains the core meaning of the text while being easy to read and understand. Use short, precise sentences and maintain logical flow. If the text includes data, key figures, or important names, include them in the summary while keeping it brief and to the point. Don't give any intro and outro.")
    return jsonify({'content': content})

@app.route('/export_pdf', methods=['POST'])
def export_pdf():
    data = request.json
    notes = data.get('notes', '')
    questions = data.get('questions', '')
    summary = data.get('summary', '')
    if not (notes or questions or summary):
        return jsonify({'error': 'No content to export'}), 400

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", style="B", size=18)

    if notes:
        pdf.cell(200, 10, "Notes", ln=True, align="L")
        pdf.set_font("Arial", size=14)
        pdf.multi_cell(0, 8, notes + "\n\n")

    if questions:
        pdf.set_font("Arial", style="B", size=18)
        pdf.cell(200, 10, "Questions", ln=True, align="L")
        pdf.set_font("Arial", size=14)
        pdf.multi_cell(0, 8, questions + "\n\n")

    if summary:
        pdf.set_font("Arial", style="B", size=18)
        pdf.cell(200, 10, "Summary", ln=True, align="L")
        pdf.set_font("Arial", size=14)
        pdf.multi_cell(0, 8, summary + "\n\n")

    buffer = BytesIO()
    pdf.output(buffer)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='study_assistant.pdf', mimetype='application/pdf')

@app.route('/generate_plan', methods=['POST'])
def generate_plan():
    data = request.json
    text = data.get('text', '')
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    plan = generate_content(text, "Generate a day-wise study plan for the following subjects and time durations. Divide the available time efficiently across the days based on subject difficulty and coverage needs. Do not include any additional explanation, notes and tips — only provide the plan in a clear and day-wise format.")
    tasks = [line.strip() for line in plan.split("\n") if line.strip()]
    return jsonify({'tasks': tasks})

@app.route('/save_tasks', methods=['POST'])
def save_tasks():
    tasks = request.json
    if not tasks:
        return jsonify({'error': 'No tasks provided'}), 400
    buffer = BytesIO()
    buffer.write(json.dumps(tasks, indent=4).encode('utf-8'))
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='tasks.json', mimetype='application/json')

@app.route('/load_tasks', methods=['POST'])
def load_tasks():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if file.filename.endswith('.json'):
        tasks = json.load(file)
        return jsonify(tasks)
    return jsonify({'error': 'Invalid file format'}), 400

@app.route('/search_word', methods=['POST'])
def search_word():
    data = request.json
    word = data.get('word', '').strip()
    if not word:
        return jsonify({'error': 'No word provided'}), 400

    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
        response = requests.get(url)
        if response.status_code != 200:
            return jsonify({'content': f"No information found for '{word}'."})

        data = response.json()[0]
        meanings = data.get("meanings", [])
        definitions = []
        synonyms = set()
        examples = []

        for meaning in meanings[:3]:
            part_of_speech = meaning.get("partOfSpeech", "")
            for defn in meaning.get("definitions", []):
                definition = defn.get("definition", "")
                example = defn.get("example", "")
                definitions.append(f"({part_of_speech}) {definition}")
                if example:
                    examples.append(example)
                synonyms.update(defn.get("synonyms", []))

        def_text = "\n".join(definitions) or "No definitions found."
        syn_text = ", ".join(list(synonyms)[:10]) or "No synonyms found."
        ex_text = "\n".join(examples[:3]) or "No examples found."

        content = f"Definition:\n{def_text}\n\nSynonyms:\n{syn_text}\n\nExamples:\n{ex_text}"
        return jsonify({'content': content})
    except Exception as e:
        return jsonify({'content': f"Error: {str(e)}"})

if __name__ == '__main__':
    app.run(debug=True)