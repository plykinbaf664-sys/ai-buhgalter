"""Dedicated project-local native FirstBit UI; OData remains accounting authority."""
import asyncio
import re
import uuid
import time
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, parse_qs, unquote
from uuid import UUID

from app.domain import BackendFailure


def native_reference_id(reference: UUID) -> str:
    text=UUID(str(reference)).hex
    return text[16:]+text[12:16]+text[8:12]+text[:8]


def reference_from_native_id(value: str) -> UUID:
    if not re.fullmatch(r'[0-9a-fA-F]{32}',value):
        raise BackendFailure('firstbit_ui_reference_mismatch')
    return UUID(value[24:32]+value[20:24]+value[16:20]+value[:16])


def document_link(kind: Literal['InventoryExpense','TaxInvoice'],reference: UUID) -> str:
    if kind not in ('InventoryExpense','TaxInvoice'):
        raise BackendFailure('firstbit_ui_document_type')
    return 'e1cib/data/Document.'+kind+'?ref='+native_reference_id(reference)


def native_method_name(raw: str) -> str | None:
    # 1C's wire format can contain bare undefined in params. Inspect only the
    # fixed method-name prefix; never eval or rewrite arbitrary response data.
    match=re.match(r'\s*\{\s*"root"\s*:\s*\{\s*"name"\s*:\s*"([A-Za-z_][A-Za-z0-9_]*)"',raw.lstrip(chr(65279)))
    return match.group(1) if match else None


def native_session_rejected(payload: bytes) -> bool:
    """Recognize only the platform's pre-application session rejection."""
    import json
    try:
        node = json.loads(payload).get('exception')
        if not isinstance(node, dict) or not node.get('descr', '').startswith('Session error'):
            return False
        for _ in range(6):
            kind = node.get('#inner')
            inner = node.get('inner')
            if not isinstance(inner, dict):
                return False
            if (kind == '{http://v8.1c.ru/8.2/managed-application/seancecontextexception}SeanceContextException'
                    and inner.get('reason') == 1
                    and inner.get('descr', '').startswith('Session is not available or has been dropped')):
                return True
            node = inner
    except (ValueError, TypeError, AttributeError):
        pass
    return False


