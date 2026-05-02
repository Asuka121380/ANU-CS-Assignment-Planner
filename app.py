import cgi
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
COURSE_PATH = DATA_DIR / "anu_comp_course_workload_data_2025_clean.jsonl"
GRADE_PATH = DATA_DIR / "anu_grading_scale.jsonl"
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/chat/completions"


def load_env():
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def read_jsonl(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


load_env()
COURSES = read_jsonl(COURSE_PATH)
GRADES = read_jsonl(GRADE_PATH)


def compact_course(course):
    return {
        "course_code": course.get("course_code"),
        "title": course.get("title"),
        "unit_value": course.get("unit_value"),
        "description": course.get("description"),
        "workload": course.get("workload"),
        "learning_outcomes": course.get("learning_outcomes") or [],
        "requisite_and_incompatibility": course.get("requisite_and_incompatibility") or {},
        "target_year": course.get("target_year"),
    }


def find_course(code):
    normalized = str(code or "").strip().upper()
    for course in COURSES:
        if course.get("course_code") == normalized:
            return course
    return None


def search_courses(query, limit=12):
    query = str(query or "").strip().lower()
    if not query:
        return [compact_course(course) for course in COURSES[:limit]]

    terms = [term for term in query.split() if term]
    scored = []
    for course in COURSES:
        title = course.get("title", "")
        code = course.get("course_code", "").lower()
        searchable = " ".join(
            [
                course.get("course_code", ""),
                title,
                course.get("description", ""),
                *course.get("learning_outcomes", []),
            ]
        ).lower()
        score = 0
        for term in terms:
            if code == term:
                score += 12
            if code.startswith(term):
                score += 8
            if term in title.lower():
                score += 5
            if term in searchable:
                score += 1
        if score:
            scored.append((score, course))

    scored.sort(key=lambda item: (-item[0], item[1].get("course_code", "")))
    return [compact_course(course) for _, course in scored[:limit]]


def grade_band(mark):
    try:
        numeric = float(mark)
    except (TypeError, ValueError):
        return None
    for grade in GRADES:
        min_mark = grade.get("min_mark")
        max_mark = grade.get("max_mark")
        if min_mark is not None and max_mark is not None and min_mark <= numeric <= max_mark:
            return grade
    return {
        "grade_code": "P" if numeric >= 50 else "N",
        "grade_name": "Pass" if numeric >= 50 else "Fail",
        "interpretation_for_estimator": (
            "Passing result; use as moderate evidence of preparation."
            if numeric >= 50
            else "Fail; do not treat as completed preparation."
        ),
    }


def summarize_student_background(student_courses):
    profile = []
    for entry in student_courses:
        course_code = str(entry.get("courseCode", "")).strip().upper()
        try:
            mark = float(entry.get("mark"))
        except (TypeError, ValueError):
            continue
        course = find_course(course_code)
        grade = grade_band(mark) or {}
        profile.append(
            {
                "courseCode": course_code,
                "mark": mark,
                "gradeCode": grade.get("grade_code", "Unknown"),
                "gradeName": grade.get("grade_name", "Unknown"),
                "gradeInterpretation": grade.get("interpretation_for_estimator", ""),
                "course": compact_course(course) if course else None,
            }
        )
    return profile


def configured_api_key(name):
    value = os.environ.get(name, "").strip()
    if not value or value.startswith("your_"):
        return ""
    return value


def analyze_with_deepseek(student_profile, target_course, assignment_text):
    api_key = configured_api_key("DEEPSEEK_API_KEY")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
    if not api_key:
        return demo_estimate(student_profile, target_course, assignment_text)

    output_template_constraints = {
        "summary": "One paragraph assignment readiness assessment.",
        "totalHours": {"min": 0, "max": 0},
        "difficulty": "Easy | Medium | Hard | Very Hard",
        "confidence": 0.0,
        "coveredKnowledge": [
            {
                "topic": "Topic the student likely knows",
                "evidence": "Completed course and mark evidence",
                "relevance": "How it helps this assignment",
            }
        ],
        "missingKnowledge": [
            {
                "topic": "Topic to learn or revise",
                "whyItMatters": "Why this topic matters",
                "suggestedAction": "Practical next step",
            }
        ],
        "workBreakdown": [
            {
                "phase": "Understand requirements",
                "description": "Concrete work in this phase",
                "hours": {"min": 0, "max": 0},
            }
        ],
        "estimateFactors": {
            "increased": ["Concrete factor that increased estimated hours"],
            "decreased": ["Concrete factor that decreased estimated hours"],
        },
        "risks": ["Main risks or blockers"],
        "assumptions": ["Assumptions behind the estimate"],
    }
    performance_method = [
        {
            "grade_code": grade.get("grade_code"),
            "grade_name": grade.get("grade_name"),
            "min_mark": grade.get("min_mark"),
            "max_mark": grade.get("max_mark"),
            "interpretation_for_estimator": grade.get("interpretation_for_estimator"),
        }
        for grade in GRADES
    ]
    score_classification_rule = [
        {
            "grade_code": grade.get("grade_code"),
            "mark_range_text": grade.get("mark_range_text"),
            "is_passing_grade": grade.get("is_passing_grade"),
            "interpretation_for_estimator": grade.get("interpretation_for_estimator"),
        }
        for grade in GRADES
    ]
    structured_course_information = {
        "target_course": target_course,
        "completed_course_records": [entry.get("course") for entry in student_profile if entry.get("course")],
    }
    system_prompt = """## Your Role
You are a specialised ANU course workload estimation assistant.

## TASK DESCRIPTION
Your only task is to estimate how long a student may need to complete a specific assignment for a specific ANU computing course.

You are not a general chatbot. Do not answer questions outside this task.

## Items will be given:
1. (1)The student's completed courses and grades;
   (2)The student's performance estimation method;
   (3)The student's current courses.
2. The target assignment description.
3. Structured course information retrieved from a local course database, including:
   - course_code
   - title
   - unit_value
   - description
   - workload
   - learning_outcomes
   - requisite_and_incompatibility
4. Score classification rule, measures how well the student's performance in this course.

You must estimate the assignment completion time using only:
- the target course information,
- the assignment description,
- the student's previous grades and related course history,
- the official workload statement,
- the course learning outcomes,
- the prerequisite/requisite information.

## Rules:
- Do not invent course information.
- Do not provide academic dishonesty assistance.
- Do not write the assignment for the student.
- Output must follow the required JSON schema exactly.
- Use hours, not days, as the main estimate.
- Explain which factors increased or decreased the estimate.
- If the assignment description is vague, produce a wider range and lower confidence.
- If the student has high grades in closely related prerequisite courses, reduce the estimate moderately.
- If the student has low grades or no background in prerequisite areas, increase the estimate moderately.
- Estimate only the hours required for the assignment unless the user asks for calendar scheduling.
"""
    user_prompt = """## Given items:
### The student's completed courses and grades:
{completed_courses}

### The student's performance estimation method:
{performance_method}

### The student's current courses:
{current_courses}

### The target assignment description:
{assignment_description}

### Structured course information retrieved from a local course database, including:
{course_information}

### Score classification rule
{score_rule}

## Output:
### Output template constraints:
{output_constraints}

### Your result:
Return only the Assignments Schedule result as a valid JSON object matching the output template constraints. Do not wrap it in markdown.
""".format(
        completed_courses=json.dumps(student_profile, ensure_ascii=False, indent=2),
        performance_method=json.dumps(performance_method, ensure_ascii=False, indent=2),
        current_courses=json.dumps([], ensure_ascii=False, indent=2),
        assignment_description=json.dumps({"text": truncate(assignment_text, 24000)}, ensure_ascii=False, indent=2),
        course_information=json.dumps(structured_course_information, ensure_ascii=False, indent=2),
        score_rule=json.dumps(score_classification_rule, ensure_ascii=False, indent=2),
        output_constraints=json.dumps(output_template_constraints, ensure_ascii=False, indent=2),
    )
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "max_tokens": 4096,
    }
    request = Request(
        DEEPSEEK_ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"DeepSeek API request failed: {exc}") from exc

    content = payload.get("choices", [{}])[0].get("message", {}).get("content")
    if not content:
        raise RuntimeError("DeepSeek API returned an empty response.")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"The model response was not valid JSON: {exc}") from exc
    return normalize_estimate(parsed, {"model": model, "usedMock": False})


