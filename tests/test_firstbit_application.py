from scripts.firstbit_readonly_smoke import offline_smoke


def test_application_get_only_smoke():
    result = offline_smoke()
    assert result["result"] == "PASS"
    assert result["production_contact"] is False
    assert result["ai_calls"] == 4  # STT, legacy extraction, quantity patch, price/VAT/name patch.
    assert "quantity/price/VAT/description edits" in result["verified"]
    assert result["mutations"] == result["pdf_deliveries"] == 0
