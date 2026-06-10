"""Unit tests for stored radiology report template selection."""
from app.templates.report_templates import select_report_template


def test_greek_abdominal_ultrasound_template_selection():
    template = select_report_template("el", "US", "ABDOMEN", None)
    assert template.name == "ΥΠΕΡΗΧΟΓΡΑΦΗΜΑ ΑΝΩ ΚΑΙ ΚΑΤΩ ΚΟΙΛΙΑΣ"
    assert "Ήπαρ φυσιολογικού μεγέθους" in template.text
    assert "Ο ΙΑΤΡΟΣ ΑΚΤΙΝΟΛΟΓΟΣ" in template.text
    assert "______________________" in template.text
    assert template.physician is None


def test_greek_kidney_ultrasound_template_selection():
    template = select_report_template("el", "US", "KIDNEY", None)
    assert template.name == "ΥΠΕΡΗΧΟΓΡΑΦΗΜΑ ΝΕΦΡΩΝ"
    assert "Οι νεφροί είναι φυσιολογικού μεγέθους" in template.text
    assert "επινεφριδικών περιοχών" in template.text


def test_greek_kub_ultrasound_template_selection():
    template = select_report_template(
        "el",
        "US",
        "KIDNEY,URETER,BLADDER,PROSTATE",
        "ΥΠΕΡΗΧΟΓΡΑΦΗΜΑ ΝΕΦΡΩΝ—ΟΥΡΗΤΗΡΩΝ—ΟΥΡΟΔΟΧΟΥ ΚΥΣΤΕΩΣ—ΠΡΟΣΤΑΤΟΥ",
    )
    assert template.name == "ΥΠΕΡΗΧΟΓΡΑΦΗΜΑ ΝΕΦΡΩΝ—ΟΥΡΗΤΗΡΩΝ—ΟΥΡΟΔΟΧΟΥ ΚΥΣΤΕΩΣ—ΠΡΟΣΤΑΤΟΥ"
    assert "Φλοιώδεις κύστεις νεφρών άμφω" in template.text
    assert "Προστάτης αδένας" in template.text


def test_portuguese_abdominal_ultrasound_template_selection():
    template = select_report_template("pt", "US", "ABDOMEN", "Ecografia abdominal")
    assert template.name == "Ecografia abdominal"
    assert template.text.startswith("Fígado: tamanho e ecoestrutura normal")
    assert "Não alterações ecográficas de urgências" in template.text


def test_output_language_el_returns_greek_template_text():
    template = select_report_template("el", "CR", "CHEST", None)
    assert template.name == "ΑΚΤΙΝΟΓΡΑΦΙΑ ΘΩΡΑΚΟΣ"
    assert "ΑΚΤΙΝΟΓΡΑΦΙΑ ΘΩΡΑΚΟΣ" in template.text
    assert "Ευρήματα:" in template.text


def test_greek_chest_xray_two_view_template_selection():
    template = select_report_template("el", "CR", "CHEST", "Chest X-ray 2 Views")
    assert template.name == "ΑΚΤΙΝΟΓΡΑΦΙΑ ΘΩΡΑΚΟΣ 2 ΛΗΨΕΩΝ"
    assert template.text.startswith("ΑΚΤΙΝΟΓΡΑΦΙΑ ΘΩΡΑΚΟΣ 2 ΛΗΨΕΩΝ")
    assert "Συμπέρασμα:" in template.text


def test_output_language_pt_returns_portuguese_template_text():
    template = select_report_template("pt", "CR", "CHEST", None)
    assert "Relatório de Radiologia" in template.text
    assert "Achados:" in template.text


def test_fallback_is_full_template_style_not_short_summary():
    template = select_report_template("en", "MR", "BRAIN", None)
    assert template.name == "RADIOLOGY REPORT"
    assert "Clinical indication:" in template.text
    assert "Findings:" in template.text
    assert "Impression:" in template.text
    assert len(template.text.splitlines()) >= 8
