"""Public chat boundaries adapted from kenya-afya-bot's query guard."""
import re


def response(status: str, reason: str, answer: str) -> dict:
    return {"status": status, "reason": reason, "answer": answer, "citations": []}


def before_retrieval(question: str) -> dict | None:
    q = question
    if re.search(r"\b(i|my|me)\b", q, re.I) and re.search(r"\b(fever|bleeding|hemorrhag\w*)\b", q, re.I):
        return response("declined", "urgent_personal_symptoms",
                        "I cannot assess your symptoms here. Please seek prompt help from a qualified local health service and follow its instructions.")
    if re.search(r"\b(what is this app|what does this app do|what can afya msaada do|how does this chatbot work)\b", q, re.I):
        return response("answered", "app_help",
                        "Afya Msaada searches approved local Ebola and Marburg PDFs and links cited pages. It may ask for clarification or decline when it cannot support an answer. It does not diagnose illness or provide live outbreak updates.")
    if re.search(r"\b(nini|dalili|ninaweza|nifanye|nikihisi|kusalimiana)\b", q, re.I):
        return response("declined", "language_not_reviewed",
                        "Kwa sasa, majibu ya Kiswahili hayajapitiwa kwa usahihi wa kitabibu. Tafadhali uliza kwa Kiingereza au wasiliana na mhudumu wa afya aliyehitimu.")
    if re.search(r"\b(today|now|current|currently|latest|live|this week)\b", q, re.I):
        return response("declined", "current_information_unavailable",
                        "I cannot verify current outbreak information from this local document collection. Check the relevant health authority's latest update.")
    if re.search(r"\b(airborne|through the air|air like measles)\b", q, re.I):
        return response("declined", "transmission_claim_needs_review",
                        "I cannot verify that transmission comparison from the approved passages. Consult current public-health guidance for the named disease.")
    if re.search(r"\b(i|my|me|we|our)\b", q, re.I) and re.search(r"\b(exposed|symptoms|sick|infected|diagnos\w*|treat\w*|isolat\w*|suspect|have\s+(?:ebola|marburg)|will\s+i\s+die)\b", q, re.I):
        return response("declined", "personal_medical_advice",
                        "I cannot assess whether you have Ebola or predict your outcome. If you suspect infection or have concerning symptoms, seek prompt advice from a qualified local health service and follow its instructions.")
    if re.search(r"\b(?:dose|dosage|how much medicine)\b", q, re.I):
        return response("declined", "individual_treatment_request",
                        "I cannot recommend a medicine or dose. Please ask a qualified clinician.")
    if re.search(r"\b(?:case management|clinical management)\b", q, re.I) and not re.search(r"\b(?:symptoms|testing|triage|treatment|fluids|infection prevention)\b", q, re.I):
        return response("clarify", "broad_clinical_guidance",
                        "Which part of case management do you mean? The supplied guidelines cover many clinical and facility procedures. Please name the topic and whether you need a public explanation or professional guidance.")
    if not re.search(r"\b(ebola|marburg|bundibugyo|filovirus|orthoebolavirus|orthomarburgvirus)\b", q, re.I):
        if re.search(r"\b(symptom|spread|transmiss|testing|diagnos|treat|vaccine|mortality|fatality)\w*\b", q, re.I):
            return response("clarify", "disease_unspecified", "Which disease do you mean? Please name Ebola, Marburg, or Bundibugyo disease.")
        return response("declined", "outside_source_scope", "I can only answer questions about the approved Ebola and Marburg source documents.")
    return None


def before_model(question: str) -> dict | None:
    if re.search(r"\b(vaccine|vaccination|immunization|immunisation)\w*\b", question, re.I):
        return response("declined", "current_vaccine_guidance_needed",
                        "The supplied PDFs cannot establish vaccine availability or eligibility for your situation. Ask the relevant health authority for current guidance on the specific virus.")
    if (re.search(r"\b(ebola|bundibugyo)\b", question, re.I)
            and re.search(r"\bmarburg\b", question, re.I)
            and re.search(r"\b(compare|versus|vs|differ|difference|vary from)\b", question, re.I)):
        return response("declined", "comparison_needs_review",
                        "I cannot verify a reliable comparison of Ebola and Marburg from the selected passages. Please consult the full approved guidance or ask a qualified health professional.")
    if re.search(r"\b(specimen|assay|intravenous|resuscitation|PPE|protective equipment|isolat\w*|quarantin\w*|case definition|diagnos\w*|clinical guideline|IPC guideline|laboratory testing|medication|medicine|therapy|treat\w*)\b", question, re.I):
        return response("declined", "professional_clinical_guidance",
                        "This asks for clinical or infection-control guidance that needs a qualified professional and the full current protocol. I cannot safely summarize it for an individual in this public chat prototype.")
    return None
