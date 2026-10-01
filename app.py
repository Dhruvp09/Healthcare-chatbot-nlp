import hashlib
import io
import json
import os
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

import streamlit as st
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ----------------- PAGE CONFIG -----------------
st.set_page_config(
    page_title="MediBot - Clinical NLP Triage & Health Portal",
    page_icon="🩺",
    layout="wide"
)

load_dotenv()

# ----------------- THEME MANAGEMENT -----------------
if "theme" not in st.session_state:
    st.session_state.theme = "Dark"

def apply_theme_css(theme_mode: str):
    if theme_mode == "Dark":
        css = """
        <style>
            .stApp {
                background-color: #0E1117;
                color: #FAFAFA;
            }
            div[data-testid="stSidebar"] {
                background-color: #161B22;
                border-right: 1px solid #30363D;
            }
            .stTextInput > div > div > input, 
            .stNumberInput > div > div > input,
            .stSelectbox > div > div {
                background-color: #21262D !important;
                color: #FFFFFF !important;
                border: 1px solid #30363D !important;
            }
            div[data-testid="stMetricValue"] {
                color: #58A6FF !important;
            }
            div[data-testid="stContainer"] {
                border-color: #30363D !important;
            }
        </style>
        """
    else:
        css = """
        <style>
            .stApp {
                background-color: #F8FAFC;
                color: #0F172A;
            }
            div[data-testid="stSidebar"] {
                background-color: #FFFFFF;
                border-right: 1px solid #E2E8F0;
            }
            .stTextInput > div > div > input, 
            .stNumberInput > div > div > input,
            .stSelectbox > div > div {
                background-color: #FFFFFF !important;
                color: #0F172A !important;
                border: 1px solid #CBD5E1 !important;
            }
            div[data-testid="stMetricValue"] {
                color: #1E40AF !important;
            }
            div[data-testid="stContainer"] {
                border-color: #E2E8F0 !important;
            }
        </style>
        """
    st.markdown(css, unsafe_allow_html=True)

apply_theme_css(st.session_state.theme)

# ----------------- DATABASE SETUP -----------------
DB_FILE = "health_platform.db"

