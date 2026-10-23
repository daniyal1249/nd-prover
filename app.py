from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from nd_prover import *


app = Flask(
    __name__,
    template_folder="site/templates",
    static_folder="site/static",
    static_url_path="/static"
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
        ""
    ]
    body = "\n".join(lines)
    return body, 200, {"Content-Type": "text/plain"}


def _json_error(message: str, status: str = "error", code: int = 400):
    """Return a standardized JSON error response."""
    return jsonify({"ok": False, "status": status, "message": message}), code


def _extract_problem_fields(data):
    """Extract problem fields from a JSON payload."""
    logic_name = data.get("logic")
    logic_name = logic_name.strip() if isinstance(logic_name, str) else ""

    premises_text = data.get("premisesText")
    premises_text = premises_text if isinstance(premises_text, str) else ""

    conclusion_text = data.get("conclusionText")
    conclusion_text = conclusion_text if isinstance(conclusion_text, str) else ""

    domain_semantics = data.get("domainSemantics")
    if isinstance(domain_semantics, str):
        domain_semantics = domain_semantics.strip().lower() or None

    equality_semantics = data.get("equalitySemantics")
    if isinstance(equality_semantics, str):
        equality_semantics = equality_semantics.strip().lower() or None

    derived_rules = data.get("derivedRules", True)

    return (
        logic_name,
        premises_text,
        conclusion_text,
        domain_semantics,
        equality_semantics,
        derived_rules
    )


def _resolve_logic(logic_name):
    """Resolve the logic from its label, or return an error message."""
    logic = logics.get(logic_name)
    if logic is None:
        msg = f'Logic not recognized: "{logic_name}".'
        return None, msg
    return logic, None


def _parse_problem(data):
    """Parse and validate a problem payload."""
    (
        logic_name,
        premises_text,
        conclusion_text,
        domain_semantics,
        equality_semantics,
        derived_rules
    ) = _extract_problem_fields(data)

    logic, msg = _resolve_logic(logic_name)
    if logic is None:
        return None, _json_error(msg)

    semantics = (domain_semantics, equality_semantics)
    if not all(s is None or isinstance(s, str) for s in semantics):
        return None, _json_error("Invalid semantic configuration.")
    if not isinstance(derived_rules, bool):
        return None, _json_error("Invalid derived rules setting.")

    try:
        premises = parse_and_verify_premises(premises_text, logic)
    except ParsingError as e:
        return None, _json_error(f"Invalid premise(s): {e}")

    if not conclusion_text.strip():
        msg = "Invalid conclusion: A conclusion must be provided."
        return None, _json_error(msg)

    try:
        conclusion = parse_and_verify_formula(conclusion_text, logic)
    except ParsingError as e:
        return None, _json_error(f"Invalid conclusion: {e}")

    try:
        problem = Problem(
            logic,
            premises,
            conclusion,
            domain_semantics,
            equality_semantics,
            derived_rules
        )
    except SemanticsError as e:
        msg = str(e) or "Invalid semantic configuration."
        return None, _json_error(msg)
    except InferenceError as e:
        return None, _json_error(str(e))

    return problem, None


def _reconstruct_problem_from_lines(data):
    """Parse a problem payload and replay its serialized proof lines."""
    problem, error_msg = _parse_problem(data)

    if error_msg is not None:
        return None, error_msg

    for payload in data.get("lines") or []:
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
                return None, _json_error(prefix + "Formula is missing.")
            try:
                assumption = parse_assumption(formula_text)
            except ParsingError as e:
                return None, _json_error(prefix + str(e))

            if kind == "assumption":
                try:
                    problem.begin_subproof(assumption)
                except Exception as e:
                    return None, _json_error(prefix + str(e))
            else:  # end_and_begin
                try:
                    problem.end_and_begin_subproof(assumption)
                except Exception as e:
                    return None, _json_error(prefix + str(e))

            continue

        # All other kinds should have both formula and justification.
        if not formula_text:
            return None, _json_error(prefix + "Formula is missing.")
        if not just_text:
            return None, _json_error(prefix + "Justification is missing.")
        if not raw:
            raw = f"{formula_text}; {just_text}"

        try:
            formula, justification = parse_line(raw, problem.logic)
        except ParsingError as e:
            return None, _json_error(prefix + str(e))

        try:
            if kind == "line":
                problem.add_line(formula, justification)
            elif kind == "close_subproof":
                problem.end_subproof(formula, justification)
        except Exception as e:
            return None, _json_error(prefix + str(e))

    return problem, None