def normalize_estimate(estimate, meta):
    total = estimate.get("totalHours") or {}
    return {
        "summary": str(estimate.get("summary", "")),
        "totalHours": {
            "min": max(0, number(total.get("min"), 8)),
            "max": max(0, number(total.get("max"), number(total.get("min"), 16))),
        },
        "difficulty": estimate.get("difficulty", "Medium"),
        "confidence": min(1, max(0, number(estimate.get("confidence"), 0.5))),
        "coveredKnowledge": estimate.get("coveredKnowledge") if isinstance(estimate.get("coveredKnowledge"), list) else [],
        "missingKnowledge": estimate.get("missingKnowledge") if isinstance(estimate.get("missingKnowledge"), list) else [],
        "workBreakdown": estimate.get("workBreakdown") if isinstance(estimate.get("workBreakdown"), list) else [],
        "estimateFactors": estimate.get("estimateFactors") if isinstance(estimate.get("estimateFactors"), dict) else {},
        "risks": estimate.get("risks") if isinstance(estimate.get("risks"), list) else [],
        "assumptions": estimate.get("assumptions") if isinstance(estimate.get("assumptions"), list) else [],
        "meta": meta,
    }


def demo_estimate(student_profile, target_course, assignment_text):
    known = [entry for entry in student_profile if entry.get("course")][:4]
    strong_programming = any(
        entry.get("mark", 0) >= 70
        and any(word in entry.get("course", {}).get("title", "").lower() for word in ["programming", "software"])
        for entry in student_profile
    )
    text_factor = min(10, max(1, len(assignment_text) // 2500))
    base_min = 10 if strong_programming else 14
    base_max = 18 if strong_programming else 26
    return normalize_estimate(
        {
            "summary": (
                f"Demo estimate for {target_course.get('course_code', 'the selected course')}. "
                "Add DEEPSEEK_API_KEY to .env to replace this deterministic fallback with a live AI assessment."
            ),
            "totalHours": {"min": base_min + text_factor, "max": base_max + text_factor},
            "difficulty": "Medium" if strong_programming else "Hard",
            "confidence": 0.58 if target_course else 0.42,
            "coveredKnowledge": [
                {
                    "topic": entry["course"]["title"],
                    "evidence": f"{entry['courseCode']} with mark {entry['mark']:.0f} ({entry['gradeCode']})",
                    "relevance": "Relevant course outcomes may reduce ramp-up time for overlapping assignment concepts.",
                }
                for entry in known
            ],
            "missingKnowledge": [
                {
                    "topic": "Assignment-specific requirements",
                    "whyItMatters": "The exact marking criteria and deliverables drive most of the workload estimate.",
                    "suggestedAction": "Read the specification, rubric, starter code, and submission instructions before coding.",
                },
                {
                    "topic": "Testing and validation strategy",
                    "whyItMatters": "Most CS assignments need time for debugging, edge cases, and final polish.",
                    "suggestedAction": "Reserve a separate testing phase instead of treating testing as a final quick check.",
                },
            ],
            "workBreakdown": [
                {
                    "phase": "Brief analysis",
                    "description": "Read the assignment, identify deliverables, map tasks to known course concepts.",
                    "hours": {"min": 2, "max": 4},
                },
                {
                    "phase": "Knowledge refresh",
                    "description": "Revise unfamiliar concepts and inspect relevant examples or lecture material.",
                    "hours": {"min": 3, "max": 6},
                },
                {
                    "phase": "Implementation",
                    "description": "Build the main solution and iterate against requirements.",
                    "hours": {"min": 6, "max": 12},
                },
                {
                    "phase": "Testing and submission",
                    "description": "Test edge cases, prepare documentation, and check submission packaging.",
                    "hours": {"min": 3, "max": 5},
                },
            ],
            "estimateFactors": {
                "increased": [
                    "The fallback cannot inspect the assignment requirements deeply without a live API response.",
                    "Testing, debugging, and submission packaging are reserved as separate work.",
                ],
                "decreased": [
                    "The student has strong prior performance in a related programming course."
                    if strong_programming
                    else "No strong reduction factor was detected from the entered course history."
                ],
            },
            "risks": ["No live AI key is configured, so this is a generic fallback estimate."],
            "assumptions": ["Marks are on a 0-100 scale.", "The uploaded file contains the full assignment specification."],
        },
        {"model": "demo-fallback", "usedMock": True},
    )


def number(value, fallback):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def truncate(text, limit):
    return text if len(text) <= limit else text[:limit] + "\n\n[Assignment text truncated for analysis.]"


def extract_file_text(field):
    if field is None or not getattr(field, "filename", ""):
        return ""
    data = field.file.read()
    filename = field.filename.lower()
    content_type = field.type or ""
    if filename.endswith(".pdf") or "pdf" in content_type:
        temp_path = ROOT / ".tmp_assignment.pdf"
        temp_path.write_bytes(data)
        try:
            reader = PdfReader(str(temp_path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        finally:
            temp_path.unlink(missing_ok=True)
    if filename.endswith(".txt") or content_type.startswith("text/"):
        return data.decode("utf-8", errors="replace")
    raise ValueError("Unsupported file type. Please upload a .txt or .pdf file.")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self.serve_file(ROOT / "index.html", "text/html")
        if parsed.path == "/api/health":
            return self.send_json(
                {
                    "ok": True,
                    "courses": len(COURSES),
                    "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
                    "hasApiKey": bool(configured_api_key("DEEPSEEK_API_KEY")),
                }
            )
        if parsed.path == "/api/courses/search":
            query = parse_qs(parsed.query).get("q", [""])[0]
            return self.send_json({"courses": search_courses(query)})
        if parsed.path.startswith("/static/"):
            file_path = ROOT / parsed.path.lstrip("/")
            content_type = "text/css" if file_path.suffix == ".css" else "application/javascript"
            return self.serve_file(file_path, content_type)
        self.send_error(404)

    def do_POST(self):
        if self.path != "/api/analyze":
            self.send_error(404)
            return
        try:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": self.headers.get("Content-Type"),
                    "CONTENT_LENGTH": self.headers.get("Content-Length"),
                },
            )
            student_courses = json.loads(form.getvalue("studentCourses") or "[]")
            target_code = str(form.getvalue("targetCourseCode") or "").strip().upper()
            target_course = find_course(target_code)
            uploaded_text = extract_file_text(form["assignmentFile"] if "assignmentFile" in form else None)
            pasted_text = str(form.getvalue("assignmentText") or "")
            assignment_text = uploaded_text.strip() or pasted_text.strip()
            if not target_course:
                return self.send_json({"error": "Select a valid ANU COMP course to analyze."}, 400)
            if not assignment_text.strip():
                return self.send_json({"error": "Upload a readable TXT/PDF file or paste assignment text."}, 400)

            student_profile = summarize_student_background(student_courses)
            target = compact_course(target_course)
            estimate = analyze_with_deepseek(student_profile, target, assignment_text)
            self.send_json(
                {
                    "estimate": estimate,
                    "studentProfile": student_profile,
                    "targetCourse": target,
                    "assignmentTextPreview": assignment_text[:900],
                }
            )
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def serve_file(self, file_path, content_type):
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404)
            return
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    port = int(os.environ.get("PORT", "8787"))
    host = os.environ.get("HOST", "0.0.0.0")
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"ANU CS Assignment Analyse Helper running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
