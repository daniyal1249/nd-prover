from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from nd_prover import *


app = Flask(
    __name__,
    template_folder="site/templates",
    static_folder="site/static",
    static_url_path="/static",
)


@app.after_request
def add_cache_control(response):
    """Add cache-control headers to static file responses."""
    if request.path.startswith("/static/"):
        # In production, cache static assets for 1 day
        if app.debug:
            response.cache_control.no_cache = True
            response.cache_control.no_store = True
            response.cache_control.must_revalidate = True
        else:
            response.cache_control.max_age = 86400
            response.cache_control.public = True
    return response


@app.get("/robots.txt")
def robots_txt():
    """Robots.txt for search engines."""
    lines = [
        "User-agent: *",
        "Allow: /",
        "Sitemap: https://ndprover.org/sitemap.xml",
        "",
    ]
    body = "\n".join(lines)
    return body, 200, {"Content-Type": "text/plain"}


def _json_error(message: str, *, status: str = "error", code: int = 400):
    """Return a standardized JSON error response."""
    return jsonify({"ok": False, "status": status, "message": message}), code


def _extract_problem_fields(data):
    """Extract logic label and problem text fields from a JSON payload."""
    logic_name = (data.get("logic") or "").strip()
    premises_text = data.get("premisesText") or ""
    conclusion_text = data.get("conclusionText") or ""
    return logic_name, premises_text, conclusion_text


def _resolve_logic(logic_name):
    """Resolve the logic implementation from its label, or return an error message."""
    logic = logics.get(logic_name)
    if logic is None:
        message = f'Logic not recognized: "{logic_name}".'
        return None, message
    return logic, None


def _serialize_proof(proof):
    """Serialize a Proof object to the frontend format.
    
    Returns a list of line objects with the structure:
    {
        indent: int,
        text: str,
        justText: str,
        isAssumption: bool,
        isPremise: bool,
    }
    """
    lines = []
    
    def traverse(obj, indent=0, is_premise=False):
        """Recursively traverse proof objects."""
        if obj.is_line():
            formula_str = str(obj.formula)
            just_str = str(obj.justification)
            is_assumption = obj.justification.rule is Rules.AS
            # Check if this is a premise (PR rule) or was marked as premise from context
            is_premise_line = is_premise or obj.justification.rule is Rules.PR
            
            lines.append({
                'indent': indent,
                'text': formula_str,
                'justText': just_str,
                'isAssumption': is_assumption,
                'isPremise': is_premise_line,
            })
        else:
            # Process assumption line (first line of subproof) at indent + 1
            subproof_indent = indent + 1
            if obj.seq and obj.seq[0].is_line():
                assumption_line = obj.seq[0]
                formula_str = str(assumption_line.formula)
                just_str = str(assumption_line.justification)
                
                lines.append({
                    'indent': subproof_indent,
                    'text': formula_str,
                    'justText': just_str,
                    'isAssumption': True,
                    'isPremise': False,
                })
                
                # Process remaining lines in subproof at the same indent level
                for item in obj.seq[1:]:
                    traverse(item, subproof_indent, False)
            else:
                # Process all items in subproof at increased indent
                for item in obj.seq:
                    traverse(item, subproof_indent, False)

    for obj in proof.context:
        is_premise = obj.is_line() and obj.justification.rule is Rules.PR
        traverse(obj, 0, is_premise=is_premise)
    for obj in proof.seq:
        traverse(obj, 0, is_premise=False)
    
    return lines


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/exercises/tfl")
def exercises_tfl():
    return render_template("exercises_tfl.html")


@app.get("/exercises/fol")
def exercises_fol():
    return render_template("exercises_fol.html")


@app.get("/exercises/ml")
def exercises_ml():
    return render_template("exercises_ml.html")


@app.get("/rules")
def rules():
    return render_template("rules.html")


