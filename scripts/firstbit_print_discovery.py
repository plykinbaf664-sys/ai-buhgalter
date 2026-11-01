"""Validate a local metadata-only export. Never connects to 1C or invokes printing."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Annotated, Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pydantic import Field, model_validator
from app.domain import StrictModel

Name = Annotated[str, Field(min_length=1, max_length=256)]
Text = Annotated[str, Field(max_length=2048)]


class Named(StrictModel):
    name: Name


class Method(Named):
    http_method: Text | None = None
    handler: Text | None = None


class Route(Named):
    template: Text | None = None
    methods: Annotated[list[Method], Field(max_length=5000)]


class Service(Named):
    root_url: Text | None = None
    routes: Annotated[list[Route], Field(max_length=5000)]


class Document(StrictModel):
    name: Literal['InventoryExpense', 'TaxInvoice'] | None = None
    commands: Annotated[list[Named], Field(max_length=5000)] = Field(default_factory=list)
    templates: Annotated[list[Named], Field(max_length=5000)] = Field(default_factory=list)


class Discovery(StrictModel):
    schema_version: Literal[1, 2]
    scope: Literal['InventoryExpense_print_metadata_only', 'Invoice_TaxInvoice_print_metadata_only']
    configuration_name: Name
    configuration_version: Text
    runtime_module_source_available: Literal[False]
    publication_verified: Literal[False]
    native_pdf_verified: Literal[False]
    http_services: Annotated[list[Service], Field(max_length=5000)]
    common_modules: Annotated[list[Named], Field(max_length=5000)]
    common_commands: Annotated[list[Named], Field(max_length=5000)]
    document: Document
    tax_document: Document | None = None
    gaps: Annotated[list[Text], Field(max_length=5000)]
    metadata_complete: bool

    @model_validator(mode='after')
    def consistent_completeness(self):
        if self.document.name not in (None, 'InventoryExpense'):
            raise ValueError('Unexpected source document')
        if self.schema_version == 1:
            if self.scope != 'InventoryExpense_print_metadata_only' or self.tax_document is not None:
                raise ValueError('Unexpected legacy export scope')
        elif (self.scope != 'Invoice_TaxInvoice_print_metadata_only' or self.tax_document is None
              or self.tax_document.name not in (None, 'TaxInvoice')
              or self.tax_document.name is None and not self.gaps):
            raise ValueError('Missing linked document discovery')
        if self.metadata_complete != (not self.gaps):
            raise ValueError('Inconsistent completeness')
        if self.document.name is None and not self.gaps:
            raise ValueError('Missing document discovery')
        for collection in (self.http_services, self.common_modules, self.common_commands):
            if len({item.name for item in collection}) != len(collection):
                raise ValueError('Duplicate metadata identity')
        return self


def summarize(raw: bytes) -> dict:
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError('Discovery export exceeds bound')
    result = Discovery.model_validate_json(raw)
    keywords = ('print', 'invoice', 'печат', 'счет', 'счёт')
    candidate = lambda text: any(word in text.casefold() for word in keywords)
    routes = []
    for service in result.http_services:
        for route in service.routes:
            for method in route.methods:
                context = ' '.join((service.name, service.root_url or '', route.name,
                                    route.template or '', method.handler or ''))
                if candidate(context):
                    routes.append({'service': service.name, 'root_url': service.root_url,
                                   'template': route.template, 'method': method.http_method,
                                   'handler': method.handler, 'verified_safe_to_call': False})
    return {'export_sha256': hashlib.sha256(raw).hexdigest(),
            'status': 'NEEDS_HANDLER_AND_PUBLICATION_EVIDENCE',
            'metadata_complete': result.metadata_complete, 'gaps': result.gaps,
            'http_service_count': len(result.http_services),
            'common_module_count': len(result.common_modules),
            'document': result.document.model_dump(), 'candidate_routes': routes,
            'tax_document': result.tax_document.model_dump() if result.tax_document else None,
            'candidate_modules': [item.name for item in result.common_modules if candidate(item.name)],
            'candidate_common_commands': [item.name for item in result.common_commands if candidate(item.name)],
            'candidate_filter_is_exhaustive': False,
            'mechanism_verified': False, 'exact_invoice_invocation': None,
            'direct_pdf_available': 'UNKNOWN', 'new_http_endpoint_required': 'UNKNOWN',
            'network_requests': 0, 'business_reads': 0, 'financial_mutations': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    args = parser.parse_args()
    private = Path(__file__).resolve().parents[1] / '.local/firstbit/print-discovery'
    try:
        path = args.input.resolve(strict=True)
        if not path.is_relative_to(private.resolve()) or path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('Expected bounded private input')
        summary = summarize(path.read_bytes())
        output = private / 'discovery-summary.json'
        output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({key: summary[key] for key in ('status', 'metadata_complete', 'http_service_count',
                                                       'common_module_count', 'network_requests', 'financial_mutations')}))
    except (ValueError, OSError):
        print('DISCOVERY_INVALID: private export missing, incomplete schema or unsafe input')
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
