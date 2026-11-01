"""Native UI boundary tests use synthetic identifiers and never launch a browser."""
from uuid import UUID
import pytest
from app.domain import BackendFailure
from app.firstbit_ui import native_reference_id, reference_from_native_id, document_link, FirstBitUI


def test_standard_1c_navigation_encoding_roundtrips_without_session_data():
    reference=UUID('01234567-89ab-cdef-0123-456789abcdef')
    assert native_reference_id(reference)=='0123456789abcdefcdef89ab01234567'
    assert reference_from_native_id(native_reference_id(reference))==reference
    assert document_link('TaxInvoice',reference)=='e1cib/data/Document.TaxInvoice?ref='+native_reference_id(reference)


@pytest.mark.parametrize('value',['', '../outside', 'x'*32, '0'*31, '0'*33, '0'*32+'?module=anything'])
def test_invalid_native_identifiers_never_become_navigation(value):
    with pytest.raises(BackendFailure):reference_from_native_id(value)


def test_arbitrary_metadata_path_cannot_be_requested():
    with pytest.raises(BackendFailure):document_link('TaxInvoice?module=unsafe',UUID(int=1))


def test_browser_state_cannot_escape_project_private_storage(tmp_path):
    with pytest.raises(ValueError):
        FirstBitUI(None,private_root=tmp_path/'outside-project')
    assert not (tmp_path/'outside-project').exists()

@pytest.mark.parametrize('action',['post_document','generate_tax_invoice'])
def test_wrong_live_document_blocks_financial_action_before_provider_claim(action):
    import asyncio
    async def scenario():
        ui=FirstBitUI.__new__(FirstBitUI)
        ui._lock=asyncio.Lock()
        calls=[]
        async def opened(*args):return object()
        async def mismatch(*args):raise BackendFailure('firstbit_ui_reference_mismatch')
        async def claim():calls.append('mutation')
        ui._open_document=opened
        ui._assert_reference=mismatch
        with pytest.raises(BackendFailure):
            if action=='post_document':
                await ui.post_document('InventoryExpense',UUID(int=1),'SYNTHETIC',claim)
            else:
                await ui.generate_tax_invoice(UUID(int=1),'SYNTHETIC',claim)
        assert calls==[]
    asyncio.run(scenario())

def test_native_method_observer_handles_protocol_undefined_without_eval():
    from app.firstbit_ui import native_method_name
    assert native_method_name('{"root":{"name":"GenerateTaxInvoice","param":[undefined]}}')=='GenerateTaxInvoice'
    assert native_method_name('{"root":{"name":"CheckBasisBeforeFilling","param":[undefined]}}')=='CheckBasisBeforeFilling'
    assert native_method_name('unexpected wire data') is None
    assert native_method_name('{"root":{"name":"arbitrary;code()"}}') is None

@pytest.mark.parametrize('ack',[200,500])
def test_generation_uses_dedicated_native_command_and_never_retries_click(ack):
    import asyncio
    async def scenario():
        ui=FirstBitUI.__new__(FirstBitUI)
        ui._lock=asyncio.Lock();ui._generate_event=asyncio.Event();ui._generate_ack=None
        ui._capture_native_print=False
        selected=[];claims=[];clicks=[]
        class Control:
            async def wait_for(self,**kwargs):pass
            async def click(self):
                clicks.append('native')
                ui._generate_ack=ack;ui._generate_event.set()
        class Page:
            def locator(self,selector):
                selected.append(selector);return Control()
        async def opened(*args):return Page()
        async def verified(*args):pass
        async def claim():claims.append('claimed')
        ui._open_document=opened;ui._assert_reference=verified;ui._wait_commands=verified
        if ack==200:
            await ui.generate_tax_invoice(UUID(int=1),'SYNTHETIC',claim)
        else:
            with pytest.raises(BackendFailure):
                await ui.generate_tax_invoice(UUID(int=1),'SYNTHETIC',claim)
        assert selected==['[id$="_GenerateTaxInvoice"]:visible > a']
        assert clicks==['native'] and claims==['claimed'] and not ui._capture_native_print
    asyncio.run(scenario())
