# Copyright 2026 Daniyal Akif

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from .parser import *


logics = {
    "TFL": TFL,
    "FOL": FOL,
    "MLK": MLK,
    "MLT": MLT,
    "MLS4": MLS4,
    "MLS5": MLS5,
    "FOMLK": FOMLK,
    "FOMLT": FOMLT,
    "FOMLS4": FOMLS4,
    "FOMLS5": FOMLS5,
}


def parse_and_verify_formula(f, logic):
    f = parse_formula(f)
    if logic is TFL and is_tfl_formula(f):
        return f
    if logic is FOL and is_fol_formula(f):
        return f   
    if logic in (MLK, MLT, MLS4, MLS5) and is_ml_formula(f):
        return f
    if logic in (FOMLK, FOMLT, FOMLS4, FOMLS5):
        return f
    raise ParsingError(f'"{f}" is not a well-formed {logic.__name__} formula.')


def parse_and_verify_premises(s, logic):
    s = s.strip()
    if s == "NA":
        return []

    def split_top_level(text):
        parts, depth, start = [], 0, 0
        for i, ch in enumerate(text):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            elif depth == 0 and ch in (",", ";"):
                if part := text[start:i].strip():
                    parts.append(part)
                start = i + 1
        if tail := text[start:].strip():
            parts.append(tail)
        return parts

    parts = split_top_level(s)
    return [parse_and_verify_formula(p, logic) for p in parts]


def select_logic():
    while True:
        raw = input(f"Select logic ({', '.join(logics)}): ")
        logic = logics.get(raw.strip().upper())
        if logic is not None:
            return logic
        print("Logic not recognized. Please try again.")


def input_premises(logic):
    while True:
        raw = input('Enter premises (separated by "," or ";"), or "NA" if none: ')
        try:
            return parse_and_verify_premises(raw, logic)
        except ParsingError as e:
            print(f"{e} Please try again.")


def input_conclusion(logic):
    while True:
        raw = input("Enter conclusion: ")
        try:
            return parse_and_verify_formula(raw, logic)
        except ParsingError as e:
            print(f"{e} Please try again.")


def create_problem():
    logic = select_logic()
    premises = input_premises(logic)
    conclusion = input_conclusion(logic)
    return Problem(logic, premises, conclusion)


def select_edit():
    edits = (
        "1 - Add a new line",
        "2 - Begin a new subproof",
        "3 - End the current subproof",
        "4 - End the current subproof and begin a new one",
        "5 - Delete the last line",
    )

    while True:
        raw = input("\n".join(edits) + "\n\nSelect edit: ")
        if raw.strip().isdecimal() and 1 <= int(raw) <= 5:
            return int(raw)
        print("Invalid edit. Please try again.\n")


def input_line():
    raw = input("Enter line: ")
    return parse_line(raw)


def input_assumption():
    raw = input("Enter assumption: ")
    return parse_assumption(raw)


def perform_edit(problem, edit):
    try:
        match edit:
            case 1:
                f, j = input_line()
                problem.add_line(f, j)
            case 2:
                a = input_assumption()
                problem.begin_subproof(a)
            case 3:
                f, j = input_line()
                problem.end_subproof(f, j)
            case 4:
                a = input_assumption()
                problem.end_and_begin_subproof(a)
            case 5:
                problem.delete_line()

        if errors := problem.errors():
            problem.delete_line()
            error = errors[0].split(": ", 1)[-1]
            raise InferenceError(error)

    except Exception as e:
        print(f"{e} Please try again.")


def main():
    problem = create_problem()
    while not problem.conclusion_reached():
        print()
        if problem_str := str(problem):
            print(f"{problem_str}\n")
        edit = select_edit()
        perform_edit(problem, edit)

    print(f"\n{problem}\n")
    print("Proof complete! 🎉")
