from flask import Flask, render_template_string, request
import difflib
import re

app = Flask(__name__)

# Normalize text: trim spaces but keep returns (newlines) intact
def normalize_text(text):
    return "\n".join([line.strip() for line in text.splitlines() if line.strip()])

# Exclude both versions of the "attending review" line from the comparison
def remove_attending_review_line(text):
    excluded_lines = [
        "As the attending physician, I have personally reviewed the images, interpreted and/or supervised the study or procedure, and agree with the wording of the above report.",
        "As the Attending radiologist, I have personally reviewed the images, interpreted the study, and agree with the wording of the above report by Sterling M. Jones"
    ]
    return "\n".join([line for line in text.splitlines() if line.strip() not in excluded_lines])

# Function to extract sections by headers ending with a colon
def extract_sections(text):
    pattern = r'(.*?:)(.*?)(?=(?:\n.*?:)|\Z)'
    matches = re.findall(pattern, text, flags=re.DOTALL)
    sections = []
    for header, content in matches:
        sections.append({'header': header.strip(), 'content': content.strip()})
    return sections

# Function to calculate percentage change between two reports (word-by-word)
def calculate_change_percentage(resident_text, attending_text):
    resident_words = resident_text.split()
    attending_words = attending_text.split()
    matcher = difflib.SequenceMatcher(None, resident_words, attending_words)
    return round((1 - matcher.ratio()) * 100, 2)


import difflib
import re

def split_into_paragraphs(text):
    # Split the text into paragraphs based on double line breaks or single line breaks after punctuation
    paragraphs = re.split(r'\n{2,}|\n(?=\w)', text)
    return [para.strip() for para in paragraphs if para.strip()]

def create_diff_by_section(resident_text, attending_text):
    # Normalize text for comparison
    resident_text = normalize_text(resident_text)
    attending_text = normalize_text(remove_attending_review_line(attending_text))

    # Split text into paragraphs instead of sentences
    resident_paragraphs = split_into_paragraphs(resident_text)
    attending_paragraphs = split_into_paragraphs(attending_text)

    diff_html = ""

    # Use SequenceMatcher on the paragraph level first
    matcher = difflib.SequenceMatcher(None, resident_paragraphs, attending_paragraphs)
    for opcode, a1, a2, b1, b2 in matcher.get_opcodes():
        # Handle matched (equal) paragraphs
        if opcode == 'equal':
            for paragraph in resident_paragraphs[a1:a2]:
                diff_html += paragraph + "<br><br>"

        # Handle inserted paragraphs as a block
        elif opcode == 'insert':
            for paragraph in attending_paragraphs[b1:b2]:
                diff_html += f'<div style="color:lightgreen;">[Inserted: {paragraph}]</div><br><br>'

        # Handle deleted paragraphs as a block
        elif opcode == 'delete':
            for paragraph in resident_paragraphs[a1:a2]:
                diff_html += f'<div style="color:#ff6b6b;text-decoration:line-through;">[Deleted: {paragraph}]</div><br><br>'

        # Handle replacements by breaking down into smaller parts
        elif opcode == 'replace':
            res_paragraphs = resident_paragraphs[a1:a2]
            att_paragraphs = attending_paragraphs[b1:b2]
            for res_paragraph, att_paragraph in zip(res_paragraphs, att_paragraphs):
                # Apply word-by-word comparison within mismatched paragraphs
                diff_html += break_down_replacement(res_paragraph, att_paragraph)

    return diff_html

def break_down_replacement(res_paragraph, att_paragraph):
    # This function applies a finer word-level comparison within replacement paragraphs
    diff_html = ""
    word_matcher = difflib.SequenceMatcher(None, res_paragraph.split(), att_paragraph.split())

    for word_opcode, w_a1, w_a2, w_b1, w_b2 in word_matcher.get_opcodes():
        if word_opcode == 'equal':
            diff_html += " ".join(res_paragraph.split()[w_a1:w_a2]) + " "
        elif word_opcode == 'replace':
            # Show both deletions and insertions for replacements
            diff_html += (
                '<span style="color:#ff6b6b;text-decoration:line-through;">' +
                " ".join(res_paragraph.split()[w_a1:w_a2]) +
                '</span> <span style="color:lightgreen;">' +
                " ".join(att_paragraph.split()[w_b1:w_b2]) +
                '</span> '
            )
        elif word_opcode == 'delete':
            diff_html += (
                '<span style="color:#ff6b6b;text-decoration:line-through;">' +
                " ".join(res_paragraph.split()[w_a1:w_a2]) +
                '</span> '
            )
        elif word_opcode == 'insert':
            diff_html += (
                '<span style="color:lightgreen;">' +
                " ".join(att_paragraph.split()[w_b1:w_b2]) +
                '</span> '
            )

    return diff_html + "<br><br>"




