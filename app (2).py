
import os, tempfile
from datetime import datetime
from xml.sax.saxutils import escape
import gradio as gr
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

def confidence_score(decision, evidence, uncertainty):
    # Transparent completeness heuristic, NOT a calibrated AI probability.
    score = 0.20
    d, e, u = (decision or "").strip(), (evidence or "").strip().lower(), (uncertainty or "").strip().lower()
    score += 0.20 if len(d) >= 35 else 0.10 if len(d) >= 12 else 0
    score += 0.35 if len(e) >= 120 else 0.25 if len(e) >= 50 else 0.12 if len(e) >= 15 else 0
    markers = ["data", "report", "study", "source", "test", "budget", "result", "document", "verified"]
    score += min(sum(word in e for word in markers), 3) * 0.05
    if u:
        score -= 0.05
        if any(x in u for x in ["unknown", "not sure", "missing", "unclear", "unverified"]): score -= 0.10
    score = round(max(0.05, min(0.95, score)), 2)
    return score, ("High" if score >= 0.70 else "Medium" if score >= 0.45 else "Low")

def risk_score(impact, reversibility, people, decision, evidence):
    score = {"Low":0.15,"Medium":0.45,"High":0.75,"Critical":0.95}.get(impact,0.45)
    reasons = [f"Selected impact level: {impact}."]
    if reversibility == "Difficult to reverse":
        score += 0.12; reasons.append("The action may be difficult to reverse.")
    elif reversibility == "Irreversible":
        score += 0.20; reasons.append("The action is described as irreversible.")
    if people == "A small group":
        score += 0.05; reasons.append("The decision may affect a group of people.")
    elif people == "Many people":
        score += 0.12; reasons.append("The decision may affect many people.")
    text = f"{decision or ''} {evidence or ''}".lower()
    words = {"medical":0.15,"health":0.15,"surgery":0.20,"legal":0.15,"lawsuit":0.15,
      "financial loss":0.15,"investment":0.10,"employment":0.15,"hiring":0.15,
      "firing":0.20,"safety":0.20,"emergency":0.20,"personal data":0.15,"child":0.15,"criminal":0.20}
    found = [w for w in words if w in text]
    if found:
        score += min(0.25, sum(words[w] for w in found))
        reasons.append("Potentially high-impact topic(s) detected: " + ", ".join(found) + ".")
    score = round(max(0.05,min(0.99,score)),2)
    level = "Critical" if score >= .85 else "High" if score >= .65 else "Medium" if score >= .35 else "Low"
    return score, level, reasons

def decide(conf, risk):
    if risk >= .70 or conf < .40:
        return "REQUEST HUMAN REVIEW", "Potential consequences are high, or the information is too limited. A qualified person should review this before action."
    if conf >= .65 and risk <= .35:
        return "PROCEED", "The supplied information is reasonably complete and the indicated consequence risk is low. Check the inputs and applicable rules before acting."
    return "VERIFY BEFORE PROCEEDING", "The evidence and risk profile are mixed. Verify important facts, gather missing evidence, and reassess before acting."

def analyze(decision,evidence,impact,reversibility,people,uncertainty,history):
    decision=(decision or "").strip()
    if len(decision)<5: raise gr.Error("Please describe the decision in at least a few words.")
    conf,cl=confidence_score(decision,evidence,uncertainty)
    risk,rl,reasons=risk_score(impact,reversibility,people,decision,evidence)
    outcome,explanation=decide(conf,risk)
    item={"time":datetime.now().strftime("%Y-%m-%d %H:%M"),"decision":decision,"evidence":evidence or "Not provided",
      "confidence":conf,"confidence_level":cl,"risk":risk,"risk_level":rl,"impact":impact,
      "reversibility":reversibility,"people":people,"outcome":outcome,"explanation":explanation,
      "reasons":reasons,"uncertainty":uncertainty or "Not provided"}
    history=list(history or []); history.insert(0,item); history=history[:20]
    color="#22c55e" if outcome=="PROCEED" else "#f59e0b" if outcome.startswith("VERIFY") else "#ef4444"
    final_html=f'''<div class="result" style="border-color:{color}"><div class="kicker">FINAL DECISION</div>
      <div class="outcome" style="color:{color}">{escape(outcome)}</div><p>{escape(explanation)}</p>
      <small>Decision-support guidance only. Human judgment remains essential.</small></div>'''
    conf_html=f'''<div class="metric"><b>CONFIDENCE ASSESSMENT</b><div class="score">{conf:.2f}<small> / 1.00</small></div>
      <p>Level: <b>{cl}</b></p><div class="bar"><i style="width:{conf*100}%"></i></div></div>'''
    risk_html=f'''<div class="metric risk"><b>CONSEQUENCE RISK</b><div class="score">{risk:.2f}<small> / 1.00</small></div>
      <p>Level: <b>{rl}</b></p><div class="bar"><i style="width:{risk*100}%"></i></div></div>'''
    explanation_md=(f"**Why this result?** {explanation}\n\n**Confidence:** {conf:.2f} ({cl}). This is a completeness heuristic, not a statistical probability.\n\n"
      f"**Risk factors:** "+" ".join(reasons)+"\n\n**Limitations:** This prototype uses explicit rules and keyword checks. It can miss context or flag terms incorrectly.")
    rows=[[x["time"],x["decision"][:55],f'{x["confidence"]:.2f}',f'{x["risk"]:.2f}',x["outcome"]] for x in history]
    return final_html,conf_html,risk_html,explanation_md,rows,history,item