class FirstBitUI:
    def __init__(self,settings,*,private_root:Path):
        self.settings=settings
        candidate=Path(private_root)
        if not candidate.is_absolute() or candidate.is_symlink():raise ValueError('Absolute private root required')
        self.root=candidate.resolve()
        project=Path(__file__).resolve().parents[1]
        if not self.root.is_relative_to(project/'.local/firstbit'):raise ValueError('Browser state must stay in project private storage')
        self.root.mkdir(parents=True,mode=0o700,exist_ok=True)
        self._lock=asyncio.Lock()
        self._pw=self._context=self._page=None
        self._profile=None
        self._profile_tmp=None
        self._trace=[]
        self._capture_native_print=False
        self._login_submitted=False
        self._verified_document=None
        self._busy_commands=set()
        self._last_command=0.0
        self._session_failed=False
        self._generate_ack=None
        self._generate_dispatched=False
        self._generate_preflight_failed=False
        self._generate_dispatch_error=None
        self._generate_event=asyncio.Event()

    async def _launch(self,link):
        self._busy_commands.clear()
        self._session_failed=False
        from playwright.async_api import async_playwright
        self._pw=await async_playwright().start()
        import tempfile
        self._profile_tmp=tempfile.TemporaryDirectory(prefix='session-',dir=self.root)
        self._profile=Path(self._profile_tmp.name)
        self._context=await self._pw.chromium.launch_persistent_context(str(self._profile),
            headless=True,channel='chromium',chromium_sandbox=True,accept_downloads=True,service_workers="block")
        self._page=self._context.pages[0]
        self._page.set_default_timeout(25000)
        def native_command(request):
            path=urlsplit(request.url).path
            return any(part in path for part in ('/forms/','/modules/','/cmi/'))
        def command_started(request):
            if native_command(request):
                self._busy_commands.add(id(request))
                self._last_command=time.monotonic()
        def command_finished(request):
            self._busy_commands.discard(id(request))
            if native_command(request):self._last_command=time.monotonic()
        self._page.on('request',command_started)
        self._page.on('requestfinished',command_finished)
        self._page.on('requestfailed',command_finished)
        async def native_response(response):
            from urllib.parse import urlsplit
            path=urlsplit(response.url).path
            method_name=native_method_name(response.request.post_data or '') if response.request.method=='POST' else None
            if method_name=='GenerateTaxInvoice' and self._capture_native_print:
                self._generate_ack=response.status
                receipt=self.root/('native-generate-receipt-'+uuid.uuid4().hex+'.json')
                receipt.write_text(__import__('json').dumps({'method':method_name,'http_status':response.status,'at':time.time()}))
                receipt.chmod(0o600)
                self._generate_event.set()
            if (method_name == 'CheckBasisBeforeFilling' and self._capture_native_print
                    and response.status >= 400 and not self._generate_dispatched):
                if native_session_rejected(await response.body()):
                    self._generate_preflight_failed = True
                    self._generate_event.set()
            if path.endswith('/login'):
                self._trace.append({'at':round(time.monotonic(),3),'status':response.status,'resource':'login','submitted':self._login_submitted})
            if self._capture_native_print and response.request.method=='POST' and any(part in path for part in ('/forms/','/modules/')):
                try:
                    payload=await response.body()
                    if len(payload)<=2000000:
                        artifact=self.root/('print-call-'+uuid.uuid4().hex+'.private')
                        artifact.write_bytes(payload);artifact.chmod(0o600)
                        request_artifact=artifact.with_suffix('.request-private')
                        request_artifact.write_text(response.request.post_data or '');request_artifact.chmod(0o600)
                except Exception:pass
            if any(part in path for part in ('/forms/','/modules/','/cmi/')) or path.endswith('/logForm'):
                self._trace.append({'at':round(time.monotonic(),3),'status':response.status,'method':response.request.method,'resource':path.rsplit('/',1)[-1],'native_method':method_name})
                if len(self._trace)>300:self._trace.pop(0)
            if response.status>=500 and '/e1cib/' in path:
                self._session_failed=True
            if response.status>=400:
                try:
                    payload=await response.body()
                    if len(payload)<=1000000:
                        path=self.root/('native-error-'+uuid.uuid4().hex+'.private')
                        path.write_bytes(payload);path.chmod(0o600)
                except Exception:pass
        self._page.on('response',native_response)

        publication=self.settings.base_url.removesuffix('odata/standard.odata/')
        await self._page.goto(publication+'#'+link,wait_until='domcontentloaded',timeout=45000)
        login=self._page.locator('#authWindow_basic_login:visible')
        ready=self._page.locator('[id$="_Number_i0"]:visible')
        await login.or_(ready).first.wait_for(state='visible',timeout=60000)
        if await login.count():
            if urlsplit(self._page.url).netloc!=urlsplit(self.settings.base_url).netloc:
                raise BackendFailure('firstbit_ui_untrusted_origin')
            await login.click()
            await login.press('Control+a')
            await login.press_sequentially(self.settings.username.get_secret_value(),delay=15)
            password=self._page.locator('#authWindow_basic_password')
            await password.click()
            await password.press('Control+a')
            await password.press_sequentially(self.settings.password.get_secret_value(),delay=15)
            self._login_submitted=True
            await self._page.get_by_role('button',name='Log in',exact=True).click()
        await ready.wait_for(state='visible',timeout=90000)

    async def _open_document(self,kind,reference,number):
        # Only navigation/read preparation can reconnect. Actual financial
        # clicks below are one-shot and never covered by this retry.
        from playwright.async_api import TimeoutError as BrowserTimeout
        if self._session_failed and self._context is not None:
            await self.aclose()
        try:
            if (self._context is not None and not self._page.is_closed() and
                    self._verified_document==(kind,UUID(str(reference)))):
                current=urlsplit(self._page.url);expected=urlsplit(self.settings.base_url)
                if (current.scheme,current.netloc)!=(expected.scheme,expected.netloc):
                    raise BackendFailure('firstbit_ui_untrusted_origin')
                fields=self._page.locator('[id$="_Number_i0"]:visible')
                if await fields.count()==1 and await fields.input_value()==number:
                    await self._wait_commands()
                    return self._page
            return await self._open_once(kind,reference,number)
        except (BrowserTimeout,BackendFailure) as error:
            if isinstance(error,BackendFailure) and str(error) not in ('firstbit_ui_session_unavailable','firstbit_ui_command_not_ready'):
                raise
            await self.aclose()
            return await self._open_once(kind,reference,number)

    async def _open_once(self,kind,reference,number):
        link=document_link(kind,reference)
        if self._context is None:
            await self._launch(link)
        else:
            await self._page.keyboard.press('Escape')
            await self._page.get_by_title('Service and settings',exact=True).click()
            await self._page.get_by_text(re.compile(r'^Go\s+to\s+link\.\.\.$')).click()
            field=self._page.locator('[id$="_CurrentUrlContent_i0"]:visible')
            await field.wait_for(state='visible')
            await field.fill(link)
            await self._page.locator('[id$="_GotoUrl"]:visible').click()
            await field.wait_for(state='hidden')
        fields=self._page.locator('[id$="_Number_i0"]:visible')
        await fields.wait_for(state='visible',timeout=45000)
        current=urlsplit(self._page.url);expected=urlsplit(self.settings.base_url)
        if (current.scheme,current.netloc)!=(expected.scheme,expected.netloc):
            raise BackendFailure('firstbit_ui_untrusted_origin')
        if not number or await fields.count()!=1 or await fields.input_value()!=number:
            raise BackendFailure('firstbit_ui_reference_mismatch')
        await self._wait_commands()
        return self._page

    async def warm_document(self,kind,reference,number):
        async with self._lock:
            await self._open_document(kind,reference,number)
            await self._assert_reference(kind,reference)

    async def _assert_reference(self,kind,reference):
        self._verified_document=None
        await self._wait_commands()
        await self._page.locator('[id$="headerTopLine_cmd_GetURLButton"]:visible').click()
        show=self._page.locator('[id$="_btnGetURL"]:visible')
        await show.wait_for(state='visible')
        await show.click()
        field=self._page.locator('[id$="_CurrentNavPointContent_i0"]:visible')
        await field.wait_for(state='visible')
        actual=unquote(await field.input_value()).split('#',1)[-1]
        parsed=urlsplit(actual);values=parse_qs(parsed.query)
        if (parsed.path!='e1cib/data/Document.'+kind or set(values)!={'ref'}
            or len(values['ref'])!=1 or reference_from_native_id(values['ref'][0])!=UUID(str(reference))):
            raise BackendFailure('firstbit_ui_reference_mismatch')
        await self._page.keyboard.press('Escape')
        await field.wait_for(state='hidden')
        self._verified_document=(kind,UUID(str(reference)))

    async def post_document(self,kind,reference,number,before_action):
        if not callable(before_action):raise BackendFailure('firstbit_ui_missing_write_guard')
        async with self._lock:
            page=await self._open_document(kind,reference,number)
            await self._assert_reference(kind,reference)
            await self._wait_commands()
            control=page.locator('[id$="_FormPost"]:visible')
            await control.wait_for(state='visible')
            await before_action()
            await control.click()
            await page.wait_for_timeout(500)

    async def generate_tax_invoice(self,reference,number,before_action,*,before_send):
        if not callable(before_action) or not callable(before_send):
            raise BackendFailure('firstbit_ui_missing_write_guard')
        async with self._lock:
            for attempt in range(2):
                # OData verification must finish before opening a fresh native
                # session. A previous session can be invalidated by read-back.
                await self.aclose()
                await before_action()
                page=await self._open_document('InventoryExpense',reference,number)
                try:
                    await self._assert_reference('InventoryExpense',reference)
                    await self._wait_commands()
                    control=page.locator('[id$="_GenerateTaxInvoice"]:visible > a')
                    await control.wait_for(state='visible')
                    self._verified_document=None
                    self._generate_event.clear()
                    self._generate_ack=None
                    self._generate_dispatched=False
                    self._generate_preflight_failed=False
                    self._generate_dispatch_error=None

                    async def dispatch(route):
                        request=route.request
                        if (request.method != 'POST' or
                                native_method_name(request.post_data or '') != 'GenerateTaxInvoice'):
                            await route.continue_()
                            return
                        if self._generate_dispatched or self._generate_preflight_failed:
                            await route.abort()
                            return
                        try:
                            # The last durable claim gates the actual financial
                            # RPC, not its read-only CheckBasisBeforeFilling.
                            await before_send()
                            self._generate_dispatched=True
                        except Exception as error:
                            self._generate_dispatch_error=error
                            self._generate_event.set()
                            await route.abort()
                            return
                        await route.continue_()

                    await page.route('**/*',dispatch)
                    self._capture_native_print=True
                    await control.click()
                    try:
                        await asyncio.wait_for(self._generate_event.wait(),timeout=35)
                    except asyncio.TimeoutError:
                        code=('firstbit_ui_generate_not_acknowledged' if self._generate_dispatched
                              else 'firstbit_ui_generate_not_submitted')
                        raise BackendFailure(code) from None
                    if self._generate_dispatch_error is not None:
                        raise self._generate_dispatch_error
                    if self._generate_preflight_failed and not self._generate_dispatched:
                        if not attempt:
                            continue
                        raise BackendFailure('firstbit_ui_session_unavailable')
                    if self._generate_ack != 200 or not self._generate_dispatched:
                        raise BackendFailure('firstbit_ui_generate_not_acknowledged')
                    return
                finally:
                    self._capture_native_print=False
                    # Keep the dispatch gate until every pending browser task is
                    # cancelled, including delayed preflight callbacks.
                    await self.aclose()

    async def print_tax_invoice(self,reference,number,before_action):
        from playwright.async_api import TimeoutError as BrowserTimeout
        async with self._lock:
            for attempt in range(2):
                try:
                    return await self._print_once(reference,number,before_action)
                except (BrowserTimeout,BackendFailure) as error:
                    if attempt or (isinstance(error,BackendFailure) and
                            str(error) not in ('firstbit_ui_session_unavailable','firstbit_ui_command_not_ready')):
                        raise
                    await self.aclose()

    async def _print_once(self,reference,number,before_action):
        if not callable(before_action):raise BackendFailure('firstbit_ui_missing_write_guard')
        await self.aclose()
        await before_action()
        page=await self._open_document('TaxInvoice',reference,number)
        await self._assert_reference('TaxInvoice',reference)
        await self._wait_commands()
        await page.locator('[id$="_PrintSubmenu"]:visible').click()
        await page.get_by_text('Tax Invoice (EN, landscape)',exact=True).filter(visible=True).click()
        # These controls belong to 1C CommonForm.PrintDocuments, not the
        # browser's page-print dialog. Only its native PDF download is accepted.
        print_form=page.locator('[id^="form"][id$="_CurrentPrintForm"]:visible')
        await print_form.wait_for(state='visible',timeout=45000)
        await self._wait_commands()
        save=page.locator('[id^="form"][id$="_SaveButton"]:visible')
        await save.wait_for(state='visible',timeout=45000)
        formats=page.locator('[id^="form"][id$="_SelectedSaveFormats"]:visible')
        # Showing the native save dialog is read-only and safe to repeat if
        # 1C ignored an early click while initializing the Moxel control.
        for attempt in range(2):
            await save.click()
            try:
                await formats.wait_for(state='visible',timeout=8000)
                break
            except Exception:
                if attempt or self._session_failed:raise
                await self._wait_commands()
        await formats.wait_for(state='visible')
        prefix=(await formats.get_attribute('id')).removesuffix('SelectedSaveFormats')
        local=page.locator('[id="'+prefix+'SavingOption"]:visible')
        if not await local.count():raise BackendFailure('firstbit_ui_print_schema')
        if 'select' not in (await local.get_attribute('class') or '').split():
            await local.click()
        rows=formats.locator('.gridLine')
        if await rows.count()<1:raise BackendFailure('firstbit_ui_print_schema')
        selected_pdf=0
        for row in await rows.all():
            label=' '.join((await row.inner_text()).split())
            checkbox=row.locator('.checkbox')
            if await checkbox.count()!=1:raise BackendFailure('firstbit_ui_print_schema')
            is_pdf=label=='Adobe PDF document (.pdf)'
            selected_pdf+=int(is_pdf)
            checked='select' in (await checkbox.get_attribute('class') or '').split()
            if checked!=is_pdf:await checkbox.click()
        if selected_pdf!=1:raise BackendFailure('firstbit_ui_print_schema')
        archive=page.locator('[id="'+prefix+'PackToArchive"]:visible')
        if await archive.count()!=1:raise BackendFailure('firstbit_ui_print_schema')
        if 'select' in (await archive.get_attribute('class') or '').split():
            await archive.click()
        async with page.expect_download(timeout=90000) as pending:
            await page.locator('[id="'+prefix+'SaveButton"]:visible').click()
        download=await pending.value
        artifact=self.root/('tax-native-'+uuid.uuid4().hex+'.pdf')
        await download.save_as(artifact)
        artifact.chmod(0o600)
        if not 100<=artifact.stat().st_size<=20_000_000:
            raise BackendFailure('firstbit_native_pdf_size')
        content=artifact.read_bytes()
        if not content.startswith(b'%PDF-'):
            raise BackendFailure('firstbit_native_pdf_signature')
        return content

    async def _wait_commands(self):
        for attempt in range(150):
            if self._session_failed:raise BackendFailure('firstbit_ui_session_unavailable')
            if not self._busy_commands and time.monotonic()-self._last_command>=.8:
                return
            await asyncio.sleep(.2)
        raise BackendFailure('firstbit_ui_command_not_ready')

    async def aclose(self):
        try:
            if self._context is not None:
                await self._context.close()
        finally:
            self._context=self._page=None
            self._verified_document=None
            try:
                if self._pw is not None:
                    await self._pw.stop()
            finally:
                self._pw=None
                temporary=getattr(self,'_profile_tmp',None)
                if temporary is not None:
                    try:
                        temporary.cleanup()
                    finally:
                        self._profile_tmp=None
                        self._profile=None