# Function to extract cases from the pasted text block
def extract_cases(text):
    cases = re.split(r'\bCase\s+(\d+)', text, flags=re.IGNORECASE)  # Split by case numbers
    parsed_cases = []

    for i in range(1, len(cases), 2):  # We expect case numbers at odd indices
        case_num = cases[i]
        case_content = cases[i + 1].strip()

        # Split reports using a case-insensitive regex
        reports = re.split(r'\s*(Attending\s+Report\s*:|Resident\s+Report\s*:)\s*', case_content, flags=re.IGNORECASE)
        if len(reports) >= 3:
            # Initialize variables
            attending_report = ''
            resident_report = ''
            # Extract the reports
            report_indices = [j for j in range(1, len(reports), 2)]
            for idx in report_indices:
                report_type = reports[idx].strip().lower().replace(":", "")
                report_text = reports[idx + 1].strip()
                if 'attending' in report_type:
                    attending_report = report_text
                elif 'resident' in report_type:
                    resident_report = report_text

            # Only proceed if we have both reports
            if attending_report and resident_report:
                parsed_cases.append({
                    'case_num': case_num,
                    'resident_report': resident_report,
                    'attending_report': attending_report,
                    'percentage_change': calculate_change_percentage(resident_report, remove_attending_review_line(attending_report)),
                    'diff': create_diff_by_section(resident_report, attending_report)
                })
            else:
                # Skip cases without both reports
                continue
        else:
            # Skip if not enough parts
            continue

    return parsed_cases