def make_pdf(item):
    if not item: raise gr.Error("Analyze a decision before downloading a report.")
    path=os.path.join(tempfile.gettempdir(),"ccdf_report_"+datetime.now().strftime("%Y%m%d_%H%M%S")+".pdf")
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CCDFTitle",parent=styles["Title"],textColor=colors.HexColor("#087bd5"),alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="NoteSmall",parent=styles["BodyText"],fontSize=8,textColor=colors.HexColor("#555555")))
    doc=SimpleDocTemplate(path,pagesize=A4,rightMargin=42,leftMargin=42,topMargin=42,bottomMargin=42)
    story=[Paragraph("CCDF – AI Decision Guardian",styles["CCDFTitle"]),Paragraph("Decision Assessment Report",styles["Heading2"]),Spacer(1,12),
      Paragraph("<b>Date:</b> "+escape(item["time"]),styles["BodyText"]),Paragraph("<b>Decision:</b> "+escape(item["decision"]),styles["BodyText"]),Spacer(1,12)]
    data=[["Assessment","Result"],["Confidence",f'{item["confidence"]:.2f} ({item["confidence_level"]})'],
      ["Consequence risk",f'{item["risk"]:.2f} ({item["risk_level"]})'],["Impact",item["impact"]],
      ["Reversibility",item["reversibility"]],["People affected",item["people"]],["Final recommendation",item["outcome"]]]
    table=Table(data,colWidths=[150,340])
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#10294b")),("TEXTCOLOR",(0,0),(-1,0),colors.white),
      ("GRID",(0,0),(-1,-1),.5,colors.HexColor("#cbd5e1")),("BACKGROUND",(0,1),(-1,-1),colors.HexColor("#f3f7fc")),
      ("PADDING",(0,0),(-1,-1),8),("VALIGN",(0,0),(-1,-1),"TOP")]))
    story += [table,Spacer(1,16),Paragraph("Decision explanation",styles["Heading2"]),Paragraph(escape(item["explanation"]),styles["BodyText"]),Spacer(1,10),Paragraph("Risk factors",styles["Heading2"])]
    for reason in item["reasons"]: story.append(Paragraph("• "+escape(reason),styles["BodyText"]))
    story += [Spacer(1,16),Paragraph("Limitations: This is a rule-based prototype. Scores are heuristic indicators, not calibrated probabilities or professional advice. Seek qualified human review for high-impact decisions.",styles["NoteSmall"])]
    doc.build(story); return path