@app.post("/api/check-proof")
def check_proof():
    data = request.get_json(silent=True) or {}
    logic_name, premises_text, conclusion_text = _extract_problem_fields(data)
    logic, error_message = _resolve_logic(logic_name)
    line_payloads = data.get("lines") or []

    if logic is None:
        return _json_error(error_message)

    try:
        premises = parse_and_verify_premises(premises_text, logic)
        conclusion = parse_and_verify_formula(conclusion_text, logic)
    except ParsingError as e:
        return _json_error(str(e))

    problem = Problem(logic, premises, conclusion)

    for payload in line_payloads:
        kind = payload.get("kind")
        raw = (payload.get("raw") or "").strip()
        line_no = payload.get("lineNumber")
        formula_text = (payload.get("formulaText") or "").strip()
        just_text = (payload.get("justText") or "").strip()

        prefix = f"Line {line_no}: " if line_no is not None else ""

        # Premises are already encoded in the initial Problem context.
        if kind == "premise":
            continue

        # Assumptions / end-and-begin only carry a formula.
        if kind in {"assumption", "end_and_begin"}:
            if not formula_text:
                message = prefix + "Formula is missing."
                return _json_error(message)
            try:
                assumption = parse_assumption(formula_text)
            except ParsingError as e:
                message = prefix + str(e)
                return _json_error(message)

            if kind == "assumption":
                try:
                    problem.begin_subproof(assumption)
                except Exception as e:
                    message = prefix + str(e)
                    return _json_error(message)
            else:  # end_and_begin
                try:
                    problem.end_and_begin_subproof(assumption)
                except Exception as e:
                    message = prefix + str(e)
                    return _json_error(message)
            continue

        # All other kinds should have both formula and justification.
        if not formula_text:
            message = prefix + "Formula is missing."
            return _json_error(message)
        if not just_text:
            message = prefix + "Justification is missing."
            return _json_error(message)
        if not raw:
            raw = f"{formula_text}; {just_text}"

        try:
            formula, justification = parse_line(raw)
        except ParsingError as e:
            message = prefix + str(e)
            return _json_error(message)

        try:
            if kind == "line":
                problem.add_line(formula, justification)
            elif kind == "close_subproof":
                problem.end_subproof(formula, justification)
        except Exception as e:
            message = prefix + str(e)
            return _json_error(message)

    if errors := problem.errors():
        message = "\n".join(errors)
        return _json_error(message)
    is_complete = problem.conclusion_reached()

    if is_complete:
        message = "Proof complete! 🎉"
        status = "complete"
    else:
        message = "No errors yet, but the proof is incomplete!"
        status = "incomplete"

    return jsonify(
        {
            "ok": True,
            "status": status,
            "isComplete": is_complete,
            "message": message,
            "proofString": str(problem),
        }
    )


@app.post("/api/validate-problem")
def validate_problem():
    data = request.get_json(silent=True) or {}
    logic_name, premises_text, conclusion_text = _extract_problem_fields(data)
    logic, error_message = _resolve_logic(logic_name)

    if logic is None:
        return _json_error(error_message)

    try:
        parse_and_verify_premises(premises_text, logic)
    except ParsingError as e:
        message = f"Invalid premise(s): {e}"
        return _json_error(message)

    if not conclusion_text.strip():
        message = "Invalid conclusion: A conclusion must be provided."
        return _json_error(message)

    try:
        parse_and_verify_formula(conclusion_text, logic)
    except ParsingError as e:
        message = f"Invalid conclusion: {e}"
        return _json_error(message)
    except Exception as e:
        return _json_error(str(e))

    return jsonify({"ok": True, "status": "ok", "message": ""})


@app.post("/api/generate-proof")
def generate_proof():
    data = request.get_json(silent=True) or {}
    logic_name, premises_text, conclusion_text = _extract_problem_fields(data)
    logic, error_message = _resolve_logic(logic_name)

    if logic is None:
        return _json_error(error_message)
    if logic_name != "TFL":
        return _json_error("Proof generation is only supported for TFL.")

    try:
        premises = parse_and_verify_premises(premises_text, logic)
        conclusion = parse_and_verify_formula(conclusion_text, logic)
    except ParsingError as e:
        return _json_error(str(e))

    try:
        problem = prove(premises, conclusion)
    except Exception as e:
        return _json_error(str(e))

    proof_lines = _serialize_proof(problem.proof)

    return jsonify({
        "ok": True,
        "status": "complete",
        "message": "Proof complete! 🎉",
        "lines": proof_lines,
    })


@app.get("/sitemap.xml")
def sitemap_xml():
    """XML sitemap exposing the main site URLs."""
    base_url = "https://ndprover.org"
    paths = [
        "/",
        "/rules",
        "/exercises/tfl",
        "/exercises/fol",
        "/exercises/ml",
    ]
    url_items = "\n".join(
        f"  <url><loc>{base_url}{path}</loc></url>" for path in paths
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{url_items}\n"
        "</urlset>\n"
    )
    return xml, 200, {"Content-Type": "application/xml"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
