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
                async def verified():pass
                ui.aclose=verified
                await ui.generate_tax_invoice(UUID(int=1),'SYNTHETIC',verified,before_send=claim)
        assert calls==[]
    asyncio.run(scenario())

def test_native_method_observer_handles_protocol_undefined_without_eval():
    from app.firstbit_ui import native_method_name
    assert native_method_name('{"root":{"name":"GenerateTaxInvoice","param":[undefined]}}')=='GenerateTaxInvoice'
    assert native_method_name('{"root":{"name":"CheckBasisBeforeFilling","param":[undefined]}}')=='CheckBasisBeforeFilling'
    assert native_method_name('unexpected wire data') is None
    assert native_method_name('{"root":{"name":"arbitrary;code()"}}') is None

@pytest.mark.parametrize('ack,preflight_rejected',[(200,False),(500,False),(200,True)])
def test_generation_claim_gates_real_rpc_and_only_unsent_preflight_can_reconnect(ack,preflight_rejected):
    import asyncio
    async def scenario():
        ui=FirstBitUI.__new__(FirstBitUI)
        ui._lock=asyncio.Lock();ui._generate_event=asyncio.Event()
        selected=[];events=[];clicks=[]
        class Request:
            method='POST'
            post_data='{"root":{"name":"GenerateTaxInvoice","param":[undefined]}}'
        class Route:
            request=Request()
            async def continue_(self):
                events.append('dispatch')
                ui._generate_ack=ack;ui._generate_event.set()
            async def abort(self):events.append('abort')
        class Control:
            async def wait_for(self,**kwargs):pass
            async def click(self):
                clicks.append('native')
                if preflight_rejected and len(clicks)==1:
                    ui._generate_preflight_failed=True;ui._generate_event.set()
                    return
                await page.handler(Route())
                await page.handler(Route())  # a duplicate UI request must be blocked
        class Page:
            async def route(self,pattern,handler):self.handler=handler
            def locator(self,selector):
                selected.append(selector);return Control()
        page=Page()
        async def opened(*args):events.append('open');return page
        async def verified(*args):pass
        async def closed():events.append('close')
        async def validate():events.append('validate')
        async def claim():events.append('claim')
        ui._open_document=opened;ui._assert_reference=verified;ui._wait_commands=verified;ui.aclose=closed
        if ack==200:
            await ui.generate_tax_invoice(UUID(int=1),'SYNTHETIC',validate,before_send=claim)
        else:
            with pytest.raises(BackendFailure):
                await ui.generate_tax_invoice(UUID(int=1),'SYNTHETIC',validate,before_send=claim)
        assert all(x=='[id$="_GenerateTaxInvoice"]:visible > a' for x in selected)
        assert len(clicks)==(2 if preflight_rejected else 1)
        assert events.count('claim')==events.count('dispatch')==1
        assert events.index('validate')<events.index('open')<events.index('claim')<events.index('dispatch')
        assert events[-1]=='close' and 'abort' in events and not ui._capture_native_print
    asyncio.run(scenario())


def test_native_session_rejection_requires_platform_exception_not_provider_text():
    import json
    from app.firstbit_ui import native_session_rejected
    rejection={'exception':{'descr':'Session error', '#inner':
        '{http://v8.1c.ru/8.2/managed-application/seancecontextexception}SeanceContextException',
        'inner':{'reason':1,'descr':'Session is not available or has been dropped'}}}
    assert native_session_rejected(json.dumps(rejection).encode())
    for value in ({'error':'Session is not available or has been dropped'},
                  {'exception':{'descr':'Business error','inner':rejection['exception']['inner']}},
                  {'exception':{'descr':'Session error','#inner':'BusinessException',
                                'inner':rejection['exception']['inner']}}):
        assert not native_session_rejected(json.dumps(value).encode())
    assert not native_session_rejected(b'not JSON')


def test_native_print_opens_fresh_session_only_after_live_validation():
    import asyncio
    class NavigationReached(Exception):pass
    async def scenario():
        ui=FirstBitUI.__new__(FirstBitUI);events=[]
        async def close():events.append('close')
        async def validate():events.append('validate')
        async def open_document(*args):
            events.append('open')
            raise NavigationReached()
        ui.aclose=close;ui._open_document=open_document
        with pytest.raises(NavigationReached):
            await ui._print_once(UUID(int=1),'SYNTHETIC',validate)
        assert events==['close','validate','open']
    asyncio.run(scenario())


def test_each_native_session_has_clean_private_profile_and_cleanup_is_owned(tmp_path, monkeypatch):
    import asyncio
    import playwright.async_api
    class LaunchObserved(Exception):pass
    async def scenario():
        ui=FirstBitUI.__new__(FirstBitUI)
        ui.root=tmp_path/'private';ui.root.mkdir(mode=0o700)
        old=ui.root/'profile';old.mkdir();(old/'unrelated.txt').write_text('synthetic old profile')
        ui._busy_commands=set();ui._context=ui._page=ui._pw=ui._profile_tmp=None
        paths=[]
        class Chromium:
            async def launch_persistent_context(self,path,**kwargs):
                candidate=type(tmp_path)(path);paths.append(candidate)
                assert candidate.is_dir() and candidate.parent==ui.root
                assert kwargs['chromium_sandbox'] is True and kwargs['service_workers']=='block'
                raise LaunchObserved()
        class Playwright:
            chromium=Chromium()
            async def stop(self):pass
        class Manager:
            async def start(self):return Playwright()
        monkeypatch.setattr(playwright.async_api,'async_playwright',lambda:Manager())
        for _ in range(2):
            with pytest.raises(LaunchObserved):
                await ui._launch('synthetic-link')
            await ui.aclose()
            assert not paths[-1].exists()
        assert paths[0]!=paths[1] and (old/'unrelated.txt').read_text()=='synthetic old profile'
    asyncio.run(scenario())
