"""Stored radiology report templates and deterministic template selection."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

SUPPORTED_LANGUAGES = {"el", "pt", "en", "ar"}


def build_greek_signature_block(
    physician_name: str | None = None,
    physician_code: str | None = None,
) -> str:
    """Return the Greek signing block using request-provided physician details when available."""
    name = (physician_name or "").strip()
    code = (physician_code or "").strip()
    if not name and not code:
        return "Ο ΙΑΤΡΟΣ ΑΚΤΙΝΟΛΟΓΟΣ\n\n______________________"

    lines = ["Ο ΙΑΤΡΟΣ ΑΚΤΙΝΟΛΟΓΟΣ", ""]
    lines.append(name or "______________________")
    if code:
        lines.append(f"(κωδικός: {code})")
    return "\n".join(lines)


_SIGNATURE_BLOCK_EL = build_greek_signature_block()


def _build_greek_chest_xray_text(title: str) -> str:
    return (
        f"{title}\n\n"
        "Κλινική ένδειξη:\n"
        "Αναμένεται συμπλήρωση της κλινικής ένδειξης από τον παραπέμποντα ιατρό.\n\n"
        "Τεχνική:\n"
        "Αναμένεται συμπλήρωση της τεχνικής από τον ακτινολόγο.\n\n"
        "Ευρήματα:\n"
        "Αναμένεται συμπλήρωση των ευρημάτων από τον ακτινολόγο.\n\n"
        "Συμπέρασμα:\n"
        "Αναμένεται συμπλήρωση του συμπεράσματος από τον ακτινολόγο.\n\n"
        f"{_SIGNATURE_BLOCK_EL}"
    )

_GREEK_US_ABDOMEN_NAME = "ΥΠΕΡΗΧΟΓΡΑΦΗΜΑ ΑΝΩ ΚΑΙ ΚΑΤΩ ΚΟΙΛΙΑΣ"
_GREEK_US_ABDOMEN_TEXT = (
    f"{_GREEK_US_ABDOMEN_NAME}\n\n"
    "Ήπαρ φυσιολογικού μεγέθους και ηχοδομής, χωρίς εστιακές αλλοιώσεις.\n"
    "Χοληδόχος κύστη χωρίς ηχωγενές ενδοαυλικό περιεχόμενο, με φυσιολογικό πάχος τοιχώματος.\n"
    "Ένδο- έξωηπατικά χοληφόρα χωρίς διάταση.\n"
    "Πάγκρεας, στο βαθμό ελέγχου, φυσιολογικού μεγέθους χωρίς εστιακές αλλοιώσεις.\n"
    "Σπλήνας φυσιολογικού μεγέθους και ηχοδομής, χωρίς εστιακές αλλοιώσεις.\n"
    "Οι νεφροί είναι φυσιολογικού μεγέθους, ηχοδομής και πάχους φλοιού.\n"
    "Δεν παρατηρείται διάταση των πυελοκαλυκικών συστημάτων, ούτε των ανωτέρων τμημάτων των ουρητήρων.\n"
    "Επίσης δεν ελέγχεται ύπαρξη λίθου με μέγεθος μεγαλύτερο των 3mm.\n"
    "Η κοιλιακή αορτή απεικονίζεται με φυσιολογικό εύρος και ομαλό τοίχωμα χωρίς παρουσία αθηρωματικών πλακών και τοιχωματικών αποτιτανώσεων.\n"
    "Η ουροδόχος κύστη παρουσιάζει φυσιολογική διάταση, ομαλό τοίχωμα και δεν περιέχει ηχωγενή λιθιασικά στοιχεία.\n"
    "Μετά την ούρηση η ουροδόχος κύστη περιέχει περίπου 30ml υπολείμματος ούρων.\n"
    "Προστάτης αδένας διαστάσεων 5,2cm X 5,2cm X 5,2cm και όγκου 60cm3, αυξημένου μεγέθους με αποτιτανώσεις στο παρέγχυμα και ενδοκυστική προβολή μέσου λοβού.\n\n"
    f"{_SIGNATURE_BLOCK_EL}"
)

_GREEK_US_KIDNEY_NAME = "ΥΠΕΡΗΧΟΓΡΑΦΗΜΑ ΝΕΦΡΩΝ"
_GREEK_US_KIDNEY_TEXT = (
    f"{_GREEK_US_KIDNEY_NAME}\n\n"
    "Οι νεφροί είναι φυσιολογικού μεγέθους, ηχοδομής και πάχους φλοιού.\n"
    "Δεν παρατηρείται διάταση των πυελοκαλυκικών συστημάτων, ούτε των ανωτέρων τμημάτων των ουρητήρων.\n"
    "Επίσης δεν ελέγχεται ύπαρξη λίθου με μέγεθος μεγαλύτερο των 3mm.\n\n"
    "Από το έλεγχο των επινεφριδικών περιοχών δεν παρατηρήθηκαν αδρές εστιακές αλλοιώσεις.\n\n"
    f"{_SIGNATURE_BLOCK_EL}"
)

_GREEK_US_KUB_NAME = "ΥΠΕΡΗΧΟΓΡΑΦΗΜΑ ΝΕΦΡΩΝ—ΟΥΡΗΤΗΡΩΝ—ΟΥΡΟΔΟΧΟΥ ΚΥΣΤΕΩΣ—ΠΡΟΣΤΑΤΟΥ"
_GREEK_US_KUB_TEXT = (
    f"{_GREEK_US_KUB_NAME}\n\n"
    "Οι νεφροί είναι φυσιολογικού μεγέθους, ηχοδομής και πάχους φλοιού.\n"
    "Δεν παρατηρείται διάταση των πυελοκαλυκικών συστημάτων, ούτε των ανωτέρων τμημάτων των ουρητήρων.\n"
    "Επίσης δεν ελέγχεται ύπαρξη λίθου με μέγεθος μεγαλύτερο των 3mm.\n"
    "Φλοιώδεις κύστεις νεφρών άμφω.\n"
    "Η ουροδόχος κύστη παρουσιάζει φυσιολογική διάταση, ομαλό τοίχωμα και δεν περιέχει ηχωγενή λιθιασικά στοιχεία.\n"
    "Μετά την ούρηση η ουροδόχος κύστη περιέχει περίπου 30ml υπολείμματος ούρων.\n"
    "Προστάτης αδένας διαστάσεων 5,2cm X 5,2cm X 5,2cm και όγκου 60cm3, αυξημένου μεγέθους με αποτιτανώσεις στο παρέγχυμα και ενδοκυστική προβολή μέσου λοβού.\n\n"
    f"{_SIGNATURE_BLOCK_EL}"
)

_GREEK_CHEST_XR_NAME = "ΑΚΤΙΝΟΓΡΑΦΙΑ ΘΩΡΑΚΟΣ"
_GREEK_CHEST_XR_TEXT = _build_greek_chest_xray_text(_GREEK_CHEST_XR_NAME)

_GREEK_CHEST_XR_2VIEWS_NAME = "ΑΚΤΙΝΟΓΡΑΦΙΑ ΘΩΡΑΚΟΣ 2 ΛΗΨΕΩΝ"
_GREEK_CHEST_XR_2VIEWS_TEXT = _build_greek_chest_xray_text(_GREEK_CHEST_XR_2VIEWS_NAME)

_PORTUGUESE_US_ABDOMEN_NAME = "Ecografia abdominal"
_PORTUGUESE_US_ABDOMEN_TEXT = (
    "Fígado: tamanho e ecoestrutura normal, contornos regulares, não imagem de lesão sólida, não quisto, não dilatação de VB intra-hepáticas, não metástases.\n"
    "Vesícula B: Parede vesicular de espessura normal, conteúdo vesicular anecogênico, sem cálculos.\n"
    "Pâncreas: morfologia, dimensões e ecogenicidade normais, não há dilatação do ducto pancreático principal.\n\n"
    "Rins tópicos, de morfologia, contornos e dimensões normais, camada córtico-medular de ecogenicidade e espessura normais, complexo ecogênico central compacto e normorrefringente, não há evidências de hidronefrose ou de imagens calculosas.\n\n"
    "Áreas suprarrenais: normais.\n"
    "Aorta abdominal e veia cava inferior com trajeto e calibre normais.\n"
    "Baço: morfologia, dimensões e ecogenicidade normais.\n"
    "Bexiga urinária de morfologia, contornos e repleção normais. Paredes vesicais regulares, sem imagens endoluminais ou parietais anómalas, conteúdo líquido anecóico, jactos ureterais normais.\n"
    "Não líquido livre. Não dilatação de ansas intestinais delgadas. Fossas ilíacas livres.\n\n"
    "ID: estudo dentro da normalidade.\n\n"
    "Não alterações ecográficas de urgências.\n"
    "Não adenomegalias intrabdominais."
)

_FALLBACK_TEMPLATES: dict[str, tuple[str, str, Optional[str]]] = {
    "el": (
        "ΑΚΤΙΝΟΛΟΓΙΚΗ ΕΚΘΕΣΗ",
        (
            "ΑΚΤΙΝΟΛΟΓΙΚΗ ΕΚΘΕΣΗ\n\n"
            "Κλινική ένδειξη: Δεν αναφέρεται.\n"
            "Τεχνική: Η εξέταση εκτελέστηκε σύμφωνα με το πρότυπο πρωτόκολλο του τμήματος.\n\n"
            "Ευρήματα:\n"
            "Δεν παρατηρούνται εστιακές παθολογικές αλλοιώσεις στο βαθμό ελέγχου της μελέτης.\n"
            "Δεν υπάρχει εικόνα ελεύθερου υγρού ή συλλογής.\n"
            "Τα ανατομικά όρια απεικονίζονται εντός φυσιολογικών ορίων.\n\n"
            "Συμπέρασμα:\n"
            "Μελέτη χωρίς αξιολογήσιμη παθολογική εικόνα στο παρόν στάδιο αξιολόγησης.\n\n"
            f"{_SIGNATURE_BLOCK_EL}"
        ),
        None,
    ),
    "pt": (
        "Relatório de Radiologia",
        (
            "Relatório de Radiologia\n\n"
            "Indicação clínica: Não referida.\n"
            "Técnica: Exame realizado segundo o protocolo padrão do serviço.\n\n"
            "Achados:\n"
            "Não se observam alterações focais patológicas no âmbito avaliado.\n"
            "Sem evidência de líquido livre ou coleções.\n"
            "Estruturas anatómicas com morfologia e dimensões dentro dos limites habituais.\n\n"
            "Conclusão:\n"
            "Exame sem alterações ecográficas/radiológicas significativas na presente avaliação.\n"
        ),
        None,
    ),
    "en": (
        "RADIOLOGY REPORT",
        (
            "RADIOLOGY REPORT\n\n"
            "Clinical indication: Not stated.\n"
            "Technique: The study was performed according to the department standard protocol.\n\n"
            "Findings:\n"
            "No focal pathological abnormality is identified within the evaluated field of view.\n"
            "No free fluid or collection is seen.\n"
            "Anatomical structures are within expected limits.\n\n"
            "Impression:\n"
            "No significant radiological abnormality identified on the current evaluation.\n"
        ),
        None,
    ),
    "ar": (
        "تقرير الأشعة",
        (
            "تقرير الأشعة\n\n"
            "الاستطباب السريري: غير مذكور.\n"
            "الطريقة: أُجري الفحص وفق البروتوكول المعتاد في القسم.\n\n"
            "النتائج:\n"
            "لا توجد تغيرات مرضية بؤرية ضمن نطاق التقييم.\n"
            "لا يوجد سائل حر أو تجمع.\n"
            "الهياكل التشريحية ضمن الحدود المتوقعة.\n\n"
            "الانطباع:\n"
            "لا توجد حالة إشعاعية مهمة في التقييم الحالي.\n"
        ),
        None,
    ),
}

_MODALITY_ALIASES = {
    "US": "ultrasound",
    "ULTRASOUND": "ultrasound",
    "ECHO": "ultrasound",
    "ECO": "ultrasound",
    "ECOGRAFIA": "ultrasound",
    "ΥΠΕΡΗΧΟΓΡΑΦΗΜΑ": "ultrasound",
    "XR": "xray",
    "XRY": "xray",
    "CR": "xray",
    "DX": "xray",
}

_BODY_PART_ALIASES = {
    "ABDOMEN": "abdomen",
    "ABDOMINAL": "abdomen",
    "ΚΟΙΛΙΑ": "abdomen",
    "ΚΟΙΛΙΑΣ": "abdomen",
    "KIDNEY": "kidney",
    "KIDNEYS": "kidney",
    "RENAL": "kidney",
    "NEPHRO": "kidney",
    "ΝΕΦΡΩΝ": "kidney",
    "ΝΕΦΡΩΝΩΝ": "kidney",
    "RINS": "kidney",
    "BLADDER": "bladder",
    "URINARY": "bladder",
    "ΚΥΣΤΗ": "bladder",
    "ΟΥΡΟΔΟΧΟΥ": "bladder",
    "ΟΥΡΟΔΟΧΟΣ": "bladder",
    "URETER": "ureter",
    "ΟΥΡΗΤΗΡ": "ureter",
    "ΟΥΡΗΤΗΡΩΝ": "ureter",
    "PROSTATE": "prostate",
    "ΠΡΟΣΤΑΤΟΥ": "prostate",
    "ΠΡΟΣΤΑΤΗΣ": "prostate",
    "CHEST": "chest",
    "THORAX": "chest",
    "ΘΩΡΑΚΟΣ": "chest",
    "ΘΩΡΑΚΑ": "chest",
}

_KUB_EXAM_MARKERS = (
    "ΝΕΦΡΩΝ—ΟΥΡΗΤΗΡΩΝ",
    "ΝΕΦΡΩΝ-ΟΥΡΗΤΗΡΩΝ",
    "KIDNEY/URETER/BLADDER",
    "KIDNEYS URETER BLADDER",
    "KUB",
    "ΟΥΡΟΔΟΧΟΥ ΚΥΣΤΕΩΣ",
    "ΟΥΡΟΔΟΧΟΣ ΚΥΣΤΗ",
    "ΠΡΟΣΤΑΤΟΥ",
    "PROSTATE",
)

_ABDOMEN_EXAM_MARKERS = (
    "ΑΝΩ ΚΑΙ ΚΑΤΩ ΚΟΙΛΙΑΣ",
    "ΑΝΩ ΚΑΤΩ ΚΟΙΛΙΑΣ",
    "UPPER AND LOWER ABDOMEN",
    "ABDOMINAL ULTRASOUND",
    "ECOGRAFIA ABDOMINAL",
    "ECOGRAFIA ABDOMINAL",
)

_KIDNEY_EXAM_MARKERS = (
    "ΥΠΕΡΗΧΟΓΡΑΦΗΜΑ ΝΕΦΡΩΝ",
    "KIDNEY ULTRASOUND",
    "RENAL ULTRASOUND",
    "US KIDNEY",
)

_CHEST_EXAM_MARKERS = (
    "CHEST X-RAY",
    "CHEST XRAY",
    "CHEST RADIOGRAPH",
    "PA/LATERAL CHEST",
    "PA LATERAL CHEST",
    "ΑΚΤΙΝΟΓΡΑΦΙΑ ΘΩΡΑΚ",
    "ΘΩΡΑΚΟΣ",
    "ΘΩΡΑΚΑ",
)

_CHEST_TWO_VIEW_MARKERS = (
    "2 VIEWS",
    "TWO VIEWS",
    "PA/LATERAL",
    "PA AND LATERAL",
    "2 ΛΗΨ",
    "ΔΥΟ ΛΗΨ",
)


@dataclass(frozen=True)
class ReportTemplate:
    """Selected report template with optional signing physician."""

    name: str
    text: str
    physician: Optional[str] = None


def _normalize_token(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value).strip()).upper()


def _normalize_language(output_language: Optional[str]) -> str:
    language = (output_language or "el").strip().lower()
    return language if language in SUPPORTED_LANGUAGES else "el"


def _normalize_modality(modality: Optional[str]) -> str:
    token = _normalize_token(modality)
    if not token:
        return ""
    if token in _MODALITY_ALIASES:
        return _MODALITY_ALIASES[token]
    for alias, normalized in _MODALITY_ALIASES.items():
        if alias in token:
            return normalized
    if "ΥΠΕΡΗΧ" in token:
        return "ultrasound"
    return token.lower()


def _extract_body_part_tokens(body_part: Optional[str]) -> set[str]:
    raw = _normalize_token(body_part)
    if not raw:
        return set()
    tokens: set[str] = set()
    for chunk in re.split(r"[,;/\-\s]+", raw):
        chunk = chunk.strip()
        if not chunk:
            continue
        mapped = _BODY_PART_ALIASES.get(chunk)
        if mapped:
            tokens.add(mapped)
        else:
            for alias, normalized in _BODY_PART_ALIASES.items():
                if alias in chunk:
                    tokens.add(normalized)
    if not tokens and raw in _BODY_PART_ALIASES:
        tokens.add(_BODY_PART_ALIASES[raw])
    return tokens


def _exam_contains_any(exam_type: str, markers: tuple[str, ...]) -> bool:
    return any(marker in exam_type for marker in markers)


def _is_kub_exam(exam_type: str, body_part_tokens: set[str]) -> bool:
    if _exam_contains_any(exam_type, _KUB_EXAM_MARKERS):
        return True
    kub_parts = {"kidney", "ureter", "bladder", "prostate"}
    matched = body_part_tokens & kub_parts
    if len(matched) >= 2:
        return True
    if "bladder" in matched and ("kidney" in matched or "ureter" in matched or "prostate" in matched):
        return True
    if "prostate" in matched and ("kidney" in matched or "ureter" in matched or "bladder" in matched):
        return True
    return False


def _is_kidney_only_exam(exam_type: str, body_part_tokens: set[str]) -> bool:
    if _is_kub_exam(exam_type, body_part_tokens):
        return False
    if _exam_contains_any(exam_type, _KIDNEY_EXAM_MARKERS):
        return True
    return body_part_tokens == {"kidney"} or (
        "kidney" in body_part_tokens and not body_part_tokens.intersection({"ureter", "bladder", "prostate"})
    )


def _is_abdomen_exam(exam_type: str, body_part_tokens: set[str]) -> bool:
    if _exam_contains_any(exam_type, _ABDOMEN_EXAM_MARKERS):
        return True
    return "abdomen" in body_part_tokens


def _is_chest_exam(exam_type: str, body_part_tokens: set[str]) -> bool:
    if _exam_contains_any(exam_type, _CHEST_EXAM_MARKERS):
        return True
    return "chest" in body_part_tokens


def _is_two_view_chest_exam(exam_type: str) -> bool:
    return _exam_contains_any(exam_type, _CHEST_TWO_VIEW_MARKERS)


def select_report_template(
    output_language: str,
    modality: str | None,
    body_part: str | None,
    exam_type: str | None,
) -> ReportTemplate:
    """Return the best stored template for the requested exam context."""
    language = _normalize_language(output_language)
    normalized_modality = _normalize_modality(modality)
    exam_type_norm = _normalize_token(exam_type)
    body_part_tokens = _extract_body_part_tokens(body_part)

    if normalized_modality == "ultrasound":
        if language == "el":
            if _is_kub_exam(exam_type_norm, body_part_tokens):
                return ReportTemplate(_GREEK_US_KUB_NAME, _GREEK_US_KUB_TEXT)
            if _is_kidney_only_exam(exam_type_norm, body_part_tokens):
                return ReportTemplate(_GREEK_US_KIDNEY_NAME, _GREEK_US_KIDNEY_TEXT)
            if _is_abdomen_exam(exam_type_norm, body_part_tokens):
                return ReportTemplate(_GREEK_US_ABDOMEN_NAME, _GREEK_US_ABDOMEN_TEXT)
        if language == "pt" and _is_abdomen_exam(exam_type_norm, body_part_tokens):
            return ReportTemplate(_PORTUGUESE_US_ABDOMEN_NAME, _PORTUGUESE_US_ABDOMEN_TEXT)

    if normalized_modality == "xray" and language == "el" and _is_chest_exam(exam_type_norm, body_part_tokens):
        if _is_two_view_chest_exam(exam_type_norm):
            return ReportTemplate(_GREEK_CHEST_XR_2VIEWS_NAME, _GREEK_CHEST_XR_2VIEWS_TEXT)
        return ReportTemplate(_GREEK_CHEST_XR_NAME, _GREEK_CHEST_XR_TEXT)

    fallback_name, fallback_text, fallback_physician = _FALLBACK_TEMPLATES[language]
    return ReportTemplate(fallback_name, fallback_text, fallback_physician)
