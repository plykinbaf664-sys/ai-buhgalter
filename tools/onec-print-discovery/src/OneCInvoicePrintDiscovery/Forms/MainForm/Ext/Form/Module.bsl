// Standalone derivative of MetadataBridge managed-form layout, XML 2.14.
// Metadata only. Never invokes a handler, printer, business query or publication.

&AtClient
Procedure OnOpen(Cancel)
    // Explicit local smoke mode writes only a local metadata JSON file.
    If LaunchParameter = "AI_PRINT_DISCOVERY_SMOKE" Then
        ExportAtServer();
        LocalText = New TextDocument;
        LocalText.SetText(OutputJSON);
        LocalText.Write(TempFilesDir() + "ai-print-discovery-smoke.json", TextEncoding.UTF8);
        ЗавершитьРаботуСистемы(Ложь);
    EndIf;
EndProcedure

&AtClient
Procedure CommandExport(Command)
    ExportAtServer();
EndProcedure

&AtServer
Procedure ExportAtServer()
    OutputJSON = "";
    Try
        Snapshot = New Structure;
        Snapshot.Insert("schema_version", 2);
        Snapshot.Insert("scope", "Invoice_TaxInvoice_print_metadata_only");
        Snapshot.Insert("configuration_name", Metadata.Name);
        Snapshot.Insert("configuration_version", Metadata.Version);
        Snapshot.Insert("runtime_module_source_available", False);
        Snapshot.Insert("publication_verified", False);
        Snapshot.Insert("native_pdf_verified", False);
        Gaps = New Array;
        Services = New Array;
        Try
            For Each Service In Metadata.HTTPServices Do
                EnsureLimit(Services);
                Entry = MetadataName(Service);
                Routes = New Array;
                Try
                    Entry.Insert("root_url", String(Service.RootURL));
                    For Each Route In Service.URLTemplates Do
                        EnsureLimit(Routes);
                        RouteEntry = MetadataName(Route);
                        Methods = New Array;
                        Try
                            RouteEntry.Insert("template", String(Route.Template));
                            For Each Method In Route.Methods Do
                                EnsureLimit(Methods);
                                MethodEntry = MetadataName(Method);
                                Try
                                    MethodEntry.Insert("http_method", String(Method.HTTPMethod));
                                    MethodEntry.Insert("handler", String(Method.Handler));
                                Except
                                    Gaps.Add("HTTPService." + Service.Name + ": method properties unavailable");
                                EndTry;
                                Methods.Add(MethodEntry);
                            EndDo;
                        Except
                            Gaps.Add("HTTPService." + Service.Name + ": route properties unavailable");
                        EndTry;
                        RouteEntry.Insert("methods", Methods);
                        Routes.Add(RouteEntry);
                    EndDo;
                Except
                    Gaps.Add("HTTPService." + Service.Name + ": route metadata unavailable");
                EndTry;
                Entry.Insert("routes", Routes);
                Services.Add(Entry);
            EndDo;
        Except
            Gaps.Add("HTTPServices collection incomplete or unavailable");
        EndTry;
        Snapshot.Insert("http_services", Services);
        Modules = New Array;
        Try
            For Each Module In Metadata.CommonModules Do
                EnsureLimit(Modules);
                Modules.Add(MetadataName(Module));
            EndDo;
        Except
            Gaps.Add("CommonModules collection incomplete or unavailable");
        EndTry;
        Snapshot.Insert("common_modules", Modules);
        Commands = New Array;
        Try
            For Each Command In Metadata.CommonCommands Do
                EnsureLimit(Commands);
                Commands.Add(MetadataName(Command));
            EndDo;
        Except
            Gaps.Add("CommonCommands collection incomplete or unavailable");
        EndTry;
        Snapshot.Insert("common_commands", Commands);
        RequiredNames = New Array;
        RequiredNames.Add("InventoryExpense");
        RequiredNames.Add("TaxInvoice");
        For Each RequiredName In RequiredNames Do
        DocumentEntry = New Structure;
        Found = False;
        For Each Document In Metadata.Documents Do
            If Document.Name = RequiredName Then
                Found = True;
                DocumentEntry = MetadataName(Document);
                DocumentCommands = New Array;
                Templates = New Array;
                Try
                    For Each Command In Document.Commands Do
                        EnsureLimit(DocumentCommands);
                        DocumentCommands.Add(MetadataName(Command));
                    EndDo;
                Except
                    Gaps.Add(RequiredName + ".Commands unavailable");
                EndTry;
                Try
                    For Each Template In Document.Templates Do
                        EnsureLimit(Templates);
                        Templates.Add(MetadataName(Template));
                    EndDo;
                Except
                    Gaps.Add(RequiredName + ".Templates unavailable");
                EndTry;
                DocumentEntry.Insert("commands", DocumentCommands);
                DocumentEntry.Insert("templates", Templates);
            EndIf;
        EndDo;
        If Not Found Then
            Gaps.Add(RequiredName + " not found");
        EndIf;
        If RequiredName = "InventoryExpense" Then
            Snapshot.Insert("document", DocumentEntry);
        Else
            Snapshot.Insert("tax_document", DocumentEntry);
        EndIf;
        EndDo;
        Snapshot.Insert("gaps", Gaps);
        Snapshot.Insert("metadata_complete", Gaps.Count() = 0);
        Writer = New JSONWriter;
        Writer.SetString();
        WriteJSON(Writer, Snapshot);
        OutputJSON = Writer.Close();
        StatusText = "READ ONLY: metadata exported. Gaps: " + String(Gaps.Count())
            + ". Names/routes do not prove publication, print behavior or PDF support.";
    Except
        // Do not expose raw exception text or leave a stale successful export.
        OutputJSON = "";
        StatusText = "DISCOVERY FAILED [METADATA/JSON]. No business data changed.";
    EndTry;
EndProcedure

&AtServer
Function MetadataName(Item)
    Return New Structure("name", Item.Name);
EndFunction

&AtServer
Procedure EnsureLimit(Items)
    If Items.Count() >= 5000 Then
        Raise "Metadata collection safety limit";
    EndIf;
EndProcedure
