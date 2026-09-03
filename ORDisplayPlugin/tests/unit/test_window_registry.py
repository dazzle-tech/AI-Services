"""Window name / role routing for EMR tabs."""

import pytest
from fastapi import HTTPException

from app.core.window_registry import NURSING_TAB, resolve_window_id


@pytest.mark.parametrize(
    "sub_tab,window_id",
    [
        ("Verification of Marking Site", "nursing_verification_of_marking_site"),
        ("Time Out", "nursing_time_out"),
        ("Intraoperative", "nursing_intraoperative"),
        ("Sign Out", "nursing_sign_out"),
    ],
)
def test_nursing_tab_sub_tabs_resolve(sub_tab, window_id):
    assert sub_tab in NURSING_TAB["sub_tabs"]
    assert resolve_window_id("Nursing", sub_tab) == window_id
    assert resolve_window_id("nurse", sub_tab) == window_id
    assert resolve_window_id("", f"Nursing / {sub_tab}") == window_id


def test_unknown_nursing_sub_tab_422():
    with pytest.raises(HTTPException) as exc:
        resolve_window_id("Nursing", "Not A Sub Tab")
    assert exc.value.status_code == 422