def hash_password(password: str) -> str:
    """Hashes a password with SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    """Initializes tables for Users and Triage Logs, seeding a default admin."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            role TEXT DEFAULT 'patient'
        )
    ''')
    
    # Triage logs table
    c.execute('''
        CREATE TABLE IF NOT EXISTS triage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            user_input TEXT NOT NULL,
            urgency_level TEXT NOT NULL,
            specialist TEXT,
            summary TEXT,
            FOREIGN KEY (username) REFERENCES users(username)
        )
    ''')
    
    # Seed default Admin account if not present
    c.execute("SELECT id FROM users WHERE username = 'admin'")
    if not c.fetchone():
        c.execute(
            "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
            ("admin", hash_password("admin123"), "Medical Director / Admin", "admin")
        )
        
    conn.commit()
    conn.close()

def authenticate_user(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT username, full_name, role FROM users WHERE username = ? AND password_hash = ?",
        (username.strip().lower(), hash_password(password))
    )
    user = c.fetchone()
    conn.close()
    return user

def register_user(username, password, full_name):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, 'patient')",
            (username.strip().lower(), hash_password(password), full_name.strip())
        )
        conn.commit()
        conn.close()
        return True, "Registration successful! Please log in above."
    except sqlite3.IntegrityError:
        return False, "Username already exists. Please choose a different one."
    except Exception as e:
        return False, f"Registration error: {e}"

def log_triage(username, user_input, urgency, specialist, summary):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO triage_logs (username, timestamp, user_input, urgency_level, specialist, summary) VALUES (?, ?, ?, ?, ?, ?)",
        (username, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), user_input, urgency, specialist, summary)
    )
    conn.commit()
    conn.close()

init_db()

# ----------------- PDF SUMMARY GENERATION -----------------
def generate_triage_pdf(patient_name, patient_vitals, triage_data, raw_symptoms):
    """Generates a professional single-page clinical summary PDF."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#1E3A8A')
    )
    meta_style = ParagraphStyle(
        'MetaStyle',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#6B7280')
    )
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#1F2937')
    )
    bold_style = ParagraphStyle(
        'BoldBody',
        parent=body_style,
        fontName='Helvetica-Bold'
    )
    
    # Title & Metadata
    story.append(Paragraph("MediBot Clinical Triage Summary", title_style))
    story.append(Paragraph(f"Patient: <b>{patient_name}</b> | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", meta_style))
    story.append(Spacer(1, 14))

    # Patient Vitals Table
    vitals_table_data = [
        [
            Paragraph(f"<b>Age:</b> {patient_vitals.get('age', 'N/A')}", body_style),
            Paragraph(f"<b>Body Temp:</b> {patient_vitals.get('temp', 'N/A')} °C", body_style)
        ],
        [
            Paragraph(f"<b>Blood Pressure:</b> {patient_vitals.get('bp', 'N/A')}", body_style),
            Paragraph(f"<b>Known Allergies:</b> {patient_vitals.get('allergies', 'None')}", body_style)
        ]
    ]
    t = Table(vitals_table_data, colWidths=[270, 270])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F3F4F6')),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#E5E7EB')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
    ]))
    story.append(t)
    story.append(Spacer(1, 14))

    # Symptoms
    story.append(Paragraph("<b>Reported Symptoms:</b>", bold_style))
    story.append(Paragraph(raw_symptoms, body_style))
    story.append(Spacer(1, 12))

    # Urgency & Doctor Card
    urgency = triage_data.get("urgency", "SELF_CARE")
    urgency_color = colors.HexColor('#DC2626') if urgency == "EMERGENCY" else (
        colors.HexColor('#D97706') if urgency == "CONSULT_DOCTOR" else colors.HexColor('#16A34A')
    )
    
    triage_summary_data = [
        [
            Paragraph(f"<b>Acuity Status:</b> <font color='{urgency_color.hexval()}'>{urgency}</font>", body_style),
            Paragraph(f"<b>Recommended Specialist:</b> {triage_data.get('specialist', 'General Physician')}", body_style)
        ]
    ]
    t_summary = Table(triage_summary_data, colWidths=[270, 270])
    t_summary.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#EFF6FF')),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#BFDBFE')),
    ]))
    story.append(t_summary)
    story.append(Spacer(1, 12))

    # Clinical Impression
    story.append(Paragraph("<b>Clinical Assessment:</b>", bold_style))
    story.append(Paragraph(triage_data.get("clinical_assessment", "N/A"), body_style))
    story.append(Spacer(1, 12))

    # Action Items
    if urgency == "EMERGENCY" and triage_data.get("emergency_first_aid"):
        story.append(Paragraph("<b>Immediate Pre-Hospital Measures:</b>", bold_style))
        for step in triage_data["emergency_first_aid"]:
            story.append(Paragraph(f"• {step}", body_style))
        story.append(Spacer(1, 12))
    elif triage_data.get("safe_self_care_or_otc"):
        story.append(Paragraph("<b>Home Care & OTC Guidance:</b>", bold_style))
        for step in triage_data["safe_self_care_or_otc"]:
            story.append(Paragraph(f"• {step}", body_style))
        story.append(Spacer(1, 12))

    # Disclaimer
    disclaimer_style = ParagraphStyle(
        'Disclaimer',
        parent=styles['Italic'],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#9CA3AF')
    )
    story.append(Spacer(1, 18))
    story.append(Paragraph(
        "Notice: This report is generated by an automated clinical triage assistant using NLP. "
        "It does not constitute a formal diagnosis or prescription. Bring this summary to your doctor's appointment.",
        disclaimer_style
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer

# ----------------- LLM SETUP -----------------
llm = ChatGroq(
    model="qwen/qwen3.8-27b",
    temperature=0.1,
    max_tokens=2048
)

STRUCTURED_SYSTEM_PROMPT = """
You are an advanced clinical triage engine. You analyze patient symptoms and return ONLY a valid JSON object matching the exact schema below.

JSON SCHEMA:
{
  "urgency": "EMERGENCY" | "CONSULT_DOCTOR" | "SELF_CARE",
  "specialist": "string (e.g., Cardiologist, General Physician, Pulmonologist, Dermatologist, Orthopedic, ENT, Neurologist)",
  "clinical_assessment": "string (1-2 sentences summarizing clinical findings)",
  "safe_self_care_or_otc": ["string (e.g., Hydration, R.I.C.E. protocol for bruises/sprains, Paracetamol/Acetaminophen for mild pain per manufacturer packaging instructions - never give strict dosage)"],
  "emergency_first_aid": ["string (e.g., Chewable Aspirin 325mg if suspected heart attack and not allergic, Sit upright, Perform CPR if unresponsive, Keep patient calm and warm)"],
  "follow_up_question": "string (one concise question to clarify symptoms if needed)"
}

RULES:
1. If symptoms suggest myocardial infarction (chest pressure, pain radiating to left arm/jaw, severe shortness of breath), severe bleeding, stroke signs (FAST: Face drooping, Arm weakness, Speech difficulty), mark "urgency" as "EMERGENCY".
2. In EMERGENCY cases: Provide clear, actionable first-aid steps to stabilize the patient until emergency services arrive.
3. For minor ailments (mild headache, superficial bruises, common cold, slight fever): Urgency is "SELF_CARE". Recommend standard, safe supportive care (hydration, rest, cold/warm compress, basic OTC symptom relief like acetaminophen/ibuprofen with package instructions warning).
4. For persistent, moderate, or ambiguous issues: Suggest the appropriate specialist doctor to consult.
5. Return ONLY pure JSON. No markdown code fences, no explanations outside the JSON.
"""

# ----------------- SESSION STATE MANAGEMENT -----------------
if "auth_user" not in st.session_state:
    st.session_state.auth_user = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "reg_success_msg" not in st.session_state:
    st.session_state.reg_success_msg = None

# =============================================================
# SCENARIO 1: NOT LOGGED IN -> AUTH SCREEN (LOGIN & REGISTER)
# =============================================================
if not st.session_state.auth_user:
    # Sidebar theme toggle for login screen
    with st.sidebar:
        st.subheader("🎨 Appearance")
        selected_theme = st.radio("Select Theme", ["Dark", "Light"], index=0 if st.session_state.theme == "Dark" else 1, horizontal=True)
        if selected_theme != st.session_state.theme:
            st.session_state.theme = selected_theme
            st.rerun()

    st.title("🩺 MediBot Clinical Platform")
    st.caption("AI-Powered Clinical Triage, Symptom Analysis, & Patient Portal")
    
    auth_tab1, auth_tab2 = st.tabs(["🔑 Log In", "📝 Register New Patient"])
    
    # --- TAB 1: LOGIN ---
    with auth_tab1:
        st.subheader("Patient / Doctor Login")

        # Show registration success notice here if user just registered
        if st.session_state.reg_success_msg:
            st.success(st.session_state.reg_success_msg)
            st.session_state.reg_success_msg = None

        with st.form("login_form"):
            login_username = st.text_input("Username", key="login_u")
            login_password = st.text_input("Password", type="password", key="login_p")
            submit_login = st.form_submit_button("Log In", use_container_width=True, type="primary")

        if submit_login:
            user = authenticate_user(login_username, login_password)
            if user:
                st.session_state.auth_user = {
                    "username": user[0],
                    "full_name": user[1],
                    "role": user[2]
                }
                st.session_state.messages = []
                st.rerun()
            else:
                st.error("Invalid username or password.")
                
        st.info("💡 **Demo Credentials**:\n- **Doctor/Admin**: `admin` / `admin123`")

    # --- TAB 2: REGISTER ---
    with auth_tab2:
        st.subheader("Create a Patient Account")
        
        # clear_on_submit=True resets the fields after submitting
        with st.form("register_form", clear_on_submit=True):
            reg_name = st.text_input("Full Name")
            reg_username = st.text_input("Choose Username")
            reg_password = st.text_input("Choose Password", type="password")
            submit_reg = st.form_submit_button("Register Account", use_container_width=True)

        if submit_reg:
            if reg_name.strip() and reg_username.strip() and reg_password.strip():
                clean_username = reg_username.strip().lower()
                success, msg = register_user(clean_username, reg_password, reg_name.strip())
                if success:
                    st.session_state.reg_success_msg = "✅ Account registered successfully! Please log in above."
                    st.rerun()
                else:
                    st.error(msg)
            else:
                st.warning("Please fill in all registration fields.")

    st.stop()

# =============================================================
# SCENARIO 2: LOGGED IN -> ADMIN / DOCTOR DASHBOARD
# =============================================================
current_user = st.session_state.auth_user

# Sidebar user banner, theme toggle & logout
with st.sidebar:
    st.write(f"Logged in as: **{current_user['full_name']}**")
    st.caption(f"Role: `{current_user['role'].upper()}`")
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🚪 Log Out", use_container_width=True):
            st.session_state.auth_user = None
            st.session_state.messages = []
            st.rerun()
    with col_btn2:
        next_theme = "Light" if st.session_state.theme == "Dark" else "Dark"
        icon = "☀️" if st.session_state.theme == "Dark" else "🌙"
        if st.button(f"{icon} {next_theme}", use_container_width=True):
            st.session_state.theme = next_theme
            st.rerun()
            
    st.divider()

if current_user["role"] == "admin":
    st.title("👨‍⚕️ Clinical Administration & Triage Dashboard")
    st.caption("Live aggregate patient logs, risk distribution, and specialist routing")

    conn = sqlite3.connect(DB_FILE)
    
    # Metrics
    total_triages = conn.execute("SELECT COUNT(*) FROM triage_logs").fetchone()[0]
    total_emergencies = conn.execute("SELECT COUNT(*) FROM triage_logs WHERE urgency_level = 'EMERGENCY'").fetchone()[0]
    total_patients = conn.execute("SELECT COUNT(DISTINCT username) FROM triage_logs").fetchone()[0]
    
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("Total Patients Triaged", total_patients)
    col_m2.metric("Total Triage Assessments", total_triages)
    col_m3.metric("🚨 Active Emergency Flags", total_emergencies)
    
    st.divider()
    
    # Filter / Search Triage Logs
    st.subheader("📋 Patient Triage Registry")
    filter_urgency = st.selectbox("Filter by Urgency Level", ["ALL", "EMERGENCY", "CONSULT_DOCTOR", "SELF_CARE"])
    
    if filter_urgency == "ALL":
        query = "SELECT timestamp, username, urgency_level, specialist, user_input, summary FROM triage_logs ORDER BY id DESC"
        records = conn.execute(query).fetchall()
    else:
        query = "SELECT timestamp, username, urgency_level, specialist, user_input, summary FROM triage_logs WHERE urgency_level = ? ORDER BY id DESC"
        records = conn.execute(query, (filter_urgency,)).fetchall()
    conn.close()

    if records:
        for t, user, urg, spec, user_in, summ in records:
            box = st.container(border=True)
            badge_color = "red" if urg == "EMERGENCY" else "orange" if urg == "CONSULT_DOCTOR" else "green"
            with box:
                col_row1, col_row2 = st.columns([3, 1])
                with col_row1:
                    st.markdown(f"**Patient:** `{user}` | **Timestamp:** {t} | :{badge_color}[**{urg}**]")
                    st.markdown(f"**Reported Symptoms:** *{user_in}*")
                    st.markdown(f"**Assessment:** {summ}")
                with col_row2:
                    st.markdown(f"**Routed Specialist:**<br>`{spec}`", unsafe_allow_html=True)
    else:
        st.info("No logs match the chosen criteria.")

    st.stop()

# =============================================================
# SCENARIO 3: LOGGED IN -> PATIENT TRIAGE ASSISTANT
# =============================================================
with st.sidebar:
    st.header("📋 My Vitals Tracker")
    st.caption("Provide current readings to improve triage accuracy.")
    
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        age = st.number_input("Age", min_value=1, max_value=120, value=28)
    with col_v2:
        temp = st.number_input("Temp (°C)", min_value=34.0, max_value=43.0, value=37.0, step=0.1)
        
    bp = st.text_input("Blood Pressure", value="120/80")
    allergies = st.text_input("Known Allergies", value="None", placeholder="e.g., Penicillin, Ibuprofen")
    
    current_vitals = {
        "age": age,
        "temp": temp,
        "bp": bp,
        "allergies": allergies
    }

    st.divider()
    if st.button("🧹 Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.subheader("📜 My Previous Consultations")
    conn = sqlite3.connect(DB_FILE)
    my_logs = conn.execute(
        "SELECT timestamp, urgency_level, specialist FROM triage_logs WHERE username = ? ORDER BY id DESC LIMIT 5",
        (current_user["username"],)
    ).fetchall()
    conn.close()
    
    if my_logs:
        for t, urg, spec in my_logs:
            badge_color = "red" if urg == "EMERGENCY" else "orange" if urg == "CONSULT_DOCTOR" else "green"
            st.markdown(f"**{t}**<br>:{badge_color}[{urg}] • *{spec}*", unsafe_allow_html=True)
    else:
        st.caption("No consultations logged yet.")

# Main Triage UI
st.title("🩺 MediBot: Healthcare Chatbot using NLP")
st.caption(f"Welcome back, **{current_user['full_name']}**. Describe your symptoms to evaluate urgency and first-aid steps.")

st.warning("⚠️ **Notice:** This assistant is an AI prototype for triage and educational purposes. In life-threatening emergencies (heart attack symptoms, severe bleeding, loss of consciousness), call emergency services (911 / 112 / 108) immediately.")

# Render existing chat conversation
for idx, msg in enumerate(st.session_state.messages):
    if msg["role"] == "user":
        with st.chat_message("user", avatar="👤"):
            st.write(msg["content"])
    else:
        with st.chat_message("assistant", avatar="🩺"):
            data = msg.get("data")
            if data:
                urgency = data.get("urgency", "SELF_CARE")
                
                # Visual Banner
                if urgency == "EMERGENCY":
                    st.error("🚨 **CRITICAL ALERT: IMMEDIATE EMERGENCY CARE REQUIRED**\nPlease contact emergency services immediately.")
                    if data.get("emergency_first_aid"):
                        st.markdown("### 🚑 Emergency Pre-Hospital Measures:")
                        for step in data["emergency_first_aid"]:
                            st.markdown(f"- **{step}**")
                elif urgency == "CONSULT_DOCTOR":
                    st.warning(f"⚠️ **Medical Attention Advised: Consult a {data.get('specialist', 'Doctor')}**")
                else:
                    st.success("🟢 **Low Acuity / Self-Care Suitable**")

                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Recommended Specialist:** `{data.get('specialist', 'General Physician')}`")
                    st.markdown(f"**Clinical Summary:** {data.get('clinical_assessment')}")
                
                with col2:
                    if data.get("safe_self_care_or_otc"):
                        st.markdown("**Home Care & OTC Suggestions:**")
                        for item in data["safe_self_care_or_otc"]:
                            st.markdown(f"- {item}")

                if data.get("follow_up_question"):
                    st.markdown(f"💬 *{data.get('follow_up_question')}*")

                # PDF Download Button
                pdf_bytes = generate_triage_pdf(
                    patient_name=current_user["full_name"],
                    patient_vitals=msg.get("vitals", current_vitals),
                    triage_data=data,
                    raw_symptoms=msg.get("user_query", "Symptom check")
                )
                
                st.download_button(
                    label="📄 Download Doctor Summary (PDF)",
                    data=pdf_bytes,
                    file_name=f"MediBot_Summary_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                    mime="application/pdf",
                    key=f"dl_btn_{idx}"
                )
            else:
                st.write(msg["content"])

# User Chat Input
user_input = st.chat_input("E.g., I have a burning pain in my chest, or bumped my elbow and have a minor bruise...")

if user_input:
    # 1. Display user query
    with st.chat_message("user", avatar="👤"):
        st.write(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    # Prepare Context
    vitals_context = f"[Patient Context: Name={current_user['full_name']}, Age={age}, Temperature={temp}°C, Blood Pressure={bp}, Allergies={allergies}]"
    
    # 2. Invoke LLM for Structured Triage
    with st.chat_message("assistant", avatar="🩺"):
        with st.spinner("Analyzing symptoms & triage protocols..."):
            try:
                system_instruction = SystemMessage(content=STRUCTURED_SYSTEM_PROMPT)
                prompt_messages = [system_instruction]
                
                # Context buffer
                for m in st.session_state.messages[-3:]:
                    if m["role"] == "user":
                        prompt_messages.append(HumanMessage(content=m["content"]))
                    elif "data" in m:
                        prompt_messages.append(AIMessage(content=json.dumps(m["data"])))

                prompt_messages.append(HumanMessage(content=f"{vitals_context} Symptoms: {user_input}"))

                response = llm.invoke(prompt_messages)
                raw_text = response.content

                # Strip potential Qwen reasoning tags
                if "</think>" in raw_text:
                    raw_text = raw_text.split("</think>")[-1].strip()

                # Clean markdown code blocks
                cleaned_json = raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                data = json.loads(cleaned_json)

                # Render response
                urgency = data.get("urgency", "SELF_CARE")
                if urgency == "EMERGENCY":
                    st.error("🚨 **CRITICAL ALERT: IMMEDIATE EMERGENCY CARE REQUIRED**\nPlease contact emergency services immediately.")
                    if data.get("emergency_first_aid"):
                        st.markdown("### 🚑 Emergency Pre-Hospital Measures:")
                        for step in data["emergency_first_aid"]:
                            st.markdown(f"- **{step}**")
                elif urgency == "CONSULT_DOCTOR":
                    st.warning(f"⚠️ **Medical Attention Advised: Consult a {data.get('specialist', 'Doctor')}**")
                else:
                    st.success("🟢 **Low Acuity / Self-Care Suitable**")

                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Recommended Specialist:** `{data.get('specialist', 'General Physician')}`")
                    st.markdown(f"**Clinical Summary:** {data.get('clinical_assessment')}")
                
                with col2:
                    if data.get("safe_self_care_or_otc"):
                        st.markdown("**Home Care & OTC Suggestions:**")
                        for item in data["safe_self_care_or_otc"]:
                            st.markdown(f"- {item}")

                if data.get("follow_up_question"):
                    st.markdown(f"💬 *{data.get('follow_up_question')}*")

                # Generate PDF
                pdf_bytes = generate_triage_pdf(
                    patient_name=current_user["full_name"],
                    patient_vitals=current_vitals,
                    triage_data=data,
                    raw_symptoms=user_input
                )
                
                st.download_button(
                    label="📄 Download Doctor Summary (PDF)",
                    data=pdf_bytes,
                    file_name=f"MediBot_Summary_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                    mime="application/pdf",
                    key=f"dl_btn_{len(st.session_state.messages)}"
                )

                # Log to DB under the logged-in patient's username
                log_triage(
                    username=current_user["username"],
                    user_input=user_input,
                    urgency=urgency,
                    specialist=data.get("specialist", "General Physician"),
                    summary=data.get("clinical_assessment", "")
                )

                # Append to session state
                st.session_state.messages.append({
                    "role": "assistant",
                    "data": data,
                    "vitals": current_vitals,
                    "user_query": user_input,
                    "content": ""
                })

            except json.JSONDecodeError:
                fallback_msg = "Could not generate a structured assessment. Please elaborate on your symptoms in more detail."
                st.write(fallback_msg)
                st.session_state.messages.append({"role": "assistant", "content": fallback_msg})
            except Exception as e:
                st.error(f"Error processing clinical query: {e}")