def _hint_scope(problem, data):
    """Validate open goals and select the innermost unfinished scope."""
    submitted = data.get("goals") or []
    if not isinstance(submitted, list) or not all(
        isinstance(g, dict) and isinstance(g.get("lineNumber"), int)
        for g in submitted
    ):
        return None, None, None, _json_error("Invalid subproof goals.")

    submitted = {g.get("lineNumber"): g.get("formulaText") for g in submitted}
    scopes, goals = [problem.proof], [problem.conclusion]
    validated = {}

    while scopes[-1].seq and scopes[-1].seq[-1].is_subproof():
        scope = scopes[-1].seq[-1]
        line_no = scope.seq[0].idx
        raw = submitted.get(line_no)
        prefix = f"Line {line_no}: "

        if raw is None or isinstance(raw, str) and not raw.strip():
            return None, None, None, _json_error(
                prefix + "Subproof goal is missing.", status="missing-goal"
            )
        if not isinstance(raw, str):
            return None, None, None, _json_error(
                prefix + "Invalid subproof goal."
            )

        try:
            goal = parse_and_verify_formula(raw, problem.logic)
        except ParsingError as e:
            return None, None, None, _json_error(
                prefix + f"Invalid subproof goal: {e}"
            )

        validated[line_no] = str(goal)
        scopes.append(scope)
        goals.append(goal)

    while len(scopes) > 1 and scopes[-1].conclusion == goals[-1]:
        scopes.pop()
        goals.pop()

    return scopes, goals[-1], validated, None


def _generated_hint_goals(proof, original_length):
    """Collect goals for assumptions added by proof completion."""
    goals = {}
    for obj in proof.seq:
        if obj.is_subproof():
            line_no = obj.seq[0].idx
            if line_no > original_length and obj.conclusion is not None:
                goals[line_no] = str(obj.conclusion)
            goals.update(_generated_hint_goals(obj, original_length))

    return goals


def _complete_hint(problem, scopes, goal):
    """Complete one scope, then verify the result in its enclosing proof."""
    converted = {}

    def convert(obj):
        if obj.is_line():
            j = obj.justification
            citations = tuple(converted[c].id for c in j.citations)
            result = _Line(obj.formula, str(j.rule), citations)
        else:
            result = _Proof([convert(item) for item in obj.seq], obj.conclusion)
        converted[obj.idx] = result
        return result

    for obj in problem.proof.context + problem.proof.seq:
        convert(obj)

    scope = scopes[-1]
    context = (
        scope.context if scope.strict_context is None else scope.strict_context
    )
    proof = _Proof([converted[obj.idx] for obj in context + scope.seq], goal)
    protected = frozenset(proof.id_to_citers())

    # Import only formulas available across the nearest strict boundary.
    strict_parent = None
    for idx, opened in enumerate(scopes[1:], 1):
        if isinstance(opened.assumption, BoxMarker):
            strict_parent = scopes[idx - 1]
    if strict_parent is not None:
        parent_context = (
            strict_parent.context if strict_parent.strict_context is None
            else strict_parent.strict_context
        )
        parent = _Proof(
            [
                converted[obj.idx]
                for obj in parent_context + strict_parent.seq[:-1]
            ],
            goal
        )
        p = Prover(
            problem.logic,
            parent,
            problem.domain_semantics,
            problem.equality_semantics,
            problem.derived_rules
        )
        Eliminator.strict_elim(p, proof)

    # Root validity is already checked before requesting a hint.
    if len(scopes) > 1:
        result = check_validity(
            problem.logic,
            proof.eff_assumptions,
            goal,
            problem.domain_semantics,
            problem.equality_semantics,
            countermodel=False,
            timeout=3000
        )
        if result.status != "valid":
            return result.status

    for exhaustive in (True, False):
        result = complete_proof(
            problem.logic,
            proof,
            problem.domain_semantics,
            problem.equality_semantics,
            problem.derived_rules,
            exhaustive=exhaustive,
            timeout=5000
        )
        if result.status == "success":
            break
    if result.status != "success":
        return result.status

    if strict_parent is not None:
        # Imports are generated material, so unused imports can be removed.
        Processor.clean(result.proof, protected)

    start = 1 if scope.assumption is not None else 0
    target = Proof(scope.seq[:start], scope.context, scope.strict_context)
    id_to_idx = {obj.id: idx for idx, obj in converted.items()}
    Processor.translate(
        result.proof.seq[len(context) + start:],
        target,
        problem.logic,
        id_to_idx
    )
    scope.seq = target.seq
    if problem.errors() or scope.conclusion != goal:
        return "failure"
    return "success"


def _export_proof(data, formatter):
    """Reconstruct a proof under QS5 and format it for export."""
    export_data = {
        **data,
        "logic": "QS5",
        "domainSemantics": None,
        "equalitySemantics": None
    }

    problem, error_msg = _reconstruct_problem_from_lines(export_data)

    if error_msg is not None:
        return error_msg

    return jsonify({
        "ok": True,
        "status": "ok",
        "proofString": formatter(problem)
    })


