# Invoice print discovery

Standalone **read-only** external processor based on the existing MetadataBridge managed-form structure. It has no publication command. It reads metadata only, not invoices, customers or module bodies, and never calls print handlers. Source XML targets the locally available 8.3.21 / format 2.14 pair; a later live platform must still be tested separately.

## Build and run

From the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/onec-print-discovery/BUILD.ps1
```

The compiled artifact is `.local/firstbit/print-discovery/OneCInvoicePrintDiscovery.epf`; build evidence and an empty local test infobase are beside it. This creates only a private local infobase, not a production extension or HTTP endpoint. No credentials needed for build. The build preserves its logs/base for diagnosis; it does not delete other files.

Open the EPF in an empty local infobase first and press **Export print metadata (READ ONLY)**. `InventoryExpense not found` is expected in an empty base; JSON serialization and available collection enumeration must work. Then open the same EPF in FirstBit through the normal external-processor UI with an authorized identity and press the same button. No changes to the configuration, publication or business data are required by this tool. If the UI disallows external processors, the 1C administrator must run the same read-only export; do not bypass security.

Save the output JSON locally as `.local/firstbit/print-discovery/live-export.json`, then:

```powershell
.venv/Scripts/python.exe scripts/firstbit_print_discovery.py --input .local/firstbit/print-discovery/live-export.json
```

The analyzer makes no requests and writes `discovery-summary.json` only in the ignored private directory. Its console output contains counts/status only. Keep both raw export and summary private.

## Minimum two-pass discovery

First pass exports names of CommonModules/CommonCommands (no source or comments), HTTP service declared root/routes/method/handler when accessible, and commands/templates of **Document.InventoryExpense and Document.TaxInvoice** (schema v2; analyzer also accepts old v1 exports). Limits and unsupported properties produce explicit `gaps`; a partial export is never declared complete. Metadata visibility is not evidence that a service is published. Name filtering in the analyzer only suggests candidates and can miss differently named implementations; the complete private name index remains available for review.

Second pass needs only the actual relevant source from Designer/EDT, without changing the configuration:

- `Documents/TaxInvoice/Ext/ManagerModule.bsl`: print command registration, exact print entry point/signatures, native `TaxInvoiceLandscapeEN` template binding and direct dependencies. `Documents/InventoryExpense/Ext/ManagerModule.bsl`: native filling/validation/finalization and TaxInvoice creation entry points. Include directly relevant object-module routines when called, not the whole configuration.
- The actual module containing exported `GenerateTaxInvoice`, plus directly called relation lookup (`TaxInvoicesByBasis`, `TaxInvoiceFor`, `TaxInvoiceListFor` if used): exact signatures, linkage, transaction/duplicate checks and posting behavior. These names are observed in HAR; the owning module must be established from source, never guessed. Include current configuration/extension versions. The capture's already-posted result does not establish a universal auto-posting rule.
- The matching HTTPService XML plus `Ext/Module.bsl`, if a candidate exists: route/HTTP method/handler, argument binding, authorization, response Content-Type and return semantics. A GET handler must be reviewed for hidden mutations before calling it.
- Only CommonModule routines directly called by those print entry points, and declaration/type of the chosen InventoryExpense template. Do not export all CommonModules or template binaries initially. Runtime metadata does not expose module source; an empty source result is not evidence of no printing.
- Sanitized `httpServices` publication settings (no credentials, connection strings or unrelated services), including relevant extension services. Declaration alone cannot prove publication. Include configuration/extension versions and whether source reflects the current database configuration.

This determines whether a supported external mechanism can generate/read back the linked TaxInvoice and render its PDF. HAR already proves native UI generation and PDF export; **external invocation, direct HTTP PDF support and need for a new endpoint remain unknown**. A native client print command is not automatically an HTTP API. Do not try guessed `/hs/` routes, generic remote-evaluation endpoints or UI print-to-PDF.

If no callable supported API exists after that review, a minimal print endpoint should accept only a TaxInvoice UUID and the fixed native form, authenticate the integration identity, check document/issuer permissions, load the exact linked document, call its proved standard print routine and return bounded `application/pdf`. It must not create/post/fill/save documents or expose arbitrary module/method/query selection. Generation/finalization need separate explicit mutation handlers with operation identity, transaction/uniqueness and authoritative read-back; they must never hide inside GET/printing. If the print routine mutates data or requires a write, report that fact rather than label it read-only. Endpoint implementation/publication follows reviewed source evidence; this package does not install one.

Project status, write admission and actual provider findings belong to [PRODUCTION_OPERATION](../../docs/firstbit/PRODUCTION_OPERATION.md).