# Main route to handle input and display output
@app.route('/', methods=['GET', 'POST'])
def index():
    sorted_cases = False
    case_data = []
    if request.method == 'POST':
        # Get the text input from the form
        text_block = request.form['report_text']
        case_data = extract_cases(text_block)

        # Sort by percentage change if requested
        if request.form.get('sort') == 'desc':
            sorted_cases = True
            case_data = sorted(case_data, key=lambda x: x['percentage_change'], reverse=True)

    # HTML template with Night Mode (dark background, light text) and no bold text
    template = """
    <html>
        <head>
            <title>Radiology Report Diff</title>
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css">
            <style>
                body {
                    background-color: #1e1e1e;
                    color: #dcdcdc;
                    font-family: Arial, sans-serif;
                }
                textarea, input, button {
                    background-color: #333333;
                    color: #dcdcdc;
                    border: 1px solid #555;
                }
                textarea {
                    background-color: #333333 !important;
                    color: #dcdcdc !important;
                    border: 1px solid #555 !important;
                }
                a {
                    color: lightblue;
                }
                h2, h3, h4 {
                    color: #f0f0f0;
                    font-weight: normal; /* Remove bold from headings */
                }
                .diff-output {
                    margin-top: 20px;
                    padding: 15px;
                    background-color: #2e2e2e;
                    border-radius: 8px;
                    border: 1px solid #555;
                    word-wrap: break-word;
                    white-space: normal;
                }
                pre {
                    white-space: pre-wrap;
                    word-wrap: break-word;
                    font-family: inherit; /* Use same font as the combined report */
                }
                .btn-primary {
                    background-color: #007bff;
                    border-color: #007bff;
                }
                .btn-secondary {
                    background-color: #6c757d;
                    border-color: #6c757d;
                }
                hr {
                    border-top: 1px solid #555;
                }
                .nav-tabs .nav-link {
                    background-color: #333;
                    border-color: #555;
                    color: #dcdcdc;
                }
                .nav-tabs .nav-link.active {
                    background-color: #007bff;
                    border-color: #007bff #007bff #333;
                    color: white; /* Improve contrast for active tab */
                }
                /* Scroll to Top button */
                #scrollToTopBtn {
                    position: fixed;
                    right: 30px;
                    bottom: 30px;
                    background-color: #007bff;
                    color: white;
                    padding: 10px 20px;
                    border-radius: 50px;
                    border: none;
                    cursor: pointer;
                    box-shadow: 0px 4px 6px rgba(0, 0, 0, 0.1);
                    font-size: 14px;
                    display: none;
                }
                #scrollToTopBtn:hover {
                    background-color: #0056b3;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h2 class="mt-4"><b>Compare Revisions</b></h2>
                <form method="POST" class="mb-4">
                    <div class="form-group mb-3">
                        <label for="report_text">Paste your reports block here:</label>
                        <textarea id="report_text" name="report_text" class="form-control" rows="10">{{ request.form.get('report_text', '') }}</textarea>
                    </div>
                    <button type="submit" class="btn btn-primary">Compare Reports</button>
                    <button type="submit" name="sort" value="desc" class="btn btn-secondary">Sort by Change %</button>
                </form>

                {% if case_data %}
                    <h3>Case Navigation</h3>
                    <ul>
                        {% for case in case_data %}
                            <li>
                                <a href="#case{{ case.case_num }}">Case {{ case.case_num }}</a> - {{ case.percentage_change }}% change
                            </li>
                        {% endfor %}
                    </ul>
                    <hr>

                    {% for case in case_data %}
                        <div id="case{{ case.case_num }}">
                            <h4>Case {{ case.case_num }} - {{ case.percentage_change }}% change</h4>
                            <ul class="nav nav-tabs" id="myTab{{ case.case_num }}" role="tablist">
                                <li class="nav-item" role="presentation">
                                    <button class="nav-link active" id="combined-tab{{ case.case_num }}" data-bs-toggle="tab" data-bs-target="#combined{{ case.case_num }}" type="button" role="tab" aria-controls="combined{{ case.case_num }}" aria-selected="true">Combined Report</button>
                                </li>
                                <li class="nav-item" role="presentation">
                                    <button class="nav-link" id="resident-tab{{ case.case_num }}" data-bs-toggle="tab" data-bs-target="#resident{{ case.case_num }}" type="button" role="tab" aria-controls="resident{{ case.case_num }}" aria-selected="false">Resident Report</button>
                                </li>
                                <li class="nav-item" role="presentation">
                                    <button class="nav-link" id="attending-tab{{ case.case_num }}" data-bs-toggle="tab" data-bs-target="#attending{{ case.case_num }}" type="button" role="tab" aria-controls="attending{{ case.case_num }}" aria-selected="false">Attending Report</button>
                                </li>
                            </ul>
                            <div class="tab-content" id="myTabContent{{ case.case_num }}">
                                <div class="tab-pane fade show active" id="combined{{ case.case_num }}" role="tabpanel" aria-labelledby="combined-tab{{ case.case_num }}">
                                    <div class="diff-output">
                                        {{ case.diff|safe }}
                                    </div>
                                </div>
                                <div class="tab-pane fade" id="resident{{ case.case_num }}" role="tabpanel" aria-labelledby="resident-tab{{ case.case_num }}">
                                    <div class="diff-output">
                                        <pre>{{ case.resident_report }}</pre>
                                    </div>
                                </div>
                                <div class="tab-pane fade" id="attending{{ case.case_num }}" role="tabpanel" aria-labelledby="attending-tab{{ case.case_num }}">
                                    <div class="diff-output">
                                        <pre>{{ case.attending_report }}</pre>
                                    </div>
                                </div>
                            </div>
                            <hr>
                        </div>
                    {% endfor %}
                {% endif %}
            </div>

            <!-- Scroll to Top Button -->
            <button id="scrollToTopBtn">Top</button>

            <script>
                // Get the button
                var mybutton = document.getElementById("scrollToTopBtn");

                // When the user scrolls down 20px from the top of the document, show the button
                window.onscroll = function() {
                    if (document.body.scrollTop > 20 || document.documentElement.scrollTop > 20) {
                        mybutton.style.display = "block";
                    } else {
                        mybutton.style.display = "none";
                    }
                };

                // When the user clicks on the button, scroll to the top of the document
                mybutton.onclick = function() {
                    document.body.scrollTop = 0;
                    document.documentElement.scrollTop = 0;
                };
            </script>

            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        </body>
    </html>
    """
    return render_template_string(template, case_data=case_data)

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