CSS = r'''
.gradio-container {max-width:1180px!important;background:#071326!important;color:#eaf2ff!important}
body {background:#071326!important}
#hero {padding:22px 26px;border:1px solid #174b83;border-radius:18px;background:linear-gradient(120deg,#0a2344,#071326 75%)}
#hero h1 {color:#35b8ff;margin:0 0 6px}
#hero p {color:#c9ddf5;margin:0}
.panel {border:1px solid #24466f!important;border-radius:16px!important;background:#0c1d35!important}
.metric {padding:18px;border-radius:14px;min-height:135px;background:#0c2540;border:1px solid #1485a7}
.metric.risk {background:#292315;border-color:#d99b22}
.metric b {color:#c5def8}
.score {font-size:38px;font-weight:800;margin-top:10px}
.score small {font-size:13px;color:#9db4ce}
.bar {height:8px;background:#263d58;border-radius:20px;overflow:hidden}
.bar i {display:block;height:100%;background:linear-gradient(90deg,#16a7f5,#31e0a0)}
.risk .bar i {background:linear-gradient(90deg,#f8c33d,#f97316)}
.result {border:2px solid;border-radius:16px;padding:20px;background:linear-gradient(110deg,#0b2d39,#0b1b30)}
.kicker {font-size:12px;letter-spacing:.14em;color:#a9c4e3;font-weight:700}
.outcome {font-size:clamp(23px,4vw,34px);font-weight:900;margin:8px 0}
.result p {color:#e0ecf8}
.result small {color:#9db4ce}
footer {display:none!important}
'''

with gr.Blocks(title="CCDF – AI Decision Guardian",theme=gr.themes.Soft(primary_hue="blue",neutral_hue="slate"),css=CSS) as demo:
    state=gr.State([]); latest=gr.State(None)
    gr.HTML("<div id='hero'><h1>🛡️ CCDF – AI Decision Guardian</h1><p>Assess • Understand • Decide | Transparent decision-support prototype</p></div>")
    with gr.Row():
        with gr.Column(scale=3):
            with gr.Group(elem_classes=["panel"]):
                gr.Markdown("### Enter Your Decision")
                decision=gr.Textbox(label="Decision or situation",placeholder="e.g. Should our team launch this new project?",lines=2,max_lines=4)
                evidence=gr.Textbox(label="Supporting evidence",placeholder="Describe facts, reports, tests, data, or sources supporting this decision.",lines=3)
                uncertainty=gr.Textbox(label="Known uncertainties or missing information",placeholder="What is unknown, unclear, or still needs checking?",lines=2)
                with gr.Row():
                    impact=gr.Dropdown(["Low","Medium","High","Critical"],value="Medium",label="Potential impact")
                    reversibility=gr.Dropdown(["Easy to reverse","Difficult to reverse","Irreversible"],value="Easy to reverse",label="Can it be reversed?")
                    people=gr.Dropdown(["Only me","A small group","Many people"],value="Only me",label="Who may be affected?")
                run=gr.Button("⚡ Analyze Decision",variant="primary",size="lg")
        with gr.Column(scale=2):
            gr.Markdown("### Assessment Overview")
            conf_out=gr.HTML("<div class='metric'><b>CONFIDENCE ASSESSMENT</b><p>Run an analysis to see the score.</p></div>")
            risk_out=gr.HTML("<div class='metric risk'><b>CONSEQUENCE RISK</b><p>Run an analysis to see the score.</p></div>")
    final_out=gr.HTML("<div class='result' style='border-color:#2d5b83'><div class='kicker'>FINAL DECISION</div><p>Your recommendation will appear here after analysis.</p></div>")
    with gr.Group(elem_classes=["panel"]):
        gr.Markdown("### Decision Explanation")
        explanation_out=gr.Markdown("The system will explain the assessment after analysis.")
    with gr.Group(elem_classes=["panel"]):
        gr.Markdown("### Decision History (this session)")
        history_out=gr.Dataframe(headers=["Date & Time","Decision","Confidence","Risk","Final Result"],datatype=["str","str","str","str","str"],interactive=False,value=[])
        with gr.Row():
            pdf_btn=gr.Button("⬇️ Download PDF Report")
            pdf_file=gr.File(label="Your report",interactive=False)
            clear_btn=gr.Button("Clear Session History",variant="secondary")
    gr.Markdown("> **Important:** This is an early rule-based prototype, not a validated AI model. Scores are heuristic indicators, not probabilities. For medical, legal, financial, employment, safety, or other high-impact matters, always obtain qualified human review.")
    run.click(analyze,inputs=[decision,evidence,impact,reversibility,people,uncertainty,state],outputs=[final_out,conf_out,risk_out,explanation_out,history_out,state,latest])
    pdf_btn.click(make_pdf,inputs=[latest],outputs=[pdf_file])
    clear_btn.click(lambda: ([],[]),outputs=[state,history_out])

demo.launch()
