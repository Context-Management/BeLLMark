"""Extract reference answers from markdown files and populate suite JSON expected_answer fields."""
import json
import re
from pathlib import Path

DELIVERABLES = Path(__file__).parent.parent.parent / "results" / "2026-02-24-bellmark-benchmark-sets" / "deliverables"
SUITES_DIR = Path(__file__).parent.parent / "data" / "suites"

# Mapping: reference answer file -> suite JSON file
MAPPING = [
    ("reference-answers-set-1.md", "analytical-reasoning.json"),
    ("reference-answers-set-2.md", "instruction-compliance.json"),
    ("reference-answers-set-3.md", "long-form-writing.json"),
    ("reference-answers-set-4.md", "epistemic-calibration.json"),
    ("reference-answers-set-5.md", "domain-expert-communication.json"),
]


def extract_set1_answers(text: str) -> list[str]:
    """Set 1 uses '### Question N' headers with '**Answer**:' and '**Worked Solution**:' sections."""
    answers = []
    # Split by question headers
    questions = re.split(r'\n### Question \d+\n', text)[1:]  # skip preamble

    for q_text in questions:
        # Extract Answer section (brief)
        answer_match = re.search(
            r'\*\*Answer\*\*:\s*\n(.*?)(?=\n---\n|\n\*\*Worked Solution\*\*:)',
            q_text, re.DOTALL
        )
        # Extract Worked Solution section
        solution_match = re.search(
            r'\*\*Worked Solution\*\*:\s*\n(.*?)(?=\n---\n|\n\*\*Key Points|$)',
            q_text, re.DOTALL
        )

        parts = []
        if answer_match:
            parts.append(answer_match.group(1).strip())
        if solution_match:
            parts.append("Worked Solution:\n" + solution_match.group(1).strip())

        if parts:
            answers.append("\n\n".join(parts))
        else:
            # Fallback: try to get everything between **Answer**: and **Key Points
            fallback = re.search(
                r'\*\*Answer\*\*:\s*\n(.*?)(?=\n\*\*Key Points|\n### Common|\n---\n## |\Z)',
                q_text, re.DOTALL
            )
            if fallback:
                answers.append(fallback.group(1).strip())
            else:
                answers.append("")
                print(f"  WARNING: Could not extract answer for a question in set 1")

    return answers


def extract_reference_response(text: str, header_pattern: str) -> list[str]:
    """Extract '### Reference Response' sections from sets 2-5."""
    answers = []
    # Split by question headers (## Q1:, ## Q1 —, etc.)
    questions = re.split(header_pattern, text)[1:]  # skip preamble

    for q_text in questions:
        # Find the Reference Response section
        resp_match = re.search(
            r'### Reference Response\s*\n(.*?)(?=\n### (?:Compliance|Fact-Check|Calibration|Key Points|Common|Red Flags)|$)',
            q_text, re.DOTALL
        )
        if resp_match:
            answers.append(resp_match.group(1).strip())
        else:
            answers.append("")
            print(f"  WARNING: Could not extract reference response from a question")

    return answers


def process_suite(ref_file: str, suite_file: str):
    ref_path = DELIVERABLES / ref_file
    suite_path = SUITES_DIR / suite_file

    print(f"\nProcessing: {ref_file} -> {suite_file}")

    ref_text = ref_path.read_text()
    suite_data = json.loads(suite_path.read_text())

    # Extract answers based on set format
    if "set-1" in ref_file:
        answers = extract_set1_answers(ref_text)
    elif "set-2" in ref_file:
        answers = extract_reference_response(ref_text, r'\n## Q\d+: ')
    elif "set-3" in ref_file:
        answers = extract_reference_response(ref_text, r'\n## Q\d+ — ')
    elif "set-4" in ref_file:
        answers = extract_reference_response(ref_text, r'\n## Q\d+: ')
    elif "set-5" in ref_file:
        answers = extract_reference_response(ref_text, r'\n## Q\d+: ')
    else:
        print(f"  ERROR: Unknown set format for {ref_file}")
        return

    num_questions = len(suite_data["questions"])
    print(f"  Questions in suite: {num_questions}")
    print(f"  Answers extracted: {len(answers)}")

    if len(answers) != num_questions:
        print(f"  ERROR: Mismatch! {len(answers)} answers for {num_questions} questions")
        # Show what we got
        for i, a in enumerate(answers):
            print(f"    Answer {i+1}: {a[:80]}..." if len(a) > 80 else f"    Answer {i+1}: {a[:80]}")
        return

    # Populate expected_answer fields
    populated = 0
    for i, answer in enumerate(answers):
        if answer:
            suite_data["questions"][i]["expected_answer"] = answer
            populated += 1
        else:
            print(f"  WARNING: Empty answer for question {i+1}")

    # Write back
    suite_path.write_text(json.dumps(suite_data, indent=2, ensure_ascii=False) + "\n")
    print(f"  Populated {populated}/{num_questions} expected_answer fields")


if __name__ == "__main__":
    for ref_file, suite_file in MAPPING:
        process_suite(ref_file, suite_file)
    print("\nDone!")
