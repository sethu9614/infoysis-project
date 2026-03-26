from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import pdfplumber, docx, re
from collections import Counter
from database import register_user, login_user
from fpdf import FPDF

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

document_text = ""

# ✅ FIX FOR PDF ENCODING
def clean_text(text):
    return text.encode("latin-1", "ignore").decode("latin-1")

# -------- FILE EXTRACTION --------
def extract_pdf(file):
    text = ""
    with pdfplumber.open(file) as pdf:
        for p in pdf.pages:
            t = p.extract_text()
            if t:
                text += t
    return text

def extract_docx(file):
    doc = docx.Document(file)
    return "\n".join([p.text for p in doc.paragraphs])

# -------- SUMMARY --------
def generate_summary(text, mode="medium"):
    sentences = re.split(r'(?<=[.!?]) +', text)

    words = re.findall(r'\w+', text.lower())
    freq = Counter(words)

    scores = {s: sum(freq[w] for w in re.findall(r'\w+', s.lower())) for s in sentences}
    ranked = sorted(scores, key=scores.get, reverse=True)

    if mode == "small":
        selected = ranked[:4]
    elif mode == "medium":
        selected = ranked[:8]
    elif mode == "long":
        selected = ranked[:15]
    else:
        selected = ranked

    selected = sorted(selected, key=lambda s: sentences.index(s))

    return {
        "summary_paragraphs": [" ".join(selected[i:i+3]) for i in range(0, len(selected), 3)],
        "headings": ["Introduction","Overview","Analysis","Conclusion"]
    }

# -------- FULL SUMMARY --------
def generate_full_summary(text):
    s = re.split(r'(?<=[.!?]) +', text)

    return {
        "title": s[0] if s else "",
        "abstract": " ".join(s[:3]),
        "introduction": " ".join(s[3:6]),
        "objectives": s[6] if len(s)>6 else "",
        "key_insights": s[7:12],
        "results": " ".join(s[12:15]),
        "conclusion": s[-1] if s else ""
    }

# -------- AUTH --------
@app.post("/register/")
def register(username: str = Form(...), password: str = Form(...)):
    return {"message": "Registered"} if register_user(username, password) else {"error": "Exists"}

@app.post("/login/")
def login(username: str = Form(...), password: str = Form(...)):
    return {"message": "Success"} if login_user(username, password) else {"error": "Invalid"}

# -------- UPLOAD --------
@app.post("/upload/")
async def upload(file: UploadFile = File(...)):
    global document_text

    if file.filename.endswith(".pdf"):
        document_text = extract_pdf(file.file)
    elif file.filename.endswith(".docx"):
        document_text = extract_docx(file.file)
    else:
        return {"error": "Unsupported file"}

    document_text = document_text[:5000]
    return {"message": "Uploaded successfully"}

# -------- SUMMARY --------
@app.get("/summary/")
def summary(mode: str = "medium"):
    if not document_text:
        return {"error": "Upload file first"}

    if mode == "full":
        return generate_full_summary(document_text)

    return generate_summary(document_text, mode)

# -------- ANALYSIS --------
@app.get("/analysis/")
def analysis():
    if not document_text:
        return {"top_words": []}

    words = re.findall(r'\w+', document_text.lower())
    return {"top_words": Counter(words).most_common(20)}

# -------- CHAT --------
@app.post("/ask/")
def ask(question: str = Form(...)):
    if not document_text:
        return {"answer": "Upload file first"}

    sentences = re.split(r'(?<=[.!?]) +', document_text)
    res = [s for s in sentences if any(w in s.lower() for w in question.lower().split())]

    return {"answer": " ".join(res[:3]) if res else "No answer found"}

# -------- REPORT (FINAL FIXED) --------
@app.get("/report/")
def report(mode: str = "medium"):

    if not document_text:
        return {"error": "Upload file first"}

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, "AI Document Analyzer Report", ln=True)

    if mode == "full":
        data = generate_full_summary(document_text)

        for k, v in data.items():
            pdf.ln(5)
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 8, clean_text(k.upper()), ln=True)

            pdf.set_font("Arial", size=11)

            if isinstance(v, list):
                for i in v:
                    pdf.multi_cell(0, 6, clean_text("- " + str(i)))
            else:
                pdf.multi_cell(0, 6, clean_text(str(v)))

    else:
        data = generate_summary(document_text, mode)

        for h, p in zip(data["headings"], data["summary_paragraphs"]):
            pdf.ln(5)
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 8, clean_text(h), ln=True)

            pdf.set_font("Arial", size=11)
            pdf.multi_cell(0, 6, clean_text(p))

    pdf_bytes = pdf.output(dest="S").encode("latin-1")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=report.pdf"}
    )