def _check_problem_validity(problem, timeout):
    """Check a parsed problem for validity."""
    return check_validity(
        problem.logic,
        problem.premises,
        problem.conclusion,
        problem.domain_semantics,
        problem.equality_semantics,
        countermodel=True,
        timeout=timeout
    )


def _search_for_proof(problem, exhaustive, timeout):
    """Run one proof-search stage for a parsed problem."""
    return prove(
        problem.logic,
        problem.premises,
        problem.conclusion,
        problem.domain_semantics,
        problem.equality_semantics,
        problem.derived_rules,
        exhaustive=exhaustive,
        timeout=timeout
    )


def _generation_note(logic):
    if modal(logic):
        return "\n\n🚧 Note: ML and QML proof generation is still under development."
    if first_order(logic):
        return "\n\n🚧 Note: FOL proof generation is still under development."
    return ""


def _validity_message(result, continue_generation=False):
    """Build the user-facing message for a validity result."""
    if result.status == "invalid":
        return f"Invalid argument. Countermodel:\n\n{result.countermodel}"

    if result.status == "valid":
        if not continue_generation:
            return "Argument is valid!"
        return "Argument is valid. Attempting an exhaustive proof search..."

    if continue_generation:
        return (
            "Argument validity unknown. "
            "Attempting an exhaustive proof search..."
        )

    return "Argument validity unknown."


