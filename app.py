from flask import Flask, request, jsonify, render_template, make_response
from flask_cors import CORS
import requests
from openai import OpenAI
import json


app = Flask(__name__)
CORS(app, supports_credentials=True)

@app.route("/version")
def version():
    return "Deployed version with CORS is active"



# ✅ Your OpenAI API key
client = OpenAI(api_key="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")

FDA_API_ENDPOINT = "https://api.fda.gov/drug/event.json"

def get_rxcui_and_name(drug_name):
    url = f"https://rxnav.nlm.nih.gov/REST/approximateTerm.json?term={drug_name}&maxEntries=1"
    response = requests.get(url)
    if response.status_code == 200:
        try:
            candidates = response.json().get("approximateGroup", {}).get("candidate", [])
            if candidates:
                rxcui = candidates[0].get("rxcui")
                name_url = f"https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/properties.json"
                name_resp = requests.get(name_url)
                if name_resp.status_code == 200:
                    name = name_resp.json().get("properties", {}).get("name", drug_name)
                    return rxcui, name
                return rxcui, drug_name
        except:
            pass
    return None, drug_name

def get_interaction(rxcui1, rxcui2):
    url = f"https://rxnav.nlm.nih.gov/REST/interaction/list.json?rxcuis={rxcui1}+{rxcui2}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    return None

def fetch_fda_data(drug_name, limit=3):
    try:
        response = requests.get(FDA_API_ENDPOINT, params={
            "search": f"patient.drug.medicinalproduct:{drug_name}",
            "limit": limit
        })
        if response.status_code == 200:
            return response.json().get("results", [])
    except:
        return []
    return []

def generate_gpt_summary(drugs_with_data):
    prompt = (
        "You are a drug safety summarizer. For each drug, summarize the adverse events into the following categories:\n"
        "- Cardiovascular Effects\n"
        "- Gastrointestinal Effects\n"
        "- Neurological Effects\n"
        "- Hematologic Effects\n"
        "- Renal Effects\n"
        "- Pregnancy & Neonatal Risks\n"
        "- Other Side Effects\n"
        "- Summary\n"
        "- Risk Notes\n"
        "- Interaction Comments\n"
        "Return only the JSON. Do not use bullet points, labels, markdown, or explanations."
    )

    for drug, data in drugs_with_data.items():
        prompt += f"\n\nDrug: {drug}\nReported reactions:\n"
        for event in data:
            reactions = event.get("patient", {}).get("reaction", [])
            reaction_texts = ", ".join(r.get("reactionmeddrapt", "") for r in reactions)
            prompt += f"- {reaction_texts or 'No data'}"

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a drug safety summarizer."},
            {"role": "user", "content": prompt}
        ]
    )

    try:
        raw_response = response.choices[0].message.content
        parsed = json.loads(raw_response)

        # Fix format if GPT returns {"Drug": "X", "Adverse Events": {...}}
        if "Drug" in parsed and "Adverse Events" in parsed:
            parsed = {
                parsed["Drug"]: parsed["Adverse Events"]
            }

        if not isinstance(parsed, dict):
            return f"<div><strong>Error:</strong> GPT response was not a valid JSON object. Raw: <pre>{raw_response}</pre></div>"

        html_output = ""
        for drug, sections in parsed.items():
            html_output += f"<div><strong>Drug:</strong> {drug}</div>"
            for label, value in sections.items():
                if isinstance(value, dict) and "Reported Adverse Events" in value:
                     events = value["Reported Adverse Events"]
                     html_output += f"<div><strong>{label}:</strong> {', '.join(events) if events else 'None'}</div>"
                    
                elif isinstance(value, list):
                    html_output += f"<div><strong>{label}:</strong> {', '.join(value) if value else 'None'}</div>"
                else:
                    html_output += f"<div><strong>{label}:</strong> {value}</div>"
            
        return html_output

    except Exception as e:
        return (
            f"<div><strong>Error:</strong> Could not parse GPT response. {str(e)}"
            f"<br><br><strong>Raw response:</strong><br><pre>{response.choices[0].message.content}</pre></div>"
        )

def explain_interaction_with_gpt(interaction):
    drug1 = interaction['drug1'].capitalize()
    drug2 = interaction['drug2'].capitalize()

    prompt = f"""
    Drug 1: {drug1}
    Drug 2: {drug2}
    Severity: {interaction['severity']}
    Description: {interaction['description']}

    Provide a structured clinical summary using:
    - Interaction Risk
    - Mechanism
    - When Co-administration May Be Justified
    - Severity Risk
    """

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a clinical pharmacist."},
            {"role": "user", "content": prompt}
        ]
    )

    raw_text = response.choices[0].message.content
    lines = raw_text.strip().splitlines()
    output_html = ""

    severity_text = ""
    for line in lines:
        if ":" in line:
            label, value = line.split(":", 1)
            label = label.strip()
            value = value.strip()
            if label.lower() == "severity risk":
                severity_text = value.lower()
            output_html += f"<div style='margin-bottom: 8px; text-align: left;'><strong>{label}:</strong> {value}</div>"

    if "high" in severity_text or "major" in severity_text:
        emoji = "🔴"
        level = "Major"
    elif "moderate" in severity_text:
        emoji = "🟡"
        level = "Moderate"
    elif "low" in severity_text or "minor" in severity_text:
        emoji = "🟢"
        level = "Minor"
    else:
        emoji = "⚪"
        level = "Unspecified"

    drug_header = f"<h2 style='font-size: 30px; font-weight: bold;'>{drug1} + {drug2}</h2>"
    risk_header = f"<div style='font-size:18px; font-weight:bold; margin-bottom:20px;'>{emoji} Interaction Risk: {level}</div>"
    reference = "<div style='margin-top: 20px; font-size: 14px; color: #777;'>Source: FDA Adverse Event Reporting System (FAERS) and RxNav Database</div>"

    return drug_header + risk_header + output_html + reference

