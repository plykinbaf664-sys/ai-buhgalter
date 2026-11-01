"""Synthetic metadata only: discovery never proves a route safe to invoke."""
import importlib.util
import json
from pathlib import Path

import pytest

from scripts.firstbit_print_discovery import summarize


def export():
    return {'schema_version': 1, 'scope': 'InventoryExpense_print_metadata_only',
            'configuration_name': 'SyntheticConfiguration', 'configuration_version': 'test',
            'runtime_module_source_available': False, 'publication_verified': False,
            'native_pdf_verified': False,
            'http_services': [{'name': 'SyntheticPrint', 'root_url': 'print',
                               'routes': [{'name': 'Invoice', 'template': '/{id}',
                                           'methods': [{'name': 'Get', 'http_method': 'GET',
                                                        'handler': 'GetInvoice'}]}]}],
            'common_modules': [{'name': 'SyntheticPrinting'}], 'common_commands': [],
            'document': {'name': 'InventoryExpense', 'commands': [],
                         'templates': [{'name': 'SyntheticInvoice'}]},
            'metadata_complete': True, 'gaps': []}


def encoded(data):
    return json.dumps(data).encode()


def test_names_and_get_route_do_not_prove_safe_native_pdf_or_publication():
    result = summarize(encoded(export()))
    assert result['candidate_routes'][0]['verified_safe_to_call'] is False
    assert result['mechanism_verified'] is False
    assert result['direct_pdf_available'] == result['new_http_endpoint_required'] == 'UNKNOWN'
    assert result['exact_invoice_invocation'] is None
    assert result['network_requests'] == result['financial_mutations'] == 0


def test_linked_tax_metadata_export_preserves_discovery_boundary():
    data = export()
    data.update(schema_version=2, scope='Invoice_TaxInvoice_print_metadata_only',
                tax_document={'name': 'TaxInvoice', 'commands': [],
                              'templates': [{'name': 'SyntheticTaxLandscape'}]})
    result = summarize(encoded(data))
    assert result['tax_document']['name'] == 'TaxInvoice'
    assert result['mechanism_verified'] is False and result['network_requests'] == 0
    del data['tax_document']
    with pytest.raises(ValueError):
        summarize(encoded(data))
    data['tax_document'] = {}
    with pytest.raises(ValueError):
        summarize(encoded(data))
    data.update(metadata_complete=False, gaps=['TaxInvoice not found'])
    assert summarize(encoded(data))['metadata_complete'] is False


def test_nonmatching_names_do_not_prove_absence_of_printing():
    data = export()
    data['http_services'] = []
    data['common_modules'] = [{'name': 'GenericOutput'}]
    result = summarize(encoded(data))
    assert result['candidate_modules'] == []
    assert result['candidate_filter_is_exhaustive'] is False
    assert result['new_http_endpoint_required'] == 'UNKNOWN'


def test_gaps_remain_visible_and_block_completeness_claim():
    data = export()
    data.update(metadata_complete=False, gaps=['HTTPService.SyntheticPrint: method properties unavailable'])
    data['http_services'][0]['routes'][0]['methods'] = [{'name': 'Get'}]
    result = summarize(encoded(data))
    assert not result['metadata_complete'] and result['gaps']
    data['metadata_complete'] = True
    with pytest.raises(ValueError):
        summarize(encoded(data))


@pytest.mark.parametrize('field', ['native_pdf_verified', 'publication_verified', 'runtime_module_source_available'])
def test_export_cannot_self_attest_capabilities(field):
    data = export()
    data[field] = True
    with pytest.raises(ValueError):
        summarize(encoded(data))


def test_business_records_unexpected_fields_duplicates_and_bounds_rejected():
    data = export()
    data['customers'] = [{'name': 'Synthetic Customer'}]
    with pytest.raises(ValueError):
        summarize(encoded(data))
    data = export()
    data['common_modules'] *= 2
    with pytest.raises(ValueError):
        summarize(encoded(data))
    with pytest.raises(ValueError):
        summarize(b' ' * (8 * 1024 * 1024 + 1))
    data = export()
    data['common_modules'] *= 5001
    with pytest.raises(ValueError):
        summarize(encoded(data))


def test_processor_form_audit_and_no_publication_command():
    root = Path(__file__).resolve().parents[1] / 'tools/onec-print-discovery'
    spec = importlib.util.spec_from_file_location('discovery_preflight', root / 'preflight.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.audit(root)
    assert result['static_audit'] == 'PASS'
    assert result['form_commands'] == ['Export']