def _serialize_proof(proof):
    """Serialize a Proof object to the frontend format.
    
    Returns a list of line objects with the structure:
    {
        indent: int,
        text: str,
        justText: str,
        isAssumption: bool,
        isPremise: bool
    }
    """
    lines = []

    def traverse(obj, indent=0, is_premise=False):
        if obj.is_line():
            formula_str = str(obj.formula)
            just_str = str(obj.justification)
            is_assumption = obj.justification.rule is Rules.AS
            is_premise_line = is_premise or obj.justification.rule is Rules.PR
            
            lines.append({
                'indent': indent,
                'text': formula_str,
                'justText': just_str,
                'isAssumption': is_assumption,
                'isPremise': is_premise_line
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
                    'isPremise': False
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


def _generated_proof_payload(logic, problem):
    """Build the shared JSON payload for a successfully generated proof."""
    return {
        "ok": True,
        "status": "complete",
        "outcome": "success",
        "message": "Proof complete! 🎉" + _generation_note(logic),
        "lines": _serialize_proof(problem.proof)
    }


@app.get("/")
def index():
    return render_template("index.html", rule_names=list(Rules.rules))


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
    problem, error_msg = _reconstruct_problem_from_lines(data)

    if error_msg is not None:
        return error_msg

    if errors := problem.errors():
        msg = "\n".join(errors)
        return _json_error(msg)

    is_complete = problem.conclusion_reached()

    if is_complete:
        msg = "Proof complete! 🎉"
        status = "complete"
    else:
        msg = "No errors yet, but the proof is incomplete!"
        status = "incomplete"

    return jsonify({
        "ok": True,
        "status": status,
        "isComplete": is_complete,
        "message": msg
    })


@app.post("/api/get-hint")
def get_hint():
    data = request.get_json(silent=True) or {}
    problem, error_msg = _reconstruct_problem_from_lines(data)

    if error_msg is not None:
        return error_msg

    if errors := problem.errors():
        return _json_error("\n".join(errors))

    scopes, goal, goals, error_msg = _hint_scope(problem, data)
    if error_msg is not None:
        return error_msg

    original = _serialize_proof(problem.proof)
    cached = data.get("cachedProof")
    if isinstance(cached, dict) and cached.get("lines") == original:
        cached_goals = cached.get("goals")
        if isinstance(cached_goals, list) and all(
            isinstance(g, dict) and isinstance(g.get("lineNumber"), int)
            for g in cached_goals
        ):
            cached_goals = {
                g.get("lineNumber"): g.get("formulaText") for g in cached_goals
            }
            if all(
                cached_goals.get(line_no) == text
                for line_no, text in goals.items()
            ):
                return jsonify({
                    "ok": True,
                    "status": "complete",
                    "outcome": "cached",
                    "message": "Cached completion is compatible."
                })

    already_complete = problem.conclusion_reached()
    try:
        outcome = (
            "success" if already_complete
            else _complete_hint(problem, scopes, goal)
        )
    except Exception as e:
        return _json_error(str(e) or "Unable to complete the current goal.")

    if outcome == "invalid":
        return _json_error(
            "Current goal does not follow from the available assumptions!"
        )
    if outcome == "unknown":
        return _json_error("Current goal validity unknown. Please try again.")

    if outcome == "success":
        lines = _serialize_proof(problem.proof)
        if lines[:len(original)] != original:
            return _json_error("Unable to preserve the existing proof.")
        goals.update(_generated_hint_goals(problem.proof, len(original)))
        return jsonify({
            "ok": True,
            "status": "complete",
            "outcome": outcome,
            "message": (
                "Proof already complete!" if already_complete
                else "Current goal completed."
            ),
            "isComplete": problem.conclusion_reached(),
            "goalLineNumber": scopes[-1].seq[0].idx if len(scopes) > 1 else None,
            "goalText": str(goal),
            "goals": [
                {"lineNumber": line_no, "formulaText": text}
                for line_no, text in goals.items()
            ],
            "lines": lines
        })

    msg = "No completion was found for the current goal."
    if outcome == "timeout":
        msg = "Proof completion timed out."
    return jsonify({
        "ok": True,
        "status": "complete",
        "outcome": outcome,
        "message": msg
    })


@app.post("/api/export-proof/plain")
def export_proof_plain():
    data = request.get_json(silent=True) or {}
    return _export_proof(data, Problem.to_plain_text)


@app.post("/api/export-proof/latex")
def export_proof_latex():
    data = request.get_json(silent=True) or {}
    return _export_proof(data, problem_to_latex)


@app.post("/api/validate-problem")
def validate_problem():
    data = request.get_json(silent=True) or {}
    _, error_msg = _parse_problem(data)

    if error_msg is not None:
        return error_msg

    return jsonify({
        "ok": True,
        "status": "ok",
        "message": ""
    })


@app.post("/api/check-validity")
def check_validity_api():
    data = request.get_json(silent=True) or {}
    problem, error_msg = _parse_problem(data)

    if error_msg is not None:
        return error_msg

    timeout = data.get("timeout", 10000)
    if type(timeout) is not int or not 0 < timeout <= 10000:
        return _json_error("Invalid validity timeout.")

    try:
        result = _check_problem_validity(problem, timeout)
    except Exception as e:
        return _json_error(str(e))

    msg = _validity_message(result)

    return jsonify({
        "ok": True,
        "status": "complete",
        "outcome": result.status,
        "message": msg
    })


@app.post("/api/generate-proof/validity")
def generate_proof_validity():
    data = request.get_json(silent=True) or {}
    problem, error_msg = _parse_problem(data)

    if error_msg is not None:
        return error_msg

    try:
        result = _check_problem_validity(problem, 3000)
    except Exception as e:
        return _json_error(str(e) + _generation_note(problem.logic))

    msg = _validity_message(result, continue_generation=True)

    return jsonify({
        "ok": True,
        "stage": "validity",
        "outcome": result.status,
        "message": msg
    })


@app.post("/api/generate-proof/exhaustive")
def generate_proof_exhaustive():
    data = request.get_json(silent=True) or {}
    problem, error_msg = _parse_problem(data)

    if error_msg is not None:
        return error_msg

    try:
        result = _search_for_proof(problem, True, 5000)
    except Exception as e:
        return _json_error(str(e) + _generation_note(problem.logic))

    if result.status == "success":
        payload = _generated_proof_payload(problem.logic, result.problem)
        payload["stage"] = "exhaustive"
        return jsonify(payload)

    if result.status == "failure":
        msg = (
            "Exhaustive search failed. "
            "Attempting a fast proof search..."
        )
    else:
        msg = (
            "Exhaustive search timed out. "
            "Attempting a fast proof search..."
        )

    return jsonify({
        "ok": True,
        "stage": "exhaustive",
        "outcome": result.status,
        "message": msg
    })


@app.post("/api/generate-proof/fast")
def generate_proof_fast():
    data = request.get_json(silent=True) or {}
    validity_outcome = data.get("validityOutcome")
    if validity_outcome not in {"valid", "unknown"}:
        return _json_error("Invalid validity outcome.")

    problem, error_msg = _parse_problem(data)
    if error_msg is not None:
        return error_msg

    try:
        result = _search_for_proof(problem, False, 5000)
    except Exception as e:
        return _json_error(str(e) + _generation_note(problem.logic))

    if result.status == "success":
        payload = _generated_proof_payload(problem.logic, result.problem)
        payload["stage"] = "fast"
        return jsonify(payload)

    if result.status == "failure":
        if validity_outcome == "valid":
            msg = "Argument is valid, but no proof was found."
        else:
            msg = "Argument validity unknown. No proof was found."
    elif validity_outcome == "valid":
        msg = "Argument is valid, but proof generation timed out."
    else:
        msg = "Argument validity unknown. Proof generation timed out."

    return jsonify({
        "ok": True,
        "stage": "fast",
        "outcome": result.status,
        "message": msg + _generation_note(problem.logic)
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