def explain_no_interaction_with_gpt(drug1, drug2):
    drug1 = drug1.capitalize()
    drug2 = drug2.capitalize()

    prompt = f"""
    A patient is taking both {drug1} and {drug2}. No interaction is listed in the RxNav database.

    As a clinical pharmacist, provide a detailed interaction summary based on pharmacologic knowledge.

    Format the response using only these categories:
    Interaction Risk: ...
    Mechanism: ...
    When Co-administration May Be Justified: ...
    Severity Risk: ...
    """

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a clinical pharmacist generating official interaction summaries."},
            {"role": "user", "content": prompt}
        ]
    )

    raw_text = response.choices[0].message.content
    lines = raw_text.strip().splitlines()
    output_html = ""

    severity_text = ""
    for line in lines:
        if ":" in line:
            label, value = line.split(":", 1)
            label = label.strip()
            value = value.strip()
            if label.lower() == "severity risk":
                severity_text = value.lower()
            output_html += f"<div style='margin-bottom: 8px; text-align: left;'><strong>{label}:</strong> {value}</div>"

    if "high" in severity_text or "major" in severity_text:
        emoji = "🔴"
        level = "Major"
    elif "moderate" in severity_text:
        emoji = "🟡"
        level = "Moderate"
    elif "low" in severity_text or "minor" in severity_text:
        emoji = "🟢"
        level = "Minor"
    else:
        emoji = "⚪"
        level = "Unspecified"

    drug_header = f"<h2 style='font-size: 24px; font-weight: bold;'>{drug1} + {drug2}</h2>"
    risk_header = f"<div style='font-size:18px; font-weight:bold; margin-bottom:20px;'>{emoji} Interaction Risk: {level}</div>"
    reference = "<div style='margin-top: 20px; font-size: 14px; color: #777;'>Source: FDA Adverse Event Reporting System (FAERS) and RxNav Database</div>"

    return drug_header + risk_header + output_html + reference

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/get", methods=["POST"])
def get_bot_response():
    user_input = request.json.get("msg", "")
    request_type = request.json.get("type", "interaction")

    try:
        if request_type == "interaction":
            if " and " not in user_input.lower():
                return jsonify({"response": "<p><strong>⚠️ Please enter two drugs to check interactions.</strong></p>"})

            parts = user_input.lower().replace("interaction between", "").split(" and ")
            if len(parts) != 2:
                return jsonify({"response": "<p><strong>❌ Invalid input format.</strong></p>"})

            drug1_input, drug2_input = parts[0].strip(), parts[1].strip()
            rxcui1, drug1 = get_rxcui_and_name(drug1_input)
            rxcui2, drug2 = get_rxcui_and_name(drug2_input)

            print(f"[DEBUG] Resolved: {drug1_input} → {drug1} (RxCUI: {rxcui1})")
            print(f"[DEBUG] Resolved: {drug2_input} → {drug2} (RxCUI: {rxcui2})")

            if not rxcui1 or not rxcui2:
                return jsonify({"response": "<p><strong>⚠️ One or both drugs not found. Please try again.</strong></p>"})

            data = get_interaction(rxcui1, rxcui2)
            print("[DEBUG] Raw interaction data:", json.dumps(data, indent=2))

            try:
                groups = data.get("fullInteractionTypeGroup", [])
                if groups:
                    interactions = groups[0].get("fullInteractionType", [])
                    if interactions:
                        pair = interactions[0].get("interactionPair", [])[0]
                        interaction = {
                            "drug1": drug1,
                            "drug2": drug2,
                            "description": pair.get("description", "Not provided."),
                            "severity": pair.get("severity", "Unknown")
                        }
                        gpt_response = explain_interaction_with_gpt(interaction)
                        return jsonify({"response": gpt_response})
            except Exception as e:
                print("[ERROR] Parsing interaction:", e)

            gpt_response = explain_no_interaction_with_gpt(drug1, drug2)
            return jsonify({"response": gpt_response})

        elif request_type == "event":
            drugs = [d.strip().capitalize() for d in user_input.lower().replace("adverse events for", "").split(" and ")]
            drugs_with_data = {}

            for drug in drugs:
                events = fetch_fda_data(drug)
                if not events:
                    events = [{"patient": {"reaction": [{"reactionmeddrapt": "No data found"}]}}]
                drugs_with_data[drug] = events

            gpt_response = generate_gpt_summary(drugs_with_data)
            return jsonify({"response": gpt_response})

        else:
            return jsonify({"response": "⚠️ Unknown request type."})

    except Exception as e:
        return jsonify({"response": f"⚠️ Server error: {str(e)}"})

if __name__ == "__main__":
    app.run(debug=True)
