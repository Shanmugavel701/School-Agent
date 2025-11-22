import os
import json
import requests
from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from io import BytesIO
import traceback
from google.api_core import exceptions as google_exceptions

load_dotenv()

app = Flask(__name__, static_folder='frontend/static', template_folder='frontend/templates')
CORS(app)

SERPER_API_KEY = os.getenv('SERPER_API_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
print("=" * 50)
print("STARTUP DEBUG INFO")
print("=" * 50)
print("Loaded SERPER_API_KEY:", SERPER_API_KEY[:20] + "..." if SERPER_API_KEY else "NOT SET")
print("Loaded GEMINI_API_KEY:", GEMINI_API_KEY[:20] + "..." if GEMINI_API_KEY else "NOT SET")
print("=" * 50)


def serper_search(query: str):
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    payload = {"q": query, "num": 5}
    resp = requests.post(url, json=payload, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.json()

def find_website_url(query, domain_hint):
    data = serper_search(query)
    results = data.get("organic") or []
    for item in results:
        link = item.get("link", "").lower()
        if "yellowslate.com" in domain_hint:
            if "yellowslate.com/school/" in link:
                if any(bad in link for bad in ["/blog/", "/news/", "/article/", "/best-", "/top-", "/ranking", "/rankings"]):
                    continue
                if link.count("/") >= 5:
                    return link
            continue
        if "edustoke.com" in domain_hint:
            if "edustoke.com" in link:
                if "/blog/" in link or "/article/" in link:
                    continue
                return link
    return None

def scrape_page(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.google.com/"
    }
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for s in soup(["script", "style", "noscript"]):
        s.decompose()
    pieces = []
    title = soup.find("h1")
    if title:
        pieces.append("Title: " + title.get_text(" ", strip=True))
    # extract ld+json if present
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            j = json.loads(script.string)
            pieces.append(json.dumps(j))
        except Exception:
            pass
    for tag in soup.find_all(["p", "li", "td", "th", "div"]):
        txt = tag.get_text(" ", strip=True)
        if txt and len(txt) > 40:
            pieces.append(txt)
    return "\n\n".join(pieces)

PROMPT = """
You are a strict school data extractor and validator.

USER QUERY: "{query}"

STEP 1: VALIDATE THE USER QUERY
- Decide if the user query looks like a real school/college name.
- If the query is invalid:
    Return ONLY:
    {{
      "error": "Invalid school name"
    }}

STEP 2: MATCH AGAINST RAW TEXT
- Check RAW TEXT for any school name that contains the entire user query.
- If no match exists:
    Return ONLY:
    {{
      "error": "No data found"
    }}

STEP 3: EXTRACT DATA
Return ONLY this JSON object:

{{
  "school_name": "",
  "address": "",
  "location": "",
  "contact": "",
  "website": "",
  "email": "",
  "board": "",
  "classes_offered": "",
  "fees": "",
  "admission_process": "",
  "facilities": [],
  "transport": "",
  "rating": "",
  "about": "",
  "summary": ""
}}

RULES:
- Strict valid JSON.
- No hallucinations.
- Use only RAW TEXT.

RAW TEXT:
{raw}
"""



@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    """Health check endpoint for Render"""
    return jsonify({"status": "ok", "service": "school-agent-backend"}), 200

@app.route('/api/school')
def api_school():
    try:
        q = request.args.get('q', '').strip()
        if not q:
            return jsonify({"error": "missing query parameter 'q'"}), 400

        ys = find_website_url(f"{q} yellowslate", "yellowslate.com")
        es = find_website_url(f"{q} edustoke", "edustoke.com")

        if not ys and not es:
            return jsonify({"error": "no pages found"}), 404

        combined = ""
        if ys:
            try:
                combined += "\n===== YellowSlate =====\n" + scrape_page(ys)
            except Exception as e:
                combined += "\n===== YellowSlate (error) =====\n" + str(e)

        if es:
            try:
                combined += "\n===== EduStoke =====\n" + scrape_page(es)
            except Exception as e:
                combined += "\n===== EduStoke (error) =====\n" + str(e)

        # Check if API key is set
        if not GEMINI_API_KEY:
            return jsonify({"error": "GEMINI_API_KEY is not set in environment variables"}), 500
        
        # Call Gemini via LangChain Google wrapper
        try:
            llm = ChatGoogleGenerativeAI(model='gemini-2.5-flash', temperature=0, api_key=GEMINI_API_KEY)
            prompt = PROMPT.format(query=q, raw=combined[:45000])
            result = llm.invoke(prompt)
            raw_out = result.content or ""
        except google_exceptions.PermissionDenied as e:
            error_msg = str(e)
            # Check for leaked API key error specifically
            if "leaked" in error_msg.lower() or "reported as leaked" in error_msg.lower():
                return jsonify({
                    "error": "API key error: Your Gemini API key has been reported as leaked. Please generate a new API key from Google AI Studio (https://aistudio.google.com/apikey) and update your .env file with GEMINI_API_KEY=<new_key>"
                }), 403
            else:
                return jsonify({
                    "error": f"API key permission denied: {error_msg}. Please check your GEMINI_API_KEY in the .env file."
                }), 403
        except Exception as llm_error:
            error_msg = str(llm_error)
            # Check for leaked API key error in generic exception (in case it's wrapped)
            if "leaked" in error_msg.lower() or "reported as leaked" in error_msg.lower():
                return jsonify({
                    "error": "API key error: Your Gemini API key has been reported as leaked. Please generate a new API key from Google AI Studio (https://aistudio.google.com/apikey) and update your .env file with GEMINI_API_KEY=<new_key>"
                }), 403
            # Check for permission denied in error message
            elif "permission denied" in error_msg.lower():
                return jsonify({
                    "error": f"API key permission denied: {error_msg}. Please check your GEMINI_API_KEY in the .env file."
                }), 403
            # Other API errors
            else:
                return jsonify({
                    "error": f"Error calling Gemini API: {error_msg}. Please check your API key and try again."
                }), 500
        try:
            start = raw_out.find('{')
            end = raw_out.rfind('}')
            data = json.loads(raw_out[start:end+1])
        except Exception:
            data = {
                "school_name": "",
                "address": "",
                "location": "",
                "contact": "",
                "website": "",
                "email": "",
                "board": "",
                "classes_offered": "",
                "fees": "",
                "admission_process": "",
                "facilities": [],
                "transport": "",
                "rating": "",
                "about": combined[:2000],
                "summary": ""
            }
        # attach found URLs for debugging
        data['_sources'] = {'yellowslate': ys, 'edustoke': es}
        return jsonify(data)
    except Exception as e:
        error_msg = str(e)
        print(f"ERROR in /api/school: {error_msg}")
        traceback.print_exc()
        
        # Check for leaked API key error in outer handler (in case inner handler didn't catch it)
        if "leaked" in error_msg.lower() or "reported as leaked" in error_msg.lower():
            return jsonify({
                "error": "API key error: Your Gemini API key has been reported as leaked. Please generate a new API key from Google AI Studio (https://aistudio.google.com/apikey) and update your .env file with GEMINI_API_KEY=<new_key>"
            }), 403
        
        # Check for other API key related errors
        if "API key" in error_msg or "permission denied" in error_msg.lower():
            return jsonify({
                "error": "API key issue detected. Please check your GEMINI_API_KEY in the .env file. If you see a 'leaked' error, generate a new key from https://aistudio.google.com/apikey"
            }), 403
        
        return jsonify({"error": f"Server error: {error_msg}"}), 500
@app.route('/api/pdf')
def api_pdf():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "missing query parameter 'q'"}), 400

    # Step 1: Fetch school data using your existing API logic
    # Call your own /api/school endpoint internally
    school_url = f"{request.host_url.rstrip('/')}/api/school?q={q}"
    r = requests.get(school_url)
    data = r.json()

    # If API returned error → show simple PDF with error message
    if "error" in data:
        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = [Paragraph(f"Error: {data['error']}", styles['Title'])]
        doc.build(story)
        pdf_buffer.seek(0)
        return send_file(pdf_buffer, download_name=f"{q}.pdf", as_attachment=True)

    # Step 2: Build PDF with school details
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=A4)
    styles = getSampleStyleSheet()

    story = []
    story.append(Paragraph(data.get("school_name", ""), styles['Title']))
    story.append(Spacer(1, 12))

    for key, value in data.items():
        if key == "_sources":
            continue
        story.append(Paragraph(f"<b>{key.upper()}:</b> {value}", styles['Normal']))
        story.append(Spacer(1, 8))

    doc.build(story)
    pdf_buffer.seek(0)

    return send_file(pdf_buffer, download_name=f"{q}.pdf", as_attachment=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